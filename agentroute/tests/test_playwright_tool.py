"""PLAYWRIGHT_TOOL drives a real Chromium page and keeps it for follow-ups."""

import os
import sys

# The product opens a visible Chromium window. These tests stay headless.
os.environ["AGENTROUTE_PLAYWRIGHT_HEADLESS"] = "1"
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.base_tool import ToolResult  # noqa: E402
from tools.playwright_tool import (  # noqa: E402
    PlaywrightTool,
    close_all_browsers,
    playwright_capability,
    playwright_session_key,
)


class _Pages(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/second":
            html = (
                "<!doctype html><html><head><title>Second Page</title></head>"
                "<body><p>Arrived</p></body></html>"
            )
        elif parsed.path == "/filled":
            value = parse_qs(parsed.query).get("q", [""])[0]
            html = (
                "<!doctype html><html><head><title>Filled "
                f"{value}</title></head><body><p>value:{value}</p></body></html>"
            )
        else:
            html = (
                "<!doctype html><html><head><title>Start Page</title></head><body>"
                '<a id="next" href="/second">Continue</a>'
                '<form action="/filled" method="get">'
                '<input id="q" name="q" />'
                '<button id="go" type="submit">Go</button>'
                "</form></body></html>"
            )
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return


class TestPlaywrightBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Pages)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address
        cls.base = f"http://{host}:{port}/"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        close_all_browsers()

    def setUp(self):
        close_all_browsers()
        self.tool = PlaywrightTool()
        self.token = playwright_capability.set(True)

    def tearDown(self):
        playwright_capability.reset(self.token)
        close_all_browsers()

    def test_open_url(self):
        result = self.tool.run([{"op": "open", "url": self.base}])
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.metadata["title"], "Start Page")
        self.assertTrue(result.metadata["url"].startswith(self.base))
        self.assertIn("Page title: Start Page", result.output)
        self.assertIn(result.metadata["url"], result.output)

    def test_open_url_then_click_element(self):
        result = self.tool.run([
            {"op": "open", "url": self.base},
            {"op": "click", "role": "link", "name": "Continue"},
        ])
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.metadata["title"], "Second Page")
        self.assertIn("/second", result.metadata["url"])
        self.assertNotIn("No browser was launched", result.error or "")

    def test_open_url_then_click_then_read(self):
        result = self.tool.run([
            {"op": "open", "url": self.base},
            {"op": "click", "selector": "text=Continue"},
            {"op": "read"},
        ])
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.metadata["title"], "Second Page")
        self.assertIn("/second", result.metadata["url"])
        self.assertIn("Arrived", result.output)
        self.assertIn("Page title: Second Page", result.output)

    def test_open_url_then_fill_input(self):
        result = self.tool.run([
            {"op": "open", "url": self.base},
            {"op": "fill", "selector": "#q", "text": "route-token"},
            {"op": "click", "selector": "#go"},
            {"op": "read"},
        ])
        self.assertTrue(result.success, result.error)
        self.assertIn("route-token", result.metadata["url"])
        self.assertIn("value:route-token", result.output)
        self.assertIn("route-token", result.metadata["title"])

    def test_screenshot(self):
        result = self.tool.run([
            {"op": "open", "url": self.base},
            {"op": "screenshot"},
        ])
        self.assertTrue(result.success, result.error)
        path = result.metadata["screenshot"]
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as handle:
            self.assertTrue(handle.read(8).startswith(b"\x89PNG"))
        os.remove(path)

    def test_follow_up_browser_action_uses_the_same_page(self):
        opened = self.tool.run([{"op": "open", "url": self.base}])
        self.assertTrue(opened.success, opened.error)
        clicked = self.tool.run([{"op": "click", "selector": "#next"}])
        self.assertTrue(clicked.success, clicked.error)
        self.assertNotIn("No browser was launched", clicked.error or "")
        self.assertEqual(clicked.metadata["title"], "Second Page")
        self.assertIn("/second", clicked.metadata["url"])
        self.assertIn("Page title: Second Page", clicked.output)

    def test_a_follow_up_does_not_use_another_conversations_page(self):
        first = playwright_session_key.set("conversation-a")
        try:
            opened = self.tool.run([{"op": "open", "url": self.base}])
        finally:
            playwright_session_key.reset(first)
        self.assertTrue(opened.success, opened.error)

        second = playwright_session_key.set("conversation-b")
        try:
            foreign = self.tool.run([{"op": "read"}])
        finally:
            playwright_session_key.reset(second)
        self.assertFalse(foreign.success)
        self.assertIn("No browser was launched", foreign.error)
        self.assertEqual(foreign.output, "")

        again = playwright_session_key.set("conversation-a")
        try:
            followed = self.tool.run([{"op": "title"}])
        finally:
            playwright_session_key.reset(again)
        self.assertTrue(followed.success, followed.error)
        self.assertEqual(followed.metadata["title"], "Start Page")

    def test_invalid_selector_returns_the_real_error(self):
        result = self.tool.run([
            {"op": "open", "url": self.base},
            {"op": "click", "selector": "#missing-element"},
        ])
        self.assertFalse(result.success)
        self.assertIn("missing-element", result.error)
        self.assertIn("No page result was invented.", result.error)
        self.assertNotIn("No browser was launched", result.error)
        self.assertNotIn("Page title:", result.output)
        self.assertEqual(result.output, "")
        self.assertFalse(result.metadata.get("title"))

    def test_click_without_an_open_page_does_not_invent_a_result(self):
        result = self.tool.run([{"op": "click", "selector": "#next"}])
        self.assertFalse(result.success)
        self.assertIn("No browser was launched", result.error)
        self.assertEqual(result.output, "")
        self.assertFalse(result.metadata.get("executed"))

    def test_wikipedia_english_link_returns_the_resulting_title_and_url(self):
        opened = self.tool.run([{"op": "open", "url": "https://www.wikipedia.org/"}])
        self.assertTrue(opened.success, opened.error)
        self.assertIn("wikipedia.org", opened.metadata["url"])
        clicked = self.tool.run([
            {"op": "click", "role": "link", "name": "English"},
            {"op": "read"},
        ])
        self.assertTrue(clicked.success, clicked.error)
        self.assertNotIn("No browser was launched", clicked.error or "")
        self.assertIn("en.wikipedia.org", clicked.metadata["url"])
        self.assertNotEqual(
            opened.metadata["url"].split("/")[2],
            clicked.metadata["url"].split("/")[2],
        )
        title = clicked.metadata["title"]
        self.assertTrue(title)
        self.assertIn("Wikipedia", title)
        self.assertIn(f"Page title: {title}", clicked.output)
        self.assertIn(clicked.metadata["url"], clicked.output)


class TestWebAgentUsesTheOpenPage(unittest.TestCase):
    def test_a_follow_up_click_is_sent_to_the_open_page(self):
        from agents.web_agent import WebAgent

        agent = WebAgent()
        tool = agent.get_tool("PLAYWRIGHT_TOOL")
        observed = ToolResult(
            tool="PLAYWRIGHT_TOOL",
            success=True,
            output="Page title: Second Page\nURL: http://127.0.0.1/second",
            metadata={
                "invoked": True,
                "executed": True,
                "title": "Second Page",
                "url": "http://127.0.0.1/second",
            },
        )
        token = playwright_capability.set(True)
        try:
            with patch("agents.web_agent.browser_is_open", return_value=True), patch.object(
                agent, "_complete", return_value='{"actions":[{"op":"click","selector":"#next"}]}'
            ), patch.object(tool, "run", return_value=observed) as run:
                out = agent.run("Click continue.")
        finally:
            playwright_capability.reset(token)
        self.assertEqual(run.call_args.args[0], [{"op": "click", "selector": "#next"}])
        self.assertIn("Page title: Second Page", out)
        self.assertIn("executed: yes", out)

    def test_a_script_reply_still_reads_the_named_page(self):
        from agents.web_agent import WebAgent

        agent = WebAgent()
        tool = agent.get_tool("PLAYWRIGHT_TOOL")
        observed = ToolResult(
            tool="PLAYWRIGHT_TOOL",
            success=True,
            output="Page title: OmniRoute\nMain heading: OmniRoute\nURL: https://www.omniroute.online/",
            metadata={
                "invoked": True,
                "executed": True,
                "title": "OmniRoute",
                "url": "https://www.omniroute.online/",
            },
        )
        prompt = (
            "Use Playwright to scrape https://www.omniroute.online/. "
            "Return the page title from the actual DOM."
        )
        token = playwright_capability.set(True)
        try:
            with patch.object(
                agent, "_complete", return_value="const { chromium } = require('playwright');"
            ), patch.object(tool, "run", return_value=observed) as run:
                out = agent.run(prompt)
        finally:
            playwright_capability.reset(token)
        self.assertEqual(
            run.call_args.args[0],
            [
                {"op": "goto", "url": "https://www.omniroute.online/"},
                {"op": "read"},
            ],
        )
        self.assertIn("Page title: OmniRoute", out)
        self.assertNotIn("npm install playwright", out)


class TestLiveBrowserRouting(unittest.TestCase):
    def test_an_enabled_plugin_sends_a_live_page_read_to_the_web_agent(self):
        from router import preview
        from routing_policy import CODING_AGENT, WEB_AGENT, RoutingPolicy

        class Fixed(RoutingPolicy):
            name = "fixed"

            def select_agent(self, intent, complexity, confidence, context=None):
                return {
                    "selected_agent": CODING_AGENT,
                    "policy": "fixed",
                    "decision_layer": "laya",
                    "reason": "Laya Decision AI selected CODING_AGENT",
                    "fallback_used": False,
                }

        prompt = (
            "Use Playwright to scrape https://www.omniroute.online/. "
            "Return the page title from the actual DOM."
        )
        token = playwright_capability.set(True)
        try:
            result = preview(prompt, policy=Fixed())
        finally:
            playwright_capability.reset(token)
        self.assertEqual(result["selected_agent"], WEB_AGENT)
        self.assertIn("WEB_AGENT", result["routing_reason"])

    def test_a_disabled_plugin_leaves_the_coding_decision(self):
        from router import preview
        from routing_policy import CODING_AGENT, RoutingPolicy

        class Fixed(RoutingPolicy):
            name = "fixed"

            def select_agent(self, intent, complexity, confidence, context=None):
                return {
                    "selected_agent": CODING_AGENT,
                    "policy": "fixed",
                    "decision_layer": "laya",
                    "reason": "Laya Decision AI selected CODING_AGENT",
                    "fallback_used": False,
                }

        prompt = (
            "Use Playwright to scrape https://www.omniroute.online/. "
            "Return the page title from the actual DOM."
        )
        token = playwright_capability.set(False)
        try:
            result = preview(prompt, policy=Fixed())
        finally:
            playwright_capability.reset(token)
        self.assertEqual(result["selected_agent"], CODING_AGENT)
