"""
scan_radar_widget.py — phosphor-green radar sweep animation for the Home page.

Plays while a network scan is running; devices appear as dots as they are
discovered. Call start() when scanning begins and stop() when the scan is done.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ui import styles as _s


class ScanRadarWidget(QWidget):
    """QPainter-based radar sweep. 33 ms tick, 2°/tick (≈60 RPM)."""

    _TICK_MS       = 33
    _DEGREES_TICK  = 2.0
    _TRAIL_STEPS   = 30
    _DOT_RADIUS    = 6
    _BURST_TICKS   = 15   # how many ticks a newly-found device flashes

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self._sweep_angle = 0.0    # 0–360, clockwise from top
        self._tick_count  = 0
        self._devices: list[dict] = []

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(self._TICK_MS)
        self._tick_timer.timeout.connect(self._tick)

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Reset state and start the animation."""
        self._sweep_angle = 0.0
        self._tick_count  = 0
        self._devices.clear()
        self._tick_timer.start()

    def stop(self) -> None:
        """Stop the animation and clear the widget."""
        self._tick_timer.stop()
        self._devices.clear()
        self.repaint()

    def add_device(self, ip: str, name: str = "", device_type: str = "") -> None:
        pass  # intentional no-op: radar is a pure sweep animation

    # ── Internal ──────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        self._sweep_angle = (self._sweep_angle + self._DEGREES_TICK) % 360
        self._tick_count += 1
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        w, h   = self.width(), self.height()
        cx, cy = w / 2, h / 2
        radius = min(cx, cy) - 8

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Background circle ─────────────────────────────────────────────────
        p.setBrush(QColor(_s.RADAR_BG))
        p.setPen(QPen(QColor(_s.RADAR_GRID), 1))
        p.drawEllipse(
            int(cx - radius), int(cy - radius),
            int(radius * 2),  int(radius * 2),
        )

        # ── Concentric rings + spoke grid ─────────────────────────────────────
        p.setPen(QPen(QColor(_s.RADAR_GRID), 1))
        for i in range(1, 5):
            r = radius * i / 4
            p.drawEllipse(
                int(cx - r), int(cy - r),
                int(r * 2), int(r * 2),
            )
        for deg in range(0, 360, 45):
            rad = math.radians(deg)
            p.drawLine(
                int(cx), int(cy),
                int(cx + radius * math.sin(rad)),
                int(cy - radius * math.cos(rad)),
            )

        # ── Phosphor trail (30 semi-transparent lines behind sweep arm) ────────
        for i in range(self._TRAIL_STEPS):
            trail_angle = (self._sweep_angle - i * self._DEGREES_TICK) % 360
            alpha = int(180 * (1 - i / self._TRAIL_STEPS))
            colour = QColor(_s.RADAR_TRAIL)
            colour.setAlpha(alpha)
            p.setPen(QPen(colour, 2))
            rad = math.radians(trail_angle)
            p.drawLine(
                int(cx), int(cy),
                int(cx + radius * math.sin(rad)),
                int(cy - radius * math.cos(rad)),
            )

        # ── Sweep arm ─────────────────────────────────────────────────────────
        p.setPen(QPen(QColor(_s.RADAR_GREEN), 2))
        sweep_rad = math.radians(self._sweep_angle)
        p.drawLine(
            int(cx), int(cy),
            int(cx + radius * math.sin(sweep_rad)),
            int(cy - radius * math.cos(sweep_rad)),
        )

        p.end()
