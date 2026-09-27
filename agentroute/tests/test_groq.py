"""Groq integration tests.

Offline by default. A real Groq call is opt-in via AGENTROUTE_LIVE_GROQ=1.
No credential value is ever read, printed or asserted on.

These prove Groq is a first-class candidate in the EXISTING model-selection
system - not a Groq agent, and not a prompt hardcoded to Groq.
"""

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models  # noqa: E402
import providers  # noqa: E402
from model_registry import default_registry  # noqa: E402
from model_selector import select_model  # noqa: E402
from task_profile import TaskProfile  # noqa: E402


def _task(capability, level):
    return TaskProfile(
        intent=capability,
        capability=capability,
        complexity="complex",
        complexity_level=level,
        confidence=0.9,
    )


def _groq_agent(model_id="openai/gpt-oss-20b"):
    """An agent deployed on Groq (a provider, never a Groq *agent*)."""
    return SimpleNamespace(model_provider="groq", model_id=model_id, available_tools=())


class TestGroqRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = default_registry()
        self.groq = [p for p in self.reg.all() if p.provider == "groq"]

    def test_groq_models_exist_in_registry(self):
        self.assertTrue(self.groq, "no Groq models registered")
        ids = {p.model_id for p in self.groq}
        # only the verified general/coding/reasoning text models
        self.assertIn("openai/gpt-oss-20b", ids)
        self.assertIn("openai/gpt-oss-120b", ids)
        self.assertIn("qwen/qwen3.8-27b", ids)

    def test_groq_models_are_marked_verified(self):
        for p in self.groq:
            with self.subTest(model=p.model_id):
                self.assertEqual(p.availability, "verified")

    def test_no_audio_or_guard_models_registered(self):
        """Whisper/Orpheus/guard models are not chat generators - keep them out."""
        ids = {p.model_id for p in self.groq}
        for banned in ("whisper", "orpheus", "prompt-guard", "safeguard"):
            self.assertFalse(any(banned in i for i in ids),
                             f"non-chat model matching {banned!r} was registered")

    def test_groq_tiers_form_a_ladder(self):
        tiers = sorted(p.tier for p in self.groq)
        self.assertEqual(tiers, [1, 2, 3], "expected a light/balanced/strong ladder")


class TestGroqSelection(unittest.TestCase):
    def setUp(self):
        self.reg = default_registry()

    def test_selector_can_select_groq_when_it_is_available(self):
        sel = select_model(_task("coding", 2), _groq_agent(),
                           registry=self.reg, available_providers={"groq"})
        self.assertEqual(sel.provider, "groq")
        self.assertTrue(sel.model_id.startswith(("openai/", "qwen/")))

    def test_groq_selection_follows_complexity_not_a_hardcoded_prompt(self):
        # Same agent, same provider - only the task LEVEL changes the model.
        picks = {
            lvl: select_model(_task("coding", lvl), _groq_agent(),
                              registry=self.reg, available_providers={"groq"}).model_id
            for lvl in (1, 3, 4)
        }
        self.assertEqual(picks[1], "openai/gpt-oss-20b")      # light
        self.assertEqual(picks[3], "qwen/qwen3.8-27b")        # balanced
        self.assertEqual(picks[4], "openai/gpt-oss-120b")     # strong
        self.assertNotEqual(picks[1], picks[4])

    def test_groq_is_a_candidate_even_for_a_gemini_agent(self):
        """With every provider available, Groq appears as a real fallback."""
        agent = SimpleNamespace(model_provider="gemini",
                                model_id="gemini-flash-latest", available_tools=())
        sel = select_model(_task("general", 2), agent, registry=self.reg,
                           available_providers={"gemini", "nvidia", "groq"})
        self.assertTrue(any(p == "groq" for _, p in sel.fallback_chain),
                        "Groq should be a considered fallback candidate")


class TestExistingBehaviourUnchanged(unittest.TestCase):
    """Adding Groq must not change who wins for Gemini/NVIDIA."""

    def setUp(self):
        self.reg = default_registry()
        self.all = {"gemini", "nvidia", "groq", "openrouter"}

    def _gemini_agent(self):
        return SimpleNamespace(model_provider="gemini",
                               model_id="gemini-flash-latest", available_tools=())

    def test_gemini_still_wins_low_complexity(self):
        sel = select_model(_task("general", 1), self._gemini_agent(),
                           registry=self.reg, available_providers=self.all)
        self.assertEqual(sel.provider, "gemini")

    def test_nvidia_still_wins_expert_complexity(self):
        sel = select_model(_task("reasoning", 4), self._gemini_agent(),
                           registry=self.reg, available_providers=self.all)
        self.assertEqual(sel.provider, "nvidia")
        self.assertEqual(sel.model_id, "nvidia/nemotron-3-ultra-550b-a55b")

    def test_gemini_only_deployment_uses_gemini(self):
        sel = select_model(_task("general", 1), self._gemini_agent(),
                           registry=self.reg, available_providers={"gemini"})
        self.assertEqual(sel.provider, "gemini")


class TestRoleValidation(unittest.TestCase):
    """A provider name is not a role: it must raise, never silently pick Gemini."""

    def test_provider_names_are_not_valid_roles(self):
        for provider in ("groq", "nvidia", "openrouter", "gemini"):
            with self.subTest(name=provider), self.assertRaises(ValueError):
                models.get_model(provider)

    def test_valid_roles_still_resolve(self):
        for role in ("general", "coding", "reasoning", "research", "three_d"):
            with self.subTest(role=role):
                self.assertTrue(models.get_provider(role))

    def test_error_names_the_confusion(self):
        with self.assertRaises(ValueError) as ctx:
            models.get_provider("groq")
        self.assertIn("role", str(ctx.exception).lower())

    def test_fast_groq_dead_role_is_gone(self):
        self.assertNotIn("fast_groq", models.ROLES)
        with self.assertRaises(ValueError):
            models.get_model("fast_groq")


@unittest.skipUnless(
    os.environ.get("AGENTROUTE_LIVE_GROQ") == "1",
    "live Groq test: set AGENTROUTE_LIVE_GROQ=1 (spends real API quota)",
)
class TestLiveGroq(unittest.TestCase):
    """Real Groq API calls. Opt-in only; never part of the default suite."""

    def setUp(self):
        from dotenv import load_dotenv

        load_dotenv()
        if not providers.is_configured("groq"):
            self.skipTest("GROQ_API_KEY not configured")

    def test_every_verified_groq_model_is_actually_callable(self):
        verified = [p for p in default_registry().all()
                    if p.provider == "groq" and p.is_verified]
        self.assertTrue(verified, "no verified Groq models to check")
        for profile in sorted(verified, key=lambda p: p.model_id):
            with self.subTest(model=profile.model_id):
                answer = providers.complete(
                    "groq", profile.model_id, "Reply with the single word: ok"
                )
                self.assertTrue(answer and answer.strip())

    def test_selected_groq_model_completes_end_to_end(self):
        sel = select_model(_task("coding", 4), _groq_agent(),
                           registry=default_registry(),
                           available_providers={"groq"})
        self.assertEqual(sel.provider, "groq")
        answer = providers.complete(sel.provider, sel.model_id,
                                    "Reply with the single word: ok")
        self.assertTrue(answer and answer.strip())


if __name__ == "__main__":
    unittest.main()
