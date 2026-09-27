"""Step 6 tests: TaskProfile, complexity levels, model registry and selection.

All offline. No model API calls, no Laya model load, no Blender.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import evaluation  # noqa: E402
from agents.base_agent import BaseAgent  # noqa: E402
from agents.registry import AGENT_NAMES, build_agent_registry  # noqa: E402
from conversation_state import ConversationState  # noqa: E402
from model_registry import (  # noqa: E402
    UNKNOWN,
    ModelProfile,
    ModelRegistry,
    curated_model_ids,
    default_registry,
)
from model_selector import REQUIRED_MIN_TIER, select_model  # noqa: E402
from models import known_model_ids  # noqa: E402
from router import preview, route  # noqa: E402
from routing_policy import (  # noqa: E402
    CODING_AGENT,
    GENERAL_AGENT,
    REASONING_AGENT,
    RESEARCH_AGENT,
    THREE_D_AGENT,
    WEB_AGENT,
    BaselineAgentPolicy,
)
from task_profile import (  # noqa: E402
    COMPLEXITY_LEVELS,
    LEVEL_EXPERT,
    LEVEL_SIMPLE,
    TaskProfile,
    build_task_profile,
    label_from_level,
    level_from_label,
)
from tools.registry import list_tools  # noqa: E402


def _classification(intent="coding", complexity="simple", confidence=0.8):
    return {"intent": intent, "complexity": complexity, "confidence": confidence}


def _decision(agent=CODING_AGENT, level=None, layer="laya"):
    decision = {"selected_agent": agent, "policy": layer, "decision_layer": layer,
                "reason": "test", "fallback_used": False}
    if level is not None:
        decision["complexity_level"] = level
    return decision


class _FakeAgent(BaseAgent):
    def __init__(self, name):
        self.name = name

    def run(self, prompt):
        return f"[{self.name}] handled: {prompt}"


def _fake_registry():
    return {name: _FakeAgent(name) for name in AGENT_NAMES}


# 1. TaskProfile creation
class TestTaskProfile(unittest.TestCase):
    def test_built_from_existing_classification_and_decision(self):
        registry = build_agent_registry()
        profile = build_task_profile(
            _classification("coding", "simple"), _decision(), registry[CODING_AGENT]
        )
        self.assertIsInstance(profile, TaskProfile)
        self.assertEqual(profile.intent, "coding")
        self.assertEqual(profile.capability, "coding")
        self.assertEqual(profile.output_type, "code")
        self.assertEqual(profile.decision_layer, "laya")

    def test_capability_derived_from_intent_when_no_agent_is_known(self):
        expected = {
            "general": "general", "coding": "coding", "reasoning": "reasoning",
            "research": "research", "blender": "creative_3d",
        }
        for intent, capability in expected.items():
            decision = {"policy": "test", "reason": "t"}  # no selected_agent
            profile = build_task_profile(_classification(intent), decision)
            self.assertEqual(profile.capability, capability, intent)

    def test_capability_follows_the_selected_agent_when_they_disagree(self):
        """The agent is the decision the system acts on, so it wins.

        Laya answers "which agent" and "what kind of request" separately and
        they can disagree; an inconsistent profile would mislead the model
        selector and the UI.
        """
        expected = {
            GENERAL_AGENT: "general", CODING_AGENT: "coding",
            REASONING_AGENT: "reasoning", RESEARCH_AGENT: "research",
            THREE_D_AGENT: "creative_3d",
            WEB_AGENT: "browser",
        }
        for agent, capability in expected.items():
            # intent deliberately says "general" while the agent says otherwise
            profile = build_task_profile(_classification("general"), _decision(agent))
            self.assertEqual(profile.capability, capability, agent)

    def test_required_tools_come_from_the_agent(self):
        registry = build_agent_registry()
        profile = build_task_profile(
            _classification("blender"), _decision(THREE_D_AGENT),
            registry[THREE_D_AGENT],
        )
        self.assertEqual(profile.required_tools, ("BLENDER_TOOL",))
        self.assertTrue(profile.requires_tools)  # 3D cannot be done without Blender

    def test_research_tools_are_permitted_not_required(self):
        registry = build_agent_registry()
        profile = build_task_profile(
            _classification("research"), _decision(RESEARCH_AGENT),
            registry[RESEARCH_AGENT],
        )
        self.assertIn("WEB_SEARCH_TOOL", profile.required_tools)
        self.assertFalse(profile.requires_tools)

    def test_to_dict_is_serialisable(self):
        profile = build_task_profile(_classification(), _decision())
        data = profile.to_dict()
        self.assertIsInstance(data["required_tools"], list)
        self.assertIn("complexity_name", data)


# 2. Complexity classification
class TestComplexity(unittest.TestCase):
    def test_four_levels_exist(self):
        self.assertEqual(COMPLEXITY_LEVELS, (1, 2, 3, 4))

    def test_decision_layer_level_is_preferred_over_derivation(self):
        profile = build_task_profile(
            _classification("coding", "simple"), _decision(level=LEVEL_EXPERT)
        )
        self.assertEqual(profile.complexity_level, LEVEL_EXPERT)
        self.assertEqual(profile.complexity_name, "expert")
        self.assertEqual(profile.complexity_source, "decision-layer")

    def test_derived_level_when_decision_layer_gives_none(self):
        profile = build_task_profile(_classification("coding", "complex"), _decision())
        self.assertEqual(profile.complexity_level, 3)
        self.assertEqual(profile.complexity_source, "derived")

    def test_derivation_never_claims_expert(self):
        """The keyword fallback cannot distinguish expert work - be honest."""
        for label in ("simple", "medium", "complex"):
            self.assertLess(level_from_label(label), LEVEL_EXPERT)

    def test_level_label_roundtrip_stays_valid(self):
        from classifier import COMPLEXITIES

        for level in COMPLEXITY_LEVELS:
            self.assertIn(label_from_level(level), COMPLEXITIES)

    def test_invalid_level_from_decision_is_ignored(self):
        profile = build_task_profile(
            _classification("coding", "simple"), _decision(level=99)
        )
        self.assertEqual(profile.complexity_level, LEVEL_SIMPLE)
        self.assertEqual(profile.complexity_source, "derived")


# 3 & 4. Model registry and metadata
class TestModelRegistry(unittest.TestCase):
    def test_registry_exposes_curated_and_configured_models(self):
        registry = default_registry()
        for model_id in curated_model_ids():
            self.assertIsNotNone(registry.get(model_id), model_id)
        # The configured default must always be selectable.
        from models import get_model

        self.assertIsNotNone(registry.get(get_model("general")))

    def test_unknown_metadata_is_represented_as_unknown(self):
        profile = ModelProfile("mystery-model", "gemini")
        self.assertEqual(profile.coding_strength, UNKNOWN)
        self.assertIsNone(profile.tier)
        self.assertIsNone(profile.context_tokens)
        self.assertEqual(profile.source, UNKNOWN)

    def test_unknown_model_is_never_excluded_by_complexity(self):
        profile = ModelProfile("mystery-model", "gemini")
        for level in COMPLEXITY_LEVELS:
            self.assertTrue(profile.covers_complexity(level))

    def test_unknown_context_capacity_never_disqualifies(self):
        self.assertTrue(ModelProfile("m", "gemini").supports_context(1_000_000))

    def test_every_profile_records_its_source(self):
        for profile in default_registry().all():
            self.assertTrue(profile.source)

    def test_for_provider_scopes_candidates(self):
        registry = default_registry()
        for profile in registry.for_provider("gemini"):
            self.assertEqual(profile.provider, "gemini")

    def test_known_model_ids_includes_registry_models(self):
        self.assertTrue(curated_model_ids() <= known_model_ids())


# 5 & 6. Candidate filtering and model selection
class TestModelSelection(unittest.TestCase):
    def setUp(self):
        self.registry = build_agent_registry()
        self.agent = self.registry[CODING_AGENT]

    def _select(self, level):
        profile = build_task_profile(
            _classification("coding", "complex"), _decision(level=level), self.agent
        )
        return select_model(profile, self.agent)

    def test_same_agent_gets_different_models_by_complexity(self):
        simple = self._select(1)
        expert = self._select(4)
        self.assertNotEqual(simple.model_id, expert.model_id)
        self.assertLess(simple.tier, expert.tier)

    def test_selection_respects_the_required_minimum_tier(self):
        for level in COMPLEXITY_LEVELS:
            selection = self._select(level)
            self.assertGreaterEqual(selection.tier, REQUIRED_MIN_TIER[level], level)

    def test_selected_model_covers_the_task_level(self):
        registry = default_registry()
        for level in COMPLEXITY_LEVELS:
            profile = registry.get(self._select(level).model_id)
            self.assertTrue(profile.covers_complexity(level), level)

    def test_selection_is_deterministic(self):
        self.assertEqual(self._select(3).model_id, self._select(3).model_id)

    def test_selection_is_explainable(self):
        selection = self._select(4)
        self.assertIn("complexity level 4", selection.reason.lower())
        self.assertIn(selection.model_id, selection.reason)

    def test_selection_stays_within_the_agents_provider(self):
        for level in COMPLEXITY_LEVELS:
            self.assertEqual(self._select(level).provider, self.agent.model_provider)

    def test_matched_capabilities_are_reported(self):
        self.assertIn("coding", self._select(3).matched_capabilities)

    # 14. fallbacks
    def test_fallbacks_are_offered_and_include_the_configured_model(self):
        selection = self._select(4)
        self.assertTrue(selection.fallback_models)
        self.assertIn(self.agent.model_id, selection.fallback_models)

    # 13. invalid selections rejected / degraded safely
    def test_agent_without_a_model_skips_selection_safely(self):
        selection = select_model(
            build_task_profile(_classification(), _decision()), _FakeAgent("X")
        )
        self.assertIsNone(selection.model_id)
        self.assertIn("no model configured", selection.reason)

    def test_no_capable_model_falls_back_to_the_configured_model(self):
        empty = ModelRegistry(profiles=(), seed_configured=False)
        profile = build_task_profile(
            _classification(), _decision(level=4), self.agent
        )
        selection = select_model(profile, self.agent, registry=empty)
        self.assertEqual(selection.model_id, self.agent.model_id)

    def test_pinned_strategy_keeps_the_configured_model(self):
        old = os.environ.get("MODEL_SELECTION")
        os.environ["MODEL_SELECTION"] = "pinned"
        try:
            self.assertEqual(self._select(1).model_id, self.agent.model_id)
            # ...but still upgrades when the configured model cannot cope.
            self.assertNotEqual(self._select(4).model_id, self.agent.model_id)
        finally:
            if old is None:
                os.environ.pop("MODEL_SELECTION", None)
            else:
                os.environ["MODEL_SELECTION"] = old


# 7-11. The Step 4/5 architecture must survive
class TestArchitecturePreserved(unittest.TestCase):
    CASES = [
        ("What is photosynthesis?", GENERAL_AGENT, "general"),
        ("Write a Python function to reverse a string.", CODING_AGENT, "coding"),
        ("Design a scalable microservices architecture.", REASONING_AGENT, "reasoning"),
        ("Research the advantages and disadvantages of RAG.", RESEARCH_AGENT, "research"),
        ("Create a 3D model of a wooden chair.", THREE_D_AGENT, "creative_3d"),
    ]

    def test_all_capabilities_remain_routable(self):
        for prompt, agent, capability in self.CASES:
            result = preview(prompt, policy=BaselineAgentPolicy())
            self.assertEqual(result["selected_agent"], agent, prompt)
            self.assertEqual(result["capability"], capability, prompt)

    def test_agent_selection_is_unchanged_by_model_selection(self):
        for prompt, agent, _ in self.CASES:
            with_model = preview(prompt, policy=BaselineAgentPolicy())
            self.assertEqual(with_model["selected_agent"], agent)

    def test_model_selection_never_yields_an_agent_or_tool_name(self):
        tools = set(list_tools())
        for prompt, _, _ in self.CASES:
            model = preview(prompt, policy=BaselineAgentPolicy())["selected_model"]
            self.assertNotIn(model, AGENT_NAMES)
            self.assertNotIn(model, tools)

    def test_gemini_remains_a_provider_not_an_agent(self):
        for prompt, _, _ in self.CASES:
            result = preview(prompt, policy=BaselineAgentPolicy())
            self.assertEqual(result["model_provider"], "gemini")
            self.assertNotIn("GEMINI", result["selected_agent"])

    def test_tools_remain_separate_from_agents(self):
        for tool in list_tools():
            self.assertNotIn(tool, AGENT_NAMES)
        self.assertNotIn("BLENDER_AGENT", AGENT_NAMES)

    def test_three_d_still_routes_to_three_d_agent_with_blender_tool(self):
        result = preview("Create a 3D model of a wooden chair.",
                         policy=BaselineAgentPolicy())
        self.assertEqual(result["selected_agent"], THREE_D_AGENT)
        self.assertIn("BLENDER_TOOL", result["required_tools"])
        self.assertTrue(result["requires_tools"])


# 12. Context influences the profile
class TestContextInfluence(unittest.TestCase):
    def test_context_dependent_is_false_without_history(self):
        result = preview("Create a Python API.", policy=BaselineAgentPolicy())
        self.assertFalse(result["context_dependent"])

    def test_context_dependent_is_true_with_history(self):
        state = ConversationState()
        route("Create a Python API.", policy=BaselineAgentPolicy(),
              conversation_state=state, agents=_fake_registry())
        result = preview("Now add authentication and PostgreSQL.",
                         policy=BaselineAgentPolicy(), conversation_state=state)
        self.assertTrue(result["context_dependent"])
        self.assertEqual(result["task_profile"]["context_dependent"], True)


# 15 & 16. Offline mode and UI preview still work
class TestOfflineAndRoute(unittest.TestCase):
    def test_preview_needs_no_api_key_and_returns_model_metadata(self):
        result = preview("Write a Python function to reverse a string.",
                         policy=BaselineAgentPolicy())
        for key in ("capability", "complexity_level", "selected_model",
                    "model_provider", "model_reason", "task_profile"):
            self.assertIn(key, result)
        self.assertTrue(result["preview"])

    def test_route_returns_both_legacy_and_new_fields(self):
        result = route("What is photosynthesis?", policy=BaselineAgentPolicy(),
                       agents=_fake_registry())
        for key in ("selected_agent", "intent", "complexity", "confidence",
                    "response", "capability", "complexity_level", "task_profile"):
            self.assertIn(key, result)

    def test_route_with_fake_agents_skips_model_selection_safely(self):
        result = route("What is photosynthesis?", policy=BaselineAgentPolicy(),
                       agents=_fake_registry())
        self.assertIsNone(result["selected_model"])
        self.assertTrue(result["response_success"])

    def test_real_agent_route_uses_the_selected_model(self):
        import providers

        calls = []

        def fake_complete(provider, model, prompt, system=None):
            calls.append(model)
            return "answer"

        original = providers.complete
        providers.complete = fake_complete
        try:
            result = route("Write a Python function to reverse a string.",
                           policy=BaselineAgentPolicy(),
                           agents=build_agent_registry())
        finally:
            providers.complete = original
        self.assertEqual(calls[0], result["selected_model"])


# 14. Evaluation dataset
class TestEvaluationSuite(unittest.TestCase):
    def test_dataset_covers_every_capability(self):
        capabilities = {case[1] for case in evaluation.EVAL_CASES}
        self.assertEqual(
            capabilities,
            {"general", "coding", "reasoning", "research", "creative_3d"},
        )

    def test_dataset_is_reasonably_sized(self):
        self.assertGreaterEqual(len(evaluation.EVAL_CASES), 20)

    def test_eval_runs_offline_and_reports_rows(self):
        rows = evaluation.run_eval(policy=BaselineAgentPolicy())
        self.assertEqual(len(rows), len(evaluation.EVAL_CASES))
        for row in rows:
            self.assertIn(row["selected_agent"], AGENT_NAMES)

    def test_capability_accuracy_does_not_regress(self):
        stats = evaluation.summarize(evaluation.run_eval(policy=BaselineAgentPolicy()))
        self.assertGreaterEqual(stats["capability_accuracy"], 0.85)

    def test_classifier_does_not_match_keywords_inside_words(self):
        """Regression: 'api' inside 'capital' used to route to coding."""
        from classifier import classify

        self.assertEqual(classify("What is the capital of Japan?")["intent"], "general")


if __name__ == "__main__":
    unittest.main()
