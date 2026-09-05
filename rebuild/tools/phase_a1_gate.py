from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "firmware" / "main" / "presentation.cpp"
PROBE19 = ROOT / "firmware" / "main" / "probe19.cpp"
CMAKE = ROOT / "firmware" / "main" / "CMakeLists.txt"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def main() -> None:
    presentation = PRESENTATION.read_text(encoding="utf-8")
    probe19 = PROBE19.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    for state in (
        "Booting",
        "Idle",
        "Attentive",
        "Listening",
        "Thinking",
        "Speaking",
        "ToolWorking",
        "Offline",
        "Degraded",
        "Fault",
        "Recovery",
    ):
        require(presentation, f"PresentationState::{state}", f"presentation state {state}")

    require(presentation, "probe8_sync_draw_bitmap", "synchronised LCD path")
    require(presentation, "xTaskCreate(\n        presentation_task", "independent presentation task")
    require(presentation, "PRESENTATION_HEARTBEAT", "presentation heartbeat")
    require(presentation, "action=attention", "purposeful touch action")
    require(presentation, "boot-complete", "boot-to-idle transition")
    require(presentation, "attention-complete", "touch attention recovery")

    require(probe19, '#include "presentation.cpp"', "live presentation include")
    require(probe19, "const bool ok = run_probe19();", "proven runtime baseline")
    require(probe19, "presentation_start(ok)", "presentation startup")
    require(probe19, "p16_execute_pose_command", "proven physical command path")
    require(probe19, "p9_release_torque", "torque release path")
    require(probe19, "PROBE19 status=ack-sent executed=1 torque=released", "post-motion ACK semantics")

    require(cmake, 'SRCS "probe19.cpp"', "current live firmware entry point")

    print(
        "PHASE_A1_GATE PASS states=11 renderer=local touch=attention "
        "presence_task=independent body_path=preserved entry=probe19"
    )


if __name__ == "__main__":
    main()
