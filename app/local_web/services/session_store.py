"""In-memory session history for local Sinai chat usage."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Literal


ChatRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatTurn:
    role: ChatRole
    content: str
    timestamp_utc: str

    @classmethod
    def create(cls, role: ChatRole, content: str) -> "ChatTurn":
        return cls(
            role=role,
            content=content,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )


class SessionStore:
    """Simple in-memory chat store keyed by session id."""

    def __init__(self, max_turns: int = 14):
        self.max_messages = max_turns * 2
        self._store: dict[str, deque[ChatTurn]] = defaultdict(
            lambda: deque(maxlen=self.max_messages)
        )
        self._lock = Lock()

    def add_turn(self, session_id: str, role: ChatRole, content: str) -> None:
        with self._lock:
            self._store[session_id].append(ChatTurn.create(role=role, content=content))

    def history(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            turns = list(self._store.get(session_id, []))
        return [
            {"role": turn.role, "content": turn.content, "timestamp_utc": turn.timestamp_utc}
            for turn in turns
        ]

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)

