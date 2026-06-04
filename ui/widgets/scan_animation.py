"""
scan_animation.py — Animated QPainter concentric rings / radar sweep widget.

Used in OnboardingOverlay:
  Screen 1 (Permission to scan): concentric rings pulsing outward
  Screen 2 (Scanning in progress): rotating radar arc
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ui.styles import ACCENT


class ScanAnimationWidget(QWidget):
    """Animated concentric rings or rotating radar arc."""

    def __init__(self, mode: str = "rings", parent=None):
        """
        mode: "rings"  — pulsing concentric circles (Screen 1 Permission)
              "radar"  — rotating sweep arc (Screen 2 Scanning)
        """
        super().__init__(parent)
        self._mode  = mode
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)   # 25 fps
        self.setMinimumSize(120, 120)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._frame += 1
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx  = self.width()  / 2
        cy  = self.height() / 2
        r   = min(self.width(), self.height()) / 2 - 4
        col = QColor(ACCENT)

        if self._mode == "rings":
            num = 3
            for i in range(num):
                phase = (self._frame / 50.0 + i / num) % 1.0
                radius = r * phase
                alpha  = int(200 * (1.0 - phase))
                c = QColor(col)
                c.setAlpha(alpha)
                pen = QPen(c)
                pen.setWidthF(2.5)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(
                    int(cx - radius), int(cy - radius),
                    int(radius * 2),  int(radius * 2),
                )
            # Static filled centre dot
            dot_c = QColor(col)
            dot_c.setAlpha(200)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dot_c)
            p.drawEllipse(int(cx - 9), int(cy - 9), 18, 18)

        elif self._mode == "radar":
            angle_deg = (self._frame * 3) % 360

            # Sweep fill (trailing arc)
            sweep_c = QColor(col)
            sweep_c.setAlpha(40)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(sweep_c)
            from PyQt6.QtCore import QRectF
            rect = QRectF(cx - r, cy - r, r * 2, r * 2)
            p.drawPie(rect, int((90 - angle_deg) * 16), -90 * 16)

            # Outer ring
            ring_c = QColor(col)
            ring_c.setAlpha(100)
            pen = QPen(ring_c)
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

            # Sweep line
            rad  = math.radians(90 - angle_deg)
            x2   = cx + r * math.cos(rad)
            y2   = cy - r * math.sin(rad)
            line_c = QColor(col)
            line_c.setAlpha(210)
            pen = QPen(line_c)
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(int(cx), int(cy), int(x2), int(y2))

        p.end()
