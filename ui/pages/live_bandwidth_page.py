"""
ui/pages/live_bandwidth_page.py — Live Interface Bandwidth Monitor
==================================================================
Real-time up/down Mbps chart for all network interfaces.

Layout
------
  Title + subtitle
  KPI row: Up Mbps  | Down Mbps  | Peak Up  | Peak Down
  Interface selector (combo) + Unit toggle (Mbps / KB/s)
  60-second rolling dual area chart (matplotlib, FigureCanvasQTAgg)
  Interface breakdown table: per-NIC totals for this session
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtCore import QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.context_menu import install_copy_menu
from ui.widgets.empty_state_card import EmptyStateCard
from PyQt6.QtGui import QColor

from ui import styles as _s
from ui.styles import (
    ACCENT, AMBER, BG_ALT_ROW, BG_CARD,
    BORDER, CHART_AXIS, CHART_DOWN, CHART_UP, GREEN, RED, TABLE_ROW_BORDER,
    TABLE_SEL, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TH_BG, TH_BORDER, TH_TEXT,
)

_HISTORY_LEN  = 60          # seconds of rolling history
_DOWN_COLOR   = CHART_DOWN  # blue  — download (theme-independent)
_UP_COLOR     = CHART_UP    # green — upload (theme-independent)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _kpi_tile(label: str, color: str = ACCENT) -> tuple[QFrame, QLabel]:
    tile = QFrame()
    tile.setStyleSheet(
        f"background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {color}; border-radius:0;"
    )
    lay = QVBoxLayout(tile)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(2)
    lbl = QLabel(label.upper())
    lbl.setStyleSheet(
        f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
        f" letter-spacing:0.5px; border:none; background:transparent;"
    )
    val = QLabel("—")
    val.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-size:22px; font-weight:bold;"
        f" border:none; background:transparent;"
    )
    lay.addWidget(lbl)
    lay.addWidget(val)
    return tile, val


# ── Main page ─────────────────────────────────────────────────────────────────

class LiveBandwidthPage(QWidget):
    """Real-time bandwidth chart + per-interface breakdown table."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Rolling history per interface: { iface: {"up": deque, "down": deque} }
        self._history: Dict[str, Dict[str, Deque[float]]] = {}
        self._peak_up   = 0.0
        self._peak_down = 0.0
        # Session totals per interface
        self._session: Dict[str, Dict[str, float]] = {}   # up_mb, down_mb

        self._worker = None
        # Event annotation ticks: list of [age_ticks, label, color]
        self._events: List[List] = []
        # ANIM-2: slide animation state
        self._slide_offset = 0.0
        self._slide_timer = QTimer(self)
        self._slide_timer.setInterval(50)   # 4 × 50 ms = 200 ms total
        self._slide_timer.timeout.connect(self._slide_tick)
        self._setup_ui()
        self._start_worker()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header
        from ui.widgets.page_header import PageHeaderBar
        _hdr = PageHeaderBar("Live Bandwidth", subtitle="Shows data transfer speeds for each network interface in real time.")
        _hdr.show_first_visit_banner(
            "live_bandwidth",
            "This chart updates every second. Look for sustained spikes — a short burst "
            "during a video call is normal; an interface pegged at 100% for minutes is not.",
        )
        root.addWidget(_hdr)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_up,    self._lbl_up    = _kpi_tile("↑ Up",       GREEN)
        self._kpi_down,  self._lbl_down  = _kpi_tile("↓ Down",     ACCENT)
        self._kpi_pkup,  self._lbl_pkup  = _kpi_tile("Peak Up",    AMBER)
        self._kpi_pkdn,  self._lbl_pkdn  = _kpi_tile("Peak Down",  RED)
        for t in (self._kpi_up, self._kpi_down, self._kpi_pkup, self._kpi_pkdn):
            kpi_row.addWidget(t, 1)
        root.addLayout(kpi_row)

        # Controls row: interface selector + reset peaks button
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        _lbl = QLabel("Interface:")
        _lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY};"
            f" background:transparent; border:none;"
        )
        self._iface_combo = QComboBox()
        self._iface_combo.setStyleSheet(
            f"QComboBox {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px;"
            f" padding:3px 8px; font-size:11px; min-height:26px; }}"
        )
        self._iface_combo.addItem("All interfaces (sum)")
        self._iface_combo.currentIndexChanged.connect(self._redraw_chart)

        btn_reset = QPushButton("Reset Peaks")
        btn_reset.setObjectName("btnNetRefresh")
        btn_reset.setFixedHeight(28)
        btn_reset.clicked.connect(self._reset_peaks)

        ctrl.addWidget(_lbl)
        ctrl.addWidget(self._iface_combo, 1)
        ctrl.addStretch()
        ctrl.addWidget(btn_reset)
        root.addLayout(ctrl)

        # Content stack: index 0 = empty state, index 1 = chart + table
        self._content_stack = QStackedWidget()

        empty_card = EmptyStateCard(
            icon="▲",
            title="No bandwidth data yet",
            what_it_shows=(
                "Real-time upload and download throughput for every network "
                "interface — 60-second rolling chart plus per-interface session totals. "
                "Starts updating within a second of clicking below."
            ),
            why_it_matters=(
                "Unexpected bandwidth spikes can reveal malware calling home, "
                "a misconfigured backup job, or a saturated link."
            ),
            btn_label="Start Monitoring",
        )
        empty_card.clicked.connect(self._start_worker)
        self._content_stack.addWidget(empty_card)

        # Index 1: chart + table
        content_w = QWidget()
        content_lay = QVBoxLayout(content_w)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(4)

        # Matplotlib chart
        chart_frame = QFrame()
        _s.themed_ss(
            chart_frame,
            "background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0;",
        )
        chart_lay = QVBoxLayout(chart_frame)
        chart_lay.setContentsMargins(8, 8, 8, 8)

        self._fig = Figure(figsize=(10, 3.2), facecolor=_s.CHART_BG)
        self._ax = self._fig.add_subplot(111)
        self._fig.subplots_adjust(left=0.06, right=0.99, top=0.93, bottom=0.15)
        self._canvas = FigureCanvas(self._fig)
        _s.themed_ss(self._canvas, "background:{CHART_BG}; border:none;")
        self._canvas.setMinimumHeight(80)
        chart_lay.addWidget(self._canvas)
        content_lay.addWidget(chart_frame, 2)

        # Per-interface breakdown table
        tbl_label = QLabel("SESSION TOTALS BY INTERFACE")
        tbl_label.setStyleSheet(
            f"font-size:10px; font-weight:bold; color:{TEXT_MUTED};"
            f" letter-spacing:0.5px; background:transparent; border:none;"
            f" padding:6px 0 2px 0;"
        )
        content_lay.addWidget(tbl_label)

        self._tbl = QTableWidget(0, 5)
        self._tbl.setHorizontalHeaderLabels(
            ["Interface", "↑ Up (MB)", "↓ Down (MB)", "Current Up", "Current Down"]
        )
        self._tbl.horizontalHeader().setStretchLastSection(True)
        self._tbl.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.verticalHeader().setDefaultSectionSize(24)
        self._tbl.setMaximumHeight(180)
        self._tbl.setStyleSheet(
            f"QTableWidget {{ border:none; font-size:11px; color:{TEXT_PRIMARY}; }}"
            f"QHeaderView::section {{"
            f"  background:{TH_BG}; color:{TH_TEXT}; font-size:11px;"
            f"  font-weight:bold; padding:4px 5px; border:none;"
            f"  border-right:1px solid {TH_BORDER};"
            f"}}"
            f"QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
            f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
            f"QTableWidget::item {{ border-bottom:1px solid {TABLE_ROW_BORDER}; }}"
        )
        def _bw_show_inventory():
            from PyQt6.QtWidgets import QApplication as _QA
            from ui.nav.labels import NavLabel as _L
            win = _QA.instance().activeWindow()
            if hasattr(win, "_nav_rail_go_to"):
                win._nav_rail_go_to(_L.DEVICES)

        install_copy_menu(self._tbl, [
            ("separator",         None),
            ("Show in Inventory", _bw_show_inventory),
        ])
        content_lay.addWidget(self._tbl)

        self._content_stack.addWidget(content_w)
        root.addWidget(self._content_stack, 1)

        self._draw_empty_chart()

    # ── Worker ────────────────────────────────────────────────────────────────

    def _start_worker(self) -> None:
        from workers.iface_bw_worker import IfaceBwPoller
        self._worker = IfaceBwPoller(interval_s=1.0, parent=self)
        self._worker.stats_ready.connect(self._on_stats)
        self._worker.error.connect(
            lambda e: self._ax.set_title(f"⚠  {e}", color=RED, fontsize=9)
        )
        self._worker.start()

    def closeEvent(self, event):
        if self._worker:
            self._worker.stop()
            self._worker.wait(2000)
        super().closeEvent(event)

    # ── Data handling ─────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def _on_stats(self, stats: dict) -> None:
        """Called every second with per-interface Mbps data."""
        self._content_stack.setCurrentIndex(1)
        # Update combo box if new interfaces appear
        current_ifaces = set(self._history.keys())
        new_ifaces = set(stats.keys()) - current_ifaces
        if new_ifaces:
            for iface in sorted(new_ifaces):
                self._history[iface] = {
                    "up":   deque([0.0] * _HISTORY_LEN, maxlen=_HISTORY_LEN),
                    "down": deque([0.0] * _HISTORY_LEN, maxlen=_HISTORY_LEN),
                }
                self._session[iface] = {"up_mb": 0.0, "down_mb": 0.0,
                                         "up_mbps": 0.0, "down_mbps": 0.0}
                self._iface_combo.addItem(iface)

        # Push new samples
        for iface, d in stats.items():
            if iface not in self._history:
                continue
            up   = d["up_mbps"]
            down = d["down_mbps"]
            self._history[iface]["up"].append(up)
            self._history[iface]["down"].append(down)
            self._session[iface]["up_mb"]    += d["up_bytes"]   / 1_000_000
            self._session[iface]["down_mb"]  += d["down_bytes"] / 1_000_000
            self._session[iface]["up_mbps"]   = up
            self._session[iface]["down_mbps"] = down

        # KPI: aggregate current values across all ifaces
        total_up   = sum(d["up_mbps"]   for d in self._session.values())
        total_down = sum(d["down_mbps"] for d in self._session.values())
        self._peak_up   = max(self._peak_up,   total_up)
        self._peak_down = max(self._peak_down, total_down)

        self._lbl_up.setText(f"{total_up:.2f}")
        self._lbl_down.setText(f"{total_down:.2f}")
        self._lbl_pkup.setText(f"{self._peak_up:.2f}")
        self._lbl_pkdn.setText(f"{self._peak_down:.2f}")

        # Age event annotations; prune those that have scrolled off the chart
        self._events = [
            [age + 1, lbl, clr]
            for age, lbl, clr in self._events
            if age + 1 < _HISTORY_LEN
        ]

        self._redraw_chart()
        self._update_table()
        self._start_slide()

    def _get_chart_data(self) -> tuple[list, list]:
        """Return (up_series, down_series) for the selected interface."""
        sel = self._iface_combo.currentText()
        if sel == "All interfaces (sum)" or sel not in self._history:
            # Sum all interfaces
            if not self._history:
                return [0.0] * _HISTORY_LEN, [0.0] * _HISTORY_LEN
            up   = [0.0] * _HISTORY_LEN
            down = [0.0] * _HISTORY_LEN
            for h in self._history.values():
                for i, (u, d) in enumerate(zip(h["up"], h["down"])):
                    up[i]   += u
                    down[i] += d
            return up, down
        h = self._history[sel]
        return list(h["up"]), list(h["down"])

    # ── Chart drawing ─────────────────────────────────────────────────────────

    def _draw_empty_chart(self) -> None:
        ax = self._ax
        ax.clear()
        ax.set_facecolor(_s.CHART_PLOT_BG)
        ax.fill_between(range(_HISTORY_LEN), 0, color=_DOWN_COLOR, alpha=0.15)
        ax.fill_between(range(_HISTORY_LEN), 0, color=_UP_COLOR,   alpha=0.15)
        ax.set_xlim(0, _HISTORY_LEN - 1)
        ax.set_ylim(0, 10)
        ax.set_xlabel("seconds ago", fontsize=8, color=CHART_AXIS)
        ax.set_ylabel("Mbps", fontsize=8, color=CHART_AXIS)
        ax.tick_params(labelsize=7, colors=CHART_AXIS)
        for sp in ax.spines.values():
            sp.set_edgecolor(_s.CHART_SPINE)
        ax.grid(True, linestyle="--", linewidth=0.4, color=_s.CHART_GRID)
        self._canvas.draw_idle()

    @pyqtSlot()
    def _redraw_chart(self) -> None:
        up, down = self._get_chart_data()
        ax = self._ax
        ax.clear()
        ax.set_facecolor(_s.CHART_PLOT_BG)

        xs = list(range(_HISTORY_LEN))
        ax.fill_between(xs, down, alpha=0.35, color=_DOWN_COLOR, label="↓ Download")
        ax.plot(xs, down, color=_DOWN_COLOR, linewidth=1.2)
        ax.fill_between(xs, up,   alpha=0.35, color=_UP_COLOR,   label="↑ Upload")
        ax.plot(xs, up,   color=_UP_COLOR,   linewidth=1.2)

        peak = max(max(up, default=0), max(down, default=0))
        ax.set_ylim(0, max(peak * 1.25, 1.0))
        ax.set_xlim(0, _HISTORY_LEN - 1)

        # x-axis: show "now" on the right, "60s ago" on the left
        ax.set_xticks([0, 15, 30, 45, 59])
        ax.set_xticklabels(["-60s", "-45s", "-30s", "-15s", "now"], fontsize=7)
        ax.set_ylabel("Mbps", fontsize=8, color=CHART_AXIS)
        ax.tick_params(labelsize=7, colors=CHART_AXIS)
        for sp in ax.spines.values():
            sp.set_edgecolor(_s.CHART_SPINE)
        ax.grid(True, linestyle="--", linewidth=0.4, color=_s.CHART_GRID)
        ax.legend(loc="upper left", fontsize=7, framealpha=0.7,
                  facecolor=_s.CHART_BG, edgecolor=_s.CHART_SPINE)

        # Event annotation ticks (device join = green, rate spike = red)
        y_top = ax.get_ylim()[1]
        for age, lbl, clr in self._events:
            x = _HISTORY_LEN - 1 - age
            ax.axvline(x, color=clr, linewidth=1.0, alpha=0.55,
                       linestyle="--", zorder=4)
            if x > 3:
                ax.text(x + 0.4, y_top * 0.88, lbl,
                        fontsize=6, color=clr, ha="left", va="top",
                        rotation=90, zorder=5)

        # Title shows current values
        sel = self._iface_combo.currentText()
        ax.set_title(
            f"{sel}  —  "
            f"↑ {up[-1]:.2f} Mbps  ↓ {down[-1]:.2f} Mbps",
            fontsize=8, color=_s.TEXT_SECONDARY, pad=4,
        )
        self._canvas.draw_idle()

    def refresh_theme(self) -> None:
        """Live theme switch: re-read the matplotlib colour tokens and redraw.

        The canvas widget background re-applies automatically (themed_ss
        registry); this re-reads the figure facecolor and repaints the chart.
        """
        self._fig.set_facecolor(_s.CHART_BG)
        self._redraw_chart()

    # ── Breakdown table ───────────────────────────────────────────────────────

    def _update_table(self) -> None:
        self._tbl.setRowCount(0)
        for iface, d in sorted(self._session.items()):
            row = self._tbl.rowCount()
            self._tbl.insertRow(row)
            cells = [
                (iface,                               TEXT_PRIMARY),
                (f"{d['up_mb']:.2f}",                 GREEN),
                (f"{d['down_mb']:.2f}",               ACCENT),
                (f"{d['up_mbps']:.2f} Mbps",          TEXT_SECONDARY),
                (f"{d['down_mbps']:.2f} Mbps",        TEXT_SECONDARY),
            ]
            for col, (text, color) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color))
                self._tbl.setItem(row, col, item)

    # ── Slide animation (ANIM-2) ──────────────────────────────────────────────

    def _start_slide(self) -> None:
        """Kick off a 200 ms / 4-frame leftward slide after new data arrives."""
        from ui.theme import _reduce_motion
        if _reduce_motion():
            return
        self._slide_timer.stop()
        self._slide_offset = -1.0   # chart appears shifted right; slides to 0
        self._slide_timer.start()

    @pyqtSlot()
    def _slide_tick(self) -> None:
        self._slide_offset += 0.25
        self._ax.set_xlim(self._slide_offset, _HISTORY_LEN + self._slide_offset)
        self._canvas.draw_idle()
        if self._slide_offset >= 0.0:
            self._slide_timer.stop()
            self._slide_offset = 0.0

    # ── Reset peaks ───────────────────────────────────────────────────────────

    @pyqtSlot()
    def _reset_peaks(self) -> None:
        self._peak_up   = 0.0
        self._peak_down = 0.0
        self._lbl_pkup.setText("—")
        self._lbl_pkdn.setText("—")

    # ── Event annotations (VIZ-2) ─────────────────────────────────────────────

    @pyqtSlot(str, str)
    def annotate_event(self, label: str, color: str) -> None:
        """Pin a labelled vertical tick at 'now' that scrolls left with the chart."""
        self._events.append([0, label, color])
