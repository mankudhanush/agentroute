"""Task-context continuity. Model calls are faked; routing itself is untouched."""

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import router as router_module  # noqa: E402
from agents.base_agent import BaseAgent  # noqa: E402
from conversation_state import ConversationState  # noqa: E402
from model_selector import ModelSelection  # noqa: E402
from router import preview, route  # noqa: E402
from routing_policy import (  # noqa: E402
    CODING_AGENT,
    GENERAL_AGENT,
    REASONING_AGENT,
    RESEARCH_AGENT,
    THREE_D_AGENT,
    BaselineAgentPolicy,
)
from task_context import content_tokens, match_task_context  # noqa: E402

_NAMES = (GENERAL_AGENT, CODING_AGENT, REASONING_AGENT, RESEARCH_AGENT, THREE_D_AGENT)


class LogAgent(BaseAgent):
    def __init__(self, name, log, tools=(), model_id=None, model_provider=None):
        self.name = name
        self.log = log
        self.available_tools = tuple(tools)
        self.model_id = model_id
        self.model_provider = model_provider

    def run(self, prompt):
        self.log.append({"agent": self.name, "model": self.model_id, "prompt": prompt})
        return "stored-answer"

    def run_with_model(self, prompt, model_id=None, provider=None, fallback_model_ids=None):
        import providers

        return providers.complete(provider, model_id, prompt, system=None)


def _registry(log, tools_for=None, **agent_kwargs):
    tools_for = tools_for or {}
    return {
        name: LogAgent(name, log, tools=tools_for.get(name, ()), **agent_kwargs)
        for name in _NAMES
    }


class ScriptedPolicy:
    def __init__(self, names):
        self.names = list(names)
        self.index = 0

    def select_agent(self, intent, complexity, confidence, context=None):
        name = self.names[min(self.index, len(self.names) - 1)]
        self.index += 1
        return {
            "selected_agent": name,
            "policy": "scripted",
            "decision_layer": "scripted",
            "reason": "scripted",
            "fallback_used": False,
        }


def _ask(state, prompt, log, policy=None, tools_for=None, **agent_kwargs):
    return route(
        prompt,
        policy=policy or BaselineAgentPolicy(),
        conversation_state=state,
        agents=_registry(log, tools_for=tools_for, **agent_kwargs),
    )


class TestContextContinuity(unittest.TestCase):
    def test_matcher_source_has_no_domain_rules(self):
        import task_context

        source = inspect.getsource(task_context).lower()
        for word in (
            "wardrobe",
            "photosynthesis",
            "fastapi",
            "jwt",
            "blender",
            "postgresql",
            "nvidia",
            "gemini",
            "groq",
            "coding_agent",
            "three_d_agent",
        ):
            self.assertNotIn(word, source)

    def test_single_prompt_without_state_is_unchanged(self):
        log = []
        result = route(
            "What is Python?",
            policy=BaselineAgentPolicy(),
            agents=_registry(log),
        )
        self.assertEqual(log[-1]["prompt"], "What is Python?")
        self.assertIsNone(result["context_id"])
        self.assertFalse(result["context_continued"])
        self.assertEqual(result["context_turns"], 0)
        self.assertEqual(result["selected_agent"], GENERAL_AGENT)

    def test_first_prompt_creates_a_context(self):
        state = ConversationState()
        log = []
        result = _ask(state, "Build a Python REST API.", log)
        self.assertEqual(len(state.contexts), 1)
        self.assertFalse(result["context_continued"])
        self.assertEqual(result["context_turns"], 0)
        self.assertEqual(result["context_id"], state.contexts[0].context_id)
        self.assertEqual(log[-1]["prompt"], "Build a Python REST API.")
        self.assertEqual(state.context()["previous_prompts"], ["Build a Python REST API."])

    def test_related_follow_up_reuses_the_context(self):
        state = ConversationState()
        log = []
        first = _ask(state, "Build a Python REST API.", log)
        second = _ask(state, "Add validation.", log)
        self.assertEqual(second["context_id"], first["context_id"])
        self.assertTrue(second["context_continued"])
        self.assertEqual(second["context_turns"], 1)
        self.assertEqual(len(state.contexts), 1)
        self.assertEqual(len(state.contexts[0].turns), 2)
        sent = log[-1]["prompt"]
        self.assertIn("We are continuing an existing task/project", sent)
        self.assertIn("Build a Python REST API.", sent)
        self.assertIn("stored-answer", sent)
        self.assertIn("Add validation.", sent)
        self.assertIn("Continue the existing work and apply the current request to it.", sent)
        self.assertIn("Do not treat the current request as an unrelated standalone question.", sent)

    def test_third_turn_receives_the_accumulated_branch(self):
        state = ConversationState()
        log = []
        prompts = [
            "Design a backend with JWT authentication.",
            "Use PostgreSQL for the database.",
            "Now write tests for authentication.",
        ]
        ids = [_ask(state, prompt, log)["context_id"] for prompt in prompts]
        self.assertEqual(len(set(ids)), 1)
        sent = log[-1]["prompt"]
        for earlier in prompts[:2]:
            self.assertIn(earlier, sent)
        self.assertIn(prompts[2], sent)
        self.assertEqual(len(state.contexts[0].turns), 3)

    def test_unrelated_prompt_opens_a_new_context(self):
        state = ConversationState()
        log = []
        first = _ask(state, "What is photosynthesis?", log)
        second = _ask(state, "Design a 3D model.", log)
        self.assertNotEqual(first["context_id"], second["context_id"])
        self.assertFalse(second["context_continued"])
        self.assertEqual(len(state.contexts), 2)
        sent = log[-1]["prompt"]
        self.assertNotIn("photosynthesis", sent.lower())
        self.assertIn("Design a 3D model.", sent)
        self.assertIn("<task_context>\nNew task.\n</task_context>", sent)
        self.assertIn("<previous_work>\nNone.\n</previous_work>", sent)
        self.assertNotIn("Continue the existing work", sent)
        self.assertNotIn("<working_artifact>", sent)
        self.assertNotIn("stored-answer", sent)

    def test_several_branches_can_coexist_and_be_resumed(self):
        state = ConversationState()
        log = []
        api = _ask(state, "Design a backend with JWT authentication.", log)
        photo = _ask(state, "What is photosynthesis?", log)
        wardrobe = _ask(state, "Design a 2400mm wardrobe.", log)
        wood = _ask(state, "Use walnut.", log)
        resumed = _ask(state, "Add JWT refresh-token tests to the API.", log)
        fresh = _ask(state, "Explain quantum computing.", log)

        self.assertEqual(wood["context_id"], wardrobe["context_id"])
        self.assertNotEqual(photo["context_id"], api["context_id"])
        self.assertNotEqual(wardrobe["context_id"], api["context_id"])
        self.assertEqual(resumed["context_id"], api["context_id"])
        self.assertNotEqual(fresh["context_id"], api["context_id"])
        self.assertNotEqual(fresh["context_id"], wardrobe["context_id"])
        self.assertEqual(len(state.contexts), 4)

        back = log[-2]["prompt"]
        self.assertIn("JWT authentication", back)
        self.assertNotIn("photosynthesis", back.lower())
        self.assertNotIn("walnut", back.lower())
        self.assertNotIn("wardrobe", back.lower())

        quantum = log[-1]["prompt"]
        self.assertNotIn("photosynthesis", quantum.lower())
        self.assertNotIn("walnut", quantum.lower())
        self.assertNotIn("JWT", quantum)

    def test_html_form_change_includes_the_latest_artifact(self):
        state = ConversationState()
        log = []
        form = (
            "<!DOCTYPE html>\n<html><body>\n"
            "<form action=\"/submit\">\n<label>Name</label>\n"
            "<input name=\"name\">\n</form>\n"
            "</body></html>"
        )

        class FormAgent(LogAgent):
            def run(self, prompt):
                self.log.append({"agent": self.name, "model": self.model_id, "prompt": prompt})
                return form

        route(
            "Create an HTML form.",
            policy=BaselineAgentPolicy(),
            conversation_state=state,
            agents={name: FormAgent(name, log) for name in _NAMES},
        )
        self.assertEqual(state.contexts[0].latest_artifact, form)
        route(
            "change background to black",
            policy=BaselineAgentPolicy(),
            conversation_state=state,
            agents={name: LogAgent(name, log) for name in _NAMES},
        )
        sent = log[-1]["prompt"]
        self.assertIn("Create an HTML form.", sent)
        self.assertIn(form, sent)
        self.assertIn("<working_artifact", sent)
        self.assertIn("change background to black", sent)
        self.assertIn("Modify the latest working artifact when the current request changes that work.", sent)
        self.assertIn("Do not treat the current request as an unrelated standalone question.", sent)
        self.assertNotEqual(sent.strip(), "change background to black")
        self.assertEqual(len(state.contexts), 1)

    def test_model_switch_receives_the_existing_artifact(self):
        state = ConversationState()
        seen = []
        form = "<form id=\"signup\"><input name=\"email\"></form>"
        replies = [form, "body { background: black; }"]

        def fake_complete(provider, model, prompt, system=None):
            seen.append({"provider": provider, "model": model, "prompt": prompt})
            return replies.pop(0)

        selections = [
            ModelSelection("model-a", "gemini", "first"),
            ModelSelection("model-b", "nvidia", "second"),
        ]

        def fake_select(profile, agent, registry=None, available_providers=None):
            return selections.pop(0)

        import providers

        original_select = router_module.select_model
        original_complete = providers.complete
        router_module.select_model = fake_select
        providers.complete = fake_complete
        try:
            log = []
            first = _ask(
                state,
                "Create an HTML form.",
                log,
                model_id="configured-model",
                model_provider="gemini",
            )
            second = _ask(
                state,
                "change background to black",
                log,
                model_id="configured-model",
                model_provider="gemini",
            )
        finally:
            router_module.select_model = original_select
            providers.complete = original_complete

        self.assertEqual(second["context_id"], first["context_id"])
        self.assertEqual(seen[0]["model"], "model-a")
        self.assertEqual(seen[1]["model"], "model-b")
        self.assertEqual(seen[0]["prompt"], "Create an HTML form.")
        handed = seen[1]["prompt"]
        self.assertIn(form, handed)
        self.assertIn("<working_artifact", handed)
        self.assertIn("change background to black", handed)
        self.assertIn("Modify the latest working artifact when the current request changes that work.", handed)
        self.assertEqual(state.contexts[0].latest_artifact, "body { background: black; }")

    def test_modification_request_is_applied_to_the_stored_project(self):
        state = ConversationState()
        log = []
        project = "app.py\ntemplates/index.html\nstatic/style.css\nbody { color: navy; }"

        class ProjectAgent(LogAgent):
            def run(self, prompt):
                self.log.append({"agent": self.name, "model": self.model_id, "prompt": prompt})
                return project

        agents = {name: ProjectAgent(name, log) for name in _NAMES}
        route(
            "Create a café website using Flask and HTML.",
            policy=BaselineAgentPolicy(),
            conversation_state=state,
            agents=agents,
        )
        self.assertEqual(log[-1]["prompt"], "Create a café website using Flask and HTML.")
        route(
            "Change the color in static/style.css to black.",
            policy=BaselineAgentPolicy(),
            conversation_state=state,
            agents={name: LogAgent(name, log) for name in _NAMES},
        )
        sent = log[-1]["prompt"]
        self.assertIn("We are continuing an existing task/project", sent)
        self.assertIn("Create a café website using Flask and HTML.", sent)
        self.assertIn("static/style.css", sent)
        self.assertIn("app.py", sent)
        self.assertIn("Change the color in static/style.css to black.", sent)
        self.assertIn("Continue the existing work and apply the current request to it.", sent)
        self.assertNotEqual(sent, "Change the color in static/style.css to black.")
        self.assertEqual(len(state.contexts), 1)

    def test_multi_turn_branch_keeps_every_earlier_request(self):
        state = ConversationState()
        log = []
        prompts = [
            "Design a wardrobe.",
            "Make it 2400mm wide.",
            "Use walnut.",
            "Add LED lighting.",
            "Make the middle door mirrored.",
        ]
        ids = [_ask(state, prompt, log)["context_id"] for prompt in prompts]
        self.assertEqual(len(set(ids)), 1)
        sent = log[-1]["prompt"]
        for earlier in prompts[:-1]:
            self.assertIn(earlier, sent)
        self.assertIn(prompts[-1], sent)
        self.assertEqual(state.contexts[0].turns[0].prompt, prompts[0])

    def test_model_switch_passes_accumulated_context_to_the_new_model(self):
        state = ConversationState()
        seen = []

        def fake_complete(provider, model, prompt, system=None):
            seen.append({"provider": provider, "model": model, "prompt": prompt})
            return "stored-answer"

        selections = [
            ModelSelection("model-a", "gemini", "first"),
            ModelSelection("model-b", "groq", "second"),
        ]

        def fake_select(profile, agent, registry=None, available_providers=None):
            return selections.pop(0)

        import providers

        original_select = router_module.select_model
        original_complete = providers.complete
        router_module.select_model = fake_select
        providers.complete = fake_complete
        try:
            log = []
            first = _ask(
                state,
                "Design a production FastAPI authentication system.",
                log,
                model_id="configured-model",
                model_provider="gemini",
            )
            second = _ask(
                state,
                "Now write unit tests for the authentication system.",
                log,
                model_id="configured-model",
                model_provider="gemini",
            )
        finally:
            router_module.select_model = original_select
            providers.complete = original_complete

        self.assertEqual(second["context_id"], first["context_id"])
        self.assertEqual(seen[0]["model"], "model-a")
        self.assertEqual(seen[1]["model"], "model-b")
        self.assertNotEqual(seen[0]["provider"], seen[1]["provider"])
        handed = seen[1]["prompt"]
        self.assertIn("Design a production FastAPI authentication system.", handed)
        self.assertIn("stored-answer", handed)
        self.assertIn("Now write unit tests for the authentication system.", handed)
        self.assertIn("Continue the existing work and apply the current request to it.", handed)
        self.assertIsInstance(handed, str)

    def test_agent_change_does_not_reset_a_related_context(self):
        state = ConversationState()
        log = []
        policy = ScriptedPolicy([CODING_AGENT, REASONING_AGENT])
        tools = {CODING_AGENT: ("CODE_EXECUTION_TOOL",), REASONING_AGENT: ("WEB_SEARCH_TOOL",)}
        first = _ask(
            state,
            "Design a backend with JWT authentication.",
            log,
            policy=policy,
            tools_for=tools,
        )
        second = _ask(state, "Add refresh tokens to it.", log, policy=policy, tools_for=tools)
        self.assertEqual(first["selected_agent"], CODING_AGENT)
        self.assertEqual(second["selected_agent"], REASONING_AGENT)
        self.assertEqual(first["context_id"], second["context_id"])
        branch = state.contexts[0]
        self.assertEqual(branch.turns[0].agent, CODING_AGENT)
        self.assertEqual(branch.turns[1].agent, REASONING_AGENT)
        self.assertEqual(branch.turns[0].tools, ("CODE_EXECUTION_TOOL",))
        self.assertEqual(branch.turns[1].tools, ("WEB_SEARCH_TOOL",))
        self.assertIn("Design a backend with JWT authentication.", log[-1]["prompt"])
        self.assertEqual(branch.last_agent, REASONING_AGENT)

    def test_assistant_text_is_bounded_but_earlier_requests_remain(self):
        state = ConversationState()
        log = []

        class Huge(LogAgent):
            def run(self, prompt):
                self.log.append({"agent": self.name, "model": None, "prompt": prompt})
                return "Z" * 20000

        agents = {name: Huge(name, log) for name in _NAMES}
        route(
            "Build a Python REST API.",
            policy=BaselineAgentPolicy(),
            conversation_state=state,
            agents=agents,
        )
        route(
            "Add validation.",
            policy=BaselineAgentPolicy(),
            conversation_state=state,
            agents={name: LogAgent(name, log) for name in _NAMES},
        )
        sent = log[-1]["prompt"]
        self.assertIn("Build a Python REST API.", sent)
        self.assertIn("Z" * 100, sent)
        self.assertNotIn("Z" * 20000, sent)
        self.assertIn("<working_artifact", sent)
        self.assertIn("Add validation.", sent)

    def test_preview_reports_the_match_without_recording_or_calling_a_model(self):
        state = ConversationState()
        log = []
        first = _ask(state, "Build a Python REST API.", log)
        before = len(state.turns)
        looked = preview(
            "Add validation.",
            policy=BaselineAgentPolicy(),
            conversation_state=state,
            agents=_registry(log),
        )
        self.assertTrue(looked["preview"])
        self.assertTrue(looked["context_continued"])
        self.assertEqual(looked["context_id"], first["context_id"])
        self.assertEqual(looked["context_turns"], 1)
        self.assertIn("Build a Python REST API.", looked["context_summary"])
        self.assertEqual(len(state.turns), before)
        self.assertEqual(len(log), 1)

    def test_manual_record_still_feeds_routing_context(self):
        state = ConversationState()
        state.record("first", GENERAL_AGENT, "a", intent="general")
        state.record("second", CODING_AGENT, "b", intent="coding")
        self.assertEqual(state.context()["previous_prompts"], ["first", "second"])
        self.assertEqual(state.context()["last_agent"], CODING_AGENT)
        self.assertEqual(state.contexts, [])
        tokens = content_tokens("Add validation to it")
        self.assertNotIn("it", tokens)
        self.assertIn("validation", tokens)
        match = match_task_context("Add validation.", state)
        self.assertFalse(match.continued)


class SequenceAgent(LogAgent):
    def __init__(self, name, log, replies):
        super().__init__(name, log)
        self.replies = list(replies)

    def run(self, prompt):
        self.log.append({"agent": self.name, "model": self.model_id, "prompt": prompt})
        if self.replies:
            return self.replies.pop(0)
        return "stored-answer"


class TestAgentChangeDoesNotImportAnotherBranch(unittest.TestCase):
    def test_blender_follow_up_stays_and_an_unrelated_coding_task_does_not(self):
        cube = (
            "```python\nimport bpy\n"
            "bpy.ops.mesh.primitive_cube_add()\n"
            "cube.name = 'SimpleCube'\n```"
        )
        cylinder = (
            "```python\nimport bpy\n"
            "bpy.ops.mesh.primitive_cube_add()\n"
            "cube.name = 'SimpleCube'\n"
            "bpy.ops.mesh.primitive_cylinder_add()\n"
            "cylinder.name = 'SceneCylinder'\n```"
        )
        email = "def validate_email(address):\n    return '@' in address\n"
        sphere = "bpy.ops.mesh.primitive_uv_sphere_add()\n"
        state = ConversationState()
        log = []
        policy = ScriptedPolicy([THREE_D_AGENT, THREE_D_AGENT, CODING_AGENT, THREE_D_AGENT])
        replies = {
            THREE_D_AGENT: [cube, cylinder, sphere],
            CODING_AGENT: [email],
        }
        agents = {
            name: SequenceAgent(name, log, replies.get(name, []))
            for name in _NAMES
        }

        def ask(prompt):
            return route(
                prompt,
                policy=policy,
                conversation_state=state,
                agents=agents,
            )

        first = ask("Create a simple Blender scene with a cube.")
        second = ask("Add a cylinder next to the cube.")
        third = ask("Create a Python email validator.")
        fourth = ask("Add a sphere next to the cube in the Blender scene.")

        self.assertEqual(second["context_id"], first["context_id"])
        self.assertTrue(second["context_continued"])
        self.assertEqual(second["selected_agent"], THREE_D_AGENT)

        self.assertEqual(third["selected_agent"], CODING_AGENT)
        self.assertNotEqual(third["context_id"], first["context_id"])
        self.assertFalse(third["context_continued"])
        handed = log[-2]["prompt"]
        self.assertNotIn("SimpleCube", handed)
        self.assertNotIn("SceneCylinder", handed)
        self.assertNotIn("primitive_cube", handed)
        self.assertNotIn("primitive_cylinder", handed)
        self.assertNotIn("bpy", handed)
        self.assertNotIn("cube", third["response"].lower())
        self.assertNotIn("cylinder", third["response"].lower())

        self.assertEqual(fourth["context_id"], first["context_id"])
        self.assertTrue(fourth["context_continued"])
        self.assertEqual(fourth["selected_agent"], THREE_D_AGENT)
        self.assertIn("SimpleCube", log[-1]["prompt"])
        self.assertNotIn("validate_email", log[-1]["prompt"])


class RememberingPolicy(ScriptedPolicy):
    def __init__(self, names):
        super().__init__(names)
        self.seen = []

    def select_agent(self, intent, complexity, confidence, context=None):
        self.seen.append(dict(context or {}))
        return super().select_agent(intent, complexity, confidence, context)


class TestBranchRelationship(unittest.TestCase):
    """A new task, a continuation, and a return to an older branch stay distinct."""

    def _agents(self, log, replies):
        return {
            name: SequenceAgent(name, log, replies.get(name, []))
            for name in _NAMES
        }

    def _route(self, state, prompt, log, policy, replies):
        return route(
            prompt,
            policy=policy,
            conversation_state=state,
            agents=self._agents(log, replies),
        )

    def test_coding_then_a_new_scene_task_opens_its_own_branch(self):
        state = ConversationState()
        log = []
        policy = RememberingPolicy([CODING_AGENT, THREE_D_AGENT])
        replies = {
            CODING_AGENT: ["def unique(items):\n    return list(dict.fromkeys(items))\n"],
            THREE_D_AGENT: ["table-scene"],
        }
        first = self._route(
            state,
            "Write a Python function that removes duplicate values from a list.",
            log,
            policy,
            replies,
        )
        second = self._route(
            state,
            "Create a 3D table in Blender.",
            log,
            policy,
            replies,
        )
        self.assertEqual(first["selected_agent"], CODING_AGENT)
        self.assertEqual(second["selected_agent"], THREE_D_AGENT)
        self.assertFalse(second["context_continued"])
        self.assertNotEqual(second["context_id"], first["context_id"])
        self.assertEqual(policy.seen[1]["previous_prompts"], [])
        self.assertNotIn("def unique", log[-1]["prompt"])
        self.assertIn("New task.", log[-1]["prompt"])

    def test_scene_then_a_new_coding_task_does_not_keep_the_scene(self):
        state = ConversationState()
        log = []
        policy = ScriptedPolicy([THREE_D_AGENT, CODING_AGENT])
        replies = {THREE_D_AGENT: ["table-scene"], CODING_AGENT: ["def search(items, target):\n    return -1\n"]}
        first = self._route(state, "Create a 3D table in Blender.", log, policy, replies)
        second = self._route(
            state,
            "Write a Python function for binary search.",
            log,
            policy,
            replies,
        )
        self.assertEqual(second["selected_agent"], CODING_AGENT)
        self.assertFalse(second["context_continued"])
        self.assertNotEqual(second["context_id"], first["context_id"])
        self.assertNotIn("table-scene", log[-1]["prompt"])

    def test_scene_follow_up_stays_on_the_scene_branch(self):
        state = ConversationState()
        log = []
        policy = ScriptedPolicy([THREE_D_AGENT, THREE_D_AGENT])
        replies = {THREE_D_AGENT: ["table-scene", "table-with-drawer"]}
        first = self._route(state, "Create a 3D table in Blender.", log, policy, replies)
        second = self._route(state, "Add a drawer to the table.", log, policy, replies)
        self.assertEqual(second["context_id"], first["context_id"])
        self.assertTrue(second["context_continued"])
        self.assertEqual(second["selected_agent"], THREE_D_AGENT)
        self.assertIn("table-scene", log[-1]["prompt"])

    def test_coding_follow_up_stays_on_the_coding_branch(self):
        state = ConversationState()
        log = []
        policy = ScriptedPolicy([CODING_AGENT, CODING_AGENT])
        replies = {CODING_AGENT: ["def unique(items):\n    return items\n", "def unique(items):\n    \"\"\"Keep order.\"\"\"\n    return items\n"]}
        first = self._route(
            state,
            "Write a Python function that removes duplicate values from a list.",
            log,
            policy,
            replies,
        )
        second = self._route(state, "Add a docstring to the function.", log, policy, replies)
        self.assertEqual(second["context_id"], first["context_id"])
        self.assertTrue(second["context_continued"])
        self.assertIn("def unique", log[-1]["prompt"])

    def test_a_later_coding_task_can_return_to_the_scene_branch(self):
        state = ConversationState()
        log = []
        policy = RememberingPolicy([THREE_D_AGENT, THREE_D_AGENT, CODING_AGENT, THREE_D_AGENT])
        replies = {
            THREE_D_AGENT: ["table-scene", "table-with-drawer", "thicker-legs"],
            CODING_AGENT: ["def validate_email(address):\n    return '@' in address\n"],
        }
        scene = self._route(state, "Create a 3D table in Blender.", log, policy, replies)
        drawer = self._route(state, "Add a drawer to the table.", log, policy, replies)
        coding = self._route(state, "Write a Python email validator.", log, policy, replies)
        returned = self._route(state, "Make the table legs thicker.", log, policy, replies)
        self.assertEqual(drawer["context_id"], scene["context_id"])
        self.assertNotEqual(coding["context_id"], scene["context_id"])
        self.assertEqual(returned["context_id"], scene["context_id"])
        self.assertTrue(returned["context_continued"])
        self.assertEqual(returned["selected_agent"], THREE_D_AGENT)
        self.assertEqual(policy.seen[3]["previous_prompts"], ["Create a 3D table in Blender."])
        handed = log[-1]["prompt"]
        self.assertIn("table-scene", handed)
        self.assertNotIn("validate_email", handed)

    def test_a_later_scene_task_can_return_to_the_coding_branch(self):
        state = ConversationState()
        log = []
        policy = RememberingPolicy([CODING_AGENT, THREE_D_AGENT, CODING_AGENT])
        replies = {
            CODING_AGENT: ["def unique(items):\n    return items\n", "def unique(items):\n    return list(dict.fromkeys(items))\n"],
            THREE_D_AGENT: ["table-scene"],
        }
        coding = self._route(
            state,
            "Write a Python function that removes duplicate values from a list.",
            log,
            policy,
            replies,
        )
        scene = self._route(state, "Create a 3D table in Blender.", log, policy, replies)
        returned = self._route(state, "Update the duplicate function.", log, policy, replies)
        self.assertNotEqual(scene["context_id"], coding["context_id"])
        self.assertEqual(returned["context_id"], coding["context_id"])
        self.assertTrue(returned["context_continued"])
        self.assertEqual(returned["selected_agent"], CODING_AGENT)
        self.assertEqual(
            policy.seen[2]["previous_prompts"],
            ["Write a Python function that removes duplicate values from a list."],
        )
        self.assertIn("def unique", log[-1]["prompt"])
        self.assertNotIn("table-scene", log[-1]["prompt"])

    def test_two_scene_branches_return_to_the_named_one(self):
        state = ConversationState()
        log = []
        policy = ScriptedPolicy([THREE_D_AGENT, THREE_D_AGENT, THREE_D_AGENT])
        replies = {THREE_D_AGENT: ["table-scene", "chair-scene", "thicker-legs"]}
        table = self._route(state, "Create a 3D table in Blender.", log, policy, replies)
        chair = self._route(state, "Create a 3D chair in Blender.", log, policy, replies)
        returned = self._route(state, "Make the table legs thicker.", log, policy, replies)
        self.assertNotEqual(chair["context_id"], table["context_id"])
        self.assertEqual(returned["context_id"], table["context_id"])
        self.assertIn("table-scene", log[-1]["prompt"])
        self.assertNotIn("chair-scene", log[-1]["prompt"])

    def test_a_shared_single_token_does_not_switch_to_an_older_branch(self):
        state = ConversationState()
        log = []
        policy = ScriptedPolicy([CODING_AGENT, CODING_AGENT, CODING_AGENT])
        replies = {
            CODING_AGENT: ["api-artifact", "email-artifact", "helper-artifact"],
        }
        agents = self._agents(log, replies)
        api = route("Build a Python REST API.", policy=policy, conversation_state=state, agents=agents)
        email = route("Write a Python email validator.", policy=policy, conversation_state=state, agents=agents)
        helper = route("Add a Python helper.", policy=policy, conversation_state=state, agents=agents)
        self.assertNotEqual(email["context_id"], api["context_id"])
        self.assertEqual(helper["context_id"], email["context_id"])
        self.assertNotIn("api-artifact", log[-1]["prompt"])

    def test_one_shared_word_does_not_attach_a_new_task_to_an_older_branch(self):
        state = ConversationState()
        log = []
        policy = ScriptedPolicy([CODING_AGENT, CODING_AGENT])
        replies = {CODING_AGENT: ["def unique(items):\n    return items\n", "table-script"]}
        coding = self._route(
            state,
            "Write a Python function that removes duplicate values from a list.",
            log,
            policy,
            replies,
        )
        scene = self._route(
            state,
            "Create a 3D table in Blender using Python.",
            log,
            policy,
            replies,
        )
        self.assertNotEqual(scene["context_id"], coding["context_id"])
        self.assertFalse(scene["context_continued"])
        self.assertNotIn("def unique", log[-1]["prompt"])

    def test_an_explicit_reference_recovers_the_older_branch_and_its_artifact(self):
        state = ConversationState()
        log = []
        policy = ScriptedPolicy([THREE_D_AGENT, CODING_AGENT, THREE_D_AGENT])
        replies = {
            THREE_D_AGENT: ["table-scene", "another-drawer"],
            CODING_AGENT: ["def validate_email(address):\n    return True\n"],
        }
        scene = self._route(state, "Create a 3D table in Blender.", log, policy, replies)
        self._route(state, "Write a Python email validator.", log, policy, replies)
        returned = self._route(state, "Add another drawer to the table.", log, policy, replies)
        self.assertEqual(returned["context_id"], scene["context_id"])
        self.assertTrue(returned["has_artifact"])
        self.assertIn("table-scene", log[-1]["prompt"])
        self.assertNotIn("validate_email", log[-1]["prompt"])

    def test_model_switch_keeps_the_branch_for_a_later_return(self):
        state = ConversationState()
        seen = []
        replies = [
            "def unique(items):\n    return items\n",
            "def unique(items):\n    return list(dict.fromkeys(items))\n",
            "table-scene",
            "def unique(items):\n    return list(dict.fromkeys(items))\n",
        ]

        def fake_complete(provider, model, prompt, system=None):
            seen.append({"model": model, "prompt": prompt})
            return replies.pop(0)

        selections = [
            ModelSelection("model-a", "gemini", "first"),
            ModelSelection("model-b", "nvidia", "second"),
            ModelSelection("model-c", "groq", "third"),
            ModelSelection("model-a", "gemini", "fourth"),
        ]

        def fake_select(profile, agent, registry=None, available_providers=None):
            return selections.pop(0)

        import providers

        original_select = router_module.select_model
        original_complete = providers.complete
        router_module.select_model = fake_select
        providers.complete = fake_complete
        log = []
        policy = ScriptedPolicy([CODING_AGENT, CODING_AGENT, THREE_D_AGENT, CODING_AGENT])
        try:
            first = _ask(
                state,
                "Write a Python function that removes duplicate values from a list.",
                log,
                policy=policy,
                model_id="configured-model",
                model_provider="gemini",
            )
            second = _ask(
                state,
                "Add a docstring to the function.",
                log,
                policy=policy,
                model_id="configured-model",
                model_provider="gemini",
            )
            _ask(
                state,
                "Create a 3D table in Blender.",
                log,
                policy=policy,
                model_id="configured-model",
                model_provider="gemini",
            )
            returned = _ask(
                state,
                "Update the duplicate function.",
                log,
                policy=policy,
                model_id="configured-model",
                model_provider="gemini",
            )
        finally:
            router_module.select_model = original_select
            providers.complete = original_complete

        self.assertEqual(second["context_id"], first["context_id"])
        self.assertEqual(seen[0]["model"], "model-a")
        self.assertEqual(seen[1]["model"], "model-b")
        self.assertEqual(returned["context_id"], first["context_id"])
        self.assertNotEqual(returned["selected_model"], second["selected_model"])
        self.assertIn("dict.fromkeys", seen[-1]["prompt"])
        self.assertNotIn("table-scene", seen[-1]["prompt"])

    def test_preview_of_a_return_does_not_record_a_turn(self):
        state = ConversationState()
        log = []
        policy = ScriptedPolicy([THREE_D_AGENT, CODING_AGENT, THREE_D_AGENT])
        replies = {THREE_D_AGENT: ["table-scene"], CODING_AGENT: ["def validate_email(address):\n    return True\n"]}
        scene = self._route(state, "Create a 3D table in Blender.", log, policy, replies)
        self._route(state, "Write a Python email validator.", log, policy, replies)
        before = (len(state.turns), len(state.contexts), len(log))
        looked = preview(
            "Make the table legs thicker.",
            policy=ScriptedPolicy([THREE_D_AGENT]),
            conversation_state=state,
            agents=self._agents(log, replies),
        )
        self.assertTrue(looked["preview"])
        self.assertTrue(looked["context_continued"])
        self.assertEqual(looked["context_id"], scene["context_id"])
        self.assertEqual(len(state.turns), before[0])
        self.assertEqual(len(state.contexts), before[1])
        self.assertEqual(len(log), before[2])
