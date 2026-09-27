"""Tool interface and the structured ToolResult every tool returns."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolResult:
    tool: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    artifacts: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "artifacts": list(self.artifacts),
            "metadata": dict(self.metadata),
        }


class BaseTool:
    name = "BASE_TOOL"
    description = ""

    def is_available(self) -> bool:
        """Whether this tool is usable in the current environment/config."""
        return True

    def run(self, *args, **kwargs) -> ToolResult:
        raise NotImplementedError
