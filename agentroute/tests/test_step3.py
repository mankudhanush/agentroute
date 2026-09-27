"""Step 3 tests: policies, routing memory, outcome scoring, and router integration.

MIGRATED to the current agent taxonomy (the architecture intentionally changed:
BLENDER_AGENT -> THREE_D_AGENT + BLENDER_TOOL; FAST_AGENT -> GENERAL_AGENT /
CODING_AGENT). All behavioural coverage is preserved; only agent identities and
the baseline policy class name were updated.

All offline. Uses temporary SQLite databases - never the production routing DB.
No API key is required (agents are faked or not invoked).
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent  # noqa: E402
from classifier import classify  # noqa: E402
from conversation_state import ConversationState  # noqa: E402
from outcome import (  # noqa: E402
    FEEDBACK_NEGATIVE,
    FEEDBACK_POSITIVE,
    score_outcome,
)
from routing_memory import RoutingMemory  # noqa: E402
from routing_observation import RoutingObservation, make_task_id  # noqa: E402
from routing_policy import (  # noqa: E402
    AGENT_NAMES,
    CODING_AGENT,
    GENERAL_AGENT,
    REASONING_AGENT,
    RESEARCH_AGENT,
    THREE_D_AGENT,
    AdaptiveRoutingPolicy,
    BaselineAgentPolicy,
)
from router import route  # noqa: E402


def _temp_memory():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return RoutingMemory(path), path


def _seed(memory, agent, intent, complexity, n, success=True, score=0.9, latency=800):
    for _ in range(n):
        memory.record_observation(
            RoutingObservation(
                intent=intent,
                complexity=complexity,
                confidence=0.9,
                selected_agent=agent,
                response_success=success,
                latency_ms=latency,
                task_id="seed",
                outcome_score=score,
                policy="test",
            )
        )


class _FakeAgent(BaseAgent):
    def __init__(self, name):
        self.name = name

    def run(self, prompt):
        return f"[{self.name}] handled: {prompt}"


def _fake_registry():
    return {name: _FakeAgent(name) for name in AGENT_NAMES}


class TestBaselinePolicy(unittest.TestCase):
    def setUp(self):
        self.p = BaselineAgentPolicy()

    def test_intent_to_agent_rules(self):
        cases = [
            ("general", "simple", GENERAL_AGENT),
            ("coding", "simple", CODING_AGENT),
            ("coding", "medium", CODING_AGENT),
            ("coding", "complex", CODING_AGENT),
            ("reasoning", "complex", REASONING_AGENT),
            ("research", "medium", RESEARCH_AGENT),
            # MIGRATED: was BLENDER_AGENT.
            ("blender", "medium", THREE_D_AGENT),
        ]
        for intent, complexity, expected in cases:
            d = self.p.select_agent(intent, complexity, 0.9)
            self.assertEqual(d["selected_agent"], expected, (intent, complexity))
            self.assertEqual(d["policy"], "baseline")
            self.assertTrue(d["reason"])  # non-empty, rule-grounded

    def test_never_returns_a_blender_agent(self):
        for intent in ("general", "coding", "reasoning", "research", "blender"):
            selected = self.p.select_agent(intent, "medium", 0.9)["selected_agent"]
            self.assertNotEqual(selected, "BLENDER_AGENT")
            self.assertIn(selected, AGENT_NAMES)


class TestAdaptivePolicy(unittest.TestCase):
    def test_falls_back_when_insufficient_data(self):
        memory, path = _temp_memory()
        try:
            # Only 2 observations (< MIN_OBSERVATIONS=5) -> insufficient.
            _seed(memory, REASONING_AGENT, "coding", "medium", n=2, score=0.99)
            adaptive = AdaptiveRoutingPolicy(memory)
            d = adaptive.select_agent("coding", "medium", 0.9)
            # Baseline for coding is CODING_AGENT.
            self.assertEqual(d["selected_agent"], CODING_AGENT)
            self.assertTrue(d["fallback_used"])
            self.assertIn("Insufficient historical data", d["reason"])
        finally:
            memory.close()
            os.remove(path)

    def test_uses_history_when_enough_data(self):
        memory, path = _temp_memory()
        try:
            # REASONING has strong history; baseline would pick CODING_AGENT.
            _seed(memory, REASONING_AGENT, "coding", "medium", n=6, score=0.95)
            _seed(memory, CODING_AGENT, "coding", "medium", n=6, score=0.60)
            adaptive = AdaptiveRoutingPolicy(memory)
            d = adaptive.select_agent("coding", "medium", 0.9)
            self.assertEqual(d["selected_agent"], REASONING_AGENT)
            self.assertFalse(d["fallback_used"])
            self.assertIn("strongest measured outcome score", d["reason"])
        finally:
            memory.close()
            os.remove(path)

    def test_three_d_defers_to_specialist(self):
        # MIGRATED: was "blender defers to specialist" -> BLENDER_AGENT.
        memory, path = _temp_memory()
        try:
            d = AdaptiveRoutingPolicy(memory).select_agent("blender", "medium", 0.9)
            self.assertEqual(d["selected_agent"], THREE_D_AGENT)
            self.assertTrue(d["fallback_used"])
        finally:
            memory.close()
            os.remove(path)

    def test_adaptive_never_selects_a_tool(self):
        memory, path = _temp_memory()
        try:
            adaptive = AdaptiveRoutingPolicy(memory)
            for intent in ("general", "coding", "reasoning", "research", "blender"):
                selected = adaptive.select_agent(intent, "medium", 0.9)["selected_agent"]
                self.assertIn(selected, AGENT_NAMES)
                self.assertNotEqual(selected, "BLENDER_TOOL")
        finally:
            memory.close()
            os.remove(path)


class TestRoutingMemory(unittest.TestCase):
    def test_record_and_statistics(self):
        memory, path = _temp_memory()
        try:
            _seed(memory, GENERAL_AGENT, "general", "simple", n=3, success=True, score=0.8, latency=700)
            _seed(memory, GENERAL_AGENT, "general", "simple", n=1, success=False, score=0.0, latency=500)
            stats = memory.get_agent_statistics()[GENERAL_AGENT]
            self.assertEqual(stats["attempts"], 4)
            self.assertEqual(stats["successes"], 3)
            self.assertEqual(stats["success_rate"], round(3 / 4, 3))
            # avg score = (0.8*3 + 0.0) / 4 = 0.6
            self.assertAlmostEqual(stats["average_score"], 0.6, places=3)

            by_intent = memory.get_statistics_by_intent()
            self.assertIn("general", by_intent)
            by_ic = memory.get_statistics_by_intent_and_complexity()
            self.assertIn(GENERAL_AGENT, by_ic["general"]["simple"])
        finally:
            memory.close()
            os.remove(path)

    def test_get_observations_filters(self):
        memory, path = _temp_memory()
        try:
            _seed(memory, CODING_AGENT, "coding", "simple", n=2)
            _seed(memory, REASONING_AGENT, "reasoning", "complex", n=2)
            self.assertEqual(len(memory.get_observations()), 4)
            self.assertEqual(len(memory.get_observations(intent="coding")), 2)
            self.assertEqual(
                len(memory.get_observations(selected_agent=REASONING_AGENT)), 2
            )
        finally:
            memory.close()
            os.remove(path)


class TestOutcomeScoring(unittest.TestCase):
    def test_success_and_failure(self):
        self.assertGreater(score_outcome(True, 500), score_outcome(True, 9000))
        self.assertEqual(score_outcome(False, 500), 0.0)

    def test_feedback_adjusts(self):
        base = score_outcome(True, 500)
        self.assertGreater(score_outcome(True, 500, FEEDBACK_POSITIVE), base)
        self.assertLess(score_outcome(True, 500, FEEDBACK_NEGATIVE), base)

    def test_bounds(self):
        self.assertLessEqual(score_outcome(True, 10, FEEDBACK_POSITIVE), 1.0)
        self.assertGreaterEqual(score_outcome(False, 9000, FEEDBACK_NEGATIVE), 0.0)


class TestRouterIntegration(unittest.TestCase):
    def test_route_records_success_observation(self):
        memory, path = _temp_memory()
        try:
            result = route(
                "What is Python?",
                policy=BaselineAgentPolicy(),
                memory=memory,
                agents=_fake_registry(),
            )
            self.assertEqual(result["selected_agent"], GENERAL_AGENT)
            self.assertEqual(result["policy"], "baseline")
            self.assertTrue(result["response_success"])
            self.assertIsNotNone(result["observation_id"])
            self.assertTrue(result["routing_reason"])
            self.assertEqual(len(memory.get_observations()), 1)
        finally:
            memory.close()
            os.remove(path)

    def test_route_records_failure_observation(self):
        memory, path = _temp_memory()

        class _BoomAgent(BaseAgent):
            name = GENERAL_AGENT

            def run(self, prompt):
                from errors import AgentExecutionError

                raise AgentExecutionError("upstream failed")

        try:
            registry = _fake_registry()
            registry[GENERAL_AGENT] = _BoomAgent()
            result = route(
                "What is Python?",
                policy=BaselineAgentPolicy(),
                memory=memory,
                agents=registry,
            )
            self.assertFalse(result["response_success"])
            self.assertEqual(result["outcome_score"], 0.0)
            obs = memory.get_observations()
            self.assertEqual(len(obs), 1)
            self.assertFalse(obs[0].response_success)
        finally:
            memory.close()
            os.remove(path)

    def test_route_without_memory_does_not_persist(self):
        result = route(
            "What is Python?",
            policy=BaselineAgentPolicy(),
            agents=_fake_registry(),
        )
        self.assertIsNone(result["observation_id"])

    def test_conversation_state_records_context(self):
        state = ConversationState()
        route(
            "What is Python?",
            policy=BaselineAgentPolicy(),
            conversation_state=state,
            agents=_fake_registry(),
        )
        self.assertEqual(len(state.turns), 1)
        ctx = state.context()
        self.assertEqual(ctx["previous_intents"], ["general"])
        self.assertEqual(ctx["last_agent"], GENERAL_AGENT)


class _DecisionLayer:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self._old = os.environ.get("DECISION_LAYER")
        os.environ["DECISION_LAYER"] = self.value
        return self

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop("DECISION_LAYER", None)
        else:
            os.environ["DECISION_LAYER"] = self._old


class TestRouterHonorsAdaptiveLayer(unittest.TestCase):
    """DECISION_LAYER=adaptive still requires memory and still reads outcomes."""

    def test_adaptive_layer_uses_memory_on_the_default_route(self):
        prompt = "Write a function to sort a list."
        classified = classify(prompt)
        memory, path = _temp_memory()
        try:
            _seed(
                memory, REASONING_AGENT,
                classified["intent"], classified["complexity"], n=6, score=0.95,
            )
            _seed(
                memory, CODING_AGENT,
                classified["intent"], classified["complexity"], n=6, score=0.40,
            )
            with _DecisionLayer("adaptive"):
                result = route(prompt, memory=memory, agents=_fake_registry())
            self.assertEqual(result["policy"], "adaptive")
            self.assertEqual(result["selected_agent"], REASONING_AGENT)
            self.assertFalse(result["fallback_used"])
        finally:
            memory.close()
            os.remove(path)

    def test_adaptive_layer_without_memory_uses_baseline(self):
        with _DecisionLayer("adaptive"):
            result = route(
                "Write a function to sort a list.",
                agents=_fake_registry(),
            )
        self.assertEqual(result["policy"], "baseline")
        self.assertEqual(result["selected_agent"], CODING_AGENT)
        self.assertFalse(result["fallback_used"])

    def test_explicit_adaptive_policy_overrides_baseline_layer(self):
        prompt = "Write a function to sort a list."
        classified = classify(prompt)
        memory, path = _temp_memory()
        try:
            _seed(
                memory, REASONING_AGENT,
                classified["intent"], classified["complexity"], n=6, score=0.95,
            )
            _seed(
                memory, CODING_AGENT,
                classified["intent"], classified["complexity"], n=6, score=0.40,
            )
            with _DecisionLayer("baseline"):
                result = route(
                    prompt,
                    policy=AdaptiveRoutingPolicy(memory),
                    memory=memory,
                    agents=_fake_registry(),
                )
            self.assertEqual(result["policy"], "adaptive")
            self.assertEqual(result["selected_agent"], REASONING_AGENT)
            self.assertFalse(result["fallback_used"])
        finally:
            memory.close()
            os.remove(path)


class TestDataSafety(unittest.TestCase):
    def test_task_id_is_hash_not_prompt(self):
        prompt = "super secret prompt text"
        tid = make_task_id(prompt)
        self.assertNotIn("secret", tid)
        self.assertEqual(len(tid), 16)
        # deterministic
        self.assertEqual(tid, make_task_id(prompt))

    def test_observation_has_no_raw_prompt_field(self):
        obs = RoutingObservation(
            intent="general",
            complexity="simple",
            confidence=0.9,
            selected_agent=GENERAL_AGENT,
            response_success=True,
            latency_ms=100,
        )
        self.assertNotIn("prompt", obs.to_dict())


if __name__ == "__main__":
    unittest.main()
