"""CODING_AGENT — code generation, debugging, code analysis.

The router selects CODING_AGENT, never a model name.
"""

from agents.base_agent import BaseAgent
from models import get_fallbacks, get_model, get_provider

ROLE = "coding"

SYSTEM = (
    "You are the Coding Agent.\n"
    "Focus on programming, debugging, software engineering, code generation, "
    "and technical implementation.\n"
    "Provide correct, runnable code with brief explanations."
)


class CodingAgent(BaseAgent):
    name = "CODING_AGENT"
    description = "Code generation & debugging"
    capabilities = (
        "code_generation",
        "debugging",
        "code_analysis",
        "software_engineering",
    )
    # Declared for the future; CODE_EXECUTION_TOOL is a registry placeholder.
    available_tools = ("CODE_EXECUTION_TOOL",)
    system_prompt = SYSTEM

    def __init__(self):
        self.model_provider = get_provider(ROLE)
        self.model_id = get_model(ROLE)
        self.fallback_model_ids = tuple(get_fallbacks(ROLE))

    def run(self, prompt: str) -> str:
        return self._complete(prompt, system=self.system_prompt)
