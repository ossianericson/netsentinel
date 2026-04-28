"""
ServicePage — TCP service/port heartbeat monitor page (T2#7).

Displays the latest check result per service (host:port), with KPI tiles
and a sortable table. Refreshes automatically every minute or when
ServiceWorker emits check_done.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
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

from modules.metric_store import MetricStore, ServiceCheckPoint
from ui.styles import (
    ACCENT,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_HOVER,
    BORDER,
    GREEN,
    RED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_TEXT,
)


def _ts_label(ts: int) -> str:
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return dt.strftime("%H:%M:%S")
    except Exception:
        return "—"


class ServicePage(QWidget):
    """Displays TCP service/port heartbeat status for all monitored services."""

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store = store
        self._setup_ui()
        self._refresh()
        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(60_000)   # auto-refresh every minute

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Service Heartbeat Monitor")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "TCP port reachability checks — configured services are probed every minute."
        )
        subtitle.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        layout.addWidget(subtitle)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_up    = self._make_kpi("SERVICES UP",    "—", GREEN)
        self._kpi_down  = self._make_kpi("SERVICES DOWN",  "—", RED)
        self._kpi_total = self._make_kpi("TOTAL SERVICES", "—", ACCENT)
        self._kpi_avg   = self._make_kpi("AVG RTT (UP)",   "—", ACCENT)
        for w in (self._kpi_up, self._kpi_down, self._kpi_total, self._kpi_avg):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        layout.addLayout(kpi_row)

        # Card
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 0px; }}"
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
        lbl = QLabel("Service Status")
        lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        tb_layout.addWidget(lbl)
        tb_layout.addStretch()
        card_layout.addWidget(title_bar)

        # Table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["SERVICE", "HOST", "PORT", "STATUS", "RTT (ms)", "LAST CHECK"]
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
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
        rows = self._store.query_service_status(hours=24.0)
        self._populate(rows)

    def on_check_done(self, results: list) -> None:
        """Slot — connected to ServiceWorker.check_done."""
        self._refresh()

    # ── Table population ──────────────────────────────────────────────────────

    def _populate(self, rows: List[ServiceCheckPoint]) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        if not rows:
            self._table.setRowCount(1)
            placeholder = QTableWidgetItem(
                "No service data yet — add targets via Settings or configure ServiceWorker targets"
            )
            placeholder.setForeground(QColor(TEXT_SECONDARY))
            placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(0, 0, placeholder)
            self._table.setSpan(0, 0, 1, 6)
            for kpi, lbl, v in [
                (self._kpi_up,    "SERVICES UP",    "0"),
                (self._kpi_down,  "SERVICES DOWN",  "0"),
                (self._kpi_total, "TOTAL SERVICES", "0"),
                (self._kpi_avg,   "AVG RTT (UP)",   "—"),
            ]:
                self._set_kpi(kpi, lbl, v)
            return

        up_count = down_count = 0
        rtts = []

        for r in rows:
            row_idx = self._table.rowCount()
            self._table.insertRow(row_idx)

            if r.up:
                status_text  = "  UP"
                status_color = GREEN
                up_count += 1
                if r.rtt_ms is not None:
                    rtts.append(r.rtt_ms)
            else:
                status_text  = "  DOWN"
                status_color = RED
                down_count += 1

            rtt_str = f"{r.rtt_ms:.1f}" if r.rtt_ms is not None else "—"

            self._table.setItem(row_idx, 0, self._cell(r.label or f"{r.host}:{r.port}"))
            self._table.setItem(row_idx, 1, self._cell(r.host))
            self._table.setItem(row_idx, 2, self._cell(str(r.port)))

            dot = QLabel(status_text)
            dot.setStyleSheet(
                f"color: {status_color}; font-size: 11px; "
                f"font-weight: bold; padding-left: 4px;"
            )
            dot.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setCellWidget(row_idx, 3, dot)

            rtt_item = QTableWidgetItem(rtt_str)
            rtt_item.setFlags(rtt_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            rtt_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if r.rtt_ms is not None:
                rtt_item.setData(Qt.ItemDataRole.UserRole, r.rtt_ms)
            self._table.setItem(row_idx, 4, rtt_item)

            self._table.setItem(row_idx, 5, self._cell(_ts_label(r.ts)))

        avg_rtt = f"{sum(rtts)/len(rtts):.1f} ms" if rtts else "—"
        self._set_kpi(self._kpi_up,    "SERVICES UP",    str(up_count))
        self._set_kpi(self._kpi_down,  "SERVICES DOWN",  str(down_count))
        self._set_kpi(self._kpi_total, "TOTAL SERVICES", str(len(rows)))
        self._set_kpi(self._kpi_avg,   "AVG RTT (UP)",   avg_rtt)

        self._table.setSortingEnabled(True)

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item
