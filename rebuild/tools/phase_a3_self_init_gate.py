from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" / "kcore"
FIRMWARE = ROOT / "firmware" / "main"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    presentation = (FIRMWARE / "presentation.cpp").read_text(encoding="utf-8")
    bridge = (FIRMWARE / "touch_voice_bridge.cpp").read_text(encoding="utf-8")
    probe = (FIRMWARE / "probe21.cpp").read_text(encoding="utf-8")
    lane = (FIRMWARE / "voice_turn_lane.cpp").read_text(encoding="utf-8")
    serial = (BACKEND / "serial_transport.py").read_text(encoding="utf-8")
    runtime = (BACKEND / "runtime.py").read_text(encoding="utf-8")
    live = (ROOT / "tools" / "phase_a3_self_init_live.py").read_text(encoding="utf-8")

    require('std::atomic<uint32_t> g_presentation_touch_action_seq' in presentation,
            "touch action publication is not atomic")
    require('fetch_add(1, std::memory_order_release)' in presentation,
            "deliberate touch press does not publish an action")
    require('presentation_touch_action_sequence()' in presentation,
            "touch action sequence accessor is missing")
    require('action=voice-toggle' in presentation,
            "touch press is not explicitly classified as the voice action")

    require('voice.request' in bridge and 'voice.touch-cancel' in bridge,
            "touch bridge does not emit both voice events")
    require('\\"kind\\":\\"event\\"' in bridge,
            "touch bridge event is not versioned protocol JSON")
    require('g_voice_lane_busy.load()' in bridge,
            "touch policy does not distinguish idle from active voice")
    require('voice_cancel_request()' in bridge,
            "active touch does not request immediate local cancellation")
    require('i2c_' not in bridge.lower(),
            "touch bridge illegally creates a second touch/I2C owner")
    require('presentation_poll_touch' not in bridge,
            "touch bridge illegally polls the physical touch device")
    require('touch_voice_consume_host_event_ack' in bridge,
            "device does not consume host event acknowledgements")

    require('touch_voice_bridge.cpp' in probe,
            "Probe21 does not compile the touch voice bridge")
    require('touch_voice_bridge_start(p21_emit_line)' in probe,
            "Probe21 does not start the touch event bridge")
    require('touch_voice_consume_host_event_ack(line)' in probe,
            "Probe21 serial reader does not consume host event ACKs")
    require('touch-init=1' in probe,
            "Probe21 readiness does not advertise physical initiation")
    require('voice_lane_start(p21_emit_line)' in probe,
            "voice worker no longer shares the serialized emitter")
    require('g_voice_lane_busy' in lane and 'xQueueCreate(1' in lane,
            "single active voice lane invariant drifted")

    require('MessageKind.EVENT' in serial and '_queue_event(incoming)' in serial,
            "serial runtime does not queue device-originated events")
    require('self.host._dispatch(self.session, incoming)' in serial,
            "device events bypass normal host protocol dispatch")
    require('async def next_event' in serial and 'async def next_event' in runtime,
            "runtime event API is missing")
    require('PRESENTATION_TOUCH' not in serial,
            "host is scraping diagnostic touch logs instead of protocol events")

    require('wait_for_device_event(runtime, "voice.request"' in live,
            "live signoff is not physically initiated")
    require('wait_for_device_event(' in live and '"voice.touch-cancel"' in live,
            "live signoff does not require physical cancellation")
    require('process_wire_turn' in live and 'VoiceProviderSettings.from_env()' in live,
            "live signoff does not include a real provider roundtrip")
    require('send_body_pose' in live and 'torque_released' in live,
            "live signoff does not prove physical recovery")
    require('await asyncio.sleep(0.8)' in live,
            "touch cancel test does not wait for local playback to start")

    print(
        "PHASE_A3_SELF_INIT_GATE PASS "
        "touch_owner=single atomic_action=1 device_event=1 host_event_queue=1 "
        "touch_start=1 touch_cancel=1 real_provider_turn=1 single_voice_lane=1"
    )


if __name__ == "__main__":
    main()
