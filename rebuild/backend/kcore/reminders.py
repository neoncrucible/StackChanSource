from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .reminder_time import Resolution, resolve_when, split_reminder_request, spoken_due, temporal_numbers
from .utility_store import UtilityStore


@dataclass(frozen=True)
class ReminderDraft:
    text: str
    resolution: Resolution


class Reminders:
    def __init__(self, store: UtilityStore, timezone_name="Europe/London", now: Callable[[], datetime] | None = None):
        self.store, self.timezone_name = store, timezone_name
        self.now = now or (lambda: datetime.now(timezone.utc))

    async def create(self, text: str, when: str, *, day_hint="", clock_hint="", kind="reminder", extra=None) -> tuple[str, ReminderDraft | None]:
        if not isinstance(text, str) or not text.strip() or len(text) > 800:
            return "What should I remind you to do? Please keep it to a short sentence.", None
        now = self.now()
        resolution = resolve_when(when, now=now, timezone_name=self.timezone_name, day_hint=day_hint, clock_hint=clock_hint)
        if resolution.due is None:
            return resolution.question, ReminderDraft(text, resolution)
        item = await self.store.call("reminder_add", text=text, due=resolution.due.timestamp(), timezone=self.timezone_name,
                                     kind=kind, extra=extra or {}, now=now.timestamp())
        return f"Reminder {item['id']} set for {spoken_due(resolution.due, self.timezone_name)}: {item['text']}", None

    async def voice_request(self, text: str, draft: ReminderDraft | None = None) -> tuple[str, ReminderDraft | None] | None:
        normal = temporal_numbers(text)
        parsed = split_reminder_request(text)
        if parsed:
            return await self.create(*parsed)
        if normal in ("read my reminders", "what are my reminders", "list my reminders", "what reminders do i have"):
            rows = await self.store.call("reminder_list")
            if not rows:
                return "You have no active reminders.", None
            lines = [f"{row['id']}: {row['text']}, {spoken_due(datetime.fromtimestamp(row['due'], timezone.utc), row['timezone'])}"
                     for row in rows[:5]]
            return "; ".join(lines)[:1200], None
        change = re.fullmatch(r"(cancel|dismiss) reminder (\d+)", normal)
        snooze = re.fullmatch(r"snooze reminder (\d+) (?:for )?(\d+) minutes?", normal)
        if change:
            changed = await self.store.call("reminder_" + change[1], id=int(change[2]))
            return ("Reminder cancelled." if change[1] == "cancel" else "Reminder dismissed.") if changed else "That reminder is no longer active.", None
        if snooze:
            changed = await self.store.call("reminder_snooze", id=int(snooze[1]), minutes=int(snooze[2]), now=self.now().timestamp())
            return f"Snoozed for {snooze[2]} minutes." if changed else "That reminder is no longer active.", None
        focus = re.fullmatch(r"(?:start|begin) (?:a )?(?:(\d+) minute )?focus(?: session)?", normal)
        if focus:
            minutes = int(focus[1] or 25)
            if not 1 <= minutes <= 180:
                return "Choose a focus session from one to 180 minutes.", None
            return await self.create("Focus session finished. Time for a break.", f"in {minutes} minutes", kind="focus", extra={"break_minutes": 5})
        if draft:
            if normal in ("cancel", "no", "never mind", "nevermind"):
                return "All right. No reminder was scheduled.", None
            # Only a bounded temporal answer continues a draft; a new topic abandons it.
            temporal_words = {"am", "pm", "in", "the", "morning", "afternoon", "evening", "tomorrow", "today", "tonight", "noon", "midnight", "first", "second", "on", "at", "next", "past", "to", "half", "quarter", "please", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "seconds", "minutes", "hours", "days", "second", "minute", "hour", "day"}
            if len(text) <= 120 and normal and all(word in temporal_words for word in re.findall(r"[a-z]+", normal)):
                r = draft.resolution
                return await self.create(draft.text, text, day_hint=r.day, clock_hint=r.clock)
        return None

    async def tick(self):
        return await self.store.call("claim_due", now=self.now().timestamp())

    async def start_break(self, reminder_id: int):
        original = await self.store.call("reminder_get", id=reminder_id)
        if not original or original["kind"] != "focus" or original["state"] != "due":
            raise ValueError("select a completed focus session")
        minutes = int(json.loads(original["extra"]).get("break_minutes", 5))
        # Stable key makes repeated UI clicks idempotent even after a process restart.
        now = self.now().timestamp()
        result = await self.store.call("reminder_add", text="Break finished. Ready to focus again?", due=now+minutes*60,
            timezone=self.timezone_name, kind="break", request_key=f"focus-break-{reminder_id}", now=now)
        await self.store.call("reminder_dismiss", id=reminder_id)
        return result
