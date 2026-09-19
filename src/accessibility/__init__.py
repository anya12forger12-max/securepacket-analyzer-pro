"""Accessibility module for SecurePacket Analyzer Pro."""

from src.accessibility.keyboard import FocusChain, KeyboardNavigation
from src.accessibility.manager import AccessibilityManager
from src.accessibility.shortcuts import ShortcutManager

__all__ = [
    "AccessibilityManager",
    "FocusChain",
    "KeyboardNavigation",
    "ShortcutManager",
]
