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

import datetime as _dt
import time as _t
from typing import Optional

from PyQt6.QtCore import Qt, QEvent, QObject, QSettings, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem,
    QTimeEdit, QVBoxLayout, QWidget,
)

from ui.styles import (
    alpha,
    ACCENT, ACCENT_DARK, AMBER, BG_ALT_ROW,
    BG_CARD, BG_DARK, BG_HOVER, BORDER,
    CARD_RADIUS, RED, TABLE_SEL,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TH_BG,
    TH_TEXT, WHITE,
)

from ui.pages.log_source_panel import (
    _LogSourcePanelMixin,
    _SOURCES, _MAX_ROWS, _LIVE_CHALLENGE_COOLDOWN,
    _fmt_ts, _status_color, _build_live_scenario,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


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
    t.verticalHeader().setDefaultSectionSize(24)
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



# ── LogHubPage ────────────────────────────────────────────────────────────────

class LogHubPage(_LogSourcePanelMixin, QWidget):
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
    start_logger_requested  = pyqtSignal()    # CTA on empty state

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
        # Use a parented QTimer so it is automatically stopped when this widget
        # is deleted.  QTimer.singleShot(n, slot) creates an unparented timer that
        # fires after widget deletion, causing RuntimeError through the C++ timer
        # callback and corrupting the heap (same pattern fixed in home_page.py).
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(self._load_history)
        _t.start(300)

    def showEvent(self, event) -> None:
        from ui.table_utils import restore_column_widths
        restore_column_widths(self._table, "log_hub")
        super().showEvent(event)
        QTimer.singleShot(600, self._maybe_show_coach_log_hub)

    def _maybe_show_coach_log_hub(self) -> None:
        if not self.isVisible():
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("tour/v1_done", False, type=bool):
            return
        key = "coach/log_hub_sources_shown"
        if qs.value(key, False, type=bool):
            return
        net_on = qs.value("logging/net_enabled", True, type=bool)
        if net_on:
            return
        win = self.window()
        if not (win and win.isVisible()):
            return
        bar = self.findChild(QFrame, "controlBar")
        if not bar:
            return
        from ui.widgets.coach_mark import CoachMarkChain
        CoachMarkChain(
            win,
            [{
                "target": lambda b=bar: b,
                "title": "Choose what to log",
                "body": (
                    "Toggle Network RTT to start logging ping latency every "
                    "30 seconds. Leave it on for 24 hours for the best insights."
                ),
            }],
            on_done=lambda: QSettings("NetSentinel", "NetSentinel").setValue(key, True),
        ).start()

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
        self._sources_bar = self._build_control_bar()
        inner_lay.addWidget(self._sources_bar)
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
        self._history_bar.setObjectName("historyBar")
        self._history_bar.setVisible(False)
        self._history_bar.setStyleSheet(
            f"QFrame#historyBar {{ background:{BG_HOVER}; border-bottom:1px solid {BORDER};"
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
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; padding:0 12px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        _hb_load.clicked.connect(self._load_history_range)
        _hb_export = QPushButton("Export →")
        _hb_export.setFlat(True)
        _hb_export.setCursor(Qt.CursorShape.PointingHandCursor)
        _hb_export.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; text-decoration:underline; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
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
        self._challenge_banner.setObjectName("challengeBanner")
        self._challenge_banner.setVisible(False)
        self._challenge_banner.setStyleSheet(
            f"QFrame#challengeBanner {{ background:{alpha(AMBER, 0x22)}; border-bottom:1px solid {alpha(AMBER, 0x55)};"
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
            f"QPushButton:hover {{ color:{ACCENT_DARK}; text-decoration:underline; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        _cb_view_btn.clicked.connect(lambda: self.navigate_to.emit("Notifications"))
        _cb_x = QPushButton("×")
        _cb_x.setFixedSize(18, 18)
        _cb_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cb_x.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:13px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
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
        self._cap_banner.setObjectName("capBanner")
        self._cap_banner.setVisible(False)
        self._cap_banner.setStyleSheet(
            f"QFrame#capBanner {{ background:{BG_HOVER}; border-bottom:1px solid {BORDER};"
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
            f"QPushButton:hover {{ color:{ACCENT_DARK}; text-decoration:underline; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
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

        from ui.widgets.density_toggle import DensityToggle
        _dt_row = QHBoxLayout()
        _dt_row.setContentsMargins(8, 2, 8, 0)
        _dt_row.addStretch()
        _dt_row.addWidget(DensityToggle("log_hub", self._table))
        card_lay.addLayout(_dt_row)
        card_lay.addWidget(self._table)
        from ui.table_utils import save_column_widths
        self._table.horizontalHeader().sectionResized.connect(
            lambda _l, _o, _n: save_column_widths(self._table, "log_hub")
        )
        from ui.empty_state import EmptyStateOverlay
        EmptyStateOverlay(
            self._table, "≡",
            "No log entries yet",
            "Sources are enabled — entries will appear as events arrive.",
        )

        # ALERT-4: inline alert correlation panel (hidden until triggered)
        self._alert_corr_panel = QFrame()
        self._alert_corr_panel.setObjectName("alertCorrPanel")
        self._alert_corr_panel.setVisible(False)
        self._alert_corr_panel.setStyleSheet(
            f"QFrame#alertCorrPanel {{ background:{BG_HOVER}; border-top:1px solid {BORDER}; }}"
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
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        _acp_close.clicked.connect(lambda: self._alert_corr_panel.setVisible(False))
        _acp_hdr.addWidget(_acp_title, 1)
        _acp_hdr.addWidget(_acp_close)
        _acp_lay.addLayout(_acp_hdr)
        self._alert_corr_rows_lay = QVBoxLayout()
        self._alert_corr_rows_lay.setSpacing(2)
        _acp_lay.addLayout(self._alert_corr_rows_lay)
        card_lay.addWidget(self._alert_corr_panel)

        # Content stack: page 0 = empty state (no sources active),
        #                page 1 = live card with table
        from PyQt6.QtWidgets import QStackedWidget as _QSW
        self._content_stack = _QSW()
        from ui.widgets.empty_state_card import EmptyStateCard
        _esc = EmptyStateCard(
            "≡",
            "No logs yet — start monitoring",
            "The Network Logger records RTT, jitter and DNS every 30 seconds.",
            "Leave it running for a few hours to see stability trends and spot outages.",
            "Start Network Logger →",
        )
        _esc.clicked.connect(self.start_logger_requested)
        self._content_stack.addWidget(_esc)   # page 0
        self._content_stack.addWidget(card)   # page 1
        # Check if any source is already enabled (persisted from prior session)
        from PyQt6.QtCore import QSettings as _QS
        _qs = _QS()
        _sources_default_on = {"net", "syslog", "snmp"}
        _any_on = any(
            _qs.value(f"logging/{k}_enabled", k in _sources_default_on, type=bool)
            for k in ("net", "modem", "mesh", "syslog", "snmp")
        )
        self._content_stack.setCurrentIndex(1 if _any_on else 0)
        inner_lay.addWidget(self._content_stack, 1)

        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG_DARK}; border:none; }}")
        root.addWidget(scroll, 1)

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
        _t1 = QTimer(self)
        _t1.setSingleShot(True)
        _t1.timeout.connect(lambda: _apply(0.8))
        _t1.start(100)
        _t2 = QTimer(self)
        _t2.setSingleShot(True)
        _t2.timeout.connect(lambda: _apply(1.0))
        _t2.start(200)

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
                    f"QPushButton:pressed {{ background:{BG_HOVER}; color:{AMBER}; }}"
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
            pass  # non-fatal

        if self._store:
            # Modem signal history
            if self._is_source_enabled("modem"):
                try:
                    for p in self._store.query_modem_signal_log(hours=168, limit=200):
                        self._entries.append(self._modem_point_to_entry(p))
                except Exception:
                    pass  # non-fatal

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
                    pass  # non-fatal

            # Plugin history
            if self._is_source_enabled("plugin"):
                try:
                    for row in self._store.query_plugin_log(hours=168, limit=200):
                        self._entries.append(self._plugin_row_to_entry(row))
                except Exception:
                    pass  # non-fatal

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
            f"QMenu::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
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
