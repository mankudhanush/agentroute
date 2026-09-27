"""Base agent interface.

An AGENT is the unit the router selects. An agent owns:
  * its model provider and model ID (an implementation detail the router never sees)
  * its in-agent model fallback chain
  * the decision of whether it needs a TOOL, and the invocation of that tool

The router depends only on `name` and `run`. Everything else below is agent-owned
configuration that keeps model/tool concerns out of router.py.
"""

from errors import AgentExecutionError


class BaseAgent:
    # Logical agent identity used by the router and in results.
    name = "BASE_AGENT"
    description = ""
    capabilities = ()
    # Distinct persona/instructions per agent. Two agents can share a model and
    # still behave differently because of this.
    system_prompt = ""

    # Model identity — owned by the agent, invisible to the router.
    model_provider = None
    model_id = None
    fallback_model_ids = ()

    # Tool names this agent is permitted to use (resolved via tools.registry).
    available_tools = ()

    def run(self, prompt: str) -> str:
        """Take a user prompt and return a response string."""
        raise NotImplementedError

    def run_with_model(self, prompt: str, model_id=None, provider=None,
                       fallback_model_ids=None) -> str:
        """Run this agent for ONE request using a selected model.

        The agent still owns its provider and its configured default; the model
        selector may pick a different model within that provider for a single
        request. The override is temporary and always restored, and the agent's
        configured model is kept as the last-resort fallback so a selected model
        the account cannot access still degrades gracefully.
        """
        if model_id is None and provider is None and fallback_model_ids is None:
            return self.run(prompt)

        saved = (self.model_id, self.model_provider, tuple(self.fallback_model_ids))
        try:
            if model_id:
                self.model_id = model_id
            if provider:
                self.model_provider = provider
            def entry_id(entry):
                return entry[0] if isinstance(entry, (tuple, list)) else entry

            merged = [
                e for e in (fallback_model_ids or ())
                if e and entry_id(e) != self.model_id
            ]
            seen = {entry_id(e) for e in merged}
            for candidate in ((saved[0], saved[1]), *saved[2]):
                cid = entry_id(candidate)
                if cid and cid != self.model_id and cid not in seen:
                    merged.append(candidate)
                    seen.add(cid)
            self.fallback_model_ids = tuple(merged)
            return self.run(prompt)
        finally:
            self.model_id, self.model_provider, self.fallback_model_ids = saved

    def describe(self) -> dict:
        """Metadata for the agent registry / CLI display."""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "model_provider": self.model_provider,
            "model_id": self.model_id,
            "fallback_model_ids": list(self.fallback_model_ids),
            "available_tools": list(self.available_tools),
        }

    # --- tool access --------------------------------------------------------
    def get_tool(self, tool_name: str):
        """Resolve a tool this agent is permitted to use.

        Permission is enforced here: an agent can only reach tools listed in its
        own `available_tools`.
        """
        if tool_name not in self.available_tools:
            raise AgentExecutionError(
                f"{self.name} is not permitted to use tool {tool_name!r}."
            )
        from tools.registry import get_tool

        return get_tool(tool_name)

    # --- model access (with in-agent fallback) ------------------------------
    def _complete(self, prompt: str, system: str | None = None) -> str:
        """Call this agent's model, falling back through fallback_model_ids.

        Fallback happens INSIDE the agent: the agent's identity never changes when
        a backup model is used (REASONING_AGENT stays REASONING_AGENT).
        """
        from providers import complete

        # A fallback entry is either "model_id" (same provider) or a
        # (model_id, provider) pair, so a fallback can cross providers - the
        # model id must travel with the endpoint that serves it.
        chain = []
        if self.model_id:
            chain.append((self.model_id, self.model_provider))
        for entry in self.fallback_model_ids:
            if isinstance(entry, (tuple, list)) and entry:
                chain.append((entry[0], (entry[1] if len(entry) > 1 else None)
                              or self.model_provider))
            elif entry:
                chain.append((entry, self.model_provider))

        chain = [(model, prov) for model, prov in chain if model and prov]
        if not chain:
            raise AgentExecutionError(f"{self.name} has no model configured.")

        last_error = None
        for model, model_provider in chain:
            try:
                return complete(model_provider, model, prompt, system=system)
            except AgentExecutionError as exc:
                last_error = exc
                continue
        raise last_error
