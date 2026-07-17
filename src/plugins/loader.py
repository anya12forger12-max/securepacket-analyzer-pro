"""Plugin discovery, loading, and validation."""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import shutil
import sys
import threading
from pathlib import Path
from typing import Any

from src.plugins.base import PluginBase, PluginMetadata, PluginState
from src.security.manager import SecurityManager
from src.utils.paths import AppPaths

logger = logging.getLogger(__name__)


class PluginLoader:
    """Discovers, imports, validates, and manages the lifecycle of plugins.

    Each plugin resides in its own subdirectory under the plugins root.
    A valid plugin directory must contain a ``plugin.json`` manifest with
    at least the mandatory :class:`PluginMetadata` fields and an
    ``entry_point`` key pointing to the Python module (without ``.py``
    extension) that exports a :class:`PluginBase` subclass.

    Parameters
    ----------
    security_manager:
        Optional :class:`SecurityManager` used for safe file I/O and
        plugin signature verification.  A new instance is created when
        *None* is supplied.
    """

    def __init__(self, security_manager: SecurityManager | None = None) -> None:
        self._security: SecurityManager = security_manager or SecurityManager()
        self._loaded_modules: dict[str, Any] = {}
        self._lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_plugins(self, plugin_dir: Path | None = None) -> list[Path]:
        """Scan a directory tree for installable plugins.

        Parameters
        ----------
        plugin_dir:
            Root directory to scan.  When *None* the default plugins
            directory from :class:`AppPaths` is used.

        Returns
        -------
        list[Path]
            Paths to plugin root directories that contain a
            ``plugin.json`` manifest.
        """
        root = plugin_dir or self.get_plugin_directory()
        root.mkdir(parents=True, exist_ok=True)

        discovered: list[Path] = []
        for candidate in sorted(root.iterdir()):
            if not candidate.is_dir():
                continue
            manifest = candidate / "plugin.json"
            if manifest.is_file():
                discovered.append(candidate)
        return discovered

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def load_metadata(self, plugin_path: Path) -> PluginMetadata | None:
        """Read and parse the ``plugin.json`` manifest at *plugin_path*.

        Parameters
        ----------
        plugin_path:
            Directory containing ``plugin.json``.

        Returns
        -------
        PluginMetadata | None
            Parsed metadata, or *None* on error.
        """
        manifest = plugin_path / "plugin.json"
        try:
            raw_text = self._security.safe_file_read(manifest)
        except Exception:
            logger.exception("Failed to read manifest: %s", manifest)
            return None

        if raw_text is None:
            logger.error("Security manager rejected read: %s", manifest)
            return None

        try:
            data: dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in %s: %s", manifest, exc)
            return None

        try:
            metadata = PluginMetadata.from_dict(data)
        except Exception:
            logger.exception("Failed to parse metadata from %s", manifest)
            return None

        return metadata

    # ------------------------------------------------------------------
    # Loading / unloading
    # ------------------------------------------------------------------

    def load_plugin(
        self, plugin_path: Path, metadata: PluginMetadata
    ) -> PluginBase | None:
        """Import, instantiate, and initialise a plugin.

        The ``entry_point`` field in ``plugin.json`` is used to locate
        the Python module.  The module must expose a single
        :class:`PluginBase` subclass or a module-level ``create_plugin``
        callable that returns one.

        Parameters
        ----------
        plugin_path:
            Root directory of the plugin.
        metadata:
            Parsed metadata for the plugin.

        Returns
        -------
        PluginBase | None
            The initialised plugin instance, or *None* on error.
        """
        manifest = plugin_path / "plugin.json"
        try:
            manifest_text = self._security.safe_file_read(manifest)
        except Exception:
            logger.exception("Cannot read manifest for load: %s", manifest)
            return None

        if manifest_text is None:
            logger.error("Security manager rejected manifest read: %s", manifest)
            return None

        try:
            manifest_data: dict[str, Any] = json.loads(manifest_text)
        except json.JSONDecodeError:
            logger.error("Corrupt manifest: %s", manifest)
            return None

        entry_point: str = manifest_data.get("entry_point", "")
        if not entry_point:
            logger.error("No entry_point in manifest: %s", manifest)
            metadata.state = PluginState.ERROR
            metadata.load_error = "No entry_point defined in plugin.json"
            return None

        module_path = plugin_path / f"{entry_point}.py"
        if not module_path.is_file():
            logger.error(
                "Entry point module not found: %s", module_path
            )
            metadata.state = PluginState.ERROR
            metadata.load_error = f"Entry point module not found: {entry_point}.py"
            return None

        module_name = f"src.plugins._external.{metadata.id}.{entry_point}"
        module = self._safe_import(module_name, module_path)
        if module is None:
            metadata.state = PluginState.ERROR
            metadata.load_error = f"Failed to import module: {entry_point}"
            return None

        plugin_instance = self._instantiate_plugin(module, metadata)
        if plugin_instance is None:
            metadata.state = PluginState.ERROR
            metadata.load_error = "No PluginBase subclass or create_plugin factory found"
            return None

        context = self._build_context()
        try:
            plugin_instance.initialize(context)
        except Exception:
            logger.exception(
                "Plugin %s raised during initialize()", metadata.name
            )
            metadata.state = PluginState.ERROR
            metadata.load_error = "initialize() raised an exception"
            return None

        with self._lock:
            self._loaded_modules[metadata.id] = module

        metadata.state = PluginState.ENABLED
        metadata.load_error = ""
        logger.info("Loaded plugin: %s (%s)", metadata.name, metadata.id)
        return plugin_instance

    def unload_plugin(self, plugin_id: str) -> None:
        """Remove a loaded plugin's module references from the process.

        This does **not** call :meth:`PluginBase.shutdown` — the caller
        is responsible for invoking it before calling this method.

        Parameters
        ----------
        plugin_id:
            The unique identifier of the plugin to unload.
        """
        with self._lock:
            module = self._loaded_modules.pop(plugin_id, None)

        if module is not None:
            prefix = f"src.plugins._external.{plugin_id}."
            keys_to_remove = [
                key for key in sys.modules if key.startswith(prefix)
            ]
            for key in keys_to_remove:
                sys.modules.pop(key, None)
            logger.info("Unloaded plugin modules: %s", plugin_id)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_plugin(self, metadata: PluginMetadata) -> list[str]:
        """Validate that metadata is complete and API-compatible.

        Parameters
        ----------
        metadata:
            Metadata to validate.

        Returns
        -------
        list[str]
            Error descriptions.  Empty when the metadata is valid.
        """
        errors: list[str] = []

        if not metadata.id:
            errors.append("Plugin id is missing")
        if not metadata.name:
            errors.append("Plugin name is missing")
        if not metadata.version:
            errors.append("Plugin version is missing")
        if not metadata.api_version:
            errors.append("Plugin api_version is missing")

        for perm in metadata.permissions:
            if not isinstance(perm, type(metadata.permissions[0])):
                errors.append(f"Invalid permission value: {perm}")

        return errors

    def check_dependencies(
        self,
        metadata: PluginMetadata,
        loaded_plugins: dict[str, PluginBase],
    ) -> list[str]:
        """Return the list of dependency plugin IDs that are not loaded.

        Parameters
        ----------
        metadata:
            Metadata whose ``dependencies`` list is checked.
        loaded_plugins:
            Mapping of currently loaded plugin IDs to instances.

        Returns
        -------
        list[str]
            Missing plugin identifiers.
        """
        return [
            dep for dep in metadata.dependencies
            if dep not in loaded_plugins
        ]

    def check_version_compatibility(
        self, metadata: PluginMetadata, app_version: str
    ) -> bool:
        """Check whether the plugin supports the running application version.

        Parameters
        ----------
        metadata:
            Plugin metadata containing version constraints.
        app_version:
            The current application version string.

        Returns
        -------
        bool
            *True* when *app_version* is within the plugin's supported range.
        """
        if not self._version_gte(app_version, metadata.min_app_version):
            return False
        if metadata.max_app_version:
            if not self._version_lte(app_version, metadata.max_app_version):
                return False
        return True

    # ------------------------------------------------------------------
    # Installation / uninstallation
    # ------------------------------------------------------------------

    def install_plugin(
        self, source_path: Path, plugin_dir: Path | None = None
    ) -> PluginMetadata | None:
        """Copy a plugin directory into the plugins folder and validate it.

        Parameters
        ----------
        source_path:
            Directory containing the plugin to install.
        plugin_dir:
            Destination root.  Defaults to :meth:`get_plugin_directory`.

        Returns
        -------
        PluginMetadata | None
            The installed plugin's metadata, or *None* on failure.
        """
        dest_root = plugin_dir or self.get_plugin_directory()
        dest_root.mkdir(parents=True, exist_ok=True)

        manifest_source = source_path / "plugin.json"
        if not manifest_source.is_file():
            logger.error("No plugin.json in source: %s", source_path)
            return None

        metadata = self.load_metadata(source_path)
        if metadata is None:
            logger.error("Could not parse metadata from: %s", source_path)
            return None

        validation_errors = self.validate_plugin(metadata)
        if validation_errors:
            logger.error(
                "Plugin validation failed for %s: %s",
                metadata.name,
                "; ".join(validation_errors),
            )
            return None

        dest_path = dest_root / metadata.id
        if dest_path.exists():
            logger.warning("Plugin directory already exists: %s", dest_path)
            try:
                shutil.rmtree(dest_path)
            except OSError as exc:
                logger.error("Failed to remove existing plugin: %s", exc)
                return None

        try:
            shutil.copytree(source_path, dest_path, dirs_exist_ok=False)
        except OSError as exc:
            logger.error("Failed to copy plugin: %s", exc)
            return None

        if not self._security.verify_plugin_signature(dest_path):
            logger.warning(
                "Signature verification failed for %s — removing", metadata.name
            )
            try:
                shutil.rmtree(dest_path)
            except OSError:
                pass
            return None

        metadata.checksum = self._compute_directory_checksum(dest_path)
        logger.info(
            "Installed plugin: %s (%s) to %s",
            metadata.name,
            metadata.id,
            dest_path,
        )
        return metadata

    def uninstall_plugin(
        self, plugin_id: str, plugin_dir: Path | None = None
    ) -> bool:
        """Remove a plugin's directory from disk.

        Parameters
        ----------
        plugin_id:
            Identifier of the plugin to uninstall.
        plugin_dir:
            Plugins root directory.  Defaults to :meth:`get_plugin_directory`.

        Returns
        -------
        bool
            *True* when the directory was successfully removed.
        """
        root = plugin_dir or self.get_plugin_directory()
        target = root / plugin_id
        if not target.exists():
            logger.warning("Plugin directory not found: %s", target)
            return False

        try:
            shutil.rmtree(target)
        except OSError as exc:
            logger.error("Failed to remove plugin %s: %s", plugin_id, exc)
            return False

        logger.info("Uninstalled plugin: %s", plugin_id)
        return True

    # ------------------------------------------------------------------
    # Plugin directory
    # ------------------------------------------------------------------

    def get_plugin_directory(self) -> Path:
        """Return the default plugin installation directory."""
        return AppPaths.plugins_dir()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_import(self, module_name: str, file_path: Path) -> Any | None:
        """Safely import a single module from a file path.

        Parameters
        ----------
        module_name:
            Dotted module name to register in ``sys.modules``.
        file_path:
            Absolute path to the ``.py`` file.

        Returns
        -------
        Any | None
            The imported module, or *None* on error.
        """
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                logger.error("Cannot create module spec for %s", file_path)
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module
        except Exception:
            logger.exception("Failed to import %s from %s", module_name, file_path)
            sys.modules.pop(module_name, None)
            return None

    def _instantiate_plugin(
        self, module: Any, metadata: PluginMetadata
    ) -> PluginBase | None:
        """Create a :class:`PluginBase` instance from a loaded module.

        Looks for a module-level ``create_plugin`` callable first, then
        falls back to finding the first :class:`PluginBase` subclass.
        """
        factory = getattr(module, "create_plugin", None)
        if callable(factory):
            try:
                instance = factory(metadata)
                if isinstance(instance, PluginBase):
                    return instance
                logger.error(
                    "create_plugin() did not return a PluginBase instance"
                )
                return None
            except Exception:
                logger.exception("create_plugin() raised")
                return None

        for attr_name in dir(module):
            attr = getattr(module, attr_name, None)
            if (
                attr is not None
                and isinstance(attr, type)
                and issubclass(attr, PluginBase)
                and attr is not PluginBase
            ):
                try:
                    return attr(metadata)
                except Exception:
                    logger.exception(
                        "Failed to instantiate %s from %s",
                        attr_name,
                        module.__name__,
                    )
                    return None

        logger.warning(
            "No PluginBase subclass found in module %s", module.__name__
        )
        return None

    def _build_context(self) -> dict[str, Any]:
        """Construct the context dictionary passed to ``initialize()``."""
        from src.config.settings import SettingsManager
        from src.services.event_bus import EventBus
        from src.services.registry import get_registry

        settings = SettingsManager()
        event_bus = EventBus.instance()
        service_registry = get_registry()

        version = settings.get("general.version", "1.0.0")

        notification_manager = service_registry.get_optional("notification_manager")

        return {
            "settings": settings,
            "event_bus": event_bus,
            "service_registry": service_registry,
            "notification_manager": notification_manager,
            "app_version": version,
        }

    def _compute_directory_checksum(self, directory: Path) -> str:
        """Compute a SHA-256 checksum of all Python files in *directory*."""
        import hashlib

        combined = b""
        for py_file in sorted(directory.rglob("*.py")):
            try:
                combined += py_file.read_bytes()
            except OSError:
                continue
        if not combined:
            return ""
        return self._security.compute_hash(combined, algorithm="sha256")

    @staticmethod
    def _version_gte(version: str, minimum: str) -> bool:
        """Return *True* when *version* >= *minimum* (semver tuples)."""
        return _parse_version(version) >= _parse_version(minimum)

    @staticmethod
    def _version_lte(version: str, maximum: str) -> bool:
        """Return *True* when *version* <= *maximum* (semver tuples)."""
        return _parse_version(version) <= _parse_version(maximum)


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Convert a dot-separated version string to a comparable tuple.

    Non-numeric segments are silently treated as ``0``.
    """
    parts: list[int] = []
    for segment in version_str.split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            parts.append(0)
    return tuple(parts)
