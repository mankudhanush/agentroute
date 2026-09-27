"""Model provider layer — OpenAI-SDK clients for Gemini, OpenRouter and Groq.

Providers are an implementation detail of AGENTS. The router, the classifier and
the UI never import this module directly for model calls.

All three providers speak the OpenAI-compatible API; only base_url and the key
env var differ. Gemini is reached through Google's official OpenAI-compatible
endpoint, so no extra SDK dependency is required. Swapping in google-genai would
be a change confined to this file.
"""

import logging

import httpx

from config import optional_env, require_env
from errors import AgentExecutionError, ConfigurationError

logger = logging.getLogger("agentroute.providers")

# A non-streaming completion sends no bytes until the model finishes. Without a
# read limit the SDK waits 10 minutes, and then retries, so one stalled model
# blocks the whole request. The agent already walks its fallback chain.
_CALL_TIMEOUT = httpx.Timeout(90.0, connect=10.0)

_ENDPOINTS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    # NVIDIA NIM hosted inference - OpenAI-compatible, Bearer auth with an
    # nvapi- key. Verified live against GET /v1/models.
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
}
_KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
}
DISPLAY_NAMES = {
    "gemini": "Gemini",
    "nvidia": "NVIDIA",
    "openrouter": "OpenRouter",
    "groq": "Groq",
}

# Maps SDK exception class names to user-facing hints. Never includes secrets.
_FRIENDLY_HINTS = {
    "AuthenticationError": "the API key was rejected",
    "PermissionDeniedError": "the API key lacks access to this model",
    "NotFoundError": "the configured model was not found",
    "BadRequestError": "the request was rejected (check the model name)",
    "RateLimitError": "rate limit or quota exceeded",
    "APITimeoutError": "the request timed out",
    "APIConnectionError": "could not reach the provider",
    "InternalServerError": "the provider reported a server error",
}


def supported_providers() -> list:
    return sorted(_ENDPOINTS)


def display_name(provider: str) -> str:
    return DISPLAY_NAMES.get((provider or "").lower(), provider or "unknown")


def key_env_var(provider: str) -> str:
    return _KEY_ENV.get((provider or "").lower(), "")


def is_configured(provider: str) -> bool:
    """Whether this provider has a key present. Never reveals the value."""
    env = _KEY_ENV.get((provider or "").lower())
    return bool(env and optional_env(env))


def available_providers() -> set:
    """Providers whose credentials are present. Used for availability filtering.

    Presence of a key is not proof of access - a provider can still reject the
    request at call time, which the model fallback chain handles.
    """
    return {name for name in _ENDPOINTS if is_configured(name)}


def get_client(provider: str):
    """Build an OpenAI-SDK client for the given provider.

    Validates configuration BEFORE importing openai so a missing key produces a
    clean ConfigurationError even when the package is not installed.
    """
    provider = (provider or "").lower()
    if provider not in _ENDPOINTS:
        raise ConfigurationError(
            f"Unknown model provider: {provider!r}. "
            f"Supported: {', '.join(supported_providers())}"
        )
    api_key = require_env(_KEY_ENV[provider])

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ConfigurationError(
            "The 'openai' package is required for model calls. "
            "Run: pip install -r requirements.txt"
        ) from exc

    headers = {}
    if provider == "openrouter":
        referer = optional_env("OPENROUTER_SITE_URL")
        title = optional_env("OPENROUTER_APP_NAME", "AgentRoute")
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

    return OpenAI(
        base_url=_ENDPOINTS[provider],
        api_key=api_key,
        default_headers=headers or None,
        timeout=_CALL_TIMEOUT,
        max_retries=0,
    )


def complete(provider: str, model: str, prompt: str, system: str | None = None) -> str:
    """One chat completion. Errors are normalised and never leak credentials."""
    logger.info("calling %s model %s", provider, model)
    client = get_client(provider)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        completion = client.chat.completions.create(model=model, messages=messages)
        return completion.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001 - sanitised, typed error
        kind = type(exc).__name__
        hint = _FRIENDLY_HINTS.get(kind)
        detail = f"{kind} - {hint}" if hint else kind
        raise AgentExecutionError(
            f"{display_name(provider)} request failed for model {model!r}: {detail}"
        ) from exc
