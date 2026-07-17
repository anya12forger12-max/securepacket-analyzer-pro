"""Plugin base class, metadata, and permission definitions for the plugin framework."""

from __future__ import annotations

import abc
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class PluginCategory(Enum):
    """Functional category for a plugin."""

    PROTOCOL_DECODER = auto()
    DASHBOARD_WIDGET = auto()
    ANALYTICS_EXTENSION = auto()
    EXPORT_FORMAT = auto()
    THEME = auto()
    TRANSLATION = auto()
    REPORT = auto()
    UTILITY = auto()
    ACCESSIBILITY = auto()
    SECURITY = auto()


class PluginPermission(Enum):
    """Capability that a plugin may request."""

    FILE_READ = auto()
    FILE_WRITE = auto()
    NETWORK_ACCESS = auto()
    DATABASE_ACCESS = auto()
    CAPTURE_ACCESS = auto()
    SETTINGS_ACCESS = auto()
    UI_MODIFY = auto()
    NOTIFICATION = auto()
    LOGGING = auto()


class PluginState(Enum):
    """Lifecycle state of an installed plugin."""

    INSTALLED = auto()
    ENABLED = auto()
    DISABLED = auto()
    ERROR = auto()
    UPDATING = auto()
    REMOVED = auto()


@dataclass
class PluginMetadata:
    """Declarative descriptor for a plugin, serialisable to JSON.

    All fields are plain values that can be read from a ``plugin.json``
    manifest file.  The :meth:`to_dict` / :meth:`from_dict` pair provide
    round-trip serialisation.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    version: str = ""
    author: str = ""
    description: str = ""
    long_description: str = ""
    category: PluginCategory = PluginCategory.UTILITY
    permissions: list[PluginPermission] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    min_app_version: str = "1.0.0"
    max_app_version: str = ""
    api_version: str = "1.0.0"
    homepage: str = ""
    license_name: str = "MIT"
    icon_path: str = ""
    enabled: bool = True
    state: PluginState = PluginState.INSTALLED
    load_error: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise metadata to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "long_description": self.long_description,
            "category": self.category.name,
            "permissions": [p.name for p in self.permissions],
            "dependencies": self.dependencies,
            "min_app_version": self.min_app_version,
            "max_app_version": self.max_app_version,
            "api_version": self.api_version,
            "homepage": self.homepage,
            "license_name": self.license_name,
            "icon_path": self.icon_path,
            "enabled": self.enabled,
            "state": self.state.name,
            "load_error": self.load_error,
            "config": self.config,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginMetadata:
        """Reconstruct a :class:`PluginMetadata` from a serialised dict."""
        permissions_raw: list[str] = data.get("permissions", [])
        permissions: list[PluginPermission] = []
        for p in permissions_raw:
            try:
                permissions.append(PluginPermission[p])
            except KeyError:
                logger.warning("Unknown plugin permission: %s", p)

        category: PluginCategory = PluginCategory.UTILITY
        category_name: str = data.get("category", "UTILITY")
        try:
            category = PluginCategory[category_name]
        except KeyError:
            logger.warning("Unknown plugin category: %s", category_name)

        state: PluginState = PluginState.INSTALLED
        state_name: str = data.get("state", "INSTALLED")
        try:
            state = PluginState[state_name]
        except KeyError:
            logger.warning("Unknown plugin state: %s", state_name)

        return cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            name=data.get("name", ""),
            version=data.get("version", ""),
            author=data.get("author", ""),
            description=data.get("description", ""),
            long_description=data.get("long_description", ""),
            category=category,
            permissions=permissions,
            dependencies=data.get("dependencies", []),
            min_app_version=data.get("min_app_version", "1.0.0"),
            max_app_version=data.get("max_app_version", ""),
            api_version=data.get("api_version", "1.0.0"),
            homepage=data.get("homepage", ""),
            license_name=data.get("license_name", "MIT"),
            icon_path=data.get("icon_path", ""),
            enabled=data.get("enabled", True),
            state=state,
            load_error=data.get("load_error", ""),
            config=data.get("config", {}),
            checksum=data.get("checksum", ""),
        )


class PluginBase(abc.ABC):
    """Abstract base class that all plugins must subclass.

    A plugin receives its :class:`PluginMetadata` at construction time
    and is later wired into the application through :meth:`initialize`.
    The initialise context supplies shared services such as the settings
    manager, event bus, and service registry.

    Parameters
    ----------
    metadata:
        Declarative descriptor for this plugin instance.
    """

    def __init__(self, metadata: PluginMetadata) -> None:
        self._metadata: PluginMetadata = metadata
        self._initialized: bool = False
        self._context: dict[str, Any] | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Return the plugin's metadata descriptor."""
        return self._metadata

    @property
    def is_initialized(self) -> bool:
        """Return *True* after :meth:`initialize` has completed."""
        return self._initialized

    # ------------------------------------------------------------------
    # Lifecycle hooks (required)
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def initialize(self, context: dict[str, Any]) -> None:
        """Called once when the plugin is loaded.

        The *context* dictionary contains the following keys:

        * ``settings`` – the application :class:`SettingsManager`.
        * ``event_bus`` – the application :class:`EventBus`.
        * ``service_registry`` – the application :class:`ServiceRegistry`.
        * ``notification_manager`` – the application notification manager.
        * ``app_version`` – current application version string.

        Subclasses **must** call ``super().initialize(context)`` if they
        override this method **and** need ``_context`` / ``_initialized``
        to be updated.  The recommended pattern is to call the parent
        first, then perform plugin-specific setup.
        """
        self._context = context
        self._initialized = True

    @abc.abstractmethod
    def shutdown(self) -> None:
        """Called once when the plugin is being unloaded.

        Release resources, unsubscribe from events, and perform any
        required cleanup.  After this call the plugin instance will be
        discarded.
        """

    # ------------------------------------------------------------------
    # Lifecycle hooks (optional)
    # ------------------------------------------------------------------

    def on_enable(self) -> None:
        """Called when the plugin transitions to the *enabled* state.

        Override to perform additional setup that is only needed while
        the plugin is actively enabled (e.g. subscribing to events).
        """

    def on_disable(self) -> None:
        """Called when the plugin transitions to the *disabled* state.

        Override to tear down resources that are only relevant while the
        plugin is enabled (e.g. unsubscribing from events).
        """

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Called when the plugin's configuration is updated at runtime.

        Parameters
        ----------
        config:
            The new configuration dictionary.
        """

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        """Return a JSON-Schema dict describing the plugin's configuration.

        The default implementation returns an empty schema (no config
        keys).  Override to declare configurable options.
        """
        return {}

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """Validate a candidate configuration dictionary.

        Parameters
        ----------
        config:
            Configuration values to validate.

        Returns
        -------
        list[str]
            A list of human-readable error descriptions.  An empty list
            means the configuration is valid.
        """
        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, level: str, msg: str, *args: Any) -> None:
        """Log a message prefixed with the plugin's name.

        Parameters
        ----------
        level:
            Python log-level name (``"debug"``, ``"info"``, ``"warning"``,
            ``"error"``, ``"critical"``).
        msg:
            Format string.
        *args:
            Interpolation arguments for *msg*.
        """
        prefixed = f"[{self._metadata.name}] {msg}"
        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn(prefixed, *args)
