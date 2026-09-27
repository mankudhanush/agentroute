"""Model registry — structured metadata about the models AgentRoute can use.

HONESTY RULE: capabilities are NOT invented to make routing look clever. Every
field defaults to UNKNOWN, and each profile records where its information came
from in `source`. Only two kinds of claim are made here:

  1. Facts stated by the provider (family membership, multimodality, free tier).
  2. A documented *heuristic tiering* - within one provider's family, the
     lite/flash/pro line is ordered by capability and cost. That ordering is the
     provider's own positioning; it is NOT a benchmark result, and the per-skill
     strengths below remain UNKNOWN precisely because we have not measured them.

`complexity_min/max` follow from the tier and are a DESIGN CHOICE for routing,
not a measured capability ceiling. A model with unknown tier is never excluded.
"""

from dataclasses import dataclass, field
from typing import Optional

UNKNOWN = "unknown"

# Tier ordering within a provider family: 1 = light/fast, 3 = strongest.
TIER_LIGHT = 1
TIER_BALANCED = 2
TIER_STRONG = 3

_GEMINI_SOURCE = (
    "Google Gemini family positioning (lite < flash < pro); model ids verified "
    "live against the Gemini /models endpoint; per-skill strengths unverified"
)
_NVIDIA_SOURCE = (
    "NVIDIA Nemotron family positioning (nano/lightning < super < ultra); model "
    "ids verified live against NVIDIA /v1/models; per-skill strengths unverified"
)
_NVIDIA_CODE_SOURCE = (
    "vendor-stated code model; id verified live against NVIDIA /v1/models; "
    "per-skill strengths unverified"
)
_GROQ_SOURCE = (
    "Groq-hosted open models (OpenAI gpt-oss + Qwen); model ids verified live "
    "against the Groq /openai/v1/models endpoint AND a real chat completion; "
    "tier ordering by parameter scale, per-skill strengths unverified"
)


@dataclass(frozen=True)
class ModelProfile:
    model_id: str
    provider: str
    tier: Optional[int] = None            # None = unknown
    complexity_min: int = 1
    complexity_max: int = 4               # unknown tier => never excluded
    capabilities: frozenset = field(default_factory=frozenset)
    # What the VENDOR built/positions this model for. This is a factual claim
    # about stated purpose, NOT a benchmark result and NOT a measured strength -
    # the *_strength fields below stay UNKNOWN precisely because we have not
    # measured them. Empty means the vendor makes no such claim.
    specializations: frozenset = field(default_factory=frozenset)
    context_tokens: Optional[int] = None  # None = unknown
    tool_support: Optional[bool] = None   # None = unknown
    coding_strength: str = UNKNOWN
    reasoning_strength: str = UNKNOWN
    research_strength: str = UNKNOWN
    creative_strength: str = UNKNOWN
    multimodal: Optional[bool] = None
    speed: Optional[str] = None
    free: Optional[bool] = None
    # "verified"  = a real chat completion succeeded during development
    # "listed"    = the provider lists the id, but calling it was NOT verified
    #               (a listed model can still 404 for a given account)
    # "unknown"   = nothing known
    availability: str = "listed"
    source: str = UNKNOWN

    def covers_complexity(self, level: int) -> bool:
        return self.complexity_min <= level <= self.complexity_max

    def supports_context(self, required_tokens: Optional[int]) -> bool:
        """Unknown capacity never disqualifies a model."""
        if required_tokens is None or self.context_tokens is None:
            return True
        return self.context_tokens >= required_tokens

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "tier": self.tier,
            "complexity_range": [self.complexity_min, self.complexity_max],
            "capabilities": sorted(self.capabilities),
            "specializations": sorted(self.specializations),
            "context_tokens": self.context_tokens,
            "tool_support": self.tool_support,
            "coding_strength": self.coding_strength,
            "reasoning_strength": self.reasoning_strength,
            "research_strength": self.research_strength,
            "creative_strength": self.creative_strength,
            "multimodal": self.multimodal,
            "speed": self.speed,
            "free": self.free,
            "availability": self.availability,
            "source": self.source,
        }

    @property
    def is_verified(self) -> bool:
        return self.availability == "verified"


# General-purpose multimodal families: the capability SET is broad (these are
# general models), while each per-skill STRENGTH stays UNKNOWN.
_GENERAL_CAPS = frozenset({"general", "coding", "reasoning", "research", "creative"})

# Vendor-stated purpose (see ModelProfile.specializations). Only assigned where
# the vendor explicitly positions the model that way; silence stays silence.
_SPEC_REASONING = frozenset({"reasoning"})
_SPEC_CODING = frozenset({"coding"})
_SPEC_REASONING_CODING = frozenset({"reasoning", "coding"})

CURATED_PROFILES = (
    # --- Gemini: VERIFIED callable -------------------------------------
    # NOTE: the concrete gemini-2.5-* ids are listed by the /models endpoint but
    # returned 404 for the development account; the "-latest" aliases worked.
    # Which ids a key can call varies by account - hence `availability`.
    ModelProfile(
        model_id="gemini-flash-latest",
        provider="gemini",
        tier=TIER_BALANCED,
        complexity_min=1,
        complexity_max=3,
        capabilities=_GENERAL_CAPS,
        multimodal=True,
        speed="fast",
        free=True,
        availability="verified",
        source=_GEMINI_SOURCE,
    ),
    ModelProfile(
        model_id="gemini-flash-lite-latest",
        provider="gemini",
        tier=TIER_LIGHT,
        complexity_min=1,
        complexity_max=2,
        capabilities=_GENERAL_CAPS,
        multimodal=True,
        speed="fast",
        free=True,
        availability="verified",
        source=_GEMINI_SOURCE,
    ),
    ModelProfile(
        model_id="gemini-2.5-pro",
        provider="gemini",
        tier=TIER_STRONG,
        complexity_min=2,
        complexity_max=4,
        capabilities=_GENERAL_CAPS,
        specializations=_SPEC_REASONING,  # vendor-positioned "thinking" model
        multimodal=True,
        speed="balanced",
        free=False,
        source=_GEMINI_SOURCE,
    ),
    ModelProfile(
        model_id="gemini-2.5-flash",
        provider="gemini",
        tier=TIER_BALANCED,
        complexity_min=1,
        complexity_max=3,
        capabilities=_GENERAL_CAPS,
        multimodal=True,
        speed="fast",
        free=True,
        source=_GEMINI_SOURCE,
    ),
    ModelProfile(
        model_id="gemini-2.5-flash-lite",
        provider="gemini",
        tier=TIER_LIGHT,
        complexity_min=1,
        complexity_max=2,
        capabilities=_GENERAL_CAPS,
        multimodal=True,
        speed="fast",
        free=True,
        source=_GEMINI_SOURCE,
    ),
    ModelProfile(
        model_id="gemini-2.0-flash",
        provider="gemini",
        tier=TIER_LIGHT,
        complexity_min=1,
        complexity_max=2,
        capabilities=_GENERAL_CAPS,
        multimodal=True,
        speed="fast",
        free=True,
        source=_GEMINI_SOURCE,
    ),
    # --- NVIDIA NIM ------------------------------------------------------
    # General-purpose Nemotron ladder.
    ModelProfile(
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
        provider="nvidia",
        tier=TIER_STRONG,
        complexity_min=2,
        complexity_max=4,
        capabilities=_GENERAL_CAPS,
        specializations=_SPEC_REASONING,  # Nemotron is positioned for reasoning
        speed="slow",
        free=None,
        availability="verified",
        source=_NVIDIA_SOURCE,
    ),
    ModelProfile(
        model_id="nvidia/nemotron-3-super-120b-a12b",
        provider="nvidia",
        tier=TIER_BALANCED,
        complexity_min=1,
        complexity_max=3,
        capabilities=_GENERAL_CAPS,
        specializations=_SPEC_REASONING,  # Nemotron is positioned for reasoning
        speed="balanced",
        availability="verified",
        source=_NVIDIA_SOURCE,
    ),
    ModelProfile(
        model_id="nvidia/nemotron-3.5-lightning-30b-a3b",
        provider="nvidia",
        tier=TIER_LIGHT,
        complexity_min=1,
        complexity_max=2,
        capabilities=_GENERAL_CAPS,
        speed="fast",
        availability="verified",
        source=_NVIDIA_SOURCE,
    ),
    ModelProfile(
        model_id="nvidia/nemotron-nano-3-30b-a3b",
        provider="nvidia",
        tier=TIER_LIGHT,
        complexity_min=1,
        complexity_max=2,
        capabilities=_GENERAL_CAPS,
        speed="fast",
        source=_NVIDIA_SOURCE,
    ),
    # Code specialists: the CAPABILITY SET is narrow because the vendor built
    # these for code. That is a stated purpose, not a benchmark claim.
    ModelProfile(
        model_id="mistralai/codestral-22b-instruct-v0.1",
        provider="nvidia",
        tier=TIER_BALANCED,
        complexity_min=1,
        complexity_max=3,
        capabilities=frozenset({"coding"}),
        specializations=_SPEC_CODING,
        source=_NVIDIA_CODE_SOURCE,
    ),
    ModelProfile(
        model_id="deepseek-ai/deepseek-coder-6.7b-instruct",
        provider="nvidia",
        tier=TIER_LIGHT,
        complexity_min=1,
        complexity_max=2,
        capabilities=frozenset({"coding"}),
        specializations=_SPEC_CODING,
        speed="fast",
        source=_NVIDIA_CODE_SOURCE,
    ),
    # --- Groq: VERIFIED callable ----------------------------------------
    # General-purpose open models confirmed callable with the current key via a
    # real chat completion. Only the general/coding/reasoning-capable text models
    # are registered; Groq's audio (whisper), TTS (orpheus) and guard/classifier
    # models are deliberately excluded because they are not chat generators.
    # Tier ordering follows parameter scale within the Groq catalog.
    ModelProfile(
        model_id="openai/gpt-oss-20b",
        provider="groq",
        tier=TIER_LIGHT,
        complexity_min=1,
        complexity_max=2,
        capabilities=_GENERAL_CAPS,
        specializations=_SPEC_REASONING_CODING,  # gpt-oss: reasoning + coding
        multimodal=False,
        speed="fast",
        availability="verified",
        source=_GROQ_SOURCE,
    ),
    ModelProfile(
        model_id="qwen/qwen3.8-27b",
        provider="groq",
        tier=TIER_BALANCED,
        complexity_min=1,
        complexity_max=3,
        capabilities=_GENERAL_CAPS,
        specializations=_SPEC_REASONING,  # Qwen3 hybrid "thinking" model
        multimodal=False,
        speed="balanced",
        availability="verified",
        source=_GROQ_SOURCE,
    ),
    ModelProfile(
        model_id="openai/gpt-oss-120b",
        provider="groq",
        tier=TIER_STRONG,
        complexity_min=2,
        complexity_max=4,
        capabilities=_GENERAL_CAPS,
        specializations=_SPEC_REASONING_CODING,  # gpt-oss: reasoning + coding
        multimodal=False,
        speed="balanced",
        availability="verified",
        source=_GROQ_SOURCE,
    ),
)


def curated_model_ids() -> set:
    return {profile.model_id for profile in CURATED_PROFILES}


class ModelRegistry:
    """Holds ModelProfiles, seeded from the curated set plus configured roles."""

    def __init__(self, profiles=None, seed_configured: bool = True):
        self._by_id = {}
        for profile in (CURATED_PROFILES if profiles is None else profiles):
            self.register(profile)
        if seed_configured:
            self._seed_from_configured_roles()

    def _seed_from_configured_roles(self) -> None:
        """Any model the project is configured to use must be selectable.

        Such a model gets an explicitly-unknown profile rather than invented
        metadata, so it is never wrongly excluded (full complexity range).
        """
        from models import catalog

        for info in catalog().values():
            model_id, provider = info.get("resolved"), info.get("provider")
            if model_id and provider and model_id not in self._by_id:
                self.register(
                    ModelProfile(
                        model_id=model_id,
                        provider=provider,
                        source="configured role (metadata unknown)",
                    )
                )

    def register(self, profile: ModelProfile) -> None:
        # First registration wins, so curated metadata beats the unknown stub.
        self._by_id.setdefault(profile.model_id, profile)

    def get(self, model_id: str):
        return self._by_id.get(model_id)

    def all(self) -> list:
        return list(self._by_id.values())

    def for_provider(self, provider: str) -> list:
        return [p for p in self._by_id.values() if p.provider == provider]

    def model_ids(self) -> set:
        return set(self._by_id)


def default_registry() -> ModelRegistry:
    """A registry reflecting the CURRENT environment (models resolve from env)."""
    return ModelRegistry()
