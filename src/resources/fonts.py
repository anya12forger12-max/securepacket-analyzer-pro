"""Font manager for SecurePacket Analyzer Pro.

Provides font configuration, loading, and platform-specific font detection
for the application interface.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from PySide6.QtGui import QFont, QFontDatabase


class FontManager:
    """Manages application fonts and font configuration.

    Handles font selection, sizing, custom font loading, and platform-specific
    font detection. Integrates with the settings manager for persisting
    font preferences.

    Attributes:
        _settings: Optional settings manager for persisting preferences.
        _font_database: Reference to the Qt font database.
    """

    _DEFAULT_FAMILY: str = "Segoe UI"
    _DEFAULT_MONO_FAMILY: str = "Consolas"
    _DEFAULT_SIZE: int = 12
    _MIN_SIZE: int = 8
    _MAX_SIZE: int = 48
    _DYSLEXIA_FONTS: tuple[str, ...] = (
        "OpenDyslexic",
        "Lexie Readable",
        "Read Regular",
        "EasyReading",
    )

    _SYSTEM_FONT_MAPS: dict[str, dict[str, str]] = {
        "Linux": {
            "sans": "Ubuntu",
            "serif": "Liberation Serif",
            "mono": "Liberation Mono",
            "ui": "Ubuntu",
        },
        "Windows": {
            "sans": "Segoe UI",
            "serif": "Times New Roman",
            "mono": "Consolas",
            "ui": "Segoe UI",
        },
        "Darwin": {
            "sans": "Helvetica Neue",
            "serif": "Times New Roman",
            "mono": "Menlo",
            "ui": "SF Pro Text",
        },
    }

    def __init__(self, settings: Any = None) -> None:
        """Initialize the font manager.

        Args:
            settings: Optional SettingsManager instance for persisting
                font preferences.
        """
        self._settings = settings
        self._font_database = QFontDatabase()
        self._custom_fonts: dict[str, QFont] = {}

    def _get_setting(self, key: str, default: Any) -> Any:
        """Retrieve a setting value from the settings manager.

        Args:
            key: The setting key.
            default: Fallback value.

        Returns:
            The setting value or the default.
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
            key: The setting key.
            value: The value to store.
        """
        if self._settings is not None and hasattr(self._settings, "set"):
            try:
                self._settings.set(key, value)
            except Exception:
                pass

    def get_default_font(self) -> QFont:
        """Return the application default font with user preferences applied.

        Returns:
            A QFont configured with the user's preferred family and size.
        """
        family = str(self._get_setting("font/family", self._DEFAULT_FAMILY))
        size = int(self._get_setting("font/size", self._DEFAULT_SIZE))

        font = QFont(family, size)
        font.setStyleStrategy(
            QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
        )
        return font

    def get_monospace_font(self) -> QFont:
        """Return a monospace font suitable for code and data display.

        Attempts to use the user's preferred monospace font, falling back
        to platform defaults.

        Returns:
            A QFont configured for monospace rendering.
        """
        family = str(self._get_setting("font/mono_family", self._DEFAULT_MONO_FAMILY))
        size = int(self._get_setting("font/mono_size", self._DEFAULT_SIZE))

        if not self.is_font_available(family):
            platform_fonts = self._detect_platform_fonts()
            family = platform_fonts.get("mono", self._DEFAULT_MONO_FAMILY)

        font = QFont(family, size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        return font

    def get_ui_font(self) -> QFont:
        """Return the font used for general UI elements.

        Returns:
            A QFont configured for UI text rendering.
        """
        platform_fonts = self._detect_platform_fonts()
        family = platform_fonts.get("ui", self._DEFAULT_FAMILY)
        size = int(self._get_setting("font/ui_size", self._DEFAULT_SIZE))

        font = QFont(family, size)
        return font

    def set_font_size(self, size: int) -> None:
        """Set the default font size and persist it.

        Args:
            size: Font size in points, clamped to [8, 48].

        Raises:
            ValueError: If size is outside the allowed range.
        """
        clamped = max(self._MIN_SIZE, min(self._MAX_SIZE, size))
        if clamped != size:
            raise ValueError(
                f"Font size must be between {self._MIN_SIZE} and " f"{self._MAX_SIZE}, got {size}"
            )
        self._set_setting("font/size", clamped)

    def set_font_family(self, family: str) -> None:
        """Set the default font family and persist it.

        Args:
            family: The font family name to use.
        """
        self._set_setting("font/family", family)

    def get_available_fonts(self) -> list[str]:
        """Return a sorted list of all available font families on the system.

        Returns:
            A list of font family name strings.
        """
        families = self._font_database.families()
        return sorted(families)

    def get_system_fonts(self) -> dict[str, str]:
        """Return platform-specific system font recommendations.

        Returns:
            A dictionary mapping category names ("sans", "serif", "mono",
            "ui") to font family names appropriate for the current platform.
        """
        system = platform.system()
        fonts = self._SYSTEM_FONT_MAPS.get(system, self._SYSTEM_FONT_MAPS["Linux"])
        result: dict[str, str] = {}

        for category, default_family in fonts.items():
            available = [
                f for f in self._font_database.families() if default_family.lower() in f.lower()
            ]
            if available:
                result[category] = available[0]
            else:
                result[category] = default_family

        return result

    def load_custom_font(self, path: Path) -> QFont | None:
        """Load a custom font file and register it with Qt.

        Args:
            path: Path to a font file (.ttf, .otf, .woff, etc.).

        Returns:
            A QFont using the loaded font, or None if loading failed.
        """
        if not path.exists():
            return None

        if not path.is_file():
            return None

        font_id = self._font_database.addApplicationFont(str(path))
        if font_id == -1:
            return None

        loaded_families = self._font_database.applicationFontFamilies(font_id)
        if not loaded_families:
            return None

        family_name = loaded_families[0]
        size = int(self._get_setting("font/size", self._DEFAULT_SIZE))
        font = QFont(family_name, size)
        self._custom_fonts[str(path)] = font
        return font

    def apply_font_scale(self, font: QFont, scale: float) -> QFont:
        """Apply a scaling factor to a font's size.

        Args:
            font: The font to scale.
            scale: The scaling factor. A value of 1.0 keeps the original size.

        Returns:
            A new QFont with the adjusted size.
        """
        original_size = font.pointSize()
        if original_size <= 0:
            original_size = self._DEFAULT_SIZE

        scaled_size = int(original_size * scale)
        scaled_size = max(self._MIN_SIZE, min(self._MAX_SIZE, scaled_size))

        new_font = QFont(font)
        new_font.setPointSize(scaled_size)
        return new_font

    def get_dyslexia_friendly_font(self) -> QFont:
        """Return a dyslexia-friendly font, attempting OpenDyslexic first.

        Iterates through known dyslexia-friendly fonts and returns the first
        one available on the system. Falls back to the default UI font.

        Returns:
            A QFont using a dyslexia-friendly font if available, otherwise
            the standard UI font.
        """
        for family in self._DYSLEXIA_FONTS:
            if self.is_font_available(family):
                size = int(self._get_setting("font/size", self._DEFAULT_SIZE))
                font = QFont(family, size)
                font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.5)
                return font

        return self.get_ui_font()

    def is_font_available(self, family: str) -> bool:
        """Check whether a font family is available on the system.

        Args:
            family: The font family name to check.

        Returns:
            True if the font family is available.
        """
        available = self._font_database.families()
        family_lower = family.lower()
        return any(f.lower() == family_lower for f in available)

    def _detect_platform_fonts(self) -> dict[str, str]:
        """Detect recommended fonts for the current platform.

        Returns:
            A dictionary mapping category names ("sans", "serif", "mono",
            "ui") to font family names detected or defaulted for the platform.
        """
        system = platform.system()
        defaults = self._SYSTEM_FONT_MAPS.get(system, self._SYSTEM_FONT_MAPS["Linux"])

        result: dict[str, str] = {}
        for category, preferred in defaults.items():
            if self.is_font_available(preferred):
                result[category] = preferred
            else:
                result[category] = self._find_best_alternative(category)

        return result

    def _find_best_alternative(self, category: str) -> str:
        """Find the best alternative font for a given category.

        Args:
            category: The font category ("sans", "serif", "mono", "ui").

        Returns:
            The name of the best available alternative font.
        """
        if sys.platform == "win32":
            fallbacks: dict[str, list[str]] = {
                "sans": ["Arial", "Tahoma", "Verdana"],
                "serif": ["Times New Roman", "Georgia", "Cambria"],
                "mono": ["Consolas", "Courier New", "Lucida Console"],
                "ui": ["Segoe UI", "Tahoma", "Arial"],
            }
        elif sys.platform == "darwin":
            fallbacks = {
                "sans": ["Helvetica Neue", "Helvetica", "Arial"],
                "serif": ["Times New Roman", "Georgia", "Palatino"],
                "mono": ["Menlo", "Monaco", "Courier New"],
                "ui": ["SF Pro Text", "Helvetica Neue", "Lucida Grande"],
            }
        else:
            fallbacks = {
                "sans": ["Ubuntu", "DejaVu Sans", "Liberation Sans", "Arial"],
                "serif": [
                    "Liberation Serif",
                    "DejaVu Serif",
                    "Times New Roman",
                ],
                "mono": [
                    "Liberation Mono",
                    "DejaVu Sans Mono",
                    "Consolas",
                ],
                "ui": ["Ubuntu", "DejaVu Sans", "Liberation Sans"],
            }

        alternatives = fallbacks.get(category, fallbacks["sans"])
        for family in alternatives:
            if self.is_font_available(family):
                return family

        available = self._font_database.families()
        if available:
            return available[0]

        return self._DEFAULT_FAMILY
