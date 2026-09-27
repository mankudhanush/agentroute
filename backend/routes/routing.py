"""Project a router.route() result for the client.

This does not classify, score, or select anything. It copies fields the core
already returned.
"""

# Fields router.route() actually attaches. Anything else stays out of the API.
ROUTE_FIELDS = (
    "response",
    "response_success",
    "selected_agent",
    "intent",
    "complexity",
    "confidence",
    "policy",
    "decision_layer",
    "routing_reason",
    "fallback_used",
    "laya_error",
    "latency_ms",
    "outcome_score",
    "capability",
    "complexity_level",
    "complexity_name",
    "complexity_source",
    "requires_tools",
    "required_tools",
    "context_dependent",
    "output_type",
    "task_profile",
    "selected_model",
    "model_provider",
    "model_reason",
    "matched_capabilities",
    "model_fallbacks",
    "model_tier",
    "context_id",
    "context_continued",
    "context_turns",
    "context_summary",
    "operation",
    "artifact_chars",
    "has_artifact",
)


def project_result(result: dict, conversation_id: str) -> dict:
    body = {"conversation_id": conversation_id}
    for key in ROUTE_FIELDS:
        if key in result:
            body[key] = result[key]
    return body


def project_turn(turn, result: dict | None) -> dict:
    item = {
        "prompt": turn.prompt,
        "response": turn.response,
        "agent": turn.agent,
        "intent": turn.intent,
        "complexity": turn.complexity,
        "routing_reason": turn.routing_reason,
        "policy": turn.policy,
        "outcome_score": turn.outcome_score,
        "routing": None,
    }
    if result is not None:
        item["routing"] = project_result(result, "")
        item["routing"].pop("conversation_id", None)
    return item
