"""
DhcpLeasePage — DHCP Lease Inventory page (item 17).

Shows a live view of DHCP leases visible from the local machine:
  • KPI tiles: Total Leases, Active, Expired, Sources
  • Lease table: IP / MAC / Hostname / Expires / DHCP Server / Source
  • Refresh button + auto-refresh every 5 minutes
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.dhcp_lease_scanner import DhcpLease
from workers.dhcp_lease_worker import DhcpLeaseWorker
from ui.styles import (
    ACCENT,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    GREEN,
    RED,
    TABLE_SEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_TEXT,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setStyleSheet(
        f"QTableWidget {{ background:{BG_CARD}; border:none; font-size:11px;"
        f" color:{TEXT_PRIMARY}; alternate-background-color:{BG_ALT_ROW}; }}"
        f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT}; font-size:11px;"
        f" font-weight:bold; padding:4px 8px; border:none; }}"
        f"QTableWidget::item:hover {{ background:{BG_HOVER}; }}"
        f"QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
    )
    return t


def _cell(text: str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(int(align | Qt.AlignmentFlag.AlignVCenter))
    item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
    return item


def _expires_label(ts: int) -> str:
    if ts == 0:
        return "Permanent"
    now = int(time.time())
    if ts < now:
        return "Expired"
    try:
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        return dt
    except Exception:
        return str(ts)


def _make_kpi(label: str, value: str, accent_color: str = ACCENT) -> QFrame:
    frame = QFrame()
    frame.setFixedHeight(60)
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {accent_color}; }}"
    )
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(10, 6, 10, 6)
    lay.setSpacing(2)
    lbl = QLabel(label.upper())
    lbl.setStyleSheet(f"font-size:9px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;")
    val = QLabel(value)
    val.setObjectName("kpi_value")
    val.setStyleSheet(f"font-size:22px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")
    lay.addWidget(lbl)
    lay.addWidget(val)
    return frame


# ── Page ─────────────────────────────────────────────────────────────────────

class DhcpLeasePage(QWidget):
    """Displays DHCP lease inventory from local lease files / ARP cache."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Optional[DhcpLeaseWorker] = None
        self._leases: List[DhcpLease] = []
        self._setup_ui()
        # Auto-refresh every 5 minutes
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._run_scan)
        self._timer.start(300_000)
        # Initial load
        self._run_scan()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Page title
        title = QLabel("DHCP Lease Inventory")
        title.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY};"
        )
        root.addWidget(title)

        subtitle = QLabel(
            "DHCP leases visible from this machine — parsed from local lease files and ARP cache."
        )
        subtitle.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        root.addWidget(subtitle)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_total   = _make_kpi("Total Leases", "—")
        self._kpi_active  = _make_kpi("Active",       "—", GREEN)
        self._kpi_expired = _make_kpi("Expired",      "—", AMBER)
        self._kpi_sources = _make_kpi("Sources",      "—", ACCENT)
        for w in (self._kpi_total, self._kpi_active, self._kpi_expired, self._kpi_sources):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        root.addLayout(kpi_row)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(6)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedHeight(30)
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; font-size:12px;"
            f" font-weight:bold; border:none; border-radius:4px; padding:0 14px; }}"
            f"QPushButton:hover {{ background:#006BBD; }}"
            f"QPushButton:disabled {{ background:#B0C4D8; color:#9BA8B4; }}"
        )
        self._refresh_btn.clicked.connect(self._run_scan)
        self._status_lbl = QLabel("Click Refresh to load leases.")
        self._status_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        tb.addWidget(self._refresh_btn)
        tb.addWidget(self._status_lbl)
        tb.addStretch()
        root.addLayout(tb)

        # Table card
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        card_title = QLabel("  DHCP Leases")
        card_title.setFixedHeight(32)
        card_title.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" border-bottom:1px solid #ECECEC; background:{BG_CARD};"
        )
        card_lay.addWidget(card_title)

        self._table = _make_table(
            ["IP Address", "MAC Address", "Hostname", "Expires", "DHCP Server", "Source"]
        )
        card_lay.addWidget(self._table)
        root.addWidget(card, stretch=1)

        # Empty state placeholder
        self._empty_widget = QWidget()
        _el = QVBoxLayout(self._empty_widget)
        _el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _el.setSpacing(10)
        _el.setContentsMargins(40, 20, 40, 20)
        _empty_lbl = QLabel(
            "No DHCP leases found — this page reads lease files from\n"
            "your system and the ARP cache. Click below to scan again."
        )
        _empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _empty_lbl.setWordWrap(True)
        _empty_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        _el.addWidget(_empty_lbl)
        _btn_empty_scan = QPushButton("▶  Scan DHCP Leases")
        _btn_empty_scan.setFixedHeight(32)
        _btn_empty_scan.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; font-size:12px;"
            f" font-weight:bold; border:none; border-radius:4px; padding:0 16px; }}"
            f"QPushButton:hover {{ background:#006BBD; }}"
        )
        _btn_empty_scan.clicked.connect(self._run_scan)
        _el.addWidget(_btn_empty_scan, alignment=Qt.AlignmentFlag.AlignCenter)
        self._empty_widget.hide()
        root.addWidget(self._empty_widget)

    # ── Scan logic ────────────────────────────────────────────────────────────

    def _run_scan(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._status_lbl.setText("Scanning…")
        self._worker = DhcpLeaseWorker()
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, leases: List[DhcpLease]) -> None:
        self._leases = leases
        self._refresh_btn.setEnabled(True)
        self._populate(leases)

    def _on_error(self, msg: str) -> None:
        self._refresh_btn.setEnabled(True)
        self._status_lbl.setText(f"Error: {msg}")

    # ── Table population ──────────────────────────────────────────────────────

    def _populate(self, leases: List[DhcpLease]) -> None:
        now = int(time.time())
        active  = [l for l in leases if l.expires == 0 or l.expires > now]
        expired = [l for l in leases if l.expires != 0 and l.expires <= now]
        sources = len({l.source for l in leases if l.source})

        # Update KPIs
        def _set_kpi(frame: QFrame, value: str) -> None:
            frame.findChild(QLabel, "kpi_value").setText(value)

        _set_kpi(self._kpi_total,   str(len(leases)))
        _set_kpi(self._kpi_active,  str(len(active)))
        _set_kpi(self._kpi_expired, str(len(expired)))
        _set_kpi(self._kpi_sources, str(sources))

        if not leases:
            self._table.setRowCount(0)
            self._empty_widget.show()
            self._status_lbl.setText("No lease data found.")
            return

        self._empty_widget.hide()
        self._table.setRowCount(0)
        self._table.setSortingEnabled(False)

        for lease in leases:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, _cell(lease.ip))
            self._table.setItem(row, 1, _cell(lease.mac or "—"))
            self._table.setItem(row, 2, _cell(lease.hostname or "—"))

            exp_label = _expires_label(lease.expires)
            exp_item  = _cell(exp_label, Qt.AlignmentFlag.AlignCenter)
            if exp_label == "Expired":
                exp_item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(RED)
                )
            elif exp_label == "Permanent":
                exp_item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(TEXT_SECONDARY)
                )
            self._table.setItem(row, 3, exp_item)

            self._table.setItem(row, 4, _cell(lease.server or "—"))
            self._table.setItem(row, 5, _cell(lease.source or "—"))

        self._table.setSortingEnabled(True)
        self._table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._status_lbl.setText(
            f"Loaded {len(leases)} lease(s). "
            f"Last refreshed {datetime.now().strftime('%H:%M:%S')}."
        )
