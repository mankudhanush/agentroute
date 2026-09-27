"""Routing policies: the seam between classification and agent selection.

A policy turns (intent, complexity, confidence, context) into an explainable
decision:

    {
        "selected_agent": <AGENT NAME>,
        "policy": <policy name>,
        "reason": <human-readable, rule/statistic-grounded explanation>,
        "fallback_used": <bool>,
    }

Policies only ever return AGENT identities - never a model ID, never a tool name.

  * BaselineAgentPolicy   - deterministic intent -> agent rules.
  * AdaptiveRoutingPolicy - data-driven preference using RoutingMemory, with a
                            minimum-observation threshold and a baseline fallback.
  * LearnedRoutingPolicy  - future seam; NOT implemented.
"""

import threading

# Canonical agent names. Defined here (not in router) so policies have no
# dependency on router; router re-exports these.
#
# NOTE: there is deliberately NO Blender agent and NO Playwright agent.
# Blender is BLENDER_TOOL, owned by THREE_D_AGENT.
# Playwright is PLAYWRIGHT_TOOL, owned by WEB_AGENT.
GENERAL_AGENT = "GENERAL_AGENT"
CODING_AGENT = "CODING_AGENT"
REASONING_AGENT = "REASONING_AGENT"
RESEARCH_AGENT = "RESEARCH_AGENT"
THREE_D_AGENT = "THREE_D_AGENT"
WEB_AGENT = "WEB_AGENT"

AGENT_NAMES = (
    GENERAL_AGENT,
    CODING_AGENT,
    REASONING_AGENT,
    RESEARCH_AGENT,
    THREE_D_AGENT,
    WEB_AGENT,
)

# Which AGENTS may serve an intent. Adaptive routing picks among these - never
# among models or tools.
STEP4_CANDIDATES = {
    "general": [GENERAL_AGENT],
    "coding": [CODING_AGENT, REASONING_AGENT],
    "reasoning": [REASONING_AGENT, GENERAL_AGENT],
    "research": [RESEARCH_AGENT],
    "blender": [THREE_D_AGENT],
}

# Used when an intent is not present in a candidate map.
_DEFAULT_CANDIDATES = (GENERAL_AGENT,)

MIN_OBSERVATIONS = 5


class RoutingPolicy:
    """Interface. Implementations return an explainable decision dict."""

    name = "base"

    def select_agent(self, intent, complexity, confidence, context=None) -> dict:
        raise NotImplementedError


class BaselineAgentPolicy(RoutingPolicy):
    """Deterministic baseline: map a classified intent to one of the agents."""

    name = "baseline"

    _MAP = {
        "general": (GENERAL_AGENT, "General requests route to GENERAL_AGENT"),
        "coding": (CODING_AGENT, "Coding tasks route to CODING_AGENT"),
        "reasoning": (REASONING_AGENT, "Complex reasoning routes to REASONING_AGENT"),
        "research": (RESEARCH_AGENT, "Research/tool-use tasks route to RESEARCH_AGENT"),
        "blender": (
            THREE_D_AGENT,
            "3D/Blender tasks route to THREE_D_AGENT, which owns BLENDER_TOOL",
        ),
    }

    def select_agent(self, intent, complexity, confidence, context=None) -> dict:
        agent, reason = self._MAP.get(
            intent,
            (GENERAL_AGENT, "Unrecognised intent falls back to GENERAL_AGENT"),
        )
        return {
            "selected_agent": agent,
            "policy": self.name,
            "reason": reason,
            "fallback_used": False,
        }


class AdaptiveRoutingPolicy(RoutingPolicy):
    """Prefer the agent with the strongest measured outcomes - when data supports it.

    This is NOT machine learning. It is a transparent, deterministic rule over
    historical statistics stored in RoutingMemory:

      1. Determine candidate AGENTS for the task's intent.
      2. Read historical stats for the (intent, complexity) category.
      3. Keep only candidates with >= MIN_OBSERVATIONS observations (else the data
         is treated as insufficient - small samples never override the baseline).
      4. Among eligible candidates, pick the highest average outcome score
         (tie-break: higher success rate, then lower latency).
      5. If nothing is eligible, defer to the baseline policy.
    """

    name = "adaptive"

    def __init__(
        self,
        memory,
        baseline=None,
        min_observations: int = MIN_OBSERVATIONS,
        candidates_by_intent: dict | None = None,
    ):
        self.memory = memory
        self.baseline = baseline or BaselineAgentPolicy()
        self.min_observations = min_observations
        self.candidates_by_intent = (
            candidates_by_intent if candidates_by_intent is not None else STEP4_CANDIDATES
        )

    def select_agent(self, intent, complexity, confidence, context=None) -> dict:
        candidates = self._candidates(intent)

        # Specialist intents (e.g. 3D) have no alternative agent to compare - defer.
        if len(candidates) < 2:
            base = self.baseline.select_agent(intent, complexity, confidence, context)
            return {
                "selected_agent": base["selected_agent"],
                "policy": self.name,
                "reason": (
                    f"Baseline specialist routing for {intent} tasks "
                    f"(no alternative agents to compare)"
                ),
                "fallback_used": True,
            }

        stats = self.memory.agent_stats(intent, complexity)
        eligible = {
            agent: s
            for agent, s in stats.items()
            if agent in candidates
            and s["attempts"] >= self.min_observations
            and s["average_score"] is not None
        }

        if not eligible:
            base = self.baseline.select_agent(intent, complexity, confidence, context)
            return {
                "selected_agent": base["selected_agent"],
                "policy": self.name,
                "reason": (
                    f"Insufficient historical data (need >= {self.min_observations} "
                    f"observations per agent for {complexity} {intent}); "
                    f"using baseline - {base['reason']}"
                ),
                "fallback_used": True,
            }

        agent, s = max(
            eligible.items(),
            key=lambda kv: (
                kv[1]["average_score"],
                kv[1]["success_rate"],
                -(kv[1]["average_latency_ms"] or 0),
            ),
        )
        return {
            "selected_agent": agent,
            "policy": self.name,
            "reason": (
                f"{agent} has the strongest measured outcome score "
                f"({s['average_score']:.2f}) for {complexity} {intent} tasks over "
                f"{s['attempts']} observations (>= {self.min_observations} threshold)"
            ),
            "fallback_used": False,
        }

    def _candidates(self, intent):
        """Agents capable of serving this intent (never models, never tools)."""
        return list(self.candidates_by_intent.get(intent, _DEFAULT_CANDIDATES))


# The Laya policy holds a loaded checkpoint. Building one per request reloads
# that checkpoint every time, which costs seconds per request and accumulates
# memory until the process can no longer load another - at which point every
# later request silently degrades to the baseline. One policy per process.
_LAYA_POLICY = None
_LAYA_LOCK = threading.Lock()


def build_policy(memory=None, layer: str | None = None) -> RoutingPolicy:
    """Construct the configured decision layer.

    DECISION_LAYER = laya (default) | baseline | adaptive

    When Laya is selected it is given a baseline fallback, so an environment
    without the laya package still routes - but such decisions are explicitly
    labelled "Laya unavailable - fallback routing" and are never reported as
    Laya decisions.

    The Laya policy is cached per process and shared across requests. The
    baseline and adaptive policies are cheap and stay per call.
    """
    from config import optional_env

    baseline = BaselineAgentPolicy()
    layer = (layer or optional_env("DECISION_LAYER", "laya") or "laya").lower()

    if layer == "laya":
        return _laya_policy(baseline)
    if layer == "adaptive" and memory is not None:
        return AdaptiveRoutingPolicy(memory, baseline=baseline)
    return baseline


def _laya_policy(baseline: RoutingPolicy) -> RoutingPolicy:
    """The process-wide Laya policy, built once."""
    global _LAYA_POLICY
    if _LAYA_POLICY is None:
        with _LAYA_LOCK:
            if _LAYA_POLICY is None:
                from laya_routing_policy import LayaRoutingPolicy

                _LAYA_POLICY = LayaRoutingPolicy(fallback=baseline)
    return _LAYA_POLICY


def reset_policy_cache() -> None:
    """Drop the cached Laya policy. For tests and for reloading after a config change."""
    global _LAYA_POLICY
    with _LAYA_LOCK:
        _LAYA_POLICY = None


class LearnedRoutingPolicy(RoutingPolicy):
    """FUTURE (Step 5+): a genuinely learned policy. NOT implemented yet.

    TODO: replace the deterministic AdaptiveRoutingPolicy with a model that can use
    any/all of:
      * historical routing observations (already collected via RoutingMemory)
      * prompt/task embeddings and task similarity
      * per-agent success rate, latency, and user feedback
      * conversation context (see ConversationState)
      * explicit reward signals / RL from routing outcomes

    The decision contract must stay the same so this drops in without touching the
    router.
    """

    name = "learned"

    def select_agent(self, intent, complexity, confidence, context=None) -> dict:
        raise NotImplementedError(
            "LearnedRoutingPolicy is a future extension point and is not implemented."
        )
