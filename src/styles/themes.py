"""Theme manager for SecurePacket Analyzer Pro.

Provides comprehensive Qt stylesheet (QSS) theming with dark, light,
and high-contrast themes. Integrates with the accessibility manager
for dynamic theme adaptation.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, ClassVar

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from collections.abc import Callable


class ThemeManager(QObject):
    """Manages application themes and Qt stylesheets.

    Provides built-in dark, light, and high-contrast themes, with support
    for registering custom themes. Integrates with AccessibilityManager
    for automatic theme adjustments.

    Signals:
        theme_changed: Emitted when the active theme is changed.
            The string parameter contains the new theme name.
    """

    theme_changed = Signal(str)

    _THEME_INFO: ClassVar[dict[str, dict[str, str]]] = {
        "dark": {
            "name": "Dark",
            "description": "A dark theme optimized for low-light environments.",
            "author": "SecurePacket Analyzer Pro",
            "version": "1.0.0",
        },
        "light": {
            "name": "Light",
            "description": "A light theme for bright environments and printing.",
            "author": "SecurePacket Analyzer Pro",
            "version": "1.0.0",
        },
        "high_contrast": {
            "name": "High Contrast",
            "description": "A high-contrast theme for maximum accessibility.",
            "author": "SecurePacket Analyzer Pro",
            "version": "1.0.0",
        },
    }

    def __init__(self, settings: Any = None, accessibility: Any = None) -> None:
        """Initialize the theme manager.

        Args:
            settings: Optional SettingsManager for persisting theme preferences.
            accessibility: Optional AccessibilityManager for adaptive theming.
        """
        super().__init__()
        self._settings = settings
        self._accessibility = accessibility
        self._current_theme: str = "dark"
        self._themes: dict[str, Callable[[], str]] = {
            "dark": self._generate_dark_stylesheet,
            "light": self._generate_light_stylesheet,
            "high_contrast": self._generate_high_contrast_stylesheet,
        }

        saved = self._get_setting("theme/current", "dark")
        if saved in self._themes:
            self._current_theme = saved

    def _get_setting(self, key: str, default: Any) -> Any:
        """Retrieve a setting from the settings manager.

        Args:
            key: The setting key.
            default: Fallback value.

        Returns:
            The stored value or the default.
        """
        if self._settings is not None and hasattr(self._settings, "get"):
            try:
                return self._settings.get(key, default)
            except Exception:
                return default
        return default

    def _set_setting(self, key: str, value: Any) -> None:
        """Persist a setting through the settings manager.

        Args:
            key: The setting key.
            value: The value to store.
        """
        if self._settings is not None and hasattr(self._settings, "set"):
            with contextlib.suppress(Exception):
                self._settings.set(key, value)

    def get_available_themes(self) -> list[str]:
        """Return a list of all registered theme names.

        Returns:
            A list of theme name strings.
        """
        return list(self._themes.keys())

    def get_current_theme(self) -> str:
        """Return the name of the currently active theme.

        Returns:
            The current theme name.
        """
        return self._current_theme

    def set_theme(self, name: str) -> None:
        """Apply a theme by name, persist the choice, and emit a signal.

        Args:
            name: The theme name to apply.

        Raises:
            ValueError: If the theme name is not registered.
        """
        if name not in self._themes:
            raise ValueError(
                f"Unknown theme '{name}'. Available themes: {sorted(self._themes.keys())}"
            )
        self._current_theme = name
        self._set_setting("theme/current", name)
        self.theme_changed.emit(name)

    def get_stylesheet(self, name: str | None = None) -> str:
        """Generate the stylesheet for a given theme or the current theme.

        Args:
            name: Theme name, or None for the current theme.

        Returns:
            A complete Qt stylesheet string.

        Raises:
            ValueError: If the specified theme name is not registered.
        """
        theme_name = name if name is not None else self._current_theme
        if theme_name not in self._themes:
            raise ValueError(f"Unknown theme '{theme_name}'.")

        generator = self._themes[theme_name]
        base = self._generate_base_stylesheet()
        theme_specific = generator()
        return base + "\n" + theme_specific

    def register_theme(self, name: str, generator: Callable[[], str]) -> None:
        """Register a custom theme with a stylesheet generator function.

        Args:
            name: The theme name. Overwrites if it already exists.
            generator: A callable that returns a Qt stylesheet string.
        """
        self._themes[name] = generator

    def get_theme_info(self, name: str) -> dict[str, str]:
        """Return metadata about a theme.

        Args:
            name: The theme name.

        Returns:
            A dict with keys: name, description, author, version.

        Raises:
            ValueError: If the theme name is not registered.
        """
        if name not in self._themes:
            raise ValueError(f"Unknown theme '{name}'.")

        info = self._THEME_INFO.get(name, {})
        return {
            "name": info.get("name", name),
            "description": info.get("description", ""),
            "author": info.get("author", ""),
            "version": info.get("version", ""),
        }

    def apply_to_application(self, app: Any) -> None:
        """Apply the current theme stylesheet to the QApplication instance.

        Args:
            app: The QApplication instance.
        """
        if app is None:
            return
        stylesheet = self.get_stylesheet()
        app.setStyleSheet(stylesheet)

    def _generate_base_stylesheet(self) -> str:
        """Generate common base stylesheet shared by all themes.

        Returns:
            A Qt stylesheet string with shared widget styling.
        """
        return """
            QMainWindow {
                spacing: 0;
            }

            QWidget {
                font-family: "Segoe UI", "Ubuntu", "Helvetica Neue", Arial, sans-serif;
            }

            QToolTip {
                padding: 6px;
                border-radius: 3px;
                font-size: 12px;
            }

            QSplitter::handle {
                width: 3px;
                height: 3px;
            }

            QStatusBar {
                font-size: 11px;
                padding: 2px 8px;
            }

            QMenuBar {
                padding: 2px 4px;
            }

            QToolBar {
                spacing: 4px;
                padding: 2px;
                border: none;
            }

            QDockWidget {
                titlebar-close-icon: none;
                titlebar-normal-icon: none;
            }

            QDockWidget::title {
                padding: 6px 8px;
                text-align: center;
            }
        """

    def _generate_dark_stylesheet(self) -> str:
        """Generate the dark theme QSS stylesheet.

        Colors: bg #1e1e1e, surface #2d2d2d, text #ffffff, accent #0078D4.

        Returns:
            A comprehensive Qt stylesheet string for the dark theme.
        """
        return """
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }

            QPushButton {
                background-color: #0078D4;
                color: #ffffff;
                border: 1px solid #005a9e;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 13px;
                min-height: 20px;
            }

            QPushButton:hover {
                background-color: #1a8ae8;
                border: 1px solid #0078D4;
            }

            QPushButton:pressed {
                background-color: #005a9e;
            }

            QPushButton:disabled {
                background-color: #3d3d3d;
                color: #888888;
                border: 1px solid #404040;
            }

            QToolButton {
                background-color: transparent;
                color: #ffffff;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px;
            }

            QToolButton:hover {
                background-color: #3d3d3d;
                border: 1px solid #555555;
            }

            QToolButton:pressed {
                background-color: #0078D4;
            }

            QToolButton:disabled {
                color: #666666;
            }

            QLineEdit {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
                selection-background-color: #0078D4;
            }

            QLineEdit:focus {
                border: 1px solid #0078D4;
            }

            QLineEdit:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }

            QTextEdit {
                background-color: #252525;
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 4px;
                font-size: 13px;
            }

            QTextEdit:focus {
                border: 1px solid #0078D4;
            }

            QTreeView {
                background-color: #252525;
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 2px;
                outline: none;
                font-size: 13px;
            }

            QTreeView::item {
                padding: 4px 8px;
                border-radius: 2px;
            }

            QTreeView::item:selected {
                background-color: #0078D4;
                color: #ffffff;
            }

            QTreeView::item:hover {
                background-color: #333333;
            }

            QTreeView::branch {
                background-color: #252525;
            }

            QTreeView::branch:has-children:closed {
                border-image: none;
            }

            QTreeView::branch:has-children:open {
                border-image: none;
            }

            QTableView {
                background-color: #252525;
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 4px;
                gridline-color: #404040;
                selection-background-color: #0078D4;
                font-size: 13px;
            }

            QTableView::item {
                padding: 4px;
            }

            QTableView::item:selected {
                background-color: #0078D4;
                color: #ffffff;
            }

            QTableView::item:hover {
                background-color: #333333;
            }

            QTableView::horizontalHeader {
                background-color: #2d2d2d;
                border: none;
                border-bottom: 1px solid #404040;
            }

            QTableView::horizontalHeader::section {
                background-color: #2d2d2d;
                color: #cccccc;
                border: none;
                border-right: 1px solid #404040;
                padding: 6px 8px;
                font-weight: bold;
            }

            QTableView::verticalHeader {
                background-color: #2d2d2d;
                border: none;
                border-bottom: 1px solid #404040;
            }

            QTableView::verticalHeader::section {
                background-color: #2d2d2d;
                color: #cccccc;
                border: none;
                border-bottom: 1px solid #404040;
                padding: 4px 8px;
            }

            QComboBox {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
                min-height: 20px;
            }

            QComboBox:hover {
                border: 1px solid #0078D4;
            }

            QComboBox:on {
                background-color: #0078D4;
            }

            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 24px;
                border: none;
            }

            QComboBox::down-arrow {
                width: 10px;
                height: 10px;
            }

            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #555555;
                selection-background-color: #0078D4;
                padding: 4px;
            }

            QTabWidget::pane {
                border: 1px solid #404040;
                border-radius: 4px;
                background-color: #252525;
            }

            QTabBar {
                background-color: #1e1e1e;
            }

            QTabBar::tab {
                background-color: #2d2d2d;
                color: #cccccc;
                border: 1px solid #404040;
                border-bottom: none;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 13px;
            }

            QTabBar::tab:selected {
                background-color: #252525;
                color: #ffffff;
                border-bottom: 2px solid #0078D4;
            }

            QTabBar::tab:hover:!selected {
                background-color: #3d3d3d;
            }

            QTabBar::tab:disabled {
                color: #666666;
            }

            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 12px;
                margin: 0;
                border: none;
            }

            QScrollBar::handle:vertical {
                background-color: #555555;
                min-height: 30px;
                border-radius: 6px;
                margin: 2px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #777777;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                background: none;
                border: none;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                background-color: #1e1e1e;
                height: 12px;
                margin: 0;
                border: none;
            }

            QScrollBar::handle:horizontal {
                background-color: #555555;
                min-width: 30px;
                border-radius: 6px;
                margin: 2px;
            }

            QScrollBar::handle:horizontal:hover {
                background-color: #777777;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0;
                background: none;
                border: none;
            }

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: none;
            }

            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background-color: #404040;
                border-radius: 2px;
            }

            QSlider::handle:horizontal {
                background-color: #0078D4;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }

            QSlider::handle:horizontal:hover {
                background-color: #1a8ae8;
            }

            QSlider::groove:vertical {
                border: none;
                width: 4px;
                background-color: #404040;
                border-radius: 2px;
            }

            QSlider::handle:vertical {
                background-color: #0078D4;
                width: 16px;
                height: 16px;
                margin: 0 -6px;
                border-radius: 8px;
            }

            QSlider::handle:vertical:hover {
                background-color: #1a8ae8;
            }

            QProgressBar {
                background-color: #404040;
                border: none;
                border-radius: 4px;
                text-align: center;
                color: #ffffff;
                font-size: 11px;
                min-height: 16px;
            }

            QProgressBar::chunk {
                background-color: #0078D4;
                border-radius: 4px;
            }

            QGroupBox {
                border: 1px solid #404040;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 16px;
                font-size: 13px;
                font-weight: bold;
                color: #cccccc;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 4px;
            }

            QMenu {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 6px;
                padding: 4px 0;
            }

            QMenu::item {
                padding: 8px 24px;
                border-radius: 2px;
            }

            QMenu::item:selected {
                background-color: #0078D4;
            }

            QMenu::item:disabled {
                color: #666666;
            }

            QMenu::separator {
                height: 1px;
                background-color: #404040;
                margin: 4px 8px;
            }

            QToolBar QToolButton {
                background-color: transparent;
                color: #ffffff;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 6px;
            }

            QToolBar QToolButton:hover {
                background-color: #3d3d3d;
                border: 1px solid #555555;
            }

            QToolBar QToolButton:pressed {
                background-color: #0078D4;
            }

            QDockWidget {
                color: #ffffff;
                titlebar-close-icon: none;
                titlebar-normal-icon: none;
            }

            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 6px 8px;
                border-bottom: 1px solid #404040;
            }

            QLabel {
                color: #ffffff;
                background-color: transparent;
                font-size: 13px;
            }

            QCheckBox {
                color: #ffffff;
                spacing: 8px;
                font-size: 13px;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #555555;
                border-radius: 3px;
                background-color: transparent;
            }

            QCheckBox::indicator:checked {
                background-color: #0078D4;
                border: 2px solid #0078D4;
            }

            QCheckBox::indicator:hover {
                border: 2px solid #0078D4;
            }

            QRadioButton {
                color: #ffffff;
                spacing: 8px;
                font-size: 13px;
            }

            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #555555;
                border-radius: 9px;
                background-color: transparent;
            }

            QRadioButton::indicator:checked {
                background-color: #0078D4;
                border: 2px solid #0078D4;
            }

            QRadioButton::indicator:hover {
                border: 2px solid #0078D4;
            }

            QSpinBox, QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
            }

            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #0078D4;
            }

            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 20px;
                border: none;
                background-color: #404040;
                border-top-right-radius: 4px;
            }

            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                border: none;
                background-color: #404040;
                border-bottom-right-radius: 4px;
            }

            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                width: 8px;
                height: 8px;
            }

            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                width: 8px;
                height: 8px;
            }

            QStatusBar {
                background-color: #2d2d2d;
                color: #cccccc;
                border-top: 1px solid #404040;
                font-size: 11px;
            }

            QMenuBar {
                background-color: #1e1e1e;
                color: #ffffff;
                border-bottom: 1px solid #404040;
            }

            QMenuBar::item {
                padding: 4px 8px;
                border-radius: 2px;
            }

            QMenuBar::item:selected {
                background-color: #3d3d3d;
            }

            QMenu {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 6px;
                padding: 4px 0;
            }

            QMenu::item {
                padding: 8px 24px;
                border-radius: 2px;
            }

            QMenu::item:selected {
                background-color: #0078D4;
            }

            QMenu::item:disabled {
                color: #666666;
            }

            QMenu::separator {
                height: 1px;
                background-color: #404040;
                margin: 4px 8px;
            }
        """

    def _generate_light_stylesheet(self) -> str:
        """Generate the light theme QSS stylesheet.

        Colors: bg #f5f5f5, surface #ffffff, text #1e1e1e, accent #0078D4.

        Returns:
            A comprehensive Qt stylesheet string for the light theme.
        """
        return """
            QMainWindow, QWidget {
                background-color: #f5f5f5;
                color: #1e1e1e;
            }

            QPushButton {
                background-color: #0078D4;
                color: #ffffff;
                border: 1px solid #005a9e;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 13px;
                min-height: 20px;
            }

            QPushButton:hover {
                background-color: #1a8ae8;
                border: 1px solid #0078D4;
            }

            QPushButton:pressed {
                background-color: #005a9e;
            }

            QPushButton:disabled {
                background-color: #e0e0e0;
                color: #999999;
                border: 1px solid #d0d0d0;
            }

            QToolButton {
                background-color: transparent;
                color: #1e1e1e;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px;
            }

            QToolButton:hover {
                background-color: #e8e8e8;
                border: 1px solid #cccccc;
            }

            QToolButton:pressed {
                background-color: #0078D4;
                color: #ffffff;
            }

            QToolButton:disabled {
                color: #aaaaaa;
            }

            QLineEdit {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
                selection-background-color: #0078D4;
            }

            QLineEdit:focus {
                border: 1px solid #0078D4;
            }

            QLineEdit:disabled {
                background-color: #f0f0f0;
                color: #999999;
            }

            QTextEdit {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px;
                font-size: 13px;
            }

            QTextEdit:focus {
                border: 1px solid #0078D4;
            }

            QTreeView {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 2px;
                outline: none;
                font-size: 13px;
            }

            QTreeView::item {
                padding: 4px 8px;
                border-radius: 2px;
            }

            QTreeView::item:selected {
                background-color: #0078D4;
                color: #ffffff;
            }

            QTreeView::item:hover {
                background-color: #e8f0fe;
            }

            QTreeView::branch {
                background-color: #ffffff;
            }

            QTreeView::branch:has-children:closed {
                border-image: none;
            }

            QTreeView::branch:has-children:open {
                border-image: none;
            }

            QTableView {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                border-radius: 4px;
                gridline-color: #e0e0e0;
                selection-background-color: #0078D4;
                font-size: 13px;
            }

            QTableView::item {
                padding: 4px;
            }

            QTableView::item:selected {
                background-color: #0078D4;
                color: #ffffff;
            }

            QTableView::item:hover {
                background-color: #e8f0fe;
            }

            QTableView::horizontalHeader {
                background-color: #f0f0f0;
                border: none;
                border-bottom: 1px solid #cccccc;
            }

            QTableView::horizontalHeader::section {
                background-color: #f0f0f0;
                color: #555555;
                border: none;
                border-right: 1px solid #cccccc;
                padding: 6px 8px;
                font-weight: bold;
            }

            QTableView::verticalHeader {
                background-color: #f0f0f0;
                border: none;
                border-right: 1px solid #cccccc;
            }

            QTableView::verticalHeader::section {
                background-color: #f0f0f0;
                color: #555555;
                border: none;
                border-bottom: 1px solid #e0e0e0;
                padding: 4px 8px;
            }

            QComboBox {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
                min-height: 20px;
            }

            QComboBox:hover {
                border: 1px solid #0078D4;
            }

            QComboBox:on {
                background-color: #0078D4;
                color: #ffffff;
            }

            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 24px;
                border: none;
            }

            QComboBox::down-arrow {
                width: 10px;
                height: 10px;
            }

            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                selection-background-color: #0078D4;
                padding: 4px;
            }

            QTabWidget::pane {
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: #ffffff;
            }

            QTabBar {
                background-color: #f5f5f5;
            }

            QTabBar::tab {
                background-color: #e8e8e8;
                color: #555555;
                border: 1px solid #cccccc;
                border-bottom: none;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 13px;
            }

            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #1e1e1e;
                border-bottom: 2px solid #0078D4;
            }

            QTabBar::tab:hover:!selected {
                background-color: #d8d8d8;
            }

            QTabBar::tab:disabled {
                color: #bbbbbb;
            }

            QScrollBar:vertical {
                background-color: #f5f5f5;
                width: 12px;
                margin: 0;
                border: none;
            }

            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                min-height: 30px;
                border-radius: 6px;
                margin: 2px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                background: none;
                border: none;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                background-color: #f5f5f5;
                height: 12px;
                margin: 0;
                border: none;
            }

            QScrollBar::handle:horizontal {
                background-color: #c0c0c0;
                min-width: 30px;
                border-radius: 6px;
                margin: 2px;
            }

            QScrollBar::handle:horizontal:hover {
                background-color: #a0a0a0;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0;
                background: none;
                border: none;
            }

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: none;
            }

            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background-color: #d0d0d0;
                border-radius: 2px;
            }

            QSlider::handle:horizontal {
                background-color: #0078D4;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }

            QSlider::handle:horizontal:hover {
                background-color: #1a8ae8;
            }

            QSlider::groove:vertical {
                border: none;
                width: 4px;
                background-color: #d0d0d0;
                border-radius: 2px;
            }

            QSlider::handle:vertical {
                background-color: #0078D4;
                width: 16px;
                height: 16px;
                margin: 0 -6px;
                border-radius: 8px;
            }

            QSlider::handle:vertical:hover {
                background-color: #1a8ae8;
            }

            QProgressBar {
                background-color: #e0e0e0;
                border: none;
                border-radius: 4px;
                text-align: center;
                color: #1e1e1e;
                font-size: 11px;
                min-height: 16px;
            }

            QProgressBar::chunk {
                background-color: #0078D4;
                border-radius: 4px;
            }

            QGroupBox {
                border: 1px solid #cccccc;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 16px;
                font-size: 13px;
                font-weight: bold;
                color: #333333;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 4px;
            }

            QMenu {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                border-radius: 6px;
                padding: 4px 0;
            }

            QMenu::item {
                padding: 8px 24px;
                border-radius: 2px;
            }

            QMenu::item:selected {
                background-color: #0078D4;
                color: #ffffff;
            }

            QMenu::item:disabled {
                color: #aaaaaa;
            }

            QMenu::separator {
                height: 1px;
                background-color: #e0e0e0;
                margin: 4px 8px;
            }

            QToolBar QToolButton {
                background-color: transparent;
                color: #1e1e1e;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 6px;
            }

            QToolBar QToolButton:hover {
                background-color: #e8e8e8;
                border: 1px solid #cccccc;
            }

            QToolBar QToolButton:pressed {
                background-color: #0078D4;
                color: #ffffff;
            }

            QDockWidget {
                color: #1e1e1e;
                titlebar-close-icon: none;
                titlebar-normal-icon: none;
            }

            QDockWidget::title {
                background-color: #f0f0f0;
                padding: 6px 8px;
                border-bottom: 1px solid #cccccc;
            }

            QLabel {
                color: #1e1e1e;
                background-color: transparent;
                font-size: 13px;
            }

            QCheckBox {
                color: #1e1e1e;
                spacing: 8px;
                font-size: 13px;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #cccccc;
                border-radius: 3px;
                background-color: #ffffff;
            }

            QCheckBox::indicator:checked {
                background-color: #0078D4;
                border: 2px solid #0078D4;
            }

            QCheckBox::indicator:hover {
                border: 2px solid #0078D4;
            }

            QRadioButton {
                color: #1e1e1e;
                spacing: 8px;
                font-size: 13px;
            }

            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #cccccc;
                border-radius: 9px;
                background-color: #ffffff;
            }

            QRadioButton::indicator:checked {
                background-color: #0078D4;
                border: 2px solid #0078D4;
            }

            QRadioButton::indicator:hover {
                border: 2px solid #0078D4;
            }

            QSpinBox, QDoubleSpinBox {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
            }

            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #0078D4;
            }

            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 20px;
                border: none;
                background-color: #f0f0f0;
                border-top-right-radius: 4px;
            }

            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                border: none;
                background-color: #f0f0f0;
                border-bottom-right-radius: 4px;
            }

            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                width: 8px;
                height: 8px;
            }

            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                width: 8px;
                height: 8px;
            }

            QStatusBar {
                background-color: #f0f0f0;
                color: #555555;
                border-top: 1px solid #cccccc;
                font-size: 11px;
            }

            QMenuBar {
                background-color: #f5f5f5;
                color: #1e1e1e;
                border-bottom: 1px solid #cccccc;
            }

            QMenuBar::item {
                padding: 4px 8px;
                border-radius: 2px;
            }

            QMenuBar::item:selected {
                background-color: #e8e8e8;
            }

            QMenu {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                border-radius: 6px;
                padding: 4px 0;
            }

            QMenu::item {
                padding: 8px 24px;
                border-radius: 2px;
            }

            QMenu::item:selected {
                background-color: #0078D4;
                color: #ffffff;
            }

            QMenu::item:disabled {
                color: #aaaaaa;
            }

            QMenu::separator {
                height: 1px;
                background-color: #e0e0e0;
                margin: 4px 8px;
            }
        """

    def _generate_high_contrast_stylesheet(self) -> str:
        """Generate the high-contrast theme QSS stylesheet.

        Colors: black background, white text, yellow accents,
        high-contrast borders for maximum accessibility.

        Returns:
            A comprehensive Qt stylesheet string for the high-contrast theme.
        """
        return """
            QMainWindow, QWidget {
                background-color: #000000;
                color: #ffffff;
            }

            QPushButton {
                background-color: #FFFF00;
                color: #000000;
                border: 2px solid #ffffff;
                border-radius: 0px;
                padding: 8px 20px;
                font-size: 14px;
                font-weight: bold;
                min-height: 22px;
            }

            QPushButton:hover {
                background-color: #FFD700;
                border: 2px solid #FFFF00;
            }

            QPushButton:pressed {
                background-color: #FFA500;
            }

            QPushButton:disabled {
                background-color: #333333;
                color: #888888;
                border: 2px solid #666666;
            }

            QToolButton {
                background-color: transparent;
                color: #ffffff;
                border: 2px solid transparent;
                border-radius: 0px;
                padding: 6px;
            }

            QToolButton:hover {
                background-color: #333333;
                border: 2px solid #FFFF00;
            }

            QToolButton:pressed {
                background-color: #FFFF00;
                color: #000000;
            }

            QToolButton:disabled {
                color: #666666;
            }

            QLineEdit {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 2px solid #ffffff;
                border-radius: 0px;
                padding: 8px 10px;
                font-size: 14px;
                selection-background-color: #FFFF00;
                selection-color: #000000;
            }

            QLineEdit:focus {
                border: 3px solid #FFFF00;
            }

            QLineEdit:disabled {
                background-color: #111111;
                color: #666666;
                border: 2px solid #444444;
            }

            QTextEdit {
                background-color: #0a0a0a;
                color: #ffffff;
                border: 2px solid #ffffff;
                border-radius: 0px;
                padding: 6px;
                font-size: 14px;
            }

            QTextEdit:focus {
                border: 3px solid #FFFF00;
            }

            QTreeView {
                background-color: #0a0a0a;
                color: #ffffff;
                border: 2px solid #ffffff;
                border-radius: 0px;
                padding: 4px;
                outline: none;
                font-size: 14px;
            }

            QTreeView::item {
                padding: 6px 10px;
                border-radius: 0px;
            }

            QTreeView::item:selected {
                background-color: #FFFF00;
                color: #000000;
            }

            QTreeView::item:hover {
                background-color: #333333;
            }

            QTreeView::branch {
                background-color: #0a0a0a;
            }

            QTreeView::branch:has-children:closed {
                border-image: none;
            }

            QTreeView::branch:has-children:open {
                border-image: none;
            }

            QTableView {
                background-color: #0a0a0a;
                color: #ffffff;
                border: 2px solid #ffffff;
                border-radius: 0px;
                gridline-color: #555555;
                selection-background-color: #FFFF00;
                selection-color: #000000;
                font-size: 14px;
            }

            QTableView::item {
                padding: 6px;
            }

            QTableView::item:selected {
                background-color: #FFFF00;
                color: #000000;
            }

            QTableView::item:hover {
                background-color: #333333;
            }

            QTableView::horizontalHeader {
                background-color: #1a1a1a;
                border: none;
                border-bottom: 2px solid #ffffff;
            }

            QTableView::horizontalHeader::section {
                background-color: #1a1a1a;
                color: #FFFF00;
                border: none;
                border-right: 2px solid #ffffff;
                padding: 8px 10px;
                font-weight: bold;
                font-size: 14px;
            }

            QTableView::verticalHeader {
                background-color: #1a1a1a;
                border: none;
                border-right: 2px solid #ffffff;
            }

            QTableView::verticalHeader::section {
                background-color: #1a1a1a;
                color: #FFFF00;
                border: none;
                border-bottom: 2px solid #ffffff;
                padding: 6px 10px;
            }

            QComboBox {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 2px solid #ffffff;
                border-radius: 0px;
                padding: 8px 10px;
                font-size: 14px;
                font-weight: bold;
                min-height: 22px;
            }

            QComboBox:hover {
                border: 2px solid #FFFF00;
            }

            QComboBox:on {
                background-color: #FFFF00;
                color: #000000;
            }

            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 28px;
                border: none;
            }

            QComboBox::down-arrow {
                width: 12px;
                height: 12px;
            }

            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 2px solid #ffffff;
                selection-background-color: #FFFF00;
                selection-color: #000000;
                padding: 4px;
            }

            QTabWidget::pane {
                border: 2px solid #ffffff;
                border-radius: 0px;
                background-color: #0a0a0a;
            }

            QTabBar {
                background-color: #000000;
            }

            QTabBar::tab {
                background-color: #1a1a1a;
                color: #cccccc;
                border: 2px solid #ffffff;
                border-bottom: none;
                padding: 10px 20px;
                margin-right: 2px;
                font-size: 14px;
                font-weight: bold;
            }

            QTabBar::tab:selected {
                background-color: #FFFF00;
                color: #000000;
                border-bottom: 3px solid #FFFF00;
            }

            QTabBar::tab:hover:!selected {
                background-color: #333333;
            }

            QTabBar::tab:disabled {
                color: #555555;
            }

            QScrollBar:vertical {
                background-color: #000000;
                width: 16px;
                margin: 0;
                border: none;
            }

            QScrollBar::handle:vertical {
                background-color: #FFFF00;
                min-height: 40px;
                border-radius: 0px;
                margin: 2px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #FFD700;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                background: none;
                border: none;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                background-color: #000000;
                height: 16px;
                margin: 0;
                border: none;
            }

            QScrollBar::handle:horizontal {
                background-color: #FFFF00;
                min-width: 40px;
                border-radius: 0px;
                margin: 2px;
            }

            QScrollBar::handle:horizontal:hover {
                background-color: #FFD700;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0;
                background: none;
                border: none;
            }

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: none;
            }

            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background-color: #555555;
                border-radius: 0px;
            }

            QSlider::handle:horizontal {
                background-color: #FFFF00;
                width: 20px;
                height: 20px;
                margin: -8px 0;
                border-radius: 0px;
                border: 2px solid #ffffff;
            }

            QSlider::handle:horizontal:hover {
                background-color: #FFD700;
            }

            QSlider::groove:vertical {
                border: none;
                width: 6px;
                background-color: #555555;
                border-radius: 0px;
            }

            QSlider::handle:vertical {
                background-color: #FFFF00;
                width: 20px;
                height: 20px;
                margin: 0 -8px;
                border-radius: 0px;
                border: 2px solid #ffffff;
            }

            QSlider::handle:vertical:hover {
                background-color: #FFD700;
            }

            QProgressBar {
                background-color: #333333;
                border: 2px solid #ffffff;
                border-radius: 0px;
                text-align: center;
                color: #000000;
                font-size: 12px;
                font-weight: bold;
                min-height: 20px;
            }

            QProgressBar::chunk {
                background-color: #FFFF00;
                border-radius: 0px;
            }

            QGroupBox {
                border: 2px solid #ffffff;
                border-radius: 0px;
                margin-top: 14px;
                padding-top: 20px;
                font-size: 14px;
                font-weight: bold;
                color: #FFFF00;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0 6px;
            }

            QMenu {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 2px solid #ffffff;
                border-radius: 0px;
                padding: 4px 0;
            }

            QMenu::item {
                padding: 10px 28px;
                border-radius: 0px;
                font-size: 14px;
            }

            QMenu::item:selected {
                background-color: #FFFF00;
                color: #000000;
            }

            QMenu::item:disabled {
                color: #555555;
            }

            QMenu::separator {
                height: 2px;
                background-color: #ffffff;
                margin: 4px 8px;
            }

            QToolBar QToolButton {
                background-color: transparent;
                color: #ffffff;
                border: 2px solid transparent;
                border-radius: 0px;
                padding: 6px 8px;
            }

            QToolBar QToolButton:hover {
                background-color: #333333;
                border: 2px solid #FFFF00;
            }

            QToolBar QToolButton:pressed {
                background-color: #FFFF00;
                color: #000000;
            }

            QDockWidget {
                color: #ffffff;
                titlebar-close-icon: none;
                titlebar-normal-icon: none;
            }

            QDockWidget::title {
                background-color: #1a1a1a;
                padding: 8px 10px;
                border-bottom: 2px solid #ffffff;
            }

            QLabel {
                color: #ffffff;
                background-color: transparent;
                font-size: 14px;
            }

            QCheckBox {
                color: #ffffff;
                spacing: 10px;
                font-size: 14px;
            }

            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border: 2px solid #ffffff;
                border-radius: 0px;
                background-color: #000000;
            }

            QCheckBox::indicator:checked {
                background-color: #FFFF00;
                border: 2px solid #FFFF00;
            }

            QCheckBox::indicator:hover {
                border: 3px solid #FFFF00;
            }

            QRadioButton {
                color: #ffffff;
                spacing: 10px;
                font-size: 14px;
            }

            QRadioButton::indicator {
                width: 20px;
                height: 20px;
                border: 2px solid #ffffff;
                border-radius: 10px;
                background-color: #000000;
            }

            QRadioButton::indicator:checked {
                background-color: #FFFF00;
                border: 2px solid #FFFF00;
            }

            QRadioButton::indicator:hover {
                border: 3px solid #FFFF00;
            }

            QSpinBox, QDoubleSpinBox {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 2px solid #ffffff;
                border-radius: 0px;
                padding: 6px 10px;
                font-size: 14px;
            }

            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 3px solid #FFFF00;
            }

            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 24px;
                border: none;
                background-color: #333333;
            }

            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 24px;
                border: none;
                background-color: #333333;
            }

            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                width: 10px;
                height: 10px;
            }

            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                width: 10px;
                height: 10px;
            }

            QSplitter::handle {
                background-color: #ffffff;
            }

            QSplitter::handle:hover {
                background-color: #FFFF00;
            }

            QStatusBar {
                background-color: #1a1a1a;
                color: #FFFF00;
                border-top: 2px solid #ffffff;
                font-size: 12px;
                font-weight: bold;
            }

            QMenuBar {
                background-color: #000000;
                color: #ffffff;
                border-bottom: 2px solid #ffffff;
            }

            QMenuBar::item {
                padding: 6px 10px;
                border-radius: 0px;
                font-size: 14px;
                font-weight: bold;
            }

            QMenuBar::item:selected {
                background-color: #FFFF00;
                color: #000000;
            }

            QMenu {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 2px solid #ffffff;
                border-radius: 0px;
                padding: 4px 0;
            }

            QMenu::item {
                padding: 10px 28px;
                border-radius: 0px;
                font-size: 14px;
            }

            QMenu::item:selected {
                background-color: #FFFF00;
                color: #000000;
            }

            QMenu::item:disabled {
                color: #555555;
            }

            QMenu::separator {
                height: 2px;
                background-color: #ffffff;
                margin: 4px 8px;
            }
        """
