"""
SignalBar — QPainter widget showing 5 vertical bars (phone-style signal strength).
Used on Modem and Mesh Router pages for RSRP, RSRQ, SINR, SNR values.

Raw value is shown in a tooltip; bar color reflects quality level.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QWidget

from ui.styles import AMBER, BORDER, GREEN, RED, TEXT_MUTED

# ── Thresholds ────────────────────────────────────────────────────────────────
# List of (min_value_or_None, bars). First match from the top wins.
_THRESHOLDS: dict[str, list] = {
    "rsrp": [(-80, 5), (-90, 4), (-100, 3), (-110, 2), (None, 1)],
    "rsrq": [(-10, 5), (-12, 4), (-14, 3), (-17, 2), (None, 1)],
    "sinr": [(20, 5), (13, 4), (0, 3), (-6, 2), (None, 1)],
    "snr":  [(20, 5), (13, 4), (0, 3), (-6, 2), (None, 1)],
}


def bars_for_metric(metric: str, value: float) -> int:
    """Return 1–5 bars for a given metric name and value."""
    thresholds = _THRESHOLDS.get(metric.lower(), _THRESHOLDS["rsrp"])
    for threshold, bars in thresholds:
        if threshold is None or value >= threshold:
            return bars
    return 1


def color_for_bars(bars: int) -> str:
    if bars >= 4:
        return GREEN
    if bars >= 3:
        return AMBER
    return RED


class SignalBar(QWidget):
    """5-bar phone-style signal-strength indicator widget."""

    def __init__(self, metric: str = "rsrp", parent=None) -> None:
        super().__init__(parent)
        self._metric = metric
        self._bars: int = 0        # 0 = no data; 1–5 = filled bars
        self.setFixedSize(34, 20)
        self.setToolTip("—")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_value(self, value: Optional[float], unit: str = "") -> None:
        if value is None:
            self._bars = 0
            self.setToolTip("—")
        else:
            self._bars = bars_for_metric(self._metric, value)
            suffix = f" {unit}" if unit else ""
            self.setToolTip(f"{value:.1f}{suffix}")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        n = 5
        w = self.width()
        h = self.height()
        bar_w = max(3, (w - (n - 1) * 2) // n)
        gap = 2
        total_w = n * bar_w + (n - 1) * gap
        x0 = (w - total_w) // 2

        active = QColor(color_for_bars(self._bars) if self._bars > 0 else TEXT_MUTED)
        inactive = QColor(BORDER)

        for i in range(n):
            bar_h = max(2, int(h * (i + 1) / n))
            x = x0 + i * (bar_w + gap)
            y = h - bar_h
            rect = QRect(x, y, bar_w, bar_h)
            p.fillRect(rect, active if (self._bars > 0 and i < self._bars) else inactive)

        p.end()
