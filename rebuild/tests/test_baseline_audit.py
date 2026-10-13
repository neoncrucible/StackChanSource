"""Read-only inventory must neither initialise storage nor disclose saved content."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

from kcore.schema import ensure_schema
from kcore.storage import KadencePaths, backup_sqlite

spec = importlib.util.spec_from_file_location('baseline_audit', Path(__file__).resolve().parents[1] / 'tools' / 'baseline_audit.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_missing_data_is_unknown_and_never_created(tmp_path):
    paths = KadencePaths.for_root(tmp_path / 'absent')
    result = module.audit(paths)
    assert result['database']['status'] == result['app_files']['status'] == 'unknown'
    assert result['physical_acceptance'] == 'pending'
    assert not paths.root.exists()


def test_inventory_reads_committed_wal_without_rows_or_migration(tmp_path):
    paths = KadencePaths.for_root(tmp_path)
    ensure_schema(paths)
    with sqlite3.connect(paths.database) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute("INSERT INTO records(kind,text,created) VALUES('note','private-test-value','2026-10-13')")
        writer.commit()
        backup_sqlite(paths.database, paths.backups_dir / 'accepted.sqlite3')
        before = writer.execute('PRAGMA user_version').fetchone()[0]
        result = module.audit(paths)
        assert result['database']['schema_version'] == before == 5
        assert len(result['database']['tables']) == 13
        assert result['database']['tables']['records']['rows'] == 1
        assert result['backups'][0]['status'] == 'verified'
        assert len(result['backups'][0]['sha256']) == 64
        assert 'private-test-value' not in json.dumps(result)
        assert writer.execute('SELECT text FROM records').fetchone()[0] == 'private-test-value'


def test_conflicting_layout_and_invalid_backup_remain_untouched(tmp_path):
    paths = KadencePaths.for_root(tmp_path)
    ensure_schema(paths)
    paths.legacy_database.write_bytes(b'legacy marker')
    damaged = paths.backups_dir / 'broken.sqlite3'
    damaged.write_bytes(b'not a SQLite backup')
    result = module.audit(paths)
    assert result['layout_conflict']
    assert result['backups'][0]['status'] == 'failed'
    assert paths.legacy_database.read_bytes() == b'legacy marker'
    assert damaged.read_bytes() == b'not a SQLite backup'


def package(root, build_commit='a'*40):
    root.mkdir()
    (root / '_internal').mkdir()
    (root / 'Kadence.exe').write_bytes(b'test fixture, not an executable')
    for name, commit in [('RELEASE.json','a'*40),('_internal/BUILD.json',build_commit)]:
        (root / name).write_text(json.dumps({'host_version':'0.5.0','source_commit':commit,'untrusted_extra':'private-test-value'}))
    (root / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix()+'\n'
        for p in sorted(root.rglob('*')) if p.is_file()))
    return root


def test_manifest_agreement_checksums_and_tampering(tmp_path):
    app = package(tmp_path / 'app')
    result = module.audit(KadencePaths.for_root(tmp_path / 'data'), app)
    assert result['app_files']['status'] == 'verified'
    assert result['app_files']['running_instance'] == 'unknown'
    assert 'private-test-value' not in json.dumps(result)
    (app / 'Kadence.exe').write_bytes(b'tampered')
    assert module.audit(KadencePaths.for_root(tmp_path / 'data'), app)['app_files']['status'] == 'unverified'


def test_mismatched_build_and_unsafe_manifest_are_rejected(tmp_path):
    app = package(tmp_path / 'app', 'b'*40)
    result = module.audit(KadencePaths.for_root(tmp_path / 'data'), app)
    assert not result['app_files']['identities_agree']
    assert result['app_files']['status'] == 'unverified'
    outside = tmp_path / 'outside'
    outside.write_bytes(b'never part of this package')
    (app / 'SHA256SUMS').write_text(module.digest(outside)+'  ../outside\n')
    assert module.package_integrity(app)['status'] == 'failed'


def test_unlisted_files_and_missing_build_identity_fail_integrity(tmp_path):
    app = package(tmp_path / 'app')
    (app / 'unlisted.dll').write_bytes(b'unlisted')
    assert module.package_integrity(app)['status'] == 'failed'
    (app / 'unlisted.dll').unlink()
    (app / '_internal' / 'BUILD.json').unlink()
    assert module.package_integrity(app)['status'] == 'failed'
