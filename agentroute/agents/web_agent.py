"""WEB_AGENT — browser tasks.

The router selects WEB_AGENT. The model comes from the existing model selector.
PLAYWRIGHT_TOOL is the capability this agent owns. The plugin flag decides
whether that tool may start a browser.
"""

import json
import re

from agents.base_agent import BaseAgent
from errors import AgentExecutionError
from models import get_fallbacks, get_model, get_provider
from tools.playwright_tool import browser_is_open, playwright_capability

ROLE = "general"

SYSTEM = (
    "You are the Web Agent.\n"
    "You plan browser actions for PLAYWRIGHT_TOOL. You do not browse by yourself, "
    "and you do not invent page titles, page text, or screenshots.\n"
    "When the user wants something done in a browser, return one JSON object and "
    "nothing else, shaped as "
    '{"actions":[{"op":"open","url":"https://host/path"},{"op":"click","selector":"text=English"},{"op":"read"}]} .\n'
    "Allowed op values are open, goto, click, fill, read, title, text, and screenshot.\n"
    "open and goto require an http or https URL. click and fill accept a CSS selector, "
    "a text selector such as text=English, or an accessible role. fill also requires text.\n"
    "The first browser plan must open a page. A follow-up may click, fill, read, or "
    "capture a screenshot on the page that is already open.\n"
    "Do not wrap the JSON in markdown. Do not describe the page.\n"
    "If the request is not a browser action, answer normally and do not return an "
    "actions object."
)

_FENCE = re.compile(r"```(?:json)?[ \t]*\n(.*?)```", re.DOTALL)
_OPS = {"goto", "open", "click", "fill", "title", "text", "read", "screenshot"}
_NAV = {"goto", "open"}


class WebAgent(BaseAgent):
    name = "WEB_AGENT"
    description = "Browser tasks"
    capabilities = (
        "browser_navigation",
        "page_interaction",
        "page_reading",
        "screenshot",
    )
    available_tools = ("PLAYWRIGHT_TOOL",)
    system_prompt = SYSTEM

    def __init__(self):
        self.model_provider = get_provider(ROLE)
        self.model_id = get_model(ROLE)
        self.fallback_model_ids = tuple(get_fallbacks(ROLE))

    def run(self, prompt: str) -> str:
        if not playwright_capability.get():
            return capability_blocked()
        try:
            text = self._complete(prompt, system=self.system_prompt)
        except AgentExecutionError as exc:
            return (
                "The model could not plan the browser task. "
                f"No browser was launched.\n{exc}"
            )
        actions = extract_actions(text)
        if actions is not None and not any(item.get("op") in _NAV for item in actions):
            if browser_is_open():
                pass
            else:
                url = _last_http_url(prompt)
                if url:
                    actions = [{"op": "goto", "url": url}, *actions]
                else:
                    actions = None
        if not actions and requests_live_browser(prompt):
            url = _last_http_url(prompt)
            if url:
                actions = [{"op": "goto", "url": url}, {"op": "read"}]
        if not actions:
            return text.strip()
        result = self.get_tool("PLAYWRIGHT_TOOL").run(actions)
        return compose_tool_response(result)


def capability_blocked() -> str:
    """Honest report used when the Playwright plugin is off. No browser starts."""
    return "\n".join(
        [
            "Playwright is disabled. Enable the Playwright plugin to execute this browser task.",
            "Playwright tool result:",
            "- tool: PLAYWRIGHT_TOOL",
            "- invoked: no",
            "- executed: no",
            "- success: no",
            "- note: No browser was launched.",
        ]
    )


def extract_actions(text: str) -> list | None:
    """The browser plan inside a model reply, when one is present."""
    raw = text or ""
    blocks = _FENCE.findall(raw)
    blob = blocks[0].strip() if blocks else None
    if blob is None:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            blob = raw[start:end + 1]
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    actions = data.get("actions") if isinstance(data, dict) else None
    if not isinstance(actions, list) or not actions:
        return None
    cleaned = []
    for item in actions[:8]:
        if not isinstance(item, dict) or item.get("op") not in _OPS:
            return None
        cleaned.append(item)
    return cleaned


def _last_http_url(prompt: str) -> str | None:
    """The page already named in this request, when the plan does not repeat it."""
    found = re.findall(r"https?://\S+", prompt or "")
    if not found:
        return None
    return found[-1].rstrip(".,);>]\"'")


_LIVE_BROWSER = re.compile(
    r"\b(?:playwright|scrape|scraping|screenshot|browse|browser|open|click)\b"
    r"|from the actual|live page|\bdom\b",
    re.IGNORECASE,
)


def requests_live_browser(prompt: str) -> bool:
    """The request names a page and asks for that live page, not for source code."""
    return bool(_last_http_url(prompt) and _LIVE_BROWSER.search(prompt or ""))


def compose_tool_response(result) -> str:
    """The tool's page result. Nothing here is filled in from the model."""
    invoked = bool(result.metadata.get("invoked"))
    executed = bool(result.metadata.get("executed"))
    lines = []
    if result.output:
        lines.extend([result.output.rstrip(), ""])
    lines.extend(
        [
            "Playwright tool result:",
            "- tool: PLAYWRIGHT_TOOL",
            f"- invoked: {'yes' if invoked else 'no'}",
            f"- executed: {'yes' if executed else 'no'}",
            f"- success: {'yes' if result.success else 'no'}",
        ]
    )
    if result.error and not result.success:
        lines.append(f"- error: {result.error}")
    if not executed:
        lines.append("- note: No browser was launched.")
    return "\n".join(lines)
