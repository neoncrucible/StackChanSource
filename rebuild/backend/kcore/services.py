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
from .utility_store import UtilityStore
from .workbench import register_workbench, convert, ohms_law, resistor_value
from .local_tools import schema, string
from .tool_bridge import KadenceToolSpec


class LocalServices:
    def __init__(self, directory: Path | None = None, timezone_name="Europe/London", emit=None):
        self.directory = directory or default_data_dir()
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

    async def start(self):
        await self.context.start()
        await self.store.start()
        self.tools = make_local_tools(self.context, timezone_name=self.reminders.timezone_name)
        register_workbench(self.tools, self.store)
        async def look(args):
            if self.look_handler is None: raise RuntimeError("Camera is disconnected")
            return await self.look_handler(args["question"])
        self.tools.register(KadenceToolSpec("desk_look", "Take one deliberate camera snapshot and describe visible objects or large labels. Only use when the current user asks to look, read this, or asks what they are holding. No person identification.",
            schema({"question": string(500)}, "question"), look, timeout=28))
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
            if name not in {"clock", "calculate", "recall", "task_list", "weather", "home_status"}:
                raise ValueError("Unsupported desktop tool")
            arguments = dict(args.get("arguments", {}))
            if name == "clock": arguments.setdefault("timezone", self.reminders.timezone_name)
            return await self.tools.execute(name, arguments)
        else: raise ValueError("Unknown utility command")
        # Reads must not trigger the UI's refresh -> entry_list -> refresh loop.
        if action not in {"project_list", "entry_list"}:
            self.emit("utilities", await self.snapshot())
        return result
