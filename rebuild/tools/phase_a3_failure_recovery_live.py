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
from kcore.voice_wire import read_wire_turn, send_wire_error

PORT = "COM4"
CAPTURE_MS = 2400
EXPECTED_FAILURE = "voice turn proof missing: ok,playback,handoff"


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
    try:
        ssid, password = wifi_credentials()
        host_ip = local_lan_ipv4()
    except Exception as exc:
        print(f"PHASE_A3_FAILURE_RECOVERY FAIL setup {type(exc).__name__}: {exc}")
        return 1

    uplink_seen = asyncio.Event()
    server_error: Exception | None = None

    async def handle_voice(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal server_error
        try:
            turn = await asyncio.wait_for(read_wire_turn(reader), timeout=12.0)
            if not turn.packets:
                raise RuntimeError("forced-failure server received no Opus packets")
            uplink_seen.set()
            await send_wire_error(writer, "forced provider failure")
        except Exception as exc:
            server_error = exc
            uplink_seen.set()
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
        print("PHASE_A3_FAILURE_RECOVERY FAIL voice server has no listening socket")
        return 1
    server_port = int(sockets[0].getsockname()[1])

    runtime: RuntimeBody | None = None
    try:
        runtime = await RuntimeBody.open(config(), port=PORT, ready_timeout=30.0)
        print(
            "PHASE_A3_FAILURE_RECOVERY READY the changed mouth IS the listening state; "
            "speech content does not matter for this forced-failure test"
        )

        forced_failure_seen = False
        try:
            await runtime.send_voice_turn(
                ssid=ssid,
                password=password,
                host=host_ip,
                port=server_port,
                capture_ms=CAPTURE_MS,
                timeout=45.0,
            )
        except RuntimeError as exc:
            message = str(exc)
            if EXPECTED_FAILURE not in message:
                raise RuntimeError(f"unexpected voice failure proof: {message}") from exc
            forced_failure_seen = True

        await asyncio.wait_for(uplink_seen.wait(), timeout=2.0)
        if server_error is not None:
            raise server_error
        if not forced_failure_seen:
            raise RuntimeError("voice turn unexpectedly succeeded during forced provider failure")

        movement = await runtime.send_body_pose(0, 430, timeout=8.0)
        if movement.payload.get("executed") is not True:
            raise RuntimeError("body recovery execution proof missing")
        if movement.payload.get("torque_released") is not True:
            raise RuntimeError("torque release proof missing after forced voice failure")

        print(
            "PHASE_A3_FAILURE_RECOVERY PASS forced_provider_failure=1 device_mic=1 opus=1 "
            "correlated=1 torque_released=1 body_recovery=1 control_lane=usable"
        )
        return 0
    except Exception as exc:
        print(f"PHASE_A3_FAILURE_RECOVERY FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        if runtime is not None:
            await runtime.close()
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
