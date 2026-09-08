import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kcore.context_store import ContextStore
from kcore.reminder_time import resolve_when, split_reminder_request, clock_context
from kcore.reminders import Reminders
from kcore.utility_store import UtilityStore
from kcore.workbench import convert, ohms_law, resistor_value

UTC = timezone.utc


class CalendarTests(unittest.TestCase):
    def resolve(self, text, now="2026-09-07T14:00:00+00:00", **hints):
        return resolve_when(text, now=datetime.fromisoformat(now), timezone_name="Europe/London", **hints)

    def test_explicit_owner_phrases(self):
        cases = {
            "Remind me at 19:30 to check the print": ("check the print", "at 19:30"),
            "Tomorrow remind me I need to order filament": ("order filament", "Tomorrow"),
            "Remind me to check the print in twenty minutes": ("check the print", "in twenty minutes"),
            "Remind me to check the print at 19:00": ("check the print", "at 19:00"),
            "Remind me to check the machine at work tomorrow at noon": ("check the machine at work", "tomorrow at noon"),
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase): self.assertEqual(split_reminder_request(phrase), expected)

    def test_relative_and_calendar_days_differ_at_dst(self):
        now = "2026-03-28T12:00:00+00:00"
        self.assertEqual(self.resolve("in a day", now).due.isoformat(), "2026-03-29T12:00:00+00:00")
        self.assertEqual(self.resolve("tomorrow at noon", now).due.isoformat(), "2026-03-29T11:00:00+00:00")
        self.assertEqual(self.resolve("in half an hour").due.hour, 14)

    def test_gap_and_both_fold_occurrences(self):
        self.assertEqual(self.resolve("29 March 2026 at 01:30", "2026-03-28T12:00:00+00:00").issue, "dst_gap")
        draft = self.resolve("25 October 2026 at 01:30")
        self.assertEqual(draft.issue, "dst_fold")
        first = self.resolve("first", day_hint=draft.day, clock_hint=draft.clock).due
        second = self.resolve("second", day_hint=draft.day, clock_hint=draft.clock).due
        self.assertEqual(second-first, timedelta(hours=1))
        self.assertEqual(first.hour, 0)
        self.assertEqual(second.hour, 1)

    def test_missing_ambiguous_invalid_and_past_do_not_schedule(self):
        for phrase, issue in (("tomorrow", "missing_time"), ("at 7", "meridian"),
                              ("today at 09:00", "past"), ("31 September at noon", "date"),
                              ("tomorrow at 29:00", "time")):
            with self.subTest(phrase=phrase):
                result = self.resolve(phrase)
                self.assertIsNone(result.due)
                self.assertEqual(result.issue, issue)

    def test_tomorrow_is_local_calendar_and_draft_survives_midnight(self):
        before = "2026-09-07T22:59:00+00:00"
        draft = self.resolve("tomorrow", before)
        self.assertEqual(draft.day, "2026-09-08")
        reply = self.resolve("9 am", "2026-09-07T23:01:00+00:00", day_hint=draft.day)
        self.assertEqual(reply.due.isoformat(), "2026-09-08T08:00:00+00:00")
        self.assertEqual(clock_context("Europe/London", datetime.fromisoformat(before))["tomorrow"], "2026-09-08")


class ReminderStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.context = ContextStore(self.directory)
        await self.context.start()
        await self.context.perform("add", kind="memory", text="existing lab note")
        self.store = UtilityStore(self.directory)
        await self.store.start()
        self.now = datetime(2026, 9, 7, 14, tzinfo=UTC)
        self.reminders = Reminders(self.store, now=lambda: self.now)

    async def asyncTearDown(self): self.temp.cleanup()

    async def test_followup_schedules_once_and_unrelated_question_abandons_draft(self):
        reply, draft = await self.reminders.voice_request("Tomorrow remind me I need to order filament")
        self.assertIn("What time", reply)
        self.assertEqual(await self.store.call("reminder_list"), [])
        self.assertIsNone(await self.reminders.voice_request("What is 2 plus 3?", draft))
        reply, draft = await self.reminders.voice_request("nine am", draft)
        self.assertIsNone(draft)
        self.assertIn("Tuesday 8 September 2026, 09:00 BST", reply)
        self.assertEqual(len(await self.store.call("reminder_list")), 1)

    async def test_overdue_restart_and_concurrent_ticks_have_one_claim(self):
        await self.reminders.create("check print", "in 20 minutes")
        self.now += timedelta(hours=2)
        restarted = Reminders(UtilityStore(self.directory), now=lambda: self.now)
        await restarted.store.start()
        claims = await asyncio.gather(self.reminders.tick(), restarted.tick())
        self.assertEqual(sum(map(len, claims)), 1)
        robot = await asyncio.gather(self.store.call("claim_robot"), restarted.store.call("claim_robot"))
        self.assertEqual(sum(map(len, robot)), 1)
        self.assertEqual(await restarted.store.call("claim_robot"), [])
        self.assertEqual((await self.store.call("reminder_list"))[0]["state"], "due")

    async def test_snooze_and_cancel_with_spoken_numbers(self):
        await self.reminders.create("check print", "in 20 minutes")
        self.assertIn("Snoozed", (await self.reminders.voice_request("snooze reminder one for five minutes"))[0])
        self.assertEqual((await self.store.call("reminder_get", id=1))["due"], self.now.timestamp()+300)
        self.assertIn("cancelled", (await self.reminders.voice_request("cancel reminder one"))[0])
        self.now += timedelta(hours=1)
        self.assertEqual(await self.reminders.tick(), [])

    async def test_existing_context_and_rollback_backup_preserved(self):
        await self.context.start()
        self.assertEqual((await self.context.perform("list", kind="memory"))["items"][0]["text"], "existing lab note")
        with closing(sqlite3.connect(self.directory / "context-before-utilities.sqlite3")) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
        await self.store.call("project_add", name="Sensor")
        self.assertEqual(len(await self.store.call("project_list")), 1)

    async def test_focus_break_is_explicit_and_not_automatically_repeated(self):
        await self.reminders.voice_request("start a one minute focus")
        self.now += timedelta(minutes=2)
        await self.reminders.tick()
        self.assertEqual(len(await self.store.call("reminder_list")), 1)
        await self.reminders.start_break(1)
        with self.assertRaises(ValueError): await self.reminders.start_break(1)
        self.assertEqual((await self.store.call("reminder_list"))[0]["kind"], "break")


class WorkbenchTests(unittest.TestCase):
    def test_physical_results_and_invalid_dimensions(self):
        self.assertAlmostEqual(convert(32, "f", "c")["result"], 0, places=8)
        self.assertEqual(convert(1, "in", "mm")["result"], 25.4)
        with self.assertRaises(ValueError): convert(1, "v", "ohm")
        with self.assertRaises(ValueError): convert(-300, "c", "f")
        self.assertEqual(ohms_law(voltage=5, resistance=1000)["current_a"], .005)
        self.assertEqual(resistor_value(["yellow", "violet", "red", "gold"])["ohms"], 4700)
        with self.assertRaises(ValueError): ohms_law(voltage=5, current=0)
