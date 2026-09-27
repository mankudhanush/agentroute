"""AgentRoute exception hierarchy.

Centralised so every layer (classifier, router, agents) raises typed errors that
the CLI can catch and render cleanly — without ever printing secret values.
"""


class AgentRouteError(Exception):
    """Base class for all AgentRoute errors."""


class ConfigurationError(AgentRouteError):
    """Missing/invalid configuration: absent API keys or model env vars."""


class ClassifierError(AgentRouteError):
    """Classifier produced output that does not meet the expected schema."""


class RoutingDecisionError(AgentRouteError):
    """A decision layer (e.g. Laya) produced an unusable routing decision."""


class AgentExecutionError(AgentRouteError):
    """An agent failed while producing a response (e.g. an upstream API error).

    Messages are intentionally sanitised: we surface the error *type* and agent
    name, never request payloads or credentials.
    """


class BlenderNotFoundError(AgentRouteError):
    """The Blender executable could not be located when execution was attempted."""
