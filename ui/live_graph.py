"""
Live matplotlib graph widget embedded in PyQt6.
Used by Module 5 (DNS / ping correlator) to show real-time latency.
"""

from typing import Dict, List, Optional

import matplotlib
matplotlib.use("QtAgg")  # must be set before importing pyplot

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout

from ui.styles import (
    BG_CARD, ACCENT, ACCENT_LITE, BORDER, RED, GREEN, TEXT_PRIMARY, TEXT_SECONDARY,
    CHART_BG, CHART_PLOT_BG, CHART_GRID, CHART_TITLE,
)

TARGET_COLORS = {
    "1.1.1.1":  "#0078D4",
    "8.8.8.8":  "#2E7D32",
    "gateway":  "#F59E0B",
    "default":  "#5A6A7A",
}


class LiveGraphWidget(QWidget):
    """Embeds a dark-themed matplotlib line graph that updates in real-time."""

    MAX_POINTS = 120   # keep only the last N data points per series

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._series: Dict[str, List] = {}   # target -> list of (t, rtt_ms or None)
        self._fig = Figure(figsize=(8, 3), dpi=96, facecolor=CHART_BG)
        self._ax = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

        self._style_axes()
        self._fig.tight_layout(pad=1.0)

    def _style_axes(self):
        ax = self._ax
        ax.set_facecolor(CHART_PLOT_BG)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
        ax.spines["bottom"].set_color(BORDER)
        ax.spines["left"].set_color(BORDER)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xlabel("Elapsed (s)", color=TEXT_SECONDARY, fontsize=9)
        ax.set_ylabel("RTT (ms)", color=TEXT_SECONDARY, fontsize=9)
        ax.set_title("Ping & DNS Latency — Live", color=CHART_TITLE, fontsize=10, fontweight="bold")
        ax.grid(True, color=CHART_GRID, linewidth=0.8, linestyle="-")

    def add_ping_point(self, timestamp: float, target: str, rtt_ms):
        """rtt_ms is None for timeouts."""
        if target not in self._series:
            self._series[target] = []
        self._series[target].append((timestamp, rtt_ms))
        # Trim
        if len(self._series[target]) > self.MAX_POINTS:
            self._series[target] = self._series[target][-self.MAX_POINTS:]

    def redraw(self):
        """Redraw the chart. Call from UI thread."""
        ax = self._ax
        ax.cla()
        self._style_axes()

        for target, points in self._series.items():
            if not points:
                continue
            times = [p[0] for p in points]
            rtts  = [p[1] if p[1] is not None else 0 for p in points]
            timeouts = [p[0] for p in points if p[1] is None]

            color = TARGET_COLORS.get(target, TARGET_COLORS["default"])
            label = f"{target}" if target != "gateway" else "Gateway"

            ax.plot(times, rtts, color=color, linewidth=1.5, label=label)
            if timeouts:
                ax.scatter(
                    timeouts,
                    [0] * len(timeouts),
                    color=RED,
                    marker="x",
                    s=40,
                    zorder=5,
                    label="Timeout" if "Timeout" not in [l.get_label() for l in ax.lines] else "",
                )

        ax.legend(
            loc="upper right",
            fontsize=8,
            facecolor=BG_CARD,
            edgecolor=BORDER,
            labelcolor=TEXT_PRIMARY,
        )
        self._fig.tight_layout(pad=1.0)
        self._canvas.draw_idle()

    def reset(self):
        self._series.clear()
        self._ax.cla()
        self._style_axes()
        self._canvas.draw_idle()
