"""Auto-update framework with download, verification, and rollback support."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from src.analysis.models import _now_iso
from src.config.settings import SettingsManager
from src.security.manager import SecurityManager
from src.services.event_bus import EventBus, Events
from src.utils.paths import AppPaths

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UpdateChannel(Enum):
    """Release channel for update checks."""

    STABLE = auto()
    BETA = auto()
    DEV = auto()


class UpdateStatus(Enum):
    """Current state of the update lifecycle."""

    CHECKING = auto()
    AVAILABLE = auto()
    NOT_AVAILABLE = auto()
    DOWNLOADING = auto()
    DOWNLOADED = auto()
    INSTALLING = auto()
    INSTALLED = auto()
    FAILED = auto()
    ROLLED_BACK = auto()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ReleaseInfo:
    """Describes a single release available from the update server."""

    version: str
    channel: UpdateChannel = UpdateChannel.STABLE
    release_date: str = ""
    download_url: str = ""
    checksum: str = ""
    checksum_algorithm: str = "sha256"
    release_notes: str = ""
    min_python_version: str = "3.12"
    file_size: int = 0
    is_security_update: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "version": self.version,
            "channel": self.channel.name,
            "release_date": self.release_date,
            "download_url": self.download_url,
            "checksum": self.checksum,
            "checksum_algorithm": self.checksum_algorithm,
            "release_notes": self.release_notes,
            "min_python_version": self.min_python_version,
            "file_size": self.file_size,
            "is_security_update": self.is_security_update,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReleaseInfo:
        """Reconstruct a ``ReleaseInfo`` from a previously serialized dict."""
        return cls(
            version=data["version"],
            channel=UpdateChannel[data.get("channel", "STABLE")],
            release_date=data.get("release_date", ""),
            download_url=data.get("download_url", ""),
            checksum=data.get("checksum", ""),
            checksum_algorithm=data.get("checksum_algorithm", "sha256"),
            release_notes=data.get("release_notes", ""),
            min_python_version=data.get("min_python_version", "3.12"),
            file_size=data.get("file_size", 0),
            is_security_update=data.get("is_security_update", False),
        )


@dataclass
class UpdateHistory:
    """Records a single past update attempt."""

    version_from: str
    version_to: str
    timestamp: str
    success: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "version_from": self.version_from,
            "version_to": self.version_to,
            "timestamp": self.timestamp,
            "success": self.success,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UpdateHistory:
        """Reconstruct an ``UpdateHistory`` from a previously serialized dict."""
        return cls(
            version_from=data["version_from"],
            version_to=data["version_to"],
            timestamp=data.get("timestamp", ""),
            success=data.get("success", False),
            notes=data.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# Update manager
# ---------------------------------------------------------------------------


class UpdateManager:
    """Orchestrates the full update lifecycle: check, download, verify,
    install, and rollback.

    Parameters
    ----------
    settings:
        Application settings manager.  A default instance is created when
        *None*.
    security:
        Security manager used for hashing and URL validation.  A default
        instance is created when *None*.
    """

    def __init__(
        self,
        settings: SettingsManager | None = None,
        security: SecurityManager | None = None,
    ) -> None:
        self._settings = settings or SettingsManager()
        self._security = security or SecurityManager(self._settings)
        self._event_bus = EventBus.instance()

        self._status: UpdateStatus = UpdateStatus.NOT_AVAILABLE
        self._current_release: ReleaseInfo | None = None
        self._history: list[UpdateHistory] = []
        self._lock = threading.Lock()

        self._update_dir: Path = AppPaths.data_dir() / "updates"
        self._backup_dir: Path = AppPaths.data_dir() / "backups" / "pre_update"
        self._history_path: Path = self._update_dir / "update_history.json"

        self._update_dir.mkdir(parents=True, exist_ok=True)
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        self._load_history()

    # ------------------------------------------------------------------
    # Version / status helpers
    # ------------------------------------------------------------------

    def get_current_version(self) -> str:
        """Return the application's current version string."""
        from src import __version__

        return __version__

    def get_status(self) -> UpdateStatus:
        """Return the current update status."""
        with self._lock:
            return self._status

    def get_history(self) -> list[UpdateHistory]:
        """Return the full update history."""
        with self._lock:
            return list(self._history)

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def set_channel(self, channel: UpdateChannel) -> None:
        """Set the preferred update channel and persist the choice."""
        self._settings.set("updates.channel", channel.name.lower())

    def get_channel(self) -> UpdateChannel:
        """Return the currently configured update channel."""
        raw = self._settings.get("updates.channel", "stable")
        try:
            return UpdateChannel[raw.upper()]
        except KeyError:
            return UpdateChannel.STABLE

    # ------------------------------------------------------------------
    # Auto-check preference
    # ------------------------------------------------------------------

    def set_auto_check(self, enabled: bool) -> None:
        """Enable or disable automatic update checks on startup."""
        self._settings.set("updates.auto_check", enabled)

    def get_auto_check(self) -> bool:
        """Return whether automatic update checks are enabled."""
        return bool(self._settings.get("updates.auto_check", True))

    # ------------------------------------------------------------------
    # Check for updates
    # ------------------------------------------------------------------

    def check_for_updates(self, server_url: str = "") -> ReleaseInfo | None:
        """Query the update server for a newer release.

        Parameters
        ----------
        server_url:
            Explicit URL to check.  When empty the method returns
            *None* after recording that no update is available.

        Returns
        -------
        ReleaseInfo or None
            A ``ReleaseInfo`` when an update is available, otherwise
            *None*.
        """
        with self._lock:
            self._status = UpdateStatus.CHECKING

        self._event_bus.emit(Events.UPDATE_CHECK_STARTED, {})

        if not server_url:
            logger.debug("No server URL configured; skipping update check")
            with self._lock:
                self._status = UpdateStatus.NOT_AVAILABLE
            self._event_bus.emit(Events.UPDATE_NOT_AVAILABLE, {})
            return None

        if not self._security.validate_url(server_url):
            logger.warning("Rejected invalid update server URL: %s", server_url)
            with self._lock:
                self._status = UpdateStatus.FAILED
            return None

        try:
            request = urllib.request.Request(  # noqa: S310 -- URL validated above
                server_url,
                headers={"User-Agent": f"SecurePacketAnalyzerPro/{self.get_current_version()}"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 -- URL validated above
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Update check failed: %s", exc)
            with self._lock:
                self._status = UpdateStatus.NOT_AVAILABLE
            self._event_bus.emit(Events.UPDATE_NOT_AVAILABLE, {})
            return None

        release = ReleaseInfo.from_dict(data)
        self._current_release = release

        if self._is_newer(release.version):
            with self._lock:
                self._status = UpdateStatus.AVAILABLE
            self._event_bus.emit(Events.UPDATE_AVAILABLE, release.to_dict())
            logger.info(
                "Update available: %s (current: %s)",
                release.version,
                self.get_current_version(),
            )
            return release

        with self._lock:
            self._status = UpdateStatus.NOT_AVAILABLE
        self._event_bus.emit(Events.UPDATE_NOT_AVAILABLE, {})
        return None

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download_update(
        self,
        release: ReleaseInfo,
        progress_callback: Any = None,
    ) -> Path | None:
        """Download the update package and verify its checksum.

        Parameters
        ----------
        release:
            The release to download.
        progress_callback:
            Optional callable invoked as
            ``progress_callback(downloaded_bytes, total_bytes)``.

        Returns
        -------
        Path or None
            Path to the downloaded file, or *None* on failure.
        """
        with self._lock:
            self._status = UpdateStatus.DOWNLOADING

        self._event_bus.emit(
            Events.UPDATE_DOWNLOAD_STARTED,
            {"version": release.version},
        )

        if not release.download_url:
            logger.error("No download URL in release info")
            with self._lock:
                self._status = UpdateStatus.FAILED
            self._event_bus.emit(Events.UPDATE_DOWNLOAD_FAILED, {"reason": "no_url"})
            return None

        if not self._security.validate_url(release.download_url):
            logger.warning("Rejected invalid download URL: %s", release.download_url)
            with self._lock:
                self._status = UpdateStatus.FAILED
            self._event_bus.emit(Events.UPDATE_DOWNLOAD_FAILED, {"reason": "invalid_url"})
            return None

        dest = self._update_dir / f"update_{release.version}.zip"

        try:
            request = urllib.request.Request(  # noqa: S310 -- URL validated above
                release.download_url,
                headers={"User-Agent": f"SecurePacketAnalyzerPro/{self.get_current_version()}"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 -- URL validated above
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                with dest.open("wb") as fh:
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback is not None:
                            try:
                                progress_callback(downloaded, total)
                            except Exception:
                                logger.debug("Progress callback raised", exc_info=True)
        except (urllib.error.URLError, OSError) as exc:
            logger.error("Download failed: %s", exc)
            dest.unlink(missing_ok=True)
            with self._lock:
                self._status = UpdateStatus.FAILED
            self._event_bus.emit(
                Events.UPDATE_DOWNLOAD_FAILED,
                {"reason": str(exc)},
            )
            return None

        if release.checksum and not self.validate_download(dest, release.checksum):
            logger.error("Checksum verification failed for %s", dest)
            dest.unlink(missing_ok=True)
            with self._lock:
                self._status = UpdateStatus.FAILED
            self._event_bus.emit(
                Events.UPDATE_DOWNLOAD_FAILED,
                {"reason": "checksum_mismatch"},
            )
            return None

        with self._lock:
            self._status = UpdateStatus.DOWNLOADED

        self._event_bus.emit(
            Events.UPDATE_DOWNLOAD_COMPLETED,
            {"version": release.version, "path": str(dest)},
        )
        logger.info("Update downloaded: %s", dest)
        return dest

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------

    def create_backup(self) -> Path | None:
        """Create a pre-update backup of critical application data.

        Copies configuration files, the active workspace directory, and
        the data directory into ``_backup_dir``.

        Returns
        -------
        Path or None
            The backup root path, or *None* on failure.
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = self._backup_dir / f"backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)

        try:
            self._copy_if_exists(AppPaths.config_dir(), backup_path / "config")
            self._copy_if_exists(AppPaths.data_dir(), backup_path / "data")
            self._copy_if_exists(AppPaths.workspaces_dir(), backup_path / "workspaces")
            self._copy_if_exists(AppPaths.plugins_dir(), backup_path / "plugins")
        except Exception as exc:
            logger.error("Backup creation failed: %s", exc)
            return None

        logger.info("Pre-update backup created at %s", backup_path)
        return backup_path

    def install_update(self, download_path: Path) -> bool:
        """Record a successful update installation.

        In this foundation the method persists the new version in
        settings and records the transition in history.

        Parameters
        ----------
        download_path:
            Path to the downloaded update package.

        Returns
        -------
        bool
            *True* when the installation was recorded successfully.
        """
        if not download_path.exists():
            logger.error("Download path does not exist: %s", download_path)
            return False

        with self._lock:
            self._status = UpdateStatus.INSTALLING

        self._event_bus.emit(Events.UPDATE_INSTALL_STARTED, {})

        previous_version = self.get_current_version()
        release = self._current_release
        new_version = release.version if release else "unknown"

        self._settings.set("general.version", new_version)

        self.record_history(previous_version, new_version, True, "install_recorded")

        with self._lock:
            self._status = UpdateStatus.INSTALLED

        self._event_bus.emit(
            Events.UPDATE_INSTALL_COMPLETED,
            {"from": previous_version, "to": new_version},
        )
        logger.info("Update recorded: %s -> %s", previous_version, new_version)
        return True

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def rollback(self, backup_path: Path) -> bool:
        """Restore application data from a pre-update backup.

        Parameters
        ----------
        backup_path:
            Root directory of the backup created by :meth:`create_backup`.

        Returns
        -------
        bool
            *True* when rollback completed successfully.
        """
        if not backup_path.exists():
            logger.error("Backup path does not exist: %s", backup_path)
            return False

        try:
            config_src = backup_path / "config"
            if config_src.exists():
                self._restore_tree(config_src, AppPaths.config_dir())

            data_src = backup_path / "data"
            if data_src.exists():
                self._restore_tree(data_src, AppPaths.data_dir())

            workspaces_src = backup_path / "workspaces"
            if workspaces_src.exists():
                self._restore_tree(workspaces_src, AppPaths.workspaces_dir())

            plugins_src = backup_path / "plugins"
            if plugins_src.exists():
                self._restore_tree(plugins_src, AppPaths.plugins_dir())
        except Exception as exc:
            logger.error("Rollback failed: %s", exc)
            with self._lock:
                self._status = UpdateStatus.FAILED
            return False

        with self._lock:
            self._status = UpdateStatus.ROLLED_BACK

        self._event_bus.emit(Events.UPDATE_ROLLBACK, {"backup": str(backup_path)})
        logger.info("Rollback completed from %s", backup_path)
        return True

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def record_history(
        self,
        version_from: str,
        version_to: str,
        success: bool,
        notes: str = "",
    ) -> None:
        """Append an entry to the update history and persist it."""
        entry = UpdateHistory(
            version_from=version_from,
            version_to=version_to,
            timestamp=_now_iso(),
            success=success,
            notes=notes,
        )
        with self._lock:
            self._history.append(entry)
        self._save_history()

    def _load_history(self) -> None:
        """Load update history from disk."""
        if not self._history_path.exists():
            return
        try:
            raw = self._history_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            with self._lock:
                self._history = [UpdateHistory.from_dict(e) for e in data]
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load update history: %s", exc)

    def _save_history(self) -> None:
        """Persist update history to disk."""
        try:
            with self._lock:
                data = [e.to_dict() for e in self._history]
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            self._history_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Failed to save update history: %s", exc)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_release_notes(notes: str) -> str:
        """Perform basic cleanup on release notes for display."""
        lines = notes.splitlines()
        cleaned = [line.rstrip() for line in lines]
        return "\n".join(cleaned).strip()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_download(self, file_path: Path, expected_checksum: str) -> bool:
        """Verify that *file_path* matches the expected SHA-256 checksum.

        Parameters
        ----------
        file_path:
            Path to the downloaded file.
        expected_checksum:
            Hex-encoded expected hash.
        """
        if not file_path.exists():
            return False
        try:
            h = hashlib.sha256()
            with file_path.open("rb") as fh:
                while True:
                    chunk = fh.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            actual = h.hexdigest()
            return actual.lower() == expected_checksum.lower()
        except OSError as exc:
            logger.error("Checksum computation failed for %s: %s", file_path, exc)
            return False

    # ------------------------------------------------------------------
    # Cleanup / diagnostics
    # ------------------------------------------------------------------

    def cleanup_downloads(self) -> int:
        """Remove old update packages from the download directory.

        Returns the number of files removed.
        """
        removed = 0
        if not self._update_dir.exists():
            return removed
        for item in self._update_dir.iterdir():
            if item.is_file() and item.suffix == ".zip":
                try:
                    item.unlink()
                    removed += 1
                except OSError as exc:
                    logger.warning("Could not remove %s: %s", item, exc)
        return removed

    def get_available_space(self) -> int:
        """Return free disk space in bytes on the update partition."""
        try:
            usage = shutil.disk_usage(str(self._update_dir))
            return usage.free
        except OSError:
            return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_newer(self, remote_version: str) -> bool:
        """Return *True* when *remote_version* is newer than the local one."""

        def _parse(v: str) -> tuple[int, ...]:
            parts = v.strip().split(".")
            result: list[int] = []
            for p in parts:
                try:
                    result.append(int(p))
                except ValueError:
                    break
            return tuple(result)

        local = _parse(self.get_current_version())
        remote = _parse(remote_version)
        return remote > local

    @staticmethod
    def _copy_if_exists(src: Path, dst: Path) -> None:
        """Recursively copy *src* to *dst* if *src* exists."""
        if not src.exists():
            return
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    @staticmethod
    def _restore_tree(src: Path, dst: Path) -> None:
        """Overwrite *dst* with the contents of *src*."""
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
