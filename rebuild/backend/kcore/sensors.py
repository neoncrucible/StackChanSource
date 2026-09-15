"""Validated discovery and measurement evidence. No action mappings or LLM input."""
from __future__ import annotations

from dataclasses import dataclass

from .device_control import request_device

ADDRESSES = (0x29, 0x44, 0x45, 0x5C, 0x70, 0x73, 0x76, 0x77)
MAX_AGE_MS = 15000


def _uint(value, high=0xFFFFFFFF):
    if type(value) is not int or not 0 <= value <= high:
        raise ValueError("invalid sensor integer")
    return value


def _addresses(mask):
    return tuple(address for bit, address in enumerate(ADDRESSES) if mask & (1 << bit))


@dataclass(frozen=True, slots=True)
class ChannelHealth:
    state: str
    addresses: tuple[int, ...]
    errors: int


@dataclass(frozen=True, slots=True)
class SensorStatus:
    sequence: int
    age_ms: int
    hub_address: int
    hub: str
    hub_errors: int
    upstream_addresses: tuple[int, ...]
    channels: tuple[ChannelHealth, ...]

    @property
    def fresh(self):
        return self.sequence > 0 and self.age_ms <= MAX_AGE_MS

    @classmethod
    def from_payload(cls, p):
        fields = {"ok", "schema", "seq", "age_ms", "hub_address", "hub", "hub_errors", "upstream_mask", "channels"}
        if not isinstance(p, dict) or set(p) != fields or p["ok"] is not True:
            raise ValueError("invalid sensor status fields")
        if type(p["schema"]) is not int or p["schema"] != 1:
            raise ValueError("unsupported sensor schema")
        address = _uint(p["hub_address"], 0x77)
        if address < 0x70 or not isinstance(p["hub"], str) or p["hub"] not in {"starting", "ready", "absent", "fault", "unavailable"}:
            raise ValueError("invalid hub state")
        if not isinstance(p["channels"], list) or len(p["channels"]) != 6:
            raise ValueError("sensor status requires six channels")
        upstream = _uint(p["upstream_mask"], 255)
        channels = []
        for item in p["channels"]:
            if not isinstance(item, dict) or set(item) != {"state", "mask", "errors"}:
                raise ValueError("invalid channel fields")
            state, mask = item["state"], _uint(item["mask"], 255)
            if not isinstance(state, str) or state not in {"ready", "quarantined", "unavailable"}:
                raise ValueError("invalid channel state")
            if (mask and state != "ready") or mask & upstream or address in _addresses(mask):
                raise ValueError("invalid downstream address evidence")
            if p["hub"] != "ready" and state != "unavailable":
                raise ValueError("channel available without hub")
            channels.append(ChannelHealth(state, _addresses(mask), _uint(item["errors"])))
        return cls(_uint(p["seq"]), _uint(p["age_ms"]), address, p["hub"],
                   _uint(p["hub_errors"]), tuple(a for a in _addresses(upstream) if a != address), tuple(channels))


async def read_sensor_status(host, *, timeout=3.0):
    reply = await request_device(host, "sensors.status", timeout=timeout)
    return SensorStatus.from_payload(reply.payload)


@dataclass(frozen=True, slots=True)
class GestureStatus:
    state: str
    sequence: int
    age_ms: int
    event_sequence: int
    event_age_ms: int
    flags: int

    @property
    def fresh(self):
        return self.state == "ready" and self.sequence > 0 and self.age_ms <= 3000

    @property
    def gestures(self):
        names = ("right", "left", "up", "down", "forward", "backward", "clockwise", "anticlockwise", "wave")
        return tuple(name for bit, name in enumerate(names) if self.flags & (1 << bit))

    @classmethod
    def from_payload(cls, p):
        fields = {"ok", "schema", "state", "channel", "address", "seq", "age_ms", "event_seq", "event_age_ms", "flags"}
        if not isinstance(p, dict) or set(p) != fields or p["ok"] is not True:
            raise ValueError("invalid gesture fields")
        if _uint(p["schema"]) != 1 or _uint(p["channel"]) != 0 or _uint(p["address"]) != 0x73:
            raise ValueError("unsupported gesture configuration")
        if not isinstance(p["state"], str) or p["state"] not in {"starting", "ready", "fault", "unavailable"}:
            raise ValueError("invalid gesture state")
        return cls(p["state"], _uint(p["seq"]), _uint(p["age_ms"]), _uint(p["event_seq"]),
                   _uint(p["event_age_ms"]), _uint(p["flags"], 511))


async def read_gesture_status(host, *, timeout=3.0):
    reply = await request_device(host, "sensors.gesture", timeout=timeout)
    return GestureStatus.from_payload(reply.payload)


@dataclass(frozen=True, slots=True)
class TofStatus:
    state: str
    sequence: int
    age_ms: int
    errors: int
    raw_status: int
    valid: bool
    distance_mm: int | None

    @property
    def fresh(self):
        return self.state == "ready" and self.sequence > 0 and self.age_ms <= 3000

    @classmethod
    def from_payload(cls, p):
        fields = {"ok", "schema", "state", "channel", "address", "seq", "age_ms",
                  "errors", "raw_status", "valid", "distance_mm"}
        if not isinstance(p, dict) or set(p) != fields or p["ok"] is not True:
            raise ValueError("invalid ToF fields")
        if _uint(p["schema"]) != 1 or _uint(p["channel"]) != 1 or _uint(p["address"]) != 0x29:
            raise ValueError("unsupported ToF configuration")
        if not isinstance(p["state"], str) or p["state"] not in {"starting", "ready", "fault", "unavailable"}:
            raise ValueError("invalid ToF state")
        seq, raw = _uint(p["seq"]), _uint(p["raw_status"], 31)
        if type(p["valid"]) is not bool:
            raise ValueError("invalid ToF validity")
        distance = p["distance_mm"]
        if p["valid"]:
            if p["state"] != "ready" or seq == 0 or raw != 9 or _uint(distance, 4000) < 40:
                raise ValueError("invalid ToF measurement")
        elif distance is not None:
            raise ValueError("invalid ToF result must not carry a distance")
        return cls(p["state"], seq, _uint(p["age_ms"]), _uint(p["errors"]), raw, p["valid"], distance)


async def read_tof_status(host, *, timeout=3.0):
    reply = await request_device(host, "sensors.tof", timeout=timeout)
    return TofStatus.from_payload(reply.payload)
