"""One cheap input path: validated sensors -> occupancy -> reflex proposals."""
from __future__ import annotations

from dataclasses import dataclass
import time
from .occupancy import Occupancy
from .reflex import ReflexController, ReflexEvent


@dataclass(frozen=True, slots=True)
class SensorObservation:
    occupancy: str
    changed: bool
    events: tuple[ReflexEvent, ...]


class SensorSampler:
    def __init__(self, emit=lambda name, data: None, *, clock=time.monotonic):
        self.clock, self.emit = clock, emit
        self.occupancy = Occupancy()
        self.reflex = ReflexController()
        self._last_publish = -1e30

    def sample(self, tof, gesture=None):
        now = self.clock()
        changed = self.occupancy.update(tof, now)
        events = self.reflex.observe(self.occupancy.state, tof, gesture, now)
        self.publish(events, force=changed)
        return SensorObservation(self.occupancy.state, changed, events)

    def reset(self, reason):
        events = self.reflex.reset(reason, self.clock())
        self.occupancy = Occupancy()
        self.publish(events, force=True)
        return events

    def publish(self, events=(), *, force=False):
        for event in events:
            self.emit("reflex_event", event.payload())
        now = self.clock()
        if force or events or now - self._last_publish >= 2:
            self._last_publish = now
            self.emit("reflex_status", {**self.reflex.status(), "occupancy": self.occupancy.state,
                                       "sensor_health": self.occupancy.health})
