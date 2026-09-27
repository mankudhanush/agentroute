"""FastAPI application factory. No routing policy lives in this module."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.chat import build_chat_router, build_health_router
from sessions import SessionStore


def _origins() -> list[str]:
    raw = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_app(*, store: SessionStore | None = None, memory=None, executor=None) -> FastAPI:
    app = FastAPI(title="AgentRoute API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(build_health_router())
    app.include_router(build_chat_router(store or SessionStore(), memory, executor))
    return app
