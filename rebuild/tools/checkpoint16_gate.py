from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
FIRMWARE = ROOT / "firmware" / "main" / "probe16.cpp"
MAIN_CMAKE = ROOT / "firmware" / "main" / "CMakeLists.txt"
PROJECT_CMAKE = ROOT / "firmware" / "CMakeLists.txt"


def require(text: str, marker: str) -> None:
    if marker not in text:
        raise AssertionError(f"missing checkpoint16 marker: {marker}")


def forbid(text: str, marker: str) -> None:
    if marker in text:
        raise AssertionError(f"forbidden checkpoint16 token: {marker}")


def main() -> None:
    source = FIRMWARE.read_text(encoding="utf-8")
    main_cmake = MAIN_CMAKE.read_text(encoding="utf-8")
    project_cmake = PROJECT_CMAKE.read_text(encoding="utf-8")

    for marker in (
        "p16_extract_request_id",
        "p16_make_ack",
        "p16_execute_pose_command",
        "p16_ack_valid",
        "p11_decode_pose(raw, &target)",
        "p10_load_zero_read_only",
        "p9_enable_primary_torque",
        "p10_enable_active_torque",
        "p11_ramp_dual",
        "p11_wait_dual",
        "p9_release_torque",
        "p10_verify_torque_released",
        "yaw_zero_before != yaw_zero_after",
        "pitch_zero_before != pitch_zero_after",
        '"executed"',
        '"torque_released"',
        "ack_after_execute=1",
        "preserve_zero=1",
        "torque=released",
        "one_shot=1",
    ):
        require(source, marker)

    # The successful ACK must be constructed only after execution, settle,
    # torque release and read-only calibration verification.
    execute_pos = source.index("bool p16_execute_pose_command")
    execute_end = source.index("bool p16_ack_valid", execute_pos)
    execute_body = source[execute_pos:execute_end]
    release_pos = execute_body.index("p9_release_torque()")
    zero_after_pos = execute_body.index("yaw_zero_after")
    ack_pos = execute_body.rindex("p16_make_ack")
    if not (release_pos < zero_after_pos < ack_pos):
        raise AssertionError("ACK is not gated behind release and zero verification")

    # Calibration is read-only in this checkpoint.
    for token in (
        "nvs_set_",
        "NVS_READWRITE",
        "setCurrentAngleAsZero",
        "resetZeroCalibration",
    ):
        forbid(source, token)

    if 'SRCS "probe16.cpp"' not in main_cmake:
        raise AssertionError("checkpoint16 firmware is not routed")
    if 'PROJECT_VER "0.16.0"' not in project_cmake:
        raise AssertionError("checkpoint16 firmware version is not selected")

    print("CHECKPOINT16_HOST_GATE PASS")


if __name__ == "__main__":
    main()
