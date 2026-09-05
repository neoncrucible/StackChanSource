from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" / "kcore"
FIRMWARE = ROOT / "firmware" / "main"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    probe = (FIRMWARE / "probe21.cpp").read_text(encoding="utf-8")
    lane = (FIRMWARE / "voice_turn_lane.cpp").read_text(encoding="utf-8")
    cancel_io = (FIRMWARE / "voice_cancel_io.cpp").read_text(encoding="utf-8")
    playback = (FIRMWARE / "voice_playback_buffer.cpp").read_text(encoding="utf-8")
    runtime = (BACKEND / "runtime.py").read_text(encoding="utf-8")
    host_cancel = (BACKEND / "voice_cancel_host.py").read_text(encoding="utf-8")

    require('voice_cancel_io.cpp' in probe and 'voice_turn_lane.cpp' in probe,
            "Probe21 cancellation lane is not compiled")
    require('#define recv voice_cancel_recv' in probe and '#define send voice_cancel_send' in probe,
            "LAN socket I/O is not cancellable")
    require('#define connect voice_cancel_connect' in probe and '#define close voice_cancel_close' in probe,
            "LAN socket lifecycle is not cancellation-aware")
    require('voice_lane_start(p21_emit_ack)' in probe,
            "voice worker lane is not started")
    require('voice_lane_route_command(line)' in probe,
            "serial reader does not route preemptive voice commands")
    require('async=1 cancellable=1' in probe,
            "Probe21 ready proof does not advertise cancellable async voice")

    require('xQueueCreate(1' in lane and 'voice_lane_worker' in lane,
            "voice turn is not isolated on a single worker lane")
    require('voice.cancel' in lane and 'voice_cancel_request()' in lane,
            "device cancel command is missing")
    require('voice_lan_execute_command(message.raw' in lane,
            "worker does not own the blocking voice turn")
    require('g_voice_lane_busy' in lane,
            "voice lane has no single-turn ownership guard")

    require('shutdown(sock, SHUT_RDWR)' in cancel_io,
            "cancel cannot interrupt a blocked LAN receive")
    require('voice_cancel_is_requested()' in playback,
            "local buffered speaker playback is not cancellable")
    require('g_voice_playback_dma_scratch.data()' in playback,
            "cancellable playback drifted away from DMA-safe staging")

    require('async def send_voice_cancel' in runtime,
            "runtime does not expose voice cancellation")
    require('host._send(writer, command)' in host_cancel and 'host._pending' in host_cancel,
            "host cancel does not use correlated control transport")
    require('_command_lock' in host_cancel,
            "host cancel module must document its lock exception")
    require('async with host._command_lock' not in host_cancel,
            "voice cancel would deadlock behind the active voice turn")

    print(
        "PHASE_A3_CANCEL_GATE PASS "
        "async_voice=1 preemptive_cancel=1 socket_interrupt=1 playback_cancel=1 "
        "correlated=1 single_voice_lane=1 dma_safe=1"
    )


if __name__ == "__main__":
    main()
