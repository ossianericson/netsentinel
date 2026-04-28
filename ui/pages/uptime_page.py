"""
UptimePage — per-device uptime / SLA percentage view (T2#13).

Shows uptime % per monitored IP for the last 24h / 7d / 30d.
KPI tiles: fleet average, worst device, best device, total monitored.
Auto-refreshes every 5 minutes or when the availability worker emits
cycle_done.
"""

from __future__ import annotations

from typing import Optional

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

from modules.metric_store import MetricStore
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

# Uptime % thresholds for colouring
_CRIT  = 95.0   # < 95% → red
_WARN  = 99.0   # < 99% → amber
# ≥ 99% → green


def _uptime_color(pct: float) -> str:
    if pct < _CRIT:
        return RED
    if pct < _WARN:
        return AMBER
    return GREEN


class UptimePage(QWidget):
    """Displays per-device uptime percentages for 24h / 7d / 30d windows."""

    _WINDOWS = [
        ("24h",  24.0),
        ("7d",   168.0),
        ("30d",  720.0),
    ]

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
        title = QLabel("Uptime & SLA")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Per-device availability percentages derived from background monitoring samples."
        )
        subtitle.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        layout.addWidget(subtitle)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_devices   = self._make_kpi("DEVICES MONITORED", "—", ACCENT)
        self._kpi_fleet     = self._make_kpi("FLEET AVG (24H)",   "—", GREEN)
        self._kpi_best      = self._make_kpi("BEST DEVICE (24H)", "—", GREEN)
        self._kpi_worst     = self._make_kpi("WORST DEVICE",      "—", AMBER)
        for w in (self._kpi_devices, self._kpi_fleet, self._kpi_best, self._kpi_worst):
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
        lbl = QLabel("Device Uptime Summary")
        lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        tb_layout.addWidget(lbl)
        tb_layout.addStretch()
        hint = QLabel("Green ≥99% · Amber ≥95% · Red <95%")
        hint.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        tb_layout.addWidget(hint)
        card_layout.addWidget(title_bar)

        # Table — IP / Hostname / 24h / 7d / 30d / Trend
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["IP ADDRESS", "HOSTNAME", "UPTIME 24H", "UPTIME 7D", "UPTIME 30D", "STATUS"]
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
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
        frame.setMinimumWidth(110)
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
        rows = self._store.query_uptime_table()
        self._populate(rows)

    def on_cycle_done(self, _result: dict) -> None:
        """Slot — connected to AvailabilityWorker.cycle_done."""
        self._refresh()

    # ── Table population ──────────────────────────────────────────────────────

    def _populate(self, rows: list) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        if not rows:
            self._table.setRowCount(1)
            placeholder = QTableWidgetItem(
                "No uptime data yet — background monitoring builds this table automatically"
            )
            placeholder.setForeground(QColor(TEXT_SECONDARY))
            placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(0, 0, placeholder)
            self._table.setSpan(0, 0, 1, 6)
            for kpi, lbl, val in [
                (self._kpi_devices, "DEVICES MONITORED", "0"),
                (self._kpi_fleet,   "FLEET AVG (24H)",   "—"),
                (self._kpi_best,    "BEST DEVICE (24H)", "—"),
                (self._kpi_worst,   "WORST DEVICE",      "—"),
            ]:
                self._set_kpi(kpi, lbl, val)
            return

        pct_24h_list = [r.get("24.0", 100.0) for r in rows]
        fleet_avg   = round(sum(pct_24h_list) / len(pct_24h_list), 1)
        best_pct    = max(pct_24h_list)
        worst_pct   = min(pct_24h_list)
        worst_ip    = rows[pct_24h_list.index(worst_pct)]["ip"]

        for r in rows:
            row_idx = self._table.rowCount()
            self._table.insertRow(row_idx)

            pct_24  = r.get("24.0", 100.0)
            pct_7d  = r.get("168.0", 100.0)
            pct_30d = r.get("720.0", 100.0)

            # Worst window drives the row status
            worst_window = min(pct_24, pct_7d, pct_30d)

            self._table.setItem(row_idx, 0, self._cell(r["ip"]))
            self._table.setItem(row_idx, 1, self._cell(r.get("hostname") or "—"))
            self._table.setItem(row_idx, 2, self._pct_cell(pct_24))
            self._table.setItem(row_idx, 3, self._pct_cell(pct_7d))
            self._table.setItem(row_idx, 4, self._pct_cell(pct_30d))

            # Status dot
            if worst_window < _CRIT:
                status_text  = "  DEGRADED"
                status_color = RED
            elif worst_window < _WARN:
                status_text  = "  WARNING"
                status_color = AMBER
            else:
                status_text  = "  HEALTHY"
                status_color = GREEN

            dot = QLabel(status_text)
            dot.setStyleSheet(
                f"color: {status_color}; font-size: 11px; "
                f"font-weight: bold; padding-left: 4px;"
            )
            dot.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setCellWidget(row_idx, 5, dot)

        # Update KPIs
        self._set_kpi(self._kpi_devices, "DEVICES MONITORED", str(len(rows)))
        self._set_kpi(self._kpi_fleet,   "FLEET AVG (24H)",   f"{fleet_avg}%")
        self._set_kpi(self._kpi_best,    "BEST DEVICE (24H)", f"{best_pct}%")
        self._set_kpi(self._kpi_worst,   "WORST DEVICE",
                      f"{worst_pct}% ({worst_ip})")

        self._table.setSortingEnabled(True)

    def _pct_cell(self, pct: float) -> QTableWidgetItem:
        item = QTableWidgetItem(f"{pct:.1f}%")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setForeground(QColor(_uptime_color(pct)))
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        # Store numeric value for sort
        item.setData(Qt.ItemDataRole.UserRole, pct)
        return item

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item
