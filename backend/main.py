"""Run the API. Loads agentroute/.env, then calls router.route() per request.

    uvicorn main:app --app-dir backend
from the repository root, or:

    uvicorn main:app
from the backend directory.
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

CORE_DIR = Path(__file__).resolve().parents[1] / "agentroute"
sys.path.insert(0, str(CORE_DIR))

from dotenv import load_dotenv

load_dotenv(CORE_DIR / ".env")

from app import create_app
from core_runner import RouteExecutor


def _memory():
    from routing_memory import RoutingMemory

    return RoutingMemory()


app = create_app(executor=RouteExecutor(_memory))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
