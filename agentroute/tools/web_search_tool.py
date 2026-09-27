"""WEB_SEARCH_TOOL — research/retrieval tool used by RESEARCH_AGENT.

Step 4 scope: the tool exists and is wired into the registry, but no search
backend is implemented. It reports honestly that it is unconfigured rather than
returning fabricated results.

TODO (Step 5+): plug in a real search backend behind SEARCH_API_KEY.
"""

from config import optional_env

from .base_tool import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    name = "WEB_SEARCH_TOOL"
    description = "Search the web for current information (backend not yet configured)."

    def is_available(self) -> bool:
        return bool(optional_env("SEARCH_API_KEY"))

    def run(self, query: str) -> ToolResult:
        if not self.is_available():
            return ToolResult(
                tool=self.name,
                success=False,
                error=(
                    "Web search is not configured (no SEARCH_API_KEY). "
                    "No results are fabricated."
                ),
                metadata={"configured": False, "query_chars": len(query or "")},
            )
        return ToolResult(
            tool=self.name,
            success=False,
            error="Search backend not implemented in Step 4.",
            metadata={"configured": True},
        )
