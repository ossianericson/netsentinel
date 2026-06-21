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

from ui.styles import RADAR_BG, RADAR_GREEN, RADAR_GRID, RADAR_TRAIL


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
        """Stop the animation (does not clear devices — last frame stays visible)."""
        self._tick_timer.stop()

    def add_device(self, ip: str, name: str = "", device_type: str = "") -> None:
        """Add a device dot at the position derived from its IP octets."""
        parts = ip.split(".")
        try:
            third  = int(parts[2]) if len(parts) > 2 else 0
            fourth = int(parts[3]) if len(parts) > 3 else 0
        except ValueError:
            third, fourth = 0, 0

        azimuth = (fourth * 360 / 256 + third * 47) % 360
        ring    = ((third % 4) + 1) / 4          # 0.25 / 0.50 / 0.75 / 1.00

        self._devices.append({
            "ip":        ip,
            "name":      name or ip,
            "type":      device_type,
            "azimuth":   azimuth,
            "ring":      ring,
            "born_tick": self._tick_count,
        })
        self.update()

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
        p.setBrush(QColor(RADAR_BG))
        p.setPen(QPen(QColor(RADAR_GRID), 1))
        p.drawEllipse(
            int(cx - radius), int(cy - radius),
            int(radius * 2),  int(radius * 2),
        )

        # ── Concentric rings + spoke grid ─────────────────────────────────────
        p.setPen(QPen(QColor(RADAR_GRID), 1))
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
            colour = QColor(RADAR_TRAIL)
            colour.setAlpha(alpha)
            p.setPen(QPen(colour, 2))
            rad = math.radians(trail_angle)
            p.drawLine(
                int(cx), int(cy),
                int(cx + radius * math.sin(rad)),
                int(cy - radius * math.cos(rad)),
            )

        # ── Sweep arm ─────────────────────────────────────────────────────────
        p.setPen(QPen(QColor(RADAR_GREEN), 2))
        sweep_rad = math.radians(self._sweep_angle)
        p.drawLine(
            int(cx), int(cy),
            int(cx + radius * math.sin(sweep_rad)),
            int(cy - radius * math.cos(sweep_rad)),
        )

        # ── Device dots ───────────────────────────────────────────────────────
        for dev in self._devices:
            dot_rad  = math.radians(dev["azimuth"])
            dot_r    = radius * dev["ring"]
            dx = cx + dot_r * math.sin(dot_rad)
            dy = cy - dot_r * math.cos(dot_rad)

            age = self._tick_count - dev["born_tick"]
            if age < self._BURST_TICKS:
                # Burst ring fades out over BURST_TICKS frames
                burst_alpha = int(200 * (1 - age / self._BURST_TICKS))
                burst_size  = self._DOT_RADIUS + age * 2
                burst_c = QColor(RADAR_GREEN)
                burst_c.setAlpha(burst_alpha)
                p.setPen(QPen(burst_c, 1))
                p.setBrush(QColor(0, 0, 0, 0))
                p.drawEllipse(
                    int(dx - burst_size), int(dy - burst_size),
                    burst_size * 2, burst_size * 2,
                )

            dot_colour = QColor(RADAR_GREEN)
            p.setBrush(dot_colour)
            p.setPen(QPen(QColor(RADAR_BG), 1))
            p.drawEllipse(
                int(dx - self._DOT_RADIUS), int(dy - self._DOT_RADIUS),
                self._DOT_RADIUS * 2, self._DOT_RADIUS * 2,
            )

        # ── Status text ───────────────────────────────────────────────────────
        p.setPen(QColor(RADAR_GREEN))
        count = len(self._devices)
        txt = f"Scanning…  {count} device{'s' if count != 1 else ''} found"
        p.drawText(
            0, int(cy + radius + 6), w, 20,
            0x0004 | 0x0080,   # AlignHCenter | TextSingleLine (Qt alignment flags)
            txt,
        )

        p.end()
