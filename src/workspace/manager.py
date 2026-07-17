"""Workspace management for SecurePacketAnalyzerPro.

A workspace encapsulates user-specific state – layout, filters,
capture preferences, and more – persisted as individual JSON files
inside the application's workspaces directory.
"""

from __future__ import annotations

import copy
import json
import logging
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.settings import SettingsManager
from src.utils.paths import AppPaths

logger = logging.getLogger(__name__)


@dataclass
class Workspace:
    """Represents a single user workspace.

    All fields have sensible defaults so that a minimal
    ``Workspace(name="foo")`` is immediately usable.
    """

    name: str
    theme: str = "dark"
    filters: dict[str, Any] = field(default_factory=dict)
    window_geometry: bytes | None = None
    window_state: bytes | None = None
    capture_preferences: dict[str, Any] = field(default_factory=dict)
    dashboard_layout: dict[str, Any] = field(default_factory=dict)
    export_location: str = ""
    notification_settings: dict[str, Any] = field(default_factory=dict)
    accessibility_preferences: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    modified_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.modified_at:
            self.modified_at = now

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise the workspace to a plain dictionary.

        ``window_geometry`` and ``window_state`` are stored as
        base-64 strings when present so that the dict is JSON-safe.
        """
        data = asdict(self)
        for key in ("window_geometry", "window_state"):
            val = data.get(key)
            if isinstance(val, bytes):
                import base64

                data[key] = base64.b64encode(val).decode("ascii")
            elif val is None:
                data[key] = None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workspace:
        """Reconstruct a :class:`Workspace` from a dictionary."""
        import base64

        data = copy.deepcopy(data)
        for key in ("window_geometry", "window_state"):
            val = data.get(key)
            if isinstance(val, str) and val:
                data[key] = base64.b64decode(val.encode("ascii"))
            else:
                data[key] = None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ------------------------------------------------------------------
# WorkspaceManager
# ------------------------------------------------------------------


class WorkspaceManager:
    """Manages the lifecycle of :class:`Workspace` instances on disk.

    Each workspace is stored as an individual ``<name>.json`` file
    inside the application's workspaces directory.  The *active*
    workspace name is persisted in the application settings.

    Parameters
    ----------
    settings:
        Application settings.  When *None* a fresh default
        :class:`SettingsManager` is created.
    """

    def __init__(self, settings: SettingsManager | None = None) -> None:
        self._settings = settings or SettingsManager()
        AppPaths.workspaces_dir().mkdir(parents=True, exist_ok=True)
        self._ensure_default_workspace()

    # ------------------------------------------------------------------
    # Directory helpers
    # ------------------------------------------------------------------

    @property
    def workspaces_dir(self) -> Path:
        """Return the directory where workspace files are stored."""
        return AppPaths.workspaces_dir()

    @property
    def active_workspace_name(self) -> str:
        """Return the name of the currently active workspace."""
        return self._settings.get("workspace.active_workspace", "default")

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def create_workspace(self, name: str) -> Workspace:
        """Create and persist a new workspace.

        Parameters
        ----------
        name:
            Unique workspace name.  If a workspace with this name
            already exists a :class:`FileExistsError` is raised.
        """
        ws_path = self._workspace_path(name)
        if ws_path.exists():
            raise FileExistsError(f"Workspace '{name}' already exists")

        ws = Workspace(name=name)
        self.save_workspace(ws)
        logger.info("Created workspace '%s'", name)
        return ws

    def delete_workspace(self, name: str) -> bool:
        """Delete a workspace by name.

        The currently active workspace cannot be deleted.

        Returns ``True`` on success, ``False`` if the workspace does
        not exist or is active.
        """
        if name == self.active_workspace_name:
            logger.warning("Cannot delete the active workspace '%s'", name)
            return False

        ws_path = self._workspace_path(name)
        if not ws_path.exists():
            logger.warning("Workspace '%s' does not exist", name)
            return False

        ws_path.unlink()
        logger.info("Deleted workspace '%s'", name)
        return True

    def rename_workspace(self, old_name: str, new_name: str) -> bool:
        """Rename an existing workspace.

        Returns ``False`` if the source does not exist, the
        destination already exists, or *old_name* is active.
        """
        if old_name == self.active_workspace_name:
            logger.warning("Cannot rename the active workspace")
            return False

        old_path = self._workspace_path(old_name)
        new_path = self._workspace_path(new_name)

        if not old_path.exists():
            logger.warning("Source workspace '%s' does not exist", old_name)
            return False
        if new_path.exists():
            logger.warning("Destination workspace '%s' already exists", new_name)
            return False

        ws = self.load_workspace(old_name)
        if ws is None:
            return False

        ws.name = new_name
        ws.modified_at = datetime.now(timezone.utc).isoformat()
        self.save_workspace(ws)
        old_path.unlink()
        logger.info("Renamed workspace '%s' -> '%s'", old_name, new_name)
        return True

    def duplicate_workspace(self, source_name: str, new_name: str) -> Workspace:
        """Create a deep copy of *source_name* under *new_name*.

        Raises ``FileNotFoundError`` if the source does not exist or
        ``FileExistsError`` if the destination already exists.
        """
        source = self.get_workspace(source_name)
        if source is None:
            raise FileNotFoundError(f"Source workspace '{source_name}' not found")

        dest_path = self._workspace_path(new_name)
        if dest_path.exists():
            raise FileExistsError(f"Workspace '{new_name}' already exists")

        dup = Workspace(
            name=new_name,
            theme=source.theme,
            filters=copy.deepcopy(source.filters),
            window_geometry=source.window_geometry,
            window_state=source.window_state,
            capture_preferences=copy.deepcopy(source.capture_preferences),
            dashboard_layout=copy.deepcopy(source.dashboard_layout),
            export_location=source.export_location,
            notification_settings=copy.deepcopy(source.notification_settings),
            accessibility_preferences=copy.deepcopy(source.accessibility_preferences),
        )
        self.save_workspace(dup)
        logger.info("Duplicated workspace '%s' -> '%s'", source_name, new_name)
        return dup

    def get_workspace(self, name: str) -> Workspace | None:
        """Return the workspace for *name*, or *None* if it doesn't exist."""
        return self.load_workspace(name)

    def list_workspaces(self) -> list[str]:
        """Return sorted names of all available workspaces."""
        names: list[str] = []
        for p in self.workspaces_dir.glob("*.json"):
            names.append(p.stem)
        names.sort()
        return names

    # ------------------------------------------------------------------
    # Active workspace
    # ------------------------------------------------------------------

    def set_active(self, name: str) -> None:
        """Set the active workspace.

        Raises ``FileNotFoundError`` if the workspace file does not exist.
        """
        ws_path = self._workspace_path(name)
        if not ws_path.exists():
            raise FileNotFoundError(f"Workspace '{name}' not found")
        self._settings.set("workspace.active_workspace", name)
        logger.info("Active workspace set to '%s'", name)

    def get_active(self) -> Workspace:
        """Return the currently active workspace.

        Falls back to creating and returning the default workspace
        if the configured active workspace is missing.
        """
        name = self.active_workspace_name
        ws = self.load_workspace(name)
        if ws is not None:
            return ws

        logger.warning("Active workspace '%s' missing – recreating default", name)
        return self.create_workspace("default")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_workspace(self, workspace: Workspace) -> None:
        """Persist a workspace to its JSON file."""
        workspace.modified_at = datetime.now(timezone.utc).isoformat()
        ws_path = self._workspace_path(workspace.name)
        ws_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = workspace.to_dict()
            ws_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Failed to save workspace '%s': %s", workspace.name, exc)
            raise

    def load_workspace(self, name: str) -> Workspace | None:
        """Load and return a workspace from disk.

        Returns *None* if the file does not exist or is unreadable.
        """
        ws_path = self._workspace_path(name)
        if not ws_path.is_file():
            return None

        try:
            raw = ws_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return Workspace.from_dict(data)
        except (json.JSONDecodeError, OSError, TypeError, KeyError) as exc:
            logger.warning("Failed to load workspace '%s': %s", name, exc)
            return None

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------

    def export_workspace(self, name: str, path: Path) -> bool:
        """Export a workspace JSON file to *path*.

        Returns ``True`` on success.
        """
        ws = self.load_workspace(name)
        if ws is None:
            logger.warning("Cannot export – workspace '%s' not found", name)
            return False

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = ws.to_dict()
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Exported workspace '%s' to %s", name, path)
            return True
        except OSError as exc:
            logger.error("Export failed for workspace '%s': %s", name, exc)
            return False

    def import_workspace(
        self, path: Path, name: str | None = None
    ) -> Workspace | None:
        """Import a workspace from an external JSON file.

        Parameters
        ----------
        path:
            Source JSON file.
        name:
            Optional override for the workspace name.  When *None* the
            name stored inside the file is used.

        Returns
        -------
        Workspace | None
            The imported workspace, or *None* on failure.
        """
        if not path.is_file():
            logger.warning("Import source does not exist: %s", path)
            return None

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read import file %s: %s", path, exc)
            return None

        if name is not None:
            data["name"] = name

        try:
            ws = Workspace.from_dict(data)
        except (TypeError, KeyError) as exc:
            logger.warning("Invalid workspace data in %s: %s", path, exc)
            return None

        # Avoid clobbering an existing workspace
        existing_path = self._workspace_path(ws.name)
        if existing_path.exists():
            ws.name = f"{ws.name}_imported_{uuid.uuid4().hex[:6]}"
            ws = Workspace.from_dict({**data, "name": ws.name})

        self.save_workspace(ws)
        logger.info("Imported workspace '%s' from %s", ws.name, path)
        return ws

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _workspace_path(self, name: str) -> Path:
        """Return the JSON file path for a named workspace."""
        return self.workspaces_dir / f"{name}.json"

    def _ensure_default_workspace(self) -> None:
        """Create the default workspace if no workspaces exist yet."""
        if not self.list_workspaces():
            self.create_workspace("default")
            self._settings.set("workspace.active_workspace", "default")
            logger.info("Created default workspace (first run)")
