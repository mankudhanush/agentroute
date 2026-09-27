"""Baseline deterministic classifier for AgentRoute (Step 2).

IMPORTANT: This is a *baseline* classifier built from simple, transparent keyword
heuristics. It is NOT machine-learned and does NOT depend on `laya` (or any ML
package). It exists so the routing pipeline works end-to-end today.

A later stage will REPLACE / augment this with a learned routing policy that uses
features, conversation history, and observed agent outcomes. Keep the public
contract stable: `classify(prompt) -> {intent, complexity, confidence}`.

Supported intents:  general | coding | reasoning | blender
Complexity levels:  simple | medium | complex
"""

import re

from errors import ClassifierError

INTENTS = ("general", "coding", "reasoning", "blender", "research")
COMPLEXITIES = ("simple", "medium", "complex")

# Priority order used to break ties when several intents match equally.
# More specialised intents win over more general ones.
_INTENT_PRIORITY = ("blender", "research", "reasoning", "coding", "general")

# --- Transparent keyword heuristics ----------------------------------------
_BLENDER_KEYWORDS = (
    "blender", "bpy", "3d", "3-d", ".blend", ".glb", "mesh", "render a",
    "3d model", "3d scene", "extrude", "vertices", "geometry node",
)
_CODING_KEYWORDS = (
    "function", "write code", "code to", "debug", "bug", "regex", "sql",
    "algorithm", "sort", "unit test", "refactor", "compile", "implement a",
    "write a program", "def ", "class ",
    # web/backend engineering signals
    "api", "authentication", "endpoint", "backend", "fastapi", "flask",
    "django", "database", "microservice", "rest api",
)
_REASONING_KEYWORDS = (
    "architecture", "design", "analyze", "analysis", "evaluate", "compare",
    "trade-off", "tradeoff", "strategy", "reasoning", "pros and cons",
    "multi-agent", "system design", "explain why", "approach to",
)
_RESEARCH_KEYWORDS = (
    "research", "latest approaches", "state of the art", "survey",
    "literature", "find sources", "cite sources", "look up",
    "gather information", "investigate", "recent advances", "references",
)

# Signals that push a request toward higher complexity.
_COMPLEX_SIGNALS = (
    "architecture", "multi-agent", "distributed", "scalable", "optimize",
    "optimization", "complex", "design", "system", "trade-off", "concurrency",
    "framework", "end-to-end", "production", "analyze", "analysis",
)


def _matches(text: str, keyword: str) -> bool:
    """Match a keyword, respecting word boundaries for alphanumeric terms.

    Plain substring matching produced false positives: "api" fired inside
    "capital", routing "What is the capital of Japan?" to coding. Keywords that
    are not purely alphanumeric (".blend", ".glb") keep substring matching,
    since a word boundary before "." would never match.
    """
    if keyword.replace(" ", "").replace("-", "").isalnum():
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
    return keyword in text


def _count_hits(text: str, keywords) -> int:
    return sum(1 for kw in keywords if _matches(text, kw))


def _classify_intent(text: str) -> tuple[str, int]:
    """Return (intent, hit_count) using keyword scoring + priority tie-break."""
    scores = {
        "blender": _count_hits(text, _BLENDER_KEYWORDS),
        "research": _count_hits(text, _RESEARCH_KEYWORDS),
        "reasoning": _count_hits(text, _REASONING_KEYWORDS),
        "coding": _count_hits(text, _CODING_KEYWORDS),
        "general": 0,  # general is the fallback, never keyword-scored
    }
    best_intent = max(
        _INTENT_PRIORITY,
        key=lambda intent: (scores[intent], -_INTENT_PRIORITY.index(intent)),
    )
    if scores[best_intent] == 0:
        return "general", 0
    return best_intent, scores[best_intent]


def _classify_complexity(text: str, intent: str) -> str:
    word_count = len(text.split())
    signal_hits = _count_hits(text, _COMPLEX_SIGNALS)

    # Reasoning requests are inherently at least medium.
    baseline_medium = intent == "reasoning"

    if signal_hits >= 2 or word_count > 25:
        return "complex"
    if signal_hits >= 1 or word_count > 12 or baseline_medium:
        return "medium"
    return "simple"


def _confidence(intent: str, hits: int) -> float:
    if intent == "general" and hits == 0:
        return 0.55  # fallback: we matched nothing specific
    return round(min(0.97, 0.70 + 0.08 * hits), 2)


def classify(prompt: str) -> dict:
    """Classify a prompt into {intent, complexity, confidence}.

    Deterministic and side-effect free. Raises ClassifierError on empty input.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ClassifierError("Classifier received an empty or non-string prompt.")

    text = prompt.lower()
    intent, hits = _classify_intent(text)
    complexity = _classify_complexity(text, intent)
    confidence = _confidence(intent, hits)

    result = {"intent": intent, "complexity": complexity, "confidence": confidence}
    validate_classification(result)
    return result


def validate_classification(result: dict) -> None:
    """Guard the classifier's output schema so the router can trust it."""
    if not isinstance(result, dict):
        raise ClassifierError("Classification must be a dict.")
    if result.get("intent") not in INTENTS:
        raise ClassifierError(f"Invalid intent: {result.get('intent')!r}")
    if result.get("complexity") not in COMPLEXITIES:
        raise ClassifierError(f"Invalid complexity: {result.get('complexity')!r}")
    conf = result.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        raise ClassifierError(f"Invalid confidence: {conf!r}")
