"""API boundary tests. Routing decisions come from router.route(), not the API."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agentroute"))
sys.path.insert(0, str(ROOT / "backend"))

import blender_scenes  # noqa: E402
import providers  # noqa: E402
import router  # noqa: E402
from app import create_app  # noqa: E402
from conversation_state import ConversationState  # noqa: E402
from errors import ConfigurationError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FIXTURE = {
    "response": "core response",
    "response_success": True,
    "selected_agent": "REASONING_AGENT",
    "intent": "reasoning",
    "complexity": "complex",
    "confidence": 0.91,
    "policy": "laya",
    "decision_layer": "laya",
    "routing_reason": "Laya Decision AI selected REASONING_AGENT",
    "fallback_used": False,
    "latency_ms": 12,
    "outcome_score": 0.7,
    "capability": "reasoning",
    "complexity_level": 3,
    "complexity_name": "complex",
    "complexity_source": "decision-layer",
    "requires_tools": False,
    "required_tools": [],
    "context_dependent": False,
    "output_type": "analysis",
    "task_profile": {"capability": "reasoning", "breadth": 6, "output_type": "analysis"},
    "selected_model": "nvidia/nemotron-3-ultra-550b-a55b",
    "model_provider": "nvidia",
    "model_reason": "best fit for this task",
    "matched_capabilities": ["reasoning"],
    "model_fallbacks": ["gemini-flash-latest"],
    "model_tier": 3,
}


class TestChatApi(unittest.TestCase):
    def test_executor_keeps_routing_memory_on_one_thread(self):
        import tempfile

        from core_runner import RouteExecutor
        from routing_memory import RoutingMemory

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        executor = RouteExecutor(lambda: RoutingMemory(path))
        old_layer = os.environ.get("DECISION_LAYER")
        os.environ["DECISION_LAYER"] = "baseline"
        original = providers.complete
        providers.complete = lambda provider, model, prompt, system=None: "ok"
        try:
            client = TestClient(create_app(executor=executor))
            response = client.post("/api/chat", json={"message": "What is photosynthesis?"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["response_success"])
            saved = RoutingMemory(path)
            try:
                rows = saved.get_observations()
            finally:
                saved.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].selected_agent, response.json()["selected_agent"])
        finally:
            providers.complete = original
            executor.close()
            if old_layer is None:
                os.environ.pop("DECISION_LAYER", None)
            else:
                os.environ["DECISION_LAYER"] = old_layer
            try:
                os.remove(path)
            except OSError:
                pass

    def test_chat_returns_the_core_result_and_calls_route(self):
        calls = []

        def spy(prompt, policy=None, conversation_state=None, memory=None, **kwargs):
            calls.append(
                {
                    "prompt": prompt,
                    "policy": policy,
                    "state": conversation_state,
                    "memory": memory,
                }
            )
            return dict(FIXTURE)

        original = router.route
        router.route = spy
        try:
            client = TestClient(create_app(memory="memory-token"))
            response = client.post("/api/chat", json={"message": "Design a backend"})
        finally:
            router.route = original

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["prompt"], "Design a backend")
        self.assertIsNone(calls[0]["policy"])
        self.assertEqual(calls[0]["memory"], "memory-token")
        self.assertIsNotNone(calls[0]["state"])
        self.assertEqual(body["selected_agent"], FIXTURE["selected_agent"])
        self.assertEqual(body["selected_model"], FIXTURE["selected_model"])
        self.assertEqual(body["model_provider"], FIXTURE["model_provider"])
        self.assertEqual(body["decision_layer"], "laya")
        self.assertEqual(body["task_profile"], FIXTURE["task_profile"])
        self.assertEqual(body["model_reason"], FIXTURE["model_reason"])
        self.assertNotIn("requirements", body)
        self.assertNotIn("blender_scene", body)
        self.assertTrue(body["conversation_id"])

    def test_chat_request_carries_the_blender_capability_to_the_agent_thread(self):
        from agents.three_d_agent import blender_capability

        seen = []

        def spy(prompt, policy=None, conversation_state=None, memory=None, **kwargs):
            seen.append(blender_capability.get())
            return dict(FIXTURE)

        original = router.route
        router.route = spy
        try:
            client = TestClient(create_app())
            off = client.post("/api/chat", json={"message": "Create a cube", "blender": False})
            on = client.post("/api/chat", json={"message": "Create a cube", "blender": True})
            omitted = client.post("/api/chat", json={"message": "Create a cube"})
        finally:
            router.route = original

        self.assertEqual(off.status_code, 200, off.text)
        self.assertEqual(on.status_code, 200, on.text)
        self.assertEqual(omitted.status_code, 200, omitted.text)
        self.assertEqual(seen, [False, True, True])
        self.assertNotIn("blender_scene", off.json())

    def test_chat_request_carries_the_playwright_capability_to_the_agent_thread(self):
        from tools.playwright_tool import playwright_capability

        seen = []

        def spy(prompt, policy=None, conversation_state=None, memory=None, **kwargs):
            seen.append(playwright_capability.get())
            return dict(FIXTURE)

        original = router.route
        router.route = spy
        try:
            client = TestClient(create_app())
            off = client.post("/api/chat", json={"message": "Open example.com", "playwright": False})
            on = client.post("/api/chat", json={"message": "Open example.com", "playwright": True})
            omitted = client.post("/api/chat", json={"message": "Open example.com"})
        finally:
            router.route = original

        self.assertEqual(off.status_code, 200, off.text)
        self.assertEqual(on.status_code, 200, on.text)
        self.assertEqual(omitted.status_code, 200, omitted.text)
        self.assertEqual(seen, [False, True, True])

    def test_real_route_agent_and_model_are_returned_unchanged(self):
        """The API body matches a direct router.route() call for the same prompt."""
        old_layer = os.environ.get("DECISION_LAYER")
        os.environ["DECISION_LAYER"] = "baseline"
        original = providers.complete

        def fake_complete(provider, model, prompt, system=None):
            return "stub answer"

        providers.complete = fake_complete
        prompt = "Write a Python function to reverse a string."
        try:
            direct = router.route(prompt, conversation_state=ConversationState())
            client = TestClient(create_app())
            response = client.post("/api/chat", json={"message": prompt})
        finally:
            providers.complete = original
            if old_layer is None:
                os.environ.pop("DECISION_LAYER", None)
            else:
                os.environ["DECISION_LAYER"] = old_layer

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["selected_agent"], direct["selected_agent"])
        self.assertEqual(body["selected_model"], direct["selected_model"])
        self.assertEqual(body["model_provider"], direct["model_provider"])
        self.assertEqual(body["decision_layer"], direct["decision_layer"])
        self.assertEqual(body["complexity_level"], direct["complexity_level"])
        self.assertEqual(body["response"], "stub answer")
        self.assertTrue(body["response_success"])

    def test_conversation_id_keeps_core_history(self):
        old_layer = os.environ.get("DECISION_LAYER")
        os.environ["DECISION_LAYER"] = "baseline"
        original = providers.complete
        providers.complete = lambda provider, model, prompt, system=None: "ok"
        try:
            client = TestClient(create_app())
            first = client.post("/api/chat", json={"message": "What is photosynthesis?"})
            self.assertEqual(first.status_code, 200)
            conversation_id = first.json()["conversation_id"]
            self.assertFalse(first.json()["task_profile"]["context_dependent"])

            second = client.post(
                "/api/chat",
                json={
                    "message": "Explain that more simply.",
                    "conversation_id": conversation_id,
                },
            )
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()["conversation_id"], conversation_id)
            self.assertTrue(second.json()["context_dependent"])
            self.assertTrue(second.json()["task_profile"]["context_dependent"])

            loaded = client.get(f"/api/conversations/{conversation_id}")
        finally:
            providers.complete = original
            if old_layer is None:
                os.environ.pop("DECISION_LAYER", None)
            else:
                os.environ["DECISION_LAYER"] = old_layer

        self.assertEqual(loaded.status_code, 200)
        messages = loaded.json()["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["prompt"], "What is photosynthesis?")
        self.assertEqual(messages[1]["routing"]["selected_agent"], second.json()["selected_agent"])
        self.assertEqual(messages[1]["routing"]["selected_model"], second.json()["selected_model"])

    def test_unknown_conversation_is_not_found(self):
        client = TestClient(create_app())
        response = client.get("/api/conversations/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["error"], "not_found")

    def test_blank_message_is_rejected(self):
        client = TestClient(create_app())
        response = client.post("/api/chat", json={"message": "   "})
        self.assertEqual(response.status_code, 422)

    def test_configuration_error_hides_secrets(self):
        secret = "test-secret-should-not-leak"
        os.environ["GEMINI_API_KEY"] = secret

        def explode(*args, **kwargs):
            raise ConfigurationError(
                "Missing required environment variable: GEMINI_API_KEY."
            )

        original = router.route
        router.route = explode
        try:
            client = TestClient(create_app())
            response = client.post("/api/chat", json={"message": "Hello"})
        finally:
            router.route = original
            os.environ.pop("GEMINI_API_KEY", None)

        self.assertEqual(response.status_code, 503)
        text = response.text
        self.assertNotIn(secret, text)
        self.assertIn("GEMINI_API_KEY", text)
        self.assertEqual(response.json()["detail"]["error"], "configuration")

    def test_provider_failure_is_the_core_result(self):
        from errors import AgentExecutionError

        old_layer = os.environ.get("DECISION_LAYER")
        os.environ["DECISION_LAYER"] = "baseline"
        original = providers.complete

        def fail(provider, model, prompt, system=None):
            raise AgentExecutionError(
                f"{provider} request failed for model {model!r}: AuthenticationError"
            )

        providers.complete = fail
        try:
            client = TestClient(create_app())
            response = client.post(
                "/api/chat",
                json={"message": "Write a Python function to reverse a string."},
            )
        finally:
            providers.complete = original
            if old_layer is None:
                os.environ.pop("DECISION_LAYER", None)
            else:
                os.environ["DECISION_LAYER"] = old_layer

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["response_success"])
        self.assertIn("AgentExecutionError", body["response"])
        self.assertEqual(body["selected_agent"], "CODING_AGENT")
        self.assertTrue(body["selected_model"])

    def test_cors_allows_the_dev_server_only(self):
        client = TestClient(create_app())
        allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "http://localhost:5173",
        )
        blocked = client.get("/api/health", headers={"Origin": "http://evil.example"})
        self.assertNotEqual(
            blocked.headers.get("access-control-allow-origin"),
            "http://evil.example",
        )


def _scene_reply(path: str, *, executed: str = "yes", success: str = "yes") -> str:
    return (
        "```python\nimport bpy\nbpy.ops.mesh.primitive_cube_add()\n```\n\n"
        "Blender tool result:\n"
        "- tool: BLENDER_TOOL\n"
        "- invoked: yes\n"
        f"- executed: {executed}\n"
        f"- success: {success}\n"
        "- objects: SimpleCube\n"
        f"- output: {path}\n"
    )


class TestBlenderSceneApi(unittest.TestCase):
    def setUp(self):
        self._scenes = tempfile.TemporaryDirectory()
        self._previous = blender_scenes.STORE
        blender_scenes.STORE = blender_scenes.SceneStore(Path(self._scenes.name))
        self._work = Path(tempfile.mkdtemp(prefix="agentroute_blender_"))
        self.blend = self._work / "scene.blend"
        self.blend.write_bytes(b"BLENDER-cube-scene")

    def tearDown(self):
        blender_scenes.STORE = self._previous
        self._scenes.cleanup()
        shutil.rmtree(self._work, ignore_errors=True)

    def _client(self, response: str, **fields):
        payload = dict(FIXTURE)
        payload.update(fields)
        payload["response"] = response

        def spy(prompt, policy=None, conversation_state=None, memory=None, **kwargs):
            result = dict(payload)
            if conversation_state is not None:
                conversation_state.record(prompt, result["selected_agent"], result["response"])
            return result

        return spy

    def test_a_successful_scene_is_exposed_by_id_and_can_be_downloaded(self):
        original = router.route
        router.route = self._client(_scene_reply(str(self.blend)))
        try:
            client = TestClient(create_app())
            response = client.post("/api/chat", json={"message": "Create a simple Blender scene with a cube."})
        finally:
            router.route = original

        self.assertEqual(response.status_code, 200)
        body = response.json()
        scene = body["blender_scene"]
        self.assertEqual(set(scene), {"scene_id"})
        self.assertNotIn(str(self.blend), str(scene))
        scene_id = scene["scene_id"]
        stored = blender_scenes.STORE.path_for(scene_id)
        self.assertIsNotNone(stored)
        self.assertNotEqual(stored.resolve(), self.blend.resolve())
        self.assertTrue(str(stored).endswith(os.path.join(scene_id, "scene.blend")))

        downloaded = client.get(f"/api/blender/scene/{scene_id}")
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, b"BLENDER-cube-scene")
        self.assertIn("scene.blend", downloaded.headers.get("content-disposition", ""))

        loaded = client.get(f"/api/conversations/{body['conversation_id']}")
        self.assertEqual(loaded.json()["messages"][0]["routing"]["blender_scene"]["scene_id"], scene_id)

    def test_a_zstd_compressed_blender_5_scene_is_exposed(self):
        import compression.zstd

        self.blend.write_bytes(compression.zstd.compress(b"BLENDER17-01v050rest"))
        original = router.route
        router.route = self._client(_scene_reply(str(self.blend)))
        try:
            client = TestClient(create_app())
            response = client.post("/api/chat", json={"message": "Create a simple Blender scene with a cube."})
        finally:
            router.route = original
        self.assertEqual(response.status_code, 200)
        self.assertIn("scene_id", response.json()["blender_scene"])

    def test_button_data_is_withheld_unless_blender_wrote_a_scene(self):
        cases = [
            ("core response", {}),
            (_scene_reply(str(self.blend), executed="no", success="no"), {}),
            (_scene_reply(str(self.blend), success="no"), {}),
            (_scene_reply(str(self.blend)), {"fallback_used": True}),
            (_scene_reply(str(self.blend)), {"response_success": False}),
            (_scene_reply(str(self._work / "missing.blend")), {}),
            (_scene_reply(str(Path(tempfile.gettempdir()) / "scene.blend")), {}),
        ]
        outside = Path(tempfile.mkdtemp(prefix="not_agentroute_"))
        self.addCleanup(lambda: shutil.rmtree(outside, ignore_errors=True))
        (outside / "scene.blend").write_bytes(b"BLENDER-nope")
        cases.append((_scene_reply(str(outside / "scene.blend")), {}))
        self.blend.write_bytes(b"not-a-blend-file")
        cases.append((_scene_reply(str(self.blend)), {}))

        for response_text, fields in cases:
            with self.subTest(response=response_text[:40], fields=fields):
                original = router.route
                router.route = self._client(response_text, **fields)
                try:
                    client = TestClient(create_app())
                    response = client.post("/api/chat", json={"message": "Create an email validator in Python."})
                finally:
                    router.route = original
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("blender_scene", response.json())

        self.assertEqual(list(Path(self._scenes.name).iterdir()), [])

    def test_scene_ids_cannot_read_other_files(self):
        client = TestClient(create_app())
        for scene_id in ("../scene.blend", "..", "a" * 32, "not-an-id", "%2e%2e%2fscene.blend"):
            with self.subTest(scene_id=scene_id):
                response = client.get(f"/api/blender/scene/{scene_id}")
                self.assertIn(response.status_code, (404, 400))
                opened = client.post(f"/api/blender/scene/{scene_id}/open")
                self.assertIn(opened.status_code, (404, 400))

    def test_open_launches_the_stored_scene_in_blender(self):
        original = router.route
        router.route = self._client(_scene_reply(str(self.blend)))
        try:
            client = TestClient(create_app())
            created = client.post("/api/chat", json={"message": "Create a simple Blender scene with a cube."})
        finally:
            router.route = original
        scene_id = created.json()["blender_scene"]["scene_id"]
        stored = str(blender_scenes.STORE.path_for(scene_id))
        binary_path = self._work / "blender.exe"
        binary_path.write_bytes(b"blender")
        binary = str(binary_path)

        with patch("tools.blender_tool.BlenderTool.find_binary", return_value=binary), patch(
            "blender_scenes.subprocess.Popen"
        ) as popen:
            opened = client.post(f"/api/blender/scene/{scene_id}/open")
            downloaded = client.get(f"/api/blender/scene/{scene_id}")

        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.json(), {"opened": True})
        self.assertNotIn(str(self.blend.parent), opened.text)
        command = popen.call_args.args[0]
        self.assertEqual(command[0], binary)
        self.assertEqual(command[1], stored)
        self.assertNotIn("--background", command)
        self.assertNotIn(str(self.blend), command)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(downloaded.status_code, 200)

    def test_open_reports_when_blender_cannot_start(self):
        original = router.route
        router.route = self._client(_scene_reply(str(self.blend)))
        try:
            client = TestClient(create_app())
            created = client.post("/api/chat", json={"message": "Create a simple Blender scene with a cube."})
        finally:
            router.route = original
        scene_id = created.json()["blender_scene"]["scene_id"]

        with patch("tools.blender_tool.BlenderTool.find_binary", return_value=None), patch(
            "blender_scenes.subprocess.Popen"
        ) as popen:
            opened = client.post(f"/api/blender/scene/{scene_id}/open")

        self.assertEqual(opened.status_code, 503)
        self.assertEqual(opened.json()["detail"]["error"], "blender_unavailable")
        self.assertNotIn(str(self.blend), opened.text)
        popen.assert_not_called()

    def test_a_later_scene_is_a_different_file(self):
        second = self._work / "scene.blend"
        calls = {"n": 0}

        def spy(prompt, policy=None, conversation_state=None, memory=None, **kwargs):
            calls["n"] += 1
            payload = dict(FIXTURE)
            if calls["n"] == 1:
                payload["response"] = _scene_reply(str(self.blend))
            else:
                payload["response"] = _scene_reply(str(second)).replace(
                    "- objects: SimpleCube",
                    "- objects: SimpleCube, SimpleCylinder",
                )
            if conversation_state is not None:
                conversation_state.record(prompt, payload["selected_agent"], payload["response"])
            return payload

        original = router.route
        router.route = spy
        try:
            client = TestClient(create_app())
            first = client.post("/api/chat", json={"message": "Create a simple Blender scene with a cube."})
            second_turn = client.post(
                "/api/chat",
                json={
                    "message": "Add a cylinder next to the cube.",
                    "conversation_id": first.json()["conversation_id"],
                },
            )
        finally:
            router.route = original

        first_id = first.json()["blender_scene"]["scene_id"]
        second_id = second_turn.json()["blender_scene"]["scene_id"]
        self.assertNotEqual(first_id, second_id)
        self.assertNotEqual(
            blender_scenes.STORE.path_for(first_id),
            blender_scenes.STORE.path_for(second_id),
        )


if __name__ == "__main__":
    unittest.main()
