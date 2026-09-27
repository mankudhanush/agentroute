"""Small configuration helpers.

Keeps environment-variable access in one place so error messages are consistent
and never leak secret values.
"""

import os

from errors import ConfigurationError


def require_env(name: str) -> str:
    """Return the value of env var ``name`` or raise a clean ConfigurationError.

    Never includes the (potentially secret) value in the error message.
    """
    value = os.environ.get(name)
    if not value:
        raise ConfigurationError(
            f"Missing required environment variable: {name}. "
            f"Set it in your .env file (see .env.example / setup.md)."
        )
    return value


def optional_env(name: str, default: str | None = None) -> str | None:
    """Return env var ``name`` if present and non-empty, else ``default``."""
    value = os.environ.get(name)
    return value if value else default
