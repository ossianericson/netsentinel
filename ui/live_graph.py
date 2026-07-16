"""
Live matplotlib graph widget embedded in PyQt6.
Used by Module 5 (DNS / ping correlator) to show real-time latency.

Theme-live: colour tokens are read from ``ui.styles`` at draw time via the
``_s`` alias, so an Arctic <-> Midnight switch recolours the chart the moment
``refresh_theme()`` runs.  This widget is embedded (not a stack page), so its
host forwards the dashboard's ``theme_changed`` fan-out to it.
"""

from typing import Dict, List, Optional

from PyQt6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout

from ui import styles as _s


def _target_colors() -> Dict[str, str]:
    """Per-target line colours, read live so a theme switch recolours them."""
    return {
        "1.1.1.1":  _s.ACCENT,
        "8.8.8.8":  _s.GREEN,
        "gateway":  _s.AMBER,
        "default":  _s.TEXT_SECONDARY,
    }


class LiveGraphWidget(QWidget):
    """Embeds a themed matplotlib line graph that updates in real-time."""

    MAX_POINTS = 120   # keep only the last N data points per series

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        import matplotlib
        matplotlib.use("QtAgg")
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure

        self._series: Dict[str, List] = {}   # target -> list of (t, rtt_ms or None)
        self._fig = Figure(figsize=(8, 3), dpi=96, facecolor=_s.CHART_BG)
        self._ax = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        _s.themed_ss(self._canvas, "background:{CHART_BG}; border:none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

        self._style_axes()
        # Fixed margins instead of tight_layout. This small 8x3 figure cannot satisfy
        # the tight-layout constraint (title + x/y labels + legend), so that engine
        # re-warns "Tight layout not applied" on every draw_idle(). subplots_adjust is
        # deterministic and silent — the same approach ui/topology_widget.py uses.
        # Figure-level, so it survives ax.cla() in redraw()/reset().
        self._fig.subplots_adjust(left=0.10, right=0.97, top=0.88, bottom=0.17)

    def _style_axes(self):
        ax = self._ax
        ax.set_facecolor(_s.CHART_PLOT_BG)
        ax.tick_params(colors=_s.TEXT_SECONDARY, labelsize=9)
        ax.spines["bottom"].set_color(_s.CHART_SPINE)
        ax.spines["left"].set_color(_s.CHART_SPINE)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xlabel("Elapsed (s)", color=_s.TEXT_SECONDARY, fontsize=9)
        ax.set_ylabel("RTT (ms)", color=_s.TEXT_SECONDARY, fontsize=9)
        ax.set_title("Ping & DNS Latency — Live", color=_s.CHART_TITLE, fontsize=10, fontweight="bold")
        ax.grid(True, color=_s.CHART_GRID, linewidth=0.8, linestyle="-")

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

        colors = _target_colors()
        for target, points in self._series.items():
            if not points:
                continue
            times = [p[0] for p in points]
            rtts  = [p[1] if p[1] is not None else 0 for p in points]
            timeouts = [p[0] for p in points if p[1] is None]

            color = colors.get(target, colors["default"])
            label = f"{target}" if target != "gateway" else "Gateway"

            ax.plot(times, rtts, color=color, linewidth=1.5, label=label)
            if timeouts:
                ax.scatter(
                    timeouts,
                    [0] * len(timeouts),
                    color=_s.RED,
                    marker="x",
                    s=40,
                    zorder=5,
                    label="Timeout" if "Timeout" not in [l.get_label() for l in ax.lines] else "",
                )

        # Only draw a legend when something labelled was actually plotted — calling
        # ax.legend() with no labelled artists warns "No artists with labels found
        # for legend" on every empty redraw (before the first ping arrives).
        if ax.get_legend_handles_labels()[0]:
            ax.legend(
                loc="upper right",
                fontsize=8,
                facecolor=_s.BG_CARD,
                edgecolor=_s.CHART_SPINE,
                labelcolor=_s.TEXT_PRIMARY,
            )
        self._canvas.draw_idle()

    def refresh_theme(self):
        """Restyle the figure after a live theme switch and repaint.

        The canvas widget background re-applies automatically (themed_ss
        registry); this re-reads the matplotlib colour tokens and redraws.
        """
        self._fig.set_facecolor(_s.CHART_BG)
        self.redraw()

    def reset(self):
        self._series.clear()
        self._ax.cla()
        self._style_axes()
        self._canvas.draw_idle()
