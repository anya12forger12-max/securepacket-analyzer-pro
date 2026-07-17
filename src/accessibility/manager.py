"""Accessibility manager for SecurePacket Analyzer Pro.

Provides comprehensive accessibility features including high contrast mode,
reduced motion, color blind support, WCAG compliance validation, and
accessible color palettes.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal


class AccessibilityManager(QObject):
    """Manages accessibility settings and provides WCAG-compliant utilities.

    This class centralizes all accessibility-related functionality including
    display preferences, color blind accommodations, WCAG compliance checking,
    and accessible color palette generation.

    Signals:
        accessibility_changed: Emitted when any accessibility property changes.
            The string parameter contains the name of the changed property.
    """

    accessibility_changed = Signal(str)

    _COLOR_BLIND_MODES: frozenset[str] = frozenset(
        {"none", "protanopia", "deuteranopia", "tritanopia"}
    )
    _WCAG_LEVELS: frozenset[str] = frozenset({"A", "AA", "AAA"})
    _TEXT_SCALE_MIN: float = 0.5
    _TEXT_SCALE_MAX: float = 3.0
    _ICON_SCALE_MIN: float = 0.5
    _ICON_SCALE_MAX: float = 3.0
    _MIN_TOUCH_TARGET: int = 44

    _PALETTES: dict[str, dict[str, str]] = {
        "normal": {
            "primary": "#0078D4",
            "secondary": "#5C2D91",
            "background": "#1e1e1e",
            "surface": "#2d2d2d",
            "text_primary": "#FFFFFF",
            "text_secondary": "#CCCCCC",
            "border": "#404040",
            "focus": "#0078D4",
            "error": "#D32F2F",
            "warning": "#FF9800",
            "success": "#4CAF50",
            "info": "#2196F3",
            "link": "#6CB2EE",
            "accent": "#0078D4",
        },
        "protanopia": {
            "primary": "#0072B5",
            "secondary": "#56B4E9",
            "background": "#1e1e1e",
            "surface": "#2d2d2d",
            "text_primary": "#FFFFFF",
            "text_secondary": "#CCCCCC",
            "border": "#404040",
            "focus": "#0072B5",
            "error": "#CC79A7",
            "warning": "#E69F00",
            "success": "#009E73",
            "info": "#56B4E9",
            "link": "#56B4E9",
            "accent": "#0072B5",
        },
        "deuteranopia": {
            "primary": "#0072B5",
            "secondary": "#CC79A7",
            "background": "#1e1e1e",
            "surface": "#2d2d2d",
            "text_primary": "#FFFFFF",
            "text_secondary": "#CCCCCC",
            "border": "#404040",
            "focus": "#0072B5",
            "error": "#D55E00",
            "warning": "#E69F00",
            "success": "#009E73",
            "info": "#56B4E9",
            "link": "#56B4E9",
            "accent": "#0072B5",
        },
        "tritanopia": {
            "primary": "#0072B5",
            "secondary": "#CC79A7",
            "background": "#1e1e1e",
            "surface": "#2d2d2d",
            "text_primary": "#FFFFFF",
            "text_secondary": "#CCCCCC",
            "border": "#404040",
            "focus": "#0072B5",
            "error": "#D55E00",
            "warning": "#E69F00",
            "success": "#009E73",
            "info": "#56B4E9",
            "link": "#56B4E9",
            "accent": "#0072B5",
        },
        "high_contrast": {
            "primary": "#FFFFFF",
            "secondary": "#FFFF00",
            "background": "#000000",
            "surface": "#1A1A1A",
            "text_primary": "#FFFFFF",
            "text_secondary": "#FFFF00",
            "border": "#FFFFFF",
            "focus": "#FFFF00",
            "error": "#FF6B6B",
            "warning": "#FFD700",
            "success": "#00FF7F",
            "info": "#00FFFF",
            "link": "#FFFF00",
            "accent": "#FFFF00",
        },
    }

    def __init__(self, settings: Any = None) -> None:
        """Initialize the accessibility manager.

        Args:
            settings: Optional SettingsManager instance for persisting preferences.
        """
        super().__init__()
        self._settings = settings

    def _get_setting(self, key: str, default: Any) -> Any:
        """Retrieve a setting value from the settings manager.

        Args:
            key: The setting key to look up.
            default: Fallback value if the setting is not found.

        Returns:
            The setting value, or the default if not available.
        """
        if self._settings is not None and hasattr(self._settings, "get"):
            try:
                return self._settings.get(key, default)
            except Exception:
                return default
        return default

    def _set_setting(self, key: str, value: Any) -> None:
        """Persist a setting value through the settings manager.

        Args:
            key: The setting key to store.
            value: The value to store.
        """
        if self._settings is not None and hasattr(self._settings, "set"):
            try:
                self._settings.set(key, value)
            except Exception:
                pass

    @property
    def high_contrast(self) -> bool:
        """Whether high contrast mode is enabled."""
        return bool(self._get_setting("accessibility/high_contrast", False))

    @property
    def reduced_motion(self) -> bool:
        """Whether reduced motion mode is enabled."""
        return bool(self._get_setting("accessibility/reduced_motion", False))

    @property
    def large_ui(self) -> bool:
        """Whether large UI elements are enabled."""
        return bool(self._get_setting("accessibility/large_ui", False))

    @property
    def large_cursor(self) -> bool:
        """Whether an enlarged cursor is enabled."""
        return bool(self._get_setting("accessibility/large_cursor", False))

    @property
    def screen_reader_enabled(self) -> bool:
        """Whether screen reader support is enabled."""
        return bool(self._get_setting("accessibility/screen_reader", False))

    @property
    def keyboard_navigation(self) -> bool:
        """Whether enhanced keyboard navigation is enabled."""
        return bool(self._get_setting("accessibility/keyboard_navigation", True))

    @property
    def focus_indicators(self) -> bool:
        """Whether visible focus indicators are enabled."""
        return bool(self._get_setting("accessibility/focus_indicators", True))

    @property
    def color_blind_mode(self) -> str:
        """Current color blind accommodation mode.

        Returns one of: "none", "protanopia", "deuteranopia", "tritanopia".
        """
        mode = str(self._get_setting("accessibility/color_blind_mode", "none"))
        if mode not in self._COLOR_BLIND_MODES:
            return "none"
        return mode

    @property
    def text_scale(self) -> float:
        """Text scaling factor. Default is 1.0, range is 0.5 to 3.0."""
        value = float(self._get_setting("accessibility/text_scale", 1.0))
        return max(self._TEXT_SCALE_MIN, min(self._TEXT_SCALE_MAX, value))

    @property
    def icon_scale(self) -> float:
        """Icon scaling factor. Default is 1.0, range is 0.5 to 3.0."""
        value = float(self._get_setting("accessibility/icon_scale", 1.0))
        return max(self._ICON_SCALE_MIN, min(self._ICON_SCALE_MAX, value))

    @property
    def wcag_level(self) -> str:
        """Target WCAG compliance level.

        Returns one of: "A", "AA", "AAA".
        """
        level = str(self._get_setting("accessibility/wcag_level", "AA"))
        if level not in self._WCAG_LEVELS:
            return "AA"
        return level

    @property
    def accessible_tooltips(self) -> bool:
        """Whether accessible (rich) tooltips are enabled."""
        return bool(self._get_setting("accessibility/accessible_tooltips", True))

    def set_high_contrast(self, enabled: bool) -> None:
        """Enable or disable high contrast mode.

        Args:
            enabled: True to enable high contrast, False to disable.
        """
        self._set_setting("accessibility/high_contrast", enabled)
        self.accessibility_changed.emit("high_contrast")

    def set_reduced_motion(self, enabled: bool) -> None:
        """Enable or disable reduced motion mode.

        Args:
            enabled: True to enable reduced motion, False to disable.
        """
        self._set_setting("accessibility/reduced_motion", enabled)
        self.accessibility_changed.emit("reduced_motion")

    def set_large_ui(self, enabled: bool) -> None:
        """Enable or disable large UI elements.

        Args:
            enabled: True to enable large UI, False to disable.
        """
        self._set_setting("accessibility/large_ui", enabled)
        self.accessibility_changed.emit("large_ui")

    def set_text_scale(self, scale: float) -> None:
        """Set the text scaling factor.

        Args:
            scale: Scaling factor clamped to [0.5, 3.0].

        Raises:
            ValueError: If scale is outside the allowed range.
        """
        if not (self._TEXT_SCALE_MIN <= scale <= self._TEXT_SCALE_MAX):
            raise ValueError(
                f"Text scale must be between {self._TEXT_SCALE_MIN} "
                f"and {self._TEXT_SCALE_MAX}, got {scale}"
            )
        self._set_setting("accessibility/text_scale", scale)
        self.accessibility_changed.emit("text_scale")

    def set_icon_scale(self, scale: float) -> None:
        """Set the icon scaling factor.

        Args:
            scale: Scaling factor clamped to [0.5, 3.0].

        Raises:
            ValueError: If scale is outside the allowed range.
        """
        if not (self._ICON_SCALE_MIN <= scale <= self._ICON_SCALE_MAX):
            raise ValueError(
                f"Icon scale must be between {self._ICON_SCALE_MIN} "
                f"and {self._ICON_SCALE_MAX}, got {scale}"
            )
        self._set_setting("accessibility/icon_scale", scale)
        self.accessibility_changed.emit("icon_scale")

    def set_color_blind_mode(self, mode: str) -> None:
        """Set the color blind accommodation mode.

        Args:
            mode: One of "none", "protanopia", "deuteranopia", "tritanopia".

        Raises:
            ValueError: If mode is not a recognized color blind mode.
        """
        if mode not in self._COLOR_BLIND_MODES:
            raise ValueError(
                f"Invalid color blind mode '{mode}'. "
                f"Must be one of: {sorted(self._COLOR_BLIND_MODES)}"
            )
        self._set_setting("accessibility/color_blind_mode", mode)
        self.accessibility_changed.emit("color_blind_mode")

    def get_palette(self) -> dict[str, str]:
        """Return the color palette for the current accessibility configuration.

        The palette is selected based on the active color blind mode and
        whether high contrast is enabled. High contrast takes precedence.

        Returns:
            A dictionary mapping palette role names to hex color strings.
            Contains keys: primary, secondary, background, surface,
            text_primary, text_secondary, border, focus, error, warning,
            success, info, link, accent.
        """
        if self.high_contrast:
            return dict(self._PALETTES["high_contrast"])

        mode = self.color_blind_mode
        if mode != "none" and mode in self._PALETTES:
            return dict(self._PALETTES[mode])

        return dict(self._PALETTES["normal"])

    def get_focus_style(self) -> str:
        """Return a Qt stylesheet for focus indicators.

        The stylesheet is tailored to the current accessibility settings,
        using thicker borders and higher contrast when needed.

        Returns:
            A valid Qt stylesheet string for focus indicator styling.
        """
        palette = self.get_palette()
        focus_color = palette["focus"]

        if self.high_contrast:
            return (
                "QWidget:focus { outline: 3px solid " + focus_color + "; } "
                "QPushButton:focus { border: 3px solid " + focus_color + "; } "
                "QLineEdit:focus { border: 3px solid " + focus_color + "; } "
                "QTextEdit:focus { border: 3px solid " + focus_color + "; } "
                "QTreeView:focus { border: 3px solid " + focus_color + "; } "
                "QTableView:focus { border: 3px solid " + focus_color + "; } "
                "QComboBox:focus { border: 3px solid " + focus_color + "; } "
                "QTabBar:focus { outline: 3px solid " + focus_color + "; } "
                "QCheckBox:focus { outline: 3px solid " + focus_color + "; } "
                "QRadioButton:focus { outline: 3px solid " + focus_color + "; } "
            )

        border_width = "2px" if self.large_ui else "1px"
        return (
            "QWidget:focus { outline: " + border_width + " solid " + focus_color + "; } "
            "QPushButton:focus { border: " + border_width + " solid " + focus_color + "; } "
            "QLineEdit:focus { border: " + border_width + " solid " + focus_color + "; } "
            "QTextEdit:focus { border: " + border_width + " solid " + focus_color + "; } "
            "QTreeView:focus { border: " + border_width + " solid " + focus_color + "; } "
            "QTableView:focus { border: " + border_width + " solid " + focus_color + "; } "
            "QComboBox:focus { border: " + border_width + " solid " + focus_color + "; } "
            "QTabBar:focus { outline: " + border_width + " solid " + focus_color + "; } "
        )

    def get_minimum_touch_target(self) -> int:
        """Return the minimum touch target size in pixels.

        WCAG 2.5.5 recommends a minimum target size of 44x44 CSS pixels
        for touch interfaces.

        Returns:
            Minimum pixel dimension for interactive touch targets.
        """
        if self.large_ui:
            return max(self._MIN_TOUCH_TARGET, 56)
        return self._MIN_TOUCH_TARGET

    def validate_wcag_compliance(self, level: str = "AA") -> list[str]:
        """Validate current accessibility settings against WCAG guidelines.

        Args:
            level: Target WCAG level ("A", "AA", or "AAA").

        Returns:
            A list of human-readable issue descriptions. An empty list means
            no issues were found at the specified compliance level.
        """
        if level not in self._WCAG_LEVELS:
            raise ValueError(
                f"Invalid WCAG level '{level}'. Must be one of: {sorted(self._WCAG_LEVELS)}"
            )

        issues: list[str] = []

        if level in ("AA", "AAA"):
            if self.text_scale < 1.0:
                issues.append(
                    "Text scale is below 1.0 which may reduce readability "
                    "for users with low vision (WCAG 1.4.4)."
                )

            if not self.focus_indicators:
                issues.append(
                    "Focus indicators are disabled. Visible focus is required "
                    "for keyboard accessibility (WCAG 2.4.7)."
                )

            if not self.keyboard_navigation:
                issues.append(
                    "Enhanced keyboard navigation is disabled. Full keyboard "
                    "accessibility is required (WCAG 2.1.1)."
                )

        if level == "AAA":
            if not self.high_contrast and self.color_blind_mode == "none":
                palette = self.get_palette()
                bg_lum = self._relative_luminance(palette["background"])
                text_lum = self._relative_luminance(palette["text_primary"])
                ratio = self._contrast_ratio(bg_lum, text_lum)
                if ratio < 7.0:
                    issues.append(
                        f"Text-to-background contrast ratio is {ratio:.1f}:1. "
                        f"WCAG AAA requires 7:1 for normal text (WCAG 1.4.6)."
                    )

            if not self.large_ui:
                issues.append(
                    "Large UI mode is not enabled. Enhanced sizing aids "
                    "readability for AAA compliance."
                )

            if self.text_scale < 1.2:
                issues.append(
                    "Text scale is below 1.2 which is recommended for "
                    "AAA-level readability (WCAG 1.4.8)."
                )

        if level in ("A", "AA", "AAA"):
            if not self.accessible_tooltips:
                issues.append(
                    "Accessible tooltips are disabled. Tooltips provide "
                    "additional context for users (WCAG 1.3.1)."
                )

        return issues

    @staticmethod
    def _relative_luminance(hex_color: str) -> float:
        """Calculate the relative luminance of a hex color per WCAG 2.0.

        Args:
            hex_color: A hex color string (e.g. "#FFFFFF").

        Returns:
            The relative luminance value between 0.0 and 1.0.
        """
        color = hex_color.lstrip("#")
        if len(color) != 6:
            return 0.0

        try:
            r = int(color[0:2], 16) / 255.0
            g = int(color[2:4], 16) / 255.0
            b = int(color[4:6], 16) / 255.0
        except ValueError:
            return 0.0

        def linearize(c: float) -> float:
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)

    @staticmethod
    def _contrast_ratio(luminance1: float, luminance2: float) -> float:
        """Calculate the WCAG contrast ratio between two luminance values.

        Args:
            luminance1: Relative luminance of the first color.
            luminance2: Relative luminance of the second color.

        Returns:
            The contrast ratio, between 1:1 and 21:1.
        """
        lighter = max(luminance1, luminance2)
        darker = min(luminance1, luminance2)
        numerator = lighter + 0.05
        denominator = darker + 0.05
        if denominator == 0:
            return 21.0
        return numerator / denominator
