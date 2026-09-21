"""Inspect canonical storage; --upgrade explicitly applies the backed-up migration."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from kcore.schema import SCHEMA_VERSION, REQUIRED, check_integrity, ensure_schema, validate_schema
from kcore.storage import KadencePaths


def inspect(paths):
    if not paths.database.exists():
        raise RuntimeError('Canonical database is absent. Check the data directory before upgrading.')
    with closing(sqlite3.connect(paths.database.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if not 1 <= version <= SCHEMA_VERSION:
            raise RuntimeError('Unsupported database version')
        validate_schema(db, version)
        check_integrity(db)
        tables = sorted({name for level in range(1, version+1) for name in REQUIRED[level]})
        counts = {name: db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0] for name in tables}
    print(f'KADENCE_STORAGE PASS schema={version} integrity=ok foreign_keys=ok')
    print(f'Database: {paths.database}')
    print('Rows: '+', '.join(f'{name}={count}' for name,count in counts.items()))
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, help='Kadence data root; defaults to KADENCE_DATA_DIR or normal user data location')
    parser.add_argument('--upgrade', action='store_true', help='Close Kadence first. Upgrade with a verified rollback backup.')
    args = parser.parse_args()
    paths = KadencePaths.for_root(args.data_dir)
    try:
        if paths.legacy_database.exists() and paths.database.exists():
            raise RuntimeError('Both legacy and canonical databases exist; preserve both and reconcile before upgrading.')
        if args.upgrade:
            if paths.desktop_lock.exists():
                raise RuntimeError('Desktop lock exists. Quit Kadence completely before upgrading.')
            # Refuse accidental initialization of an empty/wrong folder in this
            # operator tool. Normal application startup can create a fresh DB.
            if not paths.database.exists() and not paths.legacy_database.exists():
                raise RuntimeError('No existing database in this data directory; nothing upgraded.')
            backup = ensure_schema(paths)
            print(f'Upgrade: {"already current" if backup is None else "complete"}')
            if backup: print(f'Rollback backup: {backup}')
        inspect(paths)
        return 0
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        print(f'KADENCE_STORAGE FAIL {type(exc).__name__}: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
