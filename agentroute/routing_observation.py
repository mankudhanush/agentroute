"""Structured record of a single routing decision + its observed outcome.

This is the atomic unit that routing memory stores and that a future learned
policy will train on. It captures *observable* signals only.

DATA-SAFETY (see also section 11 of the Step 3 spec):
  * We DO NOT store the raw prompt. Instead we store `task_id`, a short SHA-256
    hash of the prompt, so repeated/similar tasks can be correlated without
    permanently retaining user text.
  * We NEVER store API keys, auth headers, or raw API responses.
"""

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Optional


def make_task_id(prompt: str) -> str:
    """Return a short, stable, non-reversible identifier for a prompt.

    A SHA-256 hash truncated to 16 hex chars. This is a task *fingerprint*, not
    the prompt itself — the raw text is deliberately not persisted.
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


@dataclass
class RoutingObservation:
    # --- what was asked / decided ---
    intent: str
    complexity: str
    confidence: float
    selected_agent: str
    # --- how it went ---
    response_success: bool
    latency_ms: int
    # --- identity / provenance (no raw prompt, no secrets) ---
    task_id: str = ""
    timestamp: float = field(default_factory=time.time)
    policy: Optional[str] = None
    # --- feedback / scoring (may legitimately be absent) ---
    user_feedback: Optional[str] = None  # "positive" | "negative" | None
    outcome_score: Optional[float] = None
    # --- assigned by routing memory after persistence ---
    id: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)
