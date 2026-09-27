"""HTTP entry points. AgentRoute core makes every routing decision."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger("agentroute.api")

import blender_scenes
import router as core_router
from agents.three_d_agent import blender_capability
from tools.playwright_tool import browser_is_open, playwright_capability, playwright_session_key
from blender_scenes import BlenderLaunchError, SceneNotFound, attach_blender_scene
from errors import (
    AgentRouteError,
    ClassifierError,
    ConfigurationError,
    RoutingDecisionError,
)
from routes.routing import project_result, project_turn
from schemas import ChatRequest


def _note_browser(body: dict) -> dict:
    """Tell the client when the visible Chromium window is still open."""
    if browser_is_open():
        body["browser_active"] = True
    return body


def _error(status: int, code: str, exc: Exception) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": code, "message": str(exc)})


def build_chat_router(store, memory, executor=None) -> APIRouter:
    api = APIRouter()

    @api.post("/api/chat")
    async def chat(body: ChatRequest):
        session = store.get_or_create(body.conversation_id)

        def run(bound_memory):
            with session.lock:
                token = blender_capability.set(body.blender)
                browser_token = playwright_capability.set(body.playwright)
                session_token = playwright_session_key.set(session.state.conversation_id)
                try:
                    result = core_router.route(
                        body.message,
                        conversation_state=session.state,
                        memory=bound_memory,
                    )
                    session.results.append(result)
                    projected = project_result(result, session.state.conversation_id)
                    return _note_browser(attach_blender_scene(projected, result))
                finally:
                    playwright_session_key.reset(session_token)
                    playwright_capability.reset(browser_token)
                    blender_capability.reset(token)

        try:
            if executor is not None:
                return await asyncio.wrap_future(executor.submit(run))
            return await asyncio.to_thread(run, memory)
        except ConfigurationError as exc:
            raise _error(503, "configuration", exc) from exc
        except ClassifierError as exc:
            raise _error(400, "invalid_request", exc) from exc
        except RoutingDecisionError as exc:
            raise _error(502, "routing", exc) from exc
        except AgentRouteError as exc:
            raise _error(502, "agentroute", exc) from exc
        except Exception as exc:
            logger.exception("chat request failed")
            raise HTTPException(
                status_code=500,
                detail={"error": "internal", "message": "AgentRoute could not complete the request."},
            ) from exc

    @api.get("/api/conversations/{conversation_id}")
    def conversation(conversation_id: str):
        session = store.get(conversation_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Unknown conversation."},
            )
        session_token = playwright_session_key.set(conversation_id)
        try:
            with session.lock:
                messages = []
                for index, turn in enumerate(session.state.turns):
                    result = session.results[index] if index < len(session.results) else None
                    item = project_turn(turn, result)
                    if result is not None and item.get("routing") is not None:
                        attach_blender_scene(item["routing"], result)
                        _note_browser(item["routing"])
                    messages.append(item)
        finally:
            playwright_session_key.reset(session_token)
        return {"conversation_id": conversation_id, "messages": messages}

    @api.get("/api/blender/scene/{scene_id}")
    def blender_scene(scene_id: str):
        """Download a scene this API stored. This does not launch Blender."""
        path = blender_scenes.STORE.path_for(scene_id)
        if path is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Scene not found."},
            )
        return FileResponse(path, media_type="application/octet-stream", filename="scene.blend")

    @api.post("/api/blender/scene/{scene_id}/open")
    def open_blender_scene(scene_id: str):
        """Open a stored scene in Blender on the computer running this API."""
        try:
            blender_scenes.STORE.launch(scene_id)
        except SceneNotFound:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Scene not found."},
            ) from None
        except BlenderLaunchError as exc:
            raise HTTPException(
                status_code=503,
                detail={"error": "blender_unavailable", "message": str(exc)},
            ) from exc
        return {"opened": True}

    return api


def build_health_router() -> APIRouter:
    api = APIRouter()

    @api.get("/api/health")
    def health():
        return {"status": "ok"}

    return api
