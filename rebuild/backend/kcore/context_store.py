"""Explicit, bounded local records. Conversation audio/transcripts are never stored."""
from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def default_data_dir() -> Path:
    override = os.environ.get("KADENCE_DATA_DIR")
    if override:
        return Path(override).expanduser()
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    return (Path(root) if root else Path.home() / ".local" / "share") / "Kadence"


class ContextStore:
    def __init__(self, directory: Path):
        self.path = directory / "context.sqlite3"

    async def start(self) -> None:
        def initialise() -> None:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with sqlite3.connect(self.path, timeout=0.25) as db:
                db.execute("PRAGMA journal_mode=WAL")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise RuntimeError("unsupported context database version")
                db.execute("CREATE TABLE IF NOT EXISTS records ("
                           "id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
                           "text TEXT NOT NULL, created TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)")
                db.execute("PRAGMA user_version=1")
            if os.name != "nt":
                self.path.chmod(0o600)
        await asyncio.to_thread(initialise)

    async def perform(self, action: str, **args) -> dict:
        # Each worker owns its connection. SQLite's transaction and busy deadline
        # remain effective even if its awaiting voice turn is cancelled. Never
        # retry a timed-out write automatically: commit status may be unknown.
        return await asyncio.to_thread(self._perform, action, args)

    def _perform(self, action: str, args: dict) -> dict:
        with sqlite3.connect(self.path, timeout=0.25) as db:
            db.row_factory = sqlite3.Row
            kind = args.get("kind", "memory")
            if kind not in ("memory", "task"):
                raise ValueError("unsupported record type")
            if action == "add":
                count = db.execute("SELECT count(*) FROM records").fetchone()[0]
                if count >= 1000:
                    raise RuntimeError("record capacity reached")
                text = args["text"].strip()
                if not text or len(text) > 800:
                    raise ValueError("record text must contain 1..800 characters")
                created = datetime.now(timezone.utc).isoformat(timespec="seconds")
                cur = db.execute("INSERT INTO records(kind,text,created) VALUES(?,?,?)", (kind, text, created))
                return {"id": cur.lastrowid, "kind": kind, "text": text, "created": created}
            if action == "list":
                query = args.get("query", "").strip()[:120]
                # Literal substring matching, with SQL parameters throughout.
                query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                rows = db.execute("SELECT * FROM records WHERE kind=? AND done=0 "
                                  "AND text LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT 8",
                                  (kind, "%" + query + "%")).fetchall()
                return {"items": [dict(row) for row in rows]}
            if action == "get":
                row = db.execute("SELECT * FROM records WHERE id=? AND kind=?", (args["id"], kind)).fetchone()
                return {"item": dict(row) if row else None}
            if action in ("delete", "complete"):
                if action == "delete":
                    cur = db.execute("DELETE FROM records WHERE id=? AND kind=?", (args["id"], kind))
                else:
                    cur = db.execute("UPDATE records SET done=1 WHERE id=? AND kind=? AND done=0", (args["id"], kind))
                return {"id": args["id"], "changed": cur.rowcount == 1}
            raise ValueError("unsupported record action")
