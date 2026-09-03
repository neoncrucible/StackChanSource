from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .body_contract import CONTRACT
from .protocol import Envelope, MessageKind


@dataclass(frozen=True, slots=True)
class PoseCommand:
    yaw: int
    pitch: int


class CommandRejected(ValueError):
    """Raised when a host command is not safe for the body command plane."""


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CommandRejected(f"{key} must be an integer")
    return value


def decode_body_command(envelope: Envelope) -> PoseCommand:
    if envelope.kind is not MessageKind.COMMAND:
        raise CommandRejected("body command requires command envelope")
    if envelope.name != "body.pose":
        raise CommandRejected(f"unsupported body command: {envelope.name}")

    yaw = _require_int(envelope.payload, "yaw")
    pitch = _require_int(envelope.payload, "pitch")
    safe_yaw, safe_pitch, _ = CONTRACT.clamp_motion(
        yaw,
        pitch,
        CONTRACT.default_motion_speed,
    )
    return PoseCommand(yaw=safe_yaw, pitch=safe_pitch)
