"""
CertPage — TLS certificate expiry monitor page (T2#6).

Shows the latest cert check result per host:port, with KPI tiles and
a sortable table.  Refreshes automatically every 5 minutes or when the
CertWorker emits check_done.
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.metric_store import CertCheckPoint, MetricStore
from ui.styles import (
    ACCENT,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_HOVER,
    BORDER,
    CARD_RADIUS,
    GREEN,
    RED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_TEXT,
)


class CertPage(QWidget):
    """Displays TLS certificate expiry status for all monitored hosts."""

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store = store
        self._setup_ui()
        self._refresh()
        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(300_000)   # auto-refresh every 5 minutes

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Page title
        title = QLabel("TLS Certificate Monitor")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        layout.addWidget(title)

        subtitle = QLabel("Latest TLS certificate status per host — checks run hourly.")
        subtitle.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        layout.addWidget(subtitle)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_ok       = self._make_kpi("CERTS OK",      "—", GREEN)
        self._kpi_expiring = self._make_kpi("EXPIRING SOON", "—", AMBER)
        self._kpi_expired  = self._make_kpi("EXPIRED",       "—", RED)
        self._kpi_error    = self._make_kpi("UNREACHABLE",   "—", TEXT_SECONDARY)
        for w in (self._kpi_ok, self._kpi_expiring, self._kpi_expired, self._kpi_error):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        layout.addLayout(kpi_row)

        # Card
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: {CARD_RADIUS}; }}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Card title bar
        title_bar = QFrame()
        title_bar.setFixedHeight(32)
        title_bar.setStyleSheet(
            f"background: {BG_CARD}; border-bottom: 1px solid #ECECEC;"
        )
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 10, 0)
        lbl = QLabel("Certificate Status")
        lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        tb_layout.addWidget(lbl)
        tb_layout.addStretch()
        card_layout.addWidget(title_bar)

        # Table
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
                border: none; gridline-color: #EAEAEA;
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
                background: #CCE4F7; color: {TEXT_PRIMARY};
            }}
            """
        )
        self._table.setShowGrid(True)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
        card_layout.addWidget(self._table)

        layout.addWidget(card, stretch=1)

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
        lbl.setStyleSheet(
            f"font-size: 9px; font-weight: bold; color: {TEXT_SECONDARY};"
        )
        val = QLabel(value)
        val.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
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
        rows = self._store.query_cert_status(hours=168.0)
        self._populate(rows)

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

            # Classify
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

            # Col 0: host
            self._table.setItem(row_idx, 0, self._cell(r.host))
            # Col 1: port
            self._table.setItem(row_idx, 1, self._cell(str(r.port)))
            # Col 2: status dot widget
            dot = QLabel(f"  {status_text}")
            dot.setStyleSheet(
                f"color: {status_color}; font-size: 11px; "
                f"font-weight: bold; padding-left: 4px;"
            )
            dot.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setCellWidget(row_idx, 2, dot)
            # Col 3: days left (coloured)
            days_item = self._cell(days_str)
            if r.is_expired:
                days_item.setForeground(QColor(RED))
            elif r.days_remaining is not None and r.days_remaining < 30:
                days_item.setForeground(QColor(AMBER))
            self._table.setItem(row_idx, 3, days_item)
            # Col 4: expires
            self._table.setItem(row_idx, 4, self._cell(expires_str))
            # Col 5: subject
            self._table.setItem(row_idx, 5, self._cell(r.subject or "—"))
            # Col 6: issuer
            self._table.setItem(row_idx, 6, self._cell(r.issuer or "—"))

        # Empty state
        if not rows:
            self._table.setRowCount(1)
            placeholder = QTableWidgetItem(
                "No certificate data yet — add HTTPS hosts to monitoring targets"
            )
            placeholder.setForeground(QColor(TEXT_SECONDARY))
            placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(0, 0, placeholder)
            self._table.setSpan(0, 0, 1, 7)

        # Update KPIs
        self._set_kpi(self._kpi_ok,       "CERTS OK",      ok)
        self._set_kpi(self._kpi_expiring, "EXPIRING SOON", expiring)
        self._set_kpi(self._kpi_expired,  "EXPIRED",       expired)
        self._set_kpi(self._kpi_error,    "UNREACHABLE",   errored)

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item
