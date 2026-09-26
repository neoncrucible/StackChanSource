"""Explicit, bounded local records. Conversation audio/transcripts are never stored."""
from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .storage import KadencePaths, default_data_dir, connect_database
from .schema import ensure_schema


class ContextStore:
    def __init__(self, directory: Path):
        self.paths = KadencePaths.for_root(directory)
        # Keep direct store construction testable without requiring a full service start.
        self.paths.database_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.paths.database
        from .database_jobs import DatabaseJobs
        self.jobs = DatabaseJobs()

    async def start(self) -> None:
        await self.jobs.run(ensure_schema, self.paths, target=1)

    async def close(self):
        await self.jobs.close()

    async def perform(self, action: str, **args) -> dict:
        # Each worker owns its connection. SQLite's transaction and busy deadline
        # remain effective even if its awaiting voice turn is cancelled. Never
        # retry a timed-out write automatically: commit status may be unknown.
        return await self.jobs.run(self._perform, action, args)

    def _perform(self, action: str, args: dict) -> dict:
        # SQLite's context manager commits/rolls back; it does not close.
        # Close on the owning worker even when returning or raising, so Windows
        # never has to wait for garbage collection to release database handles.
        with closing(connect_database(self.path)) as db, db:
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
