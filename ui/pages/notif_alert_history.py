"""
notif_alert_history.py — _NotifAlertHistoryMixin: alert history table, delivery/retry log,
bulk dismiss/snooze actions.

Extracted from notif_channel_panels.py (Sprint 17) to keep that file within budget.
NotificationsPage inherits _NotifAlertHistoryMixin alongside the other channel mixins.
"""
from __future__ import annotations

import csv as _csv
import os
import time

from PyQt6.QtCore import Qt, QEvent, QObject, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER,
    BG_ALT_ROW, BG_CARD, BG_HOVER,
    BORDER, GREEN, RED,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)


# ── Alert CTA routing ────────────────────────────────────────────────────────

# Maps rule_name patterns (case-insensitive substrings) → nav label to open when clicked.
# Default rule names come from _default_rules() in alert_suppressor.py.
_RULE_NAME_CTA: dict[str, str] = {
    "high rtt":         "DNS & Stability",
    "loss threshold":   "DNS & Stability",
    "host down":        "Inventory Changes",
    "host degraded":    "Inventory Changes",
    "new device":       "Devices",
    "device gone":      "Inventory Changes",
    "cert expir":       "TLS & Exposure",
    "host flapping":    "Trend Forecasts",
    "flap":             "Trend Forecasts",
    "service down":     "Service Heartbeat",
    # legacy heuristics kept for user-renamed rules
    "port scan":        "Port Scan (TCP)",
    "arp":              "ARP Spoof Watch",
    "dhcp":             "DHCP Rogue Monitor",
    "rate_spike":       "Live Bandwidth",
    "bandwidth":        "Live Bandwidth",
    "cve":              "CVE Tracker",
}


def _cta_page_for_rule(rule_name: str) -> str | None:
    """Return the nav label of the best page for this alert, or None."""
    lower = rule_name.lower()
    for pattern, page in _RULE_NAME_CTA.items():
        if pattern in lower:
            return page
    return None


# ── Alert sub-label helpers ───────────────────────────────────────────────────

def _fmt_elapsed(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m" if m else f"{h}h"


def _enrich_alert_sublabel(alert: dict) -> str:
    import re as _re
    rule    = (alert.get("rule_name") or "").upper()
    msg     = alert.get("message") or ""
    elapsed = max(0, int(time.time()) - int(alert.get("ts") or 0))
    if "RTT_THRESHOLD" in rule or "HIGH_RTT" in rule:
        m = _re.search(r":\s*([\d.]+)\s*ms", msg)
        return f"RTT: {float(m.group(1)):.0f} ms at alert time" if m else ""
    if "HOST_DOWN" in rule:
        return f"Down for {_fmt_elapsed(elapsed)}"
    if "DEVICE_GONE" in rule:
        return f"Last seen {_fmt_elapsed(elapsed)} ago"
    if "SERVICE_DOWN" in rule:
        m = _re.search(r"\((.+):(\d+)\)$", msg)
        prefix = f"Port {m.group(2)} · " if m else ""
        return f"{prefix}down for {_fmt_elapsed(elapsed)}"
    if "CERT_EXPIRY" in rule and "EXPIRED" not in rule:
        m = _re.search(r"(\d+)\s+day", msg)
        if m:
            d = int(m.group(1))
            return f"Expires in {d} day{'s' if d != 1 else ''}"
        return ""
    if "CERT_EXPIRED" in rule:
        d = elapsed // 86400
        return f"Expired {max(d, 0)} day{'s' if d != 1 else ''} ago"
    if "THREAT_INTEL" in rule:
        m = _re.search(r"score[:\s]+([\d.]+)", msg, _re.IGNORECASE)
        return f"Abuse score: {float(m.group(1)):.0f}/100" if m else ""
    return ""


# ── Severity / channel colour maps ───────────────────────────────────────────

_SEV_COLOR = {"INFO": ACCENT, "WARNING": AMBER, "CRITICAL": RED}
_CH_COLOR  = {"TOAST": ACCENT, "WEBHOOK": GREEN, "EMAIL": AMBER,
              "PUSHOVER": RED, "NTFY": GREEN, "TELEGRAM": ACCENT}


# ── J/K navigation event filter ──────────────────────────────────────────────

class _JKNavFilter(QObject):
    def __init__(self, table: QTableWidget, parent=None) -> None:
        super().__init__(parent)
        self._table = table

    def eventFilter(self, obj, event) -> bool:
        if (
            event.type() == QEvent.Type.KeyPress
            and obj is self._table.viewport()
        ):
            key = event.key()
            if key in (Qt.Key.Key_J, Qt.Key.Key_K):
                current = self._table.currentRow()
                step = 1 if key == Qt.Key.Key_J else -1
                target = max(0, min(self._table.rowCount() - 1, current + step))
                self._table.setCurrentCell(target, self._table.currentColumn())
                return True
        return False


# ── Mixin — alert history table + delivery log panel + bulk actions ───────────

class _NotifAlertHistoryMixin:
    """Pure-Python mixin providing alert history and delivery log UI.

    Extracted from ui/pages/notif_channel_panels.py (Sprint 17).
    All methods reference ``self`` which is the NotificationsPage instance.
    """

    # ── Alert history & delivery log card ─────────────────────────────────────

    def _build_log_card(self) -> QWidget:
        from PyQt6.QtWidgets import QFrame as _QFrame
        card = _QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};border-radius:0px;}}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        tb = _QFrame()
        tb.setFixedHeight(32)
        tb.setStyleSheet(
            f"background:{BG_CARD};border-bottom:1px solid {BORDER};"
        )
        tbl_lbl_lay = QHBoxLayout(tb)
        tbl_lbl_lay.setContentsMargins(12, 0, 12, 0)
        _title_lbl = QLabel("Alert History & Delivery Log")
        _title_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;"
        )
        tbl_lbl_lay.addWidget(_title_lbl)
        tbl_lbl_lay.addStretch()
        cl.addWidget(tb)
        body = QWidget()
        body.setStyleSheet(f"background:{BG_CARD};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 12, 16, 14)
        bl.setSpacing(8)
        cl.addWidget(body)

        _tbl_qss = (
            f"QTableWidget{{border:none;font-size:11px;color:{TEXT_PRIMARY};"
            f"gridline-color:{BORDER};alternate-background-color:{BG_ALT_ROW};}}"
            f"QHeaderView::section{{background:{ACCENT};color:{WHITE};"
            f"font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
            f"QTableWidget::item{{padding:2px 5px;}}"
        )
        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane {{ border:1px solid {BORDER}; border-top:none; }}"
            f"QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            f" border-bottom:none; padding:4px 12px; font-size:11px; }}"
            f"QTabBar::tab:selected {{ color:{TEXT_PRIMARY}; border-bottom:2px solid {ACCENT}; }}"
            f"QTabBar::tab:hover {{ color:{TEXT_PRIMARY}; }}"
        )

        # ── Tab 1: Alert History ──────────────────────────────────────────────
        hist_tab = QWidget()
        hist_lay = QVBoxLayout(hist_tab)
        hist_lay.setContentsMargins(0, 6, 0, 0)
        hist_lay.setSpacing(4)

        self._hist_sev_filter: set = {"INFO", "WARNING", "CRITICAL"}
        self._hist_hours = 72.0
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        filter_row.setContentsMargins(0, 0, 0, 2)
        sev_lbl = QLabel("Severity:")
        sev_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        filter_row.addWidget(sev_lbl)
        self._hist_sev_btns: dict = {}
        for sev, col in _SEV_COLOR.items():
            btn = QPushButton(sev)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedHeight(20)
            btn.setStyleSheet(
                f"QPushButton {{ font-size:9px; font-weight:bold; border:1px solid {col};"
                f" border-radius:3px; padding:0 6px; color:{col}; background:transparent; }}"
                f"QPushButton:checked {{ background:{col}; color:{WHITE}; }}"
                f"QPushButton:unchecked {{ background:transparent; }}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            )
            btn.toggled.connect(lambda checked, s=sev: self._toggle_hist_sev(s, checked))
            self._hist_sev_btns[sev] = btn
            filter_row.addWidget(btn)
        filter_row.addSpacing(12)
        time_lbl = QLabel("Window:")
        time_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        filter_row.addWidget(time_lbl)
        self._hist_time_combo = QComboBox()
        self._hist_time_combo.setFixedHeight(22)
        self._hist_time_combo.addItems(["1h", "6h", "24h", "72h", "7d"])
        self._hist_time_combo.setCurrentText("72h")
        self._hist_time_combo.setStyleSheet(
            f"QComboBox {{ font-size:10px; background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 4px; }}"
        )
        self._hist_time_combo.currentTextChanged.connect(self._on_hist_time_changed)
        filter_row.addWidget(self._hist_time_combo)
        filter_row.addStretch()
        hist_lay.addLayout(filter_row)

        # Storm suggestion banner (hidden until a burst is detected)
        self._storm_banner = QFrame()
        self._storm_banner.setVisible(False)
        self._storm_banner.setStyleSheet(
            f"QFrame {{ background:{AMBER}22; border:1px solid {AMBER}; border-radius:4px; }}"
        )
        _sb_lay = QHBoxLayout(self._storm_banner)
        _sb_lay.setContentsMargins(10, 6, 10, 6)
        _sb_lay.setSpacing(8)
        self._storm_banner_lbl = QLabel("")
        self._storm_banner_lbl.setWordWrap(True)
        self._storm_banner_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:11px; background:transparent; border:none;"
        )
        _sb_lay.addWidget(self._storm_banner_lbl, 1)
        _sb_setup_btn = QPushButton("Set up →")
        _sb_setup_btn.setFixedHeight(24)
        _sb_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _sb_setup_btn.setStyleSheet(
            f"QPushButton{{background:{AMBER};color:{WHITE};font-size:10px;font-weight:600;"
            f"border:none;border-radius:3px;padding:0 10px;}}"
            f"QPushButton:hover{{background:{AMBER}CC;}}"
            f"QPushButton:pressed{{background:{AMBER}AA;color:{TEXT_PRIMARY};}}"
        )
        _sb_setup_btn.clicked.connect(self._storm_go_to_dep)
        _sb_dismiss_btn = QPushButton("×")
        _sb_dismiss_btn.setFixedSize(20, 20)
        _sb_dismiss_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{TEXT_SECONDARY};border:none;"
            f"font-size:13px;font-weight:bold;padding:0;}}"
            f"QPushButton:hover{{color:{TEXT_PRIMARY};}}"
            f"QPushButton:pressed{{background:{BG_HOVER};color:{TEXT_SECONDARY};}}"
        )
        _sb_dismiss_btn.clicked.connect(lambda: self._storm_banner.setVisible(False))
        _sb_lay.addWidget(_sb_setup_btn)
        _sb_lay.addWidget(_sb_dismiss_btn)
        hist_lay.addWidget(self._storm_banner)

        self._alert_history_table = QTableWidget(0, 5)
        self._alert_history_table.setHorizontalHeaderLabels(
            ["Time", "Rule", "Host", "Severity", "Status"]
        )
        self._alert_history_table.horizontalHeader().setStretchLastSection(False)
        self._alert_history_table.horizontalHeader().setSectionResizeMode(
            1, self._alert_history_table.horizontalHeader().ResizeMode.Stretch
        )
        self._alert_history_table.verticalHeader().setVisible(False)
        self._alert_history_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._alert_history_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._alert_history_table.setAlternatingRowColors(True)
        self._alert_history_table.verticalHeader().setDefaultSectionSize(24)
        self._alert_history_table.setFixedHeight(200)
        self._alert_history_table.setStyleSheet(_tbl_qss)
        for w, col in zip((100, 80, 100, 80), range(4)):
            self._alert_history_table.setColumnWidth(col, w)
        self._alert_history_table.itemClicked.connect(self._on_alert_row_single_click)
        self._alert_history_table.itemDoubleClicked.connect(
            self._on_alert_history_row_clicked
        )
        self._alert_history_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._alert_history_table.customContextMenuRequested.connect(
            self._on_alert_history_context_menu
        )
        self._jk_filter_hist = _JKNavFilter(self._alert_history_table, self)
        self._alert_history_table.viewport().installEventFilter(self._jk_filter_hist)
        self._alert_history_table.itemSelectionChanged.connect(
            self._on_hist_selection_changed
        )
        hist_lay.addWidget(self._alert_history_table)

        self._hist_empty_lbl = QLabel("No alerts recorded yet — alerts appear here after the first detection event.")
        self._hist_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hist_empty_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none; padding:8px 0;"
        )
        hist_lay.addWidget(self._hist_empty_lbl)

        # Bulk action bar
        self._bulk_bar = QFrame()
        self._bulk_bar.setVisible(False)
        self._bulk_bar.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:3px; }}"
        )
        _bb_lay = QHBoxLayout(self._bulk_bar)
        _bb_lay.setContentsMargins(8, 4, 8, 4)
        _bb_lay.setSpacing(6)
        self._bulk_lbl = QLabel("0 selected")
        self._bulk_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; font-weight:600;"
        )
        _bb_lay.addWidget(self._bulk_lbl)
        _bb_lay.addSpacing(6)
        _bb_dismiss = QPushButton("Dismiss")
        _bb_dismiss.setFixedHeight(22)
        _bb_dismiss.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:{WHITE};font-size:10px;font-weight:600;"
            f"border:none;border-radius:3px;padding:0 10px;}}"
            f"QPushButton:hover{{background:{ACCENT_DARK};}}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        _bb_dismiss.clicked.connect(self._bulk_dismiss)
        _bb_snooze1 = QPushButton("Snooze 1h")
        _bb_snooze1.setFixedHeight(22)
        _bb_snooze1.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{TEXT_PRIMARY};font-size:10px;"
            f"border:1px solid {BORDER};border-radius:3px;padding:0 10px;}}"
            f"QPushButton:hover{{border-color:{ACCENT};color:{ACCENT};}}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        _bb_snooze1.clicked.connect(lambda: self._bulk_snooze(3600))
        _bb_snooze8 = QPushButton("Snooze 8h")
        _bb_snooze8.setFixedHeight(22)
        _bb_snooze8.setStyleSheet(_bb_snooze1.styleSheet())
        _bb_snooze8.clicked.connect(lambda: self._bulk_snooze(28800))
        _bb_deselect = QPushButton("Deselect all")
        _bb_deselect.setFixedHeight(22)
        _bb_deselect.setStyleSheet(
            f"QPushButton{{background:transparent;color:{TEXT_MUTED};font-size:10px;"
            f"border:none;padding:0 8px;}}"
            f"QPushButton:hover{{color:{TEXT_PRIMARY};}}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        _bb_deselect.clicked.connect(self._alert_history_table.clearSelection)
        for w in (_bb_dismiss, _bb_snooze1, _bb_snooze8):
            _bb_lay.addWidget(w)
        _bb_lay.addStretch()
        _bb_lay.addWidget(_bb_deselect)
        hist_lay.addWidget(self._bulk_bar)

        hist_btn_row = QHBoxLayout()
        btn_hist_refresh = QPushButton("Refresh")
        btn_hist_refresh.setFixedHeight(24)
        btn_hist_refresh.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{TEXT_SECONDARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 12px;font-size:11px;}}"
            f"QPushButton:hover{{color:{ACCENT};border-color:{ACCENT};}}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        btn_hist_refresh.clicked.connect(self._refresh_alert_history)
        btn_hist_export = QPushButton("↓ Export CSV")
        btn_hist_export.setFixedHeight(24)
        btn_hist_export.setStyleSheet(btn_hist_refresh.styleSheet())
        btn_hist_export.clicked.connect(self._export_alert_history_csv)
        hist_btn_row.addWidget(btn_hist_refresh)
        hist_btn_row.addWidget(btn_hist_export)
        hist_btn_row.addStretch()
        hist_lay.addLayout(hist_btn_row)
        tabs.addTab(hist_tab, "Alert History")

        # ── Tab 2: Delivery & Retry ───────────────────────────────────────────
        log_tab = QWidget()
        log_lay = QVBoxLayout(log_tab)
        log_lay.setContentsMargins(0, 6, 0, 0)
        log_lay.setSpacing(4)

        self._log_table = QTableWidget(0, 6)
        self._log_table.setHorizontalHeaderLabels(
            ["Time", "Channel", "Severity", "Host", "Message", "Status"]
        )
        self._log_table.horizontalHeader().setStretchLastSection(False)
        self._log_table.horizontalHeader().setSectionResizeMode(
            4, self._log_table.horizontalHeader().ResizeMode.Stretch
        )
        self._log_table.verticalHeader().setVisible(False)
        self._log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._log_table.setAlternatingRowColors(True)
        self._log_table.verticalHeader().setDefaultSectionSize(24)
        self._log_table.setFixedHeight(200)
        self._log_table.setStyleSheet(_tbl_qss)
        for w, col in zip((110, 90, 80, 120, 80), range(5)):
            self._log_table.setColumnWidth(col, w)
        self._log_table.itemClicked.connect(self._on_log_row_clicked)
        self._jk_filter_log = _JKNavFilter(self._log_table, self)
        self._log_table.viewport().installEventFilter(self._jk_filter_log)
        log_lay.addWidget(self._log_table)

        self._log_empty_lbl = QLabel("No delivery attempts recorded yet — entries appear here after the first alert is sent.")
        self._log_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._log_empty_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none; padding:8px 0;"
        )
        log_lay.addWidget(self._log_empty_lbl)

        self._log_detail = QFrame()
        self._log_detail.setVisible(False)
        self._log_detail.setStyleSheet(
            f"QFrame {{ background:{BG_ALT_ROW}; border:1px solid {BORDER}; border-radius:4px; }}"
        )
        _det_lay = QVBoxLayout(self._log_detail)
        _det_lay.setContentsMargins(10, 8, 10, 8)
        _det_lay.setSpacing(4)
        self._log_detail_error_lbl = QLabel("")
        self._log_detail_error_lbl.setWordWrap(True)
        self._log_detail_error_lbl.setStyleSheet(
            f"font-size:11px; color:{RED}; background:transparent; border:none;"
        )
        _det_btn_row = QHBoxLayout()
        self._log_detail_retry_btn = QPushButton("Retry →")
        self._log_detail_retry_btn.setFixedHeight(24)
        self._log_detail_retry_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; padding:0 12px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        _det_close_btn = QPushButton("Close")
        _det_close_btn.setFixedHeight(24)
        _det_close_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:11px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        _det_close_btn.clicked.connect(lambda: self._log_detail.setVisible(False))
        _det_btn_row.addWidget(self._log_detail_retry_btn)
        _det_btn_row.addWidget(_det_close_btn)
        _det_btn_row.addStretch()
        _det_lay.addWidget(self._log_detail_error_lbl)
        _det_lay.addLayout(_det_btn_row)
        log_lay.addWidget(self._log_detail)
        self._log_detail_entry: dict | None = None

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("Refresh Log")
        btn_refresh.setFixedHeight(24)
        btn_refresh.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{TEXT_SECONDARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 12px;font-size:11px;}}"
            f"QPushButton:hover{{color:{ACCENT};border-color:{ACCENT};}}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        btn_refresh.clicked.connect(self.refresh_log)
        btn_clear = QPushButton("Clear Log")
        btn_clear.setFixedHeight(24)
        btn_clear.setStyleSheet(btn_refresh.styleSheet())
        btn_clear.clicked.connect(self._clear_log)
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        log_lay.addLayout(btn_row)

        cta = QPushButton("＋  Create custom alert →")
        cta.setFlat(True)
        cta.setCursor(Qt.CursorShape.PointingHandCursor)
        cta.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:4px 0; text-align:left; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        cta.clicked.connect(lambda: self.navigate_to.emit("Custom Triggers"))
        log_lay.addWidget(cta)
        tabs.addTab(log_tab, "Delivery & Retry")

        bl.addWidget(tabs)
        return card

    # ── Log panel methods ─────────────────────────────────────────────────────

    def refresh_log(self) -> None:
        self._refresh_alert_history()
        if self._router is None:
            return
        entries = self._router.get_delivery_log()
        self._log_table.setRowCount(0)
        for entry in reversed(entries):
            row = self._log_table.rowCount()
            self._log_table.insertRow(row)
            ts_str    = time.strftime("%H:%M:%S", time.localtime(entry.get("ts", 0)))
            sev       = entry.get("severity", "")
            sev_color = _SEV_COLOR.get(sev, TEXT_PRIMARY)
            ch_type   = entry.get("channel_type", "")
            ch_color  = _CH_COLOR.get(ch_type, TEXT_PRIMARY)
            status    = entry.get("status", "PENDING")
            err       = entry.get("error", "")
            if status == "DELIVERED":
                status_txt, status_color = "✓ Delivered", GREEN
            elif status == "FAILED":
                status_txt, status_color = "✗ Failed", RED
            else:
                status_txt, status_color = "⟳ Pending", TEXT_MUTED
            for col, val in enumerate([
                ts_str, entry.get("channel_name", ""), sev,
                entry.get("host", ""), entry.get("message", ""), status_txt,
            ]):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 2:
                    item.setForeground(QColor(sev_color))
                elif col == 1:
                    item.setForeground(QColor(ch_color))
                elif col == 5:
                    item.setForeground(QColor(status_color))
                if status == "FAILED":
                    item.setBackground(QBrush(QColor(RED + "22")))
                    if err and col == 5:
                        item.setToolTip(err)
                self._log_table.setItem(row, col, item)
            self._log_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, entry)

        has_log_rows = self._log_table.rowCount() > 0
        self._log_empty_lbl.setVisible(not has_log_rows)

    def _on_log_row_clicked(self, item: QTableWidgetItem) -> None:
        first = self._log_table.item(item.row(), 0)
        if first is None:
            return
        entry = first.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict) or entry.get("status") != "FAILED":
            self._log_detail.setVisible(False)
            return
        err = entry.get("error", "Unknown error")
        self._log_detail_error_lbl.setText(
            f"Delivery failed — {err}. "
            "Check your notification settings and retry."
        )
        self._log_detail_entry = entry
        try:
            self._log_detail_retry_btn.clicked.disconnect()
        except RuntimeError:
            pass  # non-fatal
        self._log_detail_retry_btn.clicked.connect(self._retry_log_entry)
        self._log_detail.setVisible(True)

    def _retry_log_entry(self) -> None:
        if self._router and self._log_detail_entry:
            self._router.retry_delivery(self._log_detail_entry)
            self._log_detail.setVisible(False)
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self.refresh_log)
            _t.start(2000)

    def _clear_log(self) -> None:
        if self._router:
            self._router.clear_delivery_log()
        self._log_table.setRowCount(0)
        self._log_detail.setVisible(False)

    def _storm_go_to_dep(self) -> None:
        """Scroll the page to the dependency tree card when user clicks 'Set up →'."""
        dep = getattr(self, "_dep_card_widget", None)
        scr = getattr(self, "_notif_scroll", None)
        if dep and scr:
            scr.ensureWidgetVisible(dep)

    def _check_alert_storm(self, alerts: list) -> None:
        """Detect a burst of alerts for the same subnet and show the storm banner."""
        import ipaddress as _ip
        now = time.time()
        subnet_counts: dict[str, int] = {}
        for a in alerts:
            ts = a.get("ts") or 0
            if now - float(ts) > 60:
                continue
            host = a.get("host") or ""
            try:
                addr = _ip.ip_address(host)
                if isinstance(addr, _ip.IPv4Address):
                    subnet = ".".join(host.split(".")[:3]) + ".x"
                else:
                    subnet = host
            except ValueError:
                subnet = host
            subnet_counts[subnet] = subnet_counts.get(subnet, 0) + 1
        top = max(subnet_counts.items(), key=lambda x: x[1], default=(None, 0))
        if top[1] >= 5:
            self._storm_banner_lbl.setText(
                f"⚠  {top[1]} alerts from subnet <b>{top[0]}</b> in the last 60 s — "
                "this may be a parent-device outage. "
                "Set up alert dependencies to suppress duplicate alerts:"
            )
            self._storm_banner.setVisible(True)
        else:
            self._storm_banner.setVisible(False)

    def _refresh_alert_history(self) -> None:
        if self._store is None or not self.isVisible():
            return
        try:
            alerts = self._store.get_recent_alerts(hours=self._hist_hours, limit=500)
        except Exception:
            return
        self._check_alert_storm(alerts)
        if self._hist_sev_filter != {"INFO", "WARNING", "CRITICAL"}:
            alerts = [a for a in alerts if a.get("severity", "INFO") in self._hist_sev_filter]

        seen: dict = {}
        for alert in alerts:
            key = (alert.get("rule_name", ""), alert.get("host", ""))
            if key not in seen:
                seen[key] = (alert, 1)
            else:
                seen[key] = (seen[key][0], seen[key][1] + 1)
        grouped = list(seen.values())
        snoozes = self._router.get_all_snoozes() if self._router else {}

        from ui.widgets.skeleton import clear_skeleton_rows
        clear_skeleton_rows(self._alert_history_table)
        self._alert_history_table.setRowCount(0)
        for alert, count in grouped:
            row = self._alert_history_table.rowCount()
            self._alert_history_table.insertRow(row)
            ts_str    = time.strftime("%m-%d %H:%M", time.localtime(alert.get("ts", 0)))
            sev       = alert.get("severity", "INFO")
            sev_col   = _SEV_COLOR.get(sev, TEXT_PRIMARY)
            rule_name = alert.get("rule_name", "")
            rule_disp = f"{rule_name}  ×{count}" if count > 1 else rule_name
            snooze_expiry = snoozes.get(rule_name)
            if snooze_expiry is not None:
                if snooze_expiry == 0:
                    status = "Snoozed ∞"
                else:
                    status = time.strftime("Snoozed →%H:%M", time.localtime(snooze_expiry))
                st_col = TEXT_MUTED
            elif alert.get("acked_ts"):
                status = "✓ Acked"
                st_col = GREEN
            else:
                status = "Pending"
                st_col = AMBER
            for col, val in enumerate([ts_str, rule_disp, alert.get("host", ""), sev, status]):
                it = QTableWidgetItem(str(val))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 3:
                    it.setForeground(QColor(sev_col))
                elif col == 4:
                    it.setForeground(QColor(st_col))
                self._alert_history_table.setItem(row, col, it)
            self._alert_history_table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, alert
            )
            sub_label = _enrich_alert_sublabel(alert)
            _cw = QWidget()
            _cw.setAutoFillBackground(False)
            _cl = QVBoxLayout(_cw)
            _cl.setContentsMargins(4, 2, 4, 1)
            _cl.setSpacing(0)
            _lr = QLabel(rule_disp)
            _lr.setStyleSheet(
                f"color:{TEXT_PRIMARY}; font-size:11px; background:transparent; border:none;"
            )
            _cl.addWidget(_lr)
            if sub_label:
                _ls = QLabel(sub_label)
                _ls.setStyleSheet(
                    f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
                )
                _cl.addWidget(_ls)
            _cl.addStretch()
            self._alert_history_table.setCellWidget(row, 1, _cw)
            if sub_label:
                self._alert_history_table.setRowHeight(row, 36)

        has_rows = self._alert_history_table.rowCount() > 0
        self._hist_empty_lbl.setVisible(not has_rows)

    def _on_alert_row_single_click(self, item: QTableWidgetItem) -> None:
        first = self._alert_history_table.item(item.row(), 0)
        if first is None:
            return
        alert = first.data(Qt.ItemDataRole.UserRole)
        if isinstance(alert, dict):
            self._alert_drawer.open(alert)

    def _on_drawer_acknowledged(self, alert_id: int) -> None:
        from ui.widgets.toast import ToastManager
        ToastManager.show("Alert acknowledged", "success")
        self._refresh_alert_history()
        self.alert_acknowledged.emit()

    def _on_alert_history_row_clicked(self, item: QTableWidgetItem) -> None:
        first = self._alert_history_table.item(item.row(), 0)
        if first is None:
            return
        alert = first.data(Qt.ItemDataRole.UserRole)
        if not isinstance(alert, dict):
            return
        rule = alert.get("rule_name", "")
        host = alert.get("host") or alert.get("ip") or ""
        target = _cta_page_for_rule(rule)
        if target:
            self.navigate_to.emit(target)
            if host and target in ("Inventory Changes", "Devices"):
                self.select_inventory_device.emit(host)
        else:
            self.navigate_to.emit("Notifications")

    def _on_alert_history_context_menu(self, pos) -> None:
        row = self._alert_history_table.rowAt(pos.y())
        if row < 0:
            return
        first = self._alert_history_table.item(row, 0)
        if first is None:
            return
        alert = first.data(Qt.ItemDataRole.UserRole)
        if not isinstance(alert, dict):
            return
        rule_name = alert.get("rule_name", "")
        if not rule_name or not self._router:
            return
        host = alert.get("host") or alert.get("ip") or "*"
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            f" font-size:11px; }}"
            f"QMenu::item:selected {{ background:{ACCENT}; color:{WHITE}; }}"
        )
        _col = self._alert_history_table.currentColumn()
        act_copy_cell = menu.addAction("Copy cell")
        act_copy_row  = menu.addAction("Copy row")
        act_automate  = menu.addAction("Create automation rule…")
        menu.addSeparator()
        expiry = self._router.get_snooze_expiry(rule_name)
        if expiry is not None:
            label = (
                "Snoozed ∞" if expiry == 0
                else time.strftime("Snoozed until %H:%M", time.localtime(expiry))
            )
            menu.addAction(f"  {label}").setEnabled(False)
            menu.addSeparator()
            menu.addAction("Un-snooze").triggered.connect(
                lambda: self._apply_snooze(rule_name, None)
            )
        else:
            menu.addAction(f"Snooze: {rule_name}").setEnabled(False)
            menu.addSeparator()
            menu.addAction("Snooze 1 hour").triggered.connect(
                lambda: self._apply_snooze(rule_name, time.time() + 3600)
            )
            menu.addAction("Snooze 8 hours").triggered.connect(
                lambda: self._apply_snooze(rule_name, time.time() + 28800)
            )
            menu.addAction("Snooze forever").triggered.connect(
                lambda: self._apply_snooze(rule_name, 0)
            )
        chosen = menu.exec(self._alert_history_table.viewport().mapToGlobal(pos))
        if chosen == act_automate:
            self.automation_rule_requested.emit(rule_name, host)
        elif chosen == act_copy_cell:
            from PyQt6.QtWidgets import QApplication as _QApp
            it = self._alert_history_table.item(row, _col) if _col >= 0 else None
            _QApp.clipboard().setText(it.text() if it else "")
        elif chosen == act_copy_row:
            from PyQt6.QtWidgets import QApplication as _QApp
            parts = [
                (self._alert_history_table.item(row, c).text()
                 if self._alert_history_table.item(row, c) else "")
                for c in range(self._alert_history_table.columnCount())
            ]
            _QApp.clipboard().setText("\t".join(parts))

    def _export_alert_history_csv(self) -> None:
        from ui.widgets.toast import ToastManager
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Alert History", "alert_history.csv", "CSV files (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        tbl = self._alert_history_table
        cols = [tbl.horizontalHeaderItem(c).text() for c in range(tbl.columnCount())]
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = _csv.writer(f)
                w.writerow(cols)
                for r in range(tbl.rowCount()):
                    w.writerow([
                        (tbl.item(r, c).text() if tbl.item(r, c) else "")
                        for c in range(tbl.columnCount())
                    ])
            ToastManager.show(f"✓ Saved to {os.path.basename(path)}", "success")
        except Exception as exc:
            ToastManager.show(f"Export failed: {exc}", "error")

    def _on_hist_selection_changed(self) -> None:
        rows = {idx.row() for idx in self._alert_history_table.selectedIndexes()}
        n = len(rows)
        self._bulk_bar.setVisible(n > 0)
        if n > 0:
            self._bulk_lbl.setText(f"{n} selected")

    def _selected_alerts(self) -> list:
        rows = sorted({idx.row() for idx in self._alert_history_table.selectedIndexes()})
        alerts = []
        for r in rows:
            item = self._alert_history_table.item(r, 0)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict):
                    alerts.append(data)
        return alerts

    def _bulk_dismiss(self) -> None:
        alerts = self._selected_alerts()
        for alert in alerts:
            alert_id = alert.get("id") or alert.get("alert_id")
            if alert_id and self._store:
                try:
                    self._store.acknowledge_alert(int(alert_id))
                except Exception:
                    pass  # non-fatal
        self._alert_history_table.clearSelection()
        self._refresh_alert_history()
        self.alert_acknowledged.emit()
        if alerts:
            from ui.widgets.toast import ToastManager
            n = len(alerts)
            ToastManager.show(
                f"{n} alert{'s' if n != 1 else ''} acknowledged", "success"
            )

    def _bulk_snooze(self, seconds: int) -> None:
        until_ts = time.time() + seconds
        rule_names: set = set()
        for alert in self._selected_alerts():
            rn = alert.get("rule_name", "")
            if rn and rn not in rule_names:
                rule_names.add(rn)
                self._apply_snooze(rn, until_ts)
        self._alert_history_table.clearSelection()

    def _apply_snooze(self, rule_name: str, until_ts) -> None:
        if not self._router:
            return
        if until_ts is None:
            self._router.clear_snooze(rule_name)
        else:
            self._router.set_snooze(rule_name, until_ts)
        self._refresh_alert_history()

    def _toggle_hist_sev(self, sev: str, checked: bool) -> None:
        if checked:
            self._hist_sev_filter.add(sev)
        else:
            self._hist_sev_filter.discard(sev)
        self._refresh_alert_history()

    def _on_hist_time_changed(self, text: str) -> None:
        mapping = {"1h": 1.0, "6h": 6.0, "24h": 24.0, "72h": 72.0, "7d": 168.0}
        self._hist_hours = mapping.get(text, 72.0)
        self._refresh_alert_history()
