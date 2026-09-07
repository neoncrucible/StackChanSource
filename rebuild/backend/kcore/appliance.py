from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import os
import re
import socket
import subprocess
from dataclasses import dataclass, field

from .config import RuntimeConfig
from .protocol import Envelope, MessageKind
from .runtime import RuntimeBody
from .voice_providers import VoiceProviderSettings
from .voice_wire import process_wire_turn, read_wire_turn, send_wire_error, send_wire_reply


DEFAULT_PORT = "COM4"
DEFAULT_BAUD = 115200
DEFAULT_CAPTURE_MS = 4800
DEFAULT_RECONNECT_DELAY = 2.0


@dataclass(frozen=True, slots=True)
class ApplianceSettings:
    port: str
    baud: int
    capture_ms: int
    reconnect_delay: float
    ssid: str
    password: str = field(repr=False)
    lan_host: str
    providers: VoiceProviderSettings


class KadenceAppliance:
    """Always-on Phase A runtime composed from the signed-off A1-A3 slices."""

    def __init__(self, settings: ApplianceSettings):
        self.settings = settings
        self._server: asyncio.AbstractServer | None = None
        self._server_port = 0
        self._body: RuntimeBody | None = None
        self._voice_task: asyncio.Task[None] | None = None
        self._provider_task: asyncio.Task | None = None
        self._provider_lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._turn_sequence = 0

    async def run_forever(self) -> None:
        await self._start_voice_server()
        print(
            "KADENCE_RUNTIME READY "
            f"port={self.settings.port} lan={self.settings.lan_host}:{self._server_port} "
            "touch_start=1 touch_cancel=1 reconnect=1"
        )

        try:
            while not self._stop.is_set():
                body: RuntimeBody | None = None
                try:
                    body = await RuntimeBody.open(
                        _runtime_config(),
                        port=self.settings.port,
                        baud=self.settings.baud,
                        ready_timeout=30.0,
                    )
                    self._body = body
                    print("KADENCE_RUNTIME DEVICE ready presence=local")
                    await self._run_connected(body)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if not self._stop.is_set():
                        print(
                            "KADENCE_RUNTIME DEVICE offline "
                            f"reason={type(exc).__name__}:{_safe_message(exc)}"
                        )
                finally:
                    await self._cancel_active_provider()
                    await self._cancel_active_voice_task()
                    if body is not None:
                        with contextlib.suppress(Exception):
                            await body.close()
                    if self._body is body:
                        self._body = None

                if not self._stop.is_set():
                    print(
                        "KADENCE_RUNTIME RECONNECT "
                        f"delay_s={self.settings.reconnect_delay:.1f}"
                    )
                    try:
                        await asyncio.wait_for(
                            self._stop.wait(), timeout=self.settings.reconnect_delay
                        )
                    except TimeoutError:
                        pass
        finally:
            await self.close()

    async def close(self) -> None:
        self._stop.set()
        await self._cancel_active_provider()
        await self._cancel_active_voice_task()
        body = self._body
        self._body = None
        if body is not None:
            with contextlib.suppress(Exception):
                await body.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        print("KADENCE_RUNTIME STOPPED clean=1")

    async def _start_voice_server(self) -> None:
        self._server = await asyncio.start_server(self._handle_voice_connection, "0.0.0.0", 0)
        sockets = self._server.sockets or []
        if not sockets:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            raise RuntimeError("voice server has no listening socket")
        self._server_port = int(sockets[0].getsockname()[1])

    async def _run_connected(self, body: RuntimeBody) -> None:
        events = asyncio.create_task(self._event_loop(body), name="kadence-device-events")
        disconnected = asyncio.create_task(
            body.wait_disconnected(), name="kadence-device-disconnect"
        )
        done, pending = await asyncio.wait(
            {events, disconnected}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in pending:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if events in done:
            events.result()

    async def _event_loop(self, body: RuntimeBody) -> None:
        while body.connected and not self._stop.is_set():
            event = await body.next_event()
            if event.kind is not MessageKind.EVENT:
                continue
            if event.name == "voice.request":
                self._begin_voice_turn(body, event)
            elif event.name == "voice.touch-cancel":
                await self._handle_touch_cancel(body, event)

    def _begin_voice_turn(self, body: RuntimeBody, event: Envelope) -> None:
        active = self._voice_task
        if active is not None and not active.done():
            print("KADENCE_RUNTIME TURN ignored reason=voice-busy")
            return
        if event.payload.get("trigger") != "touch":
            print("KADENCE_RUNTIME TURN ignored reason=untrusted-trigger")
            return

        self._voice_task = asyncio.create_task(
            self._run_voice_turn(body), name="kadence-voice-turn"
        )
        self._voice_task.add_done_callback(self._voice_task_done)
        print("KADENCE_RUNTIME TURN start trigger=touch")

    def _voice_task_done(self, task: asyncio.Task[None]) -> None:
        if self._voice_task is task:
            self._voice_task = None
        if task.cancelled():
            return
        with contextlib.suppress(Exception):
            task.result()

    async def _run_voice_turn(self, body: RuntimeBody) -> None:
        try:
            ack = await body.send_voice_turn(
                ssid=self.settings.ssid,
                password=self.settings.password,
                host=self.settings.lan_host,
                port=self._server_port,
                capture_ms=self.settings.capture_ms,
                timeout=90.0,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "KADENCE_RUNTIME TURN recovered "
                f"reason={type(exc).__name__}:{_safe_message(exc)}"
            )
            return

        if ack.payload.get("ok") is not True:
            print("KADENCE_RUNTIME TURN recovered reason=device-proof-missing")
            return

        self._turn_sequence += 1
        body_ok = False
        try:
            movement = await body.send_body_pose(0, 430, timeout=8.0)
            body_ok = (
                movement.payload.get("executed") is True
                and movement.payload.get("torque_released") is True
            )
        except Exception as exc:
            print(
                "KADENCE_RUNTIME BODY degraded "
                f"reason={type(exc).__name__}:{_safe_message(exc)}"
            )

        print(
            "KADENCE_RUNTIME TURN complete "
            f"seq={self._turn_sequence} voice=1 body_reaction={int(body_ok)} idle_return=1"
        )

    async def _handle_touch_cancel(self, body: RuntimeBody, event: Envelope) -> None:
        if event.payload.get("trigger") != "touch":
            return

        provider_cancelled = await self._cancel_active_provider()
        active_voice = self._voice_task is not None and not self._voice_task.done()
        cancel_ok = False
        if active_voice:
            try:
                cancel_ack = await body.send_voice_cancel(timeout=3.0)
                cancel_ok = (
                    cancel_ack.payload.get("ok") is True
                    and cancel_ack.payload.get("torque_released") is True
                )
            except Exception as exc:
                print(
                    "KADENCE_RUNTIME CANCEL degraded "
                    f"reason={type(exc).__name__}:{_safe_message(exc)}"
                )

        print(
            "KADENCE_RUNTIME CANCEL touch=1 "
            f"provider={int(provider_cancelled)} control={int(cancel_ok)}"
        )

    async def _cancel_active_provider(self) -> bool:
        task = self._provider_task
        if task is None or task.done():
            return False
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        if self._provider_task is task:
            self._provider_task = None
        return True

    async def _cancel_active_voice_task(self) -> None:
        task = self._voice_task
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        if self._voice_task is task:
            self._voice_task = None

    async def _handle_voice_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        async with self._provider_lock:
            try:
                turn = await asyncio.wait_for(read_wire_turn(reader), timeout=15.0)
                provider_task = asyncio.create_task(
                    process_wire_turn(turn, settings=self.settings.providers),
                    name="kadence-provider-turn",
                )
                self._provider_task = provider_task
                try:
                    result = await provider_task
                finally:
                    if self._provider_task is provider_task:
                        self._provider_task = None

                await send_wire_reply(writer, result.pcm)
                print(
                    "KADENCE_RUNTIME PROVIDERS complete "
                    f"transcript_chars={len(result.transcript)} "
                    f"reply_chars={len(result.reply)} pcm_bytes={len(result.pcm)}"
                )
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    await send_wire_error(writer, "voice turn cancelled")
            except Exception as exc:
                print(
                    "KADENCE_RUNTIME PROVIDERS recovered "
                    f"reason={type(exc).__name__}:{_safe_message(exc)}"
                )
                with contextlib.suppress(Exception):
                    await send_wire_error(writer, "voice service failure")
            finally:
                writer.close()
                with contextlib.suppress(ConnectionError):
                    await writer.wait_closed()


def _runtime_config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


def _safe_message(exc: BaseException) -> str:
    text = str(exc).replace("\r", " ").replace("\n", " ").strip()
    return text[:180] if text else "unspecified"


def _current_wifi_ssid() -> str | None:
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


def _wifi_credentials() -> tuple[str, str]:
    ssid = _current_wifi_ssid()
    if not ssid:
        ssid = input("Wi-Fi SSID: ").strip()
    if not ssid:
        raise RuntimeError("Wi-Fi SSID was empty")
    if len(ssid.encode("utf-8")) > 32:
        raise RuntimeError("Wi-Fi SSID exceeds 32 UTF-8 bytes")

    password = os.environ.get("KADENCE_WIFI_PASSWORD")
    if password is None:
        password = getpass.getpass("Wi-Fi password (not echoed): ")
    if len(password.encode("utf-8")) > 63:
        raise RuntimeError("Wi-Fi password exceeds 63 UTF-8 bytes")
    return ssid, password


def _local_lan_ipv4() -> str:
    configured = os.environ.get("KADENCE_LAN_HOST", "").strip()
    if configured:
        return configured
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        address = probe.getsockname()[0]
    finally:
        probe.close()
    if not address or address.startswith("127."):
        raise RuntimeError("could not resolve a non-loopback LAN IPv4 address")
    return address


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Kadence Phase A appliance runtime")
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--capture-ms", type=int, default=DEFAULT_CAPTURE_MS)
    parser.add_argument("--reconnect-delay", type=float, default=DEFAULT_RECONNECT_DELAY)
    return parser.parse_args()


def _make_settings(args: argparse.Namespace) -> ApplianceSettings:
    if args.capture_ms < 2400 or args.capture_ms > 8000:
        raise ValueError("capture-ms must be in 2400..8000")
    if args.reconnect_delay <= 0:
        raise ValueError("reconnect-delay must be positive")

    providers = VoiceProviderSettings.from_env()
    missing = providers.missing_credentials()
    if missing:
        raise RuntimeError("missing credentials: " + ",".join(missing))

    try:
        import miniaudio  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("miniaudio is not installed; refresh the voice extra") from exc

    ssid, password = _wifi_credentials()
    lan_host = _local_lan_ipv4()
    return ApplianceSettings(
        port=args.port,
        baud=args.baud,
        capture_ms=args.capture_ms,
        reconnect_delay=args.reconnect_delay,
        ssid=ssid,
        password=password,
        lan_host=lan_host,
        providers=providers,
    )


def main() -> int:
    try:
        settings = _make_settings(_parse_args())
    except Exception as exc:
        print(f"KADENCE_RUNTIME NEEDS_SETUP {type(exc).__name__}: {_safe_message(exc)}")
        return 2

    appliance = KadenceAppliance(settings)
    try:
        asyncio.run(appliance.run_forever())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
