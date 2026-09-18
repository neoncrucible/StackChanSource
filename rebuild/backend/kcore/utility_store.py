"""Transactional utility state sharing Kadence's canonical context database."""
from __future__ import annotations

import asyncio
import json
import math
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .storage import KadencePaths, backup_sqlite


class UtilityStore:
    def __init__(self, directory: Path):
        self.paths = KadencePaths.for_root(directory)
        self.paths.database_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.paths.database

    async def start(self):
        await asyncio.to_thread(self._start)

    def _start(self):
        self.paths.prepare()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=0.25)) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (1, 2, 3):
            raise RuntimeError("context store must be initialised first")
        if version == 1 and not self.paths.utility_backup.exists():
            backup_sqlite(self.path, self.paths.utility_backup)
        if version == 2 and not self.paths.observation_schema_backup.exists():
            backup_sqlite(self.path, self.paths.observation_schema_backup)

        with closing(sqlite3.connect(self.path, timeout=0.25)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "text TEXT NOT NULL, due REAL NOT NULL, timezone TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'scheduled', "
                       "kind TEXT NOT NULL DEFAULT 'reminder', extra TEXT NOT NULL DEFAULT '{}', "
                       "robot TEXT NOT NULL DEFAULT 'pending', created REAL NOT NULL, request_key TEXT NOT NULL UNIQUE)")
            db.execute("CREATE INDEX IF NOT EXISTS reminders_due ON reminders(state,due)")
            db.execute("CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, created REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS project_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, "
                       "kind TEXT NOT NULL, text TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, "
                       "FOREIGN KEY(project_id) REFERENCES projects(id))")
            db.execute("CREATE TABLE IF NOT EXISTS media (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "path TEXT NOT NULL UNIQUE, media_type TEXT NOT NULL, mime_type TEXT NOT NULL, source TEXT NOT NULL, "
                       "captured REAL NOT NULL, width INTEGER, height INTEGER, size_bytes INTEGER NOT NULL, "
                       "sha256 TEXT NOT NULL, created REAL NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS media_captured ON media(captured)")
            db.execute("CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "media_id INTEGER NOT NULL UNIQUE, project_id INTEGER NOT NULL, captured REAL NOT NULL, "
                       "question TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', qr TEXT NOT NULL DEFAULT '[]', "
                       "source_device TEXT NOT NULL, created REAL NOT NULL, "
                       "FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE, "
                       "FOREIGN KEY(project_id) REFERENCES projects(id))")
            db.execute("CREATE INDEX IF NOT EXISTS observations_project ON observations(project_id,captured)")
            db.execute("PRAGMA user_version=3")

    async def call(self, action: str, **args):
        return await asyncio.to_thread(self._call, action, args)

    @staticmethod
    def _text(value, limit=800):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f"text must contain 1..{limit} characters")
        return value.strip()

    @staticmethod
    def _optional_text(value, limit):
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"text must contain 0..{limit} characters")
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
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute("SELECT * FROM reminders WHERE state='scheduled' AND due<=? ORDER BY due LIMIT 200", (now,)).fetchall()
                db.executemany("UPDATE reminders SET state='due' WHERE id=? AND state='scheduled'", [(row["id"],) for row in rows])
                return [dict(row, state="due") for row in rows]
            if action == "claim_robot":
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute("SELECT * FROM reminders WHERE state='due' AND robot='pending' ORDER BY due LIMIT 200").fetchall()
                db.executemany("UPDATE reminders SET robot='attempted' WHERE id=? AND state='due'", [(row["id"],) for row in rows])
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
                if type(args["done"]) is not bool:
                    raise ValueError("Checklist completion must be true or false")
                return db.execute("UPDATE project_entries SET done=? WHERE id=? AND kind='step'", (int(args["done"]), args["id"])).rowcount == 1
            if action == "entry_delete":
                return db.execute("DELETE FROM project_entries WHERE id=?", (args["id"],)).rowcount == 1
            if action == "observation_add":
                project_id = args["project_id"]
                if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
                    raise ValueError("Choose an existing project.")
                if db.execute("SELECT count(*) FROM project_entries").fetchone()[0] >= 5000:
                    raise ValueError("maximum 5000 project entries")
                if db.execute("SELECT count(*) FROM observations").fetchone()[0] >= 10000:
                    raise ValueError("maximum 10000 saved observations")
                path = args["path"]
                parsed = PurePosixPath(path) if isinstance(path, str) else None
                if not parsed or parsed.is_absolute() or ".." in parsed.parts or not path.startswith("media/images/") or len(path) > 300:
                    raise ValueError("invalid media path")
                captured = args["captured"]
                if type(captured) not in (int, float) or not math.isfinite(captured) or captured <= 0:
                    raise ValueError("invalid capture time")
                width, height, size_bytes = args["width"], args["height"], args["size_bytes"]
                if type(width) is not int or type(height) is not int or not 1 <= width <= 10000 or not 1 <= height <= 10000:
                    raise ValueError("invalid image dimensions")
                if type(size_bytes) is not int or not 1 <= size_bytes <= 20 * 1024 * 1024:
                    raise ValueError("invalid media size")
                digest = args["sha256"]
                if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
                    raise ValueError("invalid media digest")
                source = self._text(args["source_device"], 80)
                question = self._optional_text(args.get("question", ""), 500)
                description = self._optional_text(args.get("description", ""), 1200)
                qr = args.get("qr", [])
                if not isinstance(qr, list) or len(qr) > 20 or any(not isinstance(item, str) or len(item) > 2048 for item in qr):
                    raise ValueError("invalid QR metadata")
                media = db.execute("INSERT INTO media(path,media_type,mime_type,source,captured,width,height,size_bytes,sha256,created) "
                                   "VALUES(?,?,?,?,?,?,?,?,?,?)",
                                   (path, "image", "image/png", source, captured, width, height, size_bytes, digest.lower(), now))
                observation = db.execute("INSERT INTO observations(media_id,project_id,captured,question,description,qr,source_device,created) "
                                         "VALUES(?,?,?,?,?,?,?,?)",
                                         (media.lastrowid, project_id, captured, question, description,
                                          json.dumps(qr, ensure_ascii=False), source, now))
                stamp = datetime.fromtimestamp(captured, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                note = f"Observation {stamp}. Image: {path}."
                if description:
                    note += " " + description[:600]
                db.execute("INSERT INTO project_entries(project_id,kind,text,created) VALUES(?,?,?,?)",
                           (project_id, "note", note, now))
                return {"id": observation.lastrowid, "media_id": media.lastrowid, "path": path}
            if action == "observation_list":
                project_id = args.get("project_id")
                if project_id is not None and type(project_id) is not int:
                    raise ValueError("invalid project id")
                sql = ("SELECT o.*,m.path,m.media_type,m.mime_type,m.source,m.width,m.height,m.size_bytes,m.sha256 "
                       "FROM observations o JOIN media m ON m.id=o.media_id ")
                params = ()
                if project_id is not None:
                    sql += "WHERE o.project_id=? "
                    params = (project_id,)
                sql += "ORDER BY o.captured DESC LIMIT 250"
                rows = []
                for row in db.execute(sql, params):
                    item = dict(row)
                    try:
                        item["qr"] = json.loads(item["qr"])
                    except (TypeError, ValueError):
                        item["qr"] = []
                    rows.append(item)
                return rows
            raise ValueError("unknown utility operation")
