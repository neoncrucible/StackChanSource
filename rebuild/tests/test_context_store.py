"""Database handles must close deterministically, including on Windows."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kcore.context_store import ContextStore


class ContextHandleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ContextStore(Path(self.temp.name))
        self.connections = []
        self.real_connect = sqlite3.connect

        def retain_connection(*args, **kwargs):
            # Keep real handles alive so garbage collection cannot hide leaks.
            # Cross-thread access is enabled only for the test's closed check.
            db = self.real_connect(*args, **kwargs, check_same_thread=False)
            self.connections.append(db)
            return db

        self.connection_patch = patch("kcore.context_store.sqlite3.connect", side_effect=retain_connection)
        self.connection_patch.start()

    async def asyncTearDown(self):
        self.connection_patch.stop()
        for db in self.connections:
            db.close()
        self.temp.cleanup()

    def assert_handles_closed(self):
        self.assertTrue(self.connections)
        for db in self.connections:
            with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed"):
                db.execute("SELECT 1")

    async def test_start_and_operations_release_handles_and_preserve_commits(self):
        await self.store.start()
        self.assert_handles_closed()
        record = await self.store.perform("add", kind="task", text="test record")
        self.assert_handles_closed()
        self.assertEqual((await self.store.perform("get", kind="task", id=record["id"]))["item"]["text"], "test record")
        self.assert_handles_closed()
        self.assertEqual(len((await self.store.perform("list", kind="task"))["items"]), 1)
        self.assert_handles_closed()
        self.assertTrue((await self.store.perform("complete", kind="task", id=record["id"]))["changed"])
        self.assert_handles_closed()
        self.assertEqual((await self.store.perform("list", kind="task"))["items"], [])
        self.assertTrue((await self.store.perform("delete", kind="task", id=record["id"]))["changed"])
        self.assert_handles_closed()

    async def test_failed_operation_releases_handles(self):
        await self.store.start()
        with self.assertRaises(ValueError):
            await self.store.perform("unsupported")
        self.assert_handles_closed()

    async def test_failed_initialisation_releases_handles(self):
        db = self.real_connect(self.store.path)
        try:
            db.execute("PRAGMA user_version=99")
        finally:
            db.close()
        with self.assertRaisesRegex(RuntimeError, "unsupported"):
            await self.store.start()
        self.assert_handles_closed()


if __name__ == "__main__":
    unittest.main()
