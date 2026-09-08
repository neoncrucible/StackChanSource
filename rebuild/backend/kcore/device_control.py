"""Typed extensions over the existing single serial owner and ACK registry."""
from __future__ import annotations

import asyncio
import contextlib
import ipaddress

from .protocol import Envelope, MessageKind
from .host import VoiceTurnFailure


async def request_device(host, name: str, payload: dict | None = None, *, timeout=3.0):
    payload = dict(payload or {})
    media = name in {"voice.alert", "camera.snapshot"}
    if name not in {"device.status", "device.settings", "game.start", "game.stop", "voice.alert", "camera.snapshot"}:
        raise ValueError("unsupported device command")
    if type(timeout) not in (int, float) or not 0 < timeout <= 210: raise ValueError("invalid command timeout")
    if media:
        if set(payload) != {"ssid", "password", "host", "port", "capture_ms", "token"}: raise ValueError("invalid media fields")
        if not isinstance(payload["ssid"], str) or not 1 <= len(payload["ssid"].encode()) <= 32: raise ValueError("invalid SSID")
        if not isinstance(payload["password"], str) or len(payload["password"].encode()) > 63: raise ValueError("invalid Wi-Fi password length")
        ipaddress.IPv4Address(payload["host"])
        if type(payload["port"]) is not int or not 1 <= payload["port"] <= 65535: raise ValueError("invalid media port")
        if type(payload["capture_ms"]) is not int or not 2400 <= payload["capture_ms"] <= 8000: raise ValueError("invalid capture duration")
        token = payload["token"]
        if not isinstance(token, str) or len(token) != 32 or set(token)-set("0123456789abcdef"): raise ValueError("invalid media token")
    elif name == "device.settings":
        if set(payload)-{"volume", "maximum", "brightness", "muted", "quiet", "reverse", "sound"}: raise ValueError("unknown device setting")
        for key, value in payload.items():
            if key in {"muted", "quiet", "reverse", "sound"}:
                if type(value) is not bool: raise ValueError("setting must be boolean")
            elif type(value) is not int or not 0 <= value <= (60 if key == "brightness" else 100):
                raise ValueError("setting outside range")
    elif payload: raise ValueError("unexpected device arguments")
    async with host._command_lock if media or name == "game.start" else contextlib.nullcontext():
        writer, session = host._active_writer, host._active_session
        if writer is None or session is None or not session.hello_seen: raise RuntimeError("robot is disconnected")
        command = Envelope(MessageKind.COMMAND, name, payload)
        future = asyncio.get_running_loop().create_future()
        host._pending[command.request_id] = future
        try:
            await host._send(writer, command)
            response = await asyncio.wait_for(future, timeout)
        except (TimeoutError, asyncio.CancelledError):
            host._retire_request(command.request_id)
            raise
        finally: host._pending.pop(command.request_id, None)
        if response.kind is not MessageKind.ACK or response.name != name: raise RuntimeError("device ACK mismatch")
        required = ("ok", "network", "handoff", "torque_released", "playback" if name == "voice.alert" else "capture") if media else ("ok",)
        missing = [key for key in required if response.payload.get(key) is not True]
        if missing:
            if media: raise VoiceTurnFailure(missing, response.payload)
            raise RuntimeError("device command was not applied")
        return response
