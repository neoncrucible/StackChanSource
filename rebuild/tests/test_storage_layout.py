import sqlite3
import tempfile
import unittest
from pathlib import Path

from kcore.storage import KadencePaths


class StorageLayoutTests(unittest.TestCase):
    def test_alpha_database_and_backup_migrate_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "context.sqlite3"
            with sqlite3.connect(legacy) as db:
                db.execute("CREATE TABLE reminders (id INTEGER PRIMARY KEY, text TEXT NOT NULL)")
                db.execute("INSERT INTO reminders(id,text) VALUES(?,?)", (4, "Camera coexistence check"))
                db.execute("PRAGMA user_version=2")
            old_backup = root / "context-before-utilities.sqlite3"
            old_backup.write_bytes(b"old-alpha-backup")

            paths = KadencePaths.for_root(root)
            paths.prepare()
            paths.prepare()  # migration is deliberately idempotent

            self.assertFalse(legacy.exists())
            self.assertTrue(paths.database.exists())
            self.assertTrue(paths.pre_layout_backup.exists())
            self.assertFalse(old_backup.exists())
            self.assertEqual(paths.utility_backup.read_bytes(), b"old-alpha-backup")
            for database in (paths.database, paths.pre_layout_backup):
                with sqlite3.connect(database) as db:
                    self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(db.execute("SELECT text FROM reminders WHERE id=4").fetchone()[0],
                                     "Camera coexistence check")
                    self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_media_paths_are_bounded_under_year_and_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = KadencePaths.for_root(Path(tmp))
            paths.prepare()
            absolute, relative = paths.image_path(1789660800.0, "abcdef0123456789")
            self.assertEqual(relative, "media/images/2026/09/abcdef0123456789.png")
            self.assertEqual(absolute, paths.root / relative)
            with self.assertRaises(ValueError):
                paths.image_path(1789660800.0, "../escape")


if __name__ == "__main__":
    unittest.main()
