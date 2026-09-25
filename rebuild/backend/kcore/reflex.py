"""Cheap, deterministic sensor salience. Proposals only; no action capabilities."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import math
import time
import uuid


MODE = "OBSERVE_ONLY"
EVENT_TYPES = frozenset({"arrival", "departure", "gesture", "close_approach", "session_ended"})
ACTIONS = frozenset({"verify_arrival", "end_visit", "acknowledge_gesture", "attention", "none"})
RESET_REASONS = frozenset({"startup", "stopped", "privacy", "settings_changed", "profile_removed", "device_reconnected", "resume"})
COUNTERS = ("samples", "background", "duplicates", "invalid", "cooldowns", "proposed",
            "arrivals", "departures", "gestures", "approaches")


@dataclass(frozen=True, slots=True)
class ReflexEvent:
    type: str
    timestamp: float
    salience: float
    confidence: float
    source: tuple[str, ...]
    occupancy_session_id: str | None
    suggested_action: str
    perception_required: bool
    reason: str

    def payload(self):
        data = asdict(self)
        data["source"] = list(self.source)
        data["mode"] = MODE
        data["cooldown_key"] = f"{self.type}:{self.occupancy_session_id or 'no_session'}"
        return data


class ReflexController:
    """One occupancy visit survives missing evidence; CLEAR ends it.

    This component receives only validated sensor evidence and occupancy state.
    It has no camera, motion, tool, speech, network or database reference.
    Monotonic sample time governs all windows; wall time is diagnostic only.
    """

    mode = MODE

    def __init__(self, *, wall_clock=time.time):
        self.wall_clock = wall_clock
        self.session_id = None
        self.counts = dict.fromkeys(COUNTERS, 0)
        self.recent = deque(maxlen=120)
        self._last_tof_seq = None
        self._last_gesture_seq = None
        self._range = None
        self._approach_candidate = None
        self._close_latched = False
        self._rearm_since = None
        self._last_event = {}

    def _propose(self, kind, now, score, confidence, source, action, perception, reason):
        cooldown = {"gesture": 3.0, "close_approach": 10.0}.get(kind, 0)
        if now - self._last_event.get(kind, -1e30) < cooldown:
            self.counts["cooldowns"] += 1
            return None
        self._last_event[kind] = now
        event = ReflexEvent(kind, self.wall_clock(), score, confidence, source,
                            self.session_id, action, perception, reason)
        self.recent.append(event)
        self.counts["proposed"] += 1
        counter = {"arrival": "arrivals", "departure": "departures", "gesture": "gestures", "close_approach": "approaches"}.get(kind)
        if counter:
            self.counts[counter] += 1
        return event

    def reset(self, reason, now):
        reason = reason if reason in RESET_REASONS else "settings_changed"
        event = None
        if self.session_id:
            event = self._propose("session_ended", now, .5, 1.0, (), "none", False, reason)
        self.session_id = None
        self._last_tof_seq = self._last_gesture_seq = None
        self._range = self._approach_candidate = self._rearm_since = None
        self._close_latched = False
        self._last_event.clear()
        return (event,) if event else ()

    def observe(self, occupancy, tof, gesture, now):
        self.counts["samples"] += 1
        events = []
        if occupancy == "OCCUPIED" and self.session_id is None:
            self.session_id = str(uuid.uuid4())
            events.append(self._propose("arrival", now, .8, .85, ("tof",), "verify_arrival", True, "confirmed_arrival"))
        elif occupancy == "CLEAR" and self.session_id:
            events.append(self._propose("departure", now, .65, .85, ("tof",), "end_visit", False, "confirmed_departure"))
            self.session_id = None
            self._range = self._approach_candidate = self._rearm_since = None
            self._close_latched = False

        if tof is None or not tof.fresh or not tof.valid:
            self.counts["invalid"] += 1
            self._range = self._approach_candidate = self._rearm_since = None
        elif tof.sequence == self._last_tof_seq:
            self.counts["duplicates"] += 1
        else:
            if self._last_tof_seq is not None and tof.sequence < self._last_tof_seq:
                self._range = self._approach_candidate = self._rearm_since = None
            self._last_tof_seq = tof.sequence
            distance = tof.distance_mm
            previous = self._range
            self._range = (now, distance)
            close = None
            if self.session_id and occupancy == "OCCUPIED":
                if self._close_latched:
                    if distance >= 500:
                        if self._rearm_since is None:
                            self._rearm_since = now
                        elif now - self._rearm_since >= 1:
                            self._close_latched = False
                            self._rearm_since = None
                    else:
                        self._rearm_since = None
                elif self._approach_candidate is not None:
                    age = now - self._approach_candidate
                    if distance <= 350 and .25 <= age <= 2.5:
                        self._close_latched = True
                        close = self._propose("close_approach", now, .9, .8, ("tof",), "attention", True, "abrupt_close_approach")
                        self._approach_candidate = None
                    elif distance > 350 or age > 2.5:
                        self._approach_candidate = None
                elif previous and 0 < now - previous[0] <= 2.5 and previous[1] - distance >= 250 and distance <= 350:
                    self._approach_candidate = now
                if close:
                    events.append(close)
                else:
                    self.counts["background"] += 1
            else:
                self._approach_candidate = None

        if gesture and gesture.fresh:
            sequence = gesture.event_sequence
            if self._last_gesture_seq is None or sequence < self._last_gesture_seq:
                # Establish a baseline after startup/reconnect; never replay cached gestures.
                self._last_gesture_seq = sequence
            elif sequence != self._last_gesture_seq:
                self._last_gesture_seq = sequence
                if gesture.event_age_ms <= 1500 and gesture.flags:
                    events.append(self._propose("gesture", now, .85, .9, ("gesture",), "acknowledge_gesture", True, "deliberate_gesture"))
        return tuple(event for event in events if event is not None)

    def status(self):
        return {"mode": MODE, "occupancy_session_id": self.session_id, **self.counts}


def _session(value):
    if value is None:
        return None
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("Invalid occupancy session")
    return value


def diagnostic_event(value):
    """Allowlist the observation record; never pass arbitrary text to diagnostics."""
    try:
        if not isinstance(value, dict) or value.get("mode") != MODE:
            return None
        kind, action, reason = value.get("type"), value.get("suggested_action"), value.get("reason")
        if kind not in EVENT_TYPES or action not in ACTIONS or reason not in RESET_REASONS | {"confirmed_arrival", "confirmed_departure", "deliberate_gesture", "abrupt_close_approach"}:
            return None
        numbers = [value.get(key) for key in ("timestamp", "salience", "confidence")]
        if any(type(x) not in {int, float} or not math.isfinite(x) for x in numbers):
            return None
        if not 0 <= numbers[0] <= 253402300799 or not all(0 <= x <= 1 for x in numbers[1:]):
            return None
        source = value.get("source")
        if not isinstance(source, (list, tuple)) or len(source) > 2 or any(x not in {"tof", "gesture"} for x in source):
            return None
        if type(value.get("perception_required")) is not bool:
            return None
        return ReflexEvent(kind, *numbers, tuple(source), _session(value.get("occupancy_session_id")),
                           action, value["perception_required"], reason).payload()
    except (ValueError, TypeError, AttributeError):
        return None


def diagnostic_status(value):
    try:
        if not isinstance(value, dict) or value.get("mode") != MODE:
            return None
        if any(type(value.get(key)) is not int or not 0 <= value[key] <= 10**12 for key in COUNTERS):
            return None
        occupancy, health = value.get("occupancy", "UNKNOWN"), value.get("sensor_health", "unavailable")
        if occupancy not in {"UNKNOWN", "CLEAR", "ARRIVAL_CANDIDATE", "OCCUPIED", "DEPARTURE_CANDIDATE"} or health not in {"ready", "unavailable", "invalid_or_stale", "stale"}:
            return None
        return {"mode": MODE, "occupancy_session_id": _session(value.get("occupancy_session_id")),
                "occupancy": occupancy, "sensor_health": health,
                **{key: value[key] for key in COUNTERS}}
    except (ValueError, TypeError, AttributeError):
        return None
