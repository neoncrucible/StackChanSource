from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_MAIN = ROOT / "firmware" / "main"


def require(source: str, needle: str, label: str, failures: list[str]) -> None:
    if needle not in source:
        failures.append(label)


def forbid(source: str, needle: str, label: str, failures: list[str]) -> None:
    if needle in source:
        failures.append(label)


def main() -> int:
    cmake = (FIRMWARE_MAIN / "CMakeLists.txt").read_text(encoding="utf-8")
    probe20 = (FIRMWARE_MAIN / "probe20.cpp").read_text(encoding="utf-8")
    audio = (FIRMWARE_MAIN / "device_audio.cpp").read_text(encoding="utf-8")
    host = (ROOT / "backend" / "kcore" / "host.py").read_text(encoding="utf-8")
    runtime = (ROOT / "backend" / "kcore" / "runtime.py").read_text(encoding="utf-8")

    failures: list[str] = []

    require(cmake, 'SRCS "probe20.cpp"', "firmware-not-on-probe20", failures)
    require(probe20, '#include "probe16.cpp"', "missing-proven-body-baseline", failures)
    require(probe20, '#include "presentation.cpp"', "missing-presentation", failures)
    require(probe20, '#include "presence_engine.cpp"', "missing-presence", failures)
    require(probe20, '#include "device_audio.cpp"', "missing-device-audio", failures)
    require(probe20, "device_audio_execute_command", "audio-command-not-routed", failures)
    require(probe20, "p16_execute_pose_command", "proven-body-route-not-preserved", failures)

    require(audio, '"voice.audio-check"', "missing-versioned-audio-command", failures)
    require(audio, "open_input()", "input-open-not-reused", failures)
    require(audio, "close_input()", "input-close-not-reused", failures)
    require(audio, "open_output()", "output-open-not-reused", failures)
    require(audio, "close_output()", "output-close-not-reused", failures)
    require(audio, "kDeviceAudioReadFrames = 960", "sixty-ms-frame-contract-missing", failures)
    require(audio, "p9_release_torque()", "torque-release-proof-missing", failures)
    require(audio, "p10_verify_torque_released()", "torque-verification-missing", failures)
    forbid(audio, "i2s_new_channel", "duplicate-i2s-owner", failures)
    forbid(audio, "i2c_new_master_bus", "duplicate-i2c-owner", failures)

    require(host, "async def send_voice_audio_check", "host-command-missing", failures)
    require(host, 'Envelope(MessageKind.COMMAND, "voice.audio-check", {})', "host-envelope-missing", failures)
    require(host, 'required = ("ok", "capture", "playback", "handoff", "torque_released")', "host-proof-check-missing", failures)
    require(runtime, "async def send_voice_audio_check", "runtime-command-missing", failures)

    if failures:
        print("PHASE_A3_DEVICE_AUDIO_GATE FAIL " + ",".join(failures))
        return 1

    print(
        "PHASE_A3_DEVICE_AUDIO_GATE PASS "
        "reuse_duplex=1 no_duplicate_io_owner=1 correlated=1 "
        "handoff=1 torque_released=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
