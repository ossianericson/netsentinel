"""
DnsZonePage — DNS Zone Mapping page (item 18).

Two panels in a horizontal splitter:
  Left  — AXFR Records table (DNS records from zone transfer)
  Right — mDNS Services table (Bonjour/Avahi services on the LAN)

Controls:
  • DNS Server field + Domain field + AXFR button
  • mDNS Enumerate button (separate — doesn't need server/domain)
  • KPI tiles: Total Records, Zone Transferred, mDNS Services, Record Types

Colours from ui/styles.py; no dark content areas; 24px row height.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.dns_zone_scanner import DnsRecord, DnsZoneResult, MdnsService
from workers.dns_zone_worker import DnsZoneWorker
from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    BTN_DISABLED_BORDER,
    CARD_HDR_BORDER,
    GREEN,
    INPUT_PLACEHOLDER,
    PROGRESS_TRACK,
    RED,
    TABLE_SEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_TEXT,
    WHITE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _cell(text: str, align=Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(int(align | Qt.AlignmentFlag.AlignVCenter))
    item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
    return item


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setStyleSheet(f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; }}")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    hdr = QLabel(f"  {title}")
    hdr.setFixedHeight(32)
    hdr.setStyleSheet(
        f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
        f" border-bottom:1px solid {CARD_HDR_BORDER}; background:{BG_CARD};"
    )
    lay.addWidget(hdr)
    return frame, lay


def _make_kpi(label: str, value: str, color: str = ACCENT) -> QFrame:
    frame = QFrame()
    frame.setFixedHeight(60)
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {color}; }}"
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


def _btn(text: str, primary: bool = True) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(30)
    if primary:
        b.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; font-size:12px;"
            f" font-weight:bold; border:none; border-radius:4px; padding:0 14px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:disabled {{ background:{BTN_DISABLED_BORDER}; color:{INPUT_PLACEHOLDER}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ background:{WHITE}; color:{ACCENT}; font-size:12px;"
            f" border:1px solid {ACCENT}; border-radius:4px; padding:0 14px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:disabled {{ background:{BG_DARK}; color:{INPUT_PLACEHOLDER}; border-color:{BTN_DISABLED_BORDER}; }}"
            f"QPushButton:pressed {{ color:{ACCENT}; }}"
        )
    return b


def _field(placeholder: str, width: int = 180) -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setFixedHeight(30)
    e.setFixedWidth(width)
    e.setStyleSheet(
        f"QLineEdit {{ border:1px solid {BORDER}; border-radius:4px; padding:0 8px;"
        f" font-size:11px; color:{TEXT_PRIMARY}; background:{WHITE}; }}"
        f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
    )
    return e


# ── Page ─────────────────────────────────────────────────────────────────────

class DnsZonePage(QWidget):
    """DNS Zone Mapping — AXFR records + mDNS LAN service enumeration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Optional[DnsZoneWorker] = None
        self._setup_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Title
        from ui.widgets.page_header import PageHeaderBar
        root.addWidget(PageHeaderBar("DNS Zone Mapping"))

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_records  = _make_kpi("DNS Records",    "—")
        self._kpi_axfr     = _make_kpi("Zone Transferred","—", GREEN)
        self._kpi_mdns     = _make_kpi("mDNS Services",  "—", ACCENT)
        self._kpi_types    = _make_kpi("Record Types",   "—", AMBER)
        for w in (self._kpi_records, self._kpi_axfr, self._kpi_mdns, self._kpi_types):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        root.addLayout(kpi_row)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(6)

        tb.addWidget(QLabel("DNS Server:"))
        self._server_field = _field("192.168.1.1")
        tb.addWidget(self._server_field)

        tb.addWidget(QLabel("Domain:"))
        self._domain_field = _field("example.local")
        tb.addWidget(self._domain_field)

        self._axfr_btn = _btn("AXFR Transfer")
        self._axfr_btn.clicked.connect(self._run_axfr)
        tb.addWidget(self._axfr_btn)

        self._mdns_btn = _btn("Enumerate mDNS", primary=False)
        self._mdns_btn.clicked.connect(self._run_mdns)
        tb.addWidget(self._mdns_btn)

        self._status_lbl = QLabel("Enter a DNS server and domain, or click 'Enumerate mDNS'.")
        self._status_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        tb.addWidget(self._status_lbl)
        tb.addStretch()
        root.addLayout(tb)

        # Content — horizontal splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(f"QSplitter::handle {{ background:{PROGRESS_TRACK}; }}")

        # Left: AXFR records
        left_card, left_lay = _card("DNS Zone Records (AXFR)")
        self._rec_table = _make_table(["Name", "Type", "Value", "TTL"])
        self._rec_empty = QLabel("No records — run AXFR or server refused transfer.")
        self._rec_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rec_empty.setStyleSheet(f"font-size:12px; color:{INPUT_PLACEHOLDER};")
        left_lay.addWidget(self._rec_table)
        left_lay.addWidget(self._rec_empty)
        splitter.addWidget(left_card)

        # Right: mDNS services
        right_card, right_lay = _card("LAN mDNS Services (Bonjour / Avahi)")
        self._svc_table = _make_table(
            ["Service Type", "Instance", "Host", "IP", "Port", "TXT"]
        )
        self._svc_empty = QLabel("No mDNS services discovered. Click 'Enumerate mDNS'.")
        self._svc_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._svc_empty.setStyleSheet(f"font-size:12px; color:{INPUT_PLACEHOLDER};")
        right_lay.addWidget(self._svc_table)
        right_lay.addWidget(self._svc_empty)
        splitter.addWidget(right_card)

        splitter.setSizes([500, 500])
        root.addWidget(splitter, stretch=1)

    # ── Scan triggering ───────────────────────────────────────────────────────

    def _run_axfr(self) -> None:
        server = self._server_field.text().strip()
        domain = self._domain_field.text().strip()
        if not server or not domain:
            self._status_lbl.setText("Please enter both a DNS server IP and a domain name.")
            return
        self._start_worker(axfr_server=server, axfr_domain=domain, mdns_timeout=0.0)

    def _run_mdns(self) -> None:
        self._start_worker(axfr_server="", axfr_domain="", mdns_timeout=3.0)

    def _start_worker(
        self,
        axfr_server: str,
        axfr_domain: str,
        mdns_timeout: float,
    ) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._axfr_btn.setEnabled(False)
        self._mdns_btn.setEnabled(False)
        self._status_lbl.setText("Scanning…")
        self._worker = DnsZoneWorker(
            axfr_server=axfr_server,
            axfr_domain=axfr_domain,
            mdns_timeout=mdns_timeout,
        )
        self._worker.progress.connect(self._status_lbl.setText)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, result: DnsZoneResult) -> None:
        self._axfr_btn.setEnabled(True)
        self._mdns_btn.setEnabled(True)
        self._populate(result)

    def _on_error(self, msg: str) -> None:
        self._axfr_btn.setEnabled(True)
        self._mdns_btn.setEnabled(True)
        self._status_lbl.setText(
            f"DNS zone scan failed — {msg}. "
            "AXFR requires the DNS server to allow zone transfers; mDNS requires local network access."
        )

    # ── Table population ──────────────────────────────────────────────────────

    def _populate(self, result: DnsZoneResult) -> None:
        # KPIs
        record_types = len({r.rtype for r in result.records})

        def _set_kpi(frame: QFrame, value: str) -> None:
            frame.findChild(QLabel, "kpi_value").setText(value)

        _set_kpi(self._kpi_records, str(len(result.records)))
        _set_kpi(self._kpi_axfr,    "Yes" if result.axfr_ok else "No")
        _set_kpi(self._kpi_mdns,    str(len(result.services)))
        _set_kpi(self._kpi_types,   str(record_types))

        # AXFR records table
        self._rec_table.setRowCount(0)
        self._rec_table.setSortingEnabled(False)
        if result.records:
            self._rec_empty.hide()
            for rec in result.records:
                row = self._rec_table.rowCount()
                self._rec_table.insertRow(row)
                self._rec_table.setItem(row, 0, _cell(rec.name))
                type_item = _cell(rec.rtype, Qt.AlignmentFlag.AlignCenter)
                # Colour-code record types
                from PyQt6.QtGui import QColor
                if rec.rtype == "A":
                    type_item.setForeground(QColor(GREEN))
                elif rec.rtype in ("NS", "SOA"):
                    type_item.setForeground(QColor(ACCENT))
                elif rec.rtype == "MX":
                    type_item.setForeground(QColor(AMBER))
                self._rec_table.setItem(row, 1, type_item)
                self._rec_table.setItem(row, 2, _cell(rec.value))
                self._rec_table.setItem(row, 3, _cell(str(rec.ttl), Qt.AlignmentFlag.AlignRight))
            self._rec_table.setSortingEnabled(True)
            self._rec_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        else:
            self._rec_empty.show()

        # mDNS services table
        self._svc_table.setRowCount(0)
        self._svc_table.setSortingEnabled(False)
        if result.services:
            self._svc_empty.hide()
            for svc in result.services:
                row = self._svc_table.rowCount()
                self._svc_table.insertRow(row)
                self._svc_table.setItem(row, 0, _cell(svc.service_type))
                self._svc_table.setItem(row, 1, _cell(svc.instance))
                self._svc_table.setItem(row, 2, _cell(svc.host or "—"))
                self._svc_table.setItem(row, 3, _cell(svc.ip or "—"))
                port_text = str(svc.port) if svc.port else "—"
                self._svc_table.setItem(row, 4, _cell(port_text, Qt.AlignmentFlag.AlignCenter))
                self._svc_table.setItem(row, 5, _cell(svc.txt or "—"))
            self._svc_table.setSortingEnabled(True)
            self._svc_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        else:
            self._svc_empty.show()

        self._status_lbl.setText(result.verdict)
