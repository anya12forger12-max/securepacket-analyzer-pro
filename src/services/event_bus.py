"""Centralized event bus for decoupled inter-component communication.

Provides both Qt Signal integration and pure-Python callback support,
enabling decoupled communication between analyzers, capture engines,
and UI components. Thread-safe for background thread emission.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class Events:
    """Pre-defined event name constants for the application."""

    # Application lifecycle
    APP_STARTED = "app.started"
    APP_SHUTTING_DOWN = "app.shutting_down"

    # Packet events
    PACKET_RECEIVED = "packet.received"
    PACKET_BATCH_RECEIVED = "packet.batch_received"
    PACKET_PROCESSED = "packet.processed"

    # Capture events
    CAPTURE_STARTED = "capture.started"
    CAPTURE_STOPPED = "capture.stopped"
    CAPTURE_PAUSED = "capture.paused"
    CAPTURE_RESUMED = "capture.resumed"
    CAPTURE_ERROR = "capture.error"
    CAPTURE_STATS_UPDATED = "capture.stats_updated"

    # Interface events
    INTERFACES_CHANGED = "interfaces.changed"
    INTERFACE_SELECTED = "interface.selected"

    # Analysis events
    HOST_DISCOVERED = "host.discovered"
    HOST_UPDATED = "host.updated"
    CONNECTION_DETECTED = "connection.detected"
    CONNECTION_UPDATED = "connection.updated"
    PROTOCOL_SEEN = "protocol.seen"
    STATISTICS_UPDATED = "statistics.updated"

    # Theme/Accessibility
    THEME_CHANGED = "theme.changed"
    ACCESSIBILITY_CHANGED = "accessibility.changed"

    # Workspace
    WORKSPACE_CHANGED = "workspace.changed"
    WORKSPACE_LOADED = "workspace.loaded"

    # Settings
    SETTINGS_CHANGED = "settings.changed"

    # Notifications
    NOTIFICATION_CREATED = "notification.created"

    # Reports
    REPORT_CREATED = "report.created"
    REPORT_GENERATED = "report.generated"
    REPORT_EXPORTED = "report.exported"
    REPORT_DELETED = "report.deleted"
    REPORT_TEMPLATE_ADDED = "report.template_added"

    # Cases
    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    CASE_STATUS_CHANGED = "case.status_changed"
    CASE_CLOSED = "case.closed"
    CASE_DELETED = "case.deleted"
    CASE_LINKED_EVIDENCE = "case.linked_evidence"

    # Evidence
    EVIDENCE_ADDED = "evidence.added"
    EVIDENCE_UPDATED = "evidence.updated"
    EVIDENCE_REMOVED = "evidence.removed"
    EVIDENCE_VERIFIED = "evidence.verified"

    # Bookmarks
    BOOKMARK_CREATED = "bookmark.created"
    BOOKMARK_UPDATED = "bookmark.updated"
    BOOKMARK_DELETED = "bookmark.deleted"
    BOOKMARK_FOLDER_CREATED = "bookmark.folder_created"

    # Notes
    NOTE_CREATED = "note.created"
    NOTE_UPDATED = "note.updated"
    NOTE_DELETED = "note.deleted"

    # Investigation timeline
    INVESTIGATION_TIMELINE_EVENT = "investigation.timeline_event"

    # Import/Export
    IMPORT_STARTED = "import.started"
    IMPORT_COMPLETED = "import.completed"
    IMPORT_FAILED = "import.failed"
    EXPORT_STARTED = "export.started"
    EXPORT_COMPLETED = "export.completed"
    EXPORT_FAILED = "export.failed"

    # Plugins
    PLUGIN_INSTALLED = "plugin.installed"
    PLUGIN_UNINSTALLED = "plugin.uninstalled"
    PLUGIN_ENABLED = "plugin.enabled"
    PLUGIN_DISABLED = "plugin.disabled"
    PLUGIN_UPDATED = "plugin.updated"
    PLUGIN_ERROR = "plugin.error"
    PLUGIN_LOADED = "plugin.loaded"
    PLUGIN_UNLOADED = "plugin.unloaded"
    PLUGIN_CRASH = "plugin.crash"

    # Updates
    UPDATE_CHECK_STARTED = "update.check_started"
    UPDATE_AVAILABLE = "update.available"
    UPDATE_NOT_AVAILABLE = "update.not_available"
    UPDATE_DOWNLOAD_STARTED = "update.download_started"
    UPDATE_DOWNLOAD_COMPLETED = "update.download_completed"
    UPDATE_DOWNLOAD_FAILED = "update.download_failed"
    UPDATE_INSTALL_STARTED = "update.install_started"
    UPDATE_INSTALL_COMPLETED = "update.install_completed"
    UPDATE_INSTALL_FAILED = "update.install_failed"
    UPDATE_ROLLBACK = "update.rollback"

    # Backup
    BACKUP_CREATED = "backup.created"
    BACKUP_RESTORED = "backup.restored"
    BACKUP_DELETED = "backup.deleted"
    BACKUP_FAILED = "backup.failed"

    # Diagnostics
    DIAGNOSTICS_COMPLETED = "diagnostics.completed"
    DIAGNOSTICS_EXPORTED = "diagnostics.exported"

    # Performance
    PERFORMANCE_WARNING = "performance.warning"
    PERFORMANCE_CRITICAL = "performance.critical"
    MEMORY_WARNING = "memory.warning"
    MEMORY_CRITICAL = "memory.critical"


class EventBus(QObject):
    """Centralized event bus for decoupled inter-component communication.

    Singleton instance providing both Qt Signal-based and pure-Python
    callback subscriptions. Thread-safe for emission from any thread.

    Usage::

        bus = EventBus.instance()
        bus.subscribe(Events.PACKET_RECEIVED, my_handler)
        bus.emit(Events.PACKET_RECEIVED, packet_data)
    """

    event_emitted = Signal(str, object)

    _instance: EventBus | None = None

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._handlers: dict[str, list[Callable[[Any], None]]] = {}
        self._qt_connections: list[tuple[int, int]] = []
        self._lock = threading.Lock()
        self._event_history: deque[tuple[str, str, str]] = deque(maxlen=1000)

    @classmethod
    def instance(cls) -> EventBus:
        """Return the singleton EventBus instance, creating if needed."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (useful for testing)."""
        if cls._instance is not None:
            cls._instance.disconnect_all()
            cls._instance.deleteLater()
            cls._instance = None

    def subscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Register a Python callback for the given event.

        Args:
            event_name: The event channel name.
            handler: Callable that will receive event data.
        """
        with self._lock:
            if event_name not in self._handlers:
                self._handlers[event_name] = []
            if handler not in self._handlers[event_name]:
                self._handlers[event_name].append(handler)
                logger.debug("Subscribed %s to %s", handler, event_name)

    def unsubscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Remove a previously registered callback.

        Args:
            event_name: The event channel name.
            handler: The handler to remove.
        """
        with self._lock:
            handlers = self._handlers.get(event_name, [])
            try:
                handlers.remove(handler)
                logger.debug("Unsubscribed %s from %s", handler, event_name)
            except ValueError:
                logger.debug(
                    "Handler %s not found for event %s", handler, event_name
                )

    def emit(self, event_name: str, data: Any = None) -> None:
        """Emit an event to all subscribers (both Python and Qt).

        Thread-safe. Handler exceptions are caught and logged without
        propagating to the caller.

        Args:
            event_name: The event channel name.
            data: Arbitrary event payload.
        """
        self._log_event(event_name)
        summary = self._get_data_summary(data)

        with self._lock:
            snapshot = list(self._handlers.get(event_name, []))

        for handler in snapshot:
            try:
                handler(data)
            except Exception:
                logger.exception(
                    "Handler %s raised for event '%s'", handler, event_name
                )

        self.event_emitted.emit(event_name, data)

        with self._lock:
            self._event_history.append((event_name, summary, time.strftime("%H:%M:%S")))

    def connect_signal(self, event_name: str, slot: Callable) -> None:
        """Connect a Qt slot via the event_emitted signal with filtering.

        The slot will only be invoked when the signal carries a matching
        event_name.

        Args:
            event_name: The event channel name to filter on.
            slot: Qt-compatible callable (slot) to invoke.
        """
        def _filtered_slot(name: str, data: object) -> None:
            if name == event_name:
                slot(data)

        sender_id = id(self)
        signal_conn = self.event_emitted.connect(_filtered_slot)
        self._qt_connections.append((sender_id, signal_conn))
        logger.debug(
            "Connected Qt slot %s to event '%s'", slot, event_name
        )

    def disconnect_all(self) -> None:
        """Clear all Python subscriptions and Qt signal connections."""
        with self._lock:
            self._handlers.clear()
            self._event_history.clear()

        for _, conn in self._qt_connections:
            try:
                self.event_emitted.disconnect(conn)
            except (RuntimeError, TypeError):
                pass
        self._qt_connections.clear()
        logger.debug("All event bus subscriptions cleared")

    def get_history(self, limit: int = 100) -> list[tuple[str, str, str]]:
        """Return recent event history for debugging.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of (event_name, data_summary, timestamp) tuples.
        """
        with self._lock:
            items = list(self._event_history)
        return items[-limit:]

    def subscriber_count(self, event_name: str) -> int:
        """Return the number of Python subscribers for an event.

        Args:
            event_name: The event channel name.
        """
        with self._lock:
            return len(self._handlers.get(event_name, []))

    def has_subscribers(self, event_name: str) -> bool:
        """Check whether any subscribers exist for an event.

        Args:
            event_name: The event channel name.
        """
        with self._lock:
            return bool(self._handlers.get(event_name))

    @staticmethod
    def _get_data_summary(data: Any) -> str:
        """Generate a safe, truncated string summary of event data.

        Args:
            data: Arbitrary payload.

        Returns:
            String representation, truncated to 200 characters.
        """
        try:
            summary = repr(data)
        except Exception:
            summary = "<unrepresentable>"
        if len(summary) > 200:
            summary = summary[:197] + "..."
        return summary

    @staticmethod
    def _log_event(event_name: str) -> None:
        """Log an event emission to the performance logger.

        Args:
            event_name: The event channel name.
        """
        logger.debug("Event emitted: %s", event_name)
