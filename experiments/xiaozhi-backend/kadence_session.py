from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Deque, Dict, List, Tuple


class KadenceSessionHistory:
    """Process-lifetime, provider-neutral conversational history for Kadence.

    The store is deliberately volatile: it exists only inside the running
    backend process and is keyed by the robot's stable device id. Restarting the
    backend destroys every retained exchange by construction.
    """

    def __init__(self, max_exchanges: int = 8, max_chars: int = 12_000):
        if max_exchanges < 1:
            raise ValueError("max_exchanges must be at least 1")
        if max_chars < 1:
            raise ValueError("max_chars must be at least 1")

        self.max_exchanges = max_exchanges
        self.max_chars = max_chars
        self._sessions: Dict[str, Deque[Tuple[str, str]]] = {}
        self._lock = RLock()

    @staticmethod
    def _normalise_key(session_key: str | None) -> str:
        return (session_key or "").strip()

    @staticmethod
    def _exchange_chars(exchange: Tuple[str, str]) -> int:
        return len(exchange[0]) + len(exchange[1])

    def append_exchange(
        self,
        session_key: str | None,
        user_text: str | None,
        assistant_text: str | None,
    ) -> bool:
        """Retain one completed user/assistant exchange.

        Empty/incomplete turns are ignored. An individual exchange larger than
        the total character budget is also ignored rather than storing a
        truncated half-history that could distort later reference resolution.
        """

        key = self._normalise_key(session_key)
        user = (user_text or "").strip()
        assistant = (assistant_text or "").strip()

        if not key or not user or not assistant:
            return False

        exchange = (user, assistant)
        if self._exchange_chars(exchange) > self.max_chars:
            return False

        with self._lock:
            history = self._sessions.setdefault(key, deque())
            history.append(exchange)

            while len(history) > self.max_exchanges:
                history.popleft()

            while history and sum(self._exchange_chars(item) for item in history) > self.max_chars:
                history.popleft()

            if not history:
                self._sessions.pop(key, None)

        return True

    def get_messages(self, session_key: str | None) -> List[dict[str, str]]:
        """Return a detached generic role/content history for provider requests."""

        key = self._normalise_key(session_key)
        if not key:
            return []

        with self._lock:
            history = list(self._sessions.get(key, ()))

        messages: List[dict[str, str]] = []
        for user, assistant in history:
            messages.append({"role": "user", "content": user})
            messages.append({"role": "assistant", "content": assistant})
        return messages

    def exchange_count(self, session_key: str | None) -> int:
        key = self._normalise_key(session_key)
        if not key:
            return 0
        with self._lock:
            return len(self._sessions.get(key, ()))
