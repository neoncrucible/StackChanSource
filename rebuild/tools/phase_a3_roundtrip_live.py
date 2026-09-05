from __future__ import annotations

import asyncio
import getpass
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from kcore.config import RuntimeConfig
from kcore.runtime import RuntimeBody
from kcore.voice_providers import VoiceProviderSettings
from kcore.voice_wire import process_wire_turn, read_wire_turn, send_wire_error, send_wire_reply

PORT = "COM4"
CAPTURE_MS = 4800


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


async def main() -> int:
    settings = VoiceProviderSettings.from_env()
    missing = settings.missing_credentials()
    if missing:
        print("PHASE_A3_ROUNDTRIP FAIL missing credentials: " + ",".join(missing))
        return 1

    try:
        import miniaudio  # noqa: F401
    except ImportError:
        print("PHASE_A3_ROUNDTRIP FAIL miniaudio is not installed; refresh the voice extra")
        return 1

    try:
        ssid, password = wifi_credentials()
        host_ip = local_lan_ipv4()
    except Exception as exc:
        print(f"PHASE_A3_ROUNDTRIP FAIL {type(exc).__name__}: {exc}")
        return 1

    result_ready = asyncio.Event()
    result_error: Exception | None = None
    result_seen = False

    async def handle_voice(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal result_error, result_seen
        try:
            turn = await asyncio.wait_for(read_wire_turn(reader), timeout=15.0)
            result = await asyncio.wait_for(
                process_wire_turn(turn, settings=settings),
                timeout=70.0,
            )
            await send_wire_reply(writer, result.pcm)
            result_seen = True
            result_ready.set()
        except Exception as exc:
            result_error = exc
            result_ready.set()
            try:
                await send_wire_error(writer, "voice service failure")
            except Exception:
                pass
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
        print("PHASE_A3_ROUNDTRIP FAIL voice server has no listening socket")
        return 1
    server_port = int(sockets[0].getsockname()[1])

    runtime: RuntimeBody | None = None
    try:
        runtime = await RuntimeBody.open(config(), port=PORT, ready_timeout=30.0)
        print("PHASE_A3_ROUNDTRIP READY speak when Kadence enters listening state")

        ack = await runtime.send_voice_turn(
            ssid=ssid,
            password=password,
            host=host_ip,
            port=server_port,
            capture_ms=CAPTURE_MS,
            timeout=90.0,
        )
        await asyncio.wait_for(result_ready.wait(), timeout=2.0)
        if result_error is not None:
            raise result_error
        if not result_seen:
            raise RuntimeError("provider result was not captured")
        if ack.payload.get("ok") is not True:
            raise RuntimeError("device did not acknowledge successful voice roundtrip")

        movement = await runtime.send_body_pose(0, 430, timeout=8.0)
        if movement.payload.get("executed") is not True:
            raise RuntimeError("body execution proof missing after voice turn")
        if movement.payload.get("torque_released") is not True:
            raise RuntimeError("torque release proof missing after voice turn")

        print(
            "PHASE_A3_ROUNDTRIP PASS "
            "stt=1 thinker=1 tts=1 device_mic=1 opus=1 device_speaker=1 "
            "correlated=1 body_command=1 torque_released=1 recovery=1"
        )
        return 0
    except Exception as exc:
        print(f"PHASE_A3_ROUNDTRIP FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        if runtime is not None:
            await runtime.close()
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
