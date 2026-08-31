from kcore.body_contract import CONTRACT
from kcore.body_sim import SimulatedBody


def test_motion_contract_clamps_to_proven_envelope():
    body = SimulatedBody()
    assert body.apply_motion_command(-9999, 9999, 9999) == (-320, 870, 850)
    assert body.apply_motion_command(9999, -9999, 1) == (320, 30, 120)


def test_motion_contract_preserves_calibration_and_releases_torque():
    assert CONTRACT.preserve_stored_zero_calibration is True
    assert CONTRACT.release_torque_after_motion is True


def test_touch_contract_rejects_unknown_gesture():
    body = SimulatedBody()
    try:
        body.touch_event("triple_backflip")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
