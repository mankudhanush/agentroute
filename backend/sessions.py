"""In-process conversation sessions.

Each session holds the core ConversationState. This module does not classify
prompts or choose models.
"""

import threading

from conversation_state import ConversationState


class Session:
    def __init__(self, state: ConversationState):
        self.state = state
        self.results: list = []
        self.lock = threading.Lock()


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._guard = threading.Lock()

    def get(self, conversation_id: str) -> Session | None:
        with self._guard:
            return self._sessions.get(conversation_id)

    def get_or_create(self, conversation_id: str | None) -> Session:
        with self._guard:
            if conversation_id and conversation_id in self._sessions:
                return self._sessions[conversation_id]
            state = (
                ConversationState(conversation_id=conversation_id)
                if conversation_id
                else ConversationState()
            )
            session = Session(state)
            self._sessions[state.conversation_id] = session
            return session
