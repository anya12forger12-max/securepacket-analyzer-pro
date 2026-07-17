"""Icon manager for SecurePacket Analyzer Pro.

Provides centralized icon loading, caching, and fallback rendering using
PySide6. Supports SVG icons from disk and text-based fallback icons for
all standard application icon names.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QFont


class IconManager:
    """Manages application icons with fallback support.

    Provides a unified interface for loading icons by logical name, with
    support for SVG files from disk and text-based colored fallback icons
    when files are unavailable.

    Attributes:
        _icon_dir: Base directory for icon files.
        _registry: Mapping of logical icon names to file paths.
        _icon_sets: Named collections of icons at different sizes.
        _cache: In-memory cache of loaded QIcon objects.
    """

    _STANDARD_ICONS: dict[str, str] = {
        "home": "\u2302",
        "dashboard": "\u25A3",
        "capture": "\u25CF",
        "packet": "\u25A4",
        "hosts": "\u2514",
        "connections": "\u250C",
        "alerts": "\u26A0",
        "statistics": "\u2588",
        "reports": "\u2193",
        "settings": "\u2699",
        "help": "?",
        "plugins": "\u2699",
        "search": "\u2315",
        "menu": "\u2630",
        "close": "\u2715",
        "minimize": "\u2500",
        "maximize": "\u25A1",
        "restore": "\u2195",
        "add": "+",
        "remove": "\u2212",
        "edit": "\u270E",
        "delete": "\u2718",
        "refresh": "\u21BB",
        "filter": "\u25B3",
        "export": "\u2191",
        "import": "\u2193",
        "save": "\u2913",
        "open": "\u25BD",
        "new": "\u2795",
        "start": "\u25B6",
        "stop": "\u25A0",
        "pause": "\u23F8",
        "play": "\u25B6",
        "warning": "\u26A0",
        "error": "\u2718",
        "info": "\u2139",
        "success": "\u2714",
        "security": "\u26E8",
        "workspace": "\u2302",
        "notifications": "\u266B",
        "about": "\u2139",
        "exit": "\u2190",
        "fullscreen": "\u26F6",
        "collapse": "\u229E",
        "expand": "\u229F",
        "up": "\u2191",
        "down": "\u2193",
        "left": "\u2190",
        "right": "\u2192",
        "check": "\u2714",
        "cross": "\u2718",
        "question": "?",
    }

    _ICON_COLORS: dict[str, QColor] = {
        "home": QColor("#0078D4"),
        "dashboard": QColor("#0078D4"),
        "capture": QColor("#D32F2F"),
        "packet": QColor("#5C2D91"),
        "hosts": QColor("#4CAF50"),
        "connections": QColor("#2196F3"),
        "alerts": QColor("#FF9800"),
        "statistics": QColor("#9C27B0"),
        "reports": QColor("#607D8B"),
        "settings": QColor("#78909C"),
        "help": QColor("#2196F3"),
        "plugins": QColor("#795548"),
        "search": QColor("#0078D4"),
        "menu": QColor("#CCCCCC"),
        "close": QColor("#D32F2F"),
        "minimize": QColor("#CCCCCC"),
        "maximize": QColor("#CCCCCC"),
        "restore": QColor("#CCCCCC"),
        "add": QColor("#4CAF50"),
        "remove": QColor("#D32F2F"),
        "edit": QColor("#FF9800"),
        "delete": QColor("#D32F2F"),
        "refresh": QColor("#0078D4"),
        "filter": QColor("#9C27B0"),
        "export": QColor("#4CAF50"),
        "import": QColor("#2196F3"),
        "save": QColor("#4CAF50"),
        "open": QColor("#2196F3"),
        "new": QColor("#4CAF50"),
        "start": QColor("#4CAF50"),
        "stop": QColor("#D32F2F"),
        "pause": QColor("#FF9800"),
        "play": QColor("#4CAF50"),
        "warning": QColor("#FF9800"),
        "error": QColor("#D32F2F"),
        "info": QColor("#2196F3"),
        "success": QColor("#4CAF50"),
        "security": QColor("#FF9800"),
        "workspace": QColor("#5C2D91"),
        "notifications": QColor("#FF9800"),
        "about": QColor("#2196F3"),
        "exit": QColor("#D32F2F"),
        "fullscreen": QColor("#0078D4"),
        "collapse": QColor("#CCCCCC"),
        "expand": QColor("#CCCCCC"),
        "up": QColor("#CCCCCC"),
        "down": QColor("#CCCCCC"),
        "left": QColor("#CCCCCC"),
        "right": QColor("#CCCCCC"),
        "check": QColor("#4CAF50"),
        "cross": QColor("#D32F2F"),
        "question": QColor("#2196F3"),
    }

    def __init__(self, icon_dir: Path | None = None) -> None:
        """Initialize the icon manager.

        Args:
            icon_dir: Optional directory containing icon files. If provided,
                the manager will look for SVGs in this directory.
        """
        self._icon_dir = icon_dir
        self._registry: dict[str, Path] = {}
        self._icon_sets: dict[str, dict[int, Path]] = {}
        self._cache: dict[tuple[str, int], QIcon] = {}

        if icon_dir is not None and icon_dir.is_dir():
            self._scan_icon_directory(icon_dir)

    def _scan_icon_directory(self, directory: Path) -> None:
        """Scan a directory for icon files and register them.

        Args:
            directory: The directory to scan for .svg icon files.
        """
        try:
            for svg_file in directory.rglob("*.svg"):
                stem = svg_file.stem.lower()
                if stem not in self._registry:
                    self._registry[stem] = svg_file
        except PermissionError:
            pass
        except OSError:
            pass

    def get_icon(self, name: str, size: int = 24, fallback: str = "") -> QIcon:
        """Retrieve an icon by logical name.

        Attempts to load from the file registry first, then falls back to
        creating a text-based icon from the built-in character set.

        Args:
            name: Logical icon name (e.g., "settings", "capture").
            size: Desired icon size in pixels.
            fallback: Optional fallback character to use instead of the
                built-in character for this icon name.

        Returns:
            A QIcon instance, either loaded from file or rendered as text.
        """
        cache_key = (name, size)
        if cache_key in self._cache:
            return self._cache[cache_key]

        icon = self._load_icon(name, size, fallback)
        self._cache[cache_key] = icon
        return icon

    def _load_icon(self, name: str, size: int, fallback: str) -> QIcon:
        """Internal icon loading with file-to-fallback cascade.

        Args:
            name: Logical icon name.
            size: Desired size in pixels.
            fallback: Optional fallback character.

        Returns:
            A QIcon instance.
        """
        path = self._registry.get(name.lower())
        if path is not None and path.exists():
            loaded = self.load_svg(path, size)
            if not loaded.isNull():
                return loaded

        character = fallback if fallback else self._STANDARD_ICONS.get(name, "?")
        color = self._ICON_COLORS.get(name, QColor("#CCCCCC"))
        return self._create_text_icon(character, color, size)

    def get_pixmap(self, name: str, size: int = 24) -> QPixmap:
        """Retrieve a pixmap by logical name.

        Args:
            name: Logical icon name.
            size: Desired size in pixels.

        Returns:
            A QPixmap instance.
        """
        icon = self.get_icon(name, size)
        pixmap = icon.pixmap(QSize(size, size))
        return pixmap

    def register_icon_set(self, name: str, paths: dict[int, Path]) -> None:
        """Register a named icon set with paths for multiple sizes.

        Args:
            name: The icon set name.
            paths: Mapping of pixel sizes to icon file paths.
        """
        self._icon_sets[name] = dict(paths)
        for size, path in paths.items():
            stem = path.stem.lower()
            if stem not in self._registry:
                self._registry[stem] = path

    def load_svg(self, path: Path, size: int = 24) -> QIcon:
        """Load an SVG icon from a file path.

        Args:
            path: Path to the SVG file.
            size: Desired icon size in pixels.

        Returns:
            A QIcon loaded from the SVG, or a null QIcon on failure.
        """
        if not path.exists():
            return QIcon()

        try:
            pixmap = QPixmap(QSize(size, size))
            pixmap.fill(Qt.GlobalColor.transparent)

            svg_icon = QIcon(str(path))
            if not svg_icon.isNull():
                return svg_icon
        except Exception:
            pass

        return QIcon()

    def _create_text_icon(self, text: str, color: QColor, size: int) -> QIcon:
        """Create an icon from a text character rendered onto a pixmap.

        Args:
            text: The character to render.
            color: The color for the rendered text.
            size: The icon size in pixels.

        Returns:
            A QIcon with the rendered text character.
        """
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(color)

        font = QFont("Arial", max(10, size // 2))
        font.setBold(True)
        painter.setFont(font)

        rect = QRectF(0, 0, float(size), float(size))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()

        return QIcon(pixmap)

    def _create_colored_square(self, color: QColor, size: int) -> QPixmap:
        """Create a solid colored square pixmap as a fallback icon.

        Args:
            color: The fill color.
            size: The pixmap size in pixels.

        Returns:
            A QPixmap filled with the specified color.
        """
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(color)
        return pixmap
