"""
UptimePage — per-device uptime / SLA percentage view (T2#13).

Shows uptime % per monitored IP for the last 24h / 7d / 30d.
KPI tiles: fleet average, worst device, best device, total monitored.
Auto-refreshes every 5 minutes or when the availability worker emits
cycle_done.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.expanding_table import ExpandingTable

from modules.metric_store import MetricStore
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
    TABLE_SEL,
    TEXT_MUTED,
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

    scan_requested = pyqtSignal()

    _WINDOWS = [
        ("24h",  24.0),
        ("7d",   168.0),
        ("30d",  720.0),
    ]

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store = store
        self._rows: list = []
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

        title = QLabel("Uptime & SLA")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};")
        layout.addWidget(title)
        subtitle = QLabel(
            "Per-device availability percentages derived from background monitoring samples."
        )
        subtitle.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        layout.addWidget(subtitle)

        self._content_stack = QStackedWidget()

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addStretch()
        em_desc = QLabel(
            "No availability data yet.\n"
            "Start monitoring and NetSentinel will build per-device uptime percentages automatically."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Start Monitoring")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(180)
        em_btn.clicked.connect(self.scan_requested)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()
        self._content_stack.addWidget(empty)

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_devices = self._make_kpi("DEVICES MONITORED", "—", ACCENT)
        self._kpi_fleet   = self._make_kpi("FLEET AVG (24H)",   "—", GREEN)
        self._kpi_best    = self._make_kpi("BEST DEVICE (24H)", "—", GREEN)
        self._kpi_worst   = self._make_kpi("WORST DEVICE",      "—", AMBER)
        for w in (self._kpi_devices, self._kpi_fleet, self._kpi_best, self._kpi_worst):
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

        title_bar = QFrame()
        title_bar.setFixedHeight(32)
        title_bar.setStyleSheet(f"background: {BG_CARD}; border-bottom: 1px solid #ECECEC;")
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 10, 0)
        lbl = QLabel("Device Uptime Summary")
        lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY};")
        tb_layout.addWidget(lbl)
        tb_layout.addStretch()
        hint = QLabel("Green ≥99% · Amber ≥95% · Red <95%")
        hint.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        tb_layout.addWidget(hint)
        card_layout.addWidget(title_bar)

        self._table = ExpandingTable(
            0, 6,
            detail_builder=lambda r: self._build_uptime_detail(r),
            detail_height=100,
        )
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
        self._table.setEditTriggers(ExpandingTable.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(ExpandingTable.SelectionBehavior.SelectRows)
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
                background: {TABLE_SEL}; color: {TEXT_PRIMARY};
            }}
            """
        )
        self._table.setShowGrid(True)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
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
        self._rows = list(rows)
        if not rows:
            return
        self._content_stack.setCurrentIndex(1)
        self._table.setSortingEnabled(False)
        self._table.clear_detail()
        self._table.setRowCount(0)

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

    # ── Detail panel ──────────────────────────────────────────────────────────

    def _build_uptime_detail(self, logical_row: int) -> QWidget:
        if logical_row >= len(self._rows):
            return QWidget()
        r = self._rows[logical_row]

        pct_24  = r.get("24.0",  100.0)
        pct_7d  = r.get("168.0", 100.0)
        pct_30d = r.get("720.0", 100.0)
        worst   = min(pct_24, pct_7d, pct_30d)

        if worst < _CRIT:
            status_text  = "DEGRADED"
            status_color = RED
        elif worst < _WARN:
            status_text  = "WARNING"
            status_color = AMBER
        else:
            status_text  = "HEALTHY"
            status_color = GREEN

        outer = QWidget()
        outer.setStyleSheet(
            f"QWidget {{ background:{BG_HOVER}; border:none;"
            f" border-left:3px solid {status_color}; }}"
        )
        lay = QHBoxLayout(outer)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(32)

        def _hdr(t):
            l = QLabel(t)
            l.setStyleSheet(f"font-size:10px; font-weight:bold; color:{TEXT_MUTED}; background:transparent; border:none;")
            return l

        def _val(t, c=TEXT_PRIMARY):
            l = QLabel(str(t))
            l.setStyleSheet(f"font-size:11px; color:{c}; background:transparent; border:none;")
            return l

        col1 = QWidget()
        col1.setStyleSheet("QWidget { background:transparent; border:none; }")
        g1 = QFormLayout(col1)
        g1.setContentsMargins(0, 0, 0, 0)
        g1.setSpacing(3)
        g1.setHorizontalSpacing(12)
        g1.addRow(_hdr("IP Address"), _val(r["ip"]))
        g1.addRow(_hdr("Hostname"),   _val(r.get("hostname") or "—"))
        g1.addRow(_hdr("Status"),     _val(status_text, status_color))

        col2 = QWidget()
        col2.setStyleSheet("QWidget { background:transparent; border:none; }")
        g2 = QFormLayout(col2)
        g2.setContentsMargins(0, 0, 0, 0)
        g2.setSpacing(3)
        g2.setHorizontalSpacing(12)
        g2.addRow(_hdr("Uptime 24h"),  _val(f"{pct_24:.1f}%",  _uptime_color(pct_24)))
        g2.addRow(_hdr("Uptime 7d"),   _val(f"{pct_7d:.1f}%",  _uptime_color(pct_7d)))
        g2.addRow(_hdr("Uptime 30d"),  _val(f"{pct_30d:.1f}%", _uptime_color(pct_30d)))

        lay.addWidget(col1)
        lay.addWidget(col2)
        lay.addStretch()
        return outer

    # ── Table helpers ─────────────────────────────────────────────────────────

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
