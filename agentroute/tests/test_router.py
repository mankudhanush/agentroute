"""Tests for routing decisions and end-to-end routing with fake agents.

Originally written for the Step 2 agent taxonomy (FAST_AGENT / BLENDER_AGENT).
MIGRATED to the current taxonomy: the architecture intentionally changed so that
3D work is handled by THREE_D_AGENT, which owns BLENDER_TOOL. Blender is a tool,
never an agent. Coverage is preserved, expectations updated.

No real API calls are made. Uses fake agents injected into `route`.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import providers  # noqa: E402
from agents.base_agent import BaseAgent  # noqa: E402
from agents.three_d_agent import ThreeDAgent  # noqa: E402
from errors import ConfigurationError  # noqa: E402
from router import (  # noqa: E402
    CODING_AGENT,
    GENERAL_AGENT,
    REASONING_AGENT,
    RESEARCH_AGENT,
    THREE_D_AGENT,
    route,
    select_agent,
)
from routing_policy import BaselineAgentPolicy  # noqa: E402


class _FakeAgent(BaseAgent):
    def __init__(self, name):
        self.name = name

    def run(self, prompt: str) -> str:
        return f"[{self.name}] handled: {prompt}"


def _fake_registry():
    return {
        name: _FakeAgent(name)
        for name in (
            GENERAL_AGENT,
            CODING_AGENT,
            REASONING_AGENT,
            RESEARCH_AGENT,
            THREE_D_AGENT,
        )
    }


class TestSelectAgent(unittest.TestCase):
    def test_general_goes_to_general_agent(self):
        c = {"intent": "general", "complexity": "simple", "confidence": 0.6}
        self.assertEqual(select_agent(c), GENERAL_AGENT)

    def test_complex_reasoning_goes_to_reasoning(self):
        c = {"intent": "reasoning", "complexity": "complex", "confidence": 0.9}
        self.assertEqual(select_agent(c), REASONING_AGENT)

    def test_blender_goes_to_three_d_agent(self):
        # MIGRATED: was BLENDER_AGENT. Blender is now a TOOL owned by THREE_D_AGENT.
        c = {"intent": "blender", "complexity": "medium", "confidence": 0.9}
        self.assertEqual(select_agent(c), THREE_D_AGENT)

    def test_research_goes_to_research_agent(self):
        c = {"intent": "research", "complexity": "medium", "confidence": 0.9}
        self.assertEqual(select_agent(c), RESEARCH_AGENT)

    def test_simple_coding_goes_to_coding_agent(self):
        c = {"intent": "coding", "complexity": "simple", "confidence": 0.8}
        self.assertEqual(select_agent(c), CODING_AGENT)

    def test_complex_coding_also_goes_to_coding_agent(self):
        # MIGRATED: Step 2 escalated complex coding to REASONING_AGENT because no
        # dedicated coding agent existed. A specialist CODING_AGENT now handles
        # both. (Adaptive routing may still escalate based on measured outcomes -
        # see STEP4_CANDIDATES["coding"].)
        c = {"intent": "coding", "complexity": "complex", "confidence": 0.8}
        self.assertEqual(select_agent(c), CODING_AGENT)


class TestRouteEndToEnd(unittest.TestCase):
    def test_route_with_fake_agents(self):
        result = route(
            "What is Python?",
            policy=BaselineAgentPolicy(),
            agents=_fake_registry(),
        )
        self.assertEqual(result["selected_agent"], GENERAL_AGENT)
        self.assertEqual(result["intent"], "general")
        self.assertIn("handled", result["response"])
        for key in ("selected_agent", "intent", "complexity", "confidence", "response"):
            self.assertIn(key, result)

    def test_blender_prompt_routes_to_three_d_agent(self):
        # MIGRATED: the router must select THREE_D_AGENT - never a Blender agent,
        # never BLENDER_TOOL.
        result = route(
            "Create a 3D chair in Blender",
            policy=BaselineAgentPolicy(),
            agents=_fake_registry(),
        )
        self.assertEqual(result["selected_agent"], THREE_D_AGENT)
        self.assertNotEqual(result["selected_agent"], "BLENDER_AGENT")
        self.assertNotEqual(result["selected_agent"], "BLENDER_TOOL")

    def test_three_d_agent_produces_bpy_script(self):
        # MIGRATED from the old "blender route returns a bpy script" test. The
        # script now comes from THREE_D_AGENT (offline, deterministic, no model).
        script = ThreeDAgent().build_blender_script("Create a 3D chair in Blender")
        self.assertIn("import bpy", script)
        compile(script, "<generated>", "exec")


class TestMissingApiKey(unittest.TestCase):
    """MIGRATED: the old test used the removed GroqAgent. The behaviour under test
    - a missing key yields a clean, non-secret ConfigurationError - now lives in
    the provider layer that all agents share."""

    def _assert_missing_key(self, provider, env_var):
        old = os.environ.pop(env_var, None)
        try:
            with self.assertRaises(ConfigurationError) as ctx:
                providers.get_client(provider)
            self.assertIn(env_var, str(ctx.exception))
        finally:
            if old is not None:
                os.environ[env_var] = old

    def test_missing_groq_key_raises_clean_error(self):
        self._assert_missing_key("groq", "GROQ_API_KEY")

    def test_missing_openrouter_key_raises_clean_error(self):
        self._assert_missing_key("openrouter", "OPENROUTER_API_KEY")

    def test_unknown_provider_raises_clean_error(self):
        with self.assertRaises(ConfigurationError):
            providers.get_client("not_a_provider")


if __name__ == "__main__":
    unittest.main()
