"""Notification system for SecurePacketAnalyzerPro.

Provides a thread-safe, observable notification store backed by Qt
signals.  Notifications are held in memory (capped at 1 000) and
filtered according to the user's notification preferences.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

try:
    from PySide6.QtCore import QObject, Signal
except ImportError:
    # Lightweight stub so the module can be imported without PySide6
    # (useful for headless tests / tooling).
    class _SignalDescriptor:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __set_name__(self, owner: type, name: str) -> None:
            self._name = name

        def __get__(self, instance: Any, owner: type | None = None) -> Any:
            if instance is None:
                return self
            return lambda *a, **kw: None

    class _QObjectStub:
        pass

    # Patch into a fake module so the class body can inherit from it.
    import types

    _fake_qtcore = types.ModuleType("PySide6.QtCore")
    _fake_qtcore.QObject = _QObjectStub  # type: ignore[attr-defined]
    _fake_qtcore.Signal = _SignalDescriptor  # type: ignore[attr-defined]

    import sys

    sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
    sys.modules["PySide6.QtCore"] = _fake_qtcore
    from PySide6.QtCore import QObject, Signal  # type: ignore[no-redef]

from src.config.settings import SettingsManager

logger = logging.getLogger(__name__)

# Hard cap for in-memory notifications
_MAX_NOTIFICATIONS: int = 1000


class NotificationType(Enum):
    """Semantic categories for notifications."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SECURITY = "security"


@dataclass
class Notification:
    """A single in-memory notification."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    message: str = ""
    notification_type: NotificationType = NotificationType.INFO
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    read: bool = False
    dismissed: bool = False
    actions: list[dict[str, str]] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Convert the notification to a plain dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "notification_type": self.notification_type.value,
            "timestamp": self.timestamp,
            "read": self.read,
            "dismissed": self.dismissed,
            "actions": list(self.actions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Notification:
        """Reconstruct a :class:`Notification` from a dictionary."""
        ntype_str = data.get("notification_type", "info")
        try:
            ntype = NotificationType(ntype_str)
        except ValueError:
            ntype = NotificationType.INFO
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            title=data.get("title", ""),
            message=data.get("message", ""),
            notification_type=ntype,
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            read=data.get("read", False),
            dismissed=data.get("dismissed", False),
            actions=data.get("actions", []),
        )


# ------------------------------------------------------------------
# Manager
# ------------------------------------------------------------------


class NotificationManager(QObject):
    """Manages application-wide notifications.

    Thread-safe: all mutations are protected by a :class:`threading.Lock`.
    When running inside a Qt event loop the ``notification_added`` and
    ``notification_removed`` signals are emitted so that UI components
    can react immediately.

    Parameters
    ----------
    settings:
        Optional application settings used to filter notifications
        by type.  When *None* a fresh default :class:`SettingsManager`
        is created.
    """

    notification_added = Signal(object)
    notification_removed = Signal(str)
    notifications_cleared = Signal()

    def __init__(self, settings: SettingsManager | None = None) -> None:
        super().__init__()
        self._settings = settings or SettingsManager()
        self._lock: threading.Lock = threading.Lock()
        self._notifications: list[Notification] = []

    # ------------------------------------------------------------------
    # Convenience creators
    # ------------------------------------------------------------------

    def notify(
        self,
        title: str,
        message: str,
        ntype: NotificationType = NotificationType.INFO,
        actions: list[dict[str, str]] | None = None,
    ) -> Notification:
        """Create and store a notification.

        Parameters
        ----------
        title:
            Short headline.
        message:
            Body text.
        ntype:
            Notification category.
        actions:
            Optional list of ``{"label": ..., "callback": ...}`` dicts.

        Returns
        -------
        Notification
            The newly created notification object.
        """
        ntype_key = f"show_{ntype.value}s" if ntype != NotificationType.SECURITY else "show_security"

        # Check if this notification type is enabled
        notifications_cfg = self._settings.as_dict("notifications")
        if not notifications_cfg.get("enabled", True):
            return Notification(
                title=title,
                message=message,
                notification_type=ntype,
            )
        if not notifications_cfg.get(ntype_key, True):
            return Notification(
                title=title,
                message=message,
                notification_type=ntype,
            )

        notif = Notification(
            title=title,
            message=message,
            notification_type=ntype,
            actions=actions or [],
        )

        with self._lock:
            self._notifications.append(notif)
            # Enforce cap – drop oldest read/dismissed first, then oldest overall
            if len(self._notifications) > _MAX_NOTIFICATIONS:
                self._evict()

        try:
            self.notification_added.emit(notif)
        except Exception:
            pass

        logger.info("Notification [%s]: %s – %s", ntype.value, title, message)
        return notif

    def info(self, title: str, message: str) -> Notification:
        """Shorthand for an informational notification."""
        return self.notify(title, message, NotificationType.INFO)

    def success(self, title: str, message: str) -> Notification:
        """Shorthand for a success notification."""
        return self.notify(title, message, NotificationType.SUCCESS)

    def warning(self, title: str, message: str) -> Notification:
        """Shorthand for a warning notification."""
        return self.notify(title, message, NotificationType.WARNING)

    def error(self, title: str, message: str) -> Notification:
        """Shorthand for an error notification."""
        return self.notify(title, message, NotificationType.ERROR)

    def security(self, title: str, message: str) -> Notification:
        """Shorthand for a security notification."""
        return self.notify(title, message, NotificationType.SECURITY)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_all(self) -> list[Notification]:
        """Return a copy of every notification (newest last)."""
        with self._lock:
            return list(self._notifications)

    def get_unread(self) -> list[Notification]:
        """Return a copy of unread, non-dismissed notifications."""
        with self._lock:
            return [n for n in self._notifications if not n.read and not n.dismissed]

    def count(self) -> int:
        """Return total number of stored notifications."""
        with self._lock:
            return len(self._notifications)

    def unread_count(self) -> int:
        """Return the number of unread, non-dismissed notifications."""
        with self._lock:
            return sum(1 for n in self._notifications if not n.read and not n.dismissed)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def mark_read(self, notification_id: str) -> None:
        """Mark a single notification as read.

        Parameters
        ----------
        notification_id:
            UUID of the notification to update.
        """
        with self._lock:
            for notif in self._notifications:
                if notif.id == notification_id:
                    notif.read = True
                    return

    def mark_all_read(self) -> None:
        """Mark every notification as read."""
        with self._lock:
            for notif in self._notifications:
                notif.read = True

    def dismiss(self, notification_id: str) -> None:
        """Dismiss a single notification.

        Parameters
        ----------
        notification_id:
            UUID of the notification to dismiss.
        """
        with self._lock:
            for notif in self._notifications:
                if notif.id == notification_id:
                    notif.dismissed = True
                    break

        try:
            self.notification_removed.emit(notification_id)
        except Exception:
            pass

    def clear(self) -> None:
        """Remove all notifications from memory."""
        with self._lock:
            self._notifications.clear()

        try:
            self.notifications_cleared.emit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict(self) -> None:
        """Drop oldest notifications when the cap is exceeded.

        Must be called while ``_lock`` is held.
        """
        # First pass: drop dismissed, then read, then oldest
        for predicate in (
            lambda n: n.dismissed,
            lambda n: n.read,
            lambda n: True,
        ):
            while len(self._notifications) > _MAX_NOTIFICATIONS:
                for idx, notif in enumerate(self._notifications):
                    if predicate(notif):
                        self._notifications.pop(idx)
                        break
                else:
                    break
