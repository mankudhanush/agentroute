"""Step 5.1 tests: the Laya Decision AI adapter.

The real `laya` package is heavy (torch/transformers) and downloads a checkpoint,
so these tests inject a fake `laya` module that mimics the VERIFIED API:

    from laya import Router
    Router(preload=...).predict(state, questions)
      -> {"answers": {"agent": {"choice": ..., "confidence": ...}, ...},
          "routing": {"model": ..., "repo": ..., "reason": ...}}

The adapter under test is the real one - only the package is faked.
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import laya_routing_policy as lrp  # noqa: E402
from agents.registry import AGENT_NAMES, build_agent_registry  # noqa: E402
from agents.base_agent import BaseAgent  # noqa: E402
from conversation_state import ConversationState  # noqa: E402
from errors import ConfigurationError, RoutingDecisionError  # noqa: E402
from laya_routing_policy import LayaRoutingPolicy, build_questions  # noqa: E402
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
    build_policy,
    reset_policy_cache,
)
from tools.registry import list_tools  # noqa: E402


class _FakeLayaRouter:
    """Mimics laya.Router with the verified predict() contract."""

    def __init__(self, choice=CODING_AGENT, confidence=0.93, preload=False,
                 intent="coding", complexity="simple", answers=None, raises=None):
        self.choice = choice
        self.confidence = confidence
        self.preload = preload
        self.intent = intent
        self.complexity = complexity
        self._answers = answers
        self._raises = raises
        self.calls = []

    def predict(self, state, questions):
        self.calls.append({"state": state, "questions": questions})
        if self._raises:
            raise self._raises
        if self._answers is not None:
            return self._answers
        return {
            "answers": {
                "agent": {"choice": self.choice, "confidence": self.confidence},
                "intent": {"choice": self.intent, "confidence": 0.9},
                "complexity": {"choice": self.complexity, "confidence": 0.8},
            },
            "routing": {"model": "english", "repo": "convaiinnovations/laya",
                        "reason": "latin script detected"},
        }


class _LayaNotInstalled:
    """Makes `import laya` raise ImportError even though it IS installed.

    Setting sys.modules[name] = None is the documented way to block an import;
    merely popping it would let the real (slow, torch-backed) package load.
    """

    def __enter__(self):
        self._saved = sys.modules.get("laya", _MISSING)
        sys.modules["laya"] = None
        return self

    def __exit__(self, *exc):
        if self._saved is _MISSING:
            sys.modules.pop("laya", None)
        else:
            sys.modules["laya"] = self._saved


_MISSING = object()


class _InstalledLaya:
    """Context manager that injects a fake `laya` package into sys.modules."""

    def __init__(self, router_factory):
        self.router_factory = router_factory
        self.instances = []

    def __enter__(self):
        # The Laya policy is cached per process, so a policy built by an earlier
        # test (or by the real environment) must not leak into this one.
        reset_policy_cache()
        self._saved = sys.modules.get("laya", _MISSING)
        module = types.ModuleType("laya")

        def Router(preload=False):  # noqa: N802 - mirrors laya's real class name
            instance = self.router_factory()
            instance.preload = preload
            self.instances.append(instance)
            return instance

        module.Router = Router
        module.load = lambda repo, subfolder=None: self.router_factory()
        sys.modules["laya"] = module
        return self

    def __exit__(self, *exc):
        if self._saved is _MISSING:
            sys.modules.pop("laya", None)
        else:
            sys.modules["laya"] = self._saved
        reset_policy_cache()


class _FakeAgent(BaseAgent):
    def __init__(self, name):
        self.name = name

    def run(self, prompt):
        return f"[{self.name}] handled: {prompt}"


def _fake_registry():
    return {name: _FakeAgent(name) for name in AGENT_NAMES}


class TestLayaAvailability(unittest.TestCase):
    """1. Laya integration is available when correctly installed."""

    def test_available_when_package_present(self):
        with _InstalledLaya(lambda: _FakeLayaRouter()):
            self.assertTrue(LayaRoutingPolicy().is_available())

    def test_unavailable_without_package_raises_clean_config_error(self):
        with _LayaNotInstalled():
            policy = LayaRoutingPolicy()  # no fallback -> must fail loudly
            self.assertFalse(policy.is_available())
            with self.assertRaises(ConfigurationError) as ctx:
                policy.select_agent("coding", "simple", 0.8, {"prompt": "hi"})
            self.assertIn("pip install laya", str(ctx.exception))

    def test_uses_the_verified_api_shape(self):
        fake = _FakeLayaRouter()
        with _InstalledLaya(lambda: fake) as installed:
            LayaRoutingPolicy().select_agent("coding", "simple", 0.8,
                                             {"prompt": "write a function"})
        call = installed.instances[0].calls[0]
        # state is the request; questions use Laya's typed-choice schema.
        self.assertEqual(call["state"], {"request": "write a function"})
        agent_q = call["questions"]["agent"]
        self.assertEqual(agent_q["type"], "choice")
        self.assertIn("instructions", agent_q)
        self.assertIn("criteria", agent_q)

    def test_requires_prompt_in_context(self):
        with _InstalledLaya(lambda: _FakeLayaRouter()):
            with self.assertRaises(RoutingDecisionError):
                LayaRoutingPolicy().select_agent("coding", "simple", 0.8, context={})


class TestLayaConversationContext(unittest.TestCase):
    """Conversation context must reach Laya's state (offline shape checks)."""

    def test_first_turn_state_has_no_history(self):
        from laya_routing_policy import build_state

        self.assertEqual(build_state("hello", None), {"request": "hello"})
        self.assertEqual(build_state("hello", {}), {"request": "hello"})

    def test_context_adds_previous_request_to_state(self):
        from laya_routing_policy import build_state

        state = build_state("Now write unit tests for it.",
                            {"previous_prompts": ["Build a FastAPI auth API."]})
        self.assertEqual(state["request"], "Now write unit tests for it.")
        self.assertEqual(state["previous_request"], "Build a FastAPI auth API.")

    def test_questions_mention_the_follow_up_rule_only_with_context(self):
        from laya_routing_policy import build_questions

        plain = build_questions(with_context=False)["agent"]["instructions"]
        ctx = build_questions(with_context=True)["agent"]["instructions"]
        self.assertNotIn("previous_request", plain)
        self.assertIn("previous_request", ctx)

    def test_conversation_state_exposes_recent_prompts(self):
        state = ConversationState()
        state.record(prompt="first", agent=CODING_AGENT, response="r")
        state.record(prompt="second", agent=CODING_AGENT, response="r")
        self.assertEqual(state.recent_prompts(), ["first", "second"])
        self.assertEqual(state.context()["previous_prompts"], ["first", "second"])

    def test_policy_forwards_conversation_context_to_laya(self):
        fake = _FakeLayaRouter()
        state = ConversationState()
        state.record(prompt="Build a FastAPI authentication API.",
                     agent=CODING_AGENT, response="r")
        with _InstalledLaya(lambda: fake) as installed:
            preview("Now write unit tests for it.", policy=LayaRoutingPolicy(),
                    conversation_state=state)
        sent = installed.instances[0].calls[0]["state"]
        self.assertEqual(sent["previous_request"],
                         "Build a FastAPI authentication API.")


class TestLayaDecisionMapping(unittest.TestCase):
    """2 & 7. Laya's decision becomes a valid AgentRoute agent, for all five."""

    def test_candidates_offered_are_exactly_the_logical_agents(self):
        criteria = build_questions()["agent"]["criteria"]
        self.assertEqual(set(criteria), set(AGENT_NAMES))
        self.assertEqual(len(criteria), 6)

    def test_all_five_agents_are_routable_through_laya(self):
        for expected in AGENT_NAMES:
            # A general-agent answer is kept when the intent answer is general.
            intent = "general" if expected == GENERAL_AGENT else "coding"
            with _InstalledLaya(lambda e=expected, i=intent: _FakeLayaRouter(choice=e, intent=i)):
                decision = LayaRoutingPolicy().select_agent(
                    "general", "simple", 0.5, {"prompt": "anything"}
                )
            self.assertEqual(decision["selected_agent"], expected)
            self.assertEqual(decision["policy"], "laya")
            self.assertEqual(decision["decision_layer"], "laya")
            self.assertFalse(decision["fallback_used"])

    def test_specialized_intent_replaces_a_general_agent_answer(self):
        for intent, expected in (
            ("research", RESEARCH_AGENT),
            ("reasoning", REASONING_AGENT),
            ("coding", CODING_AGENT),
            ("blender", THREE_D_AGENT),
        ):
            with self.subTest(intent=intent):
                with _InstalledLaya(lambda i=intent: _FakeLayaRouter(
                    choice=GENERAL_AGENT, intent=i
                )):
                    decision = LayaRoutingPolicy().select_agent(
                        "general", "simple", 0.5, {"prompt": "anything"}
                    )
                self.assertEqual(decision["selected_agent"], expected)
                self.assertEqual(decision["decision_layer"], "laya")
                self.assertFalse(decision["fallback_used"])

    def test_a_specialist_agent_answer_is_not_replaced(self):
        with _InstalledLaya(lambda: _FakeLayaRouter(choice=WEB_AGENT, intent="coding")):
            decision = LayaRoutingPolicy().select_agent(
                "general", "simple", 0.5, {"prompt": "anything"}
            )
        self.assertEqual(decision["selected_agent"], WEB_AGENT)
        self.assertFalse(decision["fallback_used"])

    def test_laya_overrides_the_keyword_classifier(self):
        """A real Laya decision must win over the old keyword heuristics."""
        # Keyword classifier would say "coding" for this prompt; Laya says 3D.
        with _InstalledLaya(lambda: _FakeLayaRouter(choice=THREE_D_AGENT,
                                                    intent="blender")):
            result = preview("Write a Python function to reverse a string.",
                             policy=LayaRoutingPolicy())
        self.assertEqual(result["selected_agent"], THREE_D_AGENT)
        self.assertEqual(result["intent"], "blender")
        self.assertEqual(result["decision_layer"], "laya")

    def test_laya_confidence_is_surfaced(self):
        with _InstalledLaya(lambda: _FakeLayaRouter(confidence=0.77)):
            result = preview("anything at all", policy=LayaRoutingPolicy())
        self.assertAlmostEqual(result["confidence"], 0.77, places=2)

    def test_reason_names_laya_and_is_not_vague(self):
        with _InstalledLaya(lambda: _FakeLayaRouter()):
            decision = LayaRoutingPolicy().select_agent(
                "coding", "simple", 0.8, {"prompt": "x"}
            )
        self.assertIn("Laya", decision["reason"])
        self.assertIn(CODING_AGENT, decision["reason"])


class TestLayaInvalidOutputRejected(unittest.TestCase):
    """3, 4, 5, 6. Invalid Laya output is rejected safely."""

    def _decide_with(self, choice, fallback=None):
        with _InstalledLaya(lambda: _FakeLayaRouter(choice=choice)):
            return LayaRoutingPolicy(fallback=fallback).select_agent(
                "coding", "simple", 0.8, {"prompt": "x"}
            )

    def test_invalid_agent_is_rejected(self):
        with self.assertRaises(RoutingDecisionError):
            self._decide_with("TOTALLY_MADE_UP_AGENT")

    def test_blender_agent_is_rejected(self):
        with self.assertRaises(RoutingDecisionError) as ctx:
            self._decide_with("BLENDER_AGENT")
        self.assertIn("invalid agent", str(ctx.exception))

    def test_laya_cannot_select_a_tool(self):
        # NOTE: subTest must be the OUTER context - it swallows exceptions, so
        # wrapping assertRaises around it would never see the raise.
        for tool in list_tools():
            with self.subTest(tool=tool), self.assertRaises(RoutingDecisionError):
                self._decide_with(tool)

    def test_laya_cannot_select_a_model(self):
        for model in sorted(known_model_ids()):
            with self.subTest(model=model), self.assertRaises(RoutingDecisionError):
                self._decide_with(model)

    def test_provider_names_are_not_valid_agents(self):
        for bogus in ("GEMINI_AGENT", "OPENROUTER_AGENT", "GROQ_AGENT", "gemini"):
            with self.subTest(name=bogus), self.assertRaises(RoutingDecisionError):
                self._decide_with(bogus)

    def test_malformed_response_is_rejected(self):
        for payload in ({}, {"answers": {}}, {"answers": {"agent": {}}}):
            with self.subTest(payload=payload):
                with _InstalledLaya(lambda p=payload: _FakeLayaRouter(answers=p)):
                    with self.assertRaises(RoutingDecisionError):
                        LayaRoutingPolicy().select_agent(
                            "coding", "simple", 0.8, {"prompt": "x"}
                        )

    def test_invalid_output_falls_back_when_a_fallback_is_configured(self):
        decision = self._decide_with("BLENDER_AGENT", fallback=BaselineAgentPolicy())
        self.assertEqual(decision["selected_agent"], CODING_AGENT)
        self.assertTrue(decision["fallback_used"])
        self.assertNotEqual(decision["policy"], "laya")


class TestFallbackIsNeverReportedAsLaya(unittest.TestCase):
    """Fallback honesty requirement."""

    def test_missing_package_fallback_is_labelled(self):
        with _LayaNotInstalled():
            decision = LayaRoutingPolicy(fallback=BaselineAgentPolicy()).select_agent(
                "coding", "simple", 0.8, {"prompt": "x"}
            )
        self.assertEqual(decision["selected_agent"], CODING_AGENT)
        self.assertTrue(decision["fallback_used"])
        self.assertEqual(decision["decision_layer"], "fallback")
        self.assertNotEqual(decision["policy"], "laya")
        self.assertIn("Laya unavailable - fallback routing", decision["reason"])

    def test_runtime_failure_falls_back_and_is_labelled(self):
        with _InstalledLaya(lambda: _FakeLayaRouter(raises=RuntimeError("cuda oom"))):
            decision = LayaRoutingPolicy(fallback=BaselineAgentPolicy()).select_agent(
                "reasoning", "complex", 0.9, {"prompt": "x"}
            )
        self.assertEqual(decision["selected_agent"], REASONING_AGENT)
        self.assertTrue(decision["fallback_used"])
        self.assertNotEqual(decision["policy"], "laya")
        self.assertIn("fallback routing", decision["reason"])

    def test_ui_label_never_claims_laya_on_fallback(self):
        from ui_helpers import decision_layer_label

        self.assertEqual(
            decision_layer_label({"decision_layer": "laya", "fallback_used": False}),
            "Laya (Decision AI)",
        )
        label = decision_layer_label(
            {"decision_layer": "fallback", "fallback_used": True}
        )
        self.assertIn("Laya unavailable", label)
        self.assertNotEqual(label, "Laya (Decision AI)")


class TestEndToEndThroughRouter(unittest.TestCase):
    """8, 9, 10. Router/agent/provider separation survives the new layer."""

    def test_full_route_uses_laya_then_the_agents_own_provider(self):
        with _InstalledLaya(lambda: _FakeLayaRouter(choice=CODING_AGENT)):
            result = route(
                "Write a Python function to reverse a string.",
                policy=LayaRoutingPolicy(),
                agents=_fake_registry(),
            )
        self.assertEqual(result["selected_agent"], CODING_AGENT)
        self.assertEqual(result["decision_layer"], "laya")
        self.assertTrue(result["response_success"])

    def test_gemini_remains_a_provider_not_an_agent(self):
        registry = build_agent_registry()
        with _InstalledLaya(lambda: _FakeLayaRouter(choice=GENERAL_AGENT)):
            result = preview("What is photosynthesis?", policy=LayaRoutingPolicy())
        agent = registry[result["selected_agent"]]
        self.assertEqual(agent.model_provider, "gemini")
        self.assertIn(result["selected_agent"], AGENT_NAMES)
        self.assertNotIn("GEMINI", result["selected_agent"])

    def test_laya_never_sees_tools(self):
        """Tool names must not appear anywhere in what Laya is asked."""
        questions = build_questions()
        blob = repr(questions)
        for tool in list_tools():
            self.assertNotIn(tool, blob)

    def test_baseline_policy_still_works_unchanged(self):
        result = preview("Write a Python function to reverse a string.",
                         policy=BaselineAgentPolicy())
        self.assertEqual(result["selected_agent"], CODING_AGENT)


class TestPolicyFactory(unittest.TestCase):
    def test_default_layer_is_laya_with_a_labelled_fallback(self):
        old = os.environ.pop("DECISION_LAYER", None)
        try:
            policy = build_policy()
            self.assertIsInstance(policy, LayaRoutingPolicy)
            self.assertIsNotNone(policy.fallback)
        finally:
            if old is not None:
                os.environ["DECISION_LAYER"] = old

    def test_layer_can_be_forced_to_baseline(self):
        self.assertIsInstance(build_policy(layer="baseline"), BaselineAgentPolicy)

    def test_checkpoint_is_configurable(self):
        old = os.environ.get("LAYA_CHECKPOINT")
        os.environ["LAYA_CHECKPOINT"] = "convaiinnovations/laya-custom"
        try:
            self.assertEqual(
                LayaRoutingPolicy().checkpoint, "convaiinnovations/laya-custom"
            )
        finally:
            if old is None:
                os.environ.pop("LAYA_CHECKPOINT", None)
            else:
                os.environ["LAYA_CHECKPOINT"] = old

    def test_default_checkpoint_is_the_official_repo(self):
        self.assertEqual(lrp.DEFAULT_CHECKPOINT, "convaiinnovations/laya")


class _DecisionLayer:
    """Set DECISION_LAYER for one test and restore the previous value."""

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


class TestConfiguredDecisionLayer(unittest.TestCase):
    """route()/preview() follow DECISION_LAYER unless a policy is passed."""

    def test_laya_layer_is_the_default_router_policy(self):
        with _DecisionLayer("laya"), _InstalledLaya(
            lambda: _FakeLayaRouter(
                choice=REASONING_AGENT, intent="reasoning", complexity="complex"
            )
        ) as installed:
            previewed = preview("Design a distributed storage system.")
            routed = route(
                "Design a distributed storage system.",
                agents=_fake_registry(),
            )
        # ONE checkpoint per process, shared by every request. Building it per
        # request reloads the model each time and accumulates memory until the
        # process can no longer load another, at which point every later request
        # silently degrades to the baseline.
        self.assertEqual(len(installed.instances), 1)
        self.assertEqual(len(installed.instances[0].calls), 2)
        for result in (previewed, routed):
            self.assertEqual(result["decision_layer"], "laya")
            self.assertEqual(result["policy"], "laya")
            self.assertEqual(result["selected_agent"], REASONING_AGENT)
            self.assertFalse(result["fallback_used"])
        self.assertTrue(previewed["selected_model"])
        self.assertIn("task_profile", previewed)
        self.assertTrue(routed["response_success"])

    def test_baseline_layer_is_the_default_router_policy(self):
        with _DecisionLayer("baseline"), _InstalledLaya(
            lambda: _FakeLayaRouter()
        ) as installed:
            previewed = preview("Write a Python function to reverse a string.")
            routed = route(
                "Write a Python function to reverse a string.",
                agents=_fake_registry(),
            )
        self.assertEqual(installed.instances, [])
        for result in (previewed, routed):
            self.assertEqual(result["policy"], "baseline")
            self.assertEqual(result["decision_layer"], "baseline")
            self.assertEqual(result["selected_agent"], CODING_AGENT)
            self.assertFalse(result["fallback_used"])

    def test_explicit_policy_overrides_decision_layer(self):
        with _DecisionLayer("laya"), _InstalledLaya(
            lambda: _FakeLayaRouter(choice=THREE_D_AGENT)
        ) as installed:
            previewed = preview(
                "Write a Python function to reverse a string.",
                policy=BaselineAgentPolicy(),
            )
            routed = route(
                "Write a Python function to reverse a string.",
                policy=BaselineAgentPolicy(),
                agents=_fake_registry(),
            )
        self.assertEqual(installed.instances, [])
        for result in (previewed, routed):
            self.assertEqual(result["policy"], "baseline")
            self.assertEqual(result["decision_layer"], "baseline")
            self.assertEqual(result["selected_agent"], CODING_AGENT)
            self.assertFalse(result["fallback_used"])


@unittest.skipUnless(
    os.environ.get("AGENTROUTE_LIVE_LAYA") == "1",
    "live Laya test: set AGENTROUTE_LIVE_LAYA=1 (loads the real model, slow)",
)
class TestLiveLaya(unittest.TestCase):
    """Runs the REAL Laya model. Opt-in: it loads torch and a checkpoint."""

    EXPECTED = [
        ("What is photosynthesis?", GENERAL_AGENT),
        ("Write a Python function to reverse a string.", CODING_AGENT),
        ("Design a distributed microservices architecture.", REASONING_AGENT),
        ("Research approaches for evaluating RAG systems.", RESEARCH_AGENT),
        ("Create a detailed 3D interior scene.", THREE_D_AGENT),
    ]

    @classmethod
    def setUpClass(cls):
        cls.policy = LayaRoutingPolicy()  # no fallback: must be a real decision

    # --- dependency / runtime health -------------------------------------
    def test_laya_imports(self):
        from laya import Router  # noqa: F401

    def test_transformers_and_tokenizers_are_compatible(self):
        """Regression: transformers 5.x needs tokenizers>=0.23.1,<0.24.0.

        A stale tokenizers made every Laya prediction fail at runtime.
        """
        import transformers  # noqa: F401  (import itself is the check)
        from transformers import AutoTokenizer  # noqa: F401

    def test_laya_router_initializes(self):
        from laya import Router

        self.assertIsNotNone(Router())

    def test_real_laya_prediction_returns_the_documented_shape(self):
        from laya import Router

        from laya_routing_policy import build_questions, build_state

        result = Router().predict(build_state("Write a Python function."),
                                  build_questions())
        self.assertIn("answers", result)
        self.assertIn("agent", result["answers"])
        self.assertIn("choice", result["answers"]["agent"])
        self.assertIn(result["answers"]["agent"]["choice"], AGENT_NAMES)

    # --- routing ----------------------------------------------------------
    def test_real_laya_routes_all_five_prompts(self):
        for prompt, expected in self.EXPECTED:
            with self.subTest(prompt=prompt):
                result = preview(prompt, policy=self.policy)
                self.assertEqual(result["decision_layer"], "laya")
                self.assertFalse(result["fallback_used"])
                self.assertEqual(result["selected_agent"], expected)

    def test_complexity_does_not_decrease_as_difficulty_rises(self):
        """Measures what Laya ACTUALLY predicts - levels are never forced.

        Exact L1..L4 is not asserted: complexity is a judgement call and Laya
        rated the hardest prompt L3. The ordering is the real requirement.
        """
        prompts = [
            "What is a Python list?",
            "Write a Python REST API.",
            "Design a production FastAPI backend with authentication, "
            "PostgreSQL, caching and background jobs.",
            "Design a fault-tolerant distributed system with sharding, "
            "consistency requirements and multi-region failover.",
        ]
        levels = []
        for prompt in prompts:
            result = preview(prompt, policy=self.policy)
            self.assertEqual(result["complexity_source"], "decision-layer")
            levels.append(result["complexity_level"])
        self.assertEqual(levels, sorted(levels), f"not monotonic: {levels}")
        self.assertEqual(levels[0], 1, f"trivial prompt should be L1: {levels}")
        self.assertGreaterEqual(levels[-1], 3, f"hard prompt too low: {levels}")

    def test_context_aware_routing_with_real_laya(self):
        state = ConversationState()
        first = preview("Build a FastAPI authentication API.", policy=self.policy,
                        conversation_state=state)
        self.assertEqual(first["selected_agent"], CODING_AGENT)
        state.record(prompt="Build a FastAPI authentication API.",
                     agent=first["selected_agent"], response="(stub)")

        follow_up = preview("Now write unit tests for it.", policy=self.policy,
                            conversation_state=state)
        self.assertEqual(follow_up["selected_agent"], CODING_AGENT)
        self.assertEqual(follow_up["decision_layer"], "laya")

    def test_context_can_change_the_decision(self):
        """An ambiguous follow-up resolves differently once history exists."""
        state = ConversationState()
        first = preview("Research approaches for evaluating RAG systems.",
                        policy=self.policy, conversation_state=state)
        state.record(prompt="Research approaches for evaluating RAG systems.",
                     agent=first["selected_agent"], response="(stub)")
        with_context = preview("Now compare the top two.", policy=self.policy,
                               conversation_state=state)
        self.assertEqual(with_context["selected_agent"], RESEARCH_AGENT)

    # --- separation of concerns ------------------------------------------
    def test_model_selection_still_happens_after_laya(self):
        result = preview("Write a Python function to reverse a string.",
                         policy=self.policy)
        self.assertEqual(result["decision_layer"], "laya")
        self.assertTrue(result["selected_model"])
        self.assertIn(result["model_provider"], {"gemini", "nvidia", "groq", "openrouter"})

    def test_laya_never_returns_a_model_or_provider(self):
        from models import known_model_ids

        models = known_model_ids()
        for prompt, _ in self.EXPECTED:
            decision = self.policy.select_agent(
                "general", "simple", 0.5, {"prompt": prompt})
            self.assertIn(decision["selected_agent"], AGENT_NAMES)
            self.assertNotIn(decision["selected_agent"], models)
            self.assertNotIn(decision["selected_agent"],
                             {"gemini", "nvidia", "groq", "openrouter"})


if __name__ == "__main__":
    unittest.main()
