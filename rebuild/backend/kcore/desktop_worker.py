"""Private stdin/stdout control protocol. This process alone owns serial I/O."""
from __future__ import annotations
import asyncio
import contextlib
import ipaddress
import json
import os
import sys
import threading
import time
from zoneinfo import ZoneInfo

from .appliance import ApplianceSettings, KadenceAppliance, _local_lan_ipv4
from .device_control import request_device
from .serial_transport import set_camera_diagnostic_sink
from .services import LocalServices
from .voice_providers import VoiceProviderSettings

MAX_INPUT = 32768
MAX_OUTPUT = 1024*1024
SETTINGS = frozenset({"port", "ssid", "lan_host", "timezone", "capture_ms", "openai_api_key", "gemini_api_key", "wifi_password"})

CAMERA_CHECKPOINTS = {
    "entry": 1, "precondition": 2, "buffers-ready": 3, "buffers": 4,
    "sccb-new": 5, "sccb-ready": 6, "sensor-detect": 7, "sensor-detected": 8,
    "sensor-cancelled": 9, "format-set": 10, "format-get": 11,
    "format-contract": 12, "format-ready": 13, "controller-new": 14,
    "controller-created": 15, "callbacks": 16, "callbacks-ready": 17,
    "controller-enable": 18, "controller-enabled": 19, "controller-start": 20,
    "controller-started": 21, "stream-on": 22, "warmup-cancelled": 23,
    "warmup-complete": 24, "frame-requested": 25, "frame-cancelled": 26,
    "frame-received": 27, "frame-size": 28, "frame-timeout": 29,
    "stream-off": 30, "controller-stopped": 31, "dma-stop-quarantined": 32,
    "controller-disable": 33, "controller-disabled": 34, "controller-delete": 35,
    "controller-deleted": 36, "sensor-delete": 37, "sensor-deleted": 38,
    "sccb-delete": 39, "sccb-deleted": 40, "cache-sync": 41,
    "cache-synced": 42, "complete": 43, "failed-clean": 44,
}


def camera_diagnostic_event(data):
    """Map camera evidence onto the existing sanitised runtime_issue schema."""
    if not isinstance(data, dict): return None
    if data.get("kind") == "power":
        read_mask = 0
        for bit, key in enumerate(("pmic_enable_ok", "pmic_camera_ok", "expander_output_ok", "expander_config_ok")):
            if data.get(key) == 1: read_mask |= 1 << bit
        packed = ((read_mask & 0xF) << 32)
        for shift, key in ((24,"pmic_enable"),(16,"pmic_camera"),(8,"expander_output"),(0,"expander_config")):
            packed |= (int(data.get(key,0)) & 0xFF) << shift
        return {"stage":"camera", "reason":"device_proof", "error_code":packed}
    stage = data.get("stage")
    checkpoint = CAMERA_CHECKPOINTS.get(stage)
    if checkpoint is None: return None
    result = {"stage":"camera", "reason":"device_proof", "error_code":checkpoint}
    if type(data.get("internal_free")) is int: result["free_heap"] = data["internal_free"]
    if type(data.get("psram_free")) is int: result["free_psram"] = data["psram_free"]
    return result


def settings_from_control(value: dict):
    if not isinstance(value, dict) or set(value)-SETTINGS: raise ValueError("Unsupported connection settings.")
    def string(key, default, maximum):
        result = value.get(key, default)
        if not isinstance(result, str) or len(result)>maximum or "\0" in result: raise ValueError("Invalid connection field.")
        return result
    port = string("port", "COM4", 80).strip()
    if not port or (os.name == "nt" and not __import__("re").fullmatch(r"COM\d{1,3}", port, __import__("re").I)):
        raise ValueError("Choose a valid serial port.")
    ssid, password = string("ssid", "", 32), string("wifi_password", "", 63)
    if not ssid or len(ssid.encode())>32 or len(password.encode())>63: raise ValueError("Check the Wi-Fi name and password length.")
    lan = string("lan_host", "", 45).strip() or _local_lan_ipv4()
    address = ipaddress.IPv4Address(lan)
    if address.is_loopback or address.is_unspecified or address.is_multicast: raise ValueError("Choose this PC's LAN IPv4 address.")
    timezone_name = string("timezone", "Europe/London", 80)
    try: ZoneInfo(timezone_name)
    except Exception: raise ValueError("Choose a valid IANA timezone, such as Europe/London.") from None
    capture = value.get("capture_ms", 4800)
    if type(capture) is not int or not 2400<=capture<=8000: raise ValueError("Capture duration must be 2400..8000 ms.")
    providers = VoiceProviderSettings.from_env({})
    from dataclasses import replace
    providers = replace(providers, openai_api_key=string("openai_api_key", "", 1024) or None,
        gemini_api_key=string("gemini_api_key", "", 1024) or None)
    return ApplianceSettings(port, 115200, capture, 2, ssid, password, lan, providers, timezone_name)


class DesktopController:
    def __init__(self, emit, *, directory=None, appliance_factory=KadenceAppliance):
        self.emit = emit
        self.services = LocalServices(directory=directory, emit=emit)
        self.appliance_factory = appliance_factory
        self.app = None
        self.task = None
        self.state = "stopped"
        self._lifecycle = asyncio.Lock()
        self._media = None

    async def start(self):
        await self.services.start()
        self.emit("ready", {"protocol": 1})
        self.emit("utilities", await self.services.snapshot())

    def state_event(self, name, data):
        if name == "server": self.state = data["state"]
        self.emit(name, data)

    async def stop_server(self):
        self.state = "stopping"; self.emit("server", {"state": self.state})
        if self._media:
            self._media.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self._media
            self._media = None
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self.task
            self.task = None
        elif self.app:
            await self.app.close()
        self.app = None
        self.state = "stopped"; self.emit("server", {"state": self.state})

    async def start_server(self, args):
        if self.state != "stopped": raise ValueError("Server is already starting or running.")
        settings = settings_from_control(args)
        self.services.reminders.timezone_name = settings.timezone_name
        self.app = self.appliance_factory(settings, services=self.services, emit=self.state_event)
        self.state = "starting"; self.emit("server", {"state": self.state})
        self.task = asyncio.create_task(self._serve(self.app), name="kadence-server")
        voice_ready = not settings.providers.missing_credentials()
        return {"message": "Starting server." if voice_ready else "Starting server. Add OpenAI and Gemini keys for voice; local utilities remain available.", "voice_credentials_ready": voice_ready}

    async def _serve(self, app):
        failure = None
        try:
            await app.run_forever()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure = type(exc).__name__
        finally:
            await app.close()
            if self.app is app:
                self.app = None
                self.state = "stopped"
                self.emit("server", {"state": "stopped", "error": failure})

    async def command(self, action, args):
        if action == "speech_check":
            if set(args)-{"local"} or type(args.get("local", False)) is not bool:
                raise ValueError("Invalid speech check options.")
            async with self._lifecycle:
                if self.state != "stopped": raise ValueError("Stop the server before checking speech.")
                from .speech_output import synthesize_local
                from .voice_providers import EdgeNeuralTTS
                started = time.monotonic(); stages = []
                async def progress(stage):
                    stages.append(stage); self.emit("provider_stage", {"stage": stage})
                text = "Kadence speech check. System ready."
                pcm = (await synthesize_local(text, progress_sink=progress) if args.get("local") else
                       await EdgeNeuralTTS().synthesize_pcm(text, progress_sink=progress))
                local = bool(args.get("local")) or "tts_fallback" in stages
                if not any(pcm): raise RuntimeError("Speech check returned silent audio.")
                return {"pcm_bytes": len(pcm), "elapsed_ms": round((time.monotonic()-started)*1000),
                    "local_voice": local, "message": ("Windows voice" if local else "Sonia") +
                    " generated audio successfully. Start the server and try a voice turn to check robot playback."}
        if action == "timezone" and self.state != "stopped":
            raise ValueError("Stop the server before changing its timezone.")
        if action in {"server_start", "server_stop", "server_restart"}:
            async with self._lifecycle:
                if action != "server_start": await self.stop_server()
                if action != "server_stop": return await self.start_server(args)
                return {"message": "Server stopped. Local reminders remain active while Kadence is open."}
        if action == "media_cancel":
            app = self.app
            if self._media: self._media.cancel()
            if app and app._body:
                await app._handle_touch_cancel(app._body, __import__("types").SimpleNamespace(payload={"trigger": "touch"}))
            return {"message": "Cancellation requested."}
        if action.startswith("device.") or action.startswith("game."):
            if not self.app or not self.app._body: raise RuntimeError("Connect the robot first.")
            if action == "game.start" and self.app._voice_task and not self.app._voice_task.done():
                raise RuntimeError("Wait for the current voice or camera task before starting the game.")
            result = await request_device(self.app._body.host, action, args)
            self.emit("device", result.payload)
            return {"message": "Device setting applied."}
        if action in {"camera_capture", "camera_describe", "camera_clear", "camera_save"}:
            if not self.app: raise RuntimeError("Start the server to use the camera.")
            if action == "camera_clear": self.app.vision.clear(); return {"message": "Transient image cleared."}
            if action == "camera_save": return await self.app.vision.save(self.services.directory, self.services.store, args["project_id"])
            if self._media and not self._media.done(): raise RuntimeError("Camera is busy.")
            coroutine = self.app.capture_snapshot() if action == "camera_capture" else self.app.vision.describe(args.get("question", "What is visible?"), self.app.settings.providers)
            self._media = asyncio.create_task(coroutine, name="kadence-camera-ui")
            try: return await self._media
            finally: self._media = None
        return await self.services.command(action, args)

    async def close(self):
        await self.stop_server()
        await self.services.close()


async def run_worker(incoming, outgoing):
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue(maxsize=32)
    def emit(name, data):
        raw = json.dumps({"v": 1, "event": name, "data": data}, ensure_ascii=True, allow_nan=False)
        if len(raw)>MAX_OUTPUT: raise ValueError("control response exceeds limit")
        outgoing.write(raw+"\n"); outgoing.flush()
    def camera_emit(data):
        event = camera_diagnostic_event(data)
        if event is not None: emit("runtime_issue", event)
    set_camera_diagnostic_sink(camera_emit)
    def enqueue(value):
        if queue.full():
            while not queue.empty(): queue.get_nowait()
            queue.put_nowait(None)
        else: queue.put_nowait(value)
    def read_input():
        while True:
            raw = incoming.readline(MAX_INPUT+1)
            if not raw or len(raw)>MAX_INPUT or not raw.endswith("\n"):
                loop.call_soon_threadsafe(enqueue, None); return
            try: value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, RecursionError): value = {"invalid": True}
            loop.call_soon_threadsafe(enqueue, value)
    threading.Thread(target=read_input, daemon=True, name="kadence-control-input").start()
    controller = DesktopController(emit)
    active = set()
    async def dispatch(message):
        ident = message.get("id", 0)
        try:
            result = await controller.command(message["action"], message.get("args", {}))
            emit("result", {"id": ident, "ok": True, "result": result})
        except asyncio.CancelledError:
            emit("result", {"id": ident, "ok": False, "message": "Operation cancelled."})
        except (ValueError, RuntimeError) as exc:
            message_text = str(exc) if type(exc) in {ValueError, RuntimeError} else "Operation failed. Check connection and configuration."
            emit("result", {"id": ident, "ok": False, "message": message_text[:240]})
        except Exception:
            emit("result", {"id": ident, "ok": False, "message": "Operation failed. Check connection and configuration."})
    try:
        await controller.start()
        while True:
            message = await queue.get()
            if message is None: break
            if not isinstance(message, dict) or set(message)-{"v", "id", "action", "args"} or message.get("v")!=1 or type(message.get("id")) is not int or not isinstance(message.get("action"),str) or not isinstance(message.get("args",{}),dict):
                emit("control", {"state": "invalid_request"}); continue
            if message["action"] == "quit": break
            if len(active)>=8:
                emit("result", {"id":message["id"], "ok":False,"message":"Wait for an active operation to finish."}); continue
            task = asyncio.create_task(dispatch(message))
            active.add(task); task.add_done_callback(active.discard)
    finally:
        set_camera_diagnostic_sink(None)
        for task in active: task.cancel()
        await asyncio.gather(*active, return_exceptions=True)
        await controller.close()
        emit("closed", {"clean": True})


def main():
    incoming, outgoing = sys.stdin, sys.stdout
    if incoming is None or outgoing is None: return 2
    with open(os.devnull, "w") as discard, contextlib.redirect_stdout(discard), contextlib.redirect_stderr(discard):
        try: asyncio.run(run_worker(incoming, outgoing))
        except KeyboardInterrupt: pass
        except Exception:
            outgoing.write('{"v":1,"event":"fatal","data":{"message":"Local services could not start."}}\n'); outgoing.flush()
            return 2
    return 0


if __name__ == "__main__": raise SystemExit(main())
