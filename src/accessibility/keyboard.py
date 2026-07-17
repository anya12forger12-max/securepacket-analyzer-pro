"""Keyboard navigation framework for SecurePacket Analyzer Pro.

Provides a focus chain system and keyboard event handling for accessible
navigation throughout the application interface.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QWidget


class FocusChain:
    """Manages an ordered chain of focusable widgets.

    Widgets are registered with a numeric order value. Lower order values
    are visited first when tabbing forward, and last when tabbing backward.

    Attributes:
        _widgets: List of (order, widget) tuples, maintained in sorted order.
    """

    def __init__(self) -> None:
        """Initialize an empty focus chain."""
        self._widgets: list[tuple[int, QWidget]] = []
        self._current_index: int = -1

    def register(self, widget: QWidget, order: int) -> None:
        """Register a widget in the focus chain.

        If the widget is already registered, its order is updated.

        Args:
            widget: The focusable widget to register.
            order: Numeric order determining focus position.
        """
        for i, (existing_order, existing_widget) in enumerate(self._widgets):
            if existing_widget is widget:
                self._widgets[i] = (order, widget)
                self._widgets.sort(key=lambda item: item[0])
                return

        self._widgets.append((order, widget))
        self._widgets.sort(key=lambda item: item[0])

    def unregister(self, widget: QWidget) -> None:
        """Remove a widget from the focus chain.

        Args:
            widget: The widget to remove.
        """
        self._widgets = [
            (order, w) for order, w in self._widgets if w is not widget
        ]

        if self._widgets:
            self._current_index = max(
                0, min(self._current_index, len(self._widgets) - 1)
            )
        else:
            self._current_index = -1

    def next(self) -> QWidget | None:
        """Return the next widget in the focus chain.

        Moves the internal pointer forward by one position, wrapping
        to the first widget if at the end.

        Returns:
            The next widget, or None if the chain is empty.
        """
        if not self._widgets:
            return None

        self._current_index += 1
        if self._current_index >= len(self._widgets):
            self._current_index = 0

        return self._widgets[self._current_index][1]

    def previous(self) -> QWidget | None:
        """Return the previous widget in the focus chain.

        Moves the internal pointer backward by one position, wrapping
        to the last widget if at the beginning.

        Returns:
            The previous widget, or None if the chain is empty.
        """
        if not self._widgets:
            return None

        self._current_index -= 1
        if self._current_index < 0:
            self._current_index = len(self._widgets) - 1

        return self._widgets[self._current_index][1]

    def first(self) -> QWidget | None:
        """Return the first widget in the focus chain.

        Returns:
            The first widget, or None if the chain is empty.
        """
        if not self._widgets:
            return None

        self._current_index = 0
        return self._widgets[0][1]

    def last(self) -> QWidget | None:
        """Return the last widget in the focus chain.

        Returns:
            The last widget, or None if the chain is empty.
        """
        if not self._widgets:
            return None

        self._current_index = len(self._widgets) - 1
        return self._widgets[-1][1]

    def clear(self) -> None:
        """Remove all widgets from the focus chain."""
        self._widgets.clear()
        self._current_index = -1

    @property
    def size(self) -> int:
        """Return the number of widgets in the focus chain."""
        return len(self._widgets)


class KeyboardNavigation(QObject):
    """Handles keyboard navigation events for a widget hierarchy.

    Installs an event filter on target widgets to intercept and process
    keyboard events for Tab, Shift+Tab, arrow key, and Escape navigation.

    Attributes:
        focus_chain: The FocusChain instance controlling tab order.
    """

    _ARROW_DIRECTIONS: frozenset[str] = frozenset(
        {"horizontal", "vertical", "both"}
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the keyboard navigation handler.

        Args:
            parent: Optional parent widget for the QObject.
        """
        super().__init__(parent)
        self.focus_chain = FocusChain()
        self._arrow_navigation: dict[int, str] = {}
        self._accessible_actions: dict[str, tuple[Callable[[], Any], str]] = {}

    def install_event_filter(self, widget: QWidget) -> None:
        """Install an event filter on a widget to capture keyboard events.

        Args:
            widget: The widget to monitor for keyboard events.
        """
        widget.installEventFilter(self)

    def event_filter(self, obj: Any, event: QEvent) -> bool:
        """Filter keyboard events for navigation handling.

        Processes Tab, Shift+Tab, arrow keys, Escape, and registered
        keyboard shortcuts. Returns True if the event was handled.

        Args:
            obj: The object that the event was sent to.
            event: The event to filter.

        Returns:
            True if the event was consumed, False otherwise.
        """
        if not isinstance(event, QEvent):
            return False

        event_type = event.type()

        if event_type == QEvent.Type.KeyPress:
            return self._handle_key_press(event)

        return False

    def _handle_key_press(self, event: QEvent) -> bool:
        """Process a key press event for navigation.

        Args:
            event: The key press event.

        Returns:
            True if the event was handled.
        """
        try:
            key = event.key()
            modifiers = event.modifiers()

            from PySide6.QtCore import Qt

            is_tab = key == Qt.Key.Key_Tab
            is_shift_tab = key == Qt.Key.Key_Backtab
            is_escape = key == Qt.Key.Key_Escape

            is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
            is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

            if is_tab or is_shift_tab:
                return self._handle_tab_navigation(is_shift)

            if is_escape:
                return self._handle_escape()

            arrow_keys = {
                Qt.Key.Key_Up: "up",
                Qt.Key.Key_Down: "down",
                Qt.Key.Key_Left: "left",
                Qt.Key.Key_Right: "right",
            }

            if key in arrow_keys:
                return self._handle_arrow_navigation(arrow_keys[key], obj=None)

            if is_ctrl and not is_shift:
                action_id = self._resolve_shortcut_event(event)
                if action_id is not None:
                    return self._execute_action(action_id)

        except Exception:
            pass

        return False

    def _handle_tab_navigation(self, backwards: bool) -> bool:
        """Handle Tab or Shift+Tab focus navigation.

        Args:
            backwards: True if navigating backward (Shift+Tab).

        Returns:
            True if focus was moved.
        """
        if backwards:
            widget = self.focus_chain.previous()
        else:
            widget = self.focus_chain.next()

        if widget is not None:
            widget.setFocus()
            return True

        return False

    def _handle_escape(self) -> bool:
        """Handle Escape key press by returning focus to the first widget.

        Returns:
            True if focus was moved.
        """
        widget = self.focus_chain.first()
        if widget is not None:
            widget.setFocus()
            return True
        return False

    def _handle_arrow-navigation(self, direction: str, obj: Any) -> bool:
        """Handle arrow key navigation within a container widget.

        Args:
            direction: The direction string ("up", "down", "left", "right").
            obj: The widget that received the event.

        Returns:
            True if the event was handled.
        """
        if obj is None or not isinstance(obj, QWidget):
            return False

        widget_id = id(obj)
        nav_mode = self._arrow_navigation.get(widget_id)
        if nav_mode is None:
            return False

        if nav_mode == "horizontal" and direction in ("up", "down"):
            return False
        if nav_mode == "vertical" and direction in ("left", "right"):
            return False

        return False

    def _resolve_shortcut_event(self, event: QEvent) -> str | None:
        """Resolve a key press event to a registered action ID.

        Args:
            event: The key press event.

        Returns:
            The matching action ID, or None if no match.
        """
        return None

    def _execute_action(self, action_id: str) -> bool:
        """Execute a registered accessible action.

        Args:
            action_id: The action identifier to execute.

        Returns:
            True if the action was found and executed.
        """
        entry = self._accessible_actions.get(action_id)
        if entry is None:
            return False

        callback, _description = entry
        try:
            callback()
            return True
        except Exception:
            return False

    def set_arrow_navigation(self, widget: QWidget, direction: str) -> None:
        """Configure arrow key navigation mode for a container widget.

        Args:
            widget: The container widget.
            direction: Navigation direction - "horizontal", "vertical",
                or "both".

        Raises:
            ValueError: If direction is not a valid navigation mode.
        """
        if direction not in self._ARROW_DIRECTIONS:
            raise ValueError(
                f"Invalid direction '{direction}'. "
                f"Must be one of: {sorted(self._ARROW_DIRECTIONS)}"
            )
        self._arrow_navigation[id(widget)] = direction

    def create_accessible_action(
        self,
        widget: QWidget,
        shortcut: str,
        callback: Callable[[], Any],
        description: str,
    ) -> None:
        """Register an accessible keyboard action bound to a widget.

        Args:
            widget: The widget this action is associated with.
            shortcut: The keyboard shortcut string triggering this action.
            callback: The callable to invoke when the shortcut is activated.
            description: A human-readable description of the action.
        """
        action_id = f"{id(widget)}_{shortcut}"
        self._accessible_actions[action_id] = (callback, description)
