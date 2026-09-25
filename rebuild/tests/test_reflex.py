"""Replay sensor histories, including cached packets and missing evidence."""
from kcore.reflex import ReflexController, diagnostic_event, diagnostic_status
from kcore.sensor_sampler import SensorSampler
from kcore.sensors import GestureStatus, TofStatus


def tof(seq, distance=600, *, age=0, valid=True):
    return TofStatus("ready", seq, age, 0, 9, valid, distance if valid else None)


def gesture(seq, *, age=0, flags=1):
    return GestureStatus("ready", max(1, seq), 0, seq, age, flags)


class Replay:
    def __init__(self):
        self.now = 0.0
        self.emitted = []
        self.sampler = SensorSampler(lambda *args: self.emitted.append(args), clock=lambda: self.now)

    def sample(self, when, sample, event=None):
        self.now = when
        return self.sampler.sample(sample, event)

    def arrive(self):
        self.sample(0, tof(1), gesture(0))
        self.sample(1, tof(2), gesture(0))
        return self.sample(2, tof(3), gesture(0))


def test_thirty_minutes_of_ordinary_desk_motion_proposes_one_arrival():
    r = Replay()
    proposals = list(r.arrive().events)
    session = r.sampler.reflex.session_id
    for second in range(3, 1803):
        sample = tof(second + 1, 600 + (second % 11 - 5) * 12)
        proposals.extend(r.sample(second, sample, gesture(0)).events)
        # Reading the same cached sensor packet is not new evidence.
        proposals.extend(r.sample(second + .1, sample, gesture(0)).events)
    assert [e.type for e in proposals] == ["arrival"]
    assert r.sampler.reflex.session_id == session
    assert r.sampler.reflex.counts["background"] >= 1800
    assert r.sampler.reflex.counts["duplicates"] == 1800
    assert [name for name, _ in r.emitted].count("reflex_event") == 1


def test_confirmed_departure_closes_session_and_real_reentry_creates_another():
    r = Replay(); arrival = r.arrive().events[0]
    assert not r.sample(3, tof(4, 1500)).events
    assert not r.sample(5, tof(5, 1500)).events
    ended = r.sample(7, tof(6, 1500)).events
    assert len(ended) == 1 and ended[0].type == "departure"
    assert ended[0].occupancy_session_id == arrival.occupancy_session_id
    assert r.sampler.reflex.session_id is None
    assert not r.sample(8, tof(7)).events
    new = r.sample(10, tof(8)).events
    assert new[0].type == "arrival"
    assert new[0].occupancy_session_id != arrival.occupancy_session_id


def test_unknown_stale_invalid_and_sequence_reset_never_invent_a_departure():
    r = Replay(); r.arrive()
    session = r.sampler.reflex.session_id
    for when, sample in [(3, None), (4, tof(4, age=4000)), (5, tof(5, valid=False)),
                         (6, tof(1)), (8, tof(2)), (9, tof(3, 1500)),
                         (10, tof(4)), (12, tof(5))]:
        assert not r.sample(when, sample).events
        assert r.sampler.reflex.session_id == session
    assert r.sampler.occupancy.state == "OCCUPIED"
    assert r.sampler.reflex.counts["arrivals"] == 1
    assert r.sampler.reflex.counts["departures"] == 0


def test_initial_presence_requires_distinct_samples_and_hysteresis():
    r = Replay()
    assert not r.sample(0, tof(1)).events
    assert not r.sample(2, tof(1)).events
    assert not r.sample(2.1, tof(2, 1000)).events
    assert r.sample(3, tof(3)).events[0].type == "arrival"


def test_gestures_are_not_replayed_and_cooldowns_apply_only_to_new_events():
    r = Replay(); r.arrive()
    first = r.sample(3, tof(4), gesture(1)).events
    assert [e.type for e in first] == ["gesture"]
    assert not r.sample(3.5, tof(5), gesture(1)).events
    assert not r.sample(4, tof(6), gesture(2)).events
    assert not r.sample(7, tof(7), gesture(2)).events
    assert not r.sample(8, tof(8), gesture(3, age=2000)).events
    assert not r.sample(9, tof(9), gesture(4, flags=0)).events
    assert not r.sample(10, tof(10), gesture(1)).events
    assert r.sample(11, tof(11), gesture(2)).events[0].type == "gesture"
    assert r.sampler.reflex.counts["cooldowns"] == 1
    assert r.sampler.reflex.counts["arrivals"] == 1


def test_gesture_evidence_survives_tof_failure_without_claiming_occupancy():
    r = Replay()
    r.sample(0, None, gesture(10))
    proposal = r.sample(1, None, gesture(11)).events[0]
    assert proposal.type == "gesture" and proposal.occupancy_session_id is None
    assert r.sampler.occupancy.state == "UNKNOWN"


def test_close_approach_requires_confirmation_then_rearm_and_cooldown():
    r = Replay(); r.arrive()
    assert not r.sample(3, tof(4, 250)).events
    # A one-packet range spike must not generate a proposal.
    assert not r.sample(4, tof(5, 600)).events
    assert not r.sample(5, tof(6, 250)).events
    proposal = r.sample(6, tof(7, 260)).events[0]
    assert proposal.type == "close_approach" and proposal.suggested_action == "attention"
    assert proposal.source == ("tof",)  # No invented left/right direction.
    for second in range(7, 12):
        assert not r.sample(second, tof(second + 1, 260)).events
    r.sample(12, tof(13, 600)); r.sample(13, tof(14, 600))
    assert not r.sample(14, tof(15, 250)).events
    assert not r.sample(15, tof(16, 250)).events
    assert r.sampler.reflex.counts["cooldowns"] == 1
    r.sample(16, tof(17, 600)); r.sample(17, tof(18, 600))
    r.sample(18, tof(19, 250))
    assert r.sample(19, tof(20, 250)).events[0].type == "close_approach"


def test_approach_does_not_compare_range_across_missing_data_or_device_reset():
    r = Replay(); r.arrive()
    r.sample(3, None)
    assert not r.sample(4, tof(4, 250)).events
    assert not r.sample(6, tof(5, 250)).events
    r.sample(7, tof(6, 600))
    assert not r.sample(8, tof(1, 250)).events
    assert not r.sample(10, tof(2, 250)).events
    assert r.sampler.reflex.counts["approaches"] == 0


def test_reset_ends_occupancy_session_explicitly_without_a_false_departure():
    r = Replay(); r.arrive()
    session = r.sampler.reflex.session_id
    events = r.sampler.reset("device_reconnected")
    assert events[0].type == "session_ended" and events[0].reason == "device_reconnected"
    assert events[0].occupancy_session_id == session
    assert r.sampler.occupancy.state == "UNKNOWN"
    assert r.sampler.reflex.session_id is None
    assert r.sampler.reflex.counts["departures"] == 0
    assert r.sampler.reset("privacy") == ()


def test_proposal_history_is_bounded_and_exports_only_fixed_metadata():
    reflex = ReflexController(wall_clock=lambda: 1000)
    reflex.observe("UNKNOWN", None, gesture(0), 0)
    for index in range(1, 501):
        reflex.observe("UNKNOWN", None, gesture(index), index * 4)
    assert len(reflex.recent) == 120
    assert reflex.counts["gestures"] == 500
    raw = reflex.recent[-1].payload()
    raw.update(name="private name", prompt="secret prompt", embedding=[1], cooldown_key="secret")
    clean = diagnostic_event(raw)
    assert clean and "private" not in str(clean) and "secret" not in str(clean)
    assert diagnostic_status({**reflex.status(), "credential": "secret"}) == {
        **reflex.status(), "occupancy": "UNKNOWN", "sensor_health": "unavailable"}
    assert diagnostic_event({**raw, "salience": float("nan")}) is None
    assert diagnostic_event({**raw, "source": ["secret"]}) is None
    assert diagnostic_status({**reflex.status(), "occupancy_session_id": "private-name"}) is None
