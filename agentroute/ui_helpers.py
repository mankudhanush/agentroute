"""Pure helpers for the Streamlit UI.

Kept out of ui.py so they are importable and testable without Streamlit
installed. No Streamlit, no model calls, no routing rules in here.
"""

import re

CODE_BLOCK_RE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL)


def extract_code_blocks(text: str) -> list:
    """Return the contents of fenced code blocks in `text`."""
    return [block.strip() for block in CODE_BLOCK_RE.findall(text or "")]


def strip_code_blocks(text: str) -> str:
    """Return `text` with fenced code blocks removed."""
    return CODE_BLOCK_RE.sub("", text or "").strip()


def build_flow(
    selected_agent: str,
    provider_label: str,
    live: bool,
    decision_layer: str = "ROUTER",
) -> list:
    """The runtime flow to display, derived from the actual routing result."""
    steps = ["USER", decision_layer.upper(), selected_agent]
    if not live:
        steps.append("(model execution disabled)")
        return steps
    steps.append(provider_label.upper())
    steps.append("3D RESPONSE" if selected_agent == "THREE_D_AGENT" else "RESULT")
    return steps


def decision_layer_label(result: dict) -> str:
    """Human-readable decision layer, honest about fallbacks.

    A fallback decision is never presented as a Laya decision.
    """
    layer = (result or {}).get("decision_layer", "")
    if layer == "laya":
        return "Laya (Decision AI)"
    if result.get("fallback_used") and layer == "fallback":
        return "Laya unavailable - fallback routing"
    return f"{layer or 'baseline'} (deterministic)"


def truncate(text: str, limit: int = 70) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "..."
