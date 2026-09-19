"""Centralized configuration manager for SecurePacketAnalyzerPro.

Manages a layered configuration system: built-in defaults are defined in
``DEFAULT_CONFIG`` and persisted as ``defaults.toml``; user overrides are
stored in ``user_settings.json``.  All access is thread-safe.
"""

from __future__ import annotations

import copy
import json
import logging
import threading
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.utils.paths import AppPaths

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Canonical defaults
# ------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "app_name": "SecurePacketAnalyzerPro",
        "version": "1.0.0",
        "language": "en",
        "first_run": True,
    },
    "appearance": {
        "theme": "dark",
        "font_family": "Segoe UI",
        "font_size": 12,
        "icon_size": 24,
        "scaling": 1.0,
        "accent_color": "#0078D4",
        "show_toolbar": True,
        "show_sidebar": True,
        "sidebar_collapsed": False,
        "animate_transitions": True,
    },
    "accessibility": {
        "screen_reader": False,
        "keyboard_navigation": True,
        "high_contrast": False,
        "reduced_motion": False,
        "large_ui": False,
        "large_cursor": False,
        "color_blind_mode": "none",
        "text_scale": 1.0,
        "icon_scale": 1.0,
        "focus_indicators": True,
        "accessible_tooltips": True,
        "wcag_level": "AA",
    },
    "capture": {
        "interface": "",
        "promiscuous": True,
        "filter": "",
        "max_packets": 0,
        "timeout": 0,
        "buffer_size": 65536,
        "auto_scroll": True,
    },
    "workspace": {
        "active_workspace": "default",
        "auto_save": True,
        "save_interval": 300,
    },
    "logging": {
        "level": "INFO",
        "max_size_mb": 50,
        "backup_count": 5,
        "log_to_file": True,
        "log_to_console": True,
        "performance_logging": False,
        "security_logging": True,
    },
    "notifications": {
        "enabled": True,
        "show_info": True,
        "show_warnings": True,
        "show_errors": True,
        "show_security": True,
        "sound_enabled": False,
        "timeout_seconds": 5,
    },
    "plugins": {
        "enabled": True,
        "auto_load": True,
        "sandbox_mode": True,
        "api_version": "1.0.0",
    },
    "performance": {
        "max_memory_mb": 2048,
        "worker_threads": 4,
        "cache_size_mb": 256,
        "lazy_loading": True,
        "background_init": True,
    },
    "privacy": {
        "telemetry_enabled": False,
        "analytics_enabled": False,
        "external_connections": False,
        "crash_reports": False,
    },
    "updates": {
        "auto_check": True,
        "channel": "stable",
        "server_url": "",
        "download_dir": "",
    },
    "backup": {
        "auto_backup": False,
        "backup_interval_hours": 24,
        "max_backups": 10,
        "include_settings": True,
        "include_workspaces": True,
        "include_cases": True,
        "include_reports": True,
        "include_plugins": True,
        "include_notes": True,
        "include_bookmarks": True,
        "compression_level": 6,
    },
    "diagnostics": {
        "auto_run_on_startup": False,
        "log_level": "INFO",
        "performance_monitoring": True,
        "performance_interval_seconds": 1,
        "performance_history_size": 600,
    },
}

# ------------------------------------------------------------------
# Validation rules: key_path -> (expected_type, extra_check_or_None)
# ------------------------------------------------------------------

_VALIDATION_RULES: dict[str, tuple[type | tuple[type, ...], Callable[[Any], bool] | None]] = {
    "general.app_name": (str, None),
    "general.version": (str, None),
    "general.language": (str, None),
    "general.first_run": (bool, None),
    "appearance.theme": (str, lambda v: v in ("dark", "light", "system")),
    "appearance.font_family": (str, None),
    "appearance.font_size": ((int, float), lambda v: 6 <= v <= 72),
    "appearance.icon_size": ((int, float), lambda v: 8 <= v <= 128),
    "appearance.scaling": ((int, float), lambda v: 0.25 <= v <= 4.0),
    "appearance.accent_color": (str, lambda v: len(v) == 7 and v.startswith("#")),
    "appearance.show_toolbar": (bool, None),
    "appearance.show_sidebar": (bool, None),
    "appearance.sidebar_collapsed": (bool, None),
    "appearance.animate_transitions": (bool, None),
    "accessibility.screen_reader": (bool, None),
    "accessibility.keyboard_navigation": (bool, None),
    "accessibility.high_contrast": (bool, None),
    "accessibility.reduced_motion": (bool, None),
    "accessibility.large_ui": (bool, None),
    "accessibility.large_cursor": (bool, None),
    "accessibility.color_blind_mode": (
        str,
        lambda v: v in ("none", "protanopia", "deuteranopia", "tritanopia"),
    ),
    "accessibility.text_scale": ((int, float), lambda v: 0.5 <= v <= 3.0),
    "accessibility.icon_scale": ((int, float), lambda v: 0.5 <= v <= 3.0),
    "accessibility.focus_indicators": (bool, None),
    "accessibility.accessible_tooltips": (bool, None),
    "accessibility.wcag_level": (str, lambda v: v in ("A", "AA", "AAA")),
    "capture.interface": (str, None),
    "capture.promiscuous": (bool, None),
    "capture.filter": (str, None),
    "capture.max_packets": ((int, float), lambda v: v >= 0),
    "capture.timeout": ((int, float), lambda v: v >= 0),
    "capture.buffer_size": ((int, float), lambda v: v > 0),
    "capture.auto_scroll": (bool, None),
    "workspace.active_workspace": (str, None),
    "workspace.auto_save": (bool, None),
    "workspace.save_interval": ((int, float), lambda v: v >= 30),
    "logging.level": (str, lambda v: v in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")),
    "logging.max_size_mb": ((int, float), lambda v: 1 <= v <= 10240),
    "logging.backup_count": ((int, float), lambda v: v >= 0),
    "logging.log_to_file": (bool, None),
    "logging.log_to_console": (bool, None),
    "logging.performance_logging": (bool, None),
    "logging.security_logging": (bool, None),
    "notifications.enabled": (bool, None),
    "notifications.show_info": (bool, None),
    "notifications.show_warnings": (bool, None),
    "notifications.show_errors": (bool, None),
    "notifications.show_security": (bool, None),
    "notifications.sound_enabled": (bool, None),
    "notifications.timeout_seconds": ((int, float), lambda v: v >= 0),
    "plugins.enabled": (bool, None),
    "plugins.auto_load": (bool, None),
    "plugins.sandbox_mode": (bool, None),
    "plugins.api_version": (str, None),
    "performance.max_memory_mb": ((int, float), lambda v: v >= 256),
    "performance.worker_threads": ((int, float), lambda v: 1 <= v <= 128),
    "performance.cache_size_mb": ((int, float), lambda v: v >= 64),
    "performance.lazy_loading": (bool, None),
    "performance.background_init": (bool, None),
    "privacy.telemetry_enabled": (bool, None),
    "privacy.analytics_enabled": (bool, None),
    "privacy.external_connections": (bool, None),
    "privacy.crash_reports": (bool, None),
    "updates.auto_check": (bool, None),
    "updates.channel": (str, lambda v: v in ("stable", "beta", "dev")),
    "updates.server_url": (str, None),
    "updates.download_dir": (str, None),
    "backup.auto_backup": (bool, None),
    "backup.backup_interval_hours": ((int, float), lambda v: 1 <= v <= 168),
    "backup.max_backups": ((int, float), lambda v: 1 <= v <= 100),
    "backup.include_settings": (bool, None),
    "backup.include_workspaces": (bool, None),
    "backup.include_cases": (bool, None),
    "backup.include_reports": (bool, None),
    "backup.include_plugins": (bool, None),
    "backup.include_notes": (bool, None),
    "backup.include_bookmarks": (bool, None),
    "backup.compression_level": ((int, float), lambda v: 0 <= v <= 9),
    "diagnostics.auto_run_on_startup": (bool, None),
    "diagnostics.log_level": (
        str,
        lambda v: v in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
    ),
    "diagnostics.performance_monitoring": (bool, None),
    "diagnostics.performance_interval_seconds": ((int, float), lambda v: 0.1 <= v <= 60),
    "diagnostics.performance_history_size": ((int, float), lambda v: 60 <= v <= 3600),
}


class SettingsManager:
    """Thread-safe hierarchical configuration manager.

    Configuration is resolved in the following priority order (highest first):

    1. Values set at runtime via :meth:`set`
    2. User overrides stored in ``user_settings.json``
    3. Built-in defaults from :data:`DEFAULT_CONFIG` / ``defaults.toml``

    Parameters
    ----------
    config_dir:
        Directory for configuration files.  When *None* the default
        application config directory is used.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir: Path = config_dir or AppPaths.config_dir()
        self._lock: threading.Lock = threading.Lock()
        self._defaults: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self._user_overrides: dict[str, Any] = {}
        self._runtime_overrides: dict[str, Any] = {}
        self._callbacks: dict[str, list[Callable[[str, Any, Any], None]]] = {}

        self._load_defaults()
        self._load_user_settings()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_defaults(self) -> None:
        """Load defaults from the TOML file, falling back to ``DEFAULT_CONFIG``."""
        toml_path = AppPaths.default_config_file()
        if not toml_path.is_file():
            self._write_defaults_toml(toml_path)
            return

        try:
            with open(toml_path, "rb") as fh:
                loaded = tomllib.load(fh)
            self._defaults = self._deep_merge(copy.deepcopy(DEFAULT_CONFIG), loaded)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            logger.warning("Failed to load defaults.toml – using built-in defaults: %s", exc)
            self._defaults = copy.deepcopy(DEFAULT_CONFIG)

    def _write_defaults_toml(self, path: Path) -> None:
        """Serialise ``DEFAULT_CONFIG`` to a TOML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            lines: list[str] = []
            for section, values in DEFAULT_CONFIG.items():
                lines.append(f"[{section}]")
                for key, value in values.items():
                    lines.append(self._toml_line(key, value))
                lines.append("")
            path.write_text("\n".join(lines), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not write defaults.toml: %s", exc)

    @staticmethod
    def _toml_line(key: str, value: Any) -> str:
        """Format a single TOML key-value line."""
        if isinstance(value, bool):
            return f'{key} = {"true" if value else "false"}'
        if isinstance(value, str):
            return f'{key} = "{value}"'
        if isinstance(value, (int, float)):
            return f"{key} = {value}"
        return f"{key} = {json.dumps(value)}"

    def _load_user_settings(self) -> None:
        """Load user overrides from ``user_settings.json``."""
        user_path = AppPaths.user_settings_file()
        if not user_path.is_file():
            return
        try:
            raw = user_path.read_text(encoding="utf-8")
            self._user_overrides = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load user_settings.json: %s", exc)
            self._user_overrides = {}

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Recursively merge *override* into *base* (mutates *base*)."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                SettingsManager._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def _resolve(self, key_path: str) -> dict[str, Any]:
        """Build a merged config dict from defaults + user + runtime."""
        with self._lock:
            merged = copy.deepcopy(self._defaults)
            self._deep_merge(merged, self._user_overrides)
            self._deep_merge(merged, self._runtime_overrides)
        return merged

    @staticmethod
    def _traverse(config: dict, key_path: str) -> Any:
        """Walk *config* using a dot-separated *key_path*."""
        keys = key_path.split(".")
        current: Any = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                raise KeyError(key_path)
        return current

    @staticmethod
    def _set_in_dict(config: dict, key_path: str, value: Any) -> None:
        """Set a nested value in *config* using dot notation."""
        keys = key_path.split(".")
        target = config
        for key in keys[:-1]:
            target = target.setdefault(key, {})
        target[keys[-1]] = value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key_path: str, default: Any = None) -> Any:
        """Retrieve a configuration value using dot notation.

        Example::

            settings.get("appearance.theme")  # -> "dark"

        Parameters
        ----------
        key_path:
            Dot-separated path, e.g. ``"logging.level"``.
        default:
            Returned when the key does not exist.
        """
        merged = self._resolve(key_path)
        try:
            return self._traverse(merged, key_path)
        except (KeyError, TypeError):
            return default

    def set(self, key_path: str, value: Any) -> None:
        """Set a configuration value and persist the change.

        Registered callbacks are invoked **after** the value is stored.

        Parameters
        ----------
        key_path:
            Dot-separated path, e.g. ``"capture.promiscuous"``.
        value:
            New value for the key.
        """
        with self._lock:
            old_value = self.get(key_path)
            self._set_in_dict(self._runtime_overrides, key_path, value)
            self._set_in_dict(self._user_overrides, key_path, value)

        self.save()

        if old_value != value:
            self._fire_callbacks(key_path, old_value, value)

    def save(self) -> None:
        """Persist the current user overrides to ``user_settings.json``."""
        user_path = AppPaths.user_settings_file()
        user_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = copy.deepcopy(self._user_overrides)
        try:
            user_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Failed to save user_settings.json: %s", exc)

    def reset(self, section: str | None = None) -> None:
        """Reset one *section* (or everything) back to defaults.

        Parameters
        ----------
        section:
            Top-level configuration section name.  When *None* all
            user overrides and runtime overrides are cleared.
        """
        with self._lock:
            if section is None:
                self._user_overrides.clear()
                self._runtime_overrides.clear()
            else:
                self._user_overrides.pop(section, None)
                self._runtime_overrides.pop(section, None)
        self.save()

    def register_callback(self, key_path: str, callback: Callable[[str, Any, Any], None]) -> None:
        """Register a change notification callback.

        The callback is invoked as ``callback(key_path, old_value, new_value)``
        whenever the value at *key_path* changes via :meth:`set`.

        Parameters
        ----------
        key_path:
            Dot-separated path to watch.
        callback:
            Callable to invoke on changes.
        """
        with self._lock:
            self._callbacks.setdefault(key_path, []).append(callback)

    def _fire_callbacks(self, key_path: str, old_value: Any, new_value: Any) -> None:
        """Invoke all registered callbacks for *key_path*."""
        with self._lock:
            callbacks = list(self._callbacks.get(key_path, []))
        for cb in callbacks:
            try:
                cb(key_path, old_value, new_value)
            except Exception:
                logger.exception("Callback error for key_path=%s", key_path)

    def as_dict(self, section: str | None = None) -> dict[str, Any]:
        """Return the fully-resolved configuration as a plain dictionary.

        Parameters
        ----------
        section:
            When given, only that top-level section is returned.
        """
        merged = self._resolve("")
        if section is not None:
            return copy.deepcopy(merged.get(section, {}))
        return copy.deepcopy(merged)

    def validate(self) -> list[str]:
        """Validate the current configuration against known rules.

        Returns a list of human-readable error strings.  An empty list
        means the configuration is valid.
        """
        errors: list[str] = []
        merged = self._resolve("")
        for key_path, (expected, extra) in _VALIDATION_RULES.items():
            try:
                value = self._traverse(merged, key_path)
            except (KeyError, TypeError):
                continue

            if not isinstance(value, expected):
                errors.append(f"{key_path}: expected {expected}, got {type(value).__name__}")
                continue

            if extra is not None and not extra(value):
                errors.append(f"{key_path}: value {value!r} failed validation")
        return errors

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<SettingsManager config_dir={self._config_dir!s} "
            f"overrides={len(self._user_overrides)} sections>"
        )
