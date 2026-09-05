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
from kcore.runtime import RuntimeBody
from kcore.voice_wire import read_wire_turn, send_wire_reply

PORT = "COM4"
CAPTURE_MS = 2400
TONE_SECONDS = 20
SAMPLE_RATE = 16000


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
    # Quiet but obvious enough to hear cancellation. The server sends the whole
    # reply first; the robot then plays from its local PSRAM buffer.
    amplitude = 900
    frequency = 440.0
    samples = bytearray(SAMPLE_RATE * TONE_SECONDS * 2)
    for index in range(SAMPLE_RATE * TONE_SECONDS):
        value = int(amplitude * math.sin(2.0 * math.pi * frequency * index / SAMPLE_RATE))
        struct.pack_into("<h", samples, index * 2, value)
    return bytes(samples)


async def main() -> int:
    try:
        ssid, password = wifi_credentials()
        host_ip = local_lan_ipv4()
        pcm = synthetic_tone_pcm()
    except Exception as exc:
        print(f"PHASE_A3_CANCEL_LIVE FAIL {type(exc).__name__}: {exc}")
        return 1

    reply_sent = asyncio.Event()
    server_error: Exception | None = None

    async def handle_voice(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal server_error
        try:
            await asyncio.wait_for(read_wire_turn(reader), timeout=15.0)
            await send_wire_reply(writer, pcm)
            reply_sent.set()
            # Keep the server side alive while the device drains its local buffer.
            await asyncio.sleep(5.0)
        except Exception as exc:
            server_error = exc
            reply_sent.set()
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
        print("PHASE_A3_CANCEL_LIVE FAIL voice server has no listening socket")
        return 1
    server_port = int(sockets[0].getsockname()[1])

    runtime: RuntimeBody | None = None
    voice_task: asyncio.Task | None = None
    try:
        runtime = await RuntimeBody.open(config(), port=PORT, ready_timeout=30.0)
        print(
            "PHASE_A3_CANCEL_LIVE READY no speech required; Kadence will play a quiet "
            "test tone and the harness will cancel it while the speaker is active"
        )

        voice_task = asyncio.create_task(
            runtime.send_voice_turn(
                ssid=ssid,
                password=password,
                host=host_ip,
                port=server_port,
                capture_ms=CAPTURE_MS,
                timeout=30.0,
            )
        )

        await asyncio.wait_for(reply_sent.wait(), timeout=12.0)
        if server_error is not None:
            raise server_error

        # LAN transfer is already complete. This delay intentionally lets local
        # speaker playback begin so cancellation proves barge-in, not provider wait.
        await asyncio.sleep(1.0)
        loop = asyncio.get_running_loop()
        cancel_started = loop.time()
        cancel_ack = await runtime.send_voice_cancel(timeout=3.0)
        cancel_latency = loop.time() - cancel_started

        if cancel_ack.payload.get("active") is not True:
            raise RuntimeError("cancel ACK did not prove an active voice turn")
        if cancel_ack.payload.get("cancelled") is not True:
            raise RuntimeError("cancel ACK did not confirm cancellation")

        try:
            await asyncio.wait_for(voice_task, timeout=5.0)
        except RuntimeError:
            pass
        else:
            raise RuntimeError("cancelled voice turn unexpectedly completed successfully")

        movement = await runtime.send_body_pose(0, 430, timeout=8.0)
        if movement.payload.get("executed") is not True:
            raise RuntimeError("body execution proof missing after cancellation")
        if movement.payload.get("torque_released") is not True:
            raise RuntimeError("torque release proof missing after cancellation")
        if cancel_latency > 2.5:
            raise RuntimeError(f"cancel acknowledgement was too slow: {cancel_latency:.2f}s")

        print(
            "PHASE_A3_CANCEL_LIVE PASS "
            "async_lane=1 preemptive_cancel=1 playback_cancel=1 correlated=1 "
            "torque_released=1 body_recovery=1 control_lane=usable"
        )
        return 0
    except Exception as exc:
        print(f"PHASE_A3_CANCEL_LIVE FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        if voice_task is not None and not voice_task.done():
            voice_task.cancel()
            try:
                await voice_task
            except BaseException:
                pass
        if runtime is not None:
            await runtime.close()
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
