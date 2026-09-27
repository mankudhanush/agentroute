"""RESEARCH_AGENT — research, synthesis and (future) retrieval workflows.

Tools: WEB_SEARCH_TOOL — the AGENT decides whether it needs it. The router does
not select tools. The system prompt forbids claiming research that did not run.
"""

from agents.base_agent import BaseAgent
from models import get_fallbacks, get_model, get_provider

ROLE = "research"

SYSTEM = (
    "You are the Research Agent.\n"
    "Focus on research-oriented questions, information synthesis, comparison, "
    "and evidence-oriented answers.\n"
    "Do not claim web research was performed if no research tool was actually used."
)


class ResearchAgent(BaseAgent):
    name = "RESEARCH_AGENT"
    description = "Research & information synthesis"
    capabilities = (
        "research",
        "information_synthesis",
        "retrieval",
        "tool_use",
        "multimodal_reasoning",
    )
    available_tools = ("WEB_SEARCH_TOOL",)
    system_prompt = SYSTEM

    def __init__(self):
        self.model_provider = get_provider(ROLE)
        self.model_id = get_model(ROLE)
        self.fallback_model_ids = tuple(get_fallbacks(ROLE))

    def run(self, prompt: str) -> str:
        # The agent decides whether the tool is needed and usable. The research
        # context goes BEFORE the incoming prompt: that prompt may carry the
        # execution contract, which has to stay the last thing the model reads.
        context = self.gather_context(prompt)
        return self._complete(
            f"<research_context>\n{context}\n</research_context>\n\n{prompt}",
            system=self.system_prompt,
        )

    def gather_context(self, query: str) -> str:
        """Try the web search tool; report honestly when it is unavailable."""
        tool = self.get_tool("WEB_SEARCH_TOOL")
        if not tool.is_available():
            return (
                "[no web search tool was executed - answer from model knowledge "
                "only and do not claim live sources]"
            )
        result = tool.run(query)
        if result.success:
            return result.output
        return f"[web search unavailable: {result.error}]"
