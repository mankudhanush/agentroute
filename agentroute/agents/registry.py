"""Agent registry — the agents the router may select.

INVARIANT: only AGENTS appear here. Tools (BLENDER_TOOL, WEB_SEARCH_TOOL, ...) and
model IDs (gemma, laguna, nemotron, inkling) must NEVER appear as entries.

Adding an agent here requires no change to router.py or to the tool layer.
"""

from agents.coding_agent import CodingAgent
from agents.general_agent import GeneralAgent
from agents.reasoning_agent import ReasoningAgent
from agents.research_agent import ResearchAgent
from agents.three_d_agent import ThreeDAgent
from agents.web_agent import WebAgent

AGENT_CLASSES = (
    GeneralAgent,
    CodingAgent,
    ReasoningAgent,
    ResearchAgent,
    ThreeDAgent,
    WebAgent,
)

AGENT_NAMES = (
    "GENERAL_AGENT",
    "CODING_AGENT",
    "REASONING_AGENT",
    "RESEARCH_AGENT",
    "THREE_D_AGENT",
    "WEB_AGENT",
)


def build_agent_registry() -> dict:
    """Return {agent_name: agent_instance} for the Step 4 architecture."""
    return {cls.name: cls() for cls in AGENT_CLASSES}


def agent_metadata() -> list:
    """Describe every registered agent (name, capabilities, model, tools)."""
    return [agent.describe() for agent in build_agent_registry().values()]
