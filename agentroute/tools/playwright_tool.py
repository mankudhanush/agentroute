"""PLAYWRIGHT_TOOL — real browser actions for WEB_AGENT.

Playwright is a tool. It is not an agent and it is not a model. A visible
Chromium window starts when a page is opened and stays open so a later click,
fill, read, screenshot, or navigation uses that same page.
"""

import os
import queue
import tempfile
import threading
from contextvars import ContextVar
from urllib.parse import urlparse

from .base_tool import BaseTool, ToolResult

# Per chat request. Unset means the existing tool path, so callers that do not
# send the plugin toggle keep the tool available.
playwright_capability: ContextVar[bool] = ContextVar("playwright_capability", default=True)

_OPS = ("goto", "open", "navigate", "click", "fill", "title", "text", "read", "screenshot")
_NAV = ("goto", "open", "navigate")
_MAX_ACTIONS = 8
_TEXT_LIMIT = 2000
_SELECTOR_ENGINES = ("role=", "text=", "css=", "xpath=", "id=", "internal:")


class PlaywrightTool(BaseTool):
    name = "PLAYWRIGHT_TOOL"
    description = "Open a page, click, type, read it, and capture a screenshot."

    def is_available(self) -> bool:
        import importlib.util

        return importlib.util.find_spec("playwright") is not None

    def run(self, actions) -> ToolResult:
        """Run one browser plan. A disabled plugin never starts a browser."""
        if not playwright_capability.get():
            return ToolResult(
                tool=self.name,
                success=False,
                error=(
                    "Playwright is disabled. Enable the Playwright plugin to "
                    "execute this browser task."
                ),
                metadata={"invoked": False, "executed": False},
            )
        try:
            plan = _prepare(actions)
        except ValueError as exc:
            return ToolResult(
                tool=self.name,
                success=False,
                error=str(exc),
                metadata={"invoked": True, "executed": False},
            )
        if not self.is_available():
            return ToolResult(
                tool=self.name,
                success=False,
                error="Playwright is not installed. No browser was launched.",
                metadata={"invoked": True, "executed": False},
            )
        return _browse(plan)


def _headless() -> bool:
    """Visible Chromium is the normal path. Tests may opt into headless."""
    return os.environ.get("AGENTROUTE_PLAYWRIGHT_HEADLESS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def browser_is_open() -> bool:
    """Whether a page from an earlier browser action is still open."""
    return _SESSION.alive()


def close_browser() -> None:
    """Close the shared Chromium page. Tests use this between cases."""
    _SESSION.close()


def _prepare(actions) -> list:
    if not isinstance(actions, list) or not actions:
        raise ValueError("The browser plan has no actions. No browser was launched.")
    plan = []
    for item in actions[:_MAX_ACTIONS]:
        if not isinstance(item, dict):
            raise ValueError("A browser action was not an object. No browser was launched.")
        op = item.get("op")
        if op not in _OPS:
            raise ValueError(f"Unsupported browser action {op!r}. No browser was launched.")
        if op in _NAV:
            url = _http_url(item.get("url"))
            if not url:
                raise ValueError("A goto action needs an http(s) URL. No browser was launched.")
            plan.append({"op": "goto", "url": url})
        elif op == "click":
            plan.append({"op": "click", **_target(item, "A click action needs a selector.")})
        elif op == "fill":
            plan.append({
                "op": "fill",
                **_target(item, "A fill action needs a selector."),
                "value": str(item.get("value", item.get("text")) or "")[:_TEXT_LIMIT],
            })
        else:
            plan.append({"op": op})
    if not any(step["op"] == "goto" for step in plan) and not _SESSION.alive():
        raise ValueError("The browser plan has no page to open. No browser was launched.")
    return plan


def _target(item: dict, missing: str) -> dict:
    """A CSS selector, text selector, or accessible role for one element."""
    selector = str(item.get("selector") or "").strip()
    role = str(item.get("role") or "").strip()
    name = str(item.get("name") or "").strip()
    text = str(item.get("text") or "").strip() if item.get("op") == "click" else ""
    if item.get("op") == "fill":
        text = ""
    if not selector and not role and not text:
        raise ValueError(f"{missing} No browser was launched.")
    return {"selector": selector, "role": role, "name": name, "text": text}


def _http_url(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return text


def _browse(plan: list) -> ToolResult:
    opens = any(step["op"] == "goto" for step in plan)
    if not _SESSION.alive():
        if not opens:
            return ToolResult(
                tool="PLAYWRIGHT_TOOL",
                success=False,
                error="The browser plan has no page to open. No browser was launched.",
                metadata={"invoked": True, "executed": False},
            )
        try:
            _SESSION.ensure()
        except Exception as exc:  # noqa: BLE001 - report the launch failure, do not invent a page
            return _failed(exc, executed=False)
    try:
        observed = _SESSION.call(lambda page: _run(page, plan))
    except Exception as exc:  # noqa: BLE001 - the browser error is the result
        return _failed(exc, executed=True)

    lines = []
    if observed["title"]:
        lines.append(f"Page title: {observed['title']}")
    if observed["url"]:
        lines.append(f"URL: {observed['url']}")
    if observed["text"]:
        lines.extend(["Page text:", observed["text"].strip()])
    if observed["screenshot"]:
        lines.append(f"Screenshot: {observed['screenshot']}")
    return ToolResult(
        tool="PLAYWRIGHT_TOOL",
        success=True,
        output="\n".join(lines),
        artifacts=[observed["screenshot"]] if observed["screenshot"] else [],
        metadata={
            "invoked": True,
            "executed": True,
            "title": observed["title"],
            "url": observed["url"],
            "screenshot": observed["screenshot"],
        },
    )


def _failed(exc: Exception, *, executed: bool) -> ToolResult:
    message = str(exc).strip() or exc.__class__.__name__
    return ToolResult(
        tool="PLAYWRIGHT_TOOL",
        success=False,
        error=f"{message}\nNo page result was invented.",
        metadata={"invoked": True, "executed": executed},
    )


def _run(page, plan: list) -> dict:
    observed = {"title": "", "url": "", "text": "", "screenshot": None}
    for step in plan:
        op = step["op"]
        if op == "goto":
            page.goto(step["url"], wait_until="domcontentloaded", timeout=30000)
            _reveal(page)
            _capture(page, observed)
        elif op == "click":
            _locator(page, step).click()
            page.wait_for_load_state("domcontentloaded")
            _reveal(page)
            _capture(page, observed)
        elif op == "fill":
            _locator(page, step).fill(step["value"])
            _capture(page, observed)
        elif op == "title":
            _capture(page, observed)
        elif op in ("text", "read"):
            _capture(page, observed)
            observed["text"] = _dom_report(page)
        elif op == "screenshot":
            handle = tempfile.NamedTemporaryFile(
                delete=False, suffix=".png", prefix="agentroute_browser_"
            )
            handle.close()
            page.screenshot(path=handle.name)
            observed["screenshot"] = handle.name
            _capture(page, observed)
    if observed["url"] and not observed["title"]:
        observed["title"] = page.title()
    if observed["url"] and not observed["text"]:
        observed["text"] = page.inner_text("body")[:_TEXT_LIMIT]
    return observed


def _reveal(page) -> None:
    if _headless():
        return
    try:
        page.bring_to_front()
    except Exception:
        return


def _dom_report(page) -> str:
    """Facts read from the live DOM. Missing elements stay missing."""

    def lines(selector: str, limit: int) -> list[str]:
        found = []
        for raw in page.locator(selector).all_inner_texts():
            text = " ".join(raw.split())
            if text and text not in found:
                found.append(text)
            if len(found) >= limit:
                break
        return found

    heading = lines("h1", 3)
    navigation = lines("nav a, header a, [role='navigation'] a", 30)
    sections = lines("h2, h3", 30)
    visible = " ".join(page.inner_text("body").split())[:_TEXT_LIMIT]
    return "\n".join(
        [
            "Main heading: " + (heading[0] if heading else "(none in the DOM)"),
            "Navigation: " + (" | ".join(navigation) if navigation else "(none in the DOM)"),
            "Headings: " + (" | ".join(sections) if sections else "(none in the DOM)"),
            "Visible text:",
            visible,
        ]
    )


def _capture(page, observed: dict, *, body: bool = False) -> None:
    observed["url"] = page.url
    observed["title"] = page.title()
    if body:
        observed["text"] = page.inner_text("body")[:_TEXT_LIMIT]


def _locator(page, step: dict):
    role = step.get("role") or ""
    if role:
        name = step.get("name") or None
        locator = page.get_by_role(role, name=name) if name else page.get_by_role(role)
        return locator.first
    selector = step.get("selector") or ""
    if selector:
        if selector.lower().startswith(_SELECTOR_ENGINES) or _looks_like_css(selector):
            return page.locator(selector).first
        return page.get_by_text(selector).first
    return page.get_by_text(step.get("text") or "").first


def _looks_like_css(selector: str) -> bool:
    if selector[:1] in ".#[*>":
        return True
    return any(token in selector for token in (" ", ">", "+", "~", ":", "[", "=", "#", "."))


class _BrowserSession:
    """One Chromium page, used only from the thread that launched it."""

    def __init__(self):
        self._gate = threading.Lock()
        self._inbox: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._start_error: Exception | None = None
        self._has_page = False

    def alive(self) -> bool:
        return bool(self._has_page and self._thread and self._thread.is_alive())

    def ensure(self) -> None:
        with self._gate:
            if self.alive():
                return
            self._inbox = queue.Queue()
            self._started.clear()
            self._start_error = None
            self._has_page = False
            self._thread = threading.Thread(
                target=self._loop, name="agentroute-playwright", daemon=True
            )
            self._thread.start()
        if not self._started.wait(45):
            raise TimeoutError("Timed out starting Playwright Chromium.")
        if self._start_error is not None:
            error = self._start_error
            self._start_error = None
            raise error

    def call(self, fn):
        self.ensure()
        box: queue.Queue = queue.Queue(maxsize=1)
        with self._gate:
            self._inbox.put((fn, box))
            try:
                ok, value = box.get(timeout=90)
            except queue.Empty as exc:
                raise TimeoutError("The browser did not finish the action.") from exc
        if not ok:
            raise value
        return value

    def close(self) -> None:
        with self._gate:
            thread = self._thread
            if thread is None or not thread.is_alive():
                self._has_page = False
                self._thread = None
                return
            self._inbox.put(None)
        thread.join(timeout=15)
        with self._gate:
            self._has_page = False
            self._thread = None

    def _loop(self) -> None:
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=_headless())
                page = browser.new_page()
                page.set_default_timeout(15000)
                page.set_default_navigation_timeout(30000)
                self._has_page = True
                self._started.set()
                while True:
                    job = self._inbox.get()
                    if job is None:
                        break
                    fn, box = job
                    try:
                        box.put((True, fn(page)))
                    except Exception as exc:  # noqa: BLE001 - handed back to the caller
                        box.put((False, exc))
                browser.close()
        except Exception as exc:  # noqa: BLE001 - launch failure is reported by ensure()
            self._start_error = exc
        finally:
            self._has_page = False
            self._started.set()


_SESSION = _BrowserSession()
