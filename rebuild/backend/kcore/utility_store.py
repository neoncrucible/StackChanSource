"""Transactional utility state sharing the owner's existing context database."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class UtilityStore:
    def __init__(self, directory: Path):
        self.path = directory / "context.sqlite3"

    async def start(self):
        await asyncio.to_thread(self._start)

    def _start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=0.25)) as db, db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (1, 2):
                raise RuntimeError("context store must be initialised first")
            if version == 1:
                # SQLite backup includes committed WAL pages; retain the RC1 format
                # for an explicit host rollback without touching current records.
                backup = self.path.with_name("context-before-utilities.sqlite3")
                if not backup.exists():
                    temporary = backup.with_suffix(".tmp")
                    with closing(sqlite3.connect(temporary)) as destination:
                        db.backup(destination)
                    temporary.replace(backup)
            db.execute("CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "text TEXT NOT NULL, due REAL NOT NULL, timezone TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'scheduled', "
                       "kind TEXT NOT NULL DEFAULT 'reminder', extra TEXT NOT NULL DEFAULT '{}', "
                       "robot TEXT NOT NULL DEFAULT 'pending', created REAL NOT NULL, request_key TEXT NOT NULL UNIQUE)")
            db.execute("CREATE INDEX IF NOT EXISTS reminders_due ON reminders(state,due)")
            db.execute("CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, created REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS project_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, "
                       "kind TEXT NOT NULL, text TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, "
                       "FOREIGN KEY(project_id) REFERENCES projects(id))")
            db.execute("PRAGMA user_version=2")

    async def call(self, action: str, **args):
        return await asyncio.to_thread(self._call, action, args)

    @staticmethod
    def _text(value, limit=800):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f"text must contain 1..{limit} characters")
        return value.strip()

    def _call(self, action, args):
        with closing(sqlite3.connect(self.path, timeout=0.25)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            now = args.get("now", datetime.now(timezone.utc).timestamp())
            if action == "reminder_add":
                text = self._text(args["text"])
                due = args["due"]
                if type(due) not in (int, float) or not now < due <= now + 366 * 86400:
                    raise ValueError("reminder deadline must be within the next year")
                if db.execute("SELECT count(*) FROM reminders WHERE state IN ('scheduled','due')").fetchone()[0] >= 200:
                    raise ValueError("maximum 200 active reminders")
                kind = args.get("kind", "reminder")
                if kind not in ("reminder", "focus", "break"):
                    raise ValueError("unknown reminder kind")
                key = args.get("request_key", str(uuid.uuid4()))
                existing = db.execute("SELECT * FROM reminders WHERE request_key=?", (key,)).fetchone()
                if existing:
                    return dict(existing)
                cursor = db.execute("INSERT INTO reminders(text,due,timezone,kind,extra,created,request_key) VALUES(?,?,?,?,?,?,?)",
                    (text, due, args["timezone"], kind, json.dumps(args.get("extra", {})), now, key))
                return dict(db.execute("SELECT * FROM reminders WHERE id=?", (cursor.lastrowid,)).fetchone())
            if action == "reminder_list":
                return [dict(row) for row in db.execute("SELECT * FROM reminders WHERE state IN ('scheduled','due') ORDER BY due LIMIT 200")]
            if action == "reminder_get":
                row = db.execute("SELECT * FROM reminders WHERE id=?", (args["id"],)).fetchone()
                return dict(row) if row else None
            if action == "claim_due":
                # One transaction serialises concurrent scheduler ticks and restarts.
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute("SELECT * FROM reminders WHERE state='scheduled' AND due<=? ORDER BY due LIMIT 200", (now,)).fetchall()
                db.executemany("UPDATE reminders SET state='due' WHERE id=? AND state='scheduled'", [(row["id"],) for row in rows])
                return [dict(row, state="due") for row in rows]
            if action == "claim_robot":
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute("SELECT * FROM reminders WHERE state='due' AND robot='pending' ORDER BY due LIMIT 200").fetchall()
                # Mark before starting playback. An uncertain ACK cannot replay an alert.
                db.executemany("UPDATE reminders SET robot='attempted' WHERE id=?", [(row["id"],) for row in rows])
                return [dict(row) for row in rows]
            if action == "robot_delivered":
                db.executemany("UPDATE reminders SET robot='delivered' WHERE id=? AND state='due'", [(i,) for i in args["ids"]])
                return True
            if action in ("reminder_cancel", "reminder_dismiss"):
                state = "cancelled" if action.endswith("cancel") else "dismissed"
                return db.execute("UPDATE reminders SET state=? WHERE id=? AND state IN ('scheduled','due')", (state, args["id"])).rowcount == 1
            if action == "reminder_snooze":
                minutes = args["minutes"]
                if type(minutes) is not int or not 1 <= minutes <= 10080:
                    raise ValueError("snooze must be 1..10080 minutes")
                return db.execute("UPDATE reminders SET due=?,state='scheduled',robot='pending' WHERE id=? AND state IN ('scheduled','due')",
                                  (now + minutes * 60, args["id"])).rowcount == 1
            if action == "project_add":
                name = self._text(args["name"], 80)
                if db.execute("SELECT count(*) FROM projects").fetchone()[0] >= 100:
                    raise ValueError("maximum 100 projects")
                db.execute("INSERT OR IGNORE INTO projects(name,created) VALUES(?,?)", (name, now))
                return dict(db.execute("SELECT * FROM projects WHERE name=?", (name,)).fetchone())
            if action == "project_list":
                return [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY name LIMIT 100")]
            if action == "entry_add":
                kind = args["kind"]
                if kind not in ("note", "step"):
                    raise ValueError("entry must be note or step")
                text = self._text(args["text"])
                if db.execute("SELECT count(*) FROM project_entries").fetchone()[0] >= 5000:
                    raise ValueError("maximum 5000 project entries")
                cur = db.execute("INSERT INTO project_entries(project_id,kind,text,created) VALUES(?,?,?,?)", (args["project_id"], kind, text, now))
                return dict(db.execute("SELECT * FROM project_entries WHERE id=?", (cur.lastrowid,)).fetchone())
            if action == "entry_list":
                query = args.get("query", "")
                if not isinstance(query, str) or len(query) > 120:
                    raise ValueError("query exceeds limit")
                return [dict(row) for row in db.execute("SELECT * FROM project_entries WHERE project_id=? AND instr(lower(text),lower(?))>0 ORDER BY id LIMIT 250",
                                                       (args["project_id"], query))]
            if action == "entry_done":
                if type(args["done"]) is not bool: raise ValueError("Checklist completion must be true or false")
                return db.execute("UPDATE project_entries SET done=? WHERE id=? AND kind='step'", (int(args["done"]), args["id"])).rowcount == 1
            if action == "entry_delete":
                return db.execute("DELETE FROM project_entries WHERE id=?", (args["id"],)).rowcount == 1
            raise ValueError("unknown utility operation")
