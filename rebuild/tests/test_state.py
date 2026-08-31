import pytest

from kcore.state import Presence, RuntimeState


def test_normal_conversation_cycle():
    state = RuntimeState()
    for target in (Presence.IDLE, Presence.LISTENING, Presence.THINKING, Presence.SPEAKING, Presence.IDLE):
        state.transition(target)
    assert state.presence is Presence.IDLE
    assert state.sequence == 5


def test_invalid_transition_fails_closed():
    state = RuntimeState()
    with pytest.raises(ValueError, match="invalid transition"):
        state.transition(Presence.SPEAKING)
