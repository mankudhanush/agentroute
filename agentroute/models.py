"""Model registry — maps logical model *roles* to a provider + concrete model ID.

Design rules:
  * Model IDs are NEVER hard-coded inside agent implementation files.
  * Everything is overridable via environment variables.
  * Agents reference a ROLE; provider and model ID both resolve from here.

Provider resolution order for a role:
    1. <ROLE>_MODEL_PROVIDER      (e.g. THREE_D_MODEL_PROVIDER=openrouter)
    2. AGENTROUTE_PROVIDER        (global default)
    3. DEFAULT_PROVIDER           (Step 5: gemini)

A few roles are pinned to one provider because they describe that provider's
catalog (e.g. openrouter/free).
"""

from config import optional_env

# Step 5 default: all agents run on Gemini. OpenRouter/Groq remain fully
# available - set AGENTROUTE_PROVIDER or a per-role override to switch back.
DEFAULT_PROVIDER = "gemini"

# Roles the agents use.
AGENT_ROLES = ("general", "coding", "reasoning", "research", "three_d")

# --- Gemini -----------------------------------------------------------------
# NOTE: these defaults are NOT verified against the live Gemini catalog. Set
# GEMINI_MODEL in your .env to the model you actually have access to.
# The "-latest" aliases were verified callable; concrete gemini-2.5-* ids are
# listed by the API but 404 on some accounts. Override with GEMINI_MODEL.
GEMINI_DEFAULT_MODEL = "gemini-flash-latest"
GEMINI_DEFAULT_FALLBACK = "gemini-flash-lite-latest"

# --- OpenRouter (role -> env var, default model id) -------------------------
_OPENROUTER_ROLES = {
    "general": ("OPENROUTER_GENERAL_MODEL", "google/gemma-4-26b-a4b-it:free"),
    "coding": ("OPENROUTER_CODING_MODEL", "poolside/laguna-s-2.1:free"),
    "reasoning": ("OPENROUTER_REASONING_MODEL", "nvidia/nemotron-3-ultra:free"),
    "reasoning_fallback": (
        "OPENROUTER_REASONING_FALLBACK_MODEL",
        "nvidia/nemotron-3-super:free",
    ),
    "research": ("OPENROUTER_RESEARCH_MODEL", "thinkingmachines/inkling:free"),
    "three_d": ("OPENROUTER_3D_MODEL", "google/gemma-4-26b-a4b-it:free"),
    "fast_agentic": ("OPENROUTER_FAST_MODEL", "nvidia/nemotron-3.5-lightning:free"),
    "dynamic_free_fallback": ("OPENROUTER_FALLBACK_MODEL", "openrouter/free"),
}

# Roles that describe a specific provider's catalog and never follow the default.
_FIXED_PROVIDER_ROLES = {
    "fast_agentic": "openrouter",
    "dynamic_free_fallback": "openrouter",
}

ROLES = tuple(_OPENROUTER_ROLES)

# Every role name the resolver accepts. Passing anything else (for example a
# PROVIDER name like "groq") is a programming error, not a role that should
# silently fall back to the default provider.
KNOWN_ROLES = frozenset(ROLES)


def _require_role(role: str) -> None:
    if role not in KNOWN_ROLES:
        raise ValueError(
            f"Unknown model role {role!r}. Valid roles: "
            f"{', '.join(sorted(KNOWN_ROLES))}. "
            "get_model()/get_provider() take a ROLE, not a provider name - to work "
            "with a provider use providers.py or a <ROLE>_MODEL_PROVIDER override."
        )


def get_provider(role: str) -> str:
    """Resolve which provider serves this role."""
    _require_role(role)
    if role in _FIXED_PROVIDER_ROLES:
        return _FIXED_PROVIDER_ROLES[role]
    per_role = optional_env(f"{role.upper()}_MODEL_PROVIDER")
    if per_role:
        return per_role.strip().lower()
    return (optional_env("AGENTROUTE_PROVIDER", DEFAULT_PROVIDER) or DEFAULT_PROVIDER).lower()


def _gemini_model(role: str) -> str:
    if role.endswith("_fallback"):
        return optional_env("GEMINI_FALLBACK_MODEL", GEMINI_DEFAULT_FALLBACK)
    # Optional per-role override, e.g. GEMINI_CODING_MODEL.
    per_role = optional_env(f"GEMINI_{role.upper()}_MODEL")
    return per_role or optional_env("GEMINI_MODEL", GEMINI_DEFAULT_MODEL)


def model_env_var(role: str) -> str:
    """Name of the env var that controls this role's model (for display/docs)."""
    provider = get_provider(role)
    if provider == "gemini":
        return "GEMINI_FALLBACK_MODEL" if role.endswith("_fallback") else "GEMINI_MODEL"
    if provider == "groq":
        return "GROQ_MODEL"
    if provider == "nvidia":
        return "NVIDIA_MODEL"
    env, _ = _OPENROUTER_ROLES.get(role, ("", None))
    return env


def get_model(role: str):
    """Resolve a role to a concrete model ID for its provider."""
    provider = get_provider(role)
    if provider == "gemini":
        return _gemini_model(role)
    if provider == "groq":
        return optional_env("GROQ_MODEL")
    if provider == "nvidia":
        # No invented default: set NVIDIA_MODEL to pin an agent to NVIDIA.
        # Otherwise the model selector picks NVIDIA models from the registry.
        return optional_env("NVIDIA_MODEL")
    env, default = _OPENROUTER_ROLES.get(role, (None, None))
    return optional_env(env, default) if env else None


def get_fallbacks(role: str) -> list:
    """Same-provider fallback models for this role (used inside the agent).

    Fallbacks always stay on the agent's own provider - mixing providers in one
    fallback chain would send a model ID to the wrong endpoint.
    """
    provider = get_provider(role)
    primary = get_model(role)
    if provider == "gemini":
        fallback = optional_env("GEMINI_FALLBACK_MODEL", GEMINI_DEFAULT_FALLBACK)
        return [fallback] if fallback and fallback != primary else []
    if provider == "openrouter":
        chain = []
        if role == "reasoning":
            chain.append(get_model("reasoning_fallback"))
        chain.append(get_model("dynamic_free_fallback"))
        return [m for m in chain if m and m != primary]
    return []


def catalog() -> dict:
    """Full catalog with resolved provider/model (for display/inspection)."""
    return {
        role: {
            "provider": get_provider(role),
            "env": model_env_var(role),
            "default": _OPENROUTER_ROLES.get(role, (None, None))[1],
            "resolved": get_model(role),
        }
        for role in ROLES
    }


def known_model_ids() -> set:
    """Every non-empty model ID this project knows about (resolved + defaults).

    Used by architectural checks asserting model IDs never leak into the router
    or get treated as agent identities.
    """
    ids = {GEMINI_DEFAULT_MODEL, GEMINI_DEFAULT_FALLBACK}
    try:  # lazy import: model_registry reads this module's catalog()
        from model_registry import curated_model_ids

        ids |= curated_model_ids()
    except ImportError:
        pass
    for role in ROLES:
        resolved = get_model(role)
        if resolved:
            ids.add(resolved)
        default = _OPENROUTER_ROLES.get(role, (None, None))[1]
        if default:
            ids.add(default)
    return ids
