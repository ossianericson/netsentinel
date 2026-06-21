"""
DhcpLeasePage — DHCP Lease Inventory page (item 17).

Shows a live view of DHCP leases visible from the local machine:
  • KPI tiles: Total Leases, Active, Expired, Sources
  • Lease table: IP / MAC / Hostname / Expires / DHCP Server / Source
  • Refresh button + auto-refresh every 5 minutes
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.dhcp_lease_scanner import DhcpLease
from workers.dhcp_lease_worker import DhcpLeaseWorker
from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_HOVER,
    BORDER,
    BTN_DISABLED_BORDER,
    CARD_HDR_BORDER,
    GREEN,
    INPUT_PLACEHOLDER,
    RED,
    TABLE_SEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_TEXT,
    WHITE,
)
from ui.table_utils import kpi_tile as _shared_kpi_tile, restore_column_widths, save_column_widths
from ui.widgets.empty_state_card import EmptyStateCard


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
    item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
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




# ── Page ─────────────────────────────────────────────────────────────────────

class DhcpLeasePage(QWidget):
    """Displays DHCP lease inventory from local lease files / ARP cache."""

    navigate_to    = pyqtSignal(str)  # page label
    select_device  = pyqtSignal(str)  # IP address
    scan_requested = pyqtSignal()     # emitted by empty-state CTA

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

    def showEvent(self, event) -> None:
        restore_column_widths(self._table, "dhcp")
        super().showEvent(event)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Page title
        from ui.widgets.page_header import PageHeaderBar
        _hdr = PageHeaderBar("DHCP Lease Inventory", subtitle="Lists all IP addresses currently assigned to devices by your router.")
        _hdr.show_first_visit_banner(
            "dhcp_lease",
            "Each row is a lease your router's DHCP server handed out. A device with a lease "
            "about to expire will usually renew automatically — only worry if a device "
            "disappears and never comes back.",
        )
        root.addWidget(_hdr)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        t1, self._kpi_total_lbl   = _shared_kpi_tile("Total Leases", "—")
        t2, self._kpi_active_lbl  = _shared_kpi_tile("Active",       "—", GREEN)
        t3, self._kpi_expired_lbl = _shared_kpi_tile("Expired",      "—", AMBER)
        t4, self._kpi_sources_lbl = _shared_kpi_tile("Sources",      "—", ACCENT)
        for w in (t1, t2, t3, t4):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        root.addLayout(kpi_row)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(6)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedHeight(30)
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; font-size:12px;"
            f" font-weight:bold; border:none; border-radius:4px; padding:0 14px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:disabled {{ background:{BTN_DISABLED_BORDER}; color:{INPUT_PLACEHOLDER}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._refresh_btn.clicked.connect(self._run_scan)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter by IP, MAC, or hostname…")
        self._search_box.setFixedWidth(240)
        self._search_box.setFixedHeight(30)
        self._search_box.setStyleSheet(
            f"QLineEdit {{ font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            f" border-radius:3px; padding:0 8px; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_box.textChanged.connect(self._search_timer.start)
        self._search_timer.timeout.connect(self._apply_filter)

        self._status_lbl = QLabel("Click Refresh to load leases.")
        self._status_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        tb.addWidget(self._refresh_btn)
        tb.addWidget(self._search_box)
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
            f" border-bottom:1px solid {CARD_HDR_BORDER}; background:{BG_CARD};"
        )
        card_lay.addWidget(card_title)

        self._table = _make_table(
            ["IP Address", "MAC Address", "Hostname", "Expires", "DHCP Server", "Source"]
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)

        from ui.widgets.density_toggle import DensityToggle
        from PyQt6.QtWidgets import QHBoxLayout as _QHL
        _dt_row = _QHL()
        _dt_row.setContentsMargins(8, 4, 8, 0)
        _dt_row.addStretch()
        _dt_row.addWidget(DensityToggle("dhcp_leases", self._table))
        card_lay.addLayout(_dt_row)
        card_lay.addWidget(self._table)
        self._table.horizontalHeader().sectionResized.connect(
            lambda _l, _o, _n: save_column_widths(self._table, "dhcp")
        )

        # ── Empty state + content stack ───────────────────────────────────────
        from PyQt6.QtWidgets import QStackedWidget
        self._content_stack = QStackedWidget()

        _empty = EmptyStateCard(
            icon="◆",
            title="DHCP Lease Inventory",
            what_it_shows=(
                "Every IP address currently assigned by your router's DHCP server — "
                "hostname, MAC, expiry time, and which DHCP server handed it out."
            ),
            why_it_matters=(
                "A rogue DHCP server can redirect all your network traffic. "
                "Seeing an unexpected server here is an immediate red flag."
            ),
            btn_label="Scan DHCP Leases",
        )
        _empty.clicked.connect(self.scan_requested.emit)
        _empty.clicked.connect(self._run_scan)

        _content_w = QWidget()
        _content_lay = QVBoxLayout(_content_w)
        _content_lay.setContentsMargins(0, 0, 0, 0)
        _content_lay.setSpacing(0)
        _content_lay.addWidget(card, stretch=1)

        self._content_stack.addWidget(_empty)    # index 0 — empty state
        self._content_stack.addWidget(_content_w)  # index 1 — content
        root.addWidget(self._content_stack, stretch=1)

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
        self._apply_filter()

    def _on_error(self, msg: str) -> None:
        self._refresh_btn.setEnabled(True)
        self._status_lbl.setText(
            f"DHCP lease scan failed — {msg}. "
            "Check that you are running as administrator and your network adapter is active."
        )

    # ── Table population ──────────────────────────────────────────────────────

    def _apply_filter(self) -> None:
        """Filter self._leases by search text and repopulate the table."""
        query = self._search_box.text().strip().lower()
        if query:
            filtered = [
                l for l in self._leases
                if query in l.ip.lower()
                or query in (l.mac or "").lower()
                or query in (l.hostname or "").lower()
            ]
        else:
            filtered = self._leases
        self._populate(filtered)

    def _populate(self, leases: List[DhcpLease]) -> None:
        now = int(time.time())
        all_leases = self._leases
        active  = [l for l in all_leases if l.expires == 0 or l.expires > now]
        expired = [l for l in all_leases if l.expires != 0 and l.expires <= now]
        sources = len({l.source for l in all_leases if l.source})

        self._kpi_total_lbl.set_value(len(all_leases))
        self._kpi_active_lbl.set_value(len(active))
        self._kpi_expired_lbl.set_value(len(expired))
        self._kpi_sources_lbl.set_value(sources)

        visible = len(leases)
        total = len(all_leases)
        if not leases:
            self._table.setRowCount(0)
            self._content_stack.setCurrentIndex(0)
            self._status_lbl.setText("No lease data found.")
            return

        self._content_stack.setCurrentIndex(1)
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
        suffix = f" · showing {visible} of {total}" if visible != total else f" · {total} lease(s)"
        self._status_lbl.setText(
            f"Last refreshed {datetime.now().strftime('%H:%M:%S')}{suffix}."
        )

    # ── Context menu ──────────────────────────────────────────────────────────

    def _on_table_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        ip_item = self._table.item(row, 0)
        if not ip_item:
            return
        ip = ip_item.text()

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            f" font-size:11px; }}"
            f"QMenu::item:selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            f"QMenu::separator {{ height:1px; background:{BORDER}; margin:2px 0; }}"
        )

        act_inv = menu.addAction("▶  Find in Inventory →")
        act_inv.triggered.connect(lambda: self._find_in_inventory(ip))
        menu.addSeparator()
        act_copy = menu.addAction("Copy IP")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(ip))
        mac_item = self._table.item(row, 1)
        if mac_item and mac_item.text() not in ("", "—"):
            act_copy_mac = menu.addAction("Copy MAC")
            act_copy_mac.triggered.connect(
                lambda: QApplication.clipboard().setText(mac_item.text())
            )
        menu.addSeparator()
        _server_item = self._table.item(row, 4)
        _server = _server_item.text() if _server_item else ""
        act_fix = menu.addAction("How to Fix")
        act_fix.triggered.connect(lambda: self._show_dhcp_fix(ip, _server))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _show_dhcp_fix(self, ip: str, server: str) -> None:
        from PyQt6.QtWidgets import QMessageBox
        if server and server not in ("—", ""):
            msg = (
                f"<b>{ip}</b> was assigned by DHCP server <b>{server}</b>.<br><br>"
                "If you don't recognise this DHCP server, it may be a rogue server "
                "handing out addresses and redirecting your traffic.<br><br>"
                "<b>Steps to investigate:</b><br>"
                "1. Open the <b>Devices</b> page — find the device at this server IP and verify its vendor.<br>"
                "2. Check your router admin panel to confirm the authorised DHCP server address.<br>"
                "3. If the server is unexpected: isolate it and run a port scan on it.<br>"
                "4. Enable DHCP snooping on your managed switch if available."
            )
        else:
            msg = (
                f"<b>{ip}</b> — DHCP lease found on your network.<br><br>"
                "1. Open the <b>Devices</b> page to identify the vendor and label this device.<br>"
                "2. If you don't recognise this IP, check the MAC address against known devices.<br>"
                "3. Unknown devices should be investigated before being trusted on your network."
            )
        QMessageBox.information(self, "How to Fix", msg)

    def _find_in_inventory(self, ip: str) -> None:
        self.select_device.emit(ip)
        self.navigate_to.emit("Devices")
