"""Router — classify a prompt, pick an agent via a routing policy, run it, and
record the outcome.

Pipeline:
    prompt -> classifier -> decision layer -> agent.run() -> outcome
           -> routing observation (persisted if a memory is given) -> result

When ``policy`` is omitted, ``DECISION_LAYER`` chooses the policy
(laya | baseline | adaptive). An explicit ``policy`` always wins.
``select_agent()`` keeps the baseline map for its Step 2 contract.

Architectural rules (still enforced):
  * The router NEVER calls Groq/OpenRouter/Blender directly — agents own all
    external calls.
  * `select_agent(classification) -> str` keeps its Step 2 contract for backwards
    compatibility; the policy object is the new, richer path.

Public contract:
    route(prompt, policy=None, conversation_state=None, memory=None,
          agents=None, feedback=None) -> dict
"""

from time import perf_counter

from agents.registry import build_agent_registry
from agents.web_agent import requests_live_browser
from classifier import classify, validate_classification
from errors import AgentRouteError, ClassifierError, ConfigurationError
from model_selector import select_model
from outcome import score_outcome
from routing_observation import RoutingObservation, make_task_id
from task_context import (
    adopt_context,
    empty_context_fields,
    execution_prompt,
    match_task_context,
    strip_internal_markers,
)
from task_profile import build_task_profile, capability_for

# Re-export canonical agent names (defined in routing_policy) for convenience.
# There is no Blender agent: Blender is a TOOL owned by THREE_D_AGENT.
from routing_policy import (  # noqa: F401
    AGENT_NAMES,
    CODING_AGENT,
    GENERAL_AGENT,
    REASONING_AGENT,
    RESEARCH_AGENT,
    THREE_D_AGENT,
    WEB_AGENT,
    BaselineAgentPolicy,
    build_policy,
)
from tools.playwright_tool import playwright_capability

# Baseline map for select_agent(). route()/preview() use build_policy() instead.
_BASELINE = BaselineAgentPolicy()


def default_agents() -> dict:
    """Default agent registry: {agent_name: agent_instance}."""
    return build_agent_registry()


def select_agent(classification: dict) -> str:
    """Convenience helper: classification dict -> agent name string.

    Delegates to the baseline policy so there is a single source of truth for the
    baseline rules.
    """
    validate_classification(classification)
    decision = _BASELINE.select_agent(
        classification["intent"],
        classification["complexity"],
        classification["confidence"],
    )
    return decision["selected_agent"]


def _decide(prompt: str, policy, conversation_state):
    """Shared classify + policy step. No agent is invoked, no model is called.

    The routing context always carries the request text under "prompt" so that a
    decision layer which reads the raw request (e.g. Laya) can do so without
    changing the RoutingPolicy signature.
    """
    classification = classify(prompt)  # may raise ClassifierError (bad input)
    context = dict(conversation_state.context()) if conversation_state is not None else {}
    context["prompt"] = prompt
    # The previous turn must not define a new request. A follow-up sees only the
    # branch it actually continues, so an older branch can be named again.
    if conversation_state is not None and getattr(conversation_state, "contexts", None):
        hinted = match_task_context(prompt, conversation_state)
        if hinted.continued and hinted.context is not None and hinted.context.turns:
            # The branch's first request names the task. A later short turn
            # ("add a drawer") does not, and must not redefine it.
            context["previous_prompts"] = [hinted.context.turns[0].prompt]
        else:
            context["previous_prompts"] = []

    decision = policy.select_agent(
        classification["intent"],
        classification["complexity"],
        classification["confidence"],
        context,
    )
    decision = _use_web_agent_for_live_browser(prompt, decision)

    # A decision layer may supply its own classification metadata (Laya answers
    # intent/complexity in the same forward pass). Validate before trusting it.
    override = decision.get("classification")
    if override:
        validate_classification(override)
        classification = override

    return classification, decision, context


def _use_web_agent_for_live_browser(prompt: str, decision: dict) -> dict:
    """A live page read uses WEB_AGENT when the Playwright plugin is on.

    The plugin does not choose an agent by itself. Laya can still call a
    request to read a live page a coding task, and CODING_AGENT then writes a
    script instead of opening the page. WEB_AGENT owns PLAYWRIGHT_TOOL, so
    that request is handed to it.
    """
    if decision.get("selected_agent") not in (CODING_AGENT, GENERAL_AGENT):
        return decision
    if not playwright_capability.get() or not requests_live_browser(prompt):
        return decision
    corrected = dict(decision)
    corrected["selected_agent"] = WEB_AGENT
    corrected["reason"] = (
        "Playwright is enabled and this request asks to read a live page, "
        f"so WEB_AGENT handles it. {decision.get('reason', '')}"
    )
    return corrected


def _task_and_model(classification, decision, agent, context, match=None):
    """Build the TaskProfile then select a model for it (no model call).

    ``match`` is the task-context decision for this request. It is what knows
    whether a stored artifact exists, so the profile can describe the operation
    (create | modify | fix | extend | continue | explain) and the model can be
    chosen for the work that is actually being asked for.
    """
    artifact = match.artifact if match is not None else None
    profile = build_task_profile(
        classification,
        decision,
        agent=agent,
        context=context,
        operation=match.operation if match is not None else "create",
        artifact_chars=len(artifact or ""),
    )
    selection = select_model(profile, agent) if agent is not None else None
    return profile, selection


def _match_context(prompt, conversation_state, classification, decision):
    """Which stored branch this request continues. No branch is created here."""
    if conversation_state is None:
        return None
    capability = capability_for(
        classification.get("intent", "general"), decision.get("selected_agent")
    )
    return match_task_context(
        prompt,
        conversation_state,
        capability=capability,
        selected_agent=decision.get("selected_agent"),
    )


def _routing_fields(profile, selection) -> dict:
    """Step 6 routing metadata, added alongside the existing result keys."""
    fields = {
        "capability": profile.capability,
        "complexity_level": profile.complexity_level,
        "complexity_name": profile.complexity_name,
        "complexity_source": profile.complexity_source,
        "requires_tools": profile.requires_tools,
        "required_tools": list(profile.required_tools),
        "context_dependent": profile.context_dependent,
        "output_type": profile.output_type,
        "task_profile": profile.to_dict(),
        "operation": profile.operation,
        "artifact_chars": profile.artifact_chars,
        "selected_model": None,
        "model_provider": None,
        "model_reason": "no model selected",
        "matched_capabilities": [],
        "model_fallbacks": [],
    }
    if selection is not None:
        fields.update(
            selected_model=selection.model_id,
            model_provider=selection.provider,
            model_reason=selection.reason,
            matched_capabilities=list(selection.matched_capabilities),
            model_fallbacks=list(selection.fallback_models),
            model_tier=selection.tier,
        )
    return fields


def preview(prompt: str, policy=None, conversation_state=None, agents: dict | None = None) -> dict:
    """Routing decision WITHOUT invoking the agent (no model call, no API key).

    Lets a caller show which agent would handle a prompt - used by the UI's
    offline mode so it still goes through the router rather than around it.

    An omitted policy follows DECISION_LAYER. An explicit policy is used as given.
    """
    if policy is None:
        policy = build_policy()
    classification, decision, context = _decide(prompt, policy, conversation_state)

    # Metadata only - building the registry makes no API calls.
    agent = (agents if agents is not None else default_agents()).get(
        decision["selected_agent"]
    )
    match = _match_context(prompt, conversation_state, classification, decision)
    profile, selection = _task_and_model(classification, decision, agent, context, match)

    result = {
        "selected_agent": decision["selected_agent"],
        "intent": classification["intent"],
        "complexity": classification["complexity"],
        "confidence": classification["confidence"],
        "policy": decision["policy"],
        "decision_layer": decision.get("decision_layer", decision["policy"]),
        "routing_reason": decision["reason"],
        "fallback_used": decision.get("fallback_used", False),
        "laya_error": decision.get("laya_error"),
        "preview": True,
    }
    result.update(_routing_fields(profile, selection))
    result.update(match.public_fields() if match is not None else empty_context_fields())
    return result


def route(
    prompt: str,
    policy=None,
    conversation_state=None,
    memory=None,
    agents: dict | None = None,
    feedback: str | None = None,
    state=None,  # deprecated alias for conversation_state
) -> dict:
    """Classify, select via policy, run the agent, score + record, return result.

    An omitted policy follows DECISION_LAYER. Adaptive routing receives ``memory``.
    """
    registry = agents if agents is not None else default_agents()
    conversation_state = conversation_state or state
    # Adaptive routing needs the caller's memory; laya/baseline ignore it.
    if policy is None:
        policy = build_policy(memory=memory)

    classification, decision, context = _decide(prompt, policy, conversation_state)
    intent = classification["intent"]
    complexity = classification["complexity"]
    confidence = classification["confidence"]
    agent_name = decision["selected_agent"]

    agent = registry.get(agent_name)
    if agent is None:
        raise ClassifierError(f"No agent registered for {agent_name!r}.")

    # Which stored branch this request continues, and what it does to that work.
    # This does not change the AGENT decision, which is already made; it tells
    # the profile and the model selector what is actually being asked for.
    task_match = _match_context(prompt, conversation_state, classification, decision)

    # Agent chosen -> now choose the model for THIS request (no API call yet).
    profile, selection = _task_and_model(
        classification, decision, agent, context, task_match
    )

    # Callers with no conversation state keep receiving the raw prompt.
    outgoing = prompt
    if task_match is not None:
        outgoing = execution_prompt(
            prompt,
            task_match.prior_turns,
            fresh=not conversation_state.contexts,
            artifact=task_match.artifact,
            operation=task_match.operation,
        )

    # Run the agent. Config problems propagate (setup issue, not an outcome);
    # genuine execution failures are captured as a failed outcome so the CLI keeps
    # running and the failure is still learnable.
    start = perf_counter()
    try:
        chosen_model = selection.model_id if selection else None
        if chosen_model and chosen_model != getattr(agent, "model_id", None):
            response = agent.run_with_model(
                outgoing, chosen_model, selection.provider, selection.fallback_chain
            )
        else:
            response = agent.run(outgoing)
        response_success = True
    except ConfigurationError:
        raise
    except AgentRouteError as exc:
        response = f"[error] {type(exc).__name__}: {exc}"
        response_success = False
    response = strip_internal_markers(response)
    latency_ms = int((perf_counter() - start) * 1000)

    outcome_score = score_outcome(response_success, latency_ms, feedback)

    observation_id = None
    if memory is not None:
        observation = RoutingObservation(
            intent=intent,
            complexity=complexity,
            confidence=confidence,
            selected_agent=agent_name,
            response_success=response_success,
            latency_ms=latency_ms,
            task_id=make_task_id(prompt),
            policy=decision["policy"],
            user_feedback=feedback,
            outcome_score=outcome_score,
        )
        observation_id = memory.record_observation(observation)

    result = {
        "selected_agent": agent_name,
        "intent": intent,
        "complexity": complexity,
        "confidence": confidence,
        "policy": decision["policy"],
        "decision_layer": decision.get("decision_layer", decision["policy"]),
        "routing_reason": decision["reason"],
        "fallback_used": decision.get("fallback_used", False),
        # Why the decision layer degraded, when it did. Without this a fallback
        # is invisible except as a changed reason string.
        "laya_error": decision.get("laya_error"),
        "response": response,
        "response_success": response_success,
        "latency_ms": latency_ms,
        "outcome_score": outcome_score,
        "observation_id": observation_id,
    }
    result.update(_routing_fields(profile, selection))

    if conversation_state is not None:
        branch = adopt_context(conversation_state, task_match)
        conversation_state.record(
            prompt=prompt,
            agent=agent_name,
            response=response,
            intent=intent,
            complexity=complexity,
            outcome_score=outcome_score,
            routing_reason=decision["reason"],
            policy=decision["policy"],
            task_context=branch,
            selected_model=selection.model_id if selection else None,
            model_provider=selection.provider if selection else None,
            capability=profile.capability,
            tools=tuple(profile.required_tools),
        )
        fields = task_match.public_fields()
        fields["context_id"] = branch.context_id
        result.update(fields)
    else:
        result.update(empty_context_fields())

    return result


# --- Future extension points ------------------------------------------------
# `route` and `select_agent` contracts are stable seams. Later stages can:
#   * pass a LearnedRoutingPolicy as `policy` (no router change needed)
#   * use `conversation_state.context()` for conversation-aware routing
#   * consume RoutingMemory statistics for agent performance tracking / RL
#   * add multi-agent negotiation / handoff around the single-agent call above
