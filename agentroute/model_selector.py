"""Model selector — picks the best-fit MODEL for a TaskProfile.

This is the core differentiator of AgentRoute, so it is deliberately NOT a
complexity-to-tier lookup. It asks one question:

    "Which available model is best suited to execute THIS specific task?"

    TaskProfile -> TaskRequirements -> score every candidate on every relevant
    signal -> best overall fit

Complexity is only ONE signal. It sets a FLOOR on the capability demanded
(`COMPLEXITY_TIER_FLOOR`); depth, breadth, synthesis and output needs can raise
that demand. Consequently:

  * two tasks at the SAME complexity can select DIFFERENT models (a complex
    coding build vs a complex consistency analysis demand different things);
  * two tasks at DIFFERENT complexities can select the SAME model when it is
    genuinely sufficient for both.

Every criterion below is named, weighted and reported in `fit_breakdown`, so a
selection can always be explained. Nothing here names a provider, and model id
ordering is only ever a final determinism guard - never a reason to prefer a
model.

Provider independence: candidates are every registered model whose provider is
available, plus the agent's own configured model. Provider is an OUTCOME of the
model choice, never an input preference.
"""

from dataclasses import dataclass, field
from typing import Optional

from model_registry import ModelProfile, default_registry
from task_profile import (
    CAPABILITY_TOKEN as _CAPABILITY_TOKEN,
    COMPLEXITY_TIER_FLOOR,
    derive_requirements,
    level_name,
)

# Kept as the published name for the complexity FLOOR. Complexity alone never
# decides the model; it only says how weak a model is allowed to be.
REQUIRED_MIN_TIER = COMPLEXITY_TIER_FLOOR

# --- Scoring weights --------------------------------------------------------
# Stated plainly so a selection is auditable. Higher magnitude = stronger say.
W_TIER_RIGHT_SIZED = 4.0      # meets the demand exactly - the efficient choice
W_TIER_ONE_ABOVE = 1.0        # capable, but heavier than this task needs
W_TIER_FAR_ABOVE = -1.0       # wasteful overkill
W_TIER_BELOW_PER_STEP = -4.0  # underpowered for what the task demands
W_TIER_UNKNOWN = 1.0          # unknown capability never disqualifies a model

W_VERIFIED = 6.0              # proven callable; a listed-only id can 404
W_AVAILABILITY_UNKNOWN = -1.0

W_SPECIALIZATION = 3.0        # vendor built this model for what the task needs
W_SPECIALIZATION_FOCUS = 1.0  # and for little else - a tight fit
W_NARROW_CAPABILITY = 2.0     # declares the needed capability and few others

W_FAST_WHEN_LATENCY_SENSITIVE = 1.0
W_SLOW_WHEN_LATENCY_SENSITIVE = -1.0
W_TOOL_SUPPORT_PRESENT = 1.0
W_TOOL_SUPPORT_ABSENT = -2.0
W_LONG_CONTEXT_PRESENT = 1.0

# A model advertising at least this many tokens counts as long-context capable.
LONG_CONTEXT_TOKENS = 100_000

_NARROW_CAPABILITY_MAX = 2
_SPEED_ORDER = {"fast": 0, "balanced": 1, "slow": 2}


@dataclass
class ModelSelection:
    model_id: Optional[str]
    provider: Optional[str]
    reason: str
    matched_capabilities: tuple = ()
    fallback_models: tuple = ()          # model ids, in order
    fallback_chain: tuple = ()           # (model_id, provider) pairs, in order
    candidates_considered: int = 0
    tier: Optional[int] = None
    fit_score: Optional[float] = None
    fit_breakdown: tuple = ()            # ("criterion +N.N", ...) for the winner
    requirements: tuple = ()             # what the task was judged to need
    demand_tier: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "selected_model": self.model_id,
            "provider": self.provider,
            "reason": self.reason,
            "matched_capabilities": list(self.matched_capabilities),
            "fallback_models": list(self.fallback_models),
            "candidates_considered": self.candidates_considered,
            "tier": self.tier,
            "fit_score": self.fit_score,
            "fit_breakdown": list(self.fit_breakdown),
            "requirements": list(self.requirements),
            "demand_tier": self.demand_tier,
        }


@dataclass
class FitResult:
    """One model's suitability for one task, with the reasoning kept."""

    profile: ModelProfile
    score: float = 0.0
    breakdown: list = field(default_factory=list)

    def add(self, criterion: str, points: float) -> None:
        if points:
            self.score += points
            self.breakdown.append(f"{criterion} {points:+.1f}")


def _strategy() -> str:
    """'efficient' (default) picks the best-fitting model; 'pinned' keeps the
    configured model whenever it is a viable candidate (upgrade-only)."""
    from config import optional_env

    return (optional_env("MODEL_SELECTION", "efficient") or "efficient").lower()


def _matched_capabilities(profile: ModelProfile, capability: str) -> tuple:
    token = _CAPABILITY_TOKEN.get(capability)
    if not token or not profile.capabilities:
        return ()
    return (token,) if token in profile.capabilities else ()


def score_fit(profile: ModelProfile, requirements, configured: Optional[str],
              agent_provider: Optional[str]) -> FitResult:
    """Score how well one model suits one task. Pure and side-effect free.

    ``configured`` and ``agent_provider`` are not scoring inputs. Being the
    agent's configured model, or sharing its provider, does not add points.
    """
    del configured, agent_provider
    fit = FitResult(profile=profile)
    demand = requirements.demand_tier

    # 1. Capability demand vs what this model is built to carry.
    if profile.tier is None:
        fit.add("capability unknown", W_TIER_UNKNOWN)
    elif profile.tier == demand:
        fit.add(f"right-sized for demand tier {demand}", W_TIER_RIGHT_SIZED)
    elif profile.tier == demand + 1:
        fit.add("stronger than required", W_TIER_ONE_ABOVE)
    elif profile.tier > demand + 1:
        fit.add("far heavier than required", W_TIER_FAR_ABOVE)
    else:
        short = demand - profile.tier
        fit.add(f"underpowered by {short} tier(s)", W_TIER_BELOW_PER_STEP * short)

    # 2. Can we actually call it? A listed-only id may 404.
    if profile.availability == "verified":
        fit.add("verified callable", W_VERIFIED)
    elif profile.availability == "unknown":
        fit.add("availability unknown", W_AVAILABILITY_UNKNOWN)

    # 3. Built for this kind of work (vendor-stated purpose).
    needed = requirements.needed_specializations
    if needed and profile.specializations:
        if profile.specializations & needed:
            fit.add("built for this kind of task", W_SPECIALIZATION)
            if profile.specializations <= needed:
                fit.add("specialised in exactly this", W_SPECIALIZATION_FOCUS)

    # 4. A model that declares this capability and little else is a tight fit.
    token = requirements.capability_token
    if (token and profile.capabilities and token in profile.capabilities
            and len(profile.capabilities) <= _NARROW_CAPABILITY_MAX):
        fit.add(f"dedicated {token} model", W_NARROW_CAPABILITY)

    # 5. Speed only matters when the task is genuinely latency-sensitive.
    if requirements.latency_sensitive:
        if profile.speed == "fast":
            fit.add("fast, and this task is latency-sensitive",
                    W_FAST_WHEN_LATENCY_SENSITIVE)
        elif profile.speed == "slow":
            fit.add("slow for a latency-sensitive task",
                    W_SLOW_WHEN_LATENCY_SENSITIVE)

    # 6. Tooling. Unknown support never disqualifies; explicit absence hurts.
    if requirements.needs_tools:
        if profile.tool_support is True:
            fit.add("supports tool use", W_TOOL_SUPPORT_PRESENT)
        elif profile.tool_support is False:
            fit.add("cannot use tools", W_TOOL_SUPPORT_ABSENT)

    # 7. Context capacity, when the task actually needs it.
    if (requirements.needs_long_context and profile.context_tokens
            and profile.context_tokens >= LONG_CONTEXT_TOKENS):
        fit.add("large context window", W_LONG_CONTEXT_PRESENT)

    return fit


def _ordering_key(fit: FitResult, requirements):
    """Rank by fit, then by meaningful tie-breakers.

    Model id appears only as the LAST element: a determinism guard so repeated
    runs agree. It is not a requirement signal. No provider-neutral order
    already exists ahead of it, so this guard is unchanged.
    """
    profile = fit.profile
    verified = 0 if profile.availability == "verified" else 1
    # Prefer the lighter model when the fit is otherwise identical.
    tier = profile.tier if profile.tier is not None else requirements.demand_tier
    speed = (_SPEED_ORDER.get(profile.speed, 1)
             if requirements.latency_sensitive else 0)
    return (
        -fit.score,
        verified,
        tier,
        speed,
        profile.model_id,
    )


def select_model(task_profile, agent, registry=None,
                 available_providers=None) -> ModelSelection:
    """Choose the model best suited to executing this task."""
    provider = getattr(agent, "model_provider", None)
    configured = getattr(agent, "model_id", None)

    if not provider or not configured:
        return ModelSelection(
            model_id=configured,
            provider=provider,
            reason="Agent has no model configured; model selection skipped.",
        )

    registry = registry or default_registry()
    requirements = derive_requirements(task_profile)

    # 1. Provider availability. The agent's own provider is always considered,
    #    so behaviour degrades gracefully when nothing else is configured.
    if available_providers is None:
        from providers import available_providers as detect

        available = detect()
    else:
        available = set(available_providers)
    available = available | {provider}

    candidates = [c for c in registry.all() if c.provider in available]
    if configured not in {c.model_id for c in candidates}:
        candidates.append(
            ModelProfile(configured, provider, source="agent default (metadata unknown)")
        )

    level = requirements.complexity_level
    token = requirements.capability_token

    # 2. Hard requirements. A model that cannot cover the task's complexity, or
    #    that declares capabilities and not this one, is not a candidate at all.
    #    Unknown metadata never disqualifies.
    capable = [
        c for c in candidates
        if c.covers_complexity(level)
        and c.supports_context(requirements.required_context_tokens)
    ]
    if token:
        capable = [c for c in capable if not c.capabilities or token in c.capabilities]

    if not capable:
        return ModelSelection(
            model_id=configured,
            provider=provider,
            reason=(
                f"No available model meets this task's requirements "
                f"({requirements.describe()}) at complexity level {level}; "
                f"kept the agent's configured model {configured}."
            ),
            fallback_models=tuple(sorted(c.model_id for c in candidates)),
            candidates_considered=len(candidates),
            requirements=tuple(requirements.describe().split(", ")),
            demand_tier=requirements.demand_tier,
        )

    # 3. Score every surviving candidate on every relevant signal.
    scored = [score_fit(c, requirements, configured, provider) for c in capable]
    ordered = sorted(scored, key=lambda f: _ordering_key(f, requirements))
    best = ordered[0]

    # MODEL_SELECTION=pinned keeps the operator's configured model whenever it
    # is a viable candidate, so selection only ever upgrades.
    if _strategy() == "pinned":
        for fit in ordered:
            if fit.profile.model_id == configured:
                best = fit
                break

    chosen = best.profile

    # Fallbacks carry their provider: a cross-provider fallback is useless if
    # the model id is sent to the wrong endpoint.
    chain = [(f.profile.model_id, f.profile.provider)
             for f in ordered if f.profile.model_id != chosen.model_id]
    if configured != chosen.model_id and configured not in {m for m, _ in chain}:
        chain.append((configured, provider))  # configured model is the safety net

    return ModelSelection(
        model_id=chosen.model_id,
        provider=chosen.provider,
        reason=_reason(chosen, best, configured, provider, requirements),
        matched_capabilities=_matched_capabilities(chosen, requirements.capability),
        fallback_models=tuple(m for m, _ in chain),
        fallback_chain=tuple(chain),
        candidates_considered=len(candidates),
        tier=chosen.tier,
        fit_score=round(best.score, 2),
        fit_breakdown=tuple(best.breakdown),
        requirements=tuple(requirements.describe().split(", ")),
        demand_tier=requirements.demand_tier,
    )


def _reason(chosen, fit, configured, configured_provider, requirements) -> str:
    """Explain the choice in terms of the TASK, not just its complexity number."""
    level = requirements.complexity_level
    tier = "unknown tier" if chosen.tier is None else f"tier {chosen.tier}"
    drivers = ", ".join(fit.breakdown[:3]) or "no distinguishing signal"
    cross = (
        f" It runs on a different provider ({chosen.provider}) than the agent's default."
        if chosen.provider != configured_provider
        else ""
    )
    kept = " It is also the agent's configured model." if chosen.model_id == configured else ""
    return (
        f"{chosen.model_id} ({tier}) is the best fit for this task: it needs "
        f"{requirements.describe()} at complexity level {level} "
        f"({level_name(level)}), which demands tier {requirements.demand_tier}. "
        f"Deciding factors: {drivers}.{cross}{kept}"
    )
