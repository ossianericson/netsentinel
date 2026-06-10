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
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.expanding_table import ExpandingTable
from ui.widgets.context_menu import install_copy_menu
from ui.widgets.empty_state_card import EmptyStateCard

from modules.metric_store import MetricStore
from ui.styles import (
    ACCENT, AMBER, BG_ALT_ROW, BG_CARD,
    BG_HOVER, BORDER, CARD_HDR_BORDER, CARD_RADIUS,
    GREEN, RED, TABLE_SEL,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TH_BG,
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
        empty = EmptyStateCard(
            icon="▲",
            title="Device Uptime Monitor",
            what_it_shows=(
                "Uptime percentage for every device on your network over the last 24 hours, "
                "7 days, and 30 days — updated automatically by the background availability monitor."
            ),
            why_it_matters=(
                "Chronic 99.9% uptime sounds good until you realise it means 8 hours of downtime "
                "per year — catch intermittent devices before they become critical failures."
            ),
            btn_label="Start Monitoring",
        )
        empty.clicked.connect(self.scan_requested)
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
        title_bar.setStyleSheet(f"background: {BG_CARD}; border-bottom: 1px solid {CARD_HDR_BORDER};")
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
        self._table.verticalHeader().setDefaultSectionSize(24)

        def _upt_copy_host():
            r = self._table.currentRow()
            if r >= 0:
                it = self._table.item(r, 1) or self._table.item(r, 0)
                if it:
                    from PyQt6.QtWidgets import QApplication as _QApp
                    _QApp.clipboard().setText(it.text())

        def _upt_export_row():
            r = self._table.currentRow()
            if r < 0:
                return
            headers = [self._table.horizontalHeaderItem(c).text()
                       for c in range(self._table.columnCount())]
            values  = [(self._table.item(r, c).text() if self._table.item(r, c) else "")
                       for c in range(self._table.columnCount())]
            from PyQt6.QtWidgets import QApplication as _QApp
            _QApp.clipboard().setText(",".join(headers) + "\n" + ",".join(values))

        install_copy_menu(self._table, [
            ("separator",  None),
            ("Copy host",  _upt_copy_host),
            ("separator",  None),
            ("Export row", _upt_export_row),
        ])

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

        pct_24h_list = [r.get("24.0") for r in rows]
        known_24h   = [p for p in pct_24h_list if p is not None]
        fleet_avg   = round(sum(known_24h) / len(known_24h), 1) if known_24h else None
        best_pct    = max(known_24h) if known_24h else None
        worst_pct   = min(known_24h) if known_24h else None
        worst_ip    = rows[pct_24h_list.index(worst_pct)]["ip"] if worst_pct is not None else "—"

        for r in rows:
            row_idx = self._table.rowCount()
            self._table.insertRow(row_idx)

            pct_24  = r.get("24.0")
            pct_7d  = r.get("168.0")
            pct_30d = r.get("720.0")

            # Worst window drives the row status (exclude None — no data yet)
            known_windows = [p for p in (pct_24, pct_7d, pct_30d) if p is not None]
            worst_window = min(known_windows) if known_windows else None

            self._table.setItem(row_idx, 0, self._cell(r["ip"]))
            self._table.setItem(row_idx, 1, self._cell(r.get("hostname") or "—"))
            self._table.setItem(row_idx, 2, self._pct_cell(pct_24))
            self._table.setItem(row_idx, 3, self._pct_cell(pct_7d))
            self._table.setItem(row_idx, 4, self._pct_cell(pct_30d))

            # Status dot
            if worst_window is None:
                status_text  = "  NO DATA"
                status_color = TEXT_SECONDARY
            elif worst_window < _CRIT:
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
        self._set_kpi(self._kpi_fleet,   "FLEET AVG (24H)",
                      f"{fleet_avg}%" if fleet_avg is not None else "—")
        self._set_kpi(self._kpi_best,    "BEST DEVICE (24H)",
                      f"{best_pct}%" if best_pct is not None else "—")
        self._set_kpi(self._kpi_worst,   "WORST DEVICE",
                      f"{worst_pct}% ({worst_ip})" if worst_pct is not None else "—")

        self._table.setSortingEnabled(True)

    # ── Detail panel ──────────────────────────────────────────────────────────

    def _build_uptime_detail(self, logical_row: int) -> QWidget:
        if logical_row >= len(self._rows):
            return QWidget()
        r = self._rows[logical_row]

        pct_24  = r.get("24.0")
        pct_7d  = r.get("168.0")
        pct_30d = r.get("720.0")
        known   = [p for p in (pct_24, pct_7d, pct_30d) if p is not None]
        worst   = min(known) if known else None

        if worst is None:
            status_text  = "NO DATA"
            status_color = TEXT_SECONDARY
        elif worst < _CRIT:
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
        def _pct_str(p): return f"{p:.1f}%" if p is not None else "—"
        def _pct_col(p): return _uptime_color(p) if p is not None else TEXT_SECONDARY
        g2.addRow(_hdr("Uptime 24h"),  _val(_pct_str(pct_24),  _pct_col(pct_24)))
        g2.addRow(_hdr("Uptime 7d"),   _val(_pct_str(pct_7d),  _pct_col(pct_7d)))
        g2.addRow(_hdr("Uptime 30d"),  _val(_pct_str(pct_30d), _pct_col(pct_30d)))

        lay.addWidget(col1)
        lay.addWidget(col2)
        lay.addStretch()
        return outer

    # ── Table helpers ─────────────────────────────────────────────────────────

    def _pct_cell(self, pct) -> QTableWidgetItem:
        if pct is None:
            item = QTableWidgetItem("—")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            item.setData(Qt.ItemDataRole.UserRole, -1.0)
            return item
        item = QTableWidgetItem(f"{pct:.1f}%")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setForeground(QColor(_uptime_color(pct)))
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        item.setData(Qt.ItemDataRole.UserRole, pct)
        return item

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ── Public navigation slot ────────────────────────────────────────────────

    def focus_on_host(self, ip: str, mac: str = "") -> None:
        """Public slot — scroll to and select the uptime row for this host."""
        if not ip or ip in ("—", ""):
            return
        for row in range(self._table.rowCount()):
            ip_it = self._table.item(row, 0)
            if ip_it and ip_it.text() == ip:
                self._table.setCurrentCell(row, 0)
                self._table.scrollToItem(ip_it)
                break
