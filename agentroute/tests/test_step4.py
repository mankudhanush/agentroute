"""Step 4 tests: agent/model/tool separation.

All offline: no API keys, no network, no Blender binary required.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import providers  # noqa: E402
from agents.base_agent import BaseAgent  # noqa: E402
from agents.coding_agent import CodingAgent  # noqa: E402
from agents.general_agent import GeneralAgent  # noqa: E402
from agents.reasoning_agent import ReasoningAgent  # noqa: E402
from agents.registry import AGENT_NAMES, agent_metadata, build_agent_registry  # noqa: E402
from agents.research_agent import ResearchAgent  # noqa: E402
from agents.three_d_agent import ThreeDAgent  # noqa: E402
from classifier import classify  # noqa: E402
from errors import AgentExecutionError  # noqa: E402
from models import get_model, get_provider, known_model_ids  # noqa: E402
from router import route  # noqa: E402
from routing_policy import (  # noqa: E402
    CODING_AGENT,
    GENERAL_AGENT,
    REASONING_AGENT,
    RESEARCH_AGENT,
    STEP4_CANDIDATES,
    THREE_D_AGENT,
    BaselineAgentPolicy,
)
from tools.base_tool import ToolResult  # noqa: E402
from tools.blender_tool import BlenderTool  # noqa: E402
from tools.registry import get_tool, list_tools  # noqa: E402


class _FakeAgent(BaseAgent):
    """Stands in for a real agent so no model API is ever called."""

    def __init__(self, name):
        self.name = name

    def run(self, prompt):
        return f"[{self.name}] handled: {prompt}"


def _fake_registry():
    return {name: _FakeAgent(name) for name in AGENT_NAMES}


def _routed(prompt):
    """Route a prompt through the Step 4 policy using fake agents (no API)."""
    return route(prompt, policy=BaselineAgentPolicy(), agents=_fake_registry())


class TestRouterSelectsAgents(unittest.TestCase):
    def test_selects_general_agent(self):
        self.assertEqual(_routed("What is a Python decorator?")["selected_agent"],
                         GENERAL_AGENT)

    def test_selects_coding_agent(self):
        self.assertEqual(_routed("Write a FastAPI authentication system.")["selected_agent"],
                         CODING_AGENT)

    def test_selects_reasoning_agent(self):
        self.assertEqual(
            _routed("Explain how to design a scalable multi-agent architecture.")[
                "selected_agent"],
            REASONING_AGENT,
        )

    def test_selects_research_agent(self):
        self.assertEqual(
            _routed("Research the latest approaches to RAG evaluation.")["selected_agent"],
            RESEARCH_AGENT,
        )

    def test_selects_three_d_agent(self):
        self.assertEqual(
            _routed("Create a modern 3D wardrobe in Blender.")["selected_agent"],
            THREE_D_AGENT,
        )


class TestRouterNeverSelectsToolsOrModels(unittest.TestCase):
    PROMPTS = [
        "What is a Python decorator?",
        "Write a FastAPI authentication system.",
        "Explain how to design a scalable multi-agent architecture.",
        "Research the latest approaches to RAG evaluation.",
        "Create a modern 3D wardrobe in Blender.",
    ]

    def _selections(self):
        policy = BaselineAgentPolicy()
        out = set()
        for prompt in self.PROMPTS:
            c = classify(prompt)
            out.add(policy.select_agent(c["intent"], c["complexity"], c["confidence"])[
                "selected_agent"])
        return out

    def test_router_never_selects_a_tool(self):
        selections = self._selections()
        self.assertFalse(selections & set(list_tools()))
        self.assertNotIn("BLENDER_TOOL", selections)

    def test_router_never_selects_a_model_as_agent(self):
        self.assertFalse(self._selections() & known_model_ids())

    def test_all_selections_are_registered_agents(self):
        self.assertTrue(self._selections() <= set(AGENT_NAMES))

    def test_blender_is_not_an_agent(self):
        registry = build_agent_registry()
        self.assertNotIn("BLENDER_AGENT", registry)
        self.assertNotIn("BLENDER_TOOL", registry)
        self.assertNotIn("BLENDER_AGENT", AGENT_NAMES)

    def test_blender_is_a_registered_tool(self):
        self.assertIn("BLENDER_TOOL", list_tools())
        self.assertIsInstance(get_tool("BLENDER_TOOL"), BlenderTool)


class TestAgentToolAccess(unittest.TestCase):
    def test_three_d_agent_can_access_blender_tool(self):
        agent = ThreeDAgent()
        self.assertIn("BLENDER_TOOL", agent.available_tools)
        self.assertIsInstance(agent.get_tool("BLENDER_TOOL"), BlenderTool)

    def test_research_agent_can_access_search_tool(self):
        agent = ResearchAgent()
        self.assertIn("WEB_SEARCH_TOOL", agent.available_tools)
        self.assertEqual(agent.get_tool("WEB_SEARCH_TOOL").name, "WEB_SEARCH_TOOL")

    def test_agent_cannot_use_unpermitted_tool(self):
        with self.assertRaises(AgentExecutionError):
            GeneralAgent().get_tool("BLENDER_TOOL")

    def test_blender_tool_works_without_blender_installed(self):
        # Execution disabled by default -> no binary needed, structured result.
        os.environ.pop("BLENDER_EXECUTION_ENABLED", None)
        result = BlenderTool().run("import bpy\n")
        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.success)
        self.assertFalse(result.metadata["executed"])

    def test_execute_does_not_claim_a_scene_when_disabled(self):
        os.environ["BLENDER_EXECUTION_ENABLED"] = "false"
        try:
            result = BlenderTool().execute("import bpy\n")
        finally:
            os.environ.pop("BLENDER_EXECUTION_ENABLED", None)
        self.assertFalse(result.success)
        self.assertFalse(result.metadata["executed"])
        self.assertIn("No scene was created", result.error)

    def test_execute_records_objects_only_after_blender_writes_a_scene(self):
        os.environ["BLENDER_EXECUTION_ENABLED"] = "true"
        try:
            tool = BlenderTool()

            def fake_run(cmd, **kwargs):
                harness = cmd[-1]
                text = open(harness, encoding="utf-8").read()
                self.assertIn("runpy.run_path", text)
                self.assertIn("AGENTROUTE_OBJECTS=", text)
                self.assertIn("save_as_mainfile", text)
                self.assertIn("--factory-startup", cmd)
                blend = os.path.join(kwargs["cwd"], "scene.blend")
                with open(blend, "w", encoding="utf-8") as fh:
                    fh.write("scene")

                class Proc:
                    returncode = 0
                    stdout = "AGENTROUTE_OBJECTS=SimpleCube|SceneCylinder\n"
                    stderr = ""

                return Proc()

            with patch.object(tool, "find_binary", return_value="blender"), patch(
                "tools.blender_tool.subprocess.run", side_effect=fake_run
            ):
                result = tool.execute("import bpy\nbpy.ops.mesh.primitive_cube_add()\n")
        finally:
            os.environ.pop("BLENDER_EXECUTION_ENABLED", None)
        self.assertTrue(result.success)
        self.assertTrue(result.metadata["executed"])
        self.assertEqual(result.metadata["objects"], ["SimpleCube", "SceneCylinder"])
        self.assertTrue(result.artifacts[0].endswith("scene.blend"))

    def test_three_d_agent_builds_valid_bpy_script_offline(self):
        script = ThreeDAgent().build_blender_script("a modern wooden wardrobe")
        self.assertIn("import bpy", script)
        compile(script, "<generated>", "exec")  # must be valid Python


class TestAgentModelConfiguration(unittest.TestCase):
    def test_each_agent_has_its_own_model(self):
        expected = {
            GENERAL_AGENT: get_model("general"),
            CODING_AGENT: get_model("coding"),
            REASONING_AGENT: get_model("reasoning"),
            RESEARCH_AGENT: get_model("research"),
            THREE_D_AGENT: get_model("three_d"),
        }
        registry = build_agent_registry()
        role_by_agent = {
            GENERAL_AGENT: "general", CODING_AGENT: "coding",
            REASONING_AGENT: "reasoning", RESEARCH_AGENT: "research",
            THREE_D_AGENT: "three_d",
        }
        for name, model in expected.items():
            self.assertEqual(registry[name].model_id, model, name)
            # MIGRATED (Step 5): the provider is no longer pinned to OpenRouter -
            # each agent uses whatever provider its role resolves to.
            self.assertEqual(
                registry[name].model_provider, get_provider(role_by_agent[name]), name
            )

    def test_model_is_env_configurable_without_code_change(self):
        # MIGRATED (Step 5): pin the role to OpenRouter so this still exercises
        # the OpenRouter env override path.
        old_model = os.environ.get("OPENROUTER_3D_MODEL")
        old_provider = os.environ.get("THREE_D_MODEL_PROVIDER")
        os.environ["THREE_D_MODEL_PROVIDER"] = "openrouter"
        os.environ["OPENROUTER_3D_MODEL"] = "some/other-model:free"
        try:
            agent = ThreeDAgent()
            self.assertEqual(agent.model_id, "some/other-model:free")
            self.assertEqual(agent.model_provider, "openrouter")
        finally:
            for key, value in (
                ("OPENROUTER_3D_MODEL", old_model),
                ("THREE_D_MODEL_PROVIDER", old_provider),
            ):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_router_source_contains_no_model_ids(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "router.py"), encoding="utf-8") as fh:
            source = fh.read()
        for model_id in known_model_ids():
            self.assertNotIn(model_id, source)

    def test_agent_metadata_exposes_required_fields(self):
        for meta in agent_metadata():
            for field in ("name", "description", "capabilities", "model_provider",
                          "model_id", "available_tools"):
                self.assertIn(field, meta)


class TestModelFallbackInsideAgent(unittest.TestCase):
    def test_reasoning_agent_declares_a_fallback(self):
        agent = ReasoningAgent()
        self.assertTrue(agent.fallback_model_ids)
        self.assertIn(get_model("reasoning_fallback"), agent.fallback_model_ids)

    def test_fallback_is_used_and_agent_identity_is_unchanged(self):
        agent = ReasoningAgent()
        primary, fallback = agent.model_id, agent.fallback_model_ids[0]
        calls = []

        def fake_complete(provider, model, prompt, system=None):
            calls.append(model)
            if model == primary:
                raise AgentExecutionError("primary unavailable")
            return f"answered by {model}"

        original = providers.complete
        providers.complete = fake_complete
        try:
            result = agent.run("plan a system")
        finally:
            providers.complete = original

        self.assertEqual(result, f"answered by {fallback}")
        self.assertEqual(calls[:2], [primary, fallback])
        # Identity never changes just because a backup model was used.
        self.assertEqual(agent.name, REASONING_AGENT)

    def test_all_models_failing_raises_agent_error(self):
        agent = CodingAgent()

        def always_fail(provider, model, prompt, system=None):
            raise AgentExecutionError("down")

        original = providers.complete
        providers.complete = always_fail
        try:
            with self.assertRaises(AgentExecutionError):
                agent.run("write a function")
        finally:
            providers.complete = original


class TestNoLegacyBlenderAgent(unittest.TestCase):
    """The deprecated BLENDER_AGENT compatibility layer must be fully removed."""

    @staticmethod
    def _active_sources():
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames if d not in {"tests", "__pycache__", "venv", ".venv"}
            ]
            for filename in filenames:
                if filename.endswith(".py"):
                    yield os.path.join(dirpath, filename)

    def test_blender_agent_absent_from_active_source(self):
        offenders = []
        for path in self._active_sources():
            with open(path, encoding="utf-8") as fh:
                if "BLENDER_AGENT" in fh.read():
                    offenders.append(os.path.basename(path))
        self.assertEqual(offenders, [], f"BLENDER_AGENT still present in: {offenders}")

    def test_legacy_agent_modules_are_gone(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for legacy in ("blender_agent.py", "groq_agent.py", "openrouter_agent.py"):
            self.assertFalse(
                os.path.exists(os.path.join(root, "agents", legacy)),
                f"legacy module still present: {legacy}",
            )

    def test_three_d_agent_is_the_only_3d_agent(self):
        registry = build_agent_registry()
        three_d = [
            name for name, agent in registry.items()
            if "3d_design" in agent.capabilities or "blender" in agent.capabilities
        ]
        self.assertEqual(three_d, [THREE_D_AGENT])

    def test_blender_tool_is_the_execution_layer(self):
        tool = get_tool("BLENDER_TOOL")
        self.assertTrue(hasattr(tool, "check_installation"))
        self.assertTrue(hasattr(tool, "find_binary"))
        # Only THREE_D_AGENT may reach it.
        owners = [
            name for name, agent in build_agent_registry().items()
            if "BLENDER_TOOL" in agent.available_tools
        ]
        self.assertEqual(owners, [THREE_D_AGENT])


class TestAdaptiveChoosesAgents(unittest.TestCase):
    def test_step4_candidates_are_agents_only(self):
        for intent, candidates in STEP4_CANDIDATES.items():
            self.assertTrue(set(candidates) <= set(AGENT_NAMES), intent)
            self.assertFalse(set(candidates) & set(list_tools()), intent)


if __name__ == "__main__":
    unittest.main()
