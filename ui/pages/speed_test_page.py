"""
SpeedTestPage — Ookla-style internet speed test.

Layout
──────
  Top:    Page title + subtitle
  Middle: [Server Selection card] | [Live Speed Gauge card]
  Action: Run Speed Test button + status label
  Bottom: Test History table
"""

from __future__ import annotations

import math
from typing import List, Optional

import matplotlib
matplotlib.use("QtAgg")
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    CARD_HDR_BORDER,
    GREEN,
    PROGRESS_TRACK,
    RED,
    TABLE_ROW_BORDER,
    TABLE_SEL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_BORDER,
    TH_TEXT,
)

from ui.pages.ookla_cli_banner import OoklaCliBanner

# ── Gauge constants ───────────────────────────────────────────────────────────
_GAUGE_START_DEG = 210     # 7 o'clock — 0 Mbps (left)
_GAUGE_END_DEG   = -30     # 5 o'clock — max Mbps (right)
_GAUGE_SPAN      = 240     # total arc degrees
_GAUGE_MAX_MBPS  = 1000.0
_GAUGE_R_OUTER   = 0.42
_GAUGE_R_INNER   = 0.28
_GAUGE_CENTER    = (0.0, -0.06)

# Log-scale tick marks matching speedtest.net
_GAUGE_TICKS = [1, 5, 10, 50, 100, 250, 500, 1000]
_GAUGE_MAJOR = {0, 10, 100, 1000}   # ticks that get a text label

_COLOR_DOWNLOAD = ACCENT             # brand blue
_COLOR_UPLOAD   = GREEN              # green
_COLOR_IDLE     = TEXT_MUTED         # muted grey
_COLOR_TRACK    = PROGRESS_TRACK     # light grey track


def _speed_fraction(mbps: float, max_mbps: float = _GAUGE_MAX_MBPS) -> float:
    """Convert speed to 0-1 fill fraction on a log₁₀ scale."""
    if mbps <= 0 or max_mbps <= 0:
        return 0.0
    return min(math.log10(mbps + 1) / math.log10(max_mbps + 1), 1.0)


# ── Gauge widget ──────────────────────────────────────────────────────────────

class SpeedGaugeWidget(QWidget):
    """
    Matplotlib-powered semicircular speed gauge.
    Call set_value(mbps, phase) to update display.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._value  = 0.0
        self._phase  = "idle"   # "idle" | "download" | "upload"
        self._status = ""

        self._fig    = Figure(figsize=(3.6, 2.6), dpi=96, facecolor=BG_CARD)
        self._ax     = self._fig.add_axes([0, 0, 1, 1])
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

        self._draw()

    # ── Public interface ──────────────────────────────────────────────────────

    def set_value(self, mbps: float, phase: str = "download") -> None:
        self._value  = mbps
        self._phase  = phase
        self._draw()

    def set_status(self, text: str) -> None:
        self._status = text
        self._draw()

    def reset(self) -> None:
        self._value  = 0.0
        self._phase  = "idle"
        self._status = ""
        self._draw()

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        ax = self._ax
        ax.cla()
        ax.set_facecolor(BG_CARD)
        ax.set_xlim(-0.62, 0.62)
        ax.set_ylim(-0.40, 0.58)
        ax.set_aspect("equal")
        ax.axis("off")

        cx, cy = _GAUGE_CENTER

        # --- Background track ---
        theta_bg = np.linspace(
            math.radians(_GAUGE_START_DEG),
            math.radians(_GAUGE_END_DEG),
            300,
        )
        xo = cx + _GAUGE_R_OUTER * np.cos(theta_bg)
        yo = cy + _GAUGE_R_OUTER * np.sin(theta_bg)
        xi = cx + _GAUGE_R_INNER * np.cos(theta_bg[::-1])
        yi = cy + _GAUGE_R_INNER * np.sin(theta_bg[::-1])
        ax.fill(
            np.concatenate([xo, xi]),
            np.concatenate([yo, yi]),
            color=_COLOR_TRACK, zorder=1,
        )

        # --- Fill arc ---
        fraction = _speed_fraction(self._value, _GAUGE_MAX_MBPS)
        if fraction > 0.002:
            fill_end_deg = _GAUGE_START_DEG - fraction * _GAUGE_SPAN
            theta_f = np.linspace(
                math.radians(_GAUGE_START_DEG),
                math.radians(fill_end_deg),
                300,
            )
            xof = cx + _GAUGE_R_OUTER * np.cos(theta_f)
            yof = cy + _GAUGE_R_OUTER * np.sin(theta_f)
            xif = cx + _GAUGE_R_INNER * np.cos(theta_f[::-1])
            yif = cy + _GAUGE_R_INNER * np.sin(theta_f[::-1])
            fill_color = (
                _COLOR_UPLOAD if self._phase == "upload"
                else _COLOR_DOWNLOAD if self._phase == "download"
                else ACCENT
            )
            ax.fill(
                np.concatenate([xof, xif]),
                np.concatenate([yof, yif]),
                color=fill_color, zorder=2,
            )

            # Tip highlight dot at the arc end
            tip_r = (_GAUGE_R_INNER + _GAUGE_R_OUTER) / 2
            tip_x = cx + tip_r * math.cos(math.radians(fill_end_deg))
            tip_y = cy + tip_r * math.sin(math.radians(fill_end_deg))
            ax.plot(
                tip_x, tip_y, "o",
                color="white", markersize=5.5, zorder=4,
            )

        # --- Scale tick marks ---
        for t in _GAUGE_TICKS:
            frac = _speed_fraction(t, _GAUGE_MAX_MBPS)
            deg  = _GAUGE_START_DEG - frac * _GAUGE_SPAN
            rad  = math.radians(deg)
            r_inner_tick = _GAUGE_R_OUTER + 0.025
            r_outer_tick = _GAUGE_R_OUTER + (0.055 if t in _GAUGE_MAJOR else 0.038)
            ax.plot(
                [cx + r_inner_tick * math.cos(rad), cx + r_outer_tick * math.cos(rad)],
                [cy + r_inner_tick * math.sin(rad), cy + r_outer_tick * math.sin(rad)],
                color=_COLOR_IDLE, linewidth=0.9, zorder=3,
            )
            if t in _GAUGE_MAJOR:
                r_lbl = _GAUGE_R_OUTER + 0.115
                ax.text(
                    cx + r_lbl * math.cos(rad),
                    cy + r_lbl * math.sin(rad),
                    str(t),
                    ha="center", va="center",
                    fontsize=6.5, color=TEXT_MUTED, fontfamily="Segoe UI",
                )

        # --- Centre speed value ---
        val_str = f"{self._value:.1f}" if self._phase != "idle" else "—"
        ax.text(
            cx, cy + 0.04, val_str,
            ha="center", va="center",
            fontsize=26, fontweight="bold",
            color=TEXT_PRIMARY, fontfamily="Segoe UI",
        )
        ax.text(
            cx, cy - 0.11, "Mbps",
            ha="center", va="center",
            fontsize=9, color=TEXT_SECONDARY, fontfamily="Segoe UI",
        )

        # --- Phase label ---
        if self._phase == "download":
            phase_label = "↓  DOWNLOAD"
            phase_color = _COLOR_DOWNLOAD
        elif self._phase == "upload":
            phase_label = "↑  UPLOAD"
            phase_color = _COLOR_UPLOAD
        else:
            phase_label = self._status or "READY"
            phase_color = TEXT_MUTED

        ax.text(
            cx, cy + 0.20, phase_label,
            ha="center", va="center",
            fontsize=8.5, fontweight="bold",
            color=phase_color, fontfamily="Segoe UI",
        )

        self._fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self._canvas.draw_idle()


# ── Server list widget ────────────────────────────────────────────────────────

class _ServerList(QListWidget):
    """Styled server selection list."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("serverList")
        self.setAlternatingRowColors(True)
        self.setStyleSheet(
            f"QListWidget#serverList {{"
            f"  background:{BG_CARD}; border:1px solid {BORDER};"
            f"  font-size:11px; color:{TEXT_PRIMARY}; outline:none;"
            f"}}"
            f"QListWidget#serverList::item {{"
            f"  padding:5px 8px; border-bottom:1px solid {BORDER};"
            f"}}"
            f"QListWidget#serverList::item:selected {{"
            f"  background:{TABLE_SEL}; color:{TEXT_PRIMARY};"
            f"}}"
            f"QListWidget#serverList::item:hover:!selected {{"
            f"  background:{BG_HOVER};"
            f"}}"
        )


# ── Card helper ───────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    """Return (card_frame, body_layout). Title bar with bold heading."""
    frame = QFrame()
    frame.setObjectName("card")
    frame.setStyleSheet(
        f"QFrame#card {{"
        f"  background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0px;"
        f"}}"
    )
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QFrame()
    hdr.setFixedHeight(32)
    hdr.setStyleSheet(
        f"background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER};"
        f" border-radius:0px;"
    )
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 0, 10, 0)
    t = QLabel(title.upper())
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
        f" letter-spacing:0.5px; background:transparent; border:none;"
    )
    hdr_lay.addWidget(t)
    hdr_lay.addStretch()
    outer.addWidget(hdr)

    body = QVBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(0)
    outer.addLayout(body, 1)

    return frame, body


# ── Stat tile ─────────────────────────────────────────────────────────────────

def _stat_tile(label: str) -> tuple[QFrame, QLabel, QLabel]:
    """Return (tile, value_label, unit_label)."""
    tile = QFrame()
    tile.setStyleSheet(
        f"background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {ACCENT}; border-radius:0px;"
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
        f"color:{TEXT_PRIMARY}; font-size:20px; font-weight:bold;"
        f" border:none; background:transparent;"
    )

    unit = QLabel("")
    unit.setStyleSheet(
        f"color:{TEXT_SECONDARY}; font-size:10px;"
        f" border:none; background:transparent;"
    )

    lay.addWidget(lbl)
    lay.addWidget(val)
    lay.addWidget(unit)
    return tile, val, unit


# ── Main page ─────────────────────────────────────────────────────────────────

class SpeedTestPage(QWidget):
    """
    Ookla-style internet speed test page.
    """

    #: Emitted when a speed test completes successfully. Carries the SpeedTestResult.
    test_completed = pyqtSignal(object)

    def __init__(self, store=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._store = store  # MetricStore | None
        self._servers: List[dict] = []
        self._selected_server_id: Optional[str] = None
        self._fetch_worker  = None
        self._test_worker   = None
        self._last_fetch_ts: float = 0.0   # epoch; 0 = never
        self._history: List[dict] = []
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(80)
        self._anim_timer.timeout.connect(self._anim_tick)
        self._anim_target  = 0.0
        self._anim_current = 0.0
        self._anim_phase   = "download"

        self._setup_ui()
        self._fetch_servers()
        self._load_history_from_db()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Page title
        title = QLabel("Speed Test")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
            f" background:transparent; border:none;"
        )
        sub = QLabel(
            "Measure download, upload and ping using Ookla-compatible servers"
        )
        sub.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            f" background:transparent; border:none; padding:0 0 4px 0;"
        )
        root.addWidget(title)
        root.addWidget(sub)

        # ── Ookla CLI install banner (hidden if CLI already present) ──────────
        self._ookla_banner = OoklaCliBanner(parent=self)
        self._ookla_banner.installed.connect(self._on_ookla_installed)
        root.addWidget(self._ookla_banner)

        # ── Top row: server card + gauge card ─────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # --- Server selection card ---
        srv_card, srv_body = _card("Server Selection")
        srv_body.setContentsMargins(8, 8, 8, 8)
        srv_body.setSpacing(6)

        # Search box
        search_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search servers…")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setStyleSheet(
            f"QLineEdit {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:3px; padding:4px 8px; font-size:11px;"
            f" color:{TEXT_PRIMARY}; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._search_box.textChanged.connect(self._filter_servers)
        search_row.addWidget(self._search_box)
        srv_body.addLayout(search_row)

        # Server list
        self._server_list = _ServerList()
        self._server_list.currentItemChanged.connect(self._on_server_selected)
        srv_body.addWidget(self._server_list, 1)

        # "Closest server" label + Refresh
        footer_row = QHBoxLayout()
        self._server_hint = QLabel("Loading servers…")
        self._server_hint.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
        )
        footer_row.addWidget(self._server_hint, 1)
        btn_refresh = QPushButton("↻  Refresh")
        btn_refresh.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT};"
            f" border:none; font-size:11px; padding:2px 4px; }}"
            f"QPushButton:hover {{ text-decoration:underline; }}"
        )
        btn_refresh.clicked.connect(self._fetch_servers)
        footer_row.addWidget(btn_refresh)
        srv_body.addLayout(footer_row)

        top_row.addWidget(srv_card, 4)

        # --- Gauge card ---
        gauge_card, gauge_body = _card("Live Speed")
        gauge_body.setContentsMargins(8, 8, 8, 8)
        gauge_body.setSpacing(6)

        self._gauge = SpeedGaugeWidget()
        self._gauge.setMinimumHeight(220)
        gauge_body.addWidget(self._gauge, 1)

        # Stat tiles row: Ping | Download | Upload
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)

        self._tile_ping,     self._lbl_ping,     self._unit_ping     = _stat_tile("Ping")
        self._tile_down,     self._lbl_down,     self._unit_down     = _stat_tile("Download")
        self._tile_up,       self._lbl_up,       self._unit_up       = _stat_tile("Upload")

        self._unit_ping.setText("ms")
        self._unit_down.setText("Mbps")
        self._unit_up.setText("Mbps")

        for tile in (self._tile_ping, self._tile_down, self._tile_up):
            stats_row.addWidget(tile, 1)

        gauge_body.addLayout(stats_row)
        top_row.addWidget(gauge_card, 6)

        root.addLayout(top_row, 3)

        # ── Run button + status ───────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self._btn_run = QPushButton("▶   Run Speed Test")
        self._btn_run.setObjectName("btnScan")
        self._btn_run.setMinimumWidth(180)
        self._btn_run.setFixedHeight(34)
        self._btn_run.clicked.connect(self._run_test)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            f" background:transparent; border:none;"
        )

        # Engine badge — shows which backend will be used
        self._engine_lbl = QLabel()
        self._engine_lbl.setStyleSheet(
            f"font-size:10px; background:transparent; border:none; padding:0 4px;"
        )
        self._engine_lbl.setToolTip(
            "Speed test engine in use.\n"
            "Ookla CLI = highest accuracy (1 Gbps+)\n"
            "speedtest-cli = 8-thread library fallback\n"
            "Pure-Python = built-in 16-stream fallback"
        )
        self._refresh_engine_badge()

        action_row.addWidget(self._btn_run)
        action_row.addWidget(self._engine_lbl)
        action_row.addWidget(self._status_lbl, 1)
        root.addLayout(action_row)

        # ── History table ─────────────────────────────────────────────────────
        hist_card, hist_body = _card("Test History")

        self._hist_table = QTableWidget(0, 7)
        self._hist_table.setHorizontalHeaderLabels([
            "Date / Time", "Server", "Location", "Ping (ms)",
            "↓ Download", "↑ Upload", "Status",
        ])
        self._hist_table.horizontalHeader().setStretchLastSection(True)
        self._hist_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._hist_table.setAlternatingRowColors(True)
        self._hist_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._hist_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._hist_table.verticalHeader().setVisible(False)
        self._hist_table.setShowGrid(True)
        self._hist_table.verticalHeader().setDefaultSectionSize(24)
        self._hist_table.setColumnWidth(0, 145)
        self._hist_table.setColumnWidth(3, 75)
        self._hist_table.setColumnWidth(4, 105)
        self._hist_table.setColumnWidth(5, 105)
        self._hist_table.setColumnWidth(6, 100)
        self._hist_table.setStyleSheet(
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

        hist_body.addWidget(self._hist_table)
        root.addWidget(hist_card, 2)

    # ── Server fetching ───────────────────────────────────────────────────────

    def _fetch_servers(self) -> None:
        from workers.speed_test_worker import FetchServersWorker

        if self._fetch_worker and self._fetch_worker.isRunning():
            return

        self._server_hint.setText("Fetching servers…")
        self._server_list.clear()
        item = QListWidgetItem("Connecting to Speedtest network…")
        item.setForeground(QColor(TEXT_MUTED))
        self._server_list.addItem(item)

        self._fetch_worker = FetchServersWorker(limit=20, parent=self)
        self._fetch_worker.servers_ready.connect(self._on_servers_ready)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Auto-refresh server list if it is more than 30 minutes old."""
        super().showEvent(event)
        import time
        if time.time() - self._last_fetch_ts > 1800:
            self._fetch_servers()

    @pyqtSlot(list)
    def _on_servers_ready(self, servers: list) -> None:
        import time
        self._last_fetch_ts = time.time()
        self._servers = servers
        self._server_list.clear()
        self._populate_server_list(servers)
        count = len(servers)
        self._server_hint.setText(
            f"{count} server{'s' if count != 1 else ''} nearby — "
            "auto-best selected if none chosen"
        )
        # Pre-select the first (lowest latency)
        if self._server_list.count() > 0:
            self._server_list.setCurrentRow(0)

    @pyqtSlot(str)
    def _on_fetch_error(self, msg: str) -> None:
        self._server_list.clear()
        err_item = QListWidgetItem(f"⚠  {msg}")
        err_item.setForeground(QColor(RED))
        self._server_list.addItem(err_item)
        self._server_hint.setText("Could not fetch server list — auto-best will be used")

    def _populate_server_list(self, servers: list) -> None:
        for s in servers:
            lat_str = f"{s['latency_ms']:.0f} ms" if s["latency_ms"] > 0 else "—"
            text = (
                f"{s['city']} — {s['name']}   "
                f"({s['country']})   {lat_str}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            item.setToolTip(f"Host: {s['host']}")
            self._server_list.addItem(item)

    @pyqtSlot(str)
    def _filter_servers(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self._server_list.count()):
            item = self._server_list.item(i)
            if item:
                item.setHidden(bool(text) and text not in item.text().lower())

    @pyqtSlot()
    def _on_server_selected(self) -> None:
        cur = self._server_list.currentItem()
        if cur:
            self._selected_server_id = cur.data(Qt.ItemDataRole.UserRole)

    # ── Engine badge ──────────────────────────────────────────────────────────

    def _refresh_engine_badge(self) -> None:
        """Update the engine badge based on what _find_ookla_cli() returns."""
        try:
            from modules.speed_tester import _find_ookla_cli
            cli = _find_ookla_cli()
        except Exception:
            cli = None

        if cli:
            self._engine_lbl.setText(f"Engine: Ookla CLI ✓")
            self._engine_lbl.setStyleSheet(
                f"font-size:10px; background:transparent; border:none;"
                f" color:{GREEN}; padding:0 4px;"
            )
        else:
            try:
                import speedtest  # noqa: F401
                label = "Engine: speedtest-cli"
            except ImportError:
                label = "Engine: Pure-Python"
            self._engine_lbl.setText(label)
            self._engine_lbl.setStyleSheet(
                f"font-size:10px; background:transparent; border:none;"
                f" color:{AMBER}; padding:0 4px;"
            )

    # ── Ookla CLI banner callback ─────────────────────────────────────────────

    @pyqtSlot()
    def _on_ookla_installed(self) -> None:
        """Called after OoklaCliBanner successfully installs the Ookla CLI."""
        self._refresh_engine_badge()
        self._set_status("\u2713  Ookla CLI installed \u2014 rerun the test for 1 Gbps+ speeds.")

    # ── Test execution ────────────────────────────────────────────────────────

    @pyqtSlot()
    def _run_test(self) -> None:
        from workers.speed_test_worker import SpeedTestWorker

        if self._test_worker and self._test_worker.isRunning():
            return

        # Reset display
        self._btn_run.setEnabled(False)
        self._btn_run.setText("⏳  Testing…")
        self._lbl_ping.setText("—")
        self._lbl_down.setText("—")
        self._lbl_up.setText("—")
        self._gauge.reset()
        self._anim_current = 0.0
        self._set_status("Connecting to server…")

        self._test_worker = SpeedTestWorker(
            server_id=self._selected_server_id,
            parent=self,
        )
        self._test_worker.phase_changed.connect(self._on_phase_changed)
        self._test_worker.speed_sample.connect(self._on_speed_sample)
        self._test_worker.result_ready.connect(self._on_result_ready)
        self._test_worker.error.connect(self._on_test_error)
        self._test_worker.start()

    @pyqtSlot(str, str)
    def _on_phase_changed(self, phase: str, message: str) -> None:
        self._set_status(message)
        if phase == "ping":
            # Parse ping value from message e.g. "Ping: 50 ms → …"
            try:
                ping_val = float(message.split(":")[1].split("ms")[0].strip())
                self._lbl_ping.setText(f"{ping_val:.0f}")
            except (IndexError, ValueError):
                pass
            self._gauge.set_value(0.0, "download")
            self._gauge.set_status("Starting…")

        elif phase == "download":
            self._anim_phase   = "download"
            self._anim_current = 0.0
            self._anim_target  = 0.0
            self._anim_timer.start()
            self._gauge.set_value(0.0, "download")

        elif phase == "upload":
            self._anim_timer.stop()
            # Lock download result on gauge
            self._anim_phase   = "upload"
            self._anim_current = 0.0
            self._anim_target  = 0.0
            self._anim_timer.start()
            self._gauge.set_value(0.0, "upload")

        elif phase == "done":
            self._anim_timer.stop()

    @pyqtSlot(float, str)
    def _on_speed_sample(self, mbps: float, phase: str) -> None:
        """Receive a live throughput sample and update the gauge target."""
        self._anim_phase  = phase
        self._anim_target = mbps
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    @pyqtSlot(object)
    def _on_result_ready(self, result: object) -> None:
        self._anim_timer.stop()
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶   Run Speed Test")
        self.test_completed.emit(result)
        self._lbl_ping.setText(f"{result.ping_ms:.0f}")
        self._lbl_down.setText(f"{result.download_mbps:.1f}")
        self._lbl_up.setText(f"{result.upload_mbps:.1f}")

        # Animate gauge to final download value, then hold
        self._anim_phase   = "download"
        self._anim_target  = result.download_mbps
        self._anim_timer.start()
        self._set_status(
            f"✓  {result.server_name}, {result.server_city} — "
            f"↓ {result.download_mbps:.1f}  ↑ {result.upload_mbps:.1f}  Mbps"
        )

        # Persist to database
        if self._store:
            try:
                self._store.record_speed_test(
                    download_mbps=result.download_mbps,
                    upload_mbps=result.upload_mbps,
                    ping_ms=result.ping_ms,
                    server_name=result.server_name,
                    server_city=result.server_city,
                    server_country=result.server_country,
                )
            except Exception:
                pass  # never let a DB write break the UI

        # Add to history
        self._add_history_row(result)

    @pyqtSlot(str)
    def _on_test_error(self, msg: str) -> None:
        self._anim_timer.stop()
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶   Run Speed Test")
        self._gauge.set_value(0.0, "idle")
        self._gauge.set_status("ERROR")
        self._set_status(f"⚠  {msg}")
        self._add_history_row(None, error=msg)

    # ── Animation ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _anim_tick(self) -> None:
        """Smoothly ramp gauge needle toward target."""
        step = max((self._anim_target - self._anim_current) * 0.15, 1.0)
        self._anim_current = min(self._anim_current + step, self._anim_target)
        self._gauge.set_value(self._anim_current, self._anim_phase)
        if abs(self._anim_current - self._anim_target) < 0.5 and self._anim_target > 0:
            self._anim_timer.stop()

    # ── History ───────────────────────────────────────────────────────────────

    def _add_history_row(self, result, error: str = "") -> None:
        row = self._hist_table.rowCount()
        self._hist_table.insertRow(0)  # newest at top

        if result:
            backend = getattr(result, "backend", "") or "OK"
            backend_color = GREEN if backend == "Ookla CLI" else AMBER
            cells = [
                result.timestamp.replace("T", "  "),
                result.server_name,
                f"{result.server_city}, {result.server_country}",
                f"{result.ping_ms:.0f}",
                f"{result.download_mbps:.1f} Mbps",
                f"{result.upload_mbps:.1f} Mbps",
                backend,
            ]
            colors = [None, None, None, None,
                      GREEN if result.download_mbps >= 25 else AMBER,
                      GREEN if result.upload_mbps >= 5  else AMBER,
                      backend_color]
        else:
            cells = ["—", "—", "—", "—", "—", "—", "Error"]
            colors = [None]*6 + [RED]

        for col, (val, col_color) in enumerate(zip(cells, colors)):
            item = QTableWidgetItem(str(val))
            if col_color:
                item.setForeground(QColor(col_color))
            self._hist_table.setItem(0, col, item)

        self._hist_table.scrollToTop()

    # ── Status helper ─────────────────────────────────────────────────────────
    def _load_history_from_db(self) -> None:
        """Populate history table from MetricStore on page load."""
        if not self._store:
            return
        try:
            points = self._store.query_speed_test_history(hours=168 * 4)  # ~28 days
            for p in points:
                import datetime as _dt
                ts_str = _dt.datetime.fromtimestamp(p.ts).strftime("%Y-%m-%d  %H:%M:%S")
                row = self._hist_table.rowCount()
                self._hist_table.insertRow(row)
                cells = [
                    ts_str,
                    p.server_name or "",
                    f"{p.server_city or ''}, {p.server_country or ''}".strip(", "),
                    f"{p.ping_ms:.0f}",
                    f"{p.download_mbps:.1f} Mbps",
                    f"{p.upload_mbps:.1f} Mbps",
                    "OK",
                ]
                clrs = [None, None, None, None,
                        GREEN if p.download_mbps >= 25 else AMBER,
                        GREEN if p.upload_mbps >= 5  else AMBER,
                        GREEN]
                for col, (val, col_color) in enumerate(zip(cells, clrs)):
                    item = QTableWidgetItem(str(val))
                    if col_color:
                        item.setForeground(QColor(col_color))
                    self._hist_table.setItem(row, col, item)
        except Exception:
            pass  # DB not available yet is fine
    def _set_status(self, text: str) -> None:
        self._status_lbl.setText(text)
