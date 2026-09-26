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
from .services import LocalServices
from .voice_providers import VoiceProviderSettings
from .ollama_models import DEFAULT_OLLAMA_MODEL, model_name, installed_models

MAX_INPUT = 32768
MAX_OUTPUT = 1024*1024
SETTINGS = frozenset({"port", "ssid", "lan_host", "timezone", "capture_ms", "openai_api_key", "gemini_api_key", "wifi_password", "thinker_provider", "ollama_model", "audio_output"})


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
        gemini_api_key=string("gemini_api_key", "", 1024) or None,
        thinker_provider=string("thinker_provider", "gemini", 16),
        ollama_model=model_name(string("ollama_model", DEFAULT_OLLAMA_MODEL, 160)))
    return ApplianceSettings(port, 115200, capture, 2, ssid, password, lan, providers, timezone_name,
                             string("audio_output", "robot", 16), not bool(string("lan_host", "", 45).strip()))


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
        self._network_media = False
        self._camera_settings_lock = asyncio.Lock()
        self.services.camera_handler = self.camera_voice

    async def camera_voice(self, command):
        from dataclasses import asdict
        from .camera_manager import CameraConfig
        from .camera_voice import CAMERA_CHANGES
        config = self.app.camera.config if self.app else CameraConfig.load(self.services.paths.root)
        if command == "status":
            source = {"unitv2-camera":"UnitV2 extra camera","robot-camera":"built-in StackChan camera","auto":"AUTO, preferring the UnitV2 extra camera"}[config.source]
            perception = getattr(self.app,"perception",None)
            gate = perception.gate() if perception else "stopped"
            gate = {"ready":"enabled","observation_only":"off","policy_off":"off by policy","privacy":"blocked by privacy","stopped":"stopped","lifecycle_check_required":"waiting for a passed camera start and stop test","enrolling":"paused for a local face operation"}.get(gate,"unavailable")
            camera = getattr(self.app,"camera",None)
            producer = camera.unitv2.status.get("state","UNKNOWN") if camera else "UNKNOWN"
            spoken = f"My selected source is {source}. Privacy is {'on' if config.privacy else 'off'}. UnitV2 producer: {producer}. Automatic perception: {gate.replace('_',' ')}. Greetings are {'on' if config.greetings else 'off'}."
            if perception:
                age = f" {int(max(0,perception.clock()-perception._last_capture))} seconds ago" if perception._last_capture is not None else ""
                spoken += " Last local look" + age + ": " + perception.last_result + " " + perception.last_greeting
            return {"spoken":spoken,"settings":asdict(config)}
        if command not in CAMERA_CHANGES: raise ValueError("Unsupported camera command.")
        patches = {
            "privacy_on":{"privacy":True},"privacy_off":{"privacy":False},
            "perception_on":{"perception_enabled":True,"policy":config.policy if config.policy!="OFF" else "EVENT_ONLY"},
            "perception_off":{"perception_enabled":False},
            "greetings_on":{"greetings":True},"greetings_off":{"greetings":False},
            "unitv2":{"source":"unitv2-camera"},"robot":{"source":"robot-camera"},"auto":{"source":"auto"},
            "aware":{"policy":"AWARE","perception_enabled":True},"event_only":{"policy":"EVENT_ONLY","perception_enabled":True},
        }
        try:
            if command in patches:
                await self.command("camera_patch",patches[command])
                message = "Saved: " + CAMERA_CHANGES[command] + "."
                saved = self.app.camera.config if self.app else CameraConfig.load(self.services.paths.root)
                if command == "greetings_on" and (not saved.perception_enabled or saved.policy=="OFF"):
                    message += " Automatic perception is still off; enable it when you want me to look for arrivals."
                if command in {"perception_on","aware","event_only"} and saved.privacy:
                    message += " Privacy is still on, so camera access remains blocked."
                if command == "privacy_on" and self.app and not self.app.camera.unitv2.status.get("stop_confirmed"):
                    message += " Access is blocked, but the UnitV2 producer stop is not confirmed."
            else:
                mode={"stop":"STOPPED","on_demand":"ON_DEMAND","keep_ready":"KEEP_READY"}[command]
                await self.command("unitv2_mode",{"mode":mode})
                status=self.app.camera.unitv2.status
                message = f"UnitV2 mode is {mode.replace('_',' ').lower()}. Producer state: {status.get('state','UNKNOWN')}."
                if mode!="KEEP_READY": message += " Stop confirmed." if status.get("stop_confirmed") else " Stop is not confirmed."
            self.emit("vision_activity",{"kind":"voice_control","message":message})
            return {"spoken":message}
        except (RuntimeError,ValueError) as exc:
            return {"spoken":str(exc) if type(exc) in {RuntimeError,ValueError} else "The camera change was not confirmed. Check Vision on the PC."}

    async def start(self):
        await self.services.start()
        from .camera_manager import CameraConfig
        from dataclasses import asdict
        self.emit("camera_settings", asdict(CameraConfig.load(self.services.paths.root)))
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
        # The timezone is authoritative for all new relative-date requests.
        self.services.reminders.timezone_name = settings.timezone_name
        self.app = self.appliance_factory(settings, services=self.services, emit=self.state_event)
        self.state = "starting"; self.emit("server", {"state": self.state})
        self.task = asyncio.create_task(self._serve(self.app), name="kadence-server")
        voice_ready = not settings.providers.missing_credentials()
        return {"message": "Starting server." if voice_ready else "Starting server. Add credentials for the selected voice services; local utilities remain available.", "voice_credentials_ready": voice_ready}

    async def _serve(self, app):
        failure = None
        try:
            await app.run_forever()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure = type(exc).__name__
        finally:
            # Also covers failure before the appliance enters its main loop.
            await app.close()
            if self.app is app:
                self.app = None
                self.state = "stopped"
                self.emit("server", {"state": "stopped", "error": failure})

    async def command(self, action, args):
        if action == "face_model_check":
            from .local_faces import LocalFaces
            from .camera_manager import settled_thread
            import io
            from PIL import Image
            image=io.BytesIO(); Image.new("RGB",(320,240)).save(image,format="PNG")
            loop=asyncio.get_running_loop()
            faces=LocalFaces(self.services.paths.root, progress=lambda stage:loop.call_soon_threadsafe(self.emit,"model_check",{"stage":stage}))
            self.emit("model_check", {"stage":"preload_cv2"})
            faces.preload(progress=lambda stage:self.emit("model_check", {"stage":stage}))
            result=await settled_thread(faces.analyze,image.getvalue())
            return {"model_health":faces.health,"faces":len(result)}
        if action in {"camera_settings","camera_patch"}:
            from .camera_manager import CameraConfig
            from dataclasses import asdict
            async with self._camera_settings_lock:
                if action == "camera_patch":
                    previous = self.app.camera.config if self.app else CameraConfig.load(self.services.paths.root)
                    args = {**asdict(previous),**args}
                # Privacy must remain reachable even while an address edit is invalid.
                if args.get("privacy") is True:
                    from dataclasses import replace
                    previous = self.app.camera.config if self.app else CameraConfig.load(self.services.paths.root)
                    blocked = replace(previous, privacy=True)
                    if self.app:
                        self.app.camera.configure(blocked)
                        self.app.vision.clear()
                        if self._media: self._media.cancel()
                    blocked.save(self.services.paths.root)
                    if self.app and self.app.perception: await self.app.perception.reset("privacy")
                    if self.app:
                        with contextlib.suppress(Exception): await self.app.camera.settle_settings()
                try:
                    config = CameraConfig.parse(args)
                    if (not config.privacy and config.perception_enabled and config.policy != "OFF" and config.source != "robot-camera"
                            and (not self.app or not self.app.camera.unitv2.verified)):
                        raise ValueError("Run TEST START / STOP successfully before enabling automatic UnitV2 perception.")
                except ValueError:
                    self.emit("camera_settings", asdict(CameraConfig.load(self.services.paths.root)))
                    raise
                if self.app and config == self.app.camera.config:
                    config.save(self.services.paths.root)
                    self.emit("camera_settings",asdict(config))
                    return {"message":"Camera settings saved."}
                # Apply privacy immediately before any asynchronous work or disk I/O.
                if self.app:
                    self.app.camera.configure(config)
                    self.app.vision.clear()
                    if self._media: self._media.cancel()
                config.save(self.services.paths.root)
                self.emit("camera_settings", asdict(config))
                if self.app and self.app.perception: await self.app.perception.reset("settings_changed")
                if self.app:
                    with contextlib.suppress(Exception): await self.app.camera.settle_settings()
            return {"message": "Camera policy saved."}
        if action in {"unitv2_mode", "unitv2_status", "unitv2_check"}:
            if not self.app: raise RuntimeError("Start the server to control UnitV2.")
            camera = self.app.camera
            if action == "unitv2_status": return await camera.unitv2.refresh(camera.config.address)
            if self.app.perception: await self.app.perception.interrupt()
            if action == "unitv2_mode":
                await camera.unitv2_control(args.get("mode"))
                if args.get("mode") == "STOPPED": self.app.vision.clear()
                return {"message":"UnitV2 mode applied; see producer status for confirmation."}
            camera.check()
            await camera.unitv2_control("ON_DEMAND")
            for cycle in range(2):
                frame = await camera.acquire(source="unitv2-camera")
                status = await camera.unitv2.refresh(camera.config.address)
                if not status["stop_confirmed"]: raise RuntimeError("UnitV2 stop was not confirmed.")
                camera.check(frame.generation)
                self.app.vision.accept_frame(frame)
                self.emit("unitv2_check", {"cycle":cycle+1,"state":"passed"})
            camera.unitv2.record_verified(self.services.paths.root)
            return {"message":"UnitV2 lifecycle PASS: two fresh captures, two confirmed stops. Producer is stopped."}
        if action in {"face_profiles", "face_photos", "face_preview_clear", "face_forget", "face_enroll", "face_update", "vision_activity", "database_backup", "recognition_test", "perception_test"}:
            from .perception_store import PerceptionStore
            from .camera_manager import settled_thread
            store = PerceptionStore(self.services.paths.database)
            if action == "face_preview_clear":
                self.emit("face_preview",{})
                return {"message":"Face preview cleared."}
            if action == "face_photos":
                return {"person_id":args.get("person_id"),"photos":await settled_thread(lambda:store.call("photos",person=args.get("person_id")))}
            if action == "database_backup":
                from .storage import backup_sqlite
                import uuid
                destination=self.services.paths.backups_dir / f"kadence-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.sqlite3"
                await settled_thread(backup_sqlite,self.services.paths.database,destination)
                return {"message":f"Database backup saved: {destination}. Review photos are separate files in the Kadence media folder.","path":str(destination)}
            if action == "vision_activity":
                return {"items":await settled_thread(lambda:store.call("activity"))}
            if action in {"face_forget","face_update"}:
                if self.app and self.app.perception:
                    self.app.camera.configure(self.app.camera.config)
                    if self._media: self._media.cancel()
                    await self.app.perception.reset("profile_removed")
                if action == "face_forget": await settled_thread(lambda: store.call("forget", person=args.get("person_id")))
                else: await settled_thread(lambda:store.call("update_person",person=args.get("person_id"),name=args.get("name"),recognition_enabled=args.get("recognition_enabled"),greeting_enabled=args.get("greeting_enabled")))
            if action in {"face_enroll","recognition_test","perception_test"}:
                if not self.app or not self.app.perception: raise RuntimeError("Start the server before using local recognition.")
                if self._media and not self._media.done(): raise RuntimeError("Camera is busy.")
                pc = self.app.perception
                if pc.busy(): raise RuntimeError("Voice is busy. Wait for the reply to finish.")
                if action == "perception_test":
                    completed = pc._completed_bursts
                    if not pc.request("gesture",defer=False):
                        reason={"observation_only":"enable Automatic Perception first","policy_off":"choose EVENT ONLY or AWARE","privacy":"turn Privacy off first","stopped":"start the server and select ON DEMAND","lifecycle_check_required":"pass TEST START / STOP first","enrolling":"wait for the face operation to finish"}.get(pc.gate(),"camera busy or burst cooldown; wait 20 seconds")
                        raise RuntimeError("Test event blocked: " + reason + ".")
                    async def event_test():
                        await pc.task
                        if pc._completed_bursts == completed:
                            raise RuntimeError("Automatic test did not complete: " + pc.health.replace('_',' ') + ". Check Activity and camera status.")
                        return {"message":"Automatic event finished. " + pc.last_result + " " + pc.last_greeting}
                    operation=event_test()
                elif action == "recognition_test": operation=pc.test_recognition()
                else: operation=pc.enroll(args.get("name"),args.get("person_id"),keep_photos=args.get("keep_photos",False))
                self._network_media = True
                self._media = asyncio.create_task(operation)
                try: return await self._media
                finally: self._media = None; self._network_media = False
            return {"persons":await settled_thread(lambda: store.call("persons")),"database":str(self.services.paths.database),"message":"Local face profiles loaded." if action=="face_profiles" else "Profile changes saved."}
        if action == "ollama_models":
            if args: raise ValueError("Model discovery takes no arguments.")
            return {"models": await installed_models()}
        if action == "ollama_reply_check":
            if set(args) != {"model"}: raise ValueError("Choose an Ollama model to test.")
            model = model_name(args["model"])
            async with self._lifecycle:
                if self.state != "stopped": raise ValueError("Stop the server before testing the Ollama reply.")
                from .companion import Companion
                from .voice_providers import OllamaThinker
                from .thinking import request_plan, ThinkingServiceError, issue_data, failure_message
                thinker = OllamaThinker(model=model)
                # Full voice planner context, but no user history, tool execution,
                # camera, microphone or speech. A discovered tag is not this check.
                companion = Companion(self.services.tools, reminders=self.services.reminders,
                                      timezone_name=self.services.reminders.timezone_name)
                prompt = companion.planner_prompt("For this diagnostic check, reply briefly that you are ready. Do not request a tool.")
                started = time.monotonic()
                try:
                    plan = await request_plan(thinker, prompt)
                    if set(plan) != {"reply"}:
                        raise ThinkingServiceError("invalid_plan")
                except ThinkingServiceError as exc:
                    data = issue_data(thinker, exc)
                    self.emit("runtime_issue", data)
                    return {"passed": False, "reason": exc.reason,
                            "elapsed_ms": round((time.monotonic()-started)*1000),
                            "message": failure_message(exc.reason, "ollama")}
                elapsed = round((time.monotonic()-started)*1000)
                for stage, elapsed_ms in thinker.timings.items():
                    self.emit("timing", {"stage": stage, "elapsed_ms": elapsed_ms})
                self.emit("thinking_check", {"provider": "ollama", "state": "ready", "elapsed_ms": elapsed})
                return {"passed": True, "elapsed_ms": elapsed,
                        "message": f"Ollama generated a valid Kadence reply in {elapsed/1000:.1f}s. Start the server and try a voice turn."}
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
            self.emit("face_preview",{})
            app = self.app
            if self._media: self._media.cancel()
            if app and app._body and not self._network_media:
                await app._handle_touch_cancel(app._body, __import__("types").SimpleNamespace(payload={"trigger": "touch"}))
            return {"message": "Cancellation requested."}
        if action.startswith("device."):
            if not self.app or not self.app._body: raise RuntimeError("Connect the robot first.")
            result = await request_device(self.app._body.host, action, args)
            self.emit("device", result.payload)
            return {"message": "Device setting applied."}
        if action in {"camera_capture", "camera_describe", "camera_look", "camera_clear", "camera_save"}:
            if not self.app: raise RuntimeError("Start the server to use the camera.")
            if action == "camera_clear": self.app.vision.clear(); return {"message": "Transient image cleared."}
            if action == "camera_save": return await self.app.vision.save(self.services.paths, self.services.store, args["project_id"])
            if self._media and not self._media.done(): raise RuntimeError("Camera is busy.")
            if action == "camera_capture":
                source = args.get("source", "robot-camera")
                if source == "unitv2-camera":
                    address = str(ipaddress.IPv4Address(args.get("address", "")))
                    coroutine = self.app.capture_unitv2_snapshot(address)
                elif source == "robot-camera":
                    coroutine = self.app.capture_snapshot()
                elif source == "auto":
                    coroutine = self.app.capture_camera(source="auto", address=args.get("address"))
                else:
                    raise ValueError("Choose a supported camera source.")
            elif action == "camera_look":
                coroutine = self.app.look_camera(args.get("question", "What is visible?"))
            else:
                coroutine = self.app.vision.describe(args.get("question", "What is visible?"), self.app.settings.providers)
            self._network_media = action == "camera_capture" and args.get("source") in {"unitv2-camera", "auto"}
            self._media = asyncio.create_task(coroutine, name="kadence-camera-ui")
            try: return await self._media
            finally:
                self._media = None
                self._network_media = False
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
    def enqueue(value):
        if queue.full():
            # Bounded work: overload closes this control session cleanly.
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
            # Only project-owned messages may cross into the UI. Never expose
            # provider/serial exception strings (which may include request data).
            from .vision_provider import VisionServiceError
            message_text = str(exc) if type(exc) in {ValueError, RuntimeError, VisionServiceError} else "Operation failed. Check connection and configuration."
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
        for task in active: task.cancel()
        await asyncio.gather(*active, return_exceptions=True)
        await controller.close()
        emit("closed", {"clean": True})


def main():
    incoming, outgoing = sys.stdin, sys.stdout
    if incoming is None or outgoing is None: return 2
    # The protocol never parses appliance print output. Suppress raw adapter and
    # device logs; typed status is the only path to GUI diagnostics.
    with open(os.devnull, "w") as discard, contextlib.redirect_stdout(discard), contextlib.redirect_stderr(discard):
        try:
            # Frozen NumPy/OpenCV native initialization must happen before the
            # control reader or any other worker thread exists. Delayed first
            # import can deadlock the Windows frozen loader after normal host
            # activity even though the same modules work in source runs.
            if getattr(sys, "frozen", False):
                from .local_faces import LocalFaces
                LocalFaces.preload()
                # Initialize the streaming output extension before worker
                # threads, following the frozen native-loader ownership rule.
                import miniaudio
            asyncio.run(run_worker(incoming, outgoing))
        except KeyboardInterrupt: pass
        except Exception:
            outgoing.write('{"v":1,"event":"fatal","data":{"message":"Local services could not start."}}\n'); outgoing.flush()
            return 2
    return 0


if __name__ == "__main__": raise SystemExit(main())
