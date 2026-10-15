from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from .reminder_time import Resolution, request_body, resolve_when, split_reminder_request, spoken_due, temporal_numbers
from .utility_store import UtilityStore


@dataclass(frozen=True)
class ReminderDraft:
    text: str
    resolution: Resolution
    when: str = ""
    reminder_id: int | None = None

    def to_data(self):
        value = asdict(self)
        if self.resolution.due: value['resolution']['due'] = self.resolution.due.isoformat()
        return value

    @classmethod
    def from_data(cls, value):
        value = dict(value)
        resolution = dict(value.pop('resolution'))
        if resolution.get('due'): resolution['due'] = datetime.fromisoformat(resolution['due'])
        return cls(resolution=Resolution(**resolution), **value)


class Reminders:
    def __init__(self, store: UtilityStore, timezone_name="Europe/London", now: Callable[[], datetime] | None = None):
        self.store, self.timezone_name = store, timezone_name
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._recent_id = None
        self._recent_at = 0.0

    async def create(self, text: str, when: str, *, day_hint="", clock_hint="", kind="reminder", extra=None, reminder_id=None) -> tuple[str, ReminderDraft | None]:
        if not isinstance(text, str) or len(text) > 800 or not isinstance(when, str) or len(when) > 240:
            return "What should I remind you to do? Please keep it to a short sentence.", None
        now = self.now()
        resolution = resolve_when(when, now=now, timezone_name=self.timezone_name, day_hint=day_hint, clock_hint=clock_hint)
        if not text.strip():
            if resolution.issue in {'condition', 'recurrence'}:
                return resolution.question, None
            # Hold the resolved instant while asking for the task, so a relative
            # delay does not restart when the owner answers.
            return "What should I remind you to do, Boss?", ReminderDraft('', resolution, when)
        if resolution.due is None:
            return resolution.question, ReminderDraft(text, resolution, when, reminder_id)
        if reminder_id is not None:
            changed = await self.store.call('reminder_reschedule', id=reminder_id, due=resolution.due.timestamp(), timezone=self.timezone_name, now=now.timestamp())
            if not changed: return 'That reminder is no longer active.', None
            self._remember(reminder_id)
            return f"Reminder {reminder_id} moved to {spoken_due(resolution.due, self.timezone_name)}: {text}", None
        item = await self.store.call("reminder_add", text=text, due=resolution.due.timestamp(), timezone=self.timezone_name,
                                     kind=kind, extra=extra or {}, now=now.timestamp())
        self._remember(item['id'])
        return f"Reminder {item['id']} set for {spoken_due(resolution.due, self.timezone_name)}: {item['text']}", None

    def _remember(self, reminder_id):
        self._recent_id, self._recent_at = reminder_id, time.monotonic()

    @staticmethod
    def tool_result(result):
        spoken, draft = result
        return {'spoken': spoken, 'draft': draft.to_data() if draft else None}

    async def manage(self, action, target, when=''):
        rows = await self.store.call('reminder_list')
        normal = temporal_numbers(target)
        if normal in {'it', 'that', 'this', 'that reminder', 'this reminder', 'the last reminder', 'my last reminder', 'last'}:
            matches = [row for row in rows if row['id'] == self._recent_id] if time.monotonic()-self._recent_at < 120 else []
        else:
            key = re.sub(r'^(?:my|the)\s+|\breminder\b', '', normal).strip()
            if key.isdigit(): matches = [row for row in rows if row['id'] == int(key)]
            else: matches = [row for row in rows if key and key in temporal_numbers(row['text'])]
        if len(matches) != 1:
            choices = '; '.join(f"{row['id']}: {row['text']}" for row in (matches or rows)[:5])
            return ('Which reminder do you mean, Boss? ' + choices if rows else 'You have no active reminders.'), None
        row = matches[0]
        if action in {'cancel', 'dismiss'}:
            changed = await self.store.call('reminder_' + action, id=row['id'])
            return (f"Reminder {row['id']} {'cancelled' if action == 'cancel' else 'dismissed'}: {row['text']}" if changed else 'That reminder is no longer active.'), None
        if action not in {'snooze', 'reschedule'}: raise ValueError('Unknown reminder action')
        return await self.create(row['text'], when, reminder_id=row['id'])

    async def voice_request(self, text: str, draft: ReminderDraft | None = None) -> tuple[str, ReminderDraft | None] | None:
        source = request_body(text)
        normal = temporal_numbers(source)
        # Observable camera conditions belong to the actual watch controller.
        from .camera_voice import camera_plan
        camera = camera_plan(text)
        if camera and camera['tool'] == 'tracking_control' and camera['arguments']['action'] == 'watch':
            return None
        parsed = split_reminder_request(text)
        if parsed:
            return await self.create(*parsed)
        if normal in ("read my reminders", "what are my reminders", "list my reminders", "what reminders do i have", "show my reminders", "show me my reminders", "any reminders", "do i have any reminders", "what reminders are set", "what have you set reminders for", "read out my reminders"):
            rows = await self.store.call("reminder_list")
            if not rows:
                return "You have no active reminders.", None
            lines = [f"{row['id']}: {row['text']}, {spoken_due(datetime.fromtimestamp(row['due'], timezone.utc), row['timezone'])}"
                     for row in rows[:5]]
            return "; ".join(lines)[:1200], None
        change = re.fullmatch(r"(cancel|delete|remove|drop|dismiss) ((?:.*\breminder\b.*)|it|that)", normal)
        snooze = re.fullmatch(r"snooze (.+?) (?:for )?(\d+) minutes?", normal)
        move = re.fullmatch(r"(?:move|reschedule|change|postpone) (.+?\breminder(?: \d+)?) (?:to|until|for) (.+)", source, re.I)
        if change:
            return await self.manage('dismiss' if change[1] == 'dismiss' else 'cancel', change[2])
        if snooze:
            reply, proposed = await self.manage('snooze', snooze[1], f'in {snooze[2]} minutes')
            return (f"Snoozed for {snooze[2]} minutes." if ' moved to ' in reply else reply), proposed
        if move: return await self.manage('reschedule', move[1], move[2])
        focus = re.fullmatch(r"(?:start|begin) (?:a )?(?:(\d+) minute )?focus(?: session)?", normal)
        if focus:
            minutes = int(focus[1] or 25)
            if not 1 <= minutes <= 180:
                return "Choose a focus session from one to 180 minutes.", None
            return await self.create("Focus session finished. Time for a break.", f"in {minutes} minutes", kind="focus", extra={"break_minutes": 5})
        if draft:
            if normal in ("cancel", "no", "never mind", "nevermind"):
                return "All right. No reminder was scheduled.", None
            if not draft.text and not re.match(r'^(?:what|who|where|why|how|can|could|hello|hi|track|follow|look|read|show|tell|stop)\b', normal):
                task = re.sub(r'^(?:to|about|that|i need to)\s+', '', source, flags=re.I)
                when = draft.resolution.due.astimezone(ZoneInfo(self.timezone_name)).strftime('%Y-%m-%d at %H:%M') if draft.resolution.due else draft.when
                return await self.create(task, when, day_hint=draft.resolution.day, clock_hint=draft.resolution.clock)
            answer = self._temporal_answer(source)
            if answer is not None:
                r = draft.resolution
                return await self.create(draft.text, answer, day_hint=r.day, clock_hint=r.clock, reminder_id=draft.reminder_id)
        if re.match(r'^(?:actually\b|i meant\b|make (?:it|that)\b|change (?:it|that) to\b)', normal):
            answer = self._temporal_answer(source)
            if answer is not None and time.monotonic()-self._recent_at < 120:
                return await self.manage('reschedule', 'that', answer)
        return None

    @staticmethod
    def _temporal_answer(text):
        normal = temporal_numbers(text)
        for _ in range(3):
            normal = re.sub(r'^(?:(?:actually|yes|no)[, ]+|i meant |make (?:it|that) |change (?:it|that) to |how about |let\'s do )', '', normal)
        normal = re.sub(r'\s+(?:instead|please)$', '', normal)
        words = set('am pm in the morning afternoon evening tomorrow today tonight noon midnight first second on at next past to half quarter monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october november december seconds minutes hours days weeks second minute hour day week after from now and'.split())
        if len(normal) <= 120 and normal and all(word in words for word in re.findall(r'[a-z]+', normal)):
            return normal
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
