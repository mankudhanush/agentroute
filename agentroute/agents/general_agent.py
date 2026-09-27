"""GENERAL_AGENT — general questions, explanations, summarisation.

Model provider/ID resolve from the "general" role. The router selects
GENERAL_AGENT; it never sees the model behind it.
"""

from agents.base_agent import BaseAgent
from models import get_fallbacks, get_model, get_provider

ROLE = "general"

SYSTEM = (
    "You are the General Agent.\n"
    "Handle general questions, explanations, summarization, and simple tasks.\n"
    "Do not pretend to be another specialist agent."
)


class GeneralAgent(BaseAgent):
    name = "GENERAL_AGENT"
    description = "General questions, explanations & summarization"
    capabilities = ("general_qa", "explanation", "summarization", "multimodal")
    available_tools = ()
    system_prompt = SYSTEM

    def __init__(self):
        self.model_provider = get_provider(ROLE)
        self.model_id = get_model(ROLE)
        self.fallback_model_ids = tuple(get_fallbacks(ROLE))

    def run(self, prompt: str) -> str:
        return self._complete(prompt, system=self.system_prompt)
