"""Read-only OpenRouter model discovery.

Free-model availability changes over time, so AgentRoute should not depend on a
hard-coded catalog forever. This utility queries OpenRouter's public models
endpoint and reports which free models are currently listed.

Step 4 scope: READ-ONLY. It never rewrites models.py or the .env — it only
reports. Uses urllib from the standard library (no new dependency).

Usage:
    python model_discovery.py
    python model_discovery.py --all
"""

import json
import urllib.error
import urllib.request

from config import optional_env

MODELS_URL = "https://openrouter.ai/api/v1/models"
REQUEST_TIMEOUT = 20


def _is_free(model: dict) -> bool:
    """A model is 'free' if its id is :free-suffixed or its pricing is all zero."""
    if str(model.get("id", "")).endswith(":free"):
        return True
    pricing = model.get("pricing") or {}
    values = [pricing.get("prompt"), pricing.get("completion")]
    try:
        return all(v is not None and float(v) == 0.0 for v in values)
    except (TypeError, ValueError):
        return False


def fetch_models(api_key: str | None = None, timeout: int = REQUEST_TIMEOUT) -> list:
    """Fetch the raw model list from OpenRouter. Raises on network/parse failure."""
    api_key = api_key or optional_env("OPENROUTER_API_KEY")
    request = urllib.request.Request(MODELS_URL, headers={"Accept": "application/json"})
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("data", [])


def discover_free_models(api_key: str | None = None) -> dict:
    """Return {'ok': bool, 'free': [...], 'total': int, 'error': str|None}.

    Never raises — callers (and the CLI) get a structured result either way.
    """
    try:
        models = fetch_models(api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"ok": False, "free": [], "total": 0, "error": f"{type(exc).__name__}"}
    except (ValueError, KeyError) as exc:
        return {"ok": False, "free": [], "total": 0, "error": f"parse error: {type(exc).__name__}"}

    free = [
        {
            "id": m.get("id"),
            "name": m.get("name"),
            "context_length": m.get("context_length"),
            "modalities": ((m.get("architecture") or {}).get("input_modalities")),
        }
        for m in models
        if _is_free(m)
    ]
    free.sort(key=lambda m: m["id"] or "")
    return {"ok": True, "free": free, "total": len(models), "error": None}


def verify_configured_models(api_key: str | None = None) -> dict:
    """Check the models AgentRoute is configured to use against what is listed."""
    from models import catalog

    discovery = discover_free_models(api_key)
    if not discovery["ok"]:
        return {"ok": False, "error": discovery["error"], "checked": {}}

    available = {m["id"] for m in discovery["free"]}
    # Only OpenRouter-backed roles can be checked against OpenRouter's catalog.
    checked = {
        role: {"model": info["resolved"], "listed_as_free": info["resolved"] in available}
        for role, info in catalog().items()
        if info["provider"] == "openrouter" and info["resolved"]
    }
    return {"ok": True, "error": None, "checked": checked}


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="OpenRouter free-model discovery (read-only)")
    parser.add_argument("--all", action="store_true", help="list every free model found")
    parser.add_argument("--verify", action="store_true", help="check configured models")
    args = parser.parse_args(argv)

    if args.verify:
        result = verify_configured_models()
        if not result["ok"]:
            print(f"Discovery failed: {result['error']}")
            return 1
        if not result["checked"]:
            print("No OpenRouter-backed roles are configured (active provider "
                  "is not OpenRouter). Set AGENTROUTE_PROVIDER=openrouter to check.")
            return 0
        for role, info in result["checked"].items():
            mark = "OK " if info["listed_as_free"] else "MISSING"
            print(f"[{mark}] {role:24s} {info['model']}")
        return 0

    result = discover_free_models()
    if not result["ok"]:
        print(f"Discovery failed: {result['error']}")
        return 1
    print(f"Found {len(result['free'])} free models (of {result['total']} listed).")
    shown = result["free"] if args.all else result["free"][:25]
    for model in shown:
        print(f"  {model['id']}")
    if not args.all and len(result["free"]) > len(shown):
        print(f"  ... {len(result['free']) - len(shown)} more (use --all)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
