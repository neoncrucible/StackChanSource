from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import importlib
import os
import re
import secrets
import socket
import math
import struct
import time
import subprocess
import sys
from dataclasses import dataclass, field, replace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import RuntimeConfig
from .host import VoiceTurnFailure
from .companion import Companion
from .context_store import ContextStore, default_data_dir
from .integrations import register_integrations
from .local_tools import make_local_tools
from .protocol import Envelope, MessageKind
from .runtime import RuntimeBody
from .runtime_bridge import RuntimePresentationBridge
from .voice_providers import VoiceProviderSettings
from .voice_wire import process_wire_turn, read_wire_turn, send_wire_error, send_wire_reply
from .services import LocalServices
from .device_control import request_device
from .vision import DeskVision, read_media_auth, read_image
from .voice_wire import _synthesize_reply
from .voice_providers import LiveVoiceProviders


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
    timezone_name: str = "Europe/London"


class KadenceAppliance:
    """Normal companion runtime composed from the signed-off hardware owners."""

    def __init__(self, settings: ApplianceSettings, *, services: LocalServices | None = None, emit=None):
        self.settings = settings
        self.emit = emit or (lambda name, data: None)
        self.services = services
        self._owns_services = services is None
        self.vision = DeskVision(self.emit)
        self._utility_task = None
        self._media_mode = "voice"
        self._media_result = None
        self._alert_pcm = b""
        self._capture_in_voice = None
        self._last_device_status = {}
        self._server: asyncio.AbstractServer | None = None
        self._server_port = 0
        self._body: RuntimeBody | None = None
        self._voice_task: asyncio.Task[None] | None = None
        self._provider_task: asyncio.Task | None = None
        self._provider_lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._turn_sequence = 0
        self._turn_token: str | None = None
        self._wire_claimed = False
        self._wire_result = None
        self._connections: dict[asyncio.Task, asyncio.StreamWriter] = {}
        self._companion: Companion | None = None
        self._provider_stage: str | None = None

    def _report_issue(self, stage: str, error: Exception) -> None:
        # Status crosses the GUI boundary; arbitrary exception text never does.
        data = {"stage": stage, "reason": "timeout" if isinstance(error, TimeoutError) else "unavailable"}
        if isinstance(error, VoiceTurnFailure):
            data.update(reason="device_proof", device_stage=error.stage,
                        error_code=error.error_code, wifi_reason=error.wifi_reason)
        if stage == "providers" and self._provider_stage in {"stt", "reasoning", "tts", "tts_connect", "tts_audio", "tts_decode", "tts_fallback", "tts_local_load", "tts_local_render", "tts_ready"}:
            data["provider_stage"] = self._provider_stage
        self.emit("runtime_issue", data)

    async def run_forever(self) -> None:
        await self._start_companion()
        await self._start_voice_server()
        self._utility_task = asyncio.create_task(self._utility_loop(), name="kadence-device-status")
        self.emit("server", {"state": "running", "port": self.settings.port, "lan": self.settings.lan_host, "media_port": self._server_port})
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
                    self.emit("robot", {"connected": True})
                    print("KADENCE_RUNTIME DEVICE ready presence=local")
                    await self._run_connected(body)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if not self._stop.is_set():
                        self._report_issue("connection", exc)
                        print(
                            "KADENCE_RUNTIME DEVICE offline "
                            f"reason={type(exc).__name__}:{_safe_message(exc)}"
                        )
                finally:
                    self.emit("robot", {"connected": False})
                    self._turn_token = None
                    await self._cancel_active_provider()
                    await self._cancel_active_voice_task()
                    await self._close_connections()
                    if self._companion:
                        self._companion.abort_turn()
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
        if self._utility_task:
            self._utility_task.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self._utility_task
            self._utility_task = None
        if self._body and self._voice_task and not self._voice_task.done():
            with contextlib.suppress(Exception): await self._body.send_voice_cancel(timeout=3)
        self._turn_token = None
        await self._cancel_active_provider()
        await self._cancel_active_voice_task()
        await self._close_connections()
        if self._companion:
            self._companion.abort_turn()
            if self.services is None: await self._companion.tools.close()
        if self.services:
            self.services.look_handler = None
            if self._owns_services: await self.services.close()
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
        self.emit("server", {"state": "stopped"})

    async def _start_companion(self) -> None:
        if self.services is None:
            candidate = LocalServices(timezone_name=self.settings.timezone_name, emit=self.emit)
            try:
                await candidate.start()
                self.services = candidate
            except Exception:
                await candidate.close()
                print("KADENCE_RUNTIME UTILITIES unavailable local_store=unavailable")
        if self.services:
            self.services.look_handler = self._look_during_voice
            self._companion = Companion(self.services.tools, self.services.context,
                reminders=self.services.reminders, timezone_name=self.settings.timezone_name)
            return
        store = ContextStore(default_data_dir())
        try:
            await asyncio.wait_for(store.start(), timeout=2)
        except Exception:
            store = None
            print("KADENCE_RUNTIME CONTEXT degraded local_store=unavailable")
        tools = make_local_tools(store, timezone_name=os.environ.get("KADENCE_TIMEZONE", "Europe/London"))
        try:
            register_integrations(tools)
        except ValueError:
            print("KADENCE_RUNTIME INTEGRATION unavailable configuration=invalid")
        self._companion = Companion(tools, store)

    async def _utility_loop(self):
        while not self._stop.is_set():
            body = self._body
            if body is not None and body.connected:
                try:
                    ack = await request_device(body.host, "device.status")
                    self._last_device_status = ack.payload
                    self.emit("device", ack.payload)
                    idle = self._voice_task is None or self._voice_task.done()
                    if self.services and idle and not ack.payload.get("media_busy") and ack.payload.get("game") == "off":
                        reminders = await self.services.store.call("reminder_list")
                        if (self._voice_task is None or self._voice_task.done()) and any(r["state"] == "due" and r["robot"] == "pending" for r in reminders):
                            self._voice_task = asyncio.create_task(self._deliver_reminders(body), name="kadence-alert")
                            self._voice_task.add_done_callback(self._voice_task_done)
                except asyncio.CancelledError: raise
                except Exception:
                    self.emit("device_status", {"state": "unavailable"})
            await asyncio.sleep(1)

    async def _deliver_reminders(self, body):
        rows = await self.services.store.call("claim_robot")
        if not rows: return
        reply = f"You have {len(rows)} reminders due. Open Kadence to review them." if len(rows) > 2 else "Reminder. " + ". ".join(row["text"] for row in rows)
        try:
            providers = LiveVoiceProviders.from_settings(self.settings.providers)
            self._alert_pcm = await _synthesize_reply(providers, reply[:600])
        except asyncio.CancelledError: raise
        except Exception:
            # A bounded local chime needs neither API credentials nor an Internet connection.
            self._alert_pcm = b"".join(struct.pack("<h", int(2200*math.sin(i*2*math.pi*660/16000))) if i%8000<4000 else b"\0\0" for i in range(24000))
        try:
            await self._run_media(body, "voice.alert")
            await self.services.store.call("robot_delivered", ids=[r["id"] for r in rows])
            self.emit("alert", {"state": "delivered", "count": len(rows)})
        except asyncio.CancelledError: raise
        except Exception:
            self.emit("alert", {"state": "review_in_windows", "count": len(rows)})
        finally: self._alert_pcm = b""

    async def _run_media(self, body, name):
        self._media_mode = "alert" if name == "voice.alert" else "camera"
        self._turn_token = secrets.token_hex(16)
        self._wire_claimed = False
        self._media_result = None
        self.emit("activity", {"state": self._media_mode})
        try:
            await request_device(body.host, name, {"ssid": self.settings.ssid, "password": self.settings.password,
                "host": self.settings.lan_host, "port": self._server_port, "capture_ms": self.settings.capture_ms,
                "token": self._turn_token}, timeout=45 if name == "camera.snapshot" else 190)
            if self._media_result is None: raise RuntimeError("media transfer was not confirmed")
            return self._media_result
        except BaseException as exc:
            if isinstance(exc, Exception): self._report_issue(self._media_mode, exc)
            with contextlib.suppress(Exception): await body.send_voice_cancel(timeout=3)
            raise
        finally:
            self._turn_token = None
            await self._close_connections()
            self._media_mode = "voice"
            self.emit("activity", {"state": "idle"})

    async def capture_snapshot(self):
        body = self._body
        if body is None or not body.connected: raise RuntimeError("Connect the robot first.")
        if self._voice_task is not None and not self._voice_task.done(): raise RuntimeError("Wait for the current voice or camera task.")
        if self._last_device_status.get("game", "off") != "off": raise RuntimeError("Stop the memory game before capturing.")
        self._voice_task = asyncio.create_task(self._run_media(body, "camera.snapshot"), name="kadence-snapshot")
        self._voice_task.add_done_callback(self._voice_task_done)
        raw = await self._voice_task
        await self.vision.accept(raw)
        return {"message": "Snapshot captured. Local QR decoding complete."}

    async def _look_during_voice(self, question):
        if self._capture_in_voice is None: raise RuntimeError("No active camera request channel")
        raw = await self._capture_in_voice()
        await self.vision.accept(raw)
        return await self.vision.describe(question, self.settings.providers)

    async def _close_connections(self) -> None:
        connections = tuple(self._connections.items())
        for task, writer in connections:
            writer.close()
            task.cancel()
        if connections:
            await asyncio.wait({task for task, _ in connections}, timeout=1)

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
        try:
            done, _ = await asyncio.wait({events, disconnected}, return_when=asyncio.FIRST_COMPLETED)
            if events in done:
                events.result()
        finally:
            for task in (events, disconnected):
                task.cancel()
            await asyncio.gather(events, disconnected, return_exceptions=True)

    async def _event_loop(self, body: RuntimeBody) -> None:
        while body.connected and not self._stop.is_set():
            event = await body.next_event()
            if event.kind is not MessageKind.EVENT:
                continue
            if event.name == "voice.request":
                self._begin_voice_turn(body, event)
            elif event.name == "voice.touch-cancel":
                await self._handle_touch_cancel(body, event)
            elif event.name == "voice.phase":
                self._handle_voice_phase(body, event)

    def _handle_voice_phase(self, body: RuntimeBody, event: Envelope) -> None:
        # A delayed phase from an earlier turn cannot resurrect LISTENING.
        request_id = event.payload.get("request_id")
        if (body is not self._body or self._turn_token is None or not isinstance(request_id, str)
                or request_id not in body.host._pending):
            return
        state = event.payload.get("state")
        if state not in {"attentive", "listening", "thinking", "speaking", "degraded"}:
            return
        data = {"state": state}
        if state == "listening":
            duration = event.payload.get("capture_ms")
            if type(duration) is not int or not 2400 <= duration <= 8000:
                return
            data["capture_ms"] = duration
        self.emit("activity", data)

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
        self.emit("activity", {"state": "attentive"})

    def _voice_task_done(self, task: asyncio.Task[None]) -> None:
        if self._voice_task is task:
            self._voice_task = None
            self.emit("activity", {"state": "idle"})
        if task.cancelled():
            return
        with contextlib.suppress(Exception):
            task.result()

    async def _run_voice_turn(self, body: RuntimeBody) -> None:
        self._media_mode = "voice"
        self._turn_token = secrets.token_hex(16)
        self._wire_claimed = False
        self._wire_result = None
        self._provider_stage = None
        try:
            ack = await body.send_voice_turn(
                ssid=self.settings.ssid,
                password=self.settings.password,
                host=self.settings.lan_host,
                port=self._server_port,
                capture_ms=self.settings.capture_ms,
                timeout=210.0,
                token=self._turn_token,
            )
        except asyncio.CancelledError:
            self._turn_token = None
            if self._companion:
                self._companion.abort_turn()
            raise
        except Exception as exc:
            self._turn_token = None
            await self._cancel_active_provider()
            await self._close_connections()
            if self._companion:
                self._companion.abort_turn()
            if not isinstance(exc, VoiceTurnFailure) or not exc.torque_released:
                with contextlib.suppress(Exception):
                    await body.send_voice_cancel(timeout=3.0)
            if isinstance(exc, VoiceTurnFailure) and exc.cancelled:
                print("KADENCE_RUNTIME TURN cancelled torque=released")
                return
            self._report_issue("voice", exc)
            print(
                "KADENCE_RUNTIME TURN recovered "
                f"reason={type(exc).__name__}:{_safe_message(exc)}"
            )
            return

        self._turn_token = None
        if ack.payload.get("ok") is not True:
            if self._companion:
                self._companion.abort_turn()
            print("KADENCE_RUNTIME TURN recovered reason=device-proof-missing")
            return

        if self._companion and self._wire_result is not None:
            result = self._wire_result
            self._companion.commit_spoken(result.transcript, result.reply)
        self._wire_result = None

        self._turn_sequence += 1
        self.emit("turn", {"completed": self._turn_sequence})
        self.emit("activity", {"state": "idle"})
        body_ok = False
        try:
            movement = await body.send_body_pose(0, 430, timeout=8.0)
            body_ok = (
                movement.payload.get("executed") is True
                and movement.payload.get("torque_released") is True
            )
        except Exception as exc:
            self._report_issue("body", exc)
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

        self._turn_token = None
        self._wire_result = None
        if self._companion:
            self._companion.abort_turn()
        provider_cancelled = await self._cancel_active_provider()
        await self._close_connections()
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
                self._report_issue("cancel", exc)
                print(
                    "KADENCE_RUNTIME CANCEL degraded "
                    f"reason={type(exc).__name__}:{_safe_message(exc)}"
                )

        if cancel_ok:
            # Retire the original wait after the device confirmed cancellation.
            # A dropped final voice ACK must not hold the UI busy for 210 seconds.
            await self._cancel_active_voice_task()

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
        task = asyncio.current_task()
        body, token = self._body, self._turn_token
        mode = self._media_mode
        if (task is None or body is None or token is None or self._wire_claimed
                or self._provider_lock.locked() or len(self._connections) >= 4):
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            return
        self._connections[task] = writer
        phase = "UPLINK"
        try:
            async with self._provider_lock:
                if mode in {"alert", "camera"}:
                    await asyncio.wait_for(read_media_auth(reader, magic=b"KDA1" if mode == "alert" else b"KDC1", token=token), 5)
                    if self._turn_token != token or self._body is not body or not body.connected: return
                    self._wire_claimed = True
                    if mode == "alert":
                        await asyncio.wait_for(send_wire_reply(writer, self._alert_pcm), 10)
                        self._media_result = True
                    else:
                        self._media_result = await asyncio.wait_for(read_image(reader), 12)
                        writer.write(b"KDAK")
                        await writer.drain()
                    return
                turn = await asyncio.wait_for(read_wire_turn(reader, expected_token=token), timeout=20.0)
                if self._turn_token != token or self._body is not body or not body.connected:
                    return
                self._wire_claimed = True
                phase = "PROVIDERS"
                bridge = RuntimePresentationBridge(body)
                camera_requested = False

                async def capture_in_voice():
                    nonlocal camera_requested
                    if camera_requested or self._turn_token != token: raise RuntimeError("Only one snapshot is available per voice turn")
                    camera_requested = True
                    self.emit("activity", {"state": "camera"})
                    writer.write(b"KDQ1")
                    await writer.drain()
                    return await asyncio.wait_for(read_image(reader), 10)

                self._capture_in_voice = capture_in_voice

                async def state_sink(state: str) -> None:
                    if self._turn_token != token or self._body is not body or not body.connected:
                        raise asyncio.CancelledError()
                    await bridge.set_state(state)
                    self.emit("activity", {"state": state})

                await state_sink("thinking")

                async def provider_progress(stage: str) -> None:
                    if self._turn_token != token:
                        raise asyncio.CancelledError()
                    self._provider_stage = stage
                    self.emit("provider_stage", {"stage": stage})

                provider_task = asyncio.create_task(
                    process_wire_turn(turn, settings=self.settings.providers,
                                      companion=self._companion, state_sink=state_sink,
                                      progress_sink=provider_progress),
                    name="kadence-provider-turn",
                )
                self._provider_task = provider_task
                try:
                    async with asyncio.timeout(52):
                        result = await provider_task
                finally:
                    if self._provider_task is provider_task:
                        self._provider_task = None
                if self._turn_token != token:
                    return
                self._wire_result = result
                for stage, elapsed_ms in result.timings.items():
                    self.emit("timing", {"stage": stage, "elapsed_ms": elapsed_ms})
                await asyncio.wait_for(send_wire_reply(writer, result.pcm), timeout=10)
                print(
                    "KADENCE_RUNTIME PROVIDERS complete "
                    f"transcript_chars={len(result.transcript)} "
                    f"reply_chars={len(result.reply)} pcm_bytes={len(result.pcm)}"
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._report_issue("providers" if phase == "PROVIDERS" else "uplink", exc)
            if self._turn_token == token:
                self._wire_result = None
                if self._companion:
                    self._companion.abort_turn()
            if isinstance(exc, asyncio.IncompleteReadError) and phase == "UPLINK":
                print(f"KADENCE_RUNTIME UPLINK ended_early expected_bytes={exc.expected} received_bytes={len(exc.partial)}")
            else:
                print(f"KADENCE_RUNTIME {phase} recovered reason={type(exc).__name__}")
            with contextlib.suppress(Exception):
                await asyncio.wait_for(send_wire_error(writer, "voice service failure"), timeout=1)
        finally:
            self._capture_in_voice = None
            if self.services and mode == "voice":
                with contextlib.suppress(Exception):
                    self.emit("utilities", await self.services.snapshot())
            writer.close()
            self._connections.pop(task, None)
            with contextlib.suppress(ConnectionError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), timeout=1)


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


def _prompt_credential(label: str, *, visible: bool) -> str:
    return input(f"{label}: ") if visible else getpass.getpass(f"{label}: ")


def _wifi_credentials(*, visible_input: bool = False) -> tuple[str, str]:
    ssid = _current_wifi_ssid()
    if not ssid:
        ssid = input("Wi-Fi SSID: ").strip()
    if not ssid:
        raise RuntimeError("Wi-Fi SSID was empty")
    if len(ssid.encode("utf-8")) > 32:
        raise RuntimeError("Wi-Fi SSID exceeds 32 UTF-8 bytes")

    password = os.environ.get("KADENCE_WIFI_PASSWORD")
    if password is None:
        password = _prompt_credential("Wi-Fi password", visible=visible_input)
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
    parser = argparse.ArgumentParser(description="Run the Kadence companion runtime")
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--capture-ms", type=int, default=DEFAULT_CAPTURE_MS)
    parser.add_argument("--reconnect-delay", type=float, default=DEFAULT_RECONNECT_DELAY)
    parser.add_argument("--visible-input", action="store_true", help="Show credential input in the local terminal")
    parser.add_argument("--check", action="store_true", help="Check this Python's runtime dependencies without credentials or hardware")
    return parser.parse_args()


def _check_runtime_environment() -> None:
    # Use the same interpreter as the actual entry point, before asking for keys.
    missing = []
    for module in ("serial", "httpx", "edge_tts", "miniaudio", "tzdata"):
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    if missing:
        raise RuntimeError("missing runtime dependencies: " + ",".join(missing) +
                           "; install the rebuild voice extra into this Python: " + sys.executable)
    try:
        ZoneInfo(os.environ.get("KADENCE_TIMEZONE", "Europe/London"))
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError("timezone unavailable; check KADENCE_TIMEZONE and this Python's tzdata installation") from exc


def _make_settings(args: argparse.Namespace) -> ApplianceSettings:
    if args.capture_ms < 2400 or args.capture_ms > 8000:
        raise ValueError("capture-ms must be in 2400..8000")
    if args.reconnect_delay <= 0:
        raise ValueError("reconnect-delay must be positive")

    _check_runtime_environment()
    visible_input = args.visible_input
    providers = VoiceProviderSettings.from_env()
    missing = providers.missing_credentials()
    if missing and sys.stdin.isatty():
        visibility = "visible" if visible_input else "hidden"
        print(f"Provider credentials are used in this process only. Input is {visibility}.")
        if not providers.openai_api_key:
            providers = replace(providers, openai_api_key=_prompt_credential("OpenAI API key", visible=visible_input).strip() or None)
        if not providers.gemini_api_key:
            providers = replace(providers, gemini_api_key=_prompt_credential("Gemini API key", visible=visible_input).strip() or None)
        missing = providers.missing_credentials()
    if missing:
        raise RuntimeError("missing credentials: " + ",".join(missing))

    ssid, password = _wifi_credentials(visible_input=visible_input)
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
        timezone_name=os.environ.get("KADENCE_TIMEZONE", "Europe/London"),
    )


def main() -> int:
    try:
        args = _parse_args()
        if args.check:
            _check_runtime_environment()
            print("KADENCE_RUNTIME CHECK PASS dependencies=ready timezone=ready")
            return 0
        settings = _make_settings(args)
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
