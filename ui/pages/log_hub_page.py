"""
LogHubPage — unified monitor for all NetSentinel log sources.

One chronological table with a source toggle bar. Toggling a source
controls both visibility and (for Modem/Mesh) whether data is logged to DB.

Sources:
  Network RTT  — continuous ping logger entries (CSV + live)
  5G Modem     — periodic signal snapshots (DB + live, user-configurable interval)
  Mesh         — periodic status snapshots (DB + live, user-configurable interval)
  Syslog       — received syslog messages (live only)
  SNMP         — received SNMP traps (live only)

QSettings keys (prefix "logging/"):
  net_enabled         bool   default True
  modem_enabled       bool   default False
  modem_interval_min  int    default 5
  mesh_enabled        bool   default False
  mesh_interval_min   int    default 5
  syslog_enabled      bool   default True
  snmp_enabled        bool   default True
"""
from __future__ import annotations

import csv as _csv
import datetime as _dt
import os as _os
import time as _t
from typing import Optional

from PyQt6.QtCore import Qt, QEvent, QObject, QSettings, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem,
    QTimeEdit, QToolButton, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BG_HOVER, BG_ALT_ROW,
    BORDER, CARD_RADIUS, GREEN, RED, TABLE_SEL, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, TH_BG, TH_TEXT,
)

_MAX_ROWS = 2000
_LIVE_CHALLENGE_COOLDOWN = 60.0

# Source key → (display label, accent colour)
_SOURCES: dict[str, tuple[str, str]] = {
    "net":    ("RTT",         ACCENT),
    "modem":  ("5G Modem",    GREEN),
    "mesh":   ("Mesh Router", AMBER),
    "syslog": ("Syslog",      TEXT_SECONDARY),
    "snmp":   ("SNMP Traps",  RED),
    "plugin": ("PLUGIN",      "#A78BFA"),
}
_LABEL_TO_KEY = {label: key for key, (label, _) in _SOURCES.items()}

_SYSLOG_SEVERITY_COLOR = {
    "EMERG": RED, "ALERT": RED, "CRIT": RED,
    "ERR": AMBER, "WARNING": AMBER,
    "NOTICE": TEXT_PRIMARY, "INFO": TEXT_PRIMARY, "DEBUG": TEXT_MUTED,
}

_SOURCE_TIPS: dict[str, str] = {
    "net":    "Network RTT — continuous latency measurements to gateway and DNS (higher is worse).",
    "modem":  "5G Modem — periodic signal snapshots: RSRP, SINR, band. Set interval in Scan Config.",
    "mesh":   "Mesh Router — periodic TP-Link Deco status snapshots. Set interval in Scan Config.",
    "syslog": "Syslog — UDP messages received on port 514 from routers and managed switches.",
    "snmp":   "SNMP Traps — trap PDUs received on port 162 from network devices.",
    "plugin": "Plugin — log entries emitted by installed NetSentinel plugins.",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _source_key(label: str) -> str:
    return _LABEL_TO_KEY.get(label, label.lower())


def _fmt_ts(ts: float) -> str:
    dt = _dt.datetime.fromtimestamp(ts)
    if _t.time() - ts < 86400:
        return dt.strftime("%H:%M:%S")
    return dt.strftime("%m-%d %H:%M")


def _status_color(status: str) -> str:
    return {"OK": GREEN, "SLOW": AMBER, "FAIL": RED}.get(status.upper(), TEXT_SECONDARY)


class _JKNavFilter(QObject):
    """J/K row navigation event filter for QTableWidget."""
    def __init__(self, table, parent=None) -> None:
        super().__init__(parent)
        self._table = table

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and obj is self._table.viewport():
            key = event.key()
            if key in (Qt.Key.Key_J, Qt.Key.Key_K):
                cur = self._table.currentRow()
                step = 1 if key == Qt.Key.Key_J else -1
                target = max(0, min(self._table.rowCount() - 1, cur + step))
                self._table.setCurrentCell(target, self._table.currentColumn())
                return True
        return False


def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(False)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(26)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setStyleSheet(
        f"QTableWidget {{ background:{BG_CARD}; border:none; font-size:11px; color:{TEXT_PRIMARY}; }}"
        f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT}; font-size:11px;"
        f" font-weight:bold; padding:4px 8px; border:none; }}"
        f"QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        f"QTableWidget::item:hover {{ background:{BG_HOVER}; }}"
        f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
    )
    return t


# ── Live challenge builder (preserved) ───────────────────────────────────────

def _build_live_scenario(entry, consecutive_fails: int = 0):
    """Return a one-step LabScenario for an interesting log entry, or None."""
    from modules.lab_scenarios import LabScenario, LabStep
    if entry.arp_event and entry.arp_event.startswith("NEW"):
        return LabScenario(
            id="live_new_device",
            title="New Device Detected",
            goal="A new device just appeared on your network. Investigate whether it belongs here.",
            effort="S",
            steps=[LabStep(
                instruction=(
                    f"A new device appeared: {entry.arp_event}. "
                    "Run a scan to see all devices on your network and confirm it belongs."
                ),
                scan_type="rogue",
                hint="Look at the Risk column. An unexpected vendor or blank hostname may indicate a rogue device.",
                solution=(
                    "If the device has Risk = HIGH or an unexpected vendor, record its MAC address. "
                    "If it's one of your devices, whitelist it from the Overview page."
                ),
            )],
        )
    if entry.dns_ms >= 0 and entry.dns_ms > 200:
        return LabScenario(
            id="live_slow_dns",
            title="Slow DNS Detected",
            goal=f"DNS latency spiked to {entry.dns_ms:.0f} ms. Diagnose your resolver.",
            effort="S",
            steps=[LabStep(
                instruction=(
                    f"Your DNS resolver just returned {entry.dns_ms:.0f} ms — above the 200 ms threshold. "
                    "Run the DNS check to measure it formally over 60 seconds."
                ),
                scan_type="dns",
                hint="A single high reading may be transient. The 60-second scan shows whether outages correlate with DNS failures.",
                solution=(
                    "If average DNS is consistently high, switch to 1.1.1.1 (Cloudflare) or "
                    "8.8.8.8 (Google) in your router's DNS settings."
                ),
            )],
        )
    if consecutive_fails >= 3:
        return LabScenario(
            id="live_connectivity_fail",
            title="Connectivity Issues Detected",
            goal="Multiple consecutive failures were logged. Diagnose your connection.",
            effort="S",
            steps=[LabStep(
                instruction=(
                    f"Your logger recorded 3+ consecutive FAIL results to {entry.host}. "
                    "Run the DNS and stability check to determine whether this is a routing or DNS issue."
                ),
                scan_type="dns",
                hint="If pings fail but DNS works, the fault is upstream routing. If both fail together, try your DNS server settings.",
                solution=(
                    "Check your router first. If ping to 8.8.8.8 also fails, contact your ISP. "
                    "If only DNS fails, change the DNS server in your router settings to 1.1.1.1."
                ),
            )],
        )
    return None


# ── LogHubPage ────────────────────────────────────────────────────────────────

class LogHubPage(QWidget):
    """
    Unified monitor — all log sources in one chronological table.

    Source toggle bar controls logging and visibility per source.
    Modem and Mesh have user-configurable log intervals (1–60 min).

    Preserved public API:
        add_log_entry(entry)   — network RTT live entry from LoggerWorker
        add_modem_entry(data)  — modem signal dict from dashboard
        add_mesh_entry(data)   — mesh status dict from dashboard
        on_syslog_message(msg) — syslog message object
        on_snmp_trap(trap)     — SNMP trap object
        show_network_log()     — ensure RTT visible + scroll to top
    """

    animate_requested       = pyqtSignal(object)
    live_challenge_detected = pyqtSignal(object)
    logging_active_changed  = pyqtSignal(bool)
    navigate_to             = pyqtSignal(str)

    _HEADERS = ["Time", "Source", "Host", "Event", "Detail", "Status"]

    def __init__(self, store=None, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._store = store
        self._popover = None
        self._entries:             list[dict] = []
        self._consecutive_fails:   int        = 0
        self._last_live_challenge: float      = 0.0
        self._challenge_banner_ts: float      = 0.0
        self._cap_shown:           bool       = False
        self._anim_row_ts:         list[float] = []
        self._toggle_btns:    dict[str, QPushButton] = {}
        self._db_btns:        dict[str, QPushButton] = {}
        self._interval_combos: dict[str, QComboBox]  = {}
        self._all_btn:         Optional[QPushButton]  = None
        self._is_history_mode: bool = False
        self._src_bold_font = QFont()
        self._src_bold_font.setBold(True)
        self._src_bold_font.setPointSize(8)

        self._setup_ui()
        QTimer.singleShot(300, self._load_history)

    def set_popover(self, popover) -> None:
        self._popover = popover

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QLabel("Monitor")
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"QLabel {{ background:{BG_DARK}; font-size:15px; font-weight:bold;"
            f" color:{TEXT_PRIMARY}; padding:0 16px; border-bottom:1px solid {BORDER}; }}"
        )
        root.addWidget(hdr)

        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(16, 10, 16, 12)
        inner_lay.setSpacing(8)

        inner_lay.addWidget(self._build_scan_config_panel())
        inner_lay.addWidget(self._build_control_bar())
        inner_lay.addWidget(self._build_logged_sources_bar())

        card = QFrame()
        card.setObjectName("logcard")
        card.setStyleSheet(
            f"QFrame#logcard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # ── History range bar (LOG-7) ─────────────────────────────────────────
        self._history_bar = QFrame()
        self._history_bar.setVisible(False)
        self._history_bar.setStyleSheet(
            f"QFrame {{ background:{BG_HOVER}; border-bottom:1px solid {BORDER};"
            f" border-radius:0; padding:0; }}"
        )
        _hb_lay = QHBoxLayout(self._history_bar)
        _hb_lay.setContentsMargins(12, 6, 12, 6)
        _hb_lay.setSpacing(8)
        _hb_from_lbl = QLabel("From:")
        _hb_from_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        from PyQt6.QtCore import QDate, QTime
        _today = _dt.date.today()
        _yesterday = _today - _dt.timedelta(days=1)
        self._hist_from_date = QDateEdit()
        self._hist_from_date.setCalendarPopup(True)
        self._hist_from_date.setDate(QDate(_yesterday.year, _yesterday.month, _yesterday.day))
        self._hist_from_date.setFixedWidth(100)
        self._hist_from_time = QTimeEdit()
        self._hist_from_time.setTime(QTime(0, 0))
        self._hist_from_time.setFixedWidth(72)
        _hb_to_lbl = QLabel("To:")
        _hb_to_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._hist_to_date = QDateEdit()
        self._hist_to_date.setCalendarPopup(True)
        self._hist_to_date.setDate(QDate(_today.year, _today.month, _today.day))
        self._hist_to_date.setFixedWidth(100)
        self._hist_to_time = QTimeEdit()
        self._hist_to_time.setTime(QTime(23, 59))
        self._hist_to_time.setFixedWidth(72)
        for _w in (self._hist_from_date, self._hist_from_time,
                   self._hist_to_date, self._hist_to_time):
            _w.setStyleSheet(
                f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:3px;"
                f" padding:1px 4px; font-size:11px; color:{TEXT_PRIMARY};"
            )
        _hb_load = QPushButton("Load")
        _hb_load.setFixedHeight(24)
        _hb_load.setCursor(Qt.CursorShape.PointingHandCursor)
        _hb_load.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" border-radius:3px; padding:0 12px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#1a6fc4; }}"
        )
        _hb_load.clicked.connect(self._load_history_range)
        _hb_export = QPushButton("Export →")
        _hb_export.setFlat(True)
        _hb_export.setCursor(Qt.CursorShape.PointingHandCursor)
        _hb_export.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:#1a6fc4; text-decoration:underline; }}"
        )
        _hb_export.clicked.connect(self._open_export_dialog)
        _hb_lay.addWidget(_hb_from_lbl)
        _hb_lay.addWidget(self._hist_from_date)
        _hb_lay.addWidget(self._hist_from_time)
        _hb_lay.addWidget(_hb_to_lbl)
        _hb_lay.addWidget(self._hist_to_date)
        _hb_lay.addWidget(self._hist_to_time)
        _hb_lay.addWidget(_hb_load)
        _hb_lay.addStretch()
        _hb_lay.addWidget(_hb_export)
        card_lay.addWidget(self._history_bar)

        # ── Live-challenge banner (LOG-5) ─────────────────────────────────────
        self._challenge_banner = QFrame()
        self._challenge_banner.setVisible(False)
        self._challenge_banner.setStyleSheet(
            f"QFrame {{ background:{AMBER}22; border-bottom:1px solid {AMBER}55;"
            f" border-radius:0; padding:0; }}"
        )
        _cb_lay = QHBoxLayout(self._challenge_banner)
        _cb_lay.setContentsMargins(12, 6, 12, 6)
        _cb_lay.setSpacing(8)
        self._challenge_time_lbl = QLabel("")
        self._challenge_time_lbl.setStyleSheet(
            f"font-size:11px; color:{AMBER}; background:transparent; border:none;"
        )
        _cb_view_btn = QPushButton("View alert →")
        _cb_view_btn.setFlat(True)
        _cb_view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _cb_view_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:#1a6fc4; text-decoration:underline; }}"
        )
        _cb_view_btn.clicked.connect(lambda: self.navigate_to.emit("Notifications"))
        _cb_x = QPushButton("×")
        _cb_x.setFixedSize(18, 18)
        _cb_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cb_x.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:13px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        _cb_x.clicked.connect(self._hide_challenge_banner)
        _cb_lay.addWidget(self._challenge_time_lbl, 1)
        _cb_lay.addWidget(_cb_view_btn)
        _cb_lay.addWidget(_cb_x)

        self._challenge_timer = QTimer(self)
        self._challenge_timer.setSingleShot(True)
        self._challenge_timer.timeout.connect(self._hide_challenge_banner)
        card_lay.addWidget(self._challenge_banner)

        # ── Row-cap banner (LOG-4) ─────────────────────────────────────────────
        self._cap_banner = QFrame()
        self._cap_banner.setVisible(False)
        self._cap_banner.setStyleSheet(
            f"QFrame {{ background:{BG_HOVER}; border-bottom:1px solid {BORDER};"
            f" border-radius:0; padding:0; }}"
        )
        _cap_lay = QHBoxLayout(self._cap_banner)
        _cap_lay.setContentsMargins(12, 5, 12, 5)
        _cap_lay.setSpacing(8)
        _cap_lbl = QLabel(
            f"Showing last {_MAX_ROWS:,} entries — older entries are in your database."
        )
        _cap_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        _cap_export_btn = QPushButton("Export log →")
        _cap_export_btn.setFlat(True)
        _cap_export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _cap_export_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:#1a6fc4; text-decoration:underline; }}"
        )
        _cap_export_btn.clicked.connect(self._open_export_dialog)
        _cap_lay.addWidget(_cap_lbl, 1)
        _cap_lay.addWidget(_cap_export_btn)
        card_lay.addWidget(self._cap_banner)

        self._table = _make_table(self._HEADERS)
        self._jk_filter = _JKNavFilter(self._table, self)
        self._table.viewport().installEventFilter(self._jk_filter)
        self._table.setColumnWidth(0, 130)
        self._table.setColumnWidth(1, 68)
        self._table.setColumnWidth(2, 150)
        self._table.setColumnWidth(3, 145)
        self._table.setColumnWidth(5, 72)
        self._table.horizontalHeader().setSectionResizeMode(
            4, self._table.horizontalHeader().ResizeMode.Stretch
        )
        # Context menu always available (Device Info only when popover set)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        card_lay.addWidget(self._table)
        from ui.empty_state import EmptyStateOverlay
        EmptyStateOverlay(
            self._table, "≡",
            "No log entries yet",
            "Entries appear here as network events arrive. Enable sources above.",
        )

        # ALERT-4: inline alert correlation panel (hidden until triggered)
        self._alert_corr_panel = QFrame()
        self._alert_corr_panel.setVisible(False)
        self._alert_corr_panel.setStyleSheet(
            f"QFrame {{ background:{BG_HOVER}; border-top:1px solid {BORDER}; }}"
        )
        _acp_lay = QVBoxLayout(self._alert_corr_panel)
        _acp_lay.setContentsMargins(12, 8, 12, 8)
        _acp_lay.setSpacing(4)
        _acp_hdr = QHBoxLayout()
        _acp_title = QLabel("Alerts near this time (±10 min)")
        _acp_title.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        _acp_close = QPushButton("×")
        _acp_close.setFixedSize(18, 18)
        _acp_close.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none; font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        _acp_close.clicked.connect(lambda: self._alert_corr_panel.setVisible(False))
        _acp_hdr.addWidget(_acp_title, 1)
        _acp_hdr.addWidget(_acp_close)
        _acp_lay.addLayout(_acp_hdr)
        self._alert_corr_rows_lay = QVBoxLayout()
        self._alert_corr_rows_lay.setSpacing(2)
        _acp_lay.addLayout(self._alert_corr_rows_lay)
        card_lay.addWidget(self._alert_corr_panel)
        inner_lay.addWidget(card, 1)

        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG_DARK}; border:none; }}")
        root.addWidget(scroll, 1)

    def _build_scan_config_panel(self) -> QWidget:
        """Collapsible 'Scan Configuration' accordion — module toggles and durations."""
        _qs = QSettings("NetSentinel", "NetSentinel")

        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        # ── Toggle header ──────────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        hdr_lay = QHBoxLayout(header)
        hdr_lay.setContentsMargins(12, 6, 12, 6)
        hdr_lay.setSpacing(8)

        toggle_btn = QToolButton()
        toggle_btn.setText("▶  Scan Configuration")
        toggle_btn.setCheckable(True)
        toggle_btn.setChecked(False)
        toggle_btn.setStyleSheet(
            f"QToolButton {{ background:transparent; color:{TEXT_MUTED}; font-size:11px;"
            f" font-weight:bold; border:none; padding:0; }}"
            f"QToolButton:checked {{ color:{ACCENT}; }}"
            f"QToolButton::menu-indicator {{ image:none; }}"
        )
        hdr_lay.addWidget(toggle_btn)
        hdr_lay.addStretch()

        sub = QLabel("Controls which modules run when you click Scan")
        sub.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
        )
        hdr_lay.addWidget(sub)
        outer_lay.addWidget(header)

        # ── Body (hidden by default) ───────────────────────────────────────────
        body = QFrame()
        body.setVisible(False)
        body.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-top:none; border-radius:0 0 {CARD_RADIUS} {CARD_RADIUS}; }}"
        )
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(16, 10, 16, 12)
        body_lay.setSpacing(8)

        _chk_qss = (
            f"QCheckBox {{ color:{TEXT_PRIMARY}; font-size:11px; padding:3px 0; }}"
            f"QCheckBox::indicator {{ width:12px; height:12px; border:1px solid {BORDER};"
            f" border-radius:2px; background:{BG_DARK}; }}"
            f"QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}"
        )
        _spin_qss = (
            f"QSpinBox {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:1px 4px;"
            f" font-size:11px; }}"
        )

        def _chk_row(label: str, key: str) -> QCheckBox:
            chk = QCheckBox(label)
            chk.setChecked(_qs.value(f"scan/{key}_enabled", True, type=bool))
            chk.setStyleSheet(_chk_qss)
            chk.toggled.connect(
                lambda v, k=key: QSettings("NetSentinel", "NetSentinel").setValue(
                    f"scan/{k}_enabled", v
                )
            )
            return chk

        def _spin_row(label: str, key: str, default: int) -> QWidget:
            row = QWidget()
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent;"
            )
            spin = QSpinBox()
            spin.setRange(5, 120)
            spin.setValue(_qs.value(f"scan/{key}_duration_s", default, type=int))
            spin.setFixedWidth(64)
            spin.setStyleSheet(_spin_qss)
            spin.valueChanged.connect(
                lambda v, k=key: QSettings("NetSentinel", "NetSentinel").setValue(
                    f"scan/{k}_duration_s", v
                )
            )
            rl.addWidget(lbl)
            rl.addWidget(spin)
            rl.addStretch()
            return row

        # Two-column grid: left = checkboxes, right = duration spinners
        grid = QWidget()
        grid.setStyleSheet("background:transparent;")
        gl = QHBoxLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(24)

        chk_col = QVBoxLayout()
        chk_col.setSpacing(4)
        chk_col.addWidget(_chk_row("STP detection",  "stp"))
        chk_col.addWidget(_chk_row("Storm analysis", "storm"))
        chk_col.addWidget(_chk_row("WiFi scan",      "wifi"))
        chk_col.addWidget(_chk_row("DNS check",      "dns"))
        gl.addLayout(chk_col)

        spin_col = QVBoxLayout()
        spin_col.setSpacing(4)
        spin_col.addWidget(_spin_row("STP listen (s):",   "stp",   10))
        spin_col.addWidget(_spin_row("Storm listen (s):", "storm", 10))
        spin_col.addStretch()
        gl.addLayout(spin_col)
        gl.addStretch()

        body_lay.addWidget(grid)
        outer_lay.addWidget(body)

        def _on_toggle(checked: bool) -> None:
            toggle_btn.setText(
                f"{'▼' if checked else '▶'}  Scan Configuration"
            )
            body.setVisible(checked)

        toggle_btn.toggled.connect(_on_toggle)
        return outer

    def _build_control_bar(self) -> QWidget:
        """Unified filter row: search | source chips | + | stretch | live/history pill."""
        bar = QFrame()
        bar.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)

        # Search input — leftmost
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search…  (source:arp  ip:x  severity:critical)")
        self._search_box.setMinimumWidth(150)
        self._search_box.setMaximumWidth(230)
        self._search_box.setFixedHeight(26)
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setStyleSheet(
            f"QLineEdit {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:4px;"
            f" padding:1px 8px; font-size:11px; color:{TEXT_PRIMARY}; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._search_box.textChanged.connect(self._apply_filter)
        lay.addWidget(self._search_box)

        _div = QFrame()
        _div.setFrameShape(QFrame.Shape.VLine)
        _div.setFixedWidth(1)
        _div.setStyleSheet(f"background:{BORDER}; border:none;")
        lay.addWidget(_div)

        # "All" button
        all_btn = QPushButton("● All")
        all_btn.setCheckable(True)
        all_btn.setChecked(True)
        all_btn.setFixedHeight(26)
        self._style_toggle(all_btn, True, ACCENT)
        all_btn.clicked.connect(self._on_all_toggled)
        self._all_btn = all_btn
        lay.addWidget(all_btn)

        # Source chips — show only enabled sources; hidden ones accessible via "+"
        s = QSettings()
        for key, (label, color) in _SOURCES.items():
            default_on = key in ("net", "syslog", "snmp")
            enabled = s.value(f"logging/{key}_enabled", default_on, type=bool)
            btn = QPushButton(f"{'●' if enabled else '○'}  {label}")
            btn.setCheckable(True)
            btn.setChecked(enabled)
            btn.setFixedHeight(26)
            self._style_toggle(btn, enabled, color)
            btn.clicked.connect(lambda checked, k=key: self._on_source_toggled(k, checked))
            self._toggle_btns[key] = btn
            btn.setVisible(enabled and key != "plugin")
            btn.setToolTip(_SOURCE_TIPS.get(key, ""))
            if key == "modem" and not enabled:
                btn.setToolTip("Enable modem logging in Scan Configuration to show here.")
            lay.addWidget(btn)

        # "+" chip — opens source picker for disabled sources
        self._source_plus_btn = QPushButton("+")
        self._source_plus_btn.setFixedSize(26, 26)
        self._source_plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._source_plus_btn.setToolTip("Add source filter")
        self._source_plus_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_HOVER}; color:{TEXT_MUTED}; font-size:13px;"
            f" font-weight:bold; border:1px solid {BORDER}; border-radius:4px; padding:0; }}"
            f"QPushButton:hover {{ border-color:{ACCENT}; color:{ACCENT}; }}"
        )
        self._source_plus_btn.clicked.connect(self._open_source_picker)
        lay.addWidget(self._source_plus_btn)

        lay.addStretch()

        # Live / History pill toggle — rightmost
        _pill = QFrame()
        _pill.setStyleSheet(
            f"QFrame {{ background:{BG_DARK}; border:1px solid {BORDER}; border-radius:13px; }}"
        )
        _pill_lay = QHBoxLayout(_pill)
        _pill_lay.setContentsMargins(2, 2, 2, 2)
        _pill_lay.setSpacing(0)

        _pill_seg_on = (
            f"QPushButton {{ background:{ACCENT}; color:#fff; font-size:11px; font-weight:bold;"
            f" border:none; border-radius:11px; padding:2px 12px; }}"
        )
        _pill_seg_off = (
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; font-size:11px;"
            f" border:none; border-radius:11px; padding:2px 12px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        self._live_mode_btn = QPushButton("● Live")
        self._live_mode_btn.setFixedHeight(24)
        self._live_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._live_mode_btn.setStyleSheet(_pill_seg_on)
        self._live_mode_btn.clicked.connect(self._on_mode_live)

        self._hist_mode_btn = QPushButton("⊙ History")
        self._hist_mode_btn.setFixedHeight(24)
        self._hist_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hist_mode_btn.setStyleSheet(_pill_seg_off)
        self._hist_mode_btn.clicked.connect(self._on_mode_history)

        _pill_lay.addWidget(self._live_mode_btn)
        _pill_lay.addWidget(self._hist_mode_btn)
        lay.addWidget(_pill)

        return bar

    def _open_source_picker(self) -> None:
        """Popup menu for enabling hidden (disabled) source chips."""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:4px; padding:2px; }}"
            f"QMenu::item {{ padding:5px 14px; color:{TEXT_PRIMARY}; font-size:11px; }}"
            f"QMenu::item:selected {{ background:{ACCENT}22; }}"
        )
        has_hidden = False
        for key, (label, _color) in _SOURCES.items():
            btn = self._toggle_btns.get(key)
            if btn and not btn.isVisible():
                action = menu.addAction(f"+ {label}")
                action.triggered.connect(lambda _, k=key: self._reveal_source_chip(k))
                has_hidden = True
        if not has_hidden:
            return
        pos = self._source_plus_btn.mapToGlobal(
            self._source_plus_btn.rect().bottomLeft()
        )
        menu.exec(pos)

    def _reveal_source_chip(self, key: str) -> None:
        """Show a hidden source chip and enable it."""
        btn = self._toggle_btns.get(key)
        if btn:
            btn.setVisible(True)
            btn.setChecked(True)
            self._on_source_toggled(key, True)

    def _build_source_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(6)

        lbl = QLabel("Show:")
        lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none;"
        )
        lay.addWidget(lbl)

        all_btn = QPushButton("● All")
        all_btn.setCheckable(True)
        all_btn.setChecked(True)
        all_btn.setFixedHeight(26)
        self._style_toggle(all_btn, True, ACCENT)
        all_btn.clicked.connect(self._on_all_toggled)
        self._all_btn = all_btn
        lay.addWidget(all_btn)

        # Toggles are pure in-memory visibility filters — they do not persist to
        # QSettings.  Initial state reflects what is enabled in the Network Logger.
        s = QSettings()
        for key, (label, color) in _SOURCES.items():
            default_on = key in ("net", "syslog", "snmp")
            enabled = s.value(f"logging/{key}_enabled", default_on, type=bool)

            btn = QPushButton(f"{'●' if enabled else '○'}  {label}")
            btn.setCheckable(True)
            btn.setChecked(enabled)
            btn.setFixedHeight(26)
            self._style_toggle(btn, enabled, color)
            btn.clicked.connect(lambda checked, k=key: self._on_source_toggled(k, checked))
            self._toggle_btns[key] = btn
            lay.addWidget(btn)
            if key == "plugin":
                btn.setVisible(False)
            if key == "modem" and not enabled:
                btn.setToolTip("Connect a modem plugin to enable modem logging.")

        cfg_lbl = QLabel("· Configure in Network Logger")
        cfg_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
        )
        lay.addWidget(cfg_lbl)
        lay.addStretch()

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search…  (source:arp  ip:x  severity:critical)")
        self._search_box.setFixedWidth(260)
        self._search_box.setFixedHeight(26)
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setStyleSheet(
            f"QLineEdit {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:4px;"
            f" padding:1px 8px; font-size:11px; color:{TEXT_PRIMARY}; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._search_box.textChanged.connect(self._apply_filter)
        lay.addWidget(self._search_box)

        return bar

    def _build_mode_bar(self) -> QWidget:
        """Live / History segmented toggle (LOG-7)."""
        bar = QFrame()
        bar.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(4)

        _seg_qss_on = (
            f"QPushButton {{ background:{ACCENT}; color:#fff; font-size:11px; font-weight:bold;"
            f" border:none; border-radius:3px; padding:2px 14px; }}"
        )
        _seg_qss_off = (
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; font-size:11px;"
            f" border:none; border-radius:3px; padding:2px 14px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:{BG_HOVER}; }}"
        )

        self._live_mode_btn = QPushButton("● Live")
        self._live_mode_btn.setFixedHeight(24)
        self._live_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._live_mode_btn.setStyleSheet(_seg_qss_on)
        self._live_mode_btn.clicked.connect(self._on_mode_live)

        self._hist_mode_btn = QPushButton("⊙ History")
        self._hist_mode_btn.setFixedHeight(24)
        self._hist_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hist_mode_btn.setStyleSheet(_seg_qss_off)
        self._hist_mode_btn.clicked.connect(self._on_mode_history)

        lay.addWidget(self._live_mode_btn)
        lay.addWidget(self._hist_mode_btn)
        lay.addStretch()

        hint = QLabel("History mode queries your database for any time range")
        hint.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        lay.addWidget(hint)
        return bar

    def _build_logged_sources_bar(self) -> QWidget:
        """DB logging controls — one row per configured hardware plugin."""
        bar = QFrame()
        bar.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        hdr = QLabel("LOGGING TO DATABASE")
        hdr.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
            f" letter-spacing:0.08em; background:transparent; border:none;"
        )
        lay.addWidget(hdr)

        self._plugin_db_empty_lbl = QLabel(
            "No hardware plugins configured — add one in Hardware Integrations"
        )
        self._plugin_db_empty_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
        )
        lay.addWidget(self._plugin_db_empty_lbl)

        self._plugin_db_container = QWidget()
        self._plugin_db_container.setStyleSheet("background:transparent;")
        self._plugin_db_container_lay = QVBoxLayout(self._plugin_db_container)
        self._plugin_db_container_lay.setContentsMargins(0, 0, 0, 0)
        self._plugin_db_container_lay.setSpacing(6)
        lay.addWidget(self._plugin_db_container)

        self._db_feedback_lbl = QLabel("")
        self._db_feedback_lbl.setStyleSheet(
            f"color:{GREEN}; font-size:10px; background:transparent; border:none;"
        )
        self._db_feedback_lbl.setVisible(False)
        lay.addWidget(self._db_feedback_lbl)

        return bar

    def _style_db_btn(self, btn: QPushButton, enabled: bool) -> None:
        if enabled:
            btn.setStyleSheet(
                f"QPushButton {{ background:{GREEN}22; color:{GREEN}; font-size:10px;"
                f" font-weight:bold; border:1px solid {GREEN}; border-radius:11px;"
                f" padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{GREEN}44; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background:{BG_CARD}; color:{TEXT_MUTED}; font-size:10px;"
                f" border:1px solid {BORDER}; border-radius:11px; padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            )

    def _on_db_toggled(self, key: str, checked: bool, btn: QPushButton) -> None:
        label = _SOURCES[key][0]
        btn.setText("● Logging to DB" if checked else "○  Not logging  ")
        self._style_db_btn(btn, checked)
        QSettings("NetSentinel", "NetSentinel").setValue(f"logging/{key}_enabled", checked)
        if checked:
            self._show_db_feedback(
                f"{label} data will be saved to your database.", GREEN
            )
        else:
            self._show_db_feedback(
                f"{label} logging stopped. History recorded so far is preserved.", TEXT_SECONDARY
            )

    def _on_interval_changed(self, key: str, combo: QComboBox) -> None:
        val = combo.currentData()
        if val is not None:
            QSettings("NetSentinel", "NetSentinel").setValue(
                f"logging/{key}_interval_min", val
            )

    def _show_db_feedback(self, msg: str, color: str) -> None:
        self._db_feedback_lbl.setText(msg)
        self._db_feedback_lbl.setStyleSheet(
            f"color:{color}; font-size:10px; background:transparent; border:none;"
        )
        self._db_feedback_lbl.setVisible(True)
        QTimer.singleShot(3000, lambda: self._db_feedback_lbl.setVisible(False))

    # ── LOG-5: live challenge banner ──────────────────────────────────────────

    def _show_challenge_banner(self, time_str: str) -> None:
        self._challenge_time_lbl.setText(
            f"Live challenge detected at {time_str} — "
        )
        self._challenge_banner_ts = _t.time()
        self._challenge_banner.setVisible(True)
        self._challenge_timer.start(60_000)

    def _hide_challenge_banner(self) -> None:
        self._challenge_timer.stop()
        self._challenge_banner.setVisible(False)

    # ── LOG-7: mode switching ─────────────────────────────────────────────────

    def _on_mode_live(self) -> None:
        self._is_history_mode = False
        _on  = (f"QPushButton {{ background:{ACCENT}; color:#fff; font-size:11px; font-weight:bold;"
                f" border:none; border-radius:11px; padding:2px 12px; }}")
        _off = (f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; font-size:11px;"
                f" border:none; border-radius:11px; padding:2px 12px; }}"
                f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}")
        self._live_mode_btn.setStyleSheet(_on)
        self._hist_mode_btn.setStyleSheet(_off)
        self._history_bar.setVisible(False)
        self._apply_filter()

    def _on_mode_history(self) -> None:
        self._is_history_mode = True
        _on  = (f"QPushButton {{ background:{ACCENT}; color:#fff; font-size:11px; font-weight:bold;"
                f" border:none; border-radius:11px; padding:2px 12px; }}")
        _off = (f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; font-size:11px;"
                f" border:none; border-radius:11px; padding:2px 12px; }}"
                f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}")
        self._hist_mode_btn.setStyleSheet(_on)
        self._live_mode_btn.setStyleSheet(_off)
        self._history_bar.setVisible(True)
        self._load_history_range()

    def _load_history_range(self) -> None:
        from PyQt6.QtCore import QDate
        fd = self._hist_from_date.date().toPyDate()
        ft = _dt.time(self._hist_from_time.time().hour(), self._hist_from_time.time().minute())
        td = self._hist_to_date.date().toPyDate()
        tt = _dt.time(self._hist_to_time.time().hour(), self._hist_to_time.time().minute(), 59)
        ts_start = _dt.datetime.combine(fd, ft).timestamp()
        ts_end   = _dt.datetime.combine(td, tt).timestamp()

        rows: list[dict] = []

        # In-memory entries within range
        for e in self._entries:
            if ts_start <= e["ts"] <= ts_end:
                rows.append(e)

        # DB entries outside in-memory window
        if self._store:
            hours = max(1, int((ts_end - ts_start) / 3600) + 1)
            try:
                for p in self._store.query_modem_signal_log(hours=hours, limit=10_000):
                    if ts_start <= float(p.ts) <= ts_end:
                        rows.append(self._modem_point_to_entry(p))
            except Exception:
                pass
            try:
                for p in self._store.query_mesh_signal_log(hours=hours, limit=10_000):
                    if ts_start <= float(p.ts) <= ts_end:
                        parts = [f"{p.online_count}/{p.unit_count} units online"]
                        if p.worst_unit and p.worst_rssi is not None:
                            parts.append(f"worst: {p.worst_unit} {p.worst_rssi:.0f} dBm")
                        rows.append(self._make_entry(
                            "mesh", float(p.ts), "Mesh system",
                            f"{p.online_count}/{p.unit_count} units",
                            "  ·  ".join(parts), "OK",
                        ))
            except Exception:
                pass
            try:
                for row in self._store.query_plugin_log(hours=hours, limit=10_000):
                    if ts_start <= float(row.get("ts", 0)) <= ts_end:
                        rows.append(self._plugin_row_to_entry(row))
            except Exception:
                pass

        rows.sort(key=lambda e: e["ts"], reverse=True)
        rows = rows[:_MAX_ROWS]

        filt = self._search_box.text().strip().lower()
        visible = [
            e for e in rows
            if self._is_source_enabled(e["source_key"])
            and (not filt or self._row_matches(e["row"], filt))
        ]

        self._table.setRowCount(0)
        for i, e in enumerate(visible):
            self._table.insertRow(i)
            self._set_table_row(i, e)

    # ── LOG-4: export dialog ──────────────────────────────────────────────────

    def _open_export_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Export Log")
        dlg.setMinimumWidth(340)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 16, 16, 12)

        today = _dt.date.today()
        week_ago = today - _dt.timedelta(days=7)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("From:"))
        start_edit = QDateEdit(dlg)
        start_edit.setCalendarPopup(True)
        from PyQt6.QtCore import QDate
        start_edit.setDate(QDate(week_ago.year, week_ago.month, week_ago.day))
        row1.addWidget(start_edit)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("To:"))
        end_edit = QDateEdit(dlg)
        end_edit.setCalendarPopup(True)
        end_edit.setDate(QDate(today.year, today.month, today.day))
        row2.addWidget(end_edit)
        lay.addLayout(row2)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Export CSV")
        btns.accepted.connect(lambda: self._do_export(
            start_edit.date().toPyDate(), end_edit.date().toPyDate(), dlg
        ))
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.exec()

    def _do_export(self, start: "_dt.date", end: "_dt.date", dlg: QDialog) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log CSV", f"netsentinel_log_{start}_{end}.csv", "CSV files (*.csv)"
        )
        if not path:
            return

        ts_start = _dt.datetime.combine(start, _dt.time.min).timestamp()
        ts_end   = _dt.datetime.combine(end,   _dt.time.max).timestamp()

        rows: list[tuple] = []

        # In-memory entries within range
        for e in self._entries:
            if ts_start <= e["ts"] <= ts_end:
                r = e["row"]
                rows.append((_fmt_ts(e["ts"]), r[1], r[2], r[3], r[4], r[5]))

        # DB entries not yet in memory
        if self._store:
            hours = max(1, int((ts_end - ts_start) / 3600) + 1)
            try:
                for p in self._store.query_modem_signal_log(hours=hours, limit=10_000):
                    if ts_start <= float(p.ts) <= ts_end:
                        e = self._modem_point_to_entry(p)
                        r = e["row"]
                        rows.append((_fmt_ts(e["ts"]), r[1], r[2], r[3], r[4], r[5]))
            except Exception:
                pass
            try:
                for p in self._store.query_mesh_signal_log(hours=hours, limit=10_000):
                    if ts_start <= float(p.ts) <= ts_end:
                        parts = [f"{p.online_count}/{p.unit_count} units online"]
                        if p.worst_unit and p.worst_rssi is not None:
                            parts.append(f"worst: {p.worst_unit} {p.worst_rssi:.0f} dBm")
                        rows.append((
                            _fmt_ts(float(p.ts)), "MESH", "Mesh system",
                            f"{p.online_count}/{p.unit_count} units",
                            "  ·  ".join(parts), "OK",
                        ))
            except Exception:
                pass
            try:
                for row in self._store.query_plugin_log(hours=hours, limit=10_000):
                    if ts_start <= float(row.get("ts", 0)) <= ts_end:
                        e = self._plugin_row_to_entry(row)
                        r = e["row"]
                        rows.append((_fmt_ts(e["ts"]), r[1], r[2], r[3], r[4], r[5]))
            except Exception:
                pass

        rows.sort(key=lambda r: r[0])

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = _csv.writer(f)
                w.writerow(["Time", "Source", "Host", "Event", "Detail", "Status"])
                w.writerows(rows)
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Export failed", str(exc))
            return

        dlg.accept()

    def update_plugin_sources(self, names: list) -> None:
        """Rebuild the DB-logging bar rows for active hardware plugins.

        Called by the dashboard after each plugin poll so the bar always
        reflects the current set of configured plugins.
        """
        while self._plugin_db_container_lay.count():
            item = self._plugin_db_container_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        btn = self._toggle_btns.get("plugin")
        if btn:
            btn.setVisible(bool(names))

        self._plugin_db_empty_lbl.setVisible(not bool(names))

        _qs = QSettings("NetSentinel", "NetSentinel")
        for name in names:
            qs_key = f"plugin_{name.lower().replace(' ', '_')}"
            enabled = _qs.value(f"logging/{qs_key}_enabled", False, type=bool)

            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(8)

            src_lbl = QLabel(f"● {name}")
            src_lbl.setFixedWidth(120)
            src_lbl.setStyleSheet(
                "color:#A78BFA; font-size:11px; font-weight:bold;"
                " background:transparent; border:none;"
            )
            row_l.addWidget(src_lbl)

            db_btn = QPushButton("● Logging to DB" if enabled else "○  Not logging  ")
            db_btn.setCheckable(True)
            db_btn.setChecked(enabled)
            db_btn.setFixedHeight(22)
            db_btn.setFixedWidth(130)
            self._style_db_btn(db_btn, enabled)
            db_btn.clicked.connect(
                lambda checked, n=name, k=qs_key, b=db_btn:
                self._on_plugin_db_toggled(n, k, checked, b)
            )
            row_l.addWidget(db_btn)
            row_l.addStretch()
            self._plugin_db_container_lay.addWidget(row_w)

    def _on_plugin_db_toggled(
        self, name: str, qs_key: str, checked: bool, btn: QPushButton
    ) -> None:
        btn.setText("● Logging to DB" if checked else "○  Not logging  ")
        self._style_db_btn(btn, checked)
        QSettings("NetSentinel", "NetSentinel").setValue(
            f"logging/{qs_key}_enabled", checked
        )
        self.logging_active_changed.emit(checked)
        if checked:
            self._show_db_feedback(
                f"{name} data will be saved to your database.", GREEN
            )
        else:
            self._show_db_feedback(
                f"{name} logging stopped. History recorded so far is preserved.", TEXT_SECONDARY
            )

    def _style_toggle(self, btn: QPushButton, enabled: bool, color: str) -> None:
        if enabled:
            btn.setStyleSheet(
                f"QPushButton {{ background:{color}22; color:{color}; font-size:11px;"
                f" font-weight:bold; border:1px solid {color}; border-radius:12px;"
                f" padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{color}44; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background:{BG_CARD}; color:{TEXT_MUTED}; font-size:11px;"
                f" border:1px solid {BORDER}; border-radius:12px; padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            )

    def _on_source_toggled(self, key: str, checked: bool) -> None:
        label, color = _SOURCES[key]
        btn = self._toggle_btns[key]
        btn.setText(f"{'●' if checked else '○'}  {label}")
        self._style_toggle(btn, checked, color)
        self._sync_all_btn()
        self._apply_filter()

    def _on_all_toggled(self) -> None:
        for key, btn in self._toggle_btns.items():
            if not btn.isChecked():
                btn.setChecked(True)
                label, color = _SOURCES[key]
                btn.setText(f"●  {label}")
                self._style_toggle(btn, True, color)
        if self._all_btn:
            self._all_btn.setChecked(True)
            self._style_toggle(self._all_btn, True, ACCENT)
        self._apply_filter()

    def _sync_all_btn(self) -> None:
        if self._all_btn is None:
            return
        all_on = all(
            btn.isChecked()
            for btn in self._toggle_btns.values()
            if btn.isVisible()
        )
        self._all_btn.setChecked(all_on)
        self._style_toggle(self._all_btn, all_on, ACCENT)

    def _is_source_enabled(self, key: str) -> bool:
        btn = self._toggle_btns.get(key)
        return btn.isChecked() if btn else False

    # ── Entry management ──────────────────────────────────────────────────────

    def _make_entry(
        self,
        src_key: str,
        ts: float,
        host: str,
        event: str,
        detail: str,
        status: str,
        raw=None,
    ) -> dict:
        label = _SOURCES[src_key][0]
        return {
            "source_key": src_key,
            "source":     label,
            "ts":         ts,
            "row":        (_fmt_ts(ts), label, host, event, detail, status),
            "raw":        raw,
        }

    def _add_live(self, e: dict) -> None:
        """Insert a live entry and update the table immediately if visible."""
        self._entries.insert(0, e)
        if len(self._entries) > _MAX_ROWS:
            self._entries = self._entries[:_MAX_ROWS]
            if not self._cap_shown:
                self._cap_shown = True
                self._cap_banner.setVisible(True)
        # Dismiss challenge banner on next entry after it was shown
        if self._challenge_banner.isVisible() and e["ts"] > self._challenge_banner_ts:
            self._hide_challenge_banner()
        if self._is_history_mode:
            return
        if not self._is_source_enabled(e["source_key"]):
            return
        filt = self._search_box.text().strip().lower()
        if filt and not self._entry_matches(e, filt):
            return
        self._table.insertRow(0)
        self._set_table_row(0, e)
        self._animate_row_fade()
        if self._table.rowCount() > _MAX_ROWS:
            self._table.setRowCount(_MAX_ROWS)

    def _animate_row_fade(self) -> None:
        """Fade row 0 in from 60% → 100% opacity over 300 ms (ANIM-4). Skipped at high velocity."""
        from ui.theme import _reduce_motion
        if _reduce_motion():
            return
        now = _t.time()
        self._anim_row_ts = [ts for ts in self._anim_row_ts if now - ts < 1.0]
        self._anim_row_ts.append(now)
        if len(self._anim_row_ts) > 5:
            return

        from PyQt6.QtGui import QColor
        from ui.styles import BG_CARD

        n_cols = self._table.columnCount()
        final_colors: list[tuple[int, QColor | None]] = []
        for col in range(n_cols):
            item = self._table.item(0, col)
            final_colors.append((col, QColor(item.foreground().color()) if item else None))

        bg = QColor(BG_CARD)

        def _apply(weight: float) -> None:
            for col, final in final_colors:
                if final is None:
                    continue
                item = self._table.item(0, col)
                if not item:
                    continue
                r = int(bg.red()   + (final.red()   - bg.red())   * weight)
                g = int(bg.green() + (final.green() - bg.green()) * weight)
                b = int(bg.blue()  + (final.blue()  - bg.blue())  * weight)
                item.setForeground(QColor(r, g, b))

        _apply(0.6)
        QTimer.singleShot(100, lambda: _apply(0.8))
        QTimer.singleShot(200, lambda: _apply(1.0))

    def _apply_filter(self) -> None:
        filt = self._search_box.text().strip().lower()
        visible = [
            e for e in self._entries
            if self._is_source_enabled(e["source_key"])
            and self._entry_matches(e, filt)
        ]
        self._table.setRowCount(0)
        for i, e in enumerate(visible[:_MAX_ROWS]):
            self._table.insertRow(i)
            self._set_table_row(i, e)

    @staticmethod
    def _parse_filter_tokens(filt: str) -> tuple[dict, list]:
        """Split 'source:arp ip:192 critical' → ({'source':'arp','ip':'192'}, ['critical'])."""
        fields: dict[str, str] = {}
        free: list[str] = []
        for token in filt.split():
            if ":" in token:
                key, _, val = token.partition(":")
                if key in ("source", "ip", "severity") and val:
                    fields[key] = val
                    continue
            free.append(token)
        return fields, free

    def _entry_matches(self, e: dict, filt: str) -> bool:
        if not filt:
            return True
        fields, free = self._parse_filter_tokens(filt)
        row = e["row"]
        if "source" in fields and fields["source"] not in e.get("source_key", ""):
            return False
        if "ip" in fields and fields["ip"] not in str(row[2] if len(row) > 2 else "").lower():
            return False
        if "severity" in fields and fields["severity"] not in str(row[5] if len(row) > 5 else "").lower():
            return False
        for term in free:
            if not any(term in str(row[i]).lower() for i in (2, 3, 4) if i < len(row)):
                return False
        return True

    def _row_matches(self, row: tuple, filt: str) -> bool:
        return any(filt in str(row[i]).lower() for i in (2, 3, 4))

    def _set_table_row(self, idx: int, e: dict) -> None:
        row = e["row"]
        _, src_color = _SOURCES.get(e["source_key"], ("", TEXT_PRIMARY))
        sc = _status_color(row[5]) if row[5] else TEXT_SECONDARY
        raw_ts = e.get("ts")

        for col, val in enumerate(row):
            # ARP animate button in Event column for RTT entries
            if (col == 3 and e["raw"] is not None
                    and hasattr(e["raw"], "arp_event") and e["raw"].arp_event):
                btn = QPushButton(f"▶ ARP  {str(val)[:30]}")
                btn.setStyleSheet(
                    f"QPushButton {{ background:transparent; border:none; color:{AMBER};"
                    f" font-size:10px; text-align:left; padding:0 4px; }}"
                    f"QPushButton:hover {{ color:{ACCENT}; text-decoration:underline; }}"
                )
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _raw = e["raw"]
                btn.clicked.connect(lambda _=False, r=_raw: self.animate_requested.emit(r))
                self._table.setCellWidget(idx, col, btn)
            else:
                item = QTableWidgetItem(str(val))
                if col == 0 and raw_ts is not None:
                    item.setData(Qt.ItemDataRole.UserRole, raw_ts)
                if col == 1:
                    item.setForeground(QColor(src_color))
                    item.setFont(self._src_bold_font)
                elif col == 5:
                    item.setForeground(QColor(sc))
                else:
                    item.setForeground(QColor(TEXT_PRIMARY))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                self._table.setItem(idx, col, item)

    def _sort_and_render(self) -> None:
        self._entries.sort(key=lambda e: e["ts"], reverse=True)
        self._entries = self._entries[:_MAX_ROWS]
        self._apply_filter()

    # ── History loader ────────────────────────────────────────────────────────

    def _load_history(self) -> None:
        # Network RTT from CSV
        try:
            from modules.network_logger import list_log_files, load_log_file
            files = list_log_files()
            if files:
                summary = load_log_file(files[0])
                for entry in list(reversed(summary.entries[-200:])):
                    try:
                        ts = _dt.datetime.fromisoformat(entry.timestamp).timestamp()
                    except Exception:
                        ts = _t.time()
                    rtt_str  = f"{entry.rtt_ms:.0f}ms" if entry.rtt_ms >= 0 else "—"
                    dns_str  = f"DNS {entry.dns_ms:.0f}ms" if entry.dns_ms >= 0 else ""
                    http_str = f"HTTP {entry.http_status}" if entry.http_status >= 0 else ""
                    detail   = "  ·  ".join(filter(None, [rtt_str, dns_str, http_str]))
                    self._entries.append(self._make_entry(
                        "net", ts, entry.host,
                        entry.arp_event or entry.status, detail, entry.status, raw=entry,
                    ))
        except Exception:
            pass

        if self._store:
            # Modem signal history
            if self._is_source_enabled("modem"):
                try:
                    for p in self._store.query_modem_signal_log(hours=168, limit=200):
                        self._entries.append(self._modem_point_to_entry(p))
                except Exception:
                    pass

            # Mesh history
            if self._is_source_enabled("mesh"):
                try:
                    for p in self._store.query_mesh_signal_log(hours=168, limit=200):
                        unit_str = f"{p.online_count}/{p.unit_count} units"
                        parts = [f"{p.online_count}/{p.unit_count} units online"]
                        if p.worst_unit and p.worst_rssi is not None:
                            parts.append(f"worst: {p.worst_unit} {p.worst_rssi:.0f} dBm")
                        self._entries.append(self._make_entry(
                            "mesh", float(p.ts), "Mesh system",
                            unit_str, "  ·  ".join(parts), "OK",
                        ))
                except Exception:
                    pass

            # Plugin history
            if self._is_source_enabled("plugin"):
                try:
                    for row in self._store.query_plugin_log(hours=168, limit=200):
                        self._entries.append(self._plugin_row_to_entry(row))
                except Exception:
                    pass

        self._sort_and_render()

    def _plugin_row_to_entry(self, row: dict) -> dict:
        ts = float(row.get("ts", _t.time()))
        data = row.get("data", {})
        info = data.get("info", {})
        status = data.get("status", {})
        name = row.get("plugin_name", "plugin")
        host = info.get("ip") or name
        hw_type = info.get("type", "")
        wan_status = status.get("wan_status", "")
        clients = data.get("clients", [])
        extra = status.get("extra", {})
        detail_parts: list[str] = []
        if wan_status:
            detail_parts.append(wan_status)
        if clients:
            detail_parts.append(f"{len(clients)} clients")
        nt = extra.get("network_type", "")
        if nt:
            detail_parts.append(nt)
        event = f"{name}  ·  {hw_type}" if hw_type else name
        return self._make_entry(
            "plugin", ts, host, event, "  ·  ".join(detail_parts), wan_status or "",
        )

    def _modem_point_to_entry(self, p) -> dict:
        ts      = float(getattr(p, "ts", _t.time()))
        nt      = getattr(p, "network_type", None) or ""
        band    = getattr(p, "nr5g_band", None) or getattr(p, "lte_band", None) or ""
        nr_rsrp = getattr(p, "nr5g_rsrp", None)
        lte_rsrp = getattr(p, "lte_rsrp", None)
        rsrp    = nr_rsrp if nr_rsrp is not None else lte_rsrp
        rsrp_str = f"{rsrp:.1f} dBm" if rsrp is not None else ""
        sinr_raw = getattr(p, "nr5g_sinr", None)
        if sinr_raw is None:
            sinr_raw = getattr(p, "lte_snr", None)
        sinr_str = f"{sinr_raw:.1f} dB" if sinr_raw is not None else ""
        bars    = getattr(p, "signal_bars", None)
        bars_str = f"{bars}/5" if bars is not None else ""
        mcc, mnc = getattr(p, "mcc", None), getattr(p, "mnc", None)
        host    = f"{mcc}-{mnc}" if mcc and mnc else "ZTE MC889"
        detail  = "  ·  ".join(filter(None, [nt, band, rsrp_str, sinr_str, bars_str]))
        return self._make_entry("modem", ts, host, "Signal", detail, nt or "")

    # ── Public API ────────────────────────────────────────────────────────────

    def add_log_entry(self, entry) -> None:
        """Network RTT live entry from LoggerWorker."""
        if entry.status == "FAIL":
            self._consecutive_fails += 1
        else:
            self._consecutive_fails = 0

        now = _t.time()
        if now - self._last_live_challenge > _LIVE_CHALLENGE_COOLDOWN:
            scenario = _build_live_scenario(entry, self._consecutive_fails)
            if scenario is not None:
                self._last_live_challenge = now
                self.live_challenge_detected.emit(scenario)
                self._show_challenge_banner(_dt.datetime.now().strftime("%H:%M"))

        rtt_str  = f"{entry.rtt_ms:.0f}ms" if entry.rtt_ms >= 0 else "—"
        dns_str  = f"DNS {entry.dns_ms:.0f}ms" if entry.dns_ms >= 0 else ""
        http_str = f"HTTP {entry.http_status}" if entry.http_status >= 0 else ""
        detail   = "  ·  ".join(filter(None, [rtt_str, dns_str, http_str]))
        self._add_live(self._make_entry(
            "net", now, entry.host,
            entry.arp_event or entry.status, detail, entry.status, raw=entry,
        ))

    def add_modem_entry(self, data: dict) -> None:
        """Modem signal live entry — called from dashboard."""
        ts   = float(data.get("ts") or _t.time())
        mcc, mnc = data.get("mcc"), data.get("mnc")
        host = f"{mcc}-{mnc}" if mcc and mnc else "ZTE MC889"
        nt   = data.get("network_type") or ""
        band = data.get("nr5g_band") or data.get("lte_band") or ""
        rsrp_raw = (data.get("nr5g_rsrp_dbm")
                    if data.get("nr5g_rsrp_dbm") is not None
                    else data.get("lte_rsrp_dbm"))
        rsrp_str = f"{rsrp_raw:.1f} dBm" if rsrp_raw is not None else ""
        sinr_raw = data.get("nr5g_sinr_db")
        if sinr_raw is None:
            sinr_raw = data.get("lte_snr_db")
        sinr_str = f"{sinr_raw:.1f} dB" if sinr_raw is not None else ""
        bars = data.get("signal_bars")
        bars_str = f"{bars}/5" if bars is not None else ""
        detail = "  ·  ".join(filter(None, [nt, band, rsrp_str, sinr_str, bars_str]))
        self._add_live(self._make_entry("modem", ts, host, "Signal", detail, nt or ""))

    def add_mesh_entry(self, data: dict) -> None:
        """Mesh status live entry — called from dashboard."""
        units        = data.get("units", [])
        unit_count   = len(units)
        online_count = sum(1 for u in units if getattr(u, "online", True))
        worst_name, worst_rssi = "", None
        for u in units:
            rssi = getattr(u, "rssi", None) or getattr(u, "signal_level", None)
            if rssi is not None and (worst_rssi is None or rssi < worst_rssi):
                worst_rssi = rssi
                worst_name = getattr(u, "name", "") or getattr(u, "device_id", "")
        unit_str = f"{online_count}/{unit_count} units"
        parts    = [f"{online_count}/{unit_count} units online"]
        if worst_name and worst_rssi is not None:
            parts.append(f"worst: {worst_name} {worst_rssi:.0f} dBm")
        self._add_live(self._make_entry(
            "mesh", _t.time(), "Mesh system", unit_str, "  ·  ".join(parts), "OK",
        ))

    @pyqtSlot(object)
    def on_syslog_message(self, msg) -> None:
        severity = getattr(msg, "severity", "INFO")
        host     = getattr(msg, "source_ip", "") or getattr(msg, "hostname", "—")
        detail   = str(getattr(msg, "message", str(msg)))[:140]
        self._add_live(self._make_entry("syslog", _t.time(), host, severity, detail, ""))

    @pyqtSlot(object)
    def on_snmp_trap(self, trap) -> None:
        host   = getattr(trap, "source_ip", "—")
        event  = getattr(trap, "trap_type", "")
        detail = getattr(trap, "oid", "")
        self._add_live(self._make_entry("snmp", _t.time(), host, event, detail, ""))

    def add_plugin_entry(self, data: dict) -> None:
        """Hardware plugin live entry — called from dashboard on each poll result."""
        info = data.get("info", {})
        status = data.get("status", {})
        name = info.get("name", "plugin")
        host = info.get("ip") or name
        hw_type = info.get("type", "")
        wan_status = status.get("wan_status", "")
        clients = data.get("clients", [])
        extra = status.get("extra", {})
        detail_parts: list[str] = []
        if wan_status:
            detail_parts.append(wan_status)
        if clients:
            detail_parts.append(f"{len(clients)} clients")
        nt = extra.get("network_type", "")
        if nt:
            detail_parts.append(nt)
        event = f"{name}  ·  {hw_type}" if hw_type else name
        self._add_live(self._make_entry(
            "plugin", _t.time(), host, event, "  ·  ".join(detail_parts), wan_status or "",
        ))

    def show_network_log(self) -> None:
        """Ensure Network RTT source is visible and scroll to top."""
        btn = self._toggle_btns.get("net")
        if btn and not btn.isChecked():
            btn.setChecked(True)
            self._on_source_toggled("net", True)
        self._table.scrollToTop()

    def _on_table_context_menu(self, pos) -> None:
        import re
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor

        item = self._table.itemAt(pos)
        if item is None:
            return

        row = item.row()

        ts_item = self._table.item(row, 0)
        row_ts = ts_item.data(Qt.ItemDataRole.UserRole) if ts_item else None

        host_item = self._table.item(row, 2)
        host_text = (host_item.text() if host_item else "").strip()
        ip_match = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", host_text)
        ip = ip_match.group(1) if ip_match else None

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; }}"
            f"QMenu::item:selected {{ background:{TABLE_SEL}; }}"
        )

        corr_act = None
        if row_ts is not None:
            corr_act = menu.addAction("Show alerts near this time (±10 min)")

        device_act = None
        if ip and self._popover is not None:
            device_act = menu.addAction(f"Device Info — {ip}")

        if menu.isEmpty():
            return

        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return
        if corr_act and chosen == corr_act:
            self._show_alert_correlation(float(row_ts))
        elif device_act and chosen == device_act:
            self._popover.show_for(ip, QCursor.pos())

    def _show_alert_correlation(self, ts: float) -> None:
        if self._store is None:
            return

        alerts = self._store.get_recent_alerts(hours=1)
        nearby = sorted(
            [a for a in alerts if abs(a.get("ts", 0) - ts) <= 600],
            key=lambda a: (
                0 if a.get("severity", "").lower() == "critical" else
                1 if a.get("severity", "").lower() == "warning" else 2
            ),
        )[:5]

        while self._alert_corr_rows_lay.count():
            child = self._alert_corr_rows_lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not nearby:
            lbl = QLabel("No alerts in this ±10 min window")
            lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none;")
            self._alert_corr_rows_lay.addWidget(lbl)
        else:
            sev_color = {"critical": RED, "warning": AMBER}
            for a in nearby:
                sev = a.get("severity", "info").lower()
                color = sev_color.get(sev, TEXT_MUTED)
                ts_str = _fmt_ts(a.get("ts", ts))
                rule = a.get("rule", a.get("message", "Alert"))
                host = a.get("host", a.get("ip", ""))
                text = f"{ts_str}  {rule}" + (f"  — {host}" if host else "")
                row_lbl = QLabel(text)
                row_lbl.setStyleSheet(
                    f"color:{color}; font-size:11px; background:transparent; border:none;"
                )
                self._alert_corr_rows_lay.addWidget(row_lbl)

        self._alert_corr_panel.setVisible(True)

    def jump_to_alert_time(self, alert_ts: float, source_key: str) -> None:
        """TIME-2: Switch to history mode centred ±30 min on alert_ts, with source enabled."""
        from PyQt6.QtCore import QDate, QTime

        dt_before = _dt.datetime.fromtimestamp(max(0.0, alert_ts - 1800))
        dt_after  = _dt.datetime.fromtimestamp(alert_ts + 1800)

        self._hist_from_date.setDate(QDate(dt_before.year, dt_before.month, dt_before.day))
        self._hist_from_time.setTime(QTime(dt_before.hour, dt_before.minute))
        self._hist_to_date.setDate(QDate(dt_after.year, dt_after.month, dt_after.day))
        self._hist_to_time.setTime(QTime(dt_after.hour, dt_after.minute))

        # Force-enable the relevant source toggle
        key = source_key if source_key in self._toggle_btns else "net"
        btn = self._toggle_btns.get(key)
        if btn and not btn.isChecked():
            btn.setChecked(True)
            self._on_source_toggled(key, True)

        self._on_mode_history()
