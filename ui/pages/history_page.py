"""
HistoryPage — persistent time-series graphs page (T1#5).

Displays RTT history, device availability, and state-change events read from
MetricStore. Zoom controls: 1h / 12h / 24h / 7d.

Architecture rules observed:
  • This file imports PyQt6 and ui/styles — it is a UI page.
  • It does NOT import workers/ or start threads.
  • MetricStore is injected as a constructor parameter.
  • All colours come from ui/styles — no hardcoded hex values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

import matplotlib
matplotlib.use("QtAgg")  # must be set before figure imports
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, BG_CARD, BG_DARK, BORDER, GREEN, AMBER, RED,
    CHART_GRID, CHART_PLOT_BG, CHART_PURPLE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TH_BG,
)

if TYPE_CHECKING:
    from modules.metric_store import MetricStore


# ── Chart style helpers ───────────────────────────────────────────────────────

_SERIES_COLORS = [ACCENT, GREEN, AMBER, TEXT_SECONDARY, RED, CHART_PURPLE]
_STATE_COLORS  = {"UP": GREEN, "DEGRADED": AMBER, "DOWN": RED}


def _style_ax(ax, title: str) -> None:
    ax.set_facecolor(CHART_PLOT_BG)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color(BORDER)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
    ax.set_title(title, color=TH_BG, fontsize=10, fontweight="bold", pad=6)
    ax.grid(True, color=CHART_GRID, linewidth=0.7, axis="y")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))


# ── KPI tile ─────────────────────────────────────────────────────────────────

class _KpiTile(QFrame):
    """Small stat card: coloured left border, micro-label + large number."""

    def __init__(self, label: str, value: str = "—", accent: str = ACCENT, parent=None):
        super().__init__(parent)
        self.setObjectName("kpiTile")
        self.setStyleSheet(
            f"QFrame#kpiTile {{"
            f"  background:{BG_CARD}; border:1px solid {BORDER};"
            f"  border-left:3px solid {accent};"
            f"  min-width:110px; max-width:200px;"
            f"}}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)

        self._lbl = QLabel(label.upper())
        self._lbl.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{TEXT_SECONDARY};"
            f"background:transparent; border:none;"
        )
        self._val = QLabel(value)
        self._val.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY};"
            f"background:transparent; border:none;"
        )
        layout.addWidget(self._lbl)
        layout.addWidget(self._val)

    def set_value(self, v: str) -> None:
        self._val.setText(v)


# ── Chart card ────────────────────────────────────────────────────────────────

class _ChartCard(QFrame):
    """White card wrapping a matplotlib figure."""

    def __init__(self, title: str, height: int = 220, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:0px; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Card title bar
        hdr = QWidget()
        hdr.setFixedHeight(32)
        hdr.setStyleSheet(
            f"background:{BG_CARD}; border-bottom:1px solid #ECECEC;"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
            f"background:transparent; border:none;"
        )
        hl.addWidget(lbl)
        outer.addWidget(hdr)

        # Figure
        self._fig = Figure(figsize=(8, height / 96), dpi=96, facecolor=BG_CARD)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._canvas.setFixedHeight(height)
        outer.addWidget(self._canvas)

    @property
    def ax(self):
        return self._ax

    @property
    def fig(self):
        return self._fig

    @property
    def canvas(self):
        return self._canvas


# ── Main page ────────────────────────────────────────────────────────────────

_WINDOWS = {
    "1h":  1,
    "12h": 12,
    "24h": 24,
    "7d":  168,
}


class HistoryPage(QWidget):
    """
    Full-page persistent history view.

    Parameters
    ----------
    store : MetricStore | None
        Injected from app.py. If None the page shows a "no data store" placeholder.
    parent : QWidget | None
    """

    REFRESH_MS = 30_000   # re-query every 30 s

    def __init__(self, store: "Optional[MetricStore]" = None, parent=None):
        super().__init__(parent)
        self._store = store
        self._window_h = 1     # hours currently displayed
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(self.REFRESH_MS)
        self._auto_timer.timeout.connect(self._refresh)

        self._build_ui()

        if store:
            self._refresh()
            self._auto_timer.start()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # ── Page title row ────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_lbl = QLabel("Availability History")
        title_lbl.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY};"
        )
        sub_lbl = QLabel("Persistent RTT & device state from local SQLite database")
        sub_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        left_col = QVBoxLayout()
        left_col.setSpacing(0)
        left_col.addWidget(title_lbl)
        left_col.addWidget(sub_lbl)
        title_row.addLayout(left_col)
        title_row.addStretch()

        # Zoom buttons
        self._zoom_btns: dict[str, QPushButton] = {}
        for label in _WINDOWS:
            btn = QPushButton(label)
            btn.setFixedSize(40, 26)
            btn.setCheckable(True)
            btn.setStyleSheet(self._zoom_btn_style(False))
            btn.clicked.connect(lambda checked, l=label: self._set_window(l))
            self._zoom_btns[label] = btn
            title_row.addWidget(btn)

        # Host selector
        self._host_combo = QComboBox()
        self._host_combo.setFixedWidth(160)
        self._host_combo.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:{BG_CARD};"
            f"border:1px solid {BORDER}; padding:2px 6px;"
        )
        self._host_combo.currentTextChanged.connect(self._on_host_changed)
        title_row.addWidget(QLabel("Host:"))
        title_row.addWidget(self._host_combo)

        # Refresh button
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setFixedHeight(26)
        refresh_btn.setStyleSheet(
            f"QPushButton {{ font-size:11px; color:{ACCENT};"
            f" background:{BG_CARD}; border:1px solid {ACCENT}; border-radius:3px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:#EEF4FF; }}"
        )
        refresh_btn.clicked.connect(self._refresh)
        title_row.addWidget(refresh_btn)
        root.addLayout(title_row)

        # ── KPI row ───────────────────────────────────────────────────────────
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_uptime  = _KpiTile("Uptime",    "—", GREEN)
        self._kpi_avg_rtt = _KpiTile("Avg RTT",   "—", ACCENT)
        self._kpi_min_rtt = _KpiTile("Min RTT",   "—", GREEN)
        self._kpi_max_rtt = _KpiTile("Max RTT",   "—", RED)
        self._kpi_hosts   = _KpiTile("Hosts Monitored", "—", ACCENT)
        for tile in (self._kpi_uptime, self._kpi_avg_rtt, self._kpi_min_rtt,
                     self._kpi_max_rtt, self._kpi_hosts):
            kpi_row.addWidget(tile)
        kpi_row.addStretch()
        root.addLayout(kpi_row)

        # ── Scrollable chart area ─────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background:{BG_DARK}; border:none;")
        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        self._charts_layout = QVBoxLayout(inner)
        self._charts_layout.setContentsMargins(0, 0, 0, 0)
        self._charts_layout.setSpacing(10)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # Chart cards (created once, redrawn on refresh)
        self._rtt_card  = _ChartCard("RTT History (ms)",       height=220)
        self._avail_card = _ChartCard("Device Availability",   height=160)
        self._charts_layout.addWidget(self._rtt_card)
        self._charts_layout.addWidget(self._avail_card)
        self._charts_layout.addStretch()

        # Set initial zoom button state
        self._set_window("1h")

        # No-store placeholder
        if not self._store:
            for card in (self._rtt_card, self._avail_card):
                card.ax.text(
                    0.5, 0.5, "No data store connected",
                    ha="center", va="center",
                    color=TEXT_SECONDARY, fontsize=11,
                    transform=card.ax.transAxes,
                )
                card.canvas.draw_idle()

    # ── Window / host selection ───────────────────────────────────────────────

    def _set_window(self, label: str) -> None:
        self._window_h = _WINDOWS[label]
        for lbl, btn in self._zoom_btns.items():
            active = lbl == label
            btn.setChecked(active)
            btn.setStyleSheet(self._zoom_btn_style(active))
        self._refresh()

    @staticmethod
    def _zoom_btn_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ font-size:11px; background:{ACCENT}; color:#FFFFFF;"
                f" border:1px solid {ACCENT}; border-radius:3px; }}"
            )
        return (
            f"QPushButton {{ font-size:11px; background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid #B0C4D8; border-radius:3px; }}"
            f"QPushButton:hover {{ background:#EEF4FF; }}"
        )

    def _on_host_changed(self, host: str) -> None:
        self._refresh()

    # ── Refresh / draw ────────────────────────────────────────────────────────

    @pyqtSlot()
    def _refresh(self) -> None:
        if not self._store:
            return
        self._populate_host_combo()
        self._draw_rtt()
        self._draw_availability()
        self._update_kpis()

    def _populate_host_combo(self) -> None:
        hosts = self._store.query_all_rtt_hosts(hours=self._window_h)
        current = self._host_combo.currentText()
        self._host_combo.blockSignals(True)
        self._host_combo.clear()
        if hosts:
            self._host_combo.addItem("(all hosts)")
            for h in sorted(hosts):
                self._host_combo.addItem(h)
            idx = self._host_combo.findText(current)
            self._host_combo.setCurrentIndex(max(0, idx))
        self._host_combo.blockSignals(False)

    def _draw_rtt(self) -> None:
        import datetime
        ax = self._rtt_card.ax
        ax.cla()
        _style_ax(ax, "RTT History (ms)")

        if not self._store:
            self._rtt_card.canvas.draw_idle()
            return

        selected = self._host_combo.currentText()
        if selected and selected != "(all hosts)":
            hosts = [selected]
        else:
            hosts = self._store.query_all_rtt_hosts(hours=self._window_h)

        plotted = False
        for i, host in enumerate(hosts[:6]):   # cap at 6 series for readability
            pts = self._store.query_rtt_history(host, hours=self._window_h)
            if not pts:
                continue
            color = _SERIES_COLORS[i % len(_SERIES_COLORS)]
            # Separate successful pings from timeouts
            times_ok  = [datetime.datetime.fromtimestamp(p.ts) for p in pts if p.rtt_ms >= 0]
            rtts_ok   = [p.rtt_ms for p in pts if p.rtt_ms >= 0]
            times_to  = [datetime.datetime.fromtimestamp(p.ts) for p in pts if p.rtt_ms < 0]

            if times_ok:
                ax.plot(times_ok, rtts_ok, color=color, linewidth=1.5,
                        label=host, alpha=0.9)
                ax.fill_between(times_ok, rtts_ok, alpha=0.08, color=color)
                plotted = True
            if times_to:
                ax.scatter(times_to, [0] * len(times_to),
                           color=RED, marker="x", s=30, zorder=5)

        if not plotted:
            ax.text(0.5, 0.5, "No RTT data in this window",
                    ha="center", va="center", color=TEXT_SECONDARY,
                    fontsize=10, transform=ax.transAxes)
        else:
            ax.set_ylabel("RTT (ms)", color=TEXT_SECONDARY, fontsize=9)
            if len(hosts) > 1:
                ax.legend(fontsize=8, framealpha=0.9, loc="upper right")

        self._rtt_card.fig.tight_layout(pad=0.8)
        self._rtt_card.canvas.draw_idle()

    def _draw_availability(self) -> None:
        import datetime
        ax = self._avail_card.ax
        ax.cla()
        _style_ax(ax, "Device Availability")

        if not self._store:
            self._avail_card.canvas.draw_idle()
            return

        selected = self._host_combo.currentText()
        if selected and selected != "(all hosts)":
            ips = [selected]
        else:
            ips = self._store.query_all_rtt_hosts(hours=self._window_h)

        if not ips:
            ax.text(0.5, 0.5, "No availability data in this window",
                    ha="center", va="center", color=TEXT_SECONDARY,
                    fontsize=10, transform=ax.transAxes)
            self._avail_card.canvas.draw_idle()
            return

        ax.set_yticks(range(len(ips)))
        ax.set_yticklabels(ips[::-1], fontsize=8, color=TEXT_PRIMARY)
        ax.set_ylim(-0.5, len(ips) - 0.5)

        for y, ip in enumerate(reversed(ips)):
            hist = self._store.query_device_state_history(ip, hours=self._window_h)
            if not hist:
                continue
            for pt in hist:
                dt = datetime.datetime.fromtimestamp(pt.ts)
                color = _STATE_COLORS.get(pt.state, TEXT_MUTED)
                ax.barh(y, 1 / 60, left=mdates.date2num(dt),
                        height=0.6, color=color, linewidth=0)

        # Legend patches
        import matplotlib.patches as mpatches
        patches = [mpatches.Patch(color=v, label=k) for k, v in _STATE_COLORS.items()]
        ax.legend(handles=patches, fontsize=8, loc="upper right", framealpha=0.9)
        ax.xaxis_date()

        self._avail_card.fig.tight_layout(pad=0.8)
        self._avail_card.canvas.draw_idle()

    def _update_kpis(self) -> None:
        if not self._store:
            return
        selected = self._host_combo.currentText()
        hosts = (
            [selected] if selected and selected != "(all hosts)"
            else self._store.query_all_rtt_hosts(hours=self._window_h)
        )
        self._kpi_hosts.set_value(str(len(hosts)))

        if not hosts:
            for tile in (self._kpi_uptime, self._kpi_avg_rtt,
                         self._kpi_min_rtt, self._kpi_max_rtt):
                tile.set_value("—")
            return

        all_rtts = []
        uptimes  = []
        for host in hosts:
            pts = self._store.query_rtt_history(host, hours=self._window_h)
            ok  = [p.rtt_ms for p in pts if p.rtt_ms >= 0]
            all_rtts.extend(ok)
            uptimes.append(self._store.query_uptime_pct(host, hours=self._window_h))

        avg_uptime = sum(uptimes) / len(uptimes) if uptimes else 100.0
        self._kpi_uptime.set_value(f"{avg_uptime:.1f}%")

        if all_rtts:
            self._kpi_avg_rtt.set_value(f"{sum(all_rtts)/len(all_rtts):.0f} ms")
            self._kpi_min_rtt.set_value(f"{min(all_rtts):.0f} ms")
            self._kpi_max_rtt.set_value(f"{max(all_rtts):.0f} ms")
        else:
            for tile in (self._kpi_avg_rtt, self._kpi_min_rtt, self._kpi_max_rtt):
                tile.set_value("—")

    # ── External API (called by AvailabilityWorker signal) ────────────────────

    @pyqtSlot(dict)
    def on_cycle_done(self, _result: dict) -> None:
        """Slot connected to AvailabilityWorker.cycle_done — triggers a refresh."""
        self._refresh()
