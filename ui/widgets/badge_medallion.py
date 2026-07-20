"""
BadgeMedallion — QPainter hexagon+shield medallion for Lab Mode badges.

Paints the hexagon/shield motif (RULE-I2) that modules/lab_badge.py used to
render into a standalone PNG export. Two states — earned (full colour) /
locked (greyed out) — driven by set_earned(). Reads theme tokens live inside
paintEvent (RULE-LINT4) and reconnects to theme_changed so it restyles
correctly on a runtime theme switch — themed_ss() only re-renders QSS
stylesheets and is blind to a paintEvent that reads theme globals directly.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from ui.styles import get_theme_manager

# Data-space geometry, carried over verbatim from the deleted modules/lab_badge.py.
_HEX_CX, _HEX_CY, _HEX_R = 0.0, 0.42, 0.55
_SHIELD_PTS = [(-0.18, 0.68), (0.18, 0.68), (0.2, 0.4), (0.0, 0.14), (-0.2, 0.4)]


def _hexagon_points(cx: float, cy: float, r: float) -> list:
    """Pointy-top hexagon vertices per RULE-I2."""
    return [
        (cx + r * math.sin(math.radians(60 * i)), cy + r * math.cos(math.radians(60 * i)))
        for i in range(6)
    ]


class BadgeMedallion(QWidget):
    """Fixed-size widget that paints the earned/locked hexagon+shield medallion."""

    def __init__(self, size: int = 64, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._earned = False
        self.setFixedSize(size, size)
        get_theme_manager().theme_changed.connect(self._on_theme_changed)

    def set_earned(self, earned: bool) -> None:
        if self._earned != earned:
            self._earned = earned
            self.update()

    def is_earned(self) -> bool:
        return self._earned

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        return QSize(self._size, self._size)

    def _on_theme_changed(self, _name: str) -> None:
        self.update()

    def _to_px(self, pt: tuple, scale: float) -> QPointF:
        x, y = pt
        centre = self._size / 2
        return QPointF(
            centre + (x - _HEX_CX) * scale,
            centre - (y - _HEX_CY) * scale,  # data y-up -> pixel y-down
        )

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        from ui import styles as _s

        if self._earned:
            hex_fill, hex_border, shield_fill = _s.ACCENT, _s.ACCENT_DARK, _s.WHITE
        else:
            hex_fill    = _s.BADGE_OFF_BG
            hex_border  = _s.BADGE_OFF_BORDER
            shield_fill = _s.BADGE_OFF_FG

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        scale = (self._size * 0.42) / _HEX_R
        hexagon = QPolygonF(
            [self._to_px(p, scale) for p in _hexagon_points(_HEX_CX, _HEX_CY, _HEX_R)]
        )
        shield = QPolygonF([self._to_px(p, scale) for p in _SHIELD_PTS])

        pen = QPen(QColor(hex_border))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(QColor(hex_fill))
        painter.drawPolygon(hexagon)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(shield_fill))
        painter.drawPolygon(shield)

        painter.end()
