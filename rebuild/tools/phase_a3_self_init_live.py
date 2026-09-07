from __future__ import annotations

import asyncio
import getpass
import math
import os
import re
import socket
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from kcore.config import RuntimeConfig
from kcore.protocol import Envelope, MessageKind
from kcore.runtime import RuntimeBody
from kcore.voice_providers import VoiceProviderSettings
from kcore.voice_wire import process_wire_turn, read_wire_turn, send_wire_error, send_wire_reply

PORT = "COM4"
FULL_CAPTURE_MS = 4800
CANCEL_CAPTURE_MS = 2400
SAMPLE_RATE = 16000
TONE_SECONDS = 20


def config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


def current_wifi_ssid() -> str | None:
    configured = os.environ.get("KADENCE_WIFI_SSID", "").strip()
    if configured:
        return configured
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        match = re.match(r"^\s*SSID\s*:\s*(.+?)\s*$", line)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def wifi_credentials() -> tuple[str, str]:
    ssid = current_wifi_ssid()
    if not ssid:
        ssid = input("Wi-Fi SSID: ").strip()
    if not ssid:
        raise RuntimeError("Wi-Fi SSID was empty")
    password = os.environ.get("KADENCE_WIFI_PASSWORD")
    if password is None:
        password = getpass.getpass("Wi-Fi password (not echoed): ")
    if len(password.encode("utf-8")) > 63:
        raise RuntimeError("Wi-Fi password exceeds 63 UTF-8 bytes")
    return ssid, password


def local_lan_ipv4() -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        address = probe.getsockname()[0]
    finally:
        probe.close()
    if not address or address.startswith("127."):
        raise RuntimeError("could not resolve a non-loopback LAN IPv4 address")
    return address


def synthetic_tone_pcm() -> bytes:
    amplitude = 850
    frequency = 440.0
    samples = bytearray(SAMPLE_RATE * TONE_SECONDS * 2)
    for index in range(SAMPLE_RATE * TONE_SECONDS):
        value = int(amplitude * math.sin(2.0 * math.pi * frequency * index / SAMPLE_RATE))
        struct.pack_into("<h", samples, index * 2, value)
    return bytes(samples)


async def wait_for_device_event(
    runtime: RuntimeBody,
    name: str,
    *,
    timeout: float,
) -> Envelope:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for device event {name}")
        event = await runtime.next_event(timeout=remaining)
        if event.kind is not MessageKind.EVENT:
            continue
        if event.name == name:
            return event
        if event.name.startswith("voice."):
            raise RuntimeError(
                f"unexpected voice event while waiting for {name}: {event.name}"
            )


async def main() -> int:
    settings = VoiceProviderSettings.from_env()
    missing = settings.missing_credentials()
    if missing:
        print("PHASE_A3_SELF_INIT FAIL missing credentials: " + ",".join(missing))
        return 1

    try:
        import miniaudio  # noqa: F401
    except ImportError:
        print("PHASE_A3_SELF_INIT FAIL miniaudio is not installed; refresh the voice extra")
        return 1

    try:
        ssid, password = wifi_credentials()
        host_ip = local_lan_ipv4()
        tone_pcm = synthetic_tone_pcm()
    except Exception as exc:
        print(f"PHASE_A3_SELF_INIT FAIL {type(exc).__name__}: {exc}")
        return 1

    connection_index = 0
    provider_done = asyncio.Event()
    provider_error: Exception | None = None
    provider_transcript = ""
    provider_reply = ""
    tone_sent = asyncio.Event()
    synthetic_error: Exception | None = None

    async def handle_voice(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal connection_index, provider_error, provider_transcript, provider_reply
        nonlocal synthetic_error
        connection_index += 1
        index = connection_index
        try:
            turn = await asyncio.wait_for(read_wire_turn(reader), timeout=15.0)
            if index == 1:
                try:
                    result = await asyncio.wait_for(
                        process_wire_turn(turn, settings=settings),
                        timeout=70.0,
                    )
                    provider_transcript = result.transcript
                    provider_reply = result.reply
                    await send_wire_reply(writer, result.pcm)
                    print(
                        "PHASE_A3_SELF_INIT PROVIDERS PASS "
                        f"transcript_chars={len(result.transcript)} "
                        f"reply_chars={len(result.reply)} pcm_bytes={len(result.pcm)}"
                    )
                except Exception as exc:
                    provider_error = exc
                    try:
                        await send_wire_error(writer, "voice service failure")
                    except Exception:
                        pass
                finally:
                    provider_done.set()
            elif index == 2:
                try:
                    await send_wire_reply(writer, tone_pcm)
                    tone_sent.set()
                    await asyncio.sleep(4.0)
                except Exception as exc:
                    synthetic_error = exc
                    tone_sent.set()
            else:
                raise RuntimeError(f"unexpected extra voice connection: {index}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    server = await asyncio.start_server(handle_voice, "0.0.0.0", 0)
    sockets = server.sockets or []
    if not sockets:
        server.close()
        await server.wait_closed()
        print("PHASE_A3_SELF_INIT FAIL voice server has no listening socket")
        return 1
    server_port = int(sockets[0].getsockname()[1])

    runtime: RuntimeBody | None = None
    first_task: asyncio.Task | None = None
    second_task: asyncio.Task | None = None
    try:
        runtime = await RuntimeBody.open(config(), port=PORT, ready_timeout=30.0)
        print(
            "PHASE_A3_SELF_INIT READY turn 1: touch Kadence once. When her listening "
            "face appears, speak normally and finish within 4.8 seconds."
        )

        request_one = await wait_for_device_event(runtime, "voice.request", timeout=90.0)
        if request_one.payload.get("trigger") != "touch":
            raise RuntimeError("turn 1 was not physically touch initiated")

        first_task = asyncio.create_task(
            runtime.send_voice_turn(
                ssid=ssid,
                password=password,
                host=host_ip,
                port=server_port,
                capture_ms=FULL_CAPTURE_MS,
                timeout=90.0,
            )
        )
        first_ack = await first_task
        await asyncio.wait_for(provider_done.wait(), timeout=3.0)
        if provider_error is not None:
            raise RuntimeError(
                f"real provider turn failed: {type(provider_error).__name__}: {provider_error}"
            ) from provider_error
        if not provider_transcript.strip() or not provider_reply.strip():
            raise RuntimeError("real provider turn did not produce transcript/reply")
        if first_ack.payload.get("ok") is not True:
            raise RuntimeError("touch-initiated real voice turn did not complete")

        print(
            "PHASE_A3_SELF_INIT TURN1 PASS touch_start=1 stt=1 thinker=1 tts=1 "
            "device_speaker=1"
        )
        print(
            "PHASE_A3_SELF_INIT READY turn 2: touch Kadence once to start the cancel "
            "check. No speech is required. When the quiet tone starts, touch her once again."
        )

        request_two = await wait_for_device_event(runtime, "voice.request", timeout=90.0)
        if request_two.payload.get("trigger") != "touch":
            raise RuntimeError("turn 2 was not physically touch initiated")

        second_task = asyncio.create_task(
            runtime.send_voice_turn(
                ssid=ssid,
                password=password,
                host=host_ip,
                port=server_port,
                capture_ms=CANCEL_CAPTURE_MS,
                timeout=40.0,
            )
        )

        await asyncio.wait_for(tone_sent.wait(), timeout=15.0)
        if synthetic_error is not None:
            raise synthetic_error
        # The device buffers the full synthetic reply in PSRAM before opening
        # the speaker. Give that handoff a short deterministic head start so the
        # second physical touch proves cancellation during local playback.
        await asyncio.sleep(0.8)
        print("PHASE_A3_SELF_INIT TOUCH_NOW touch Kadence once while the tone is playing")

        cancel_event = await wait_for_device_event(
            runtime, "voice.touch-cancel", timeout=15.0
        )
        if cancel_event.payload.get("trigger") != "touch":
            raise RuntimeError("cancel was not physically touch initiated")
        if cancel_event.payload.get("active") is not True:
            raise RuntimeError("touch cancel event did not prove an active voice turn")

        try:
            await asyncio.wait_for(second_task, timeout=6.0)
        except RuntimeError:
            pass
        else:
            raise RuntimeError("touch-cancelled voice turn unexpectedly completed successfully")

        movement = await runtime.send_body_pose(0, 430, timeout=8.0)
        if movement.payload.get("executed") is not True:
            raise RuntimeError("body execution proof missing after touch cancellation")
        if movement.payload.get("torque_released") is not True:
            raise RuntimeError("torque release proof missing after touch cancellation")

        print(
            "PHASE_A3_SELF_INIT PASS touch_start=1 device_event=1 real_roundtrip=1 "
            "stt=1 thinker=1 tts=1 touch_cancel=1 playback_cancel=1 correlated_control=1 "
            "torque_released=1 body_recovery=1 control_lane=usable"
        )
        return 0
    except Exception as exc:
        print(f"PHASE_A3_SELF_INIT FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        for task in (first_task, second_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
        if runtime is not None:
            await runtime.close()
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
