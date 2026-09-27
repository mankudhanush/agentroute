"""Tool registry — tools are registered independently of agents.

Adding a tool here requires NO change to router.py. Agents reference tools by
name via their `available_tools`.

BLENDER_TOOL lives here and only here. It is never an agent.
"""

from .base_tool import BaseTool, ToolResult
from .blender_tool import BlenderTool
from .playwright_tool import PlaywrightTool
from .web_search_tool import WebSearchTool


class PlaceholderTool(BaseTool):
    """A declared-but-unimplemented tool, so the architecture is extensible."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description or f"{name} (declared, not yet implemented)"

    def is_available(self) -> bool:
        return False

    def run(self, *args, **kwargs) -> ToolResult:
        return ToolResult(
            tool=self.name,
            success=False,
            error=f"{self.name} is declared but not implemented in Step 4.",
            metadata={"implemented": False},
        )


_TOOLS: dict = {}


def register(tool: BaseTool) -> None:
    _TOOLS[tool.name] = tool


def get_tool(name: str) -> BaseTool:
    if name not in _TOOLS:
        raise KeyError(f"Unknown tool: {name!r}. Registered: {', '.join(list_tools())}")
    return _TOOLS[name]


def list_tools() -> list:
    return sorted(_TOOLS)


def tool_metadata() -> list:
    return [
        {
            "name": t.name,
            "description": t.description,
            "available": t.is_available(),
            "implemented": not isinstance(t, PlaceholderTool),
        }
        for _, t in sorted(_TOOLS.items())
    ]


# --- default registrations --------------------------------------------------
register(BlenderTool())
register(PlaywrightTool())
register(WebSearchTool())
for _name in ("CODE_EXECUTION_TOOL", "FILESYSTEM_TOOL", "GITHUB_TOOL"):
    register(PlaceholderTool(_name))
