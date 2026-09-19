"""Keyboard shortcut manager for SecurePacket Analyzer Pro.

Provides centralized management of application keyboard shortcuts including
definition, validation, conflict detection, and import/export.
"""

from __future__ import annotations


class ShortcutManager:
    """Manages keyboard shortcuts for the application.

    Handles registration, validation, conflict detection, and persistence
    of keyboard shortcuts. All shortcuts are identified by a dotted action
    ID (e.g., "file.new", "capture.start").

    Attributes:
        _shortcuts: Mapping of action ID to (shortcut, description) pairs.
        _defaults: Immutable copy of the original default shortcuts.
    """

    _DEFAULTS: dict[str, tuple[str, str]] = {
        "file.new": ("Ctrl+N", "New Capture"),
        "file.open": ("Ctrl+O", "Open File"),
        "file.save": ("Ctrl+S", "Save"),
        "file.save_as": ("Ctrl+Shift+S", "Save As"),
        "file.quit": ("Ctrl+Q", "Quit"),
        "edit.find": ("Ctrl+F", "Find"),
        "edit.preferences": ("Ctrl+,", "Settings"),
        "capture.start": ("F5", "Start Capture"),
        "capture.stop": ("Shift+F5", "Stop Capture"),
        "capture.restart": ("Ctrl+R", "Restart Capture"),
        "view.refresh": ("Ctrl+Shift+R", "Refresh"),
        "view.toggle_sidebar": ("Ctrl+Shift+L", "Toggle Sidebar"),
        "view.fullscreen": ("F11", "Toggle Fullscreen"),
        "help.shortcuts": ("Ctrl+/", "Keyboard Shortcuts"),
        "help.help": ("F1", "Help"),
        "command_palette": ("Ctrl+Shift+P", "Command Palette"),
    }

    _MODIFIER_PARTS: frozenset[str] = frozenset({"Ctrl", "Alt", "Shift", "Meta", "Cmd", "Super"})

    def __init__(self) -> None:
        """Initialize the shortcut manager with default shortcuts."""
        self._shortcuts: dict[str, tuple[str, str]] = {
            action: (shortcut, desc) for action, (shortcut, desc) in self._DEFAULTS.items()
        }
        self._defaults: dict[str, tuple[str, str]] = {
            action: (shortcut, desc) for action, (shortcut, desc) in self._DEFAULTS.items()
        }

    def get_shortcut(self, action_id: str) -> str | None:
        """Retrieve the keyboard shortcut for a given action.

        Args:
            action_id: The dotted action identifier.

        Returns:
            The shortcut string (e.g., "Ctrl+N"), or None if the action
            is not registered.
        """
        entry = self._shortcuts.get(action_id)
        if entry is None:
            return None
        return entry[0]

    def get_description(self, action_id: str) -> str:
        """Retrieve the human-readable description for an action.

        Args:
            action_id: The dotted action identifier.

        Returns:
            The description string, or an empty string if not found.
        """
        entry = self._shortcuts.get(action_id)
        if entry is None:
            return ""
        return entry[1]

    def set_shortcut(self, action_id: str, shortcut: str) -> None:
        """Assign a new shortcut to an action.

        If the action does not already exist, it is created with an
        empty description.

        Args:
            action_id: The dotted action identifier.
            shortcut: The new keyboard shortcut string.

        Raises:
            ValueError: If the shortcut format is invalid.
        """
        if not self._validate_format(shortcut):
            raise ValueError(f"Invalid shortcut format: '{shortcut}'")

        description = ""
        existing = self._shortcuts.get(action_id)
        if existing is not None:
            description = existing[1]

        self._shortcuts[action_id] = (shortcut, description)

    def get_all_shortcuts(self) -> dict[str, tuple[str, str]]:
        """Return a copy of all registered shortcuts.

        Returns:
            A dictionary mapping action IDs to (shortcut, description) tuples.
        """
        return dict(self._shortcuts)

    def reset_to_defaults(self) -> None:
        """Reset all shortcuts to their default values."""
        self._shortcuts = {
            action: (shortcut, desc) for action, (shortcut, desc) in self._defaults.items()
        }

    def validate_shortcut(self, shortcut: str) -> bool:
        """Check whether a shortcut string is valid and has no conflicts.

        A valid shortcut must have at least one modifier key and a single
        non-modifier key, and must not conflict with other registered
        shortcuts.

        Args:
            shortcut: The shortcut string to validate.

        Returns:
            True if the shortcut is valid and conflict-free.
        """
        if not self._validate_format(shortcut):
            return False

        conflicts = self.get_conflicts(shortcut)
        return len(conflicts) == 0

    def get_conflicts(self, shortcut: str, exclude_action: str = "") -> list[str]:
        """Find actions that share the same shortcut.

        Args:
            shortcut: The shortcut string to check.
            exclude_action: An action ID to exclude from the conflict check.
                Useful when changing an existing shortcut.

        Returns:
            A list of action IDs that conflict with the given shortcut.
        """
        normalized = self._normalize_shortcut(shortcut)
        conflicts: list[str] = []
        for action_id, (existing, _) in self._shortcuts.items():
            if action_id == exclude_action:
                continue
            if self._normalize_shortcut(existing) == normalized:
                conflicts.append(action_id)
        return conflicts

    def export_shortcuts(self) -> dict[str, str]:
        """Export all shortcuts as a simple action-to-shortcut mapping.

        Returns:
            A dictionary mapping action IDs to their shortcut strings.
        """
        return {action: shortcut for action, (shortcut, _) in self._shortcuts.items()}

    def import_shortcuts(self, data: dict[str, str]) -> list[str]:
        """Import shortcuts from an external source.

        Each valid shortcut is applied. Invalid or conflicting shortcuts
        are skipped and their action IDs are included in the returned error list.

        Args:
            data: A dictionary mapping action IDs to shortcut strings.

        Returns:
            A list of error descriptions for shortcuts that could not be
            imported.
        """
        errors: list[str] = []

        for action_id, shortcut in data.items():
            if not isinstance(action_id, str) or not isinstance(shortcut, str):
                errors.append(f"Invalid entry for '{action_id}': expected string values.")
                continue

            if not self._validate_format(shortcut):
                errors.append(f"Invalid shortcut format for '{action_id}': '{shortcut}'.")
                continue

            conflicts = self.get_conflicts(shortcut, exclude_action=action_id)
            if conflicts:
                errors.append(
                    f"Shortcut '{shortcut}' for '{action_id}' conflicts "
                    f"with: {', '.join(conflicts)}."
                )
                continue

            description = ""
            existing = self._shortcuts.get(action_id)
            if existing is not None:
                description = existing[1]

            self._shortcuts[action_id] = (shortcut, description)

        return errors

    def _validate_format(self, shortcut: str) -> bool:
        """Validate the structural format of a shortcut string.

        A valid shortcut must contain at least one modifier key and exactly
        one non-modifier key separated by '+'.

        Args:
            shortcut: The shortcut string to validate.

        Returns:
            True if the format is valid.
        """
        if not shortcut or not isinstance(shortcut, str):
            return False

        parts = [p.strip() for p in shortcut.split("+")]
        if not parts or any(p == "" for p in parts):
            return False

        modifiers = [p for p in parts if p in self._MODIFIER_PARTS]
        keys = [p for p in parts if p not in self._MODIFIER_PARTS]

        if len(modifiers) == 0:
            return False

        if len(keys) != 1:
            return False

        key = keys[0]
        if not key:
            return False

        valid_single_keys = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        valid_special_keys = frozenset(
            {
                "F1",
                "F2",
                "F3",
                "F4",
                "F5",
                "F6",
                "F7",
                "F8",
                "F9",
                "F10",
                "F11",
                "F12",
                "F13",
                "F14",
                "F15",
                "F16",
                "F17",
                "F18",
                "F19",
                "F20",
                "F21",
                "F22",
                "F23",
                "F24",
                "Space",
                "Tab",
                "Enter",
                "Return",
                "Escape",
                "Backspace",
                "Delete",
                "Insert",
                "Home",
                "End",
                "PageUp",
                "PageDown",
                "Up",
                "Down",
                "Left",
                "Right",
                "CapsLock",
                "NumLock",
                "ScrollLock",
                "PrintScreen",
                "Pause",
                "Menu",
            }
        )

        return key in valid_single_keys or key in valid_special_keys

    @staticmethod
    def _normalize_shortcut(shortcut: str) -> str:
        """Normalize a shortcut string for consistent comparison.

        Sorts modifiers alphabetically and ensures consistent casing.

        Args:
            shortcut: The shortcut string to normalize.

        Returns:
            A normalized shortcut string.
        """
        parts = [p.strip() for p in shortcut.split("+")]
        modifiers = sorted(p for p in parts if p in ShortcutManager._MODIFIER_PARTS)
        keys = [p for p in parts if p not in ShortcutManager._MODIFIER_PARTS]
        return "+".join(modifiers + keys)
