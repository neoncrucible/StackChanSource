from __future__ import annotations

from pathlib import Path

from kcore.body_contract import CONTRACT
from kcore.commands import CommandRejected, PoseCommand, decode_body_command
from kcore.protocol import Envelope, MessageKind

OFFSET_TENTHS = 60


def choose_target(start: int, minimum: int, maximum: int) -> int:
    positive = start + OFFSET_TENTHS
    if positive <= maximum:
        return positive
    negative = start - OFFSET_TENTHS
    if negative >= minimum:
        return negative
    raise AssertionError(f"no bounded target for {start}")


def main() -> None:
    assert CONTRACT.preserve_stored_zero_calibration
    assert CONTRACT.release_torque_after_motion

    for minimum, maximum in (
        (CONTRACT.safe_yaw_min_tenths, CONTRACT.safe_yaw_max_tenths),
        (CONTRACT.safe_pitch_min_tenths, CONTRACT.safe_pitch_max_tenths),
    ):
        for start in range(minimum, maximum + 1):
            target = choose_target(start, minimum, maximum)
            assert minimum <= target <= maximum
            assert abs(target - start) == OFFSET_TENTHS

    valid = Envelope(MessageKind.COMMAND, "body.pose", {"yaw": 120, "pitch": 420})
    assert decode_body_command(valid) == PoseCommand(yaw=120, pitch=420)

    bounded = Envelope(MessageKind.COMMAND, "body.pose", {"yaw": 9999, "pitch": -9999})
    assert decode_body_command(bounded) == PoseCommand(
        yaw=CONTRACT.safe_yaw_max_tenths,
        pitch=CONTRACT.safe_pitch_min_tenths,
    )

    rejected = (
        Envelope(MessageKind.EVENT, "body.pose", {"yaw": 0, "pitch": 400}),
        Envelope(MessageKind.COMMAND, "body.unknown", {"yaw": 0, "pitch": 400}),
        Envelope(MessageKind.COMMAND, "body.pose", {"yaw": True, "pitch": 400}),
        Envelope(MessageKind.COMMAND, "body.pose", {"yaw": 0}),
    )
    for envelope in rejected:
        try:
            decode_body_command(envelope)
        except CommandRejected:
            pass
        else:
            raise AssertionError(f"unsafe command accepted: {envelope}")

    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "rebuild/firmware/main/probe11.cpp").read_text(encoding="utf-8")
    command_source = (repo_root / "rebuild/backend/kcore/commands.py").read_text(encoding="utf-8")

    required = (
        '"body.pose"',
        'command_contract=ready',
        'zero_unchanged=1',
        'torque=released',
        'p11_protocol_self_test',
        'p11_ramp_dual',
    )
    for token in required:
        assert token in source, f"checkpoint marker missing: {token}"

    assert 'body.pose' in command_source
    forbidden = (
        "nvs_set_",
        "setCurrentAngleAsZero",
        "resetZeroCalibration",
        "NVS_READWRITE",
    )
    for token in forbidden:
        assert token not in source, f"forbidden calibration mutation token: {token}"

    print("CHECKPOINT11_HOST_GATE PASS")


if __name__ == "__main__":
    main()
