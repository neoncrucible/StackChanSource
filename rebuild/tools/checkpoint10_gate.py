from __future__ import annotations

from pathlib import Path

from kcore.body_contract import CONTRACT

OFFSET_TENTHS = 80


def choose_target(start: int) -> int:
    positive = start + OFFSET_TENTHS
    if positive <= CONTRACT.safe_pitch_max_tenths:
        return positive
    negative = start - OFFSET_TENTHS
    if negative >= CONTRACT.safe_pitch_min_tenths:
        return negative
    raise AssertionError(f"no bounded target for {start}")


def main() -> None:
    assert CONTRACT.preserve_stored_zero_calibration
    assert CONTRACT.release_torque_after_motion
    assert OFFSET_TENTHS > 0
    assert OFFSET_TENTHS <= (
        CONTRACT.safe_pitch_max_tenths - CONTRACT.safe_pitch_min_tenths
    )

    for start in range(
        CONTRACT.safe_pitch_min_tenths,
        CONTRACT.safe_pitch_max_tenths + 1,
    ):
        target = choose_target(start)
        assert CONTRACT.safe_pitch_min_tenths <= target <= CONTRACT.safe_pitch_max_tenths
        assert abs(target - start) == OFFSET_TENTHS

    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "rebuild/firmware/main/probe10.cpp").read_text(encoding="utf-8")

    assert 'NVS_READONLY' in source
    assert 'zero_pos_1' in source and 'zero_pos_2' in source
    assert 'zero_unchanged=1' in source
    assert 'torque=released' in source

    forbidden = (
        "nvs_set_",
        "setCurrentAngleAsZero",
        "resetZeroCalibration",
        "NVS_READWRITE",
    )
    for token in forbidden:
        assert token not in source, f"forbidden calibration mutation token: {token}"

    print("CHECKPOINT10_HOST_GATE PASS")


if __name__ == "__main__":
    main()
