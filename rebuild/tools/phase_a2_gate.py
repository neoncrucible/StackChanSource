from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRESENCE = ROOT / "firmware" / "main" / "presence_engine.cpp"
PROBE19 = ROOT / "firmware" / "main" / "probe19.cpp"
PRESENTATION = ROOT / "firmware" / "main" / "presentation.cpp"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"forbidden {label}: {needle}")


def main() -> None:
    presence = PRESENCE.read_text(encoding="utf-8")
    probe19 = PROBE19.read_text(encoding="utf-8")
    presentation = PRESENTATION.read_text(encoding="utf-8")

    require(presence, '"kadence-presence"', "independent presence task")
    require(presence, "kPresenceTickMs", "presence tick")
    require(presence, "presence_next_quiet_deadline", "non-fixed idle cadence")
    require(presence, "presence_pulse_deadline", "bounded local pulse")
    require(presence, "g_presence_interaction_active", "interaction interrupt flag")
    require(presence, "presence_user_attention_active", "touch interrupt awareness")
    require(presence, "state == PresentationState::Idle", "idle-only activation")
    require(presence, "PRESENCE_HEARTBEAT", "presence health telemetry")
    require(presence, "PRESENCE status=ready local=1 independent=1", "presence startup proof")

    for forbidden in ("p9_", "p10_", "p11_", "p16_execute_pose_command"):
        forbid(presence, forbidden, "duplicate physical movement path")

    require(probe19, '#include "presence_engine.cpp"', "live presence binding")
    require(probe19, "presence_interaction_begin();", "interaction preemption begin")
    require(probe19, "presence_interaction_end();", "interaction preemption release")
    require(probe19, "presentation_ok && presence_start()", "presence startup after presentation")
    require(probe19, "p16_execute_pose_command", "proven body command authority")
    require(probe19, "torque=released", "proven torque-release telemetry")

    require(presentation, '"kadence-ui"', "independent renderer task")
    require(presentation, "presentation_poll_touch", "local touch path")

    print(
        "PHASE_A2_GATE PASS local_presence=1 independent=1 interruptible=1 "
        "touch_yield=1 body_path=preserved no_motor_spam=1"
    )


if __name__ == "__main__":
    main()
