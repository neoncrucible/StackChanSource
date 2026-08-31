from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Presence(StrEnum):
    BOOTING = "booting"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    OFFLINE = "offline"
    FAULT = "fault"


_ALLOWED: dict[Presence, frozenset[Presence]] = {
    Presence.BOOTING: frozenset({Presence.IDLE, Presence.OFFLINE, Presence.FAULT}),
    Presence.IDLE: frozenset({Presence.LISTENING, Presence.THINKING, Presence.OFFLINE, Presence.FAULT}),
    Presence.LISTENING: frozenset({Presence.THINKING, Presence.IDLE, Presence.OFFLINE, Presence.FAULT}),
    Presence.THINKING: frozenset({Presence.SPEAKING, Presence.IDLE, Presence.OFFLINE, Presence.FAULT}),
    Presence.SPEAKING: frozenset({Presence.LISTENING, Presence.IDLE, Presence.OFFLINE, Presence.FAULT}),
    Presence.OFFLINE: frozenset({Presence.IDLE, Presence.FAULT}),
    Presence.FAULT: frozenset({Presence.BOOTING, Presence.OFFLINE}),
}


@dataclass(slots=True)
class RuntimeState:
    presence: Presence = Presence.BOOTING
    sequence: int = 0

    def transition(self, target: Presence) -> None:
        if target == self.presence:
            return
        if target not in _ALLOWED[self.presence]:
            raise ValueError(f"invalid transition: {self.presence.value} -> {target.value}")
        self.presence = target
        self.sequence += 1
