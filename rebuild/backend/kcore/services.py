"""The shared, provider-independent desktop and voice utility service."""
from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from .context_store import ContextStore, default_data_dir
from .local_tools import make_local_tools
from .integrations import register_integrations
from .reminders import Reminders
from .reminder_time import clock_context
from .storage import KadencePaths
from .utility_store import UtilityStore
from .workbench import register_workbench, convert, ohms_law, resistor_value
from .local_tools import schema, string
from .tool_bridge import KadenceToolSpec


class LocalServices:
    def __init__(self, directory: Path | None = None, timezone_name="Europe/London", emit=None):
        self.paths = KadencePaths.for_root(directory or default_data_dir())
        self.directory = self.paths.root
        self.context = ContextStore(self.directory)
        self.store = UtilityStore(self.directory)
        ZoneInfo(timezone_name)
        self.reminders = Reminders(self.store, timezone_name)
        self.emit = emit or (lambda name, data: None)
        self.tools = None
        self._scheduler = None
        self._draft = None
        self._draft_expires = 0.0
        self.look_handler = None
        self.camera_handler = None

    async def start(self):
        await asyncio.to_thread(self.paths.prepare)
        await self.context.start()
        await self.store.start()
        self.tools = make_local_tools(self.context, timezone_name=self.reminders.timezone_name)
        register_workbench(self.tools, self.store)
        async def look(args):
            from .vision_provider import VisionServiceError
            if self.look_handler is None: return {"spoken":"Start the server and connect the robot before asking me to look."}
            try: return await self.look_handler(args["question"])
            except VisionServiceError as exc:
                return {"spoken":str(exc), "description_status":"failed", "reason":exc.reason}
            except (RuntimeError,ValueError) as exc:
                return {"spoken":str(exc) if type(exc) in {RuntimeError,ValueError} else "The camera look failed. Check Vision on the PC."}
        self.tools.register(KadenceToolSpec("desk_look", "Take a fresh snapshot using the saved camera selection: UnitV2 extra camera, built-in StackChan camera, or AUTO. Describe visible objects or large labels. Only when the current user asks what you can see, to look or read. Requires Gemini for image description even with Ollama reasoning. No person identification.",
            schema({"question": string(500)}, "question"), look, timeout=28))
        from .camera_voice import CAMERA_CHANGES
        async def camera(args):
            if self.camera_handler is None: return {"spoken":"Camera controls are available in the desktop server."}
            return await self.camera_handler(args.get("command","status"))
        self.tools.register(KadenceToolSpec("camera_status","Read actual camera selection, privacy, automatic perception and latest recognition/greeting status. Both UnitV2 and StackChan are supported; status is not a fresh image.",schema({}),camera))
        self.tools.register(KadenceToolSpec("camera_control","Change a camera setting only at the owner's explicit request. Privacy and lifecycle checks always apply. Enabling greetings alone does not enable automatic perception.",schema({"command":{"type":"string","enum":list(CAMERA_CHANGES)}},"command"),camera,timeout=12,writes=True))
        try:
            register_integrations(self.tools)
        except ValueError:
            self.emit("integration", {"state": "configuration_required"})
        self._scheduler = asyncio.create_task(self._schedule(), name="kadence-reminders")

    async def close(self):
        if self._scheduler:
            self._scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self._scheduler
            self._scheduler = None
        if self.tools: await self.tools.close()
        await self.store.close()
        await self.context.close()

    async def _schedule(self):
        while True:
            try:
                due = await self.reminders.tick()
                if due:
                    self.emit("reminders_due", {"count": len(due)})
                    self.emit("utilities", await self.snapshot())
            except (OSError, RuntimeError) as exc:
                self.emit("storage", {"state": "unavailable", "error": type(exc).__name__})
            except Exception:
                self.emit("storage", {"state": "unavailable"})
            await asyncio.sleep(1)

    async def snapshot(self):
        return {"clock": clock_context(self.reminders.timezone_name),
                "reminders": await self.store.call("reminder_list"),
                "projects": await self.store.call("project_list")}

    async def command(self, action: str, args: dict):
        if action == "utilities":
            result = await self.snapshot()
            self.emit("utilities", result)
            return result
        if action == "timezone":
            name = args.get("timezone")
            try:
                if not isinstance(name, str) or len(name) > 80: raise ValueError()
                ZoneInfo(name)
            except Exception:
                raise ValueError("Choose a valid IANA timezone, such as Europe/London.") from None
            self.reminders.timezone_name = name
            self._draft = None
            result = {"message": "Local timezone applied."}
        elif action == "reminder_create":
            reply, self._draft = await self.reminders.create(args["text"], args["when"])
            self._draft_expires = time.monotonic()+120
            result = {"message": reply, "clarification": self._draft is not None}
        elif action == "reminder_answer":
            draft, self._draft = self._draft, None
            if not draft or time.monotonic() > self._draft_expires:
                raise ValueError("Reminder clarification expired. Enter the full request again.")
            value = await self.reminders.voice_request(args["answer"], draft)
            if value is None: raise ValueError("Enter a date or time, or cancel.")
            reply, self._draft = value
            self._draft_expires = time.monotonic()+120
            result = {"message": reply, "clarification": self._draft is not None}
        elif action == "focus_start":
            minutes = args.get("minutes", 25)
            if type(minutes) is not int or not 1 <= minutes <= 180: raise ValueError("Focus must be 1..180 minutes")
            reply, _ = await self.reminders.create("Focus session finished. Time for a break.", f"in {minutes} minutes", kind="focus", extra={"break_minutes": 5})
            result = {"message": reply}
        elif action == "break_start": result = await self.reminders.start_break(args["id"])
        elif action in {"reminder_cancel", "reminder_dismiss", "reminder_snooze", "project_add", "project_list", "entry_add", "entry_list", "entry_done", "entry_delete"}:
            allowed = {
                "reminder_cancel": {"id"}, "reminder_dismiss": {"id"}, "reminder_snooze": {"id", "minutes"},
                "project_add": {"name"}, "project_list": set(), "entry_add": {"project_id", "kind", "text"},
                "entry_list": {"project_id", "query"}, "entry_done": {"id", "done"}, "entry_delete": {"id"},
            }[action]
            if set(args)-allowed: raise ValueError("Unsupported utility argument")
            result = await self.store.call(action, **args)
        elif action == "convert": return convert(**args)
        elif action == "ohms": return ohms_law(**args)
        elif action == "resistor": return resistor_value(args["bands"])
        elif action == "local_tool":
            name = args["name"]
            if name not in {"clock", "calculate", "recall", "task_list", "weather", "home_status", "camera_status"}:
                raise ValueError("Unsupported desktop tool")
            arguments = dict(args.get("arguments", {}))
            if name == "clock": arguments.setdefault("timezone", self.reminders.timezone_name)
            return await self.tools.execute(name, arguments)
        else: raise ValueError("Unknown utility command")
        # Reads must not trigger the UI's refresh -> entry_list -> refresh loop.
        if action not in {"project_list", "entry_list"}:
            self.emit("utilities", await self.snapshot())
        return result
