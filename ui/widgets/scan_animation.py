"""
scan_animation.py — Animated QPainter widgets for the onboarding overlay.

Classes
-------
ScanAnimationWidget   — concentric rings or rotating radar sweep (Screens 1 & 2)
MiniSparklineWidget   — scrolling simulated RTT line chart (Screen 5)
CheckmarkAnimWidget   — circle-expand + checkmark-draw animation (Screen 6)
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from ui.styles import ACCENT, GREEN, WHITE


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
            from PyQt6.QtCore import QRectF
            sweep_c = QColor(col)
            sweep_c.setAlpha(40)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(sweep_c)
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


class MiniSparklineWidget(QWidget):
    """Simulated RTT sparkline that scrolls new data in every 400 ms.

    Used on onboarding Screen 5 to demonstrate continuous monitoring.
    No real network data is required — the values are synthetically generated.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        import random
        rng = random.Random(7)        # deterministic seed → consistent shape on first view
        self._data: list[float] = [rng.uniform(6, 16) for _ in range(22)]
        self._data[6]  = 46           # a latency spike
        self._data[15] = 38           # another spike
        self._rng = random.Random()   # live random for the scrolling tail
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(420)
        self.setMinimumSize(280, 68)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._data.pop(0)
        self._data.append(self._rng.uniform(6, 16))
        self.update()

    def paintEvent(self, _e) -> None:
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        col = QColor(ACCENT)
        n = len(self._data)

        mn = min(self._data)
        span = max(max(self._data) - mn, 20)

        pts = []
        for i, v in enumerate(self._data):
            x = int(i * (w - 1) / max(n - 1, 1))
            y = int(h - 6 - (v - mn) / span * (h - 12))
            pts.append((x, y))

        # Filled area under the line
        path = QPainterPath()
        path.moveTo(pts[0][0], h)
        for x, y in pts:
            path.lineTo(x, y)
        path.lineTo(pts[-1][0], h)
        path.closeSubpath()
        fill_c = QColor(col)
        fill_c.setAlpha(28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill_c)
        p.drawPath(path)

        # Line
        line_c = QColor(col)
        line_c.setAlpha(200)
        pen = QPen(line_c)
        pen.setWidthF(2.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(len(pts) - 1):
            p.drawLine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])

        p.end()


class CheckmarkAnimWidget(QWidget):
    """Animated green circle + white checkmark for the onboarding done screen.

    Two-phase animation driven by a 16 ms QTimer (~60 fps):
      Phase 1 — green circle expands from 0 to full radius (ease-out cubic)
      Phase 2 — white checkmark stroke draws in progressively

    Call ``start_anim()`` when the widget becomes visible.
    ``animation_done`` is emitted when the checkmark is fully drawn.
    """

    animation_done = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._circle_progress = 0.0
        self._check_progress  = 0.0
        self._phase = 0           # 0=idle, 1=circle, 2=check, 3=done
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(88, 88)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def start_anim(self) -> None:
        if self._phase == 0:
            self._phase = 1
            self._timer.start(16)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        if self._phase == 1:
            self._circle_progress = min(1.0, self._circle_progress + 0.05)
            if self._circle_progress >= 1.0:
                self._phase = 2
        elif self._phase == 2:
            self._check_progress = min(1.0, self._check_progress + 0.055)
            if self._check_progress >= 1.0:
                self._phase = 3
                self._timer.stop()
                self.animation_done.emit()
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width()  / 2
        cy = self.height() / 2
        r  = min(self.width(), self.height()) / 2 - 4

        # Circle — ease-out cubic
        t = self._circle_progress
        t_e = 1.0 - (1.0 - t) ** 3
        actual_r = r * t_e

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(GREEN))
        p.drawEllipse(
            int(cx - actual_r), int(cy - actual_r),
            int(actual_r * 2),  int(actual_r * 2),
        )

        # Checkmark — draws from left to right in two segments
        if self._check_progress > 0:
            pen = QPen(QColor(WHITE))
            pen.setWidthF(4.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)

            s   = r * 0.52
            pt1 = (cx - s * 0.62, cy + s * 0.02)
            pt2 = (cx - s * 0.06, cy + s * 0.56)
            pt3 = (cx + s * 0.65, cy - s * 0.52)

            d1    = math.hypot(pt2[0] - pt1[0], pt2[1] - pt1[1])
            d2    = math.hypot(pt3[0] - pt2[0], pt3[1] - pt2[1])
            total = d1 + d2
            drawn = self._check_progress * total

            if drawn <= d1:
                t_seg = drawn / d1
                ex = pt1[0] + (pt2[0] - pt1[0]) * t_seg
                ey = pt1[1] + (pt2[1] - pt1[1]) * t_seg
                p.drawLine(int(pt1[0]), int(pt1[1]), int(ex), int(ey))
            else:
                p.drawLine(int(pt1[0]), int(pt1[1]), int(pt2[0]), int(pt2[1]))
                t_seg = (drawn - d1) / d2
                ex = pt2[0] + (pt3[0] - pt2[0]) * t_seg
                ey = pt2[1] + (pt3[1] - pt2[1]) * t_seg
                p.drawLine(int(pt2[0]), int(pt2[1]), int(ex), int(ey))

        p.end()
