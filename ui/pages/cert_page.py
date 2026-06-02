"""
CertPage — TLS certificate expiry monitor page (T2#6).

Shows the latest cert check result per host:port, with KPI tiles and
a sortable table.  Refreshes automatically every 5 minutes or when the
CertWorker emits check_done.
"""

from __future__ import annotations

import json
from typing import List, Optional

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.cert_monitor import CertTarget
from modules.metric_store import CertCheckPoint, MetricStore
from ui.widgets.context_menu import install_copy_menu
from PyQt6.QtWidgets import QMenu

from ui.styles import (
    ACCENT, AMBER, BG_ALT_ROW, BG_CARD,
    BG_HOVER, BORDER, CARD_HDR_BORDER, CARD_RADIUS,
    GREEN, RED, TABLE_ROW_BORDER, TABLE_SEL,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TH_BG,
    TH_TEXT,
)

_QS_KEY = "cert_monitor/targets"


class CertPage(QWidget):
    """Displays TLS certificate expiry status for all monitored hosts."""

    certs_changed   = pyqtSignal(list)   # list[CertTarget]
    scan_requested  = pyqtSignal()       # emitted when first host added from empty state

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store = store
        self._query_hours = 168.0
        self._configured: list[dict] = self._load_targets()
        self._setup_ui()
        if self._configured:
            self._content_stack.setCurrentIndex(1)
        self._refresh()
        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(300_000)   # auto-refresh every 5 minutes

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_targets(self) -> list[dict]:
        raw = QSettings("NetSentinel", "NetSentinel").value(_QS_KEY, "[]")
        try:
            return list(json.loads(raw))
        except Exception:
            return []

    def _save_targets(self) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(_QS_KEY, json.dumps(self._configured))

    def _emit_targets(self) -> None:
        targets = [CertTarget(host=t["host"], ports=t.get("ports", [443])) for t in self._configured]
        self.certs_changed.emit(targets)

    def _add_host(self, host: str, port: int) -> None:
        host = host.strip()
        if not host:
            return
        for t in self._configured:
            if t["host"] == host and port in t.get("ports", [443]):
                return
        self._configured.append({"host": host, "ports": [port]})
        self._save_targets()
        self._emit_targets()
        self._content_stack.setCurrentIndex(1)

    def _remove_host(self, host: str) -> None:
        self._configured = [t for t in self._configured if t["host"] != host]
        self._save_targets()
        self._emit_targets()
        if not self._configured:
            self._content_stack.setCurrentIndex(0)
        self._refresh()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("TLS Certificate Monitor")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        subtitle = QLabel("Latest TLS certificate status per host — checks run hourly.")
        subtitle.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        layout.addWidget(subtitle)

        self._content_stack = QStackedWidget()

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addStretch()

        em_desc = QLabel(
            "No hosts configured.\n"
            "Add a hostname below to start monitoring TLS certificate expiry."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(16)

        e0_host = QLineEdit()
        e0_host.setPlaceholderText("Hostname  (e.g. example.com)")
        e0_host.setFixedWidth(220)
        e0_host.setStyleSheet(f"font-size:11px; border:1px solid {BORDER}; padding:3px 6px;")
        e0_port = QSpinBox()
        e0_port.setRange(1, 65535)
        e0_port.setValue(443)
        e0_port.setFixedWidth(75)
        e0_port.setStyleSheet(f"font-size:11px; border:1px solid {BORDER}; padding:3px 4px;")
        e0_add = QPushButton("Add Host")
        e0_add.setObjectName("btnScan")
        e0_add.setFixedHeight(30)

        def _add_from_empty():
            self._add_host(e0_host.text(), e0_port.value())
            e0_host.clear()
            self.scan_requested.emit()

        e0_add.clicked.connect(_add_from_empty)
        e0_host.returnPressed.connect(_add_from_empty)

        form_row = QHBoxLayout()
        form_row.setSpacing(6)
        for w in (e0_host, e0_port, e0_add):
            form_row.addWidget(w)
        center = QHBoxLayout()
        center.addStretch()
        center.addLayout(form_row)
        center.addStretch()
        evl.addLayout(center)
        evl.addStretch()
        self._content_stack.addWidget(empty)

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_ok       = self._make_kpi("CERTS OK",      "—", GREEN)
        self._kpi_expiring = self._make_kpi("EXPIRING SOON", "—", AMBER)
        self._kpi_expired  = self._make_kpi("EXPIRED",       "—", RED)
        self._kpi_error    = self._make_kpi("UNREACHABLE",   "—", TEXT_SECONDARY)
        for w in (self._kpi_ok, self._kpi_expiring, self._kpi_expired, self._kpi_error):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        cl.addLayout(kpi_row)

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: {CARD_RADIUS}; }}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Title bar with inline add form
        title_bar = QFrame()
        title_bar.setStyleSheet(f"background: {BG_CARD}; border-bottom: 1px solid {CARD_HDR_BORDER};")
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 6, 10, 6)
        tb_layout.setSpacing(6)

        bar_lbl = QLabel("Certificate Status")
        bar_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY};")
        tb_layout.addWidget(bar_lbl)
        tb_layout.addStretch()

        self._txt_host = QLineEdit()
        self._txt_host.setPlaceholderText("Hostname")
        self._txt_host.setFixedWidth(180)
        self._txt_host.setFixedHeight(24)
        self._txt_host.setStyleSheet(f"font-size:11px; border:1px solid {BORDER}; padding:2px 5px;")
        self._spin_port = QSpinBox()
        self._spin_port.setRange(1, 65535)
        self._spin_port.setValue(443)
        self._spin_port.setFixedWidth(70)
        self._spin_port.setFixedHeight(24)
        self._spin_port.setStyleSheet(f"font-size:11px; border:1px solid {BORDER}; padding:2px 3px;")
        btn_add = QPushButton("+ Add")
        btn_add.setFixedHeight(24)
        btn_add.setStyleSheet(
            f"font-size:11px; color:{ACCENT}; border:1px solid {ACCENT};"
            f" background:transparent; padding:0 10px;"
        )

        def _add_from_bar():
            self._add_host(self._txt_host.text(), self._spin_port.value())
            self._txt_host.clear()

        btn_add.clicked.connect(_add_from_bar)
        self._txt_host.returnPressed.connect(_add_from_bar)

        for w in (self._txt_host, self._spin_port, btn_add):
            tb_layout.addWidget(w)

        card_layout.addWidget(title_bar)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["HOST", "PORT", "STATUS", "DAYS LEFT", "EXPIRES", "SUBJECT", "ISSUER"]
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            f"""
            QTableWidget {{
                border: none; gridline-color: TABLE_ROW_BORDER;
                font-size: 11px; color: {TEXT_PRIMARY};
                alternate-background-color: {BG_ALT_ROW};
            }}
            QHeaderView::section {{
                background-color: {TH_BG}; color: {TH_TEXT};
                font-size: 11px; font-weight: bold;
                padding: 4px 5px; border: none;
            }}
            QTableWidget::item {{ padding: 4px 5px; }}
            QTableWidget::item:hover {{ background: {BG_HOVER}; }}
            QTableWidget::item:selected {{
                background: {TABLE_SEL}; color: {TEXT_PRIMARY};
            }}
            """
        )
        self._table.setShowGrid(True)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_cert_context_menu)
        install_copy_menu(self._table)
        card_layout.addWidget(self._table)
        cl.addWidget(card, stretch=1)
        self._content_stack.addWidget(content)

        layout.addWidget(self._content_stack, stretch=1)

    # ── KPI helpers ───────────────────────────────────────────────────────────

    def _make_kpi(self, label: str, value: str, accent: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; "
            f"border-left: 3px solid {accent}; }}"
        )
        frame.setMinimumWidth(100)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size: 9px; font-weight: bold; color: {TEXT_SECONDARY};")
        val = QLabel(value)
        val.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {TEXT_PRIMARY};")
        val.setObjectName(f"kpi_val_{label}")
        lay.addWidget(lbl)
        lay.addWidget(val)
        return frame

    def _set_kpi(self, frame: QFrame, label: str, value) -> None:
        w = frame.findChild(QLabel, f"kpi_val_{label}")
        if w:
            w.setText(str(value))

    # ── Data refresh ──────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        if not self._store:
            return
        rows = self._store.query_cert_status(hours=self._query_hours)
        self._populate(rows)

    def set_global_hours(self, hours: float) -> None:
        self._query_hours = hours
        self._refresh()

    def on_check_done(self, results: list) -> None:
        """Slot — connected to CertWorker.check_done."""
        self._refresh()

    # ── Table population ──────────────────────────────────────────────────────

    def _populate(self, rows: List[CertCheckPoint]) -> None:
        self._table.setRowCount(0)
        ok = expiring = expired = errored = 0

        for r in rows:
            row_idx = self._table.rowCount()
            self._table.insertRow(row_idx)

            if r.error:
                status_text  = "UNREACHABLE"
                status_color = TEXT_SECONDARY
                errored += 1
            elif r.is_expired:
                status_text  = "EXPIRED"
                status_color = RED
                expired += 1
            elif r.days_remaining is not None and r.days_remaining < 30:
                status_text  = "EXPIRING"
                status_color = AMBER
                expiring += 1
            else:
                status_text  = "OK"
                status_color = GREEN
                ok += 1

            days_str    = str(r.days_remaining) if r.days_remaining is not None else "—"
            expires_str = r.not_after or "—"

            # ACT-8: check snooze state for expiring/expired certs
            import time as _t
            snoozed = False
            snooze_chip = ""
            if status_text in ("EXPIRING", "EXPIRED"):
                snooze_key = f"cert/snooze/{r.host}:{r.port}"
                snooze_until = float(
                    QSettings("NetSentinel", "NetSentinel").value(snooze_key, 0) or 0
                )
                if snooze_until > _t.time():
                    snoozed = True
                    snooze_chip = "  z"
                else:
                    QSettings("NetSentinel", "NetSentinel").remove(snooze_key)

            effective_color = TEXT_MUTED if snoozed else status_color

            self._table.setItem(row_idx, 0, self._cell(r.host))
            self._table.setItem(row_idx, 1, self._cell(str(r.port)))

            dot = QLabel(f"  {status_text}{snooze_chip}")
            dot.setStyleSheet(
                f"color: {effective_color}; font-size: 11px; font-weight: bold; padding-left: 4px;"
            )
            dot.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setCellWidget(row_idx, 2, dot)

            days_item = self._cell(days_str)
            if not snoozed:
                if r.is_expired:
                    days_item.setForeground(QColor(RED))
                elif r.days_remaining is not None and r.days_remaining < 30:
                    days_item.setForeground(QColor(AMBER))
            else:
                days_item.setForeground(QColor(TEXT_MUTED))
            self._table.setItem(row_idx, 3, days_item)
            self._table.setItem(row_idx, 4, self._cell(expires_str))
            self._table.setItem(row_idx, 5, self._cell(r.subject or "—"))
            self._table.setItem(row_idx, 6, self._cell(r.issuer or "—"))

        if not rows and self._configured:
            self._table.setRowCount(1)
            placeholder = QTableWidgetItem("Waiting for first check cycle…")
            placeholder.setForeground(QColor(TEXT_SECONDARY))
            placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(0, 0, placeholder)
            self._table.setSpan(0, 0, 1, 7)

        self._set_kpi(self._kpi_ok,       "CERTS OK",      ok)
        self._set_kpi(self._kpi_expiring, "EXPIRING SOON", expiring)
        self._set_kpi(self._kpi_expired,  "EXPIRED",       expired)
        self._set_kpi(self._kpi_error,    "UNREACHABLE",   errored)

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ── ACT-8: snooze reminder ────────────────────────────────────────────────

    def _on_cert_context_menu(self, pos) -> None:
        import time as _t
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        host_item = self._table.item(row, 0)
        port_item = self._table.item(row, 1)
        if host_item is None or port_item is None:
            return
        host = host_item.text().strip()
        port = port_item.text().strip()
        if not host:
            return

        snooze_key = f"cert/snooze/{host}:{port}"
        snooze_until = float(
            QSettings("NetSentinel", "NetSentinel").value(snooze_key, 0) or 0
        )
        is_snoozed = snooze_until > _t.time()

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; font-size:11px;"
            f" border:1px solid {BORDER}; }}"
            f"QMenu::item:selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )

        snooze_menu = menu.addMenu("Snooze reminder")
        snooze_menu.setStyleSheet(menu.styleSheet())
        act_7d = snooze_menu.addAction("Snooze 7 days")
        act_30d = snooze_menu.addAction("Snooze 30 days")
        act_7d.triggered.connect(lambda: self._snooze_cert(host, port, days=7))
        act_30d.triggered.connect(lambda: self._snooze_cert(host, port, days=30))

        if is_snoozed:
            act_clear = menu.addAction("Clear snooze")
            act_clear.triggered.connect(lambda: self._clear_cert_snooze(host, port))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _snooze_cert(self, host: str, port: str, days: int) -> None:
        import time as _t
        expiry = _t.time() + days * 86400
        QSettings("NetSentinel", "NetSentinel").setValue(
            f"cert/snooze/{host}:{port}", expiry
        )
        self._refresh()

    def _clear_cert_snooze(self, host: str, port: str) -> None:
        QSettings("NetSentinel", "NetSentinel").remove(f"cert/snooze/{host}:{port}")
        self._refresh()
