"""Transparent outcome scoring for routing observations.

This does NOT attempt to measure true answer quality. It combines a few
*observable* signals into a single score in [0.0, 1.0] using a simple, documented
formula. A future stage can replace this with a real quality/reward model.

Formula (all constants below are the knobs):

    if the request failed:
        score = 0.0
    else:
        score = BASE_SUCCESS (0.7)
              + latency_bonus  (up to +0.2 for fast responses, 0 for slow)

    then, only if EXPLICIT feedback is present:
        positive feedback -> score + 0.2
        negative feedback -> score - 0.5

    score is clamped to [0.0, 1.0].

If no feedback is provided, it is treated as UNAVAILABLE (None) — never invented.
"""

# Feedback vocabulary (explicit only; absence == unavailable).
FEEDBACK_POSITIVE = "positive"
FEEDBACK_NEGATIVE = "negative"

BASE_SUCCESS = 0.7
BASE_FAILURE = 0.0

MAX_LATENCY_BONUS = 0.2
FAST_LATENCY_MS = 1000   # at/under this, full latency bonus
SLOW_LATENCY_MS = 8000   # at/over this, no latency bonus

FEEDBACK_BONUS = 0.2
FEEDBACK_PENALTY = 0.5


def latency_bonus(latency_ms: int) -> float:
    """Linear bonus: full at FAST_LATENCY_MS, zero at/after SLOW_LATENCY_MS."""
    if latency_ms <= FAST_LATENCY_MS:
        return MAX_LATENCY_BONUS
    if latency_ms >= SLOW_LATENCY_MS:
        return 0.0
    span = SLOW_LATENCY_MS - FAST_LATENCY_MS
    frac = (SLOW_LATENCY_MS - latency_ms) / span
    return round(MAX_LATENCY_BONUS * frac, 3)


def score_outcome(
    response_success: bool,
    latency_ms: int,
    user_feedback: str | None = None,
) -> float:
    """Compute a transparent outcome score in [0.0, 1.0]."""
    if not response_success:
        score = BASE_FAILURE
    else:
        score = BASE_SUCCESS + latency_bonus(latency_ms)

    if user_feedback == FEEDBACK_POSITIVE:
        score += FEEDBACK_BONUS
    elif user_feedback == FEEDBACK_NEGATIVE:
        score -= FEEDBACK_PENALTY
    # any other value (including None) => no adjustment; feedback stays unavailable

    return round(max(0.0, min(1.0, score)), 3)
