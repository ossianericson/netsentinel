"""
LogHubPage — unified log viewer for all NetSentinel log sources.

Three inner tabs (QTabWidget):
  Network Log  — continuous ping logger entries (CSV + live feed)
  Syslog       — received syslog messages
  SNMP Traps   — received SNMP traps

Wiring (in app.py after window creation):
    syslog_worker.message_received.connect(window._log_hub_page.on_syslog_message)
    snmp_trap_worker.trap_received.connect(window._log_hub_page.on_snmp_trap)
    window._logger_worker_started.connect(window._log_hub_page._bind_logger_worker)

Or simpler: call log_hub_page.add_log_entry(entry) from _on_log_entry in dashboard.
"""
from __future__ import annotations

import time as _t
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BG_HOVER, BG_ALT_ROW,
    BORDER, CARD_RADIUS, GREEN, RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, TH_BG, TH_TEXT,
)

_MAX_ROWS = 500
_LIVE_CHALLENGE_COOLDOWN = 60.0  # seconds between live-challenge emissions


# ── Live challenge builder ─────────────────────────────────────────────────────

def _build_live_scenario(entry, consecutive_fails: int = 0):
    """Return a one-step LabScenario for an interesting log entry, or None."""
    from modules.lab_scenarios import LabScenario, LabStep
    if entry.arp_event and entry.arp_event.startswith("NEW"):
        return LabScenario(
            id="live_new_device",
            title="New Device Detected",
            goal="A new device just appeared on your network. Investigate whether it belongs here.",
            effort="S",
            steps=[
                LabStep(
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
                ),
            ],
        )
    if entry.dns_ms >= 0 and entry.dns_ms > 200:
        return LabScenario(
            id="live_slow_dns",
            title="Slow DNS Detected",
            goal=f"DNS latency spiked to {entry.dns_ms:.0f} ms. Diagnose your resolver.",
            effort="S",
            steps=[
                LabStep(
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
                ),
            ],
        )
    if consecutive_fails >= 3:
        return LabScenario(
            id="live_connectivity_fail",
            title="Connectivity Issues Detected",
            goal="Multiple consecutive failures were logged. Diagnose your connection.",
            effort="S",
            steps=[
                LabStep(
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
                ),
            ],
        )
    return None


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(True)
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
        f"QTableWidget::item:selected {{ background:#CCE4F7; color:{TEXT_PRIMARY}; }}"
        f"QTableWidget::item:hover {{ background:{BG_HOVER}; }}"
        f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
    )
    return t


def _card_frame(title: str) -> tuple[QFrame, QVBoxLayout]:
    outer = QFrame()
    outer.setObjectName("logcard")
    outer.setStyleSheet(
        f"QFrame#logcard {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-radius:{CARD_RADIUS}; }}"
    )
    lay = QVBoxLayout(outer)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    hdr = QLabel(title)
    hdr.setFixedHeight(32)
    hdr.setStyleSheet(
        f"QLabel {{ background:{BG_CARD}; border-bottom:1px solid #ECECEC;"
        f" padding:0 12px; font-size:13px; font-weight:bold; color:{TEXT_PRIMARY}; }}"
    )
    lay.addWidget(hdr)
    return outer, lay


def _status_color(status: str) -> str:
    return {
        "OK":   GREEN,
        "SLOW": AMBER,
        "FAIL": RED,
    }.get(status.upper(), TEXT_SECONDARY)


# ── Network Log tab ────────────────────────────────────────────────────────────

class _NetworkLogTab(QWidget):
    """Reads the most recent logger CSV and accepts live entries."""

    animate_requested    = pyqtSignal(object)  # emits LogEntry when ARP button clicked
    live_challenge_detected = pyqtSignal(object)  # emits LabScenario for interesting events
    _HEADERS = ["Time", "Host", "RTT (ms)", "Jitter", "DNS (ms)", "HTTP", "ARP Event", "Status"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_entries: list = []  # parallel to _all_rows, stores raw entry objects
        self._consecutive_fails: int = 0
        self._last_live_challenge: float = 0.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        self._status_lbl = QLabel("No logger data yet.")
        self._status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        toolbar.addWidget(self._status_lbl)
        toolbar.addStretch()

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter by host…")
        self._filter_edit.setFixedWidth(180)
        self._filter_edit.setStyleSheet(
            f"QLineEdit {{ border:1px solid {BORDER}; border-radius:4px;"
            f" padding:2px 6px; font-size:11px; background:{BG_CARD}; color:{TEXT_PRIMARY}; }}"
        )
        self._filter_edit.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self._filter_edit)

        _reload_btn = QPushButton("↺  Reload")
        _reload_btn.setFixedHeight(26)
        _reload_btn.setStyleSheet(
            f"QPushButton {{ border:1px solid {BORDER}; border-radius:4px;"
            f" padding:0 10px; font-size:11px; background:{BG_CARD}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
        )
        _reload_btn.clicked.connect(self._load_from_csv)
        toolbar.addWidget(_reload_btn)

        lay.addLayout(toolbar)

        card, card_lay = _card_frame("Network Log")
        self._table = _make_table(self._HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(
            0, self._table.horizontalHeader().ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(
            1, self._table.horizontalHeader().ResizeMode.ResizeToContents)
        card_lay.addWidget(self._table)
        lay.addWidget(card)

        self._all_rows: list[tuple] = []  # cache for filter

        # Auto-load CSV after widget is shown
        QTimer.singleShot(200, self._load_from_csv)

    def _load_from_csv(self) -> None:
        try:
            from modules.network_logger import list_log_files, load_log_file
            files = list_log_files()
            if not files:
                self._status_lbl.setText("No log files found.")
                return
            summary = load_log_file(files[0])
            entries = summary.entries[-_MAX_ROWS:]
            entries.reverse()  # newest first
            self._all_entries = list(entries)
            self._all_rows = [
                (
                    e.timestamp, e.host,
                    f"{e.rtt_ms:.0f}" if e.rtt_ms >= 0 else "—",
                    f"{e.jitter_ms:.0f}" if e.jitter_ms >= 0 else "",
                    f"{e.dns_ms:.0f}" if e.dns_ms >= 0 else "",
                    str(e.http_status) if e.http_status >= 0 else "",
                    e.arp_event or "",
                    e.status,
                )
                for e in entries
            ]
            self._render_rows()
            self._status_lbl.setText(
                f"{len(summary.entries)} entries from {files[0].name}  ·  "
                f"Uptime {summary.uptime_pct:.1f}%"
            )
        except Exception as exc:
            self._status_lbl.setText(f"Load error: {exc}")

    def add_log_entry(self, entry) -> None:
        """Called live from LoggerWorker.entry_received signal."""
        # Track consecutive failures for live-challenge detection
        if entry.status == "FAIL":
            self._consecutive_fails += 1
        else:
            self._consecutive_fails = 0

        # Emit a live challenge at most once per cooldown window
        now = _t.time()
        if now - self._last_live_challenge > _LIVE_CHALLENGE_COOLDOWN:
            scenario = _build_live_scenario(entry, self._consecutive_fails)
            if scenario is not None:
                self._last_live_challenge = now
                self.live_challenge_detected.emit(scenario)

        row = (
            entry.timestamp, entry.host,
            f"{entry.rtt_ms:.0f}" if entry.rtt_ms >= 0 else "—",
            f"{entry.jitter_ms:.0f}" if entry.jitter_ms >= 0 else "",
            f"{entry.dns_ms:.0f}" if entry.dns_ms >= 0 else "",
            str(entry.http_status) if entry.http_status >= 0 else "",
            entry.arp_event or "",
            entry.status,
        )
        self._all_rows.insert(0, row)
        self._all_entries.insert(0, entry)
        if len(self._all_rows) > _MAX_ROWS:
            self._all_rows = self._all_rows[:_MAX_ROWS]
            self._all_entries = self._all_entries[:_MAX_ROWS]

        filt = self._filter_edit.text().strip().lower()
        if filt and filt not in entry.host.lower():
            return
        self._table.insertRow(0)
        self._set_table_row(0, row, entry)
        if self._table.rowCount() > _MAX_ROWS:
            self._table.setRowCount(_MAX_ROWS)
        self._status_lbl.setText(
            f"Live · last: {entry.host}  {entry.status}  {entry.rtt_ms:.0f} ms"
            if entry.rtt_ms >= 0 else
            f"Live · last: {entry.host}  {entry.status}"
        )

    def _apply_filter(self, text: str) -> None:
        filt = text.strip().lower()
        pairs = [(r, e) for r, e in zip(self._all_rows, self._all_entries)
                 if not filt or filt in r[1].lower()]
        self._table.setRowCount(0)
        for i, (row, entry) in enumerate(pairs[:_MAX_ROWS]):
            self._table.insertRow(i)
            self._set_table_row(i, row, entry)

    def _render_rows(self) -> None:
        filt = self._filter_edit.text().strip().lower()
        pairs = [(r, e) for r, e in zip(self._all_rows, self._all_entries)
                 if not filt or filt in r[1].lower()]
        self._table.setRowCount(0)
        for i, (row, entry) in enumerate(pairs[:_MAX_ROWS]):
            self._table.insertRow(i)
            self._set_table_row(i, row, entry)

    def _set_table_row(self, row_idx: int, vals: tuple, entry=None) -> None:
        status = vals[7]
        sc = _status_color(status)
        for col, val in enumerate(vals):
            if col == 6 and val and entry is not None:
                # ARP event cell: replace with a clickable button
                btn = QPushButton(f"▶ ARP  {val[:30]}")
                btn.setStyleSheet(
                    f"QPushButton {{ background:transparent; border:none; color:{AMBER};"
                    f" font-size:10px; text-align:left; padding:0 4px; }}"
                    f"QPushButton:hover {{ color:{ACCENT}; text-decoration:underline; }}"
                )
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _e = entry
                btn.clicked.connect(lambda _=False, e=_e: self.animate_requested.emit(e))
                self._table.setCellWidget(row_idx, col, btn)
            else:
                item = QTableWidgetItem(str(val))
                c = sc if col == 7 else TEXT_PRIMARY
                item.setForeground(QColor(c))
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._table.setItem(row_idx, col, item)


# ── Syslog tab ────────────────────────────────────────────────────────────────

_SYSLOG_SEVERITY_COLOR = {
    "EMERG": RED, "ALERT": RED, "CRIT": RED,
    "ERR":   AMBER, "WARNING": AMBER,
    "NOTICE": TEXT_PRIMARY, "INFO": TEXT_PRIMARY, "DEBUG": TEXT_MUTED,
}


class _SyslogTab(QWidget):
    _HEADERS = ["Time", "Source IP", "Severity", "Facility", "Host", "App", "Message"]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self._status_lbl = QLabel("Waiting for syslog messages…")
        self._status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._status_lbl)

        card, card_lay = _card_frame("Syslog")
        self._table = _make_table(self._HEADERS)
        card_lay.addWidget(self._table)
        lay.addWidget(card)

        self._count = 0

    @pyqtSlot(object)
    def on_syslog_message(self, msg) -> None:
        self._count += 1
        severity = getattr(msg, "severity", "INFO")
        row_vals = [
            getattr(msg, "timestamp", ""),
            getattr(msg, "source_ip", ""),
            severity,
            getattr(msg, "facility", ""),
            getattr(msg, "hostname", ""),
            getattr(msg, "app_name", ""),
            getattr(msg, "message", str(msg)),
        ]
        sc = _SYSLOG_SEVERITY_COLOR.get(severity.upper(), TEXT_PRIMARY)
        self._table.insertRow(0)
        for col, val in enumerate(row_vals):
            item = QTableWidgetItem(str(val))
            item.setForeground(QColor(sc if col == 2 else TEXT_PRIMARY))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setItem(0, col, item)
        if self._table.rowCount() > _MAX_ROWS:
            self._table.setRowCount(_MAX_ROWS)
        self._status_lbl.setText(f"{self._count} syslog message{'s' if self._count != 1 else ''} received")


# ── SNMP Traps tab ────────────────────────────────────────────────────────────

class _SnmpTab(QWidget):
    _HEADERS = ["Time", "Source IP", "Version", "Community", "Trap Type", "OID"]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self._status_lbl = QLabel("Waiting for SNMP traps…")
        self._status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._status_lbl)

        card, card_lay = _card_frame("SNMP Traps")
        self._table = _make_table(self._HEADERS)
        card_lay.addWidget(self._table)
        lay.addWidget(card)

        self._count = 0

    @pyqtSlot(object)
    def on_snmp_trap(self, trap) -> None:
        self._count += 1
        row_vals = [
            getattr(trap, "timestamp", ""),
            getattr(trap, "source_ip", ""),
            getattr(trap, "version", ""),
            getattr(trap, "community", ""),
            getattr(trap, "trap_type", ""),
            getattr(trap, "oid", ""),
        ]
        self._table.insertRow(0)
        for col, val in enumerate(row_vals):
            item = QTableWidgetItem(str(val))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setItem(0, col, item)
        if self._table.rowCount() > _MAX_ROWS:
            self._table.setRowCount(_MAX_ROWS)
        self._status_lbl.setText(f"{self._count} SNMP trap{'s' if self._count != 1 else ''} received")


# ── LogHubPage ────────────────────────────────────────────────────────────────

class LogHubPage(QWidget):
    """
    Unified log viewer — three tabs: Network Log, Syslog, SNMP Traps.

    Wiring (call from dashboard or app.py after workers start):
        logger_worker.entry_received.connect(page.add_log_entry)
        syslog_worker.message_received.connect(page.on_syslog_message)
        snmp_trap_worker.trap_received.connect(page.on_snmp_trap)
        page.animate_requested.connect(dashboard._on_animate_log_entry)
    """

    animate_requested       = pyqtSignal(object)  # forwards from _NetworkLogTab
    live_challenge_detected = pyqtSignal(object)  # forwards from _NetworkLogTab

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Page header
        hdr = QLabel("Logs")
        hdr.setFixedHeight(32)
        hdr.setStyleSheet(
            f"QLabel {{ background:{BG_DARK}; font-size:15px; font-weight:bold;"
            f" color:{TEXT_PRIMARY}; padding:0 16px; border-bottom:1px solid {BORDER}; }}"
        )
        root.addWidget(hdr)

        # Scroll wrapper
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG_DARK}; border:none; }}")
        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(16, 12, 16, 12)
        inner_lay.setSpacing(0)

        # Inner QTabWidget
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border:1px solid {BORDER}; background:{BG_CARD};"
            f" border-radius:{CARD_RADIUS}; }}"
            f"QTabBar::tab {{ background:{BG_DARK}; color:{TEXT_SECONDARY};"
            f" padding:6px 18px; font-size:12px; border:1px solid {BORDER};"
            f" border-bottom:none; margin-right:2px; }}"
            f"QTabBar::tab:selected {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" font-weight:bold; }}"
            f"QTabBar::tab:hover {{ background:{BG_HOVER}; }}"
        )

        self._net_log_tab  = _NetworkLogTab()
        self._syslog_tab   = _SyslogTab()
        self._snmp_tab     = _SnmpTab()
        self._net_log_tab.animate_requested.connect(self.animate_requested)
        self._net_log_tab.live_challenge_detected.connect(self.live_challenge_detected)

        self._tabs.addTab(self._net_log_tab, "Network Log")
        self._tabs.addTab(self._syslog_tab,  "Syslog")
        self._tabs.addTab(self._snmp_tab,     "SNMP Traps")

        inner_lay.addWidget(self._tabs)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_log_entry(self, entry) -> None:
        """Forward live logger entries to the Network Log tab."""
        self._net_log_tab.add_log_entry(entry)

    @pyqtSlot(object)
    def on_syslog_message(self, msg) -> None:
        """Forward syslog messages to the Syslog tab."""
        self._syslog_tab.on_syslog_message(msg)

    @pyqtSlot(object)
    def on_snmp_trap(self, trap) -> None:
        """Forward SNMP traps to the SNMP Traps tab."""
        self._snmp_tab.on_snmp_trap(trap)

    def show_network_log(self) -> None:
        """Switch to the Network Log tab (called from status bar click)."""
        self._tabs.setCurrentIndex(0)
