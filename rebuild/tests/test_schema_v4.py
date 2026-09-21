"""Upgrade real historical contracts; failures must preserve user state."""
import concurrent.futures
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from kcore import schema
from kcore.storage import KadencePaths, connect_database

FIXTURE = Path(__file__).parent / 'fixtures' / 'storage_v3.sql'
OLD_TABLES = ('records', 'reminders', 'projects', 'project_entries', 'media', 'observations')
NEW_TABLES = ('persons', 'face_profiles', 'perception_runs', 'presence_sessions', 'perception_events', 'perception_actions')


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = KadencePaths.for_root(Path(self.tmp.name))
        self.paths.prepare()
        with closing(sqlite3.connect(self.paths.database)) as db:
            db.executescript(FIXTURE.read_text())
        self.image = self.paths.root / 'media/images/2026/09/abcdef.png'
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b'KEEP')

    def snapshot(self, path=None):
        with closing(sqlite3.connect(path or self.paths.database)) as db:
            return {table: (tuple(r[1] for r in db.execute(f'PRAGMA table_info({table})')),
                            db.execute(f'SELECT * FROM {table} ORDER BY id').fetchall())
                    for table in OLD_TABLES}

    def assert_preserved(self, before):
        with closing(connect_database(self.paths.database)) as db:
            for table, (columns, rows) in before.items():
                self.assertEqual(db.execute(f'SELECT {",".join(columns)} FROM {table} ORDER BY id').fetchall(), rows)
            schema.check_integrity(db)
        self.assertEqual(self.image.read_bytes(), b'KEEP')

    def test_v3_upgrade_preserves_rows_ids_links_reminder_outcomes_and_reopens(self):
        before = self.snapshot()
        backup = schema.ensure_schema(self.paths)
        self.assertEqual(self.snapshot(backup), before)
        self.assert_preserved(before)
        with closing(connect_database(self.paths.database)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 4)
            self.assertEqual(db.execute('SELECT purpose,pinned,expires_at,deleted_at FROM media').fetchone(),
                             ('manual_capture', 1, None, None))
            for table in NEW_TABLES:
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 0)
            db.execute("INSERT INTO records(kind,text,created) VALUES('task','next','now')")
            self.assertGreater(db.execute('SELECT max(id) FROM records').fetchone()[0], 9)
            db.rollback()
        backups = set(self.paths.backups_dir.iterdir())
        self.assertIsNone(schema.ensure_schema(self.paths))
        self.assertIsNone(schema.ensure_schema(self.paths, target=1))
        self.assertEqual(set(self.paths.backups_dir.iterdir()), backups)
        self.assert_preserved(before)

    def test_partial_ddl_failure_rolls_back_schema_and_version_and_retry_succeeds(self):
        before = self.snapshot()
        original = schema._apply_migration
        def fail(db, version):
            original(db, version)
            if version == 4:
                raise OSError('injected interrupted migration')
        with patch.object(schema, '_apply_migration', fail):
            with self.assertRaises(OSError): schema.ensure_schema(self.paths)
        self.assertEqual(self.snapshot(), before)
        with closing(connect_database(self.paths.database)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 3)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='persons'").fetchone())
        first_backup = next(self.paths.backups_dir.glob('schema-v3-before-v4-*'))
        self.assertEqual(self.snapshot(first_backup), before)
        second_backup = schema.ensure_schema(self.paths)
        self.assertNotEqual(first_backup, second_backup)
        self.assert_preserved(before)

    def test_backup_failure_never_applies_migration(self):
        before = self.snapshot()
        with patch.object(schema, 'backup_sqlite', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): schema.ensure_schema(self.paths)
        self.assertEqual(self.snapshot(), before)
        with closing(connect_database(self.paths.database)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 3)

    def test_backup_includes_committed_wal_rows(self):
        with closing(sqlite3.connect(self.paths.database)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA wal_autocheckpoint=0')
            db.execute("UPDATE records SET text='committed WAL data' WHERE id=7")
            db.commit()
            self.assertTrue(Path(str(self.paths.database)+'-wal').exists())
            before = self.snapshot()
            backup = schema.ensure_schema(self.paths)
            self.assertEqual(self.snapshot(backup), before)
        self.assert_preserved(before)

    def test_concurrent_startups_migrate_once(self):
        before = self.snapshot()
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: schema.ensure_schema(self.paths), range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assert_preserved(before)

    def test_v1_and_v2_and_new_database_upgrade(self):
        for version in (0, 1, 2):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                paths = KadencePaths.for_root(Path(tmp)); paths.prepare()
                with closing(sqlite3.connect(paths.database)) as db:
                    db.executescript(FIXTURE.read_text())
                    for table in ('observations','media'):
                        db.execute(f'DROP TABLE {table}')
                    if version < 2:
                        for table in ('project_entries','projects','reminders'):
                            db.execute(f'DROP TABLE {table}')
                    if version == 0: db.execute('DROP TABLE records')
                    db.execute(f'PRAGMA user_version={version}'); db.commit()
                backup = schema.ensure_schema(paths)
                with closing(connect_database(paths.database)) as db:
                    schema.check_integrity(db)
                    self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 4)
                    if version:
                        self.assertEqual(db.execute('SELECT count(*) FROM records').fetchone()[0], 2)
                        self.assertTrue(backup.exists())
                    if version == 2:
                        self.assertEqual(db.execute("SELECT robot FROM reminders WHERE id=12").fetchone()[0], 'attempted')

    def test_foreign_key_damage_is_reported_without_repair_or_upgrade(self):
        with closing(sqlite3.connect(self.paths.database)) as db:
            db.execute('DELETE FROM projects'); db.commit()
        with self.assertRaisesRegex(RuntimeError, 'foreign key'): schema.ensure_schema(self.paths)
        with closing(sqlite3.connect(self.paths.database)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0], 1)

    def test_missing_v3_columns_and_future_versions_are_not_silently_repaired(self):
        with closing(sqlite3.connect(self.paths.database)) as db:
            db.execute('DROP TABLE observations'); db.commit()
        with self.assertRaisesRegex(RuntimeError, 'incomplete'): schema.ensure_schema(self.paths)
        with closing(sqlite3.connect(self.paths.database)) as db:
            db.execute('PRAGMA user_version=99')
        with self.assertRaisesRegex(RuntimeError, 'unsupported'): schema.ensure_schema(self.paths)

    def test_foreign_keys_session_uniqueness_action_dedup_and_embedding_shape(self):
        schema.ensure_schema(self.paths)
        with closing(connect_database(self.paths.database)) as db, db:
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            db.execute("INSERT INTO persons(id,display_name,created_at,updated_at) VALUES('p','Boss',1,1)")
            db.execute("INSERT INTO perception_runs(id,started_at,checkpoint_at,config_fingerprint) VALUES('r',1,1,'test')")
            sql = "INSERT INTO presence_sessions(id,run_id,person_id,identity_status,started_at,checkpoint_at,identity_confirmed_at,initial_trigger) VALUES(?,'r',?,'confirmed',1,1,1,'test')"
            db.execute(sql, ('s','p'))
            with self.assertRaises(sqlite3.IntegrityError): db.execute(sql, ('s2','p'))
            with self.assertRaises(sqlite3.IntegrityError): db.execute(sql, ('s3','missing-person'))
            action = "INSERT INTO perception_actions(id,presence_session_id,person_id,correlation_id,kind,created_at,expires_at) VALUES(?,'s','p','c','greeting',1,2)"
            db.execute(action, ('a',))
            with self.assertRaises(sqlite3.IntegrityError): db.execute(action, ('a2',))
            profile = "INSERT INTO face_profiles(id,person_id,model_fingerprint,preprocessing,metric,embedding_dimension,embedding,created_at) VALUES('f','p','model-hash','normalised','cosine',2,?,1)"
            with self.assertRaises(sqlite3.IntegrityError): db.execute(profile, (b'bad',))
            db.execute(profile, (b'\0'*8,))
            schema.check_integrity(db)

    def test_dual_databases_preserved_even_when_old_backup_exists(self):
        before = self.snapshot()
        with closing(sqlite3.connect(self.paths.legacy_database)) as db:
            db.execute('CREATE TABLE important(value TEXT)')
            db.execute("INSERT INTO important VALUES('legacy-only data')"); db.commit()
        self.paths.pre_layout_backup.write_bytes(b'old backup')
        with self.assertRaisesRegex(RuntimeError, 'Both legacy and canonical'): schema.ensure_schema(self.paths)
        self.assertTrue(self.paths.legacy_database.exists())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.paths.pre_layout_backup.read_bytes(), b'old backup')

    def test_stale_layout_backup_is_not_used_as_current_database(self):
        self.paths.database.unlink()
        self.paths.pre_layout_backup.write_bytes(b'stale archive')
        with closing(sqlite3.connect(self.paths.legacy_database)) as db:
            db.executescript(FIXTURE.read_text())
        self.paths.prepare()
        self.assertEqual(self.snapshot()['reminders'][1][1][7], 'attempted')
        self.assertEqual(self.paths.pre_layout_backup.read_bytes(), b'stale archive')
        self.assertFalse(self.paths.legacy_database.exists())


class StorageOperatorTests(unittest.TestCase):
    def test_readonly_then_upgrade_and_reopen_without_record_contents(self):
        import subprocess
        import sys
        tool = Path(__file__).resolve().parents[1] / 'tools' / 'storage_status.py'
        with tempfile.TemporaryDirectory() as tmp:
            paths = KadencePaths.for_root(Path(tmp)); paths.prepare()
            with closing(sqlite3.connect(paths.database)) as db:
                db.executescript(FIXTURE.read_text())
            command = [sys.executable, str(tool), '--data-dir', tmp]
            before = paths.database.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('schema=3', result.stdout)
            self.assertNotIn('Do not replay this', result.stdout)
            self.assertEqual(paths.database.read_bytes(), before)
            paths.desktop_lock.write_text('running')
            result = subprocess.run(command+['--upgrade'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(paths.database.read_bytes(), before)
            paths.desktop_lock.unlink()
            result = subprocess.run(command+['--upgrade'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('schema=4', result.stdout)
            self.assertIn('Rollback backup:', result.stdout)
            result = subprocess.run(command+['--upgrade'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('already current', result.stdout)

    def test_wrong_root_does_not_create_a_parallel_database(self):
        import subprocess
        import sys
        tool = Path(__file__).resolve().parents[1] / 'tools' / 'storage_status.py'
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(tool), '--data-dir', tmp, '--upgrade'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(KadencePaths.for_root(Path(tmp)).database.exists())
