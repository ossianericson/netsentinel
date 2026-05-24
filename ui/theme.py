"""ui/theme.py — Semantic colour helpers for V6 widget code.

Wraps ui.styles hex strings in QColor so animation/paint code avoids
repeated QColor(hex) construction.  status_color() is the single
entry-point for mapping a device/alert status string to a paint colour.
_reduce_motion() gates all animations so they respect the OS preference.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor

from ui.styles import AMBER, GREEN, RED, TEXT_MUTED


def status_color(status: str) -> QColor:
    """Map a device or alert status string → semantic QColor."""
    s = status.lower()
    if s in ("online", "good", "up", "joined", "recovered"):
        return QColor(GREEN)
    if s in ("offline", "down", "critical"):
        return QColor(RED)
    if s in ("warn", "warning", "degraded", "left"):
        return QColor(AMBER)
    return QColor(TEXT_MUTED)


def _reduce_motion() -> bool:
    """Return True when the user or OS prefers reduced motion."""
    try:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        if hasattr(hints, "isReduceMotionPreferred"):
            return hints.isReduceMotionPreferred()
    except Exception:
        pass
    return QSettings("NetSentinel", "NetSentinel").value(
        "accessibility/reduce_motion", False, type=bool
    )
