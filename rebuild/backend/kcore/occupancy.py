"""Shared ToF occupancy evidence; never visual identity."""

class Occupancy:
    def __init__(self):
        self.state = "UNKNOWN"
        self.health = "unavailable"
        self.sequence = None
        self.since = 0.0
        self.last_sample = None
        self.distance = None

    def update(self, sample, now):
        before = self.state
        if sample is None or not sample.fresh or not sample.valid:
            self.state, self.health = "UNKNOWN", "unavailable" if sample is None else "invalid_or_stale"
            self.since = now
            self.distance = None
            return before != self.state
        if self.last_sample is not None and now-self.last_sample > 4:
            self.state = "UNKNOWN"
            self.since = now
        if self.sequence is not None and sample.sequence < self.sequence:
            self.state = "UNKNOWN"
            self.since = now
        if sample.sequence == self.sequence:
            if self.last_sample is not None and now-self.last_sample > 3:
                self.state, self.health = "UNKNOWN", "stale"
            return before != self.state
        self.sequence, self.last_sample = sample.sequence, now
        self.distance, self.health = sample.distance_mm, "ready"
        near, far = sample.distance_mm <= 900, sample.distance_mm >= 1200
        if self.state == "UNKNOWN":
            if near: self.state, self.since = "ARRIVAL_CANDIDATE", now
            elif far: self.state, self.since = "DEPARTURE_CANDIDATE", now
        elif self.state in {"CLEAR", "DEPARTURE_CANDIDATE"} and near:
            self.state, self.since = "ARRIVAL_CANDIDATE", now
        elif self.state in {"OCCUPIED", "ARRIVAL_CANDIDATE"} and far:
            self.state, self.since = "DEPARTURE_CANDIDATE", now
        elif self.state == "ARRIVAL_CANDIDATE" and near and now-self.since >= 2:
            self.state = "OCCUPIED"
        elif self.state == "DEPARTURE_CANDIDATE" and far and now-self.since >= 4:
            self.state = "CLEAR"
        return before != self.state

