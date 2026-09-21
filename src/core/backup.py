"""Backup and restore system for settings, workspaces, and user data."""

from __future__ import annotations

import json
import logging
import shutil
import threading
import zipfile
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any

from src.analysis.models import _now_iso
from src.config.settings import SettingsManager
from src.security.manager import SecurityManager
from src.services.event_bus import EventBus, Events
from src.utils.paths import AppPaths

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BackupType(Enum):
    """High-level classification of backup scope."""

    FULL = auto()
    SETTINGS_ONLY = auto()
    WORKSPACE_ONLY = auto()
    DATA_ONLY = auto()
    CUSTOM = auto()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class BackupEntry:
    """Metadata describing a single backup archive."""

    id: str
    name: str
    backup_type: BackupType
    created_at: str
    file_path: str
    file_size: int = 0
    checksum: str = ""
    description: str = ""
    workspace: str = ""
    includes_settings: bool = True
    includes_workspaces: bool = True
    includes_cases: bool = True
    includes_reports: bool = True
    includes_plugins: bool = True
    includes_notes: bool = True
    includes_bookmarks: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "backup_type": self.backup_type.name,
            "created_at": self.created_at,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "checksum": self.checksum,
            "description": self.description,
            "workspace": self.workspace,
            "includes_settings": self.includes_settings,
            "includes_workspaces": self.includes_workspaces,
            "includes_cases": self.includes_cases,
            "includes_reports": self.includes_reports,
            "includes_plugins": self.includes_plugins,
            "includes_notes": self.includes_notes,
            "includes_bookmarks": self.includes_bookmarks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupEntry:
        """Reconstruct a ``BackupEntry`` from a previously serialized dict."""
        return cls(
            id=data["id"],
            name=data["name"],
            backup_type=BackupType[data.get("backup_type", "FULL")],
            created_at=data.get("created_at", ""),
            file_path=data.get("file_path", ""),
            file_size=data.get("file_size", 0),
            checksum=data.get("checksum", ""),
            description=data.get("description", ""),
            workspace=data.get("workspace", ""),
            includes_settings=data.get("includes_settings", True),
            includes_workspaces=data.get("includes_workspaces", True),
            includes_cases=data.get("includes_cases", True),
            includes_reports=data.get("includes_reports", True),
            includes_plugins=data.get("includes_plugins", True),
            includes_notes=data.get("includes_notes", True),
            includes_bookmarks=data.get("includes_bookmarks", True),
        )


# ---------------------------------------------------------------------------
# Backup manager
# ---------------------------------------------------------------------------


class BackupManager:
    """Manages creation, restoration, and lifecycle of application backups.

    Backups are stored as zip archives in the application data directory.
    An index file tracks all known backups for fast listing and lookup.

    Parameters
    ----------
    settings:
        Application settings.  A default instance is created when *None*.
    security:
        Security manager used for hashing.  A default instance is created
        when *None*.
    """

    def __init__(
        self,
        settings: SettingsManager | None = None,
        security: SecurityManager | None = None,
    ) -> None:
        self._settings = settings or SettingsManager()
        self._security = security or SecurityManager(self._settings)
        self._event_bus = EventBus.instance()

        self._backup_dir: Path = AppPaths.data_dir() / "backups"
        self._backups: list[BackupEntry] = []
        self._lock = threading.Lock()
        self._backups_index_path: Path = self._backup_dir / "backups_index.json"

        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._load_index()

    # ------------------------------------------------------------------
    # Index persistence
    # ------------------------------------------------------------------

    def _load_index(self) -> None:
        """Load the backup index from disk."""
        if not self._backups_index_path.exists():
            return
        try:
            raw = self._backups_index_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            with self._lock:
                self._backups = [BackupEntry.from_dict(e) for e in data]
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load backups index: %s", exc)

    def _save_index(self) -> None:
        """Persist the backup index to disk."""
        try:
            with self._lock:
                data = [b.to_dict() for b in self._backups]
            self._backups_index_path.parent.mkdir(parents=True, exist_ok=True)
            self._backups_index_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Failed to save backups index: %s", exc)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_backup(
        self,
        name: str,
        backup_type: BackupType = BackupType.FULL,
        description: str = "",
        workspace: str = "",
        includes: dict[str, bool] | None = None,
    ) -> BackupEntry | None:
        """Create a zip archive of the selected application data.

        Parameters
        ----------
        name:
            Human-readable name for the backup.
        backup_type:
            Scope of the backup.
        description:
            Optional free-text description.
        workspace:
            Optional workspace name to restrict the backup to.
        includes:
            Override individual include flags.  Recognised keys:
            ``settings``, ``workspaces``, ``cases``, ``reports``,
            ``plugins``, ``notes``, ``bookmarks``.

        Returns
        -------
        BackupEntry or None
            The created entry, or *None* on failure.
        """
        import uuid

        flags = self._resolve_includes(backup_type, includes)
        entry_id = uuid.uuid4().hex[:12]
        archive_name = f"backup_{entry_id}.zip"
        archive_path = self._backup_dir / archive_name

        try:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                if flags["settings"]:
                    self._add_dir_to_zip(zf, AppPaths.config_dir(), "config")

                if flags["workspaces"]:
                    ws_dir = AppPaths.workspaces_dir()
                    if workspace:
                        target = ws_dir / workspace
                        if target.exists():
                            self._add_dir_to_zip(zf, target, f"workspaces/{workspace}")
                    else:
                        self._add_dir_to_zip(zf, ws_dir, "workspaces")

                if flags["cases"]:
                    cases_dir = AppPaths.data_dir() / "cases"
                    if cases_dir.exists():
                        self._add_dir_to_zip(zf, cases_dir, "data/cases")

                if flags["reports"]:
                    reports_dir = AppPaths.data_dir() / "reports"
                    if reports_dir.exists():
                        self._add_dir_to_zip(zf, reports_dir, "data/reports")

                if flags["plugins"]:
                    self._add_dir_to_zip(zf, AppPaths.plugins_dir(), "plugins")

                if flags["notes"]:
                    notes_dir = AppPaths.data_dir() / "notes"
                    if notes_dir.exists():
                        self._add_dir_to_zip(zf, notes_dir, "data/notes")

                if flags["bookmarks"]:
                    bookmarks_dir = AppPaths.data_dir() / "bookmarks"
                    if bookmarks_dir.exists():
                        self._add_dir_to_zip(zf, bookmarks_dir, "data/bookmarks")
        except (OSError, zipfile.BadZipFile) as exc:
            logger.error("Backup creation failed: %s", exc)
            archive_path.unlink(missing_ok=True)
            return None

        file_size = archive_path.stat().st_size
        checksum = self._compute_file_checksum(archive_path)

        entry = BackupEntry(
            id=entry_id,
            name=name,
            backup_type=backup_type,
            created_at=_now_iso(),
            file_path=str(archive_path),
            file_size=file_size,
            checksum=checksum,
            description=description,
            workspace=workspace,
            includes_settings=flags["settings"],
            includes_workspaces=flags["workspaces"],
            includes_cases=flags["cases"],
            includes_reports=flags["reports"],
            includes_plugins=flags["plugins"],
            includes_notes=flags["notes"],
            includes_bookmarks=flags["bookmarks"],
        )

        with self._lock:
            self._backups.append(entry)
        self._save_index()

        self._event_bus.emit(Events.BACKUP_CREATED, entry.to_dict())
        logger.info("Backup created: %s (%s)", name, entry_id)
        return entry

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore_backup(self, backup_id: str) -> bool:
        """Extract a backup archive and restore files to their original
        locations.

        Parameters
        ----------
        backup_id:
            The unique identifier of the backup to restore.

        Returns
        -------
        bool
            *True* when the restore completed successfully.
        """
        entry = self.get_backup(backup_id)
        if entry is None:
            logger.error("Backup not found: %s", backup_id)
            return False

        archive_path = Path(entry.file_path)
        if not archive_path.exists():
            logger.error("Backup archive missing: %s", archive_path)
            return False

        if entry.checksum and not self.verify_backup(backup_id):
            logger.error("Backup checksum verification failed: %s", backup_id)
            return False

        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.namelist():
                    if member.endswith("/"):
                        continue
                    parts = member.split("/", 1)
                    if len(parts) < 2:
                        continue

                    prefix = parts[0]
                    relative = parts[1]

                    if prefix == "config":
                        dest = AppPaths.config_dir() / relative
                    elif prefix == "workspaces":
                        dest = AppPaths.workspaces_dir() / relative
                    elif prefix == "data":
                        dest = AppPaths.data_dir() / relative
                    elif prefix == "plugins":
                        dest = AppPaths.plugins_dir() / relative
                    else:
                        continue

                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, dest.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
        except (OSError, zipfile.BadZipFile) as exc:
            logger.error("Backup restore failed: %s", exc)
            return False

        self._event_bus.emit(Events.BACKUP_RESTORED, entry.to_dict())
        logger.info("Backup restored: %s", backup_id)
        return True

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup archive and remove it from the index.

        Parameters
        ----------
        backup_id:
            The unique identifier of the backup to delete.

        Returns
        -------
        bool
            *True* when the backup was found and deleted.
        """
        entry = self.get_backup(backup_id)
        if entry is None:
            return False

        archive_path = Path(entry.file_path)
        try:
            archive_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not delete backup file %s: %s", archive_path, exc)

        with self._lock:
            self._backups = [b for b in self._backups if b.id != backup_id]
        self._save_index()

        self._event_bus.emit(Events.BACKUP_DELETED, entry.to_dict())
        logger.info("Backup deleted: %s", backup_id)
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_backups(self) -> list[BackupEntry]:
        """Return all known backups sorted by creation date descending."""
        with self._lock:
            entries = list(self._backups)
        entries.sort(key=lambda b: b.created_at, reverse=True)
        return entries

    def get_backup(self, backup_id: str) -> BackupEntry | None:
        """Return the entry matching *backup_id*, or *None*."""
        with self._lock:
            for entry in self._backups:
                if entry.id == backup_id:
                    return entry
        return None

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify_backup(self, backup_id: str) -> bool:
        """Verify the stored checksum matches the archive on disk.

        Parameters
        ----------
        backup_id:
            The unique identifier of the backup to verify.

        Returns
        -------
        bool
            *True* when the checksum matches.
        """
        entry = self.get_backup(backup_id)
        if entry is None or not entry.checksum:
            return False
        archive_path = Path(entry.file_path)
        if not archive_path.exists():
            return False
        actual = self._compute_file_checksum(archive_path)
        return actual.lower() == entry.checksum.lower()

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------

    def export_backup(self, backup_id: str, export_path: Path) -> bool:
        """Copy a backup archive to an external location.

        Parameters
        ----------
        backup_id:
            The unique identifier of the backup to export.
        export_path:
            Destination file path.

        Returns
        -------
        bool
            *True* on success.
        """
        entry = self.get_backup(backup_id)
        if entry is None:
            return False
        src = Path(entry.file_path)
        if not src.exists():
            return False
        try:
            export_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, export_path)
            return True
        except OSError as exc:
            logger.error("Backup export failed: %s", exc)
            return False

    def import_backup(self, backup_path: Path) -> BackupEntry | None:
        """Import an external backup archive into the backup directory.

        Parameters
        ----------
        backup_path:
            Path to the zip archive to import.

        Returns
        -------
        BackupEntry or None
            The imported entry, or *None* on failure.
        """
        import uuid

        if not backup_path.exists():
            logger.error("Import source does not exist: %s", backup_path)
            return None

        if not zipfile.is_zipfile(backup_path):
            logger.error("Import source is not a valid zip file: %s", backup_path)
            return None

        entry_id = uuid.uuid4().hex[:12]
        dest = self._backup_dir / f"backup_{entry_id}.zip"

        try:
            shutil.copy2(backup_path, dest)
        except OSError as exc:
            logger.error("Import copy failed: %s", exc)
            return None

        file_size = dest.stat().st_size
        checksum = self._compute_file_checksum(dest)

        entry = BackupEntry(
            id=entry_id,
            name=backup_path.stem,
            backup_type=BackupType.FULL,
            created_at=_now_iso(),
            file_path=str(dest),
            file_size=file_size,
            checksum=checksum,
            description="Imported backup",
        )

        with self._lock:
            self._backups.append(entry)
        self._save_index()

        self._event_bus.emit(Events.BACKUP_CREATED, entry.to_dict())
        logger.info("Backup imported: %s -> %s", backup_path, entry_id)
        return entry

    # ------------------------------------------------------------------
    # Size helpers
    # ------------------------------------------------------------------

    def get_backup_size(self, backup_id: str) -> int:
        """Return the file size in bytes of the backup archive, or 0."""
        entry = self.get_backup(backup_id)
        if entry is None:
            return 0
        archive_path = Path(entry.file_path)
        if not archive_path.exists():
            return 0
        try:
            return archive_path.stat().st_size
        except OSError:
            return 0

    def get_total_backup_size(self) -> int:
        """Return the combined size of all backup archives in bytes."""
        total = 0
        with self._lock:
            entries = list(self._backups)
        for entry in entries:
            archive_path = Path(entry.file_path)
            try:
                if archive_path.exists():
                    total += archive_path.stat().st_size
            except OSError:
                pass
        return total

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """Delete the oldest backups, keeping at most *keep_count*.

        Returns the number of backups removed.
        """
        sorted_entries = self.list_backups()
        to_remove = sorted_entries[keep_count:]
        removed = 0
        for entry in to_remove:
            if self.delete_backup(entry.id):
                removed += 1
        return removed

    # ------------------------------------------------------------------
    # Contents listing
    # ------------------------------------------------------------------

    def get_backup_contents(self, backup_id: str) -> list[str]:
        """List the file paths stored inside the backup zip without
        extracting.

        Parameters
        ----------
        backup_id:
            The unique identifier of the backup.

        Returns
        -------
        list[str]
            Sorted list of member paths inside the archive.
        """
        entry = self.get_backup(backup_id)
        if entry is None:
            return []
        archive_path = Path(entry.file_path)
        if not archive_path.exists():
            return []
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                return sorted(zf.namelist())
        except (OSError, zipfile.BadZipFile) as exc:
            logger.warning("Could not list backup contents: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def create_quick_backup(self) -> BackupEntry | None:
        """Create a full backup with an auto-generated name.

        Returns
        -------
        BackupEntry or None
            The created entry, or *None* on failure.
        """
        timestamp = _now_iso().replace(":", "-").replace(".", "-")
        name = f"quick_backup_{timestamp}"
        return self.create_backup(name, BackupType.FULL, description="Quick backup")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_includes(
        backup_type: BackupType,
        overrides: dict[str, bool] | None,
    ) -> dict[str, bool]:
        """Build the final include flags from the backup type and
        optional overrides."""
        defaults: dict[str, bool] = {
            "settings": True,
            "workspaces": True,
            "cases": True,
            "reports": True,
            "plugins": True,
            "notes": True,
            "bookmarks": True,
        }

        if backup_type == BackupType.SETTINGS_ONLY:
            defaults = dict.fromkeys(defaults, False)
            defaults["settings"] = True
        elif backup_type == BackupType.WORKSPACE_ONLY:
            defaults = dict.fromkeys(defaults, False)
            defaults["workspaces"] = True
        elif backup_type == BackupType.DATA_ONLY:
            defaults = dict.fromkeys(defaults, False)
            defaults["cases"] = True
            defaults["reports"] = True
            defaults["notes"] = True
            defaults["bookmarks"] = True
        elif backup_type == BackupType.CUSTOM:
            defaults = dict.fromkeys(defaults, False)

        if overrides:
            defaults.update(overrides)

        return defaults

    @staticmethod
    def _add_dir_to_zip(zf: zipfile.ZipFile, directory: Path, arc_prefix: str) -> None:
        """Recursively add *directory* to *zf* under *arc_prefix*."""
        if not directory.exists():
            return
        for item in directory.rglob("*"):
            if item.is_file():
                arcname = f"{arc_prefix}/{item.relative_to(directory)}"
                zf.write(item, arcname)

    @staticmethod
    def _compute_file_checksum(file_path: Path) -> str:
        """Compute a SHA-256 hex digest of the file at *file_path*."""
        import hashlib as _hashlib

        h = _hashlib.sha256()
        with Path(file_path).open("rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
