from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from kcore.voice_wire import WIRE_FRAME_MS, WIRE_SAMPLE_RATE, _ogg_crc, build_ogg_opus


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate_ogg(data: bytes) -> int:
    offset = 0
    pages = 0
    while offset < len(data):
        require(data[offset : offset + 4] == b"OggS", "missing Ogg page capture pattern")
        require(offset + 27 <= len(data), "truncated Ogg page header")
        segments = data[offset + 26]
        header_end = offset + 27 + segments
        require(header_end <= len(data), "truncated Ogg lacing table")
        payload_bytes = sum(data[offset + 27 : header_end])
        page_end = header_end + payload_bytes
        require(page_end <= len(data), "truncated Ogg payload")

        page = bytearray(data[offset:page_end])
        expected_crc = struct.unpack("<I", page[22:26])[0]
        page[22:26] = b"\x00\x00\x00\x00"
        require(_ogg_crc(bytes(page)) == expected_crc, "Ogg page CRC mismatch")
        pages += 1
        offset = page_end
    require(offset == len(data), "Ogg parser did not consume full container")
    return pages


def main() -> None:
    firmware = (ROOT / "firmware" / "main" / "voice_lan.cpp").read_text(encoding="utf-8")
    playback = (ROOT / "firmware" / "main" / "voice_playback_buffer.cpp").read_text(encoding="utf-8")
    probe = (ROOT / "firmware" / "main" / "probe21.cpp").read_text(encoding="utf-8")
    cmake = (ROOT / "firmware" / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
    project_cmake = (ROOT / "firmware" / "CMakeLists.txt").read_text(encoding="utf-8")
    defaults = (ROOT / "firmware" / "sdkconfig.defaults").read_text(encoding="utf-8")
    partitions = (ROOT / "firmware" / "partitions.csv").read_text(encoding="utf-8")
    manifest = (ROOT / "firmware" / "main" / "idf_component.yml").read_text(encoding="utf-8")
    host = (BACKEND / "kcore" / "host.py").read_text(encoding="utf-8")
    runtime = (BACKEND / "kcore" / "runtime.py").read_text(encoding="utf-8")
    serial = (BACKEND / "kcore" / "serial_transport.py").read_text(encoding="utf-8")
    wire = (BACKEND / "kcore" / "voice_wire.py").read_text(encoding="utf-8")

    require(WIRE_SAMPLE_RATE == 16000, "voice wire sample rate drifted")
    require(WIRE_FRAME_MS == 60, "voice wire frame duration drifted")
    ogg = build_ogg_opus((b"\xf8\xff\xfe", b"\xf8\xff\xfe"))
    pages = validate_ogg(ogg)
    require(pages == 4, "unexpected Ogg page count")
    require(b"OpusHead" in ogg and b"OpusTags" in ogg, "Ogg Opus headers missing")

    require("WIFI_STORAGE_RAM" in firmware, "Wi-Fi credentials are not RAM-only")
    require("ESP_OPUS_ENC_FRAME_DURATION_60_MS" in firmware, "firmware Opus frame duration drifted")
    require("ESP_AUDIO_SAMPLE_RATE_16K" in firmware, "firmware Opus sample rate drifted")
    require("ESP_OPUS_ENC_APPLICATION_VOIP" in firmware, "firmware Opus mode drifted")
    require("voice.turn" in firmware and "voice.turn" in host, "voice.turn protocol missing")
    require("KDV1" in wire and "KDR1" in wire and "KDE1" in wire, "voice wire magic missing")
    require("KADENCE_IDENTITY" in wire, "provider-independent identity missing from wire runtime")
    require("send_voice_turn" in runtime, "runtime voice turn method missing")
    require("async with self._command_lock" in host, "voice/body exclusivity lock missing")
    require("PROBE21 status=ready" in serial, "serial runtime does not recognize Probe21")
    require('SRCS "probe21.cpp"' in cmake, "firmware build is not on Probe21")
    require("esp_wifi" in cmake and "esp_netif" in cmake and "lwip" in cmake,
            "LAN dependencies missing")
    require("esp_psram" in cmake, "PSRAM component dependency missing")
    require("espressif/esp_audio_codec: ~2.4.1" in manifest,
            "Opus codec dependency is not pinned")
    require("run_probe16()" in probe, "Probe21 does not reuse proven body baseline")
    require("run_probe20();" not in probe,
            "Probe21 would start duplicate Probe20 serial reader")
    require("usb_serial_jtag" not in firmware.lower(),
            "raw audio leaked onto COM control implementation")
    require("COM4" not in wire and "serial_transport" not in wire,
            "host voice wire depends on COM control transport")

    require("voice_playback_buffer.cpp" in probe,
            "Probe21 staged playback layer is missing")
    require("#define esp_codec_dev_write voice_lan_buffered_write" in probe,
            "LAN playback writes are not staged")
    require("MALLOC_CAP_SPIRAM" in playback and "kVoicePlaybackPsramBytes" in playback,
            "playback is not backed by PSRAM")
    require("network_during_playback=0" in playback,
            "buffered playback proof marker missing")
    require("open_output()" in playback and "close_output()" in playback,
            "buffer layer does not reuse proven speaker ownership path")

    require("SDKCONFIG" in project_cmake and "kadence-sdkconfig" in project_cmake,
            "firmware config is not isolated from stale local sdkconfig")
    require("CONFIG_PARTITION_TABLE_CUSTOM=y" in defaults,
            "custom partition layout is not selected")
    require("CONFIG_SPIRAM=y" in defaults and "CONFIG_SPIRAM_MODE_QUAD=y" in defaults,
            "CoreS3 quad PSRAM is not enabled")
    require("CONFIG_SPIRAM_USE_MALLOC=y" in defaults,
            "PSRAM is not integrated with the allocator")
    require("factory,    app,  factory, 0x10000,  0x400000" in partitions,
            "factory app partition is not 4 MiB")
    require("ota_0" in partitions and "ota_1" in partitions,
            "future OTA slots are missing")
    require("storage" in partitions and "coredump" in partitions,
            "future storage/coredump partitions are missing")

    print(
        "PHASE_A3_VOICE_WIRE_GATE PASS "
        "opus=60ms ogg=1 ram_wifi=1 control_separate=1 correlated=1 "
        "single_serial_owner=1 provider_independent=1 app_slot=4MiB ota_ready=1 "
        "psram=1 staged_playback=1 network_during_playback=0"
    )


if __name__ == "__main__":
    main()
