"""Plugin lifecycle management, configuration, and health monitoring."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from src.analysis.models import _now_iso
from src.plugins.base import (
    PluginBase,
    PluginMetadata,
    PluginState,
)
from src.plugins.loader import PluginLoader
from src.security.manager import SecurityManager
from src.services.event_bus import EventBus, Events
from src.utils.paths import AppPaths

logger = logging.getLogger(__name__)


class PluginManager:
    """High-level orchestrator for the complete plugin lifecycle.

    Manages discovery, installation, enabling, disabling, configuration,
    and health monitoring of plugins.  All public methods are thread-safe.

    Parameters
    ----------
    security_manager:
        Optional :class:`SecurityManager` for safe I/O.  A new instance
        is created when *None* is supplied.
    """

    def __init__(self, security_manager: SecurityManager | None = None) -> None:
        self._loader: PluginLoader = PluginLoader(security_manager)
        self._security: SecurityManager = security_manager or SecurityManager()
        self._plugins: dict[str, PluginBase] = {}
        self._metadata: dict[str, PluginMetadata] = {}
        self._plugin_configs: dict[str, dict[str, Any]] = {}
        self._lock: threading.Lock = threading.Lock()
        self._event_bus: EventBus = EventBus.instance()
        self._config_path: Path = AppPaths.data_dir() / "plugin_configs.json"
        self._load_configs()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_configs(self) -> None:
        """Load plugin configurations from disk."""
        if not self._config_path.is_file():
            return
        try:
            raw = self._security.safe_file_read(self._config_path)
        except Exception:
            logger.exception("Failed to read plugin configs: %s", self._config_path)
            return

        if raw is None:
            logger.error("Security manager rejected config read: %s", self._config_path)
            return

        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Corrupt plugin_configs.json: %s", exc)
            return

        with self._lock:
            self._plugin_configs = data
        logger.debug("Loaded plugin configs for %d plugins", len(data))

    def _save_configs(self) -> None:
        """Persist plugin configurations to disk."""
        with self._lock:
            data = dict(self._plugin_configs)

        content = json.dumps(data, indent=2, ensure_ascii=False)
        try:
            self._security.safe_file_write(self._config_path, content)
        except Exception:
            logger.exception("Failed to save plugin configs")

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> int:
        """Discover all available plugins and register their metadata.

        Returns the number of *newly* found plugins that were not already
        known to this manager.
        """
        plugin_paths = self._loader.discover_plugins()
        new_count = 0

        for path in plugin_paths:
            metadata = self._loader.load_metadata(path)
            if metadata is None:
                continue

            with self._lock:
                if metadata.id in self._metadata:
                    continue
                self._metadata[metadata.id] = metadata
                new_count += 1

            logger.debug(
                "Discovered plugin: %s (%s)", metadata.name, metadata.id
            )

        return new_count

    # ------------------------------------------------------------------
    # Installation / uninstallation
    # ------------------------------------------------------------------

    def install(self, source_path: Path) -> PluginMetadata | None:
        """Install a plugin from *source_path*.

        Emits :attr:`Events.PLUGIN_INSTALLED` on success.

        Parameters
        ----------
        source_path:
            Directory containing the plugin to install.

        Returns
        -------
        PluginMetadata | None
            The installed plugin's metadata, or *None* on failure.
        """
        metadata = self._loader.install_plugin(source_path)
        if metadata is None:
            return None

        with self._lock:
            self._metadata[metadata.id] = metadata
            self._plugin_configs[metadata.id] = metadata.config

        self._save_configs()
        self._event_bus.emit(Events.PLUGIN_INSTALLED, metadata.to_dict())
        logger.info("Installed plugin: %s", metadata.name)
        return metadata

    def uninstall(self, plugin_id: str) -> bool:
        """Uninstall a plugin by identifier.

        If the plugin is currently loaded it is disabled first.  Emits
        :attr:`Events.PLUGIN_UNINSTALLED` on success.

        Parameters
        ----------
        plugin_id:
            Identifier of the plugin to remove.

        Returns
        -------
        bool
            *True* on success.
        """
        with self._lock:
            if plugin_id not in self._metadata:
                logger.warning("Unknown plugin: %s", plugin_id)
                return False

        if plugin_id in self._plugins:
            self.disable(plugin_id)

        success = self._loader.uninstall_plugin(plugin_id)
        if not success:
            return False

        with self._lock:
            meta = self._metadata.pop(plugin_id, None)
            self._plugin_configs.pop(plugin_id, None)

        self._save_configs()
        self._event_bus.emit(
            Events.PLUGIN_UNINSTALLED,
            meta.to_dict() if meta is not None else {"id": plugin_id},
        )
        logger.info("Uninstalled plugin: %s", plugin_id)
        return True

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def enable(self, plugin_id: str) -> bool:
        """Enable, load, and initialise a plugin.

        Checks that all declared dependencies are already loaded before
        proceeding.  Emits :attr:`Events.PLUGIN_ENABLED` on success.

        Parameters
        ----------
        plugin_id:
            Identifier of the plugin to enable.

        Returns
        -------
        bool
            *True* on success.
        """
        with self._lock:
            metadata = self._metadata.get(plugin_id)
            if metadata is None:
                logger.warning("Cannot enable unknown plugin: %s", plugin_id)
                return False

            if plugin_id in self._plugins:
                logger.debug("Plugin already loaded: %s", plugin_id)
                return True

        missing = self._loader.check_dependencies(metadata, self._plugins)
        if missing:
            logger.warning(
                "Cannot enable %s — missing dependencies: %s",
                metadata.name,
                ", ".join(missing),
            )
            metadata.state = PluginState.ERROR
            metadata.load_error = f"Missing dependencies: {', '.join(missing)}"
            return False

        plugin_dir = self._loader.get_plugin_directory()
        plugin_path = plugin_dir / plugin_id
        if not plugin_path.is_dir():
            logger.error("Plugin directory missing: %s", plugin_path)
            metadata.state = PluginState.ERROR
            metadata.load_error = "Plugin directory not found"
            return False

        plugin = self._loader.load_plugin(plugin_path, metadata)
        if plugin is None:
            self._event_bus.emit(
                Events.PLUGIN_ERROR,
                {
                    "plugin_id": plugin_id,
                    "error": metadata.load_error,
                },
            )
            return False

        with self._lock:
            self._plugins[plugin_id] = plugin

        stored_config = self._plugin_configs.get(plugin_id, {})
        if stored_config:
            metadata.config = stored_config
            try:
                plugin.on_config_changed(stored_config)
            except Exception:
                logger.exception(
                    "Plugin %s raised during on_config_changed()", metadata.name
                )

        try:
            plugin.on_enable()
        except Exception:
            logger.exception("Plugin %s raised during on_enable()", metadata.name)

        metadata.enabled = True
        self._event_bus.emit(Events.PLUGIN_ENABLED, metadata.to_dict())
        logger.info("Enabled plugin: %s", metadata.name)
        return True

    def disable(self, plugin_id: str) -> bool:
        """Disable and unload a plugin.

        Calls :meth:`PluginBase.on_disable` and
        :meth:`PluginBase.shutdown`, then emits
        :attr:`Events.PLUGIN_DISABLED`.

        Parameters
        ----------
        plugin_id:
            Identifier of the plugin to disable.

        Returns
        -------
        bool
            *True* on success.
        """
        with self._lock:
            metadata = self._metadata.get(plugin_id)
            plugin = self._plugins.pop(plugin_id, None)

        if metadata is None:
            logger.warning("Cannot disable unknown plugin: %s", plugin_id)
            return False

        if plugin is None:
            metadata.enabled = False
            return True

        try:
            plugin.on_disable()
        except Exception:
            logger.exception(
                "Plugin %s raised during on_disable()", metadata.name
            )

        try:
            plugin.shutdown()
        except Exception:
            logger.exception(
                "Plugin %s raised during shutdown()", metadata.name
            )

        self._loader.unload_plugin(plugin_id)

        metadata.enabled = False
        metadata.state = PluginState.DISABLED
        self._event_bus.emit(Events.PLUGIN_DISABLED, metadata.to_dict())
        logger.info("Disabled plugin: %s", metadata.name)
        return True

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def load_all(self) -> int:
        """Enable every plugin that has ``metadata.enabled == True``.

        Returns the number of plugins successfully loaded.
        """
        count = 0
        with self._lock:
            targets = [
                pid
                for pid, meta in self._metadata.items()
                if meta.enabled and pid not in self._plugins
            ]

        for plugin_id in targets:
            if self.enable(plugin_id):
                count += 1

        return count

    def unload_all(self) -> None:
        """Disable every currently loaded plugin."""
        with self._lock:
            plugin_ids = list(self._plugins.keys())

        for plugin_id in plugin_ids:
            self.disable(plugin_id)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_plugin(self, plugin_id: str) -> PluginBase | None:
        """Return the loaded plugin instance, or *None*."""
        with self._lock:
            return self._plugins.get(plugin_id)

    def get_metadata(self, plugin_id: str) -> PluginMetadata | None:
        """Return metadata for a known plugin, or *None*."""
        with self._lock:
            return self._metadata.get(plugin_id)

    def list_plugins(self) -> list[PluginMetadata]:
        """Return metadata for all known plugins."""
        with self._lock:
            return list(self._metadata.values())

    def list_enabled(self) -> list[PluginMetadata]:
        """Return metadata for all enabled plugins."""
        with self._lock:
            return [
                meta
                for meta in self._metadata.values()
                if meta.enabled and meta.state == PluginState.ENABLED
            ]

    def list_disabled(self) -> list[PluginMetadata]:
        """Return metadata for all disabled plugins."""
        with self._lock:
            return [
                meta
                for meta in self._metadata.values()
                if not meta.enabled or meta.state != PluginState.ENABLED
            ]

    def list_by_category(self, category: Any) -> list[PluginMetadata]:
        """Return metadata for all plugins in *category*.

        Parameters
        ----------
        category:
            A :class:`PluginCategory` member value.
        """
        with self._lock:
            return [
                meta for meta in self._metadata.values()
                if meta.category == category
            ]

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_config(
        self, plugin_id: str, config: dict[str, Any]
    ) -> bool:
        """Update a plugin's configuration.

        Validates the new configuration against the plugin's schema and
        :meth:`PluginBase.validate_config` before applying.  Notifies a
        running plugin via :meth:`PluginBase.on_config_changed`.

        Parameters
        ----------
        plugin_id:
            Identifier of the plugin.
        config:
            New configuration dictionary.

        Returns
        -------
        bool
            *True* if the configuration was accepted and applied.
        """
        with self._lock:
            metadata = self._metadata.get(plugin_id)
            plugin = self._plugins.get(plugin_id)

        if metadata is None:
            logger.warning("Cannot set config for unknown plugin: %s", plugin_id)
            return False

        schema = plugin.get_config_schema() if plugin else metadata.config
        if schema and isinstance(schema, dict) and schema.get("properties"):
            errors = plugin.validate_config(config) if plugin else []
            if errors:
                logger.warning(
                    "Config validation failed for %s: %s",
                    metadata.name,
                    "; ".join(errors),
                )
                return False

        with self._lock:
            self._plugin_configs[plugin_id] = dict(config)
            metadata.config = dict(config)

        self._save_configs()

        if plugin is not None:
            try:
                plugin.on_config_changed(config)
            except Exception:
                logger.exception(
                    "Plugin %s raised during on_config_changed()",
                    metadata.name,
                )

        return True

    def get_config(self, plugin_id: str) -> dict[str, Any]:
        """Return the stored configuration for a plugin.

        Parameters
        ----------
        plugin_id:
            Identifier of the plugin.
        """
        with self._lock:
            return dict(self._plugin_configs.get(plugin_id, {}))

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    def get_health(self) -> dict[str, str]:
        """Return a per-plugin health status summary.

        Returns a mapping of ``plugin_id`` to a human-readable health
        string.  Possible values: ``"healthy"``, ``"error"``,
        ``"not_loaded"``, ``"unknown"``.
        """
        result: dict[str, str] = {}
        with self._lock:
            all_meta = dict(self._metadata)
            loaded = dict(self._plugins)

        for plugin_id, meta in all_meta.items():
            if meta.state == PluginState.ERROR:
                result[plugin_id] = f"error: {meta.load_error}"
            elif plugin_id in loaded:
                result[plugin_id] = "healthy"
            elif meta.enabled:
                result[plugin_id] = "not_loaded"
            else:
                result[plugin_id] = "disabled"
        return result

    def check_all_dependencies(self) -> dict[str, list[str]]:
        """Check dependency satisfaction for every known plugin.

        Returns a mapping of ``plugin_id`` to a list of missing dependency
        identifiers.  An empty list means all dependencies are satisfied.
        """
        result: dict[str, list[str]] = {}
        with self._lock:
            all_meta = dict(self._metadata)
            loaded = dict(self._plugins)

        for plugin_id, meta in all_meta.items():
            missing = self._loader.check_dependencies(meta, loaded)
            result[plugin_id] = missing
        return result

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_plugin(self, plugin_id: str, source_path: Path) -> bool:
        """Replace a plugin with a newer version from *source_path*.

        The existing plugin is disabled and uninstalled before the new
        version is installed.  Emits :attr:`Events.PLUGIN_UPDATED` on
        success.

        Parameters
        ----------
        plugin_id:
            Identifier of the plugin to update.
        source_path:
            Directory containing the updated plugin files.

        Returns
        -------
        bool
            *True* on success.
        """
        with self._lock:
            existing = self._metadata.get(plugin_id)
            if existing is None:
                logger.warning("Cannot update unknown plugin: %s", plugin_id)
                return False

        if plugin_id in self._plugins:
            self.disable(plugin_id)

        if not self._loader.uninstall_plugin(plugin_id):
            logger.error("Failed to remove old plugin version: %s", plugin_id)
            return False

        with self._lock:
            self._metadata.pop(plugin_id, None)
            self._plugin_configs.pop(plugin_id, None)

        new_metadata = self._loader.install_plugin(source_path)
        if new_metadata is None:
            logger.error("Failed to install updated plugin: %s", plugin_id)
            return False

        with self._lock:
            self._metadata[new_metadata.id] = new_metadata
            self._plugin_configs[new_metadata.id] = new_metadata.config

        self._save_configs()
        self._event_bus.emit(Events.PLUGIN_UPDATED, new_metadata.to_dict())
        logger.info(
            "Updated plugin: %s (%s)", new_metadata.name, new_metadata.id
        )
        return True

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_plugin_stats(self) -> dict[str, Any]:
        """Return aggregate plugin statistics.

        Returns a dictionary with keys ``enabled``, ``disabled``,
        ``errored``, and ``total``.
        """
        with self._lock:
            all_meta = list(self._metadata.values())

        enabled = sum(
            1 for m in all_meta
            if m.state == PluginState.ENABLED
        )
        errored = sum(
            1 for m in all_meta
            if m.state == PluginState.ERROR
        )
        total = len(all_meta)
        disabled = total - enabled - errored

        return {
            "enabled": enabled,
            "disabled": disabled,
            "errored": errored,
            "total": total,
        }

    def export_plugin_list(self) -> list[dict[str, Any]]:
        """Serialise metadata for every known plugin.

        Returns a list of dictionaries suitable for JSON serialisation.
        """
        with self._lock:
            return [meta.to_dict() for meta in self._metadata.values()]

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Disable all loaded plugins and persist configurations.

        Should be called during application shutdown to ensure orderly
        teardown of plugin resources.
        """
        self.unload_all()
        self._save_configs()
        logger.info("Plugin manager shut down")
