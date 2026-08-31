from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
from typing import Any
from uuid import uuid4

PROTOCOL_VERSION = 1


class MessageKind(StrEnum):
    HELLO = "hello"
    READY = "ready"
    HEARTBEAT = "heartbeat"
    EVENT = "event"
    COMMAND = "command"
    ACK = "ack"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Envelope:
    kind: MessageKind
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    )
    version: int = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": self.version,
            "id": self.request_id,
            "ts": self.timestamp,
            "kind": self.kind.value,
            "name": self.name,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Envelope":
        required = {"v", "id", "ts", "kind", "name", "payload"}
        missing = required.difference(data)
        if missing:
            raise ValueError(f"missing envelope fields: {sorted(missing)}")
        if data["v"] != PROTOCOL_VERSION:
            raise ValueError(f"unsupported protocol version: {data['v']}")
        if not isinstance(data["payload"], dict):
            raise TypeError("payload must be an object")
        return cls(
            version=data["v"],
            request_id=str(data["id"]),
            timestamp=str(data["ts"]),
            kind=MessageKind(data["kind"]),
            name=str(data["name"]),
            payload=data["payload"],
        )

    @classmethod
    def from_json(cls, raw: str) -> "Envelope":
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise TypeError("envelope must be an object")
        return cls.from_dict(parsed)
