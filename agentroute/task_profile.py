"""TaskProfile — the structured understanding of what a request needs.

This is the bridge between the DECISION layer (Laya) and the MODEL SELECTION
layer. It deliberately REUSES the existing pieces rather than duplicating them:

    classifier classification  ->  intent, complexity (3-value), confidence
    routing decision           ->  complexity_level (4-level, when Laya supplies it)
    selected agent             ->  permitted tools
    conversation context       ->  context_dependent

Complexity is a first-class routing dimension on a 4-level scale:

    1 SIMPLE    2 MODERATE    3 COMPLEX    4 EXPERT

The level comes from the decision layer (Laya answers it as a typed choice). It
is only *derived* from the legacy 3-value label when no decision layer supplied
one - and that derivation can never reach level 4, which is honest: the keyword
classifier cannot distinguish expert work.
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

LEVEL_SIMPLE = 1
LEVEL_MODERATE = 2
LEVEL_COMPLEX = 3
LEVEL_EXPERT = 4

COMPLEXITY_LEVELS = (LEVEL_SIMPLE, LEVEL_MODERATE, LEVEL_COMPLEX, LEVEL_EXPERT)
COMPLEXITY_NAMES = {
    LEVEL_SIMPLE: "simple",
    LEVEL_MODERATE: "moderate",
    LEVEL_COMPLEX: "complex",
    LEVEL_EXPERT: "expert",
}

# Legacy 3-value scale <-> 4-level scale.
_LABEL_TO_LEVEL = {"simple": LEVEL_SIMPLE, "medium": LEVEL_MODERATE, "complex": LEVEL_COMPLEX}
_LEVEL_TO_LABEL = {
    LEVEL_SIMPLE: "simple",
    LEVEL_MODERATE: "medium",
    LEVEL_COMPLEX: "complex",
    LEVEL_EXPERT: "complex",
}

# Option keys Laya chooses between for the 4-level complexity question.
LAYA_LEVEL_KEYS = {
    "level_1_simple": LEVEL_SIMPLE,
    "level_2_moderate": LEVEL_MODERATE,
    "level_3_complex": LEVEL_COMPLEX,
    "level_4_expert": LEVEL_EXPERT,
}

# Capability (domain) derived from the existing intent vocabulary.
CAPABILITY_BY_INTENT = {
    "general": "general",
    "coding": "coding",
    "reasoning": "reasoning",
    "research": "research",
    "blender": "creative_3d",
}
CAPABILITIES = tuple(sorted(set(CAPABILITY_BY_INTENT.values())))

# The capability each agent covers. The decision layer answers "which agent"
# and "what kind of request" separately, and those answers can disagree. The
# AGENT is the actual routing decision, so it wins - otherwise the profile (and
# therefore model selection and the UI) would describe a different task than
# the one being executed.
CAPABILITY_BY_AGENT = {
    "GENERAL_AGENT": "general",
    "CODING_AGENT": "coding",
    "REASONING_AGENT": "reasoning",
    "RESEARCH_AGENT": "research",
    "THREE_D_AGENT": "creative_3d",
    "WEB_AGENT": "browser",
}

# The capability token a model profile uses for this task capability.
CAPABILITY_TOKEN = {
    "general": "general",
    "coding": "coding",
    "reasoning": "reasoning",
    "research": "research",
    "creative_3d": "creative",
}

# Complexity sets a FLOOR on how strong a model must be - never the whole
# answer. Other task signals may raise the demand above this floor.
COMPLEXITY_TIER_FLOOR = {LEVEL_SIMPLE: 1, LEVEL_MODERATE: 1, LEVEL_COMPLEX: 2, LEVEL_EXPERT: 3}
MAX_DEMAND_TIER = 3

# Vendor-stated specializations that genuinely serve this capability. 3D work
# is produced as a Blender PYTHON SCRIPT, so it needs code generation as well
# as creative judgement - that is an architectural fact about our 3D agent.
SPECIALIZATIONS_FOR_CAPABILITY = {
    "coding": frozenset({"coding"}),
    "reasoning": frozenset({"reasoning"}),
    "research": frozenset({"research"}),
    "general": frozenset({"general"}),
    "creative_3d": frozenset({"creative", "coding"}),
}

# A request that enumerates this many distinct deliverables is broad enough to
# demand more capability than its complexity label alone implies.
BREADTH_THRESHOLD = 5

# Operations that must return the existing artifact in full. Reproducing a
# stored artifact faithfully while changing part of it is exacting work, so it
# is never "quick, shallow" work however short the request that asked for it.
REWRITING_OPERATIONS = frozenset({"modify", "fix", "extend"})

# Demand floor for a request that rewrites an existing artifact.
REWRITE_DEMAND_FLOOR = 2

# Rough characters-per-token for sizing the context a rewrite needs. Deliberately
# pessimistic: undercounting would let a model be chosen that cannot hold the
# artifact, which is the failure this guards against.
CHARS_PER_TOKEN = 3
# The artifact is carried twice over (prompt in, artifact out) plus the
# surrounding instructions.
CONTEXT_HEADROOM = 2.5

# Outputs that are run rather than read. When a tool executes the artifact,
# correctness matters more than latency.
EXECUTABLE_OUTPUTS = ("code", "blender_script")

# What the request is expected to produce. Architectural mapping, not a guess
# about the prompt's wording.
_OUTPUT_TYPE = {
    "coding": "code",
    "creative_3d": "blender_script",
    "research": "report",
    "reasoning": "analysis",
    "general": "text",
}


def capability_for(intent: str, selected_agent: Optional[str] = None) -> str:
    """The capability this request falls under.

    A pure lookup over the existing maps, exposed so a caller can know the
    capability before the full TaskProfile is assembled. The AGENT is the
    actual routing decision, so it wins over the classified intent.
    """
    return CAPABILITY_BY_AGENT.get(
        selected_agent, CAPABILITY_BY_INTENT.get(intent, "general")
    )


def level_from_label(label: str) -> int:
    return _LABEL_TO_LEVEL.get(label, LEVEL_MODERATE)


def label_from_level(level: int) -> str:
    return _LEVEL_TO_LABEL.get(level, "medium")


def level_name(level: int) -> str:
    return COMPLEXITY_NAMES.get(level, "unknown")


@dataclass
class TaskProfile:
    """What the request needs. Consumed by the model selector."""

    intent: str
    capability: str
    complexity: str          # legacy 3-value label (backwards compatible)
    complexity_level: int    # first-class 1-4 scale
    confidence: float
    requires_tools: bool = False
    required_tools: tuple = ()
    context_dependent: bool = False
    output_type: str = "text"
    decision_layer: str = "unknown"
    complexity_source: str = "derived"  # "decision-layer" | "derived"
    # How many distinct deliverables the request enumerates. A STRUCTURAL
    # property of the request, never a keyword->model rule.
    breadth: int = 1
    # What the request DOES to the work (create | modify | fix | extend |
    # continue | explain), as opposed to what the work is about. Supplied by
    # the task-context layer, which is what knows whether a stored artifact
    # exists. Defaults to "create" so callers that predate it are unchanged.
    operation: str = "create"
    # Size of the artifact this request operates on. 0 when there is none.
    artifact_chars: int = 0

    @property
    def complexity_name(self) -> str:
        return level_name(self.complexity_level)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["required_tools"] = list(self.required_tools)
        data["complexity_name"] = self.complexity_name
        return data


def _requires_tools(capability: str) -> bool:
    """Whether the capability inherently needs a tool in THIS architecture.

    3D work cannot be completed without Blender, so it is a hard requirement.
    Research may use WEB_SEARCH_TOOL but does not require it (the agent answers
    from model knowledge when the tool is unconfigured), so it is not marked
    required. This is an architectural fact about our agents, not prompt
    keyword matching.
    """
    return capability in ("creative_3d", "browser")


def count_deliverables(prompt: Optional[str]) -> int:
    """How many distinct things the request asks for.

    Purely structural: it counts enumerated clauses, so it works on any wording
    and never maps a keyword to a model. "Build X with a, b, c and d" demands
    more of a model than "Build X", even at the same complexity label.
    """
    if not prompt or not prompt.strip():
        return 1
    parts = [p for p in re.split(r",|\band\b|;|\n", prompt) if p.strip()]
    return max(1, len(parts))


@dataclass(frozen=True)
class TaskRequirements:
    """What executing THIS task actually demands of a model.

    Derived from the whole TaskProfile - capability, complexity, output, tools
    and the shape of the request - so model selection is never a lookup on the
    complexity number alone.
    """

    capability: str
    capability_token: str
    complexity_level: int
    demand_tier: int
    needed_specializations: frozenset = field(default_factory=frozenset)
    needs_code_generation: bool = False
    needs_deep_reasoning: bool = False
    needs_research_synthesis: bool = False
    needs_creative: bool = False
    needs_tools: bool = False
    needs_long_context: bool = False
    context_dependent: bool = False
    latency_sensitive: bool = False
    breadth: int = 1
    output_type: str = "text"
    operation: str = "create"
    rewrites_artifact: bool = False
    required_context_tokens: Optional[int] = None

    def describe(self) -> str:
        """Human-readable list of what this task needs (used in explanations)."""
        flags = [
            ("faithful rewrite of an existing artifact", self.rewrites_artifact),
            ("code generation", self.needs_code_generation),
            ("deep reasoning", self.needs_deep_reasoning),
            ("research synthesis", self.needs_research_synthesis),
            ("creative judgement", self.needs_creative),
            ("tool use", self.needs_tools),
            ("long context", self.needs_long_context),
            ("conversation continuity", self.context_dependent),
            ("low latency", self.latency_sensitive),
        ]
        named = [name for name, on in flags if on]
        return ", ".join(named) if named else "no special requirements"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["needed_specializations"] = sorted(self.needed_specializations)
        data["summary"] = self.describe()
        return data


def derive_requirements(profile: TaskProfile) -> TaskRequirements:
    """Turn a TaskProfile into concrete execution requirements.

    Complexity contributes a FLOOR (`COMPLEXITY_TIER_FLOOR`); depth, breadth and
    synthesis needs can raise the demand above it. Nothing here names a model or
    a provider.
    """
    capability = profile.capability
    level = profile.complexity_level
    output_type = profile.output_type

    needs_code = capability == "coding" or output_type in EXECUTABLE_OUTPUTS
    needs_creative = capability == "creative_3d"
    needs_research = capability == "research"
    # The answer IS the analysis. This does not depend on crossing the L3
    # boundary: a "moderate" consistency trade-off question is still analytical
    # work, and must not be served by the lightest model available.
    needs_deep_reasoning = (
        capability == "reasoning" or output_type == "analysis"
    ) and level >= LEVEL_MODERATE

    # Returning an existing artifact complete, with one part changed and the
    # rest intact, is exacting work - regardless of how short the request was.
    rewrites_artifact = (
        profile.operation in REWRITING_OPERATIONS and profile.artifact_chars > 0
    )

    breadth = max(1, profile.breadth)
    # Long context is demanded by breadth, by depending on earlier turns, or by
    # having to carry a stored artifact through the model.
    needs_long_context = (
        breadth >= BREADTH_THRESHOLD or profile.context_dependent or rewrites_artifact
    )

    required_context_tokens = None
    if profile.artifact_chars > 0:
        required_context_tokens = int(
            profile.artifact_chars / CHARS_PER_TOKEN * CONTEXT_HEADROOM
        )

    # The artifact will actually be executed by a tool, so a syntax error fails
    # the whole task - correctness outranks speed.
    executed_artifact = profile.requires_tools and output_type in EXECUTABLE_OUTPUTS

    demand = COMPLEXITY_TIER_FLOOR.get(level, 1)
    if needs_deep_reasoning:
        demand = max(demand, MAX_DEMAND_TIER if level >= LEVEL_COMPLEX else 2)
    if needs_research:
        demand = max(demand, MAX_DEMAND_TIER if level >= LEVEL_COMPLEX else 2)
    if executed_artifact:
        demand = max(demand, 2)
    if rewrites_artifact:
        demand = max(demand, REWRITE_DEMAND_FLOOR)
    if breadth >= BREADTH_THRESHOLD:
        demand += 1
    demand = max(1, min(MAX_DEMAND_TIER, demand))

    # Only quick, shallow work should trade capability for speed. Analysis,
    # synthesis, executable output and faithful rewrites never qualify.
    latency_sensitive = (
        level <= LEVEL_MODERATE
        and not needs_deep_reasoning
        and not needs_research
        and not executed_artifact
        and not rewrites_artifact
        and breadth < BREADTH_THRESHOLD
    )

    return TaskRequirements(
        capability=capability,
        capability_token=CAPABILITY_TOKEN.get(capability, "general"),
        complexity_level=level,
        demand_tier=demand,
        needed_specializations=SPECIALIZATIONS_FOR_CAPABILITY.get(
            capability, frozenset()
        ),
        needs_code_generation=needs_code,
        needs_deep_reasoning=needs_deep_reasoning,
        needs_research_synthesis=needs_research,
        needs_creative=needs_creative,
        needs_tools=profile.requires_tools,
        needs_long_context=needs_long_context,
        context_dependent=profile.context_dependent,
        latency_sensitive=latency_sensitive,
        breadth=breadth,
        output_type=output_type,
        operation=profile.operation,
        rewrites_artifact=rewrites_artifact,
        required_context_tokens=required_context_tokens,
    )


def build_task_profile(
    classification: dict,
    decision: dict,
    agent=None,
    context: Optional[dict] = None,
    operation: str = "create",
    artifact_chars: int = 0,
) -> TaskProfile:
    """Assemble a TaskProfile from existing routing outputs."""
    intent = classification.get("intent", "general")
    # Prefer the capability of the agent actually selected; fall back to intent
    # when no agent is known yet.
    capability = capability_for(intent, decision.get("selected_agent"))
    complexity = classification.get("complexity", "medium")

    # Prefer an explicit level from the decision layer (Laya); otherwise derive.
    supplied = decision.get("complexity_level")
    if supplied in COMPLEXITY_LEVELS:
        level, source = supplied, "decision-layer"
    else:
        level, source = level_from_label(complexity), "derived"

    required_tools = tuple(getattr(agent, "available_tools", ()) or ())
    previous = (context or {}).get("previous_intents") or []
    # The router puts the request text in the context; only the DERIVED
    # structural signal is kept, never the raw prompt.
    breadth = count_deliverables((context or {}).get("prompt"))

    return TaskProfile(
        intent=intent,
        capability=capability,
        complexity=complexity,
        complexity_level=level,
        confidence=classification.get("confidence", 0.5),
        requires_tools=_requires_tools(capability),
        required_tools=required_tools,
        context_dependent=bool(previous),
        output_type=_OUTPUT_TYPE.get(capability, "text"),
        decision_layer=decision.get("decision_layer") or decision.get("policy", "unknown"),
        complexity_source=source,
        breadth=breadth,
        operation=operation,
        artifact_chars=max(0, artifact_chars),
    )
