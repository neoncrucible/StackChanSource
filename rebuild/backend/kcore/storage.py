"""Canonical host storage layout and one-way migration from the Alpha root files."""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def default_data_dir() -> Path:
    override = os.environ.get("KADENCE_DATA_DIR")
    if override:
        return Path(override).expanduser()
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    return (Path(root) if root else Path.home() / ".local" / "share") / "Kadence"


def _readonly_uri(path: Path) -> str:
    return "file:" + path.resolve().as_posix() + "?mode=ro"


def backup_sqlite(source: Path, destination: Path) -> None:
    """Create an integrity-checked SQLite snapshot, including committed WAL pages."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(_readonly_uri(source), uri=True, timeout=1.0)) as src, \
                closing(sqlite3.connect(temporary, timeout=1.0)) as dst:
            src.backup(dst)
            result = dst.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise RuntimeError("storage database integrity check failed")
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relocate_plain(source: Path, destination: Path) -> None:
    """Copy, verify, then remove a non-live legacy file. Existing unequal files are preserved."""
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _sha256(source) == _sha256(destination):
            source.unlink(missing_ok=True)
        return
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        shutil.copy2(source, temporary)
        if _sha256(source) != _sha256(temporary):
            raise RuntimeError("storage file verification failed")
        temporary.replace(destination)
        source.unlink(missing_ok=True)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class KadencePaths:
    """All persistent host paths. Binary media stays on disk; SQLite stores metadata."""
    root: Path

    @classmethod
    def for_root(cls, root: Path | None = None) -> "KadencePaths":
        return cls(Path(root) if root is not None else default_data_dir())

    @property
    def database_dir(self) -> Path:
        return self.root / "database"

    @property
    def database(self) -> Path:
        return self.database_dir / "kadence.sqlite3"

    @property
    def media_dir(self) -> Path:
        return self.root / "media"

    @property
    def images_dir(self) -> Path:
        return self.media_dir / "images"

    @property
    def thumbnails_dir(self) -> Path:
        return self.media_dir / "thumbnails"

    @property
    def backups_dir(self) -> Path:
        return self.root / "backups"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def settings(self) -> Path:
        # Kept at the Alpha location for desktop rollback compatibility.
        return self.root / "desktop-settings.json"

    @property
    def desktop_lock(self) -> Path:
        # Keep this shared with older builds so they cannot run concurrently.
        return self.root / "desktop.lock"

    @property
    def legacy_database(self) -> Path:
        return self.root / "context.sqlite3"

    @property
    def pre_layout_backup(self) -> Path:
        return self.backups_dir / "context-before-storage-layout.sqlite3"

    @property
    def utility_backup(self) -> Path:
        return self.backups_dir / "context-before-utilities.sqlite3"

    @property
    def observation_schema_backup(self) -> Path:
        return self.backups_dir / "context-before-observations.sqlite3"

    def prepare(self) -> None:
        """Create the layout and migrate legacy database files without losing rollback data."""
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for directory in (self.database_dir, self.images_dir, self.thumbnails_dir,
                          self.backups_dir, self.exports_dir):
            directory.mkdir(parents=True, exist_ok=True)

        legacy = self.legacy_database
        if legacy.exists():
            # Snapshot the old database twice before cleaning the root copy: one
            # becomes the new live DB and one remains an explicit rollback point.
            if not self.pre_layout_backup.exists():
                backup_sqlite(legacy, self.pre_layout_backup)
            if not self.database.exists():
                backup_sqlite(legacy, self.database)
            if self.pre_layout_backup.exists() and self.database.exists():
                legacy.unlink(missing_ok=True)
                Path(str(legacy) + "-wal").unlink(missing_ok=True)
                Path(str(legacy) + "-shm").unlink(missing_ok=True)

        _relocate_plain(self.root / "context-before-utilities.sqlite3", self.utility_backup)

    def image_path(self, captured: float, identifier: str) -> tuple[Path, str]:
        if not identifier or any(ch not in "0123456789abcdef" for ch in identifier.lower()):
            raise ValueError("invalid media identifier")
        stamp = datetime.fromtimestamp(captured, timezone.utc)
        folder = self.images_dir / f"{stamp.year:04d}" / f"{stamp.month:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (identifier.lower() + ".png")
        return path, path.relative_to(self.root).as_posix()
