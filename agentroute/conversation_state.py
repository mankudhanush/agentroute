"""Lightweight conversation state for AgentRoute.

Records the running history of an interaction and exposes a small `context()`
snapshot that a future conversation-aware routing policy can consume. Step 3 only
records and surfaces this data; the baseline/adaptive policies do not yet depend on
it (adaptive uses RoutingMemory instead).
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Turn:
    prompt: str
    agent: str
    response: str
    # Step 3 additions (optional so old callers using record(prompt, agent,
    # response) keep working unchanged).
    intent: Optional[str] = None
    complexity: Optional[str] = None
    outcome_score: Optional[float] = None
    routing_reason: Optional[str] = None
    policy: Optional[str] = None
    # Filled when a turn is filed under a task context. Absent for older callers.
    context_id: Optional[str] = None
    selected_model: Optional[str] = None
    model_provider: Optional[str] = None
    capability: Optional[str] = None
    tools: tuple = ()


@dataclass
class ConversationState:
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    turns: list = field(default_factory=list)
    # Task branches inside this conversation. Routing does not own these.
    contexts: list = field(default_factory=list)
    _revision: int = 0

    def record(
        self,
        prompt: str,
        agent: str,
        response: str,
        intent: Optional[str] = None,
        complexity: Optional[str] = None,
        outcome_score: Optional[float] = None,
        routing_reason: Optional[str] = None,
        policy: Optional[str] = None,
        task_context=None,
        selected_model: Optional[str] = None,
        model_provider: Optional[str] = None,
        capability: Optional[str] = None,
        tools: tuple = (),
    ) -> "Turn":
        """Append one completed exchange to the history (backwards compatible)."""
        turn = Turn(
            prompt=prompt,
            agent=agent,
            response=response,
            intent=intent,
            complexity=complexity,
            outcome_score=outcome_score,
            routing_reason=routing_reason,
            policy=policy,
            context_id=getattr(task_context, "context_id", None),
            selected_model=selected_model,
            model_provider=model_provider,
            capability=capability,
            tools=tuple(tools or ()),
        )
        self.turns.append(turn)
        if task_context is not None:
            self._revision += 1
            task_context.revision = self._revision
            task_context.add_turn(turn)
        return turn

    # --- convenience accessors ---------------------------------------------
    @property
    def prompts(self) -> list:
        return [t.prompt for t in self.turns]

    @property
    def selected_agents(self) -> list:
        return [t.agent for t in self.turns]

    @property
    def responses(self) -> list:
        return [t.response for t in self.turns]

    @property
    def intents(self) -> list:
        return [t.intent for t in self.turns]

    @property
    def outcomes(self) -> list:
        return [t.outcome_score for t in self.turns]

    def last_agent(self) -> Optional[str]:
        return self.turns[-1].agent if self.turns else None

    def recent_decisions(self, n: int = 5) -> list:
        """Return up to the last `n` turns as compact decision dicts."""
        recent = self.turns[-n:]
        return [
            {
                "intent": t.intent,
                "complexity": t.complexity,
                "agent": t.agent,
                "outcome_score": t.outcome_score,
                "policy": t.policy,
            }
            for t in recent
        ]

    def recent_prompts(self, n: int = 2) -> list:
        """The last `n` user prompts, oldest first.

        A follow-up like "now write unit tests for it" is meaningless alone, so
        the decision layer needs the earlier request to resolve what "it" is.
        """
        return [t.prompt for t in self.turns[-n:]]

    def context(self) -> dict:
        """Snapshot passed to routing policies for conversation-aware routing."""
        return {
            "conversation_id": self.conversation_id,
            "previous_intents": self.intents,
            "previous_agents": self.selected_agents,
            "previous_outcomes": self.outcomes,
            "previous_prompts": self.recent_prompts(),
            "recent_decisions": self.recent_decisions(),
            "last_agent": self.last_agent(),
        }
