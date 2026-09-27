"""Task-based model selection tests.

These prove the selector answers "which model suits THIS task?" rather than
"what tier does this complexity number map to?".
"""

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from model_registry import ModelProfile, ModelRegistry, default_registry  # noqa: E402
from model_selector import score_fit, select_model  # noqa: E402
from task_profile import (  # noqa: E402
    TaskProfile,
    count_deliverables,
    derive_requirements,
)

ALL_PROVIDERS = {"gemini", "nvidia", "groq", "openrouter"}


def _task(capability, level, output_type="text", breadth=1,
          requires_tools=False, context_dependent=False):
    return TaskProfile(
        intent=capability,
        capability=capability,
        complexity="complex",
        complexity_level=level,
        confidence=0.9,
        output_type=output_type,
        breadth=breadth,
        requires_tools=requires_tools,
        context_dependent=context_dependent,
    )


def _agent(provider="gemini", model_id="gemini-flash-latest"):
    return SimpleNamespace(model_provider=provider, model_id=model_id,
                           available_tools=())


class TestRequirementsAreMoreThanComplexity(unittest.TestCase):
    def test_analysis_at_moderate_level_is_not_latency_sensitive(self):
        """A trade-off analysis is analytical work even when labelled L2."""
        req = derive_requirements(_task("reasoning", 2, output_type="analysis"))
        self.assertTrue(req.needs_deep_reasoning)
        self.assertFalse(req.latency_sensitive)
        self.assertGreaterEqual(req.demand_tier, 2)

    def test_simple_factual_question_is_latency_sensitive(self):
        req = derive_requirements(_task("general", 1))
        self.assertTrue(req.latency_sensitive)
        self.assertEqual(req.demand_tier, 1)

    def test_breadth_raises_demand_at_the_same_complexity(self):
        narrow = derive_requirements(_task("coding", 2, output_type="code", breadth=1))
        broad = derive_requirements(_task("coding", 2, output_type="code", breadth=9))
        self.assertGreater(broad.demand_tier, narrow.demand_tier)
        self.assertTrue(broad.needs_long_context)

    def test_executed_artifact_raises_demand_and_disables_latency_tradeoff(self):
        req = derive_requirements(
            _task("creative_3d", 2, output_type="blender_script", requires_tools=True)
        )
        self.assertTrue(req.needs_code_generation)
        self.assertTrue(req.needs_creative)
        self.assertFalse(req.latency_sensitive)
        self.assertGreaterEqual(req.demand_tier, 2)

    def test_research_synthesis_demands_more_than_the_floor(self):
        req = derive_requirements(_task("research", 2, output_type="report"))
        self.assertTrue(req.needs_research_synthesis)
        self.assertGreaterEqual(req.demand_tier, 2)

    def test_deliverable_counting_is_structural(self):
        self.assertEqual(count_deliverables("What is a Python variable?"), 1)
        self.assertGreaterEqual(
            count_deliverables("Build a backend with auth, Postgres, Redis, "
                               "logging, Docker and monitoring."), 5)
        self.assertEqual(count_deliverables(None), 1)


class TestSelectionIsTaskDriven(unittest.TestCase):
    """The headline requirement: complexity alone must not decide the model."""

    def setUp(self):
        self.reg = default_registry()

    def _pick(self, capability, level, **kw):
        return select_model(_task(capability, level, **kw), _agent(),
                            registry=self.reg, available_providers=ALL_PROVIDERS)

    def test_same_complexity_different_capability_can_pick_different_models(self):
        general = self._pick("general", 1)
        coding = self._pick("coding", 1, output_type="code")
        self.assertNotEqual(general.model_id, coding.model_id)

    def test_complex_coding_and_complex_reasoning_differ(self):
        """Both L3, different requirements - must be free to choose differently."""
        coding = self._pick("coding", 3, output_type="code", breadth=9)
        reasoning = self._pick("reasoning", 3, output_type="analysis")
        self.assertNotEqual(coding.model_id, reasoning.model_id)

    def test_different_complexity_may_share_a_model_when_sufficient(self):
        """Sufficiency, not novelty: the same model may legitimately win twice."""
        a = self._pick("reasoning", 2, output_type="analysis")
        b = self._pick("reasoning", 2, output_type="analysis", context_dependent=True)
        self.assertEqual(a.model_id, b.model_id)

    def test_every_selection_reports_why(self):
        selection = self._pick("reasoning", 3, output_type="analysis")
        self.assertTrue(selection.fit_breakdown)
        self.assertIsNotNone(selection.fit_score)
        self.assertIn(selection.model_id, selection.reason)
        self.assertTrue(selection.requirements)

    def test_selection_is_deterministic(self):
        first = self._pick("coding", 3, output_type="code")
        second = self._pick("coding", 3, output_type="code")
        self.assertEqual(first.model_id, second.model_id)


class TestOrderingIsNotAlphabetical(unittest.TestCase):
    """Model id is a determinism guard only, never a reason to prefer a model."""

    def test_a_worse_fitting_model_does_not_win_by_name(self):
        early_but_poor = ModelProfile(
            "aaa/unverified-weak", "gemini", tier=1, complexity_min=1,
            complexity_max=4, capabilities=frozenset({"reasoning"}),
            availability="listed", source="test")
        later_but_good = ModelProfile(
            "zzz/verified-strong", "gemini", tier=3, complexity_min=1,
            complexity_max=4, capabilities=frozenset({"reasoning"}),
            specializations=frozenset({"reasoning"}),
            availability="verified", source="test")
        registry = ModelRegistry(profiles=(early_but_poor, later_but_good),
                                 seed_configured=False)
        selection = select_model(
            _task("reasoning", 4, output_type="analysis"),
            _agent(model_id="zzz/verified-strong"),
            registry=registry, available_providers={"gemini"})
        self.assertEqual(selection.model_id, "zzz/verified-strong")

    def test_name_only_breaks_genuine_ties(self):
        """Two identical models: something must still be chosen, reproducibly."""
        common = dict(provider="gemini", tier=2, complexity_min=1, complexity_max=4,
                      capabilities=frozenset({"reasoning"}), availability="verified",
                      source="test")
        registry = ModelRegistry(
            profiles=(ModelProfile("bbb/twin", **common),
                      ModelProfile("aaa/twin", **common)),
            seed_configured=False)
        picks = {
            select_model(_task("reasoning", 2, output_type="analysis"),
                         _agent(model_id="aaa/twin"), registry=registry,
                         available_providers={"gemini"}).model_id
            for _ in range(3)
        }
        self.assertEqual(len(picks), 1)


class TestScoringSignals(unittest.TestCase):
    def setUp(self):
        self.req = derive_requirements(_task("coding", 2, output_type="code"))

    def test_verified_beats_listed_at_equal_tier(self):
        verified = ModelProfile("v/model", "gemini", tier=1, capabilities=frozenset({"coding"}),
                                availability="verified", source="test")
        listed = ModelProfile("l/model", "gemini", tier=1, capabilities=frozenset({"coding"}),
                              availability="listed", source="test")
        self.assertGreater(
            score_fit(verified, self.req, None, None).score,
            score_fit(listed, self.req, None, None).score,
        )

    def test_underpowered_model_scores_below_a_right_sized_one(self):
        req = derive_requirements(_task("reasoning", 4, output_type="analysis"))
        weak = ModelProfile("w/model", "gemini", tier=1, complexity_max=4,
                            capabilities=frozenset({"reasoning"}),
                            availability="verified", source="test")
        right = ModelProfile("r/model", "gemini", tier=3, complexity_max=4,
                             capabilities=frozenset({"reasoning"}),
                             availability="verified", source="test")
        self.assertGreater(score_fit(right, req, None, None).score,
                           score_fit(weak, req, None, None).score)

    def test_vendor_specialization_helps_only_the_matching_task(self):
        coder = ModelProfile("c/model", "gemini", tier=1,
                             capabilities=frozenset({"general", "coding", "reasoning"}),
                             specializations=frozenset({"coding"}),
                             availability="verified", source="test")
        coding_req = self.req
        research_req = derive_requirements(_task("research", 2, output_type="report"))
        coding_score = score_fit(coder, coding_req, None, None).score
        research_score = score_fit(coder, research_req, None, None).score
        self.assertGreater(coding_score, research_score)

    def test_speed_only_counts_when_latency_matters(self):
        fast = ModelProfile("f/model", "gemini", tier=1, speed="fast",
                            capabilities=frozenset({"general"}),
                            availability="verified", source="test")
        quick_task = derive_requirements(_task("general", 1))
        deep_task = derive_requirements(_task("reasoning", 3, output_type="analysis"))
        self.assertTrue(quick_task.latency_sensitive)
        self.assertFalse(deep_task.latency_sensitive)
        self.assertIn("fast", " ".join(score_fit(fast, quick_task, None, None).breakdown))


if __name__ == "__main__":
    unittest.main()
