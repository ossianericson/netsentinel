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

from PyQt6.QtCore import Qt, QEasingCurve, QTimer, QVariantAnimation, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_ALT_ROW, BG_CARD,
    BG_HOVER, BORDER, CARD_HDR_BORDER,
    CARD_RADIUS, CHART_GRID, CHART_PLOT_BG, GREEN,
    PROGRESS_TRACK, RED, TABLE_ROW_BORDER, TABLE_SEL,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TH_BG,
    TH_BORDER, TH_TEXT,
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


def _rsrp_color(rsrp) -> str:
    if rsrp is None:
        return TEXT_MUTED
    try:
        v = float(rsrp)
    except (TypeError, ValueError):
        return TEXT_MUTED
    if v >= -80:
        return GREEN
    if v >= -100:
        return AMBER
    return RED


def _sinr_label(v: float) -> str:
    if v < 0:   return "Very Poor"
    if v < 5:   return "Poor"
    if v < 13:  return "Fair"
    if v < 20:  return "Good"
    return "Excellent"


def _sinr_color(v: float) -> str:
    if v < 5:   return RED
    if v < 13:  return AMBER
    return GREEN


def _fmt_sinr(v) -> tuple:
    """Return (display_string, color) for a SINR/SNR value in dB."""
    if v is None:
        return "—", TEXT_MUTED
    try:
        fv = float(v)
        return f"{fv:.1f} dB ({_sinr_label(fv)})", _sinr_color(fv)
    except (TypeError, ValueError):
        return "—", TEXT_MUTED


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
            phase_label = self._status or ("Run a test to begin" if self._value == 0.0 else "READY")
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
        f"  background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
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

    modem_pause_requested  = pyqtSignal()  # pause ZteWorker before capturing signal
    modem_resume_requested = pyqtSignal()  # restart ZteWorker after test finishes
    scan_requested         = pyqtSignal()  # emitted when the user clicks Run Speed Test

    def __init__(self, store=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._store = store  # MetricStore | None
        self._history_hours = 720.0  # 30-day default (FILTER-13)
        self._servers: List[dict] = []
        self._selected_server_id: Optional[str] = None
        self._fetch_worker  = None
        self._test_worker   = None
        self._last_fetch_ts: float = 0.0   # epoch; 0 = never
        self._history: List[dict] = []
        self._zte_host:     Optional[str] = None
        self._zte_password: Optional[str] = None
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(80)
        self._anim_timer.timeout.connect(self._anim_tick)
        self._anim_target  = 0.0
        self._anim_current = 0.0
        self._anim_phase   = "download"
        # ANIM-5: count-up animations for download/upload stat tiles
        self._down_count_anim: QVariantAnimation | None = None
        self._up_count_anim:   QVariantAnimation | None = None
        # VIZ-5: history chart hover state
        self._hist_chart_cid:   object = None
        self._hist_chart_annot: object = None
        self._hist_chart_pts:   list   = []

        self._setup_ui()
        self._fetch_servers()
        self._load_history_from_db()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        from ui.widgets.page_header import PageHeaderBar
        hdr = PageHeaderBar("Speed Test")
        root.addWidget(hdr)

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
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
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

        # Static speed context chip
        _ctx = QLabel(
            "< 10 Mbps — slow for streaming  ·  25–100 Mbps — typical home  ·  100+ Mbps — fast"
        )
        _ctx.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _ctx.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; background:{BG_ALT_ROW};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:3px 8px;"
        )
        gauge_body.addWidget(_ctx)

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
        self._btn_run.clicked.connect(lambda: self.scan_requested.emit())

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

        self._hist_table = QTableWidget(0, 11)
        self._hist_table.setHorizontalHeaderLabels([
            "Date / Time", "Server", "Location", "Ping (ms)",
            "↓ Download", "↑ Upload", "Band", "RSRP",
            "4G PCC SINR", "5G PCC SINR", "Status",
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
        self._hist_table.setColumnWidth(6, 90)
        self._hist_table.setColumnWidth(7, 90)
        self._hist_table.setColumnWidth(8, 140)
        self._hist_table.setColumnWidth(9, 140)
        self._hist_table.setColumnWidth(10, 80)
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

        self._hist_table.itemSelectionChanged.connect(self._on_history_row_selected)
        self._hist_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._hist_table.customContextMenuRequested.connect(self._on_hist_context_menu)
        from ui.table_utils import save_column_widths
        self._hist_table.horizontalHeader().sectionResized.connect(
            lambda _l, _o, _n: save_column_widths(self._hist_table, "speed_test")
        )

        # Empty state — shown when no history exists yet
        from ui.widgets.empty_state_card import EmptyStateCard as _ESC
        _hist_empty = _ESC(
            icon="◈",
            title="No speed tests recorded yet",
            what_it_shows=(
                "Download speed, upload speed, ping, and jitter history — "
                "with a trend chart and per-server breakdown."
            ),
            why_it_matters=(
                "Tracking speeds over time reveals ISP throttling patterns "
                "and time-of-day degradation that single tests miss."
            ),
            btn_label="Run Speed Test →",
        )
        _hist_empty.clicked.connect(self.scan_requested.emit)
        # Date-range filter (FILTER-13)
        _date_row = QHBoxLayout()
        _date_row.setSpacing(6)
        _date_row.addWidget(QLabel("Show:"))
        self._date_filter_combo = QComboBox()
        self._date_filter_combo.addItems(["Last 7 days", "Last 30 days", "Last 90 days", "All"])
        self._date_filter_combo.setCurrentIndex(1)  # default: Last 30 days
        self._date_filter_combo.setFixedWidth(140)
        self._date_filter_combo.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        _date_hours = [168.0, 720.0, 2160.0, 999_999.0]
        self._date_filter_combo.currentIndexChanged.connect(
            lambda i: self.set_global_hours(_date_hours[i])
        )
        _date_row.addWidget(self._date_filter_combo)
        _date_row.addStretch()
        hist_body.addLayout(_date_row)

        # ── History trend chart (VIZ-5) ───────────────────────────────────────
        self._hist_chart_fig = Figure(figsize=(1, 1.4), facecolor=BG_CARD)
        self._hist_chart_canvas = FigureCanvas(self._hist_chart_fig)
        self._hist_chart_canvas.setFixedHeight(140)
        self._hist_chart_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        hist_body.addWidget(self._hist_chart_canvas)

        self._hist_stack = QStackedWidget()
        self._hist_stack.addWidget(_hist_empty)   # index 0 — empty state
        self._hist_stack.addWidget(self._hist_table)  # index 1 — data
        self._hist_stack.setCurrentIndex(0)
        hist_body.addWidget(self._hist_stack)

        # ── Modem signal snapshot panel (hidden until a test with modem data) ──
        self._signal_panel = self._build_signal_panel()
        self._signal_panel.setVisible(False)
        root.addWidget(self._signal_panel)

        root.addWidget(hist_card, 2)

    # ── Modem credentials (set by dashboard when modem connects/disconnects) ──

    def set_modem_credentials(self, host: str, password: str) -> None:
        self._zte_host     = host
        self._zte_password = password

    def clear_modem_credentials(self) -> None:
        self._zte_host     = None
        self._zte_password = None

    # ── Signal snapshot panel ─────────────────────────────────────────────────

    def _build_signal_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("sigPanel")
        panel.setStyleSheet(
            f"QFrame#sigPanel {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-left:3px solid {ACCENT}; }}"
        )
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        _lbl_style   = f"color:{TEXT_SECONDARY}; font-size:11px; border:none; background:transparent;"
        _val_style   = f"color:{TEXT_PRIMARY}; font-size:11px; font-weight:bold; border:none; background:transparent;"
        _hdr_style   = f"border:none; border-bottom:1px solid {BORDER}; background:{BG_CARD};"

        # ── header strip ─────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setStyleSheet(f"QFrame {{ {_hdr_style} }}")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 6, 12, 6)
        hdr_lay.setSpacing(8)

        title = QLabel("📡  Modem signal at test time")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold; border:none; background:transparent;"
        )
        self._sig_ts = QLabel("")
        self._sig_ts.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; border:none; background:transparent;")
        self._sig_network_type = QLabel("")
        self._sig_network_type.setStyleSheet(f"color:{ACCENT}; font-size:11px; font-weight:bold; border:none; background:transparent;")
        self._sig_bars = QLabel("")
        self._sig_bars.setStyleSheet(f"color:{GREEN}; font-size:11px; border:none; background:transparent;")

        hdr_lay.addWidget(title)
        hdr_lay.addWidget(self._sig_ts)
        hdr_lay.addStretch()
        hdr_lay.addWidget(self._sig_network_type)
        hdr_lay.addWidget(self._sig_bars)
        root.addWidget(hdr)

        # ── connection strip (operator / cell / IP) ───────────────────────────
        conn = QFrame()
        conn.setStyleSheet(f"QFrame {{ {_hdr_style} }}")
        conn_lay = QHBoxLayout(conn)
        conn_lay.setContentsMargins(12, 5, 12, 5)
        conn_lay.setSpacing(0)

        def _conn_pair(label: str, attr: str) -> None:
            lbl = QLabel(f"{label}: ")
            lbl.setStyleSheet(_lbl_style)
            val = QLabel("—")
            val.setStyleSheet(_val_style)
            setattr(self, attr, val)
            conn_lay.addWidget(lbl)
            conn_lay.addWidget(val)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet(f"border:none; border-left:1px solid {BORDER}; margin:0 16px;")
            conn_lay.addWidget(sep)

        _conn_pair("Operator", "_sig_operator")
        _conn_pair("Cell ID",  "_sig_cell")
        _conn_pair("Public IP","_sig_ip")
        conn_lay.addStretch()
        root.addWidget(conn)

        # ── two-column signal body ─────────────────────────────────────────────
        body = QFrame()
        body.setStyleSheet(f"QFrame {{ background:{BG_CARD}; border:none; }}")
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        def _col_row(label: str, attr: str, parent_lay: QVBoxLayout) -> None:
            h = QHBoxLayout()
            h.setSpacing(6)
            h.setContentsMargins(0, 1, 0, 1)
            lbl_w = QLabel(f"{label}:")
            lbl_w.setFixedWidth(58)
            lbl_w.setStyleSheet(_lbl_style)
            val_w = QLabel("—")
            val_w.setStyleSheet(_val_style)
            setattr(self, attr, val_w)
            h.addWidget(lbl_w)
            h.addWidget(val_w, 1)
            parent_lay.addLayout(h)

        def _signal_col(title: str, title_color: str, border_right: bool) -> QVBoxLayout:
            col = QFrame()
            border = f"border-right:1px solid {BORDER};" if border_right else ""
            col.setStyleSheet(f"QFrame {{ background:{BG_CARD}; border:none; {border} }}")
            lay = QVBoxLayout(col)
            lay.setContentsMargins(12, 8, 12, 8)
            lay.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet(
                f"color:{title_color}; font-size:11px; font-weight:bold;"
                f" border:none; border-bottom:1px solid {BORDER}; background:transparent;"
                f" padding-bottom:4px; margin-bottom:2px;"
            )
            lay.addWidget(t)
            body_lay.addWidget(col, 1)
            return lay

        nr_lay  = _signal_col("5G NR",        ACCENT, border_right=True)
        lte_lay = _signal_col("LTE Primary",   AMBER,  border_right=False)

        _col_row("Band",  "_sig_5g_band",  nr_lay)
        _col_row("RSRP",  "_sig_5g_rsrp",  nr_lay)
        _col_row("SINR",  "_sig_5g_sinr",  nr_lay)
        _col_row("RSRQ",  "_sig_5g_rsrq",  nr_lay)
        _col_row("PCI",   "_sig_5g_pci",   nr_lay)
        _col_row("ARFCN", "_sig_5g_arfcn", nr_lay)
        nr_lay.addStretch()

        _col_row("Band",   "_sig_lte_band",   lte_lay)
        _col_row("RSRP",   "_sig_lte_rsrp",   lte_lay)
        _col_row("SNR",    "_sig_lte_snr",    lte_lay)
        _col_row("RSRQ",   "_sig_lte_rsrq",   lte_lay)
        _col_row("PCI",    "_sig_lte_pci",    lte_lay)
        _col_row("EARFCN", "_sig_lte_earfcn", lte_lay)
        lte_lay.addStretch()

        root.addWidget(body)
        return panel

    def _update_signal_panel(self, sig: dict) -> None:
        import datetime as _dt

        def _s(v) -> str:
            return str(v) if v is not None else "—"

        def _fmt_dbm(v) -> str:
            return f"{float(v):.1f} dBm" if v is not None else "—"

        def _fmt_db(v) -> str:
            return f"{float(v):.1f} dB" if v is not None else "—"

        def _quality(rsrp) -> str:
            if rsrp is None:
                return ""
            v = float(rsrp)
            if v >= -80:  return "  — Excellent"
            if v >= -90:  return "  — Good"
            if v >= -100: return "  — Fair"
            return "  — Poor"

        # Header
        ts = sig.get("ts")
        if ts:
            self._sig_ts.setText(f"  ·  {_dt.datetime.fromtimestamp(ts).strftime('%H:%M:%S')}")
        nt   = sig.get("network_type")
        bars = sig.get("signal_bars")
        self._sig_network_type.setText(f"  {nt}" if nt else "")
        if bars is not None:
            self._sig_bars.setText(f"  {'●' * bars}{'○' * (5 - bars)}  {bars}/5")
        else:
            self._sig_bars.setText("")

        # Connection strip
        mcc, mnc = sig.get("mcc"), sig.get("mnc")
        self._sig_operator.setText(f"{mcc}-{mnc}" if mcc and mnc else "—")
        cell = sig.get("cell_id")
        enb  = sig.get("enb_id")
        self._sig_cell.setText(
            f"{cell}  (eNB: {enb})" if cell and enb else _s(cell)
        )
        self._sig_ip.setText(_s(sig.get("wan_ip")))

        # 5G NR
        nr_rsrp = sig.get("nr5g_rsrp_dbm")
        self._sig_5g_band.setText(_s(sig.get("nr5g_band")))
        self._sig_5g_rsrp.setText(_fmt_dbm(nr_rsrp) + _quality(nr_rsrp))
        self._sig_5g_rsrp.setStyleSheet(
            f"color:{_rsrp_color(nr_rsrp)}; font-size:11px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        self._sig_5g_sinr.setText(_fmt_db(sig.get("nr5g_sinr_db")))
        self._sig_5g_rsrq.setText(_fmt_db(sig.get("nr5g_rsrq_db")))
        self._sig_5g_pci.setText(_s(sig.get("nr5g_pci")))
        self._sig_5g_arfcn.setText(_s(sig.get("nr5g_arfcn")))

        # LTE Primary
        lte_rsrp = sig.get("lte_rsrp_dbm")
        self._sig_lte_band.setText(_s(sig.get("lte_band")))
        self._sig_lte_rsrp.setText(_fmt_dbm(lte_rsrp) + _quality(lte_rsrp))
        self._sig_lte_rsrp.setStyleSheet(
            f"color:{_rsrp_color(lte_rsrp)}; font-size:11px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        self._sig_lte_snr.setText(_fmt_db(sig.get("lte_snr_db")))
        self._sig_lte_rsrq.setText(_fmt_db(sig.get("lte_rsrq_db")))
        self._sig_lte_pci.setText(_s(sig.get("lte_pci")))
        self._sig_lte_earfcn.setText(_s(sig.get("lte_earfcn")))

        self._signal_panel.setVisible(True)

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
        self._fetch_worker.status_changed.connect(self._on_fetch_status)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Auto-refresh server list if it is more than 30 minutes old."""
        super().showEvent(event)
        from ui.table_utils import restore_column_widths
        restore_column_widths(self._hist_table, "speed_test")
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
    def _on_fetch_status(self, msg: str) -> None:
        self._server_hint.setText(msg)
        if self._server_list.count() == 1:
            item = self._server_list.item(0)
            if item:
                item.setText(msg)

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
        self._hist_stack.setCurrentIndex(1)  # hide CTA while test is in progress
        self._lbl_ping.setText("—")
        self._lbl_down.setText("—")
        self._lbl_up.setText("—")
        self._gauge.reset()
        self._anim_current = 0.0
        self._set_status("Connecting to server…")

        # Snapshot BEFORE pause: modem_pause_requested → _on_modem_disconnect →
        # hw_state.clear_modem(), so we must read the plugin snapshot first.
        _zte_host = self._zte_host
        _zte_pw   = self._zte_password
        _modem_snapshot = None
        if not (_zte_host and _zte_pw):
            from modules.network_infrastructure import hw_state
            _modem_snapshot = hw_state.modem_signal
        self.modem_pause_requested.emit()

        self._test_worker = SpeedTestWorker(
            server_id=self._selected_server_id,
            zte_host=_zte_host,
            zte_password=_zte_pw,
            modem_snapshot=_modem_snapshot,
            parent=self,
        )
        self._test_worker.phase_changed.connect(self._on_phase_changed)
        self._test_worker.speed_sample.connect(self._on_speed_sample)
        self._test_worker.result_ready.connect(self._on_result_ready)
        self._test_worker.error.connect(self._on_test_error)
        self._test_worker.start()

    @pyqtSlot(str, str)
    def _on_phase_changed(self, phase: str, message: str) -> None:
        if not self.isVisible():
            return
        self._set_status(message)
        if phase == "ping":
            # Parse ping value from message e.g. "Ping: 50 ms → …"
            try:
                ping_val = float(message.split(":")[1].split("ms")[0].strip())
                self._lbl_ping.setText(f"{ping_val:.0f}")
            except (IndexError, ValueError):
                pass  # non-fatal
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
        if not self.isVisible():
            return
        self._anim_phase  = phase
        self._anim_target = mbps
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    @pyqtSlot(object)
    def _on_result_ready(self, result: object) -> None:
        # Always: unblock modem monitoring, reset button, emit signal.
        self.modem_resume_requested.emit()
        self._anim_timer.stop()
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶   Run Speed Test")
        self.test_completed.emit(result)

        sig = getattr(result, "modem_signal", None)

        # Always: persist to database regardless of page visibility.
        if self._store:
            try:
                self._store.record_speed_test(
                    download_mbps=result.download_mbps,
                    upload_mbps=result.upload_mbps,
                    ping_ms=result.ping_ms,
                    server_name=result.server_name,
                    server_city=result.server_city,
                    server_country=result.server_country,
                    network_type=sig.get("network_type")   if sig else None,
                    signal_bars=sig.get("signal_bars")     if sig else None,
                    nr5g_rsrp=sig.get("nr5g_rsrp_dbm")    if sig else None,
                    nr5g_sinr=sig.get("nr5g_sinr_db")     if sig else None,
                    nr5g_band=sig.get("nr5g_band")         if sig else None,
                    lte_rsrp=sig.get("lte_rsrp_dbm")      if sig else None,
                    lte_band=sig.get("lte_band")           if sig else None,
                    cell_id=sig.get("cell_id")             if sig else None,
                    enb_id=sig.get("enb_id")               if sig else None,
                    mcc=sig.get("mcc")                     if sig else None,
                    mnc=sig.get("mnc")                     if sig else None,
                    wan_ip=sig.get("wan_ip")               if sig else None,
                    nr5g_rsrq=sig.get("nr5g_rsrq_db")     if sig else None,
                    nr5g_pci=sig.get("nr5g_pci")           if sig else None,
                    nr5g_arfcn=sig.get("nr5g_arfcn")       if sig else None,
                    lte_snr=sig.get("lte_snr_db")          if sig else None,
                    lte_rsrq=sig.get("lte_rsrq_db")        if sig else None,
                    lte_pci=sig.get("lte_pci")             if sig else None,
                    lte_earfcn=sig.get("lte_earfcn")       if sig else None,
                )
            except Exception:
                pass  # never let a DB write break the UI

        # Skip pure UI updates when page is not in view.
        if not self.isVisible():
            return

        self._lbl_ping.setText(f"{result.ping_ms:.0f}")
        self._start_tile_count_up(result.download_mbps, result.upload_mbps)

        # Animate gauge to final download value, then hold
        self._anim_phase   = "download"
        self._anim_target  = result.download_mbps
        self._anim_timer.start()
        self._set_status(
            f"✓  {result.server_name}, {result.server_city} — "
            f"↓ {result.download_mbps:.1f}  ↑ {result.upload_mbps:.1f}  Mbps"
        )

        # Show modem signal snapshot panel if present
        if sig:
            self._update_signal_panel(sig)

        # Add to history
        self._add_history_row(result)

    def _start_tile_count_up(self, download_mbps: float, upload_mbps: float) -> None:
        """ANIM-5: Tween the download/upload stat tiles from 0 → final value (600 ms, OutExpo)."""
        from ui.theme import _reduce_motion
        if _reduce_motion():
            self._lbl_down.setText(f"{download_mbps:.1f}")
            self._lbl_up.setText(f"{upload_mbps:.1f}")
            return

        def _make_anim(target: float, label) -> QVariantAnimation:
            anim = QVariantAnimation(self)
            anim.setDuration(600)
            anim.setEasingCurve(QEasingCurve.Type.OutExpo)
            anim.setStartValue(0.0)
            anim.setEndValue(float(target))
            anim.valueChanged.connect(lambda v, lbl=label: lbl.setText(f"{v:.1f}"))
            anim.start()
            return anim

        # Stop any in-flight animations from a previous test run
        if self._down_count_anim:
            self._down_count_anim.stop()
        if self._up_count_anim:
            self._up_count_anim.stop()

        self._down_count_anim = _make_anim(download_mbps, self._lbl_down)
        self._up_count_anim   = _make_anim(upload_mbps,   self._lbl_up)

    @pyqtSlot(str)
    def _on_test_error(self, msg: str) -> None:
        self.modem_resume_requested.emit()
        self._anim_timer.stop()
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶   Run Speed Test")
        if not self.isVisible():
            return
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
        self._hist_stack.setCurrentIndex(1)  # reveal table
        self._hist_table.insertRow(0)  # newest at top
        sig = None

        if result:
            backend = getattr(result, "backend", "") or "OK"
            backend_color = GREEN if backend == "Ookla CLI" else AMBER
            sig = getattr(result, "modem_signal", None)
            band = (sig.get("nr5g_band") or sig.get("lte_band") or "—") if sig else "—"
            rsrp = (sig.get("nr5g_rsrp_dbm") if sig and sig.get("nr5g_rsrp_dbm") is not None
                    else (sig.get("lte_rsrp_dbm") if sig else None))
            rsrp_str = f"{rsrp:.1f}" if rsrp is not None else "—"
            rsrp_color = _rsrp_color(rsrp)
            lte_sinr_str, lte_sinr_color = _fmt_sinr(sig.get("lte_snr_db")  if sig else None)
            nr5_sinr_str, nr5_sinr_color = _fmt_sinr(sig.get("nr5g_sinr_db") if sig else None)
            cells = [
                result.timestamp.replace("T", "  "),
                result.server_name,
                f"{result.server_city}, {result.server_country}",
                f"{result.ping_ms:.0f}",
                f"{result.download_mbps:.1f} Mbps",
                f"{result.upload_mbps:.1f} Mbps",
                band,
                rsrp_str,
                lte_sinr_str,
                nr5_sinr_str,
                backend,
            ]
            colors = [None, None, None, None,
                      GREEN if result.download_mbps >= 25 else AMBER,
                      GREEN if result.upload_mbps >= 5  else AMBER,
                      None, rsrp_color, lte_sinr_color, nr5_sinr_color, backend_color]
        else:
            cells = ["—", "—", "—", "—", "—", "—", "—", "—", "—", "—", "Error"]
            colors = [None]*10 + [RED]

        for col, (val, col_color) in enumerate(zip(cells, colors)):
            item = QTableWidgetItem(str(val))
            if col_color:
                item.setForeground(QColor(col_color))
            if col == 0:
                item.setData(Qt.ItemDataRole.UserRole, sig)
            if col == 4 and result:
                item.setData(Qt.ItemDataRole.UserRole, result.download_mbps)
            self._hist_table.setItem(0, col, item)

        self._hist_table.scrollToTop()
        self._apply_baseline_markers()
        self._refresh_history_chart()

    # ── Status helper ─────────────────────────────────────────────────────────
    @staticmethod
    def _point_to_sig_dict(p) -> Optional[dict]:
        """Reconstruct a signal dict from a SpeedTestPoint for _update_signal_panel."""
        if not any([p.network_type, p.signal_bars is not None,
                    p.nr5g_rsrp is not None, p.lte_rsrp is not None]):
            return None
        return {
            "ts":            p.ts,
            "network_type":  p.network_type,
            "signal_bars":   p.signal_bars,
            "mcc":           getattr(p, "mcc", None),
            "mnc":           getattr(p, "mnc", None),
            "cell_id":       getattr(p, "cell_id", None),
            "enb_id":        getattr(p, "enb_id", None),
            "wan_ip":        getattr(p, "wan_ip", None),
            "nr5g_band":     p.nr5g_band,
            "nr5g_rsrp_dbm": p.nr5g_rsrp,
            "nr5g_sinr_db":  p.nr5g_sinr,
            "nr5g_rsrq_db":  getattr(p, "nr5g_rsrq", None),
            "nr5g_pci":      getattr(p, "nr5g_pci", None),
            "nr5g_arfcn":    getattr(p, "nr5g_arfcn", None),
            "lte_band":      p.lte_band,
            "lte_rsrp_dbm":  p.lte_rsrp,
            "lte_snr_db":    getattr(p, "lte_snr", None),
            "lte_rsrq_db":   getattr(p, "lte_rsrq", None),
            "lte_pci":       getattr(p, "lte_pci", None),
            "lte_earfcn":    getattr(p, "lte_earfcn", None),
        }

    def set_global_hours(self, hours: float) -> None:
        self._history_hours = max(1.0, hours)
        if not self.isVisible():
            return
        if self._test_worker is not None and self._test_worker.isRunning():
            self._test_worker.quit()
            self._test_worker.wait(400)
        self._hist_table.setRowCount(0)
        self._load_history_from_db()

    def _load_history_from_db(self) -> None:
        """Populate history table from MetricStore on page load."""
        if not self._store:
            return
        try:
            points = self._store.query_speed_test_history(hours=self._history_hours)
            for p in points:
                import datetime as _dt
                ts_str = _dt.datetime.fromtimestamp(p.ts).strftime("%Y-%m-%d  %H:%M:%S")
                row = self._hist_table.rowCount()
                self._hist_table.insertRow(row)
                band = getattr(p, "nr5g_band", None) or getattr(p, "lte_band", None) or "—"
                rsrp = (getattr(p, "nr5g_rsrp", None)
                        if getattr(p, "nr5g_rsrp", None) is not None
                        else getattr(p, "lte_rsrp", None))
                rsrp_str = f"{rsrp:.1f}" if rsrp is not None else "—"
                lte_sinr_str, lte_sinr_color = _fmt_sinr(getattr(p, "lte_snr",   None))
                nr5_sinr_str, nr5_sinr_color = _fmt_sinr(getattr(p, "nr5g_sinr", None))
                sig = self._point_to_sig_dict(p)
                cells = [
                    ts_str,
                    p.server_name or "",
                    f"{p.server_city or ''}, {p.server_country or ''}".strip(", "),
                    f"{p.ping_ms:.0f}",
                    f"{p.download_mbps:.1f} Mbps",
                    f"{p.upload_mbps:.1f} Mbps",
                    band,
                    rsrp_str,
                    lte_sinr_str,
                    nr5_sinr_str,
                    "OK",
                ]
                clrs = [None, None, None, None,
                        GREEN if p.download_mbps >= 25 else AMBER,
                        GREEN if p.upload_mbps >= 5  else AMBER,
                        None, _rsrp_color(rsrp), lte_sinr_color, nr5_sinr_color, GREEN]
                for col, (val, col_color) in enumerate(zip(cells, clrs)):
                    item = QTableWidgetItem(str(val))
                    if col_color:
                        item.setForeground(QColor(col_color))
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, sig)
                    if col == 4:
                        item.setData(Qt.ItemDataRole.UserRole, p.download_mbps)
                    self._hist_table.setItem(row, col, item)
            if self._hist_table.rowCount() > 0:
                self._hist_stack.setCurrentIndex(1)
        except Exception:
            pass  # DB not available yet is fine
        self._apply_baseline_markers()
        self._refresh_history_chart()

    def _disconnect_hist_hover(self) -> None:
        if self._hist_chart_cid is not None:
            try:
                self._hist_chart_canvas.mpl_disconnect(self._hist_chart_cid)
            except Exception:
                pass  # non-fatal
            self._hist_chart_cid = None

    def hideEvent(self, event) -> None:
        self._disconnect_hist_hover()
        super().hideEvent(event)

    def _refresh_history_chart(self) -> None:
        """VIZ-5: Rebuild the download/upload history line chart."""
        import datetime as _dt
        import matplotlib.dates as _mdates

        self._disconnect_hist_hover()
        fig = self._hist_chart_fig
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor(CHART_PLOT_BG)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color(BORDER)
        ax.spines["left"].set_color(BORDER)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
        ax.grid(True, color=CHART_GRID, linewidth=0.8, linestyle="-")
        ax.set_ylabel("Mbps", fontsize=8, color=TEXT_SECONDARY)

        if not self._store:
            fig.subplots_adjust(left=0.07, right=0.99, top=0.90, bottom=0.22)
            self._hist_chart_canvas.draw_idle()
            return

        try:
            points = self._store.query_speed_test_history(hours=self._history_hours)
        except Exception:
            points = []

        if len(points) < 2:
            ax.text(0.5, 0.5, "Not enough data yet — run more speed tests",
                    ha="center", va="center", transform=ax.transAxes,
                    color=TEXT_SECONDARY, fontsize=9)
            fig.subplots_adjust(left=0.07, right=0.99, top=0.90, bottom=0.22)
            self._hist_chart_canvas.draw_idle()
            return

        pts_sorted = sorted(points, key=lambda p: p.ts)
        dates = [_dt.datetime.fromtimestamp(p.ts) for p in pts_sorted]
        dl    = [p.download_mbps for p in pts_sorted]
        ul    = [p.upload_mbps   for p in pts_sorted]

        ax.plot(dates, dl, color=_COLOR_DOWNLOAD, linewidth=1.5,
                marker="o", markersize=3.5, label="↓ Download", zorder=3)
        ax.plot(dates, ul, color=_COLOR_UPLOAD, linewidth=1.5,
                marker="o", markersize=3.5, label="↑ Upload", zorder=3)

        ax.xaxis.set_major_formatter(_mdates.DateFormatter("%m/%d"))
        ax.xaxis.set_major_locator(_mdates.AutoDateLocator(maxticks=6))
        ax.legend(loc="upper left", fontsize=8, frameon=False)

        fig.subplots_adjust(left=0.07, right=0.99, top=0.90, bottom=0.25)
        self._hist_chart_canvas.draw_idle()

        self._hist_chart_pts = list(zip(dates, dl, ul, pts_sorted))

        annot = ax.annotate(
            "", xy=(0, 0), xytext=(8, 8), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc=BG_CARD, ec=BORDER, lw=0.8),
            fontsize=8, color=TEXT_PRIMARY,
            arrowprops=dict(arrowstyle="->", color=TEXT_SECONDARY, lw=0.8),
        )
        annot.set_visible(False)
        self._hist_chart_annot = annot

        def _on_hover(event):
            if event.inaxes != ax or not self._hist_chart_pts:
                annot.set_visible(False)
                self._hist_chart_canvas.draw_idle()
                return
            x_cur = event.xdata
            best_i, best_d = 0, float("inf")
            for i, (d, _dl, _ul, _p) in enumerate(self._hist_chart_pts):
                dist = abs(_mdates.date2num(d) - x_cur)
                if dist < best_d:
                    best_d, best_i = dist, i
            d, dl_v, ul_v, p = self._hist_chart_pts[best_i]
            ts_str = d.strftime("%Y-%m-%d %H:%M")
            annot.set_text(
                f"{ts_str}\n↓ {dl_v:.1f} Mbps  ↑ {ul_v:.1f} Mbps\n"
                f"Ping: {p.ping_ms:.0f} ms"
            )
            annot.xy = (_mdates.date2num(d), dl_v)
            annot.set_visible(True)
            self._hist_chart_canvas.draw_idle()

        self._hist_chart_cid = self._hist_chart_canvas.mpl_connect(
            "motion_notify_event", _on_hover
        )

    @pyqtSlot()
    def _on_history_row_selected(self) -> None:
        row = self._hist_table.currentRow()
        if row < 0:
            return
        item = self._hist_table.item(row, 0)
        if item is None:
            return
        sig = item.data(Qt.ItemDataRole.UserRole)
        if sig:
            self._update_signal_panel(sig)
        else:
            self._signal_panel.setVisible(False)

    def _set_status(self, text: str) -> None:
        self._status_lbl.setText(text)

    # ── ACT-4: speed test baseline ────────────────────────────────────────────

    def _on_hist_context_menu(self, pos) -> None:
        from PyQt6.QtCore import QSettings
        from PyQt6.QtWidgets import QMenu
        row = self._hist_table.rowAt(pos.y())
        if row < 0:
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        baseline_ts = str(qs.value("speed_test/baseline_ts", "") or "")
        it0 = self._hist_table.item(row, 0)
        if it0 is None:
            return
        row_ts = it0.text().lstrip("★ ").strip()
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; font-size:11px;"
            f" border:1px solid {BORDER}; }}"
            f"QMenu::item:selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        if row_ts == baseline_ts:
            act = menu.addAction("✕  Clear baseline")
            act.triggered.connect(self._clear_baseline)
        else:
            act = menu.addAction("★  Set as baseline")
            act.triggered.connect(lambda: self._set_baseline(row))
        menu.exec(self._hist_table.viewport().mapToGlobal(pos))

    def _set_baseline(self, row: int) -> None:
        from PyQt6.QtCore import QSettings
        it0 = self._hist_table.item(row, 0)
        if it0 is None:
            return
        ts_str = it0.text().lstrip("★ ").strip()
        QSettings("NetSentinel", "NetSentinel").setValue("speed_test/baseline_ts", ts_str)
        self._apply_baseline_markers()

    def _clear_baseline(self) -> None:
        from PyQt6.QtCore import QSettings
        QSettings("NetSentinel", "NetSentinel").remove("speed_test/baseline_ts")
        self._apply_baseline_markers()

    def _apply_baseline_markers(self) -> None:
        from PyQt6.QtCore import QSettings
        qs = QSettings("NetSentinel", "NetSentinel")
        baseline_ts_str = str(qs.value("speed_test/baseline_ts", "") or "")

        baseline_row = -1
        baseline_dl = 0.0
        for r in range(self._hist_table.rowCount()):
            it = self._hist_table.item(r, 0)
            if it is None:
                continue
            raw = it.text().lstrip("★ ").strip()
            if baseline_ts_str and raw == baseline_ts_str:
                baseline_row = r
                dl_it = self._hist_table.item(r, 4)
                if dl_it is not None:
                    v = dl_it.data(Qt.ItemDataRole.UserRole)
                    if v is not None:
                        try:
                            baseline_dl = float(v)
                        except (TypeError, ValueError):
                            pass  # non-fatal
                break

        for r in range(self._hist_table.rowCount()):
            it0 = self._hist_table.item(r, 0)
            if it0 is None:
                continue
            raw_ts = it0.text().lstrip("★ ").strip()
            if r == baseline_row:
                it0.setText(f"★  {raw_ts}")
                it0.setForeground(QColor(ACCENT))
            else:
                it0.setText(raw_ts)
                it0.setForeground(QColor(TEXT_PRIMARY))

            dl_it = self._hist_table.item(r, 4)
            if dl_it is None:
                continue
            raw_dl = dl_it.data(Qt.ItemDataRole.UserRole)
            if raw_dl is None:
                continue
            try:
                dl = float(raw_dl)
            except (TypeError, ValueError):
                continue

            if baseline_dl > 0 and r != baseline_row:
                delta = dl - baseline_dl
                sign = "↑" if delta >= 0 else "↓"
                c = GREEN if delta >= 0 else RED
                dl_it.setText(f"{dl:.1f}  {delta:+.0f} {sign}")
                dl_it.setForeground(QColor(c))
            else:
                dl_it.setText(f"{dl:.1f} Mbps")
                dl_it.setForeground(QColor(GREEN if dl >= 25 else AMBER))
