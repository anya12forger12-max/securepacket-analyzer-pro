"""Platform-agnostic path utilities for SecurePacketAnalyzerPro.

Provides a centralized, cross-platform approach to application
directory and file path resolution using pathlib.Path.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


def _home_dir() -> Path:
    """Return the user's home directory in a platform-agnostic way."""
    return Path.home()


@dataclass(frozen=True)
class AppPaths:
    """Immutable dataclass exposing every well-known application path.

    All classmethods return ``pathlib.Path`` instances. Directories are
    *not* created automatically unless ``ensure_directories()`` is called.
    """

    app_name: str = "SecurePacketAnalyzerPro"

    # ------------------------------------------------------------------
    # Directory helpers
    # ------------------------------------------------------------------

    @classmethod
    def base_dir(cls) -> Path:
        """Return the root application directory under the user's home."""
        return _home_dir() / cls.app_name

    @classmethod
    def config_dir(cls) -> Path:
        """Return the configuration directory."""
        return cls.base_dir() / "config"

    @classmethod
    def data_dir(cls) -> Path:
        """Return the persistent data directory."""
        return cls.base_dir() / "data"

    @classmethod
    def logs_dir(cls) -> Path:
        """Return the log files directory."""
        return cls.base_dir() / "logs"

    @classmethod
    def workspaces_dir(cls) -> Path:
        """Return the workspaces directory."""
        return cls.base_dir() / "workspaces"

    @classmethod
    def plugins_dir(cls) -> Path:
        """Return the plugins directory."""
        return cls.base_dir() / "plugins"

    @classmethod
    def exports_dir(cls) -> Path:
        """Return the exports directory."""
        return cls.base_dir() / "exports"

    @classmethod
    def cache_dir(cls) -> Path:
        """Return the cache directory."""
        return cls.base_dir() / "cache"

    @classmethod
    def themes_dir(cls) -> Path:
        """Return the themes directory."""
        return cls.base_dir() / "themes"

    @classmethod
    def fonts_dir(cls) -> Path:
        """Return the fonts directory."""
        return cls.base_dir() / "fonts"

    @classmethod
    def translations_dir(cls) -> Path:
        """Return the translations directory."""
        return cls.base_dir() / "translations"

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    @classmethod
    def user_settings_file(cls) -> Path:
        """Return the path to the user-editable settings JSON file."""
        return cls.config_dir() / "user_settings.json"

    @classmethod
    def default_config_file(cls) -> Path:
        """Return the path to the default TOML configuration file."""
        return cls.config_dir() / "defaults.toml"

    # ------------------------------------------------------------------
    # Directory management
    # ------------------------------------------------------------------

    @classmethod
    def all_dirs(cls) -> list[Path]:
        """Return every known directory as a list of ``Path`` objects."""
        return [
            cls.base_dir(),
            cls.config_dir(),
            cls.data_dir(),
            cls.logs_dir(),
            cls.workspaces_dir(),
            cls.plugins_dir(),
            cls.exports_dir(),
            cls.cache_dir(),
            cls.themes_dir(),
            cls.fonts_dir(),
            cls.translations_dir(),
        ]

    @classmethod
    def ensure_directories(cls) -> None:
        """Create all application directories if they do not already exist.

        Uses ``Path.mkdir(parents=True, exist_ok=True)`` so that the call
        is safe to invoke repeatedly without raising errors.
        """
        for directory in cls.all_dirs():
            directory.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Diagnostics / string representation
    # ------------------------------------------------------------------

    @classmethod
    def describe(cls) -> dict[str, str]:
        """Return a human-readable mapping of logical names to path strings."""
        return {
            "base": str(cls.base_dir()),
            "config": str(cls.config_dir()),
            "data": str(cls.data_dir()),
            "logs": str(cls.logs_dir()),
            "workspaces": str(cls.workspaces_dir()),
            "plugins": str(cls.plugins_dir()),
            "exports": str(cls.exports_dir()),
            "cache": str(cls.cache_dir()),
            "themes": str(cls.themes_dir()),
            "fonts": str(cls.fonts_dir()),
            "translations": str(cls.translations_dir()),
            "user_settings": str(cls.user_settings_file()),
            "default_config": str(cls.default_config_file()),
        }

    @classmethod
    def platform_info(cls) -> dict[str, str]:
        """Return basic platform identifiers useful for diagnostics."""
        return {
            "system": sys.platform,
            "python_version": sys.version,
            "home": str(_home_dir()),
            "base_dir": str(cls.base_dir()),
        }
