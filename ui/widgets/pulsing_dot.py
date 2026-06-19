"""PulsingDot — status indicator widget with a one-shot scale pulse (ANIM-1)."""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, pyqtProperty
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from ui.styles import STATUS_OFFLINE


class PulsingDot(QWidget):
    """12×12 coloured circle. Call set_status() to change colour and trigger a pulse."""

    _BASE_RADIUS = 4.0
    _PULSE_RADIUS = 6.5

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._radius: float = self._BASE_RADIUS
        self._color: QColor = QColor(STATUS_OFFLINE)
        self._anim = QPropertyAnimation(self, b"dot_radius", self)
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── Animated property ─────────────────────────────────────────────────────

    def _get_radius(self) -> float:
        return self._radius

    def _set_radius(self, r: float) -> None:
        self._radius = r
        self.update()

    dot_radius = pyqtProperty(float, _get_radius, _set_radius)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        r = self._radius
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    # ── Public API ────────────────────────────────────────────────────────────

    def set_status(self, color: QColor, animate: bool = True) -> None:
        """Change dot colour; play a single scale-pulse when animate=True."""
        from ui.theme import _reduce_motion
        self._color = color
        if animate and not _reduce_motion():
            self._anim.stop()
            self._anim.setStartValue(self._PULSE_RADIUS)
            self._anim.setEndValue(self._BASE_RADIUS)
            self._anim.start()
        else:
            self._radius = self._BASE_RADIUS
            self.update()
