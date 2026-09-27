"""Step 5 tests: Gemini provider + agent switching.

All offline. No real Gemini key, no network - provider calls are faked.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models  # noqa: E402
import providers  # noqa: E402
from agents.base_agent import BaseAgent  # noqa: E402
from agents.registry import AGENT_NAMES, build_agent_registry  # noqa: E402
from agents.three_d_agent import ThreeDAgent, blender_capability, python_syntax_error  # noqa: E402
from errors import ConfigurationError  # noqa: E402
from models import get_model, known_model_ids  # noqa: E402
from router import preview, route  # noqa: E402
from routing_policy import (  # noqa: E402
    CODING_AGENT,
    GENERAL_AGENT,
    REASONING_AGENT,
    RESEARCH_AGENT,
    THREE_D_AGENT,
    BaselineAgentPolicy,
)
from tools.base_tool import ToolResult  # noqa: E402
from tools.blender_tool import BlenderTool  # noqa: E402
from tools.registry import list_tools  # noqa: E402

ROUTING_CASES = [
    ("What is photosynthesis?", GENERAL_AGENT),
    ("Write a Python function to reverse a string.", CODING_AGENT),
    ("Design a scalable microservices architecture.", REASONING_AGENT),
    ("Research the advantages and disadvantages of RAG.", RESEARCH_AGENT),
    ("Create a 3D model of a wooden chair.", THREE_D_AGENT),
]


class _FakeAgent(BaseAgent):
    def __init__(self, name):
        self.name = name

    def run(self, prompt):
        return f"[{self.name}] handled: {prompt}"


def _fake_registry():
    return {name: _FakeAgent(name) for name in AGENT_NAMES}


class _FakeProvider:
    """Records provider/model/system used, returns a canned answer."""

    def __init__(self, answer="ok"):
        self.calls = []
        self.answer = answer

    def __call__(self, provider, model, prompt, system=None):
        self.calls.append(
            {"provider": provider, "model": model, "prompt": prompt, "system": system}
        )
        return self.answer


class _SequenceProvider:
    """Returns a different model reply on each call."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, provider, model, prompt, system=None):
        self.calls.append(
            {"provider": provider, "model": model, "prompt": prompt, "system": system}
        )
        index = min(len(self.calls) - 1, len(self.answers) - 1)
        return self.answers[index]


class _PatchedComplete:
    def __init__(self, fake):
        self.fake = fake

    def __enter__(self):
        self.original = providers.complete
        providers.complete = self.fake
        return self.fake

    def __exit__(self, *exc):
        providers.complete = self.original


class TestAgentsUseGemini(unittest.TestCase):
    """Requirements 1-5: every agent is powered by Gemini, but stays distinct."""

    def setUp(self):
        self.registry = build_agent_registry()

    def test_all_agents_use_gemini_provider(self):
        for name, agent in self.registry.items():
            self.assertEqual(agent.model_provider, "gemini", name)

    def test_all_agents_use_configured_gemini_model(self):
        expected = get_model("general")
        for name, agent in self.registry.items():
            self.assertEqual(agent.model_id, expected, name)

    def test_each_agent_calls_gemini_through_the_provider_layer(self):
        for name, agent in self.registry.items():
            fake = _FakeProvider(answer=f"answer from {name}")
            with _PatchedComplete(fake):
                out = agent.run("hello")
            self.assertEqual(out, f"answer from {name}")
            self.assertEqual(fake.calls[0]["provider"], "gemini", name)
            self.assertEqual(fake.calls[0]["model"], agent.model_id, name)

    def test_agents_are_distinct_despite_sharing_a_model(self):
        """Same provider+model must NOT collapse them into one agent."""
        names = {a.name for a in self.registry.values()}
        self.assertEqual(len(names), 6)
        prompts = set()
        descriptions = set()
        for agent in self.registry.values():
            self.assertTrue(agent.system_prompt, agent.name)
            prompts.add(agent.system_prompt)
            descriptions.add(agent.description)
        # Distinct identity, system prompt and description per agent.
        self.assertEqual(len(prompts), 6)
        self.assertEqual(len(descriptions), 6)

    def test_gemini_is_a_provider_not_an_agent(self):
        self.assertIn("gemini", providers.supported_providers())
        for name in AGENT_NAMES:
            self.assertNotIn("GEMINI", name)
        self.assertNotIn("gemini", {n.lower() for n in self.registry})


class TestRouterAgentSwitching(unittest.TestCase):
    """Requirements 6-12: the router picks the right AGENT for each prompt."""

    def test_routing_cases(self):
        for prompt, expected in ROUTING_CASES:
            result = route(prompt, policy=BaselineAgentPolicy(), agents=_fake_registry())
            self.assertEqual(result["selected_agent"], expected, prompt)

    def test_preview_matches_route_without_calling_a_model(self):
        for prompt, expected in ROUTING_CASES:
            result = preview(prompt, policy=BaselineAgentPolicy())
            self.assertEqual(result["selected_agent"], expected, prompt)
            self.assertTrue(result["preview"])
            self.assertNotIn("response", result)

    def test_router_never_selects_blender_agent(self):
        for prompt, _ in ROUTING_CASES:
            selected = preview(prompt, policy=BaselineAgentPolicy())["selected_agent"]
            self.assertNotEqual(selected, "BLENDER_AGENT")
            self.assertIn(selected, AGENT_NAMES)

    def test_router_never_selects_a_tool(self):
        tools = set(list_tools())
        for prompt, _ in ROUTING_CASES:
            self.assertNotIn(
                preview(prompt, policy=BaselineAgentPolicy())["selected_agent"], tools
            )

    def test_router_never_selects_a_model_as_agent(self):
        model_ids = known_model_ids()
        for prompt, _ in ROUTING_CASES:
            self.assertNotIn(
                preview(prompt, policy=BaselineAgentPolicy())["selected_agent"],
                model_ids,
            )

    def test_three_d_prompt_selects_three_d_agent(self):
        result = preview(
            "Create a 3D model of a wooden chair.",
            policy=BaselineAgentPolicy(),
        )
        self.assertEqual(result["selected_agent"], THREE_D_AGENT)


class TestGeminiConfiguration(unittest.TestCase):
    """Requirement 13 + config safety."""

    def test_missing_gemini_key_raises_clean_error(self):
        old = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with self.assertRaises(ConfigurationError) as ctx:
                providers.get_client("gemini")
            message = str(ctx.exception)
            self.assertIn("GEMINI_API_KEY", message)
        finally:
            if old is not None:
                os.environ["GEMINI_API_KEY"] = old

    def test_is_configured_reports_without_revealing_key(self):
        old = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = "super-secret-value"
        try:
            self.assertTrue(providers.is_configured("gemini"))
            self.assertEqual(providers.key_env_var("gemini"), "GEMINI_API_KEY")
            self.assertNotIn("super-secret", providers.display_name("gemini"))
        finally:
            if old is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = old

    def test_gemini_model_is_env_configurable(self):
        old = os.environ.get("GEMINI_MODEL")
        os.environ["GEMINI_MODEL"] = "gemini-test-model"
        try:
            self.assertEqual(get_model("general"), "gemini-test-model")
            self.assertEqual(build_agent_registry()[CODING_AGENT].model_id,
                             "gemini-test-model")
        finally:
            if old is None:
                os.environ.pop("GEMINI_MODEL", None)
            else:
                os.environ["GEMINI_MODEL"] = old

    def test_provider_is_switchable_back_to_openrouter(self):
        """OpenRouter must remain available (Step 4 is not deleted)."""
        old = os.environ.get("AGENTROUTE_PROVIDER")
        os.environ["AGENTROUTE_PROVIDER"] = "openrouter"
        try:
            agent = build_agent_registry()[CODING_AGENT]
            self.assertEqual(agent.model_provider, "openrouter")
            self.assertEqual(agent.model_id, models.get_model("coding"))
        finally:
            if old is None:
                os.environ.pop("AGENTROUTE_PROVIDER", None)
            else:
                os.environ["AGENTROUTE_PROVIDER"] = old

    def test_per_agent_provider_override(self):
        old = os.environ.get("THREE_D_MODEL_PROVIDER")
        os.environ["THREE_D_MODEL_PROVIDER"] = "openrouter"
        try:
            registry = build_agent_registry()
            self.assertEqual(registry[THREE_D_AGENT].model_provider, "openrouter")
            # Other agents are unaffected.
            self.assertEqual(registry[GENERAL_AGENT].model_provider, "gemini")
        finally:
            if old is None:
                os.environ.pop("THREE_D_MODEL_PROVIDER", None)
            else:
                os.environ["THREE_D_MODEL_PROVIDER"] = old


class TestThreeDNoExecution(unittest.TestCase):
    """Requirement 20: Blender must not be executed in Step 5."""

    def test_three_d_run_returns_model_text_without_executing_blender(self):
        agent = ThreeDAgent()
        fake = _FakeProvider(answer="```python\nimport bpy\n```")
        os.environ["BLENDER_EXECUTION_ENABLED"] = "false"
        try:
            with _PatchedComplete(fake):
                out = agent.run("Create a 3D model of a wooden chair.")
        finally:
            os.environ.pop("BLENDER_EXECUTION_ENABLED", None)
        self.assertIn("import bpy", out)
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("3D Agent", fake.calls[0]["system"])
        self.assertIn("valid Python", fake.calls[0]["system"])
        self.assertIn("markdown fences", fake.calls[0]["system"])
        self.assertIn("preserve the existing scene", fake.calls[0]["system"])
        self.assertIn("- tool: BLENDER_TOOL", out)
        self.assertIn("- invoked: yes", out)
        self.assertIn("- executed: no", out)
        self.assertIn("- success: no", out)
        self.assertIn("No Blender scene was created.", out)

    def test_blender_tool_still_wired_but_not_executed(self):
        agent = ThreeDAgent()
        self.assertIn("BLENDER_TOOL", agent.available_tools)
        os.environ.pop("BLENDER_EXECUTION_ENABLED", None)
        result = agent.validate_script("import bpy\n")
        self.assertTrue(result.success)
        self.assertFalse(result.metadata["executed"])

    def test_offline_fallback_script_is_valid_python(self):
        script = ThreeDAgent().build_blender_script("a wooden chair")
        self.assertIn("import bpy", script)
        compile(script, "<generated>", "exec")

    def test_a_brace_typo_is_caught_before_blender_and_retried_once(self):
        bad = "```python\nimport bpy\nbpy.ops.mesh.primitive_cylinder_add(\n}\n```"
        good = "```python\nimport bpy\nbpy.ops.mesh.primitive_cube_add()\n```"
        caught = python_syntax_error("import bpy\nbpy.ops.mesh.primitive_cylinder_add(\n}\n")
        self.assertIn("does not match", caught)
        self.assertIn("}", caught)
        fake = _SequenceProvider([bad, good])
        seen = []

        def fake_execute(self, script, output_dir=None):
            seen.append(script)
            return ToolResult(
                tool="BLENDER_TOOL",
                success=True,
                metadata={"executed": True, "invoked": True},
            )

        with _PatchedComplete(fake), patch.object(BlenderTool, "execute", fake_execute):
            out = ThreeDAgent().run("Create a simple Blender scene with a cube.")

        self.assertEqual(len(fake.calls), 2)
        self.assertIn("Create a simple Blender scene with a cube.", fake.calls[1]["prompt"])
        self.assertIn("Syntax error:", fake.calls[1]["prompt"])
        self.assertIn("}", fake.calls[1]["prompt"])
        self.assertEqual(len(seen), 1)
        self.assertIn("primitive_cube_add", seen[0])
        self.assertNotIn("}", seen[0])
        self.assertIn("- success: no", out)
        self.assertIn("No Blender scene was created.", out)
        self.assertNotIn("- success: yes", out)

    def test_a_second_invalid_script_does_not_launch_blender(self):
        bad = "```python\nimport bpy\nbpy.ops.mesh.primitive_cylinder_add(\n}\n```"
        fake = _SequenceProvider([bad, bad])
        with _PatchedComplete(fake), patch.object(BlenderTool, "execute") as execute:
            out = ThreeDAgent().run("Add a cylinder next to the cube.")
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("Add a cylinder next to the cube.", fake.calls[1]["prompt"])
        execute.assert_not_called()
        self.assertIn("not valid Python", out)
        self.assertIn("No scene was created.", out)
        self.assertIn("- syntax error:", out)
        self.assertNotIn("- success: yes", out)
        self.assertNotIn("scene.blend", out)

    def test_a_disabled_plugin_does_not_launch_blender(self):
        script = "```python\nimport bpy\nbpy.ops.mesh.primitive_cube_add()\n```"
        fake = _SequenceProvider([script, script])
        token = blender_capability.set(False)
        try:
            with _PatchedComplete(fake), patch.object(BlenderTool, "execute") as execute:
                out = ThreeDAgent().run("Create a 3D table in Blender.")
        finally:
            blender_capability.reset(token)
        self.assertEqual(len(fake.calls), 1)
        execute.assert_not_called()
        self.assertIn("Blender is disabled. Enable the Blender plugin to execute this 3D task.", out)
        self.assertIn("- invoked: no", out)
        self.assertIn("- executed: no", out)
        self.assertIn("- success: no", out)
        self.assertIn("No Blender scene was created.", out)
        self.assertNotIn("scene.blend", out)

    def test_an_enabled_plugin_still_calls_the_blender_tool(self):
        script = "```python\nimport bpy\nbpy.ops.mesh.primitive_cube_add()\n```"
        fake = _SequenceProvider([script])
        token = blender_capability.set(True)
        seen = []

        def fake_execute(self, script, output_dir=None):
            seen.append(script)
            return ToolResult(
                tool="BLENDER_TOOL",
                success=True,
                artifacts=["scene.blend"],
                metadata={"executed": True, "invoked": True, "objects": ["Cube"]},
            )

        try:
            with _PatchedComplete(fake), patch.object(BlenderTool, "execute", fake_execute):
                out = ThreeDAgent().run("Create a 3D table in Blender.")
        finally:
            blender_capability.reset(token)
        self.assertEqual(len(seen), 1)
        self.assertIn("- success: yes", out)
        self.assertIn("scene.blend", out)

    def test_a_blender_runtime_failure_is_retried_once(self):
        bad = "```python\nimport bpy\nprincipled.inputs['Specular']\n```"
        good = "```python\nimport bpy\nbpy.ops.mesh.primitive_cube_add()\n```"
        fake = _SequenceProvider([bad, good])
        seen = []

        def fake_execute(self, script, output_dir=None):
            seen.append(script)
            if len(seen) == 1:
                return ToolResult(
                    tool="BLENDER_TOOL",
                    success=False,
                    error="KeyError: 'Specular'",
                    metadata={"executed": True, "invoked": True, "scene_written": False},
                )
            return ToolResult(
                tool="BLENDER_TOOL",
                success=True,
                artifacts=["scene.blend"],
                metadata={"executed": True, "invoked": True, "objects": ["Cube"]},
            )

        with _PatchedComplete(fake), patch.object(BlenderTool, "execute", fake_execute):
            out = ThreeDAgent().run("Create a wooden dining table.")

        self.assertEqual(len(fake.calls), 2)
        self.assertIn("Blender error:", fake.calls[1]["prompt"])
        self.assertIn("Specular", fake.calls[1]["prompt"])
        self.assertEqual(len(seen), 2)
        self.assertIn("primitive_cube_add", seen[1])
        self.assertIn("- success: yes", out)
        self.assertIn("scene.blend", out)

    def test_a_second_runtime_failure_is_not_retried_again(self):
        bad = "```python\nimport bpy\nprincipled.inputs['Specular']\n```"
        fake = _SequenceProvider([bad, bad, bad])
        seen = []

        def fake_execute(self, script, output_dir=None):
            seen.append(script)
            return ToolResult(
                tool="BLENDER_TOOL",
                success=False,
                error="KeyError: 'Specular'",
                metadata={"executed": True, "invoked": True, "scene_written": False},
            )

        with _PatchedComplete(fake), patch.object(BlenderTool, "execute", fake_execute):
            out = ThreeDAgent().run("Create a wooden dining table.")

        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(len(seen), 2)
        self.assertIn("- success: no", out)
        self.assertIn("KeyError", out)
        self.assertIn("No Blender scene was created.", out)

    def test_a_missing_scene_keeps_the_blender_traceback(self):
        import subprocess

        proc = subprocess.CompletedProcess(
            args=["blender"],
            returncode=0,
            stdout="Blender 5.2.2",
            stderr="Traceback (most recent call last):\nKeyError: 'bpy_prop_collection[key]: key \"Specular\" not found'",
        )
        with patch.dict(os.environ, {"BLENDER_EXECUTION_ENABLED": "true"}):
            with patch.object(BlenderTool, "find_binary", return_value="blender.exe"):
                with patch("tools.blender_tool.subprocess.run", return_value=proc):
                    result = BlenderTool().execute("import bpy\n")
        self.assertFalse(result.success)
        self.assertTrue(result.metadata["executed"])
        self.assertFalse(result.metadata["scene_written"])
        self.assertEqual(result.artifacts, [])
        self.assertIn("No scene was created.", result.error)
        self.assertIn("KeyError", result.error)
        self.assertIn("Specular", result.error)


class TestUiHelpers(unittest.TestCase):
    """The UI's pure logic, testable without Streamlit installed."""

    def test_extracts_python_code_blocks(self):
        from ui_helpers import extract_code_blocks, strip_code_blocks

        text = "Here is a scene:\n```python\nimport bpy\nbpy.ops.mesh.primitive_cube_add()\n```\nDone."
        blocks = extract_code_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertIn("import bpy", blocks[0])
        prose = strip_code_blocks(text)
        self.assertNotIn("import bpy", prose)
        self.assertIn("Here is a scene", prose)

    def test_handles_response_with_no_code(self):
        from ui_helpers import extract_code_blocks, strip_code_blocks

        self.assertEqual(extract_code_blocks("just prose"), [])
        self.assertEqual(strip_code_blocks("just prose"), "just prose")

    def test_flow_is_built_from_the_runtime_result(self):
        from ui_helpers import build_flow

        self.assertEqual(
            build_flow(CODING_AGENT, "Gemini", live=True),
            ["USER", "ROUTER", CODING_AGENT, "GEMINI", "RESULT"],
        )
        self.assertEqual(
            build_flow(THREE_D_AGENT, "Gemini", live=True),
            ["USER", "ROUTER", THREE_D_AGENT, "GEMINI", "3D RESPONSE"],
        )
        offline = build_flow(GENERAL_AGENT, "Gemini", live=False)
        self.assertIn("(model execution disabled)", offline)
        self.assertNotIn("GEMINI", offline)

    def test_flow_never_mentions_a_blender_agent(self):
        from ui_helpers import build_flow

        self.assertNotIn("BLENDER_AGENT", build_flow(THREE_D_AGENT, "Gemini", True))


class TestEndToEndWithFakedGemini(unittest.TestCase):
    """Full USER -> ROUTER -> real AGENT -> provider -> RESPONSE path."""

    def test_each_prompt_reaches_its_agent_and_gemini(self):
        registry = build_agent_registry()
        for prompt, expected_agent in ROUTING_CASES:
            fake = _FakeProvider(answer="response text")
            with _PatchedComplete(fake):
                result = route(prompt, policy=BaselineAgentPolicy(), agents=registry)
            self.assertEqual(result["selected_agent"], expected_agent, prompt)
            self.assertTrue(result["response_success"], prompt)
            self.assertEqual(result["response"], "response text", prompt)
            # Exactly one Gemini call, made by the selected agent.
            self.assertEqual(len(fake.calls), 1, prompt)
            self.assertEqual(fake.calls[0]["provider"], "gemini", prompt)
            self.assertEqual(
                fake.calls[0]["system"], registry[expected_agent].system_prompt, prompt
            )


class TestPlaywrightCapabilityGate(unittest.TestCase):
    """The Playwright plugin blocks the browser tool. It does not select an agent."""

    def test_a_disabled_plugin_does_not_launch_a_browser(self):
        from agents.web_agent import WebAgent
        from tools.playwright_tool import playwright_capability

        agent = WebAgent()
        tool = agent.get_tool("PLAYWRIGHT_TOOL")
        token = playwright_capability.set(False)
        try:
            with patch.object(agent, "_complete", side_effect=AssertionError("model")), patch.object(
                tool, "run", side_effect=AssertionError("browser")
            ):
                out = agent.run("Open example.com and tell me the page title.")
        finally:
            playwright_capability.reset(token)
        self.assertIn(
            "Playwright is disabled. Enable the Playwright plugin to execute this browser task.",
            out,
        )
        self.assertIn("- tool: PLAYWRIGHT_TOOL", out)
        self.assertIn("- invoked: no", out)
        self.assertIn("- executed: no", out)
        self.assertIn("- success: no", out)
        self.assertNotIn("Example Domain", out)

    def test_an_enabled_plugin_runs_the_planned_browser_actions(self):
        from agents.web_agent import WebAgent
        from tools.playwright_tool import playwright_capability

        agent = WebAgent()
        tool = agent.get_tool("PLAYWRIGHT_TOOL")
        plan = (
            '{"actions":[{"op":"goto","url":"https://example.com"},'
            '{"op":"title"}]}'
        )
        observed = ToolResult(
            tool="PLAYWRIGHT_TOOL",
            success=True,
            output="Page title: Example Domain\nURL: https://example.com/",
            metadata={"invoked": True, "executed": True, "title": "Example Domain"},
        )
        token = playwright_capability.set(True)
        try:
            with patch.object(agent, "_complete", return_value=plan), patch.object(
                tool, "run", return_value=observed
            ) as run:
                out = agent.run("Open example.com and tell me the page title.")
        finally:
            playwright_capability.reset(token)
        run.assert_called_once()
        actions = run.call_args.args[0]
        self.assertEqual(actions[0]["op"], "goto")
        self.assertEqual(actions[0]["url"], "https://example.com")
        self.assertIn("Page title: Example Domain", out)
        self.assertIn("- executed: yes", out)
        self.assertIn("- success: yes", out)

    def test_a_reply_without_a_browser_plan_does_not_launch(self):
        from agents.web_agent import WebAgent
        from tools.playwright_tool import playwright_capability

        agent = WebAgent()
        tool = agent.get_tool("PLAYWRIGHT_TOOL")
        token = playwright_capability.set(True)
        try:
            with patch.object(agent, "_complete", return_value="def is_prime(n):\n    return n > 1\n"), patch.object(
                tool, "run", side_effect=AssertionError("browser")
            ):
                out = agent.run("Write a Python function that checks whether a number is prime.")
        finally:
            playwright_capability.reset(token)
        self.assertIn("def is_prime", out)
        self.assertNotIn("Playwright tool result:", out)

    def test_a_follow_up_plan_reuses_the_page_already_in_the_task(self):
        from agents.web_agent import WebAgent
        from tools.playwright_tool import playwright_capability

        agent = WebAgent()
        tool = agent.get_tool("PLAYWRIGHT_TOOL")
        observed = ToolResult(
            tool="PLAYWRIGHT_TOOL",
            success=True,
            output="Page title: Example Domain\nScreenshot: C:/temp/page.png",
            metadata={"invoked": True, "executed": True},
        )
        prompt = (
            "URL: https://example.com/\n\n"
            "<current_request>\nNow take a screenshot.\n</current_request>"
        )
        token = playwright_capability.set(True)
        try:
            with patch.object(
                agent, "_complete", return_value='{"actions":[{"op":"screenshot"}]}'
            ), patch.object(tool, "run", return_value=observed) as run:
                out = agent.run(prompt)
        finally:
            playwright_capability.reset(token)
        actions = run.call_args.args[0]
        self.assertEqual(actions[0], {"op": "goto", "url": "https://example.com/"})
        self.assertEqual(actions[1]["op"], "screenshot")
        self.assertIn("executed: yes", out)


if __name__ == "__main__":
    unittest.main()
