"""REASONING_AGENT — complex reasoning, planning, architecture.

Fallback models stay INSIDE the agent: if the primary model is unavailable or
rate limited, this is still REASONING_AGENT.
"""

from agents.base_agent import BaseAgent
from models import get_fallbacks, get_model, get_provider

ROLE = "reasoning"

SYSTEM = (
    "You are the Reasoning Agent.\n"
    "Focus on complex reasoning, architecture, planning, analysis, and difficult "
    "technical problems.\n"
    "Think through trade-offs explicitly and structure your answer."
)


class ReasoningAgent(BaseAgent):
    name = "REASONING_AGENT"
    description = "Complex reasoning, architecture & planning"
    capabilities = (
        "complex_reasoning",
        "planning",
        "architecture",
        "long_context_reasoning",
        "agent_orchestration",
    )
    available_tools = ()
    system_prompt = SYSTEM

    def __init__(self):
        self.model_provider = get_provider(ROLE)
        self.model_id = get_model(ROLE)
        self.fallback_model_ids = tuple(get_fallbacks(ROLE))

    def run(self, prompt: str) -> str:
        return self._complete(prompt, system=self.system_prompt)
