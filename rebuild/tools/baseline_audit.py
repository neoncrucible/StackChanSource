"""Read-only M0 inventory. Never starts services, migrates data or touches devices."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'rebuild' / 'backend'))
from kcore.schema import SCHEMA_VERSION, check_integrity, validate_schema
from kcore.storage import KadencePaths


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def database_inventory(path):
    result = {'path': str(path), 'status': 'unknown'}
    if not path.is_file():
        return dict(result, reason='database_absent')
    try:
        # A single read transaction includes committed WAL pages and coherent counts.
        # Do not instantiate stores here: their startup methods can migrate data.
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            result['schema_version'] = version
            if not 1 <= version <= SCHEMA_VERSION:
                return dict(result, status='failed', reason='unsupported_schema')
            validate_schema(db, version)
            check_integrity(db)
            tables = {}
            names = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            for (name,) in names:
                quoted = '"' + name.replace('"', '""') + '"'
                tables[name] = {
                    'rows': db.execute(f'SELECT count(*) FROM {quoted}').fetchone()[0],
                    'columns': [{'name': row[1], 'type': row[2], 'not_null': bool(row[3]), 'primary_key': row[5]}
                                for row in db.execute(f'PRAGMA table_info({quoted})')],
                }
        return dict(result, status='verified', integrity='ok', foreign_keys='ok', tables=tables)
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        # Never include arbitrary row values or the text of a database error.
        return dict(result, status='failed', reason=type(exc).__name__)


def manifest_identity(path):
    result = {'path': str(path), 'status': 'unknown'}
    if not path.is_file():
        return dict(result, reason='manifest_absent')
    try:
        if path.stat().st_size > 65536:
            raise ValueError('manifest too large')
        value = json.loads(path.read_text('utf-8'))
        commit, version = value['source_commit'], value['host_version']
        if not re.fullmatch('[0-9a-f]{40}', commit) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise ValueError('invalid identity')
        return dict(result, status='verified', source_commit=commit, host_version=version, sha256=digest(path))
    except (OSError, ValueError, TypeError, KeyError):
        return dict(result, status='failed', reason='invalid_manifest')


def package_integrity(root):
    sums = root / 'SHA256SUMS'
    if not sums.is_file():
        return {'status': 'unknown', 'reason': 'checksums_absent'}
    try:
        if sums.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('oversized checksums')
        seen = set()
        for line in sums.read_text('utf-8').splitlines():
            checksum, name = line.split('  ', 1)
            relative = PurePosixPath(name)
            if (not re.fullmatch('[0-9a-f]{64}', checksum) or relative.is_absolute()
                    or '..' in relative.parts or '\\' in name or ':' in name or not name or name in seen):
                raise ValueError('unsafe checksum entry')
            file = root / relative
            if not file.resolve().is_relative_to(root.resolve()) or not file.is_file() or digest(file) != checksum:
                raise ValueError('checksum mismatch')
            seen.add(name)
        required = {'Kadence.exe', 'RELEASE.json', '_internal/BUILD.json'}
        actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != sums}
        if not required <= seen or actual != seen:
            raise ValueError('incomplete checksums')
        return {'status': 'verified', 'files': len(seen), 'checksum_manifest_sha256': digest(sums)}
    except (OSError, ValueError, UnicodeError):
        return {'status': 'failed', 'reason': 'package_checksum_validation_failed'}


def audit(paths, app_dir=None):
    try:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True))
    except (OSError, subprocess.CalledProcessError):
        head, dirty = None, None
    database = database_inventory(paths.database)
    conflict = paths.legacy_database.exists() and paths.database.exists()
    backups = []
    if paths.backups_dir.is_dir():
        # Inspect snapshots, never create one or overwrite a recovery point.
        candidates = sorted(paths.backups_dir.glob('*.sqlite3'), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in candidates[:20]:
            item = database_inventory(path)
            wal = Path(str(path) + '-wal')
            if wal.exists() and wal.stat().st_size:
                item.update(status='unknown', reason='backup_has_wal_requires_review')
            elif item['status'] == 'verified':
                item['sha256'] = digest(path)
            backups.append(item)
        backup_total = len(candidates)
    else:
        backup_total = 0
    app = {'status': 'unknown', 'reason': 'app_directory_not_supplied'}
    if app_dir is not None:
        release = manifest_identity(app_dir / 'RELEASE.json')
        build = manifest_identity(app_dir / '_internal' / 'BUILD.json')
        agreement = (release['status'] == build['status'] == 'verified'
                     and all(release[k] == build[k] for k in ('source_commit', 'host_version')))
        integrity = package_integrity(app_dir)
        app = {'release': release, 'build': build, 'identities_agree': agreement,
               'matches_source_head': agreement and build['source_commit'] == head,
               'package_integrity': integrity,
               'status': 'verified' if agreement and integrity['status'] == 'verified' else 'unverified',
               'running_instance': 'unknown'}
    return {
        'format': 1, 'observed_at': datetime.now(timezone.utc).isoformat(),
        'read_only': True, 'source': {'commit': head, 'dirty': dirty, 'schema_version': SCHEMA_VERSION},
        'data_root': str(paths.root), 'database': database, 'legacy_database_present': paths.legacy_database.exists(),
        'layout_conflict': conflict, 'desktop_lock_present': paths.desktop_lock.exists(),
        'backups': backups, 'backup_total': backup_total, 'backups_inspected': len(backups), 'app_files': app,
        'physical_acceptance': 'pending',
        'not_observed': ['CoreS3 firmware and USB/LAN/audio health', 'UnitV2 service and native face backup',
                         'configured provider and live sensors', 'KadeHQ schema/migration ledger and release files',
                         'KadePocket release files', 'owner-accepted rollback package'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--app-dir', type=Path, help='Extracted or installed version folder containing Kadence.exe and RELEASE.json')
    args = parser.parse_args()
    result = audit(KadencePaths.for_root(args.data_dir), args.app_dir)
    print(json.dumps(result, indent=2))
    # Missing evidence is explicit in JSON. A report is not a release acceptance.
    return 1 if result['layout_conflict'] or result['database']['status'] == 'failed' or result['app_files']['status'] == 'unverified' else 0


if __name__ == '__main__':
    raise SystemExit(main())
