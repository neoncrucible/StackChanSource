from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
PROBE19 = ROOT / "firmware" / "main" / "probe19.cpp"
PROBE16 = ROOT / "firmware" / "main" / "probe16.cpp"
DEFAULTS = ROOT / "firmware" / "sdkconfig.defaults"
MAIN_CMAKE = ROOT / "firmware" / "main" / "CMakeLists.txt"
PROJECT_CMAKE = ROOT / "firmware" / "CMakeLists.txt"


def require(text: str, marker: str) -> None:
    if marker not in text:
        raise AssertionError(f"checkpoint19 missing marker: {marker}")


def forbid(text: str, marker: str) -> None:
    if marker in text:
        raise AssertionError(f"checkpoint19 forbidden marker present: {marker}")


def main() -> None:
    p19 = PROBE19.read_text(encoding="utf-8")
    p16 = PROBE16.read_text(encoding="utf-8")
    defaults = DEFAULTS.read_text(encoding="utf-8")
    main_cmake = MAIN_CMAKE.read_text(encoding="utf-8")
    project_cmake = PROJECT_CMAKE.read_text(encoding="utf-8")

    for marker in (
        "CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y",
        "CONFIG_ESP_CONSOLE_SECONDARY_NONE=y",
        "# CONFIG_ESP_CONSOLE_UART_DEFAULT is not set",
        "# CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG is not set",
    ):
        require(defaults, marker)

    for marker in (
        '#include "probe16.cpp"',
        "std::fgets(line, sizeof(line), stdin)",
        "p16_execute_pose_command(line, ack, sizeof(ack))",
        'std::printf("%s\\n", ack)',
        "std::fflush(stdout)",
        "p9_release_torque()",
        "p10_verify_torque_released()",
        "xTaskCreate(",
        "PROBE19 status=ready transport=usb-serial-jtag primary=1 bidirectional=1 torque=released",
        "PROBE19 status=ack-sent executed=1 torque=released",
    ):
        require(p19, marker)

    for marker in (
        "KADE_PROBE16_EMBEDDED",
        "p16_execute_pose_command",
        "p11_wait_dual",
        "p9_release_torque()",
        "p10_verify_torque_released()",
        "return p16_make_ack(request_id, true, ack, ack_size);",
    ):
        require(p16, marker)

    # Success ACK remains downstream of physical completion and torque release.
    execute_pos = p16.index("bool p16_execute_pose_command")
    execute_end = p16.index("bool p16_ack_valid", execute_pos)
    execute_body = p16[execute_pos:execute_end]
    wait_pos = execute_body.index("p11_wait_dual")
    release_pos = execute_body.index("p9_release_torque()", wait_pos)
    ack_pos = execute_body.rindex("p16_make_ack")
    if not (wait_pos < release_pos < ack_pos):
        raise AssertionError("checkpoint19 ACK ordering bypasses physical completion/release")

    # CP19 must not introduce calibration mutation.
    for token in (
        "nvs_set_",
        "NVS_READWRITE",
        "setCurrentAngleAsZero",
        "resetZeroCalibration",
    ):
        forbid(p19, token)

    if 'SRCS "probe19.cpp"' not in main_cmake:
        raise AssertionError("checkpoint19 firmware is not routed")
    if 'PROJECT_VER "0.19.0"' not in project_cmake:
        raise AssertionError("checkpoint19 firmware version is not selected")

    print("CHECKPOINT19_HOST_GATE PASS")


if __name__ == "__main__":
    main()
