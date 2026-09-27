"""Step 7 tests: multi-provider model evaluation.

Offline by default. Live provider calls are opt-in via AGENTROUTE_LIVE_MODELS=1.
No credential value is ever read, printed or asserted on.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import evaluation  # noqa: E402
import providers  # noqa: E402
from agents.base_agent import BaseAgent  # noqa: E402
from agents.registry import AGENT_NAMES, build_agent_registry  # noqa: E402
from errors import AgentExecutionError, ConfigurationError  # noqa: E402
from model_registry import ModelProfile, ModelRegistry, default_registry  # noqa: E402
from model_selector import select_model  # noqa: E402
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
from task_profile import build_task_profile  # noqa: E402

ALL_PROVIDERS = {"gemini", "nvidia", "openrouter", "groq"}


def _profile(capability_intent, level, agent=None):
    return build_task_profile(
        {"intent": capability_intent, "complexity": "complex", "confidence": 0.9},
        {"decision_layer": "laya", "complexity_level": level},
        agent=agent,
    )


# 1-3. NVIDIA provider
class TestNvidiaProvider(unittest.TestCase):
    def test_nvidia_is_registered(self):
        self.assertIn("nvidia", providers.supported_providers())
        self.assertEqual(providers.display_name("nvidia"), "NVIDIA")

    def test_nvidia_uses_its_official_endpoint(self):
        self.assertEqual(
            providers._ENDPOINTS["nvidia"], "https://integrate.api.nvidia.com/v1"
        )

    def test_nvidia_key_env_var(self):
        self.assertEqual(providers.key_env_var("nvidia"), "NVIDIA_API_KEY")

    def test_missing_nvidia_key_raises_clean_config_error(self):
        old = os.environ.pop("NVIDIA_API_KEY", None)
        try:
            with self.assertRaises(ConfigurationError) as ctx:
                providers.get_client("nvidia")
            self.assertIn("NVIDIA_API_KEY", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["NVIDIA_API_KEY"] = old

    def test_existing_providers_are_untouched(self):
        for name in ("gemini", "openrouter", "groq"):
            self.assertIn(name, providers.supported_providers())
            self.assertTrue(providers._ENDPOINTS[name])

    def test_available_providers_reports_only_configured(self):
        old = {v: os.environ.pop(v, None) for v in
               ("GEMINI_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY")}
        try:
            self.assertEqual(providers.available_providers(), set())
            os.environ["NVIDIA_API_KEY"] = "placeholder-not-a-real-key"
            self.assertEqual(providers.available_providers(), {"nvidia"})
        finally:
            os.environ.pop("NVIDIA_API_KEY", None)
            for var, value in old.items():
                if value is not None:
                    os.environ[var] = value


# 4. Provider-independent registry
class TestMultiProviderRegistry(unittest.TestCase):
    def test_registry_holds_models_from_multiple_providers(self):
        registry = default_registry()
        found = {profile.provider for profile in registry.all()}
        self.assertIn("gemini", found)
        self.assertIn("nvidia", found)

    def test_there_is_only_one_registry_class(self):
        import model_registry

        registries = [n for n in dir(model_registry) if n.endswith("Registry")]
        self.assertEqual(registries, ["ModelRegistry"])

    def test_model_metadata_holds_no_credentials(self):
        secret_markers = ("api_key", "key", "token", "secret", "authorization")
        for profile in default_registry().all():
            for field, value in profile.to_dict().items():
                self.assertNotIn(field.lower(), secret_markers, profile.model_id)
                self.assertNotIn("nvapi-", str(value))
                self.assertNotIn("AIza", str(value))

    def test_provider_metadata_stays_out_of_model_metadata(self):
        """Models know their provider NAME, never its endpoint or key."""
        for profile in default_registry().all():
            blob = str(profile.to_dict())
            self.assertNotIn("https://", blob, profile.model_id)

    def test_nvidia_models_declare_their_source(self):
        for profile in default_registry().for_provider("nvidia"):
            self.assertIn("verified live", profile.source)


# 5-8. Multi-provider selection
class TestMultiProviderSelection(unittest.TestCase):
    def setUp(self):
        self.registry = build_agent_registry()
        self.coding = self.registry[CODING_AGENT]

    def test_selection_can_cross_providers(self):
        """Expert work leaves the agent's own provider when a better-fitting
        verified model lives elsewhere."""
        selection = select_model(
            _profile("coding", 4, self.coding), self.coding,
            available_providers=ALL_PROVIDERS,
        )
        self.assertNotEqual(selection.provider, self.coding.model_provider)

    def test_verified_models_are_preferred_over_merely_listed_ones(self):
        """A listed-but-unverified id can 404, so verified wins at equal tier."""
        from model_registry import default_registry

        for level in (1, 2, 3, 4):
            selection = select_model(
                _profile("coding", level, self.coding), self.coding,
                available_providers=ALL_PROVIDERS,
            )
            profile = default_registry().get(selection.model_id)
            self.assertTrue(profile.is_verified, f"L{level}: {selection.model_id}")

    def test_capability_specialist_wins_at_equal_tier_and_availability(self):
        """Provider-neutral: the rule is about capability, not who hosts it."""
        specialist = ModelProfile(
            "vendor-a/code-model", "nvidia", tier=1, complexity_min=1,
            complexity_max=2, capabilities=frozenset({"coding"}),
            availability="verified", source="test")
        generalist = ModelProfile(
            "vendor-b/general-model", "gemini", tier=1, complexity_min=1,
            complexity_max=2, capabilities=frozenset({"general", "coding", "reasoning"}),
            availability="verified", source="test")
        registry = ModelRegistry(profiles=(generalist, specialist),
                                 seed_configured=False)
        selection = select_model(
            _profile("coding", 1, self.coding), self.coding, registry=registry,
            available_providers=ALL_PROVIDERS)
        self.assertEqual(selection.model_id, "vendor-a/code-model")

    def test_same_agent_different_complexity_different_model(self):
        picks = {
            level: select_model(
                _profile("coding", level, self.coding), self.coding,
                available_providers=ALL_PROVIDERS,
            ).model_id
            for level in (1, 3, 4)
        }
        self.assertEqual(len(set(picks.values())), 3, picks)

    def test_agent_identity_never_changes_with_the_model(self):
        for level in (1, 2, 3, 4):
            select_model(_profile("coding", level, self.coding), self.coding,
                         available_providers=ALL_PROVIDERS)
            self.assertEqual(self.coding.name, CODING_AGENT)

    def test_provider_availability_filters_candidates(self):
        only_gemini = select_model(
            _profile("coding", 1, self.coding), self.coding,
            available_providers={"gemini"},
        )
        self.assertEqual(only_gemini.provider, "gemini")

    def test_unavailable_provider_models_are_never_selected(self):
        selection = select_model(
            _profile("coding", 3, self.coding), self.coding,
            available_providers={"gemini"},
        )
        self.assertNotEqual(selection.provider, "nvidia")
        for model_id in selection.fallback_models:
            profile = default_registry().get(model_id)
            if profile:
                self.assertNotEqual(profile.provider, "nvidia")

    def test_capability_filtering_excludes_mismatched_specialists(self):
        """A code-only model must never be chosen for a research task."""
        selection = select_model(
            _profile("research", 2, self.registry[RESEARCH_AGENT]),
            self.registry[RESEARCH_AGENT],
            available_providers=ALL_PROVIDERS,
        )
        profile = default_registry().get(selection.model_id)
        if profile and profile.capabilities:
            self.assertIn("research", profile.capabilities)

    def test_complexity_aware_selection_still_holds(self):
        from model_selector import REQUIRED_MIN_TIER

        for level in (1, 2, 3, 4):
            selection = select_model(
                _profile("coding", level, self.coding), self.coding,
                available_providers=ALL_PROVIDERS,
            )
            self.assertGreaterEqual(selection.tier, REQUIRED_MIN_TIER[level], level)

    def test_no_hard_coded_provider_preference_in_source(self):
        """Selection rules must not name a provider."""
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "model_selector.py"), encoding="utf-8") as fh:
            source = fh.read()
        for name in ("nvidia", "gemini", "openrouter", "groq"):
            self.assertNotIn(f'"{name}"', source.lower())

    def test_selection_is_deterministic_across_providers(self):
        first = select_model(_profile("coding", 3, self.coding), self.coding,
                             available_providers=ALL_PROVIDERS)
        second = select_model(_profile("coding", 3, self.coding), self.coding,
                              available_providers=ALL_PROVIDERS)
        self.assertEqual(first.model_id, second.model_id)
        self.assertEqual(first.provider, second.provider)


# 9-10. Fallback behaviour
class TestFallbackChain(unittest.TestCase):
    def setUp(self):
        self.registry = build_agent_registry()
        self.coding = self.registry[CODING_AGENT]

    def test_fallback_chain_carries_its_provider(self):
        selection = select_model(_profile("coding", 4, self.coding), self.coding,
                                 available_providers=ALL_PROVIDERS)
        self.assertTrue(selection.fallback_chain)
        for model_id, provider in selection.fallback_chain:
            self.assertTrue(model_id)
            self.assertIn(provider, ALL_PROVIDERS)

    def test_configured_model_is_always_the_last_resort(self):
        selection = select_model(_profile("coding", 1, self.coding), self.coding,
                                 available_providers=ALL_PROVIDERS)
        self.assertIn(self.coding.model_id, selection.fallback_models)

    def test_failure_falls_through_to_the_next_provider(self):
        calls = []

        def flaky(provider, model, prompt, system=None):
            calls.append((provider, model))
            if provider == "nvidia":
                raise AgentExecutionError("nvidia unavailable")
            return "answered by fallback"

        original = providers.complete
        providers.complete = flaky
        try:
            answer = self.coding.run_with_model(
                "write code", "nvidia/nemotron-3-super-120b-a12b", "nvidia",
                (("gemini-2.5-flash", "gemini"),),
            )
        finally:
            providers.complete = original

        self.assertEqual(answer, "answered by fallback")
        self.assertEqual(calls[0][0], "nvidia")
        self.assertEqual(calls[1][0], "gemini")
        # The AGENT never changed - only the model/provider did.
        self.assertEqual(self.coding.name, CODING_AGENT)

    def test_agent_config_is_restored_after_an_overridden_run(self):
        before = (self.coding.model_id, self.coding.model_provider,
                  tuple(self.coding.fallback_model_ids))

        def fake(provider, model, prompt, system=None):
            return "ok"

        original = providers.complete
        providers.complete = fake
        try:
            self.coding.run_with_model("x", "nvidia/nemotron-nano-3-30b-a3b", "nvidia",
                                       (("gemini-2.5-flash", "gemini"),))
        finally:
            providers.complete = original
        self.assertEqual(
            (self.coding.model_id, self.coding.model_provider,
             tuple(self.coding.fallback_model_ids)), before)

    def test_model_failure_does_not_change_the_routing_decision(self):
        def always_fail(provider, model, prompt, system=None):
            raise AgentExecutionError("all providers down")

        original = providers.complete
        providers.complete = always_fail
        try:
            result = route("Write a Python function to reverse a string.",
                           policy=BaselineAgentPolicy(), agents=build_agent_registry())
        finally:
            providers.complete = original
        self.assertEqual(result["selected_agent"], CODING_AGENT)
        self.assertFalse(result["response_success"])


# 11-13. Security
class TestCredentialSafety(unittest.TestCase):
    def test_no_credentials_in_routing_metadata(self):
        result = preview("Write a Python function to reverse a string.",
                         policy=BaselineAgentPolicy())
        blob = str(result)
        for marker in ("nvapi-", "AIza", "gsk_", "sk-or-"):
            self.assertNotIn(marker, blob)
        for key in result:
            self.assertNotIn("api_key", key.lower())

    def test_error_messages_never_include_key_values(self):
        os.environ["NVIDIA_API_KEY"] = "nvapi-thisisnotarealkey"
        try:
            def boom(provider, model, prompt, system=None):
                from providers import _FRIENDLY_HINTS  # noqa: F401
                raise AgentExecutionError(
                    f"{providers.display_name(provider)} request failed for "
                    f"model {model!r}: AuthenticationError"
                )

            original = providers.complete
            providers.complete = boom
            try:
                agent = build_agent_registry()[CODING_AGENT]
                with self.assertRaises(AgentExecutionError) as ctx:
                    agent.run("hi")
                self.assertNotIn("nvapi-thisisnotarealkey", str(ctx.exception))
            finally:
                providers.complete = original
        finally:
            os.environ.pop("NVIDIA_API_KEY", None)

    def test_gitignore_covers_env_and_api_txt(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        for path in (os.path.join(root, ".gitignore"),
                     os.path.join(root, "agentroute", ".gitignore")):
            self.assertTrue(os.path.exists(path), path)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn(".env", content, path)
            self.assertIn("api.txt", content, path)

    def test_no_credentials_committed_in_source(self):
        """Scan tracked source for KEY-SHAPED strings.

        Matches the shape (prefix + a long secret body), not the bare prefix -
        provider docs legitimately mention "nvapi-" in prose.
        """
        import re

        patterns = {
            "nvidia": re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),
            "gemini": re.compile(r"AIzaSy[A-Za-z0-9_\-]{20,}"),
            "groq": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
            "openrouter": re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}"),
        }
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in {"__pycache__", "venv", ".venv"}]
            for filename in filenames:
                if not filename.endswith((".py", ".md", ".txt", ".example")):
                    continue
                path = os.path.join(dirpath, filename)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                for label, pattern in patterns.items():
                    self.assertIsNone(
                        pattern.search(content),
                        f"possible {label} credential in {filename}",
                    )


# 14-20. Nothing regressed
class TestExistingBehaviourPreserved(unittest.TestCase):
    CASES = [
        ("What is photosynthesis?", GENERAL_AGENT, "general"),
        ("Write a Python function to reverse a string.", CODING_AGENT, "coding"),
        ("Design a scalable microservices architecture.", REASONING_AGENT, "reasoning"),
        ("Research the advantages and disadvantages of RAG.", RESEARCH_AGENT, "research"),
        ("Create a 3D model of a wooden chair.", THREE_D_AGENT, "creative_3d"),
    ]

    def test_all_five_categories_remain_routable(self):
        for prompt, agent, capability in self.CASES:
            result = preview(prompt, policy=BaselineAgentPolicy())
            self.assertEqual(result["selected_agent"], agent, prompt)
            self.assertEqual(result["capability"], capability, prompt)

    def test_agents_are_unchanged(self):
        self.assertEqual(
            set(AGENT_NAMES),
            {GENERAL_AGENT, CODING_AGENT, REASONING_AGENT, RESEARCH_AGENT, THREE_D_AGENT, WEB_AGENT},
        )

    def test_gemini_routing_still_works(self):
        selection = select_model(
            _profile("general", 1, build_agent_registry()[GENERAL_AGENT]),
            build_agent_registry()[GENERAL_AGENT], available_providers={"gemini"})
        self.assertEqual(selection.provider, "gemini")

    def test_openrouter_and_groq_remain_supported(self):
        from models import get_model, get_provider

        old = os.environ.get("AGENTROUTE_PROVIDER")
        try:
            os.environ["AGENTROUTE_PROVIDER"] = "openrouter"
            self.assertEqual(get_provider("coding"), "openrouter")
            self.assertTrue(get_model("coding"))
            os.environ["AGENTROUTE_PROVIDER"] = "groq"
            self.assertEqual(get_provider("coding"), "groq")
        finally:
            if old is None:
                os.environ.pop("AGENTROUTE_PROVIDER", None)
            else:
                os.environ["AGENTROUTE_PROVIDER"] = old

    def test_tools_are_still_tools(self):
        from tools.registry import list_tools

        for tool in list_tools():
            self.assertNotIn(tool, AGENT_NAMES)
        self.assertIn("BLENDER_TOOL", list_tools())


# 16. Evaluation dataset
class TestEvaluationDataset(unittest.TestCase):
    def test_dataset_is_about_thirty_cases(self):
        self.assertGreaterEqual(len(evaluation.EVAL_CASES), 30)

    def test_each_category_has_at_least_five_cases(self):
        from collections import Counter

        counts = Counter(case[1] for case in evaluation.EVAL_CASES)
        for capability in ("general", "coding", "reasoning", "research", "creative_3d"):
            self.assertGreaterEqual(counts[capability], 5, capability)

    def test_offline_eval_records_provider_and_reason(self):
        rows = evaluation.run_eval(policy=BaselineAgentPolicy())
        self.assertEqual(len(rows), len(evaluation.EVAL_CASES))
        for row in rows:
            self.assertIn("provider", row)
            self.assertIn("model_reason", row)

    def test_offline_eval_makes_no_api_calls(self):
        def explode(*args, **kwargs):
            raise AssertionError("evaluation must not call a provider")

        original = providers.complete
        providers.complete = explode
        try:
            evaluation.run_eval(policy=BaselineAgentPolicy())
        finally:
            providers.complete = original


@unittest.skipUnless(
    os.environ.get("AGENTROUTE_LIVE_MODELS") == "1",
    "live provider test: set AGENTROUTE_LIVE_MODELS=1 (spends real API quota)",
)
class TestLiveProviders(unittest.TestCase):
    """Real API calls. Opt-in only; never part of the default suite."""

    def test_every_verified_model_is_actually_callable(self):
        """`availability="verified"` is a claim - this proves it, or fails."""
        from dotenv import load_dotenv

        load_dotenv()
        available = providers.available_providers()
        self.assertTrue(available, "no provider credentials configured")

        verified = [p for p in default_registry().all()
                    if p.is_verified and p.provider in available]
        self.assertTrue(verified, "no verified models for the configured providers")

        for profile in sorted(verified, key=lambda p: p.model_id):
            with self.subTest(model=profile.model_id):
                answer = providers.complete(
                    profile.provider, profile.model_id, "Reply with the word OK."
                )
                self.assertTrue(answer and answer.strip())

    def test_routing_end_to_end_hits_a_real_provider(self):
        from dotenv import load_dotenv

        load_dotenv()
        from agents.registry import build_agent_registry

        result = route("Write a Python function to reverse a string.",
                       policy=BaselineAgentPolicy(), agents=build_agent_registry())
        self.assertEqual(result["selected_agent"], CODING_AGENT)
        self.assertTrue(result["response_success"], result["response"][:160])
        self.assertTrue(result["selected_model"])


if __name__ == "__main__":
    unittest.main()
