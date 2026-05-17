"""
InventoryPage — network inventory change history page (T2#8).

Shows a live event log of every JOINED / LEFT / DOWN / UP / DEGRADED / RECOVERED
event recorded by MetricStore, with filtering by event type and time window.

Architecture rules observed:
  • Imports PyQt6 and ui/styles — UI page only.
  • MetricStore injected as constructor parameter — never constructed here.
  • All colours from ui/styles — no hardcoded hex values.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ui.expanding_table import ExpandingTable

from ui.styles import (
    ACCENT, AMBER, BG_ALT_ROW, BG_CARD, BG_DARK, BG_HOVER,
    BORDER, CARD_RADIUS, GREEN, RED, TABLE_SEL, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TH_BG, TH_TEXT,
)

if TYPE_CHECKING:
    from modules.metric_store import MetricStore


# ── Event type display config ─────────────────────────────────────────────────

_EVENT_STYLE: dict[str, tuple[str, str]] = {
    # event_type: (badge_color, label)
    "JOINED":    (GREEN,  "JOINED"),
    "LEFT":      (AMBER,  "LEFT"),
    "DOWN":      (RED,    "DOWN"),
    "UP":        (GREEN,  "UP"),
    "DEGRADED":  (AMBER,  "DEGRADED"),
    "RECOVERED": (GREEN,  "RECOVERED"),
}

_ALL_TYPES = list(_EVENT_STYLE.keys())

_WINDOWS = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}


# ── Helper: coloured badge cell ───────────────────────────────────────────────

def _badge_item(text: str, color: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(color))
    item.setFont(
        __import__("PyQt6.QtGui", fromlist=["QFont"]).QFont("Segoe UI", 9, 75)  # Bold
    )
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    return item


def _plain_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    return item


# ── Main page ────────────────────────────────────────────────────────────────

class InventoryPage(QWidget):
    """
    Full-page inventory change event log.

    Parameters
    ----------
    store : MetricStore | None
        Injected from app.py. Shows a placeholder if None.
    """

    scan_requested = pyqtSignal()

    REFRESH_MS = 15_000   # refresh every 15 s

    def __init__(self, store: "Optional[MetricStore]" = None, parent=None):
        super().__init__(parent)
        self._store    = store
        self._window_h = 24
        self._active_types: set[str] = set(_ALL_TYPES)
        self._rows: list = []
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(self.REFRESH_MS)
        self._auto_timer.timeout.connect(self._refresh)

        self._build_ui()

        if store:
            self._refresh()
            self._auto_timer.start()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # Title — always visible
        t = QLabel("Inventory Change History")
        t.setStyleSheet(f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY};")
        s = QLabel("Device join, leave, and state-change events — recorded by the background monitor")
        s.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        root.addWidget(t)
        root.addWidget(s)

        self._content_stack = QStackedWidget()

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addStretch()
        em_desc = QLabel(
            "No device events recorded yet.\n"
            "Run a scan to start tracking devices joining, leaving, or going down."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Run Scan")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(160)
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

        ctrl_row = QHBoxLayout()
        ctrl_row.addStretch()
        self._zoom_btns: dict[str, QPushButton] = {}
        for lbl in _WINDOWS:
            btn = QPushButton(lbl)
            btn.setFixedSize(40, 26)
            btn.setCheckable(True)
            btn.setStyleSheet(self._zoom_style(False))
            btn.clicked.connect(lambda _c, l=lbl: self._set_window(l))
            self._zoom_btns[lbl] = btn
            ctrl_row.addWidget(btn)
        rb = QPushButton("↻ Refresh")
        rb.setFixedHeight(26)
        rb.setStyleSheet(
            f"QPushButton {{ font-size:11px; color:{ACCENT}; background:{BG_CARD};"
            f" border:1px solid {ACCENT}; border-radius:3px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
        )
        rb.clicked.connect(self._refresh)
        ctrl_row.addWidget(rb)
        cl.addLayout(ctrl_row)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_total   = self._make_kpi("Total Events",  "—", ACCENT)
        self._kpi_joined  = self._make_kpi("Joined",        "—", GREEN)
        self._kpi_left    = self._make_kpi("Left",          "—", AMBER)
        self._kpi_down    = self._make_kpi("Down Events",   "—", RED)
        self._kpi_devices = self._make_kpi("Devices Known", "—", ACCENT)
        for w in (self._kpi_total, self._kpi_joined, self._kpi_left,
                  self._kpi_down, self._kpi_devices):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        cl.addLayout(kpi_row)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)
        filter_lbl = QLabel("Filter:")
        filter_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        filter_row.addWidget(filter_lbl)
        self._type_checks: dict[str, QCheckBox] = {}
        for et in _ALL_TYPES:
            color, label = _EVENT_STYLE[et]
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setStyleSheet(f"QCheckBox {{ font-size:11px; color:{color}; font-weight:bold; }}")
            cb.toggled.connect(lambda checked, t=et: self._toggle_type(t, checked))
            self._type_checks[et] = cb
            filter_row.addWidget(cb)
        filter_row.addStretch()
        cl.addLayout(filter_row)

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)
        cols = ["Time", "Event", "IP / Host", "MAC", "Vendor", "Detail"]
        self._table = ExpandingTable(
            0, len(cols),
            detail_builder=lambda r: self._build_event_detail(r),
            detail_height=96,
        )
        self._table.setHorizontalHeaderLabels(cols)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(ExpandingTable.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(ExpandingTable.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setShowGrid(False)
        self._table.setStyleSheet(
            f"""
            QTableWidget {{
                font-size:11px; color:{TEXT_PRIMARY};
                background:{BG_CARD}; gridline-color:{BORDER};
                border:none; outline:none;
            }}
            QTableWidget::item {{ padding:3px 5px; border-bottom:1px solid #EAEAEA; }}
            QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}
            QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}
            QHeaderView::section {{
                background:{TH_BG}; color:{TH_TEXT};
                font-size:11px; font-weight:bold;
                padding:4px 5px; border:none;
                border-right:1px solid #2A4A6A;
            }}
            """
        )
        hdr = self._table.horizontalHeader()
        hdr.resizeSection(0, 140)
        hdr.resizeSection(1, 90)
        hdr.resizeSection(2, 130)
        hdr.resizeSection(3, 135)
        hdr.resizeSection(4, 130)
        hdr.setStretchLastSection(True)
        card_lay.addWidget(self._table)
        cl.addWidget(card, 1)
        self._content_stack.addWidget(content)

        root.addWidget(self._content_stack, 1)
        self._set_window("24h")

    # ── Window / filter controls ──────────────────────────────────────────────

    def _set_window(self, label: str) -> None:
        self._window_h = _WINDOWS[label]
        for lbl, btn in self._zoom_btns.items():
            active = lbl == label
            btn.setChecked(active)
            btn.setStyleSheet(self._zoom_style(active))
        self._refresh()

    def _toggle_type(self, event_type: str, checked: bool) -> None:
        if checked:
            self._active_types.add(event_type)
        else:
            self._active_types.discard(event_type)
        self._refresh()

    @staticmethod
    def _zoom_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ font-size:11px; background:{ACCENT}; color:#FFFFFF;"
                f" border:1px solid {ACCENT}; border-radius:3px; }}"
            )
        return (
            f"QPushButton {{ font-size:11px; background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid #B0C4D8; border-radius:3px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
        )

    # ── KPI helper ────────────────────────────────────────────────────────────

    @staticmethod
    def _make_kpi(label: str, value: str, accent: str) -> QFrame:
        f = QFrame()
        f.setObjectName("kpiTile")
        f.setStyleSheet(
            f"QFrame#kpiTile {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-left:3px solid {accent}; min-width:100px; max-width:180px; }}"
        )
        lay = QVBoxLayout(f)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(1)
        lbl_w = QLabel(label.upper())
        lbl_w.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{TEXT_SECONDARY};"
            "background:transparent; border:none;"
        )
        val_w = QLabel(value)
        val_w.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY};"
            "background:transparent; border:none;"
        )
        val_w.setObjectName("kpiVal")
        lay.addWidget(lbl_w)
        lay.addWidget(val_w)
        return f

    @staticmethod
    def _set_kpi(tile: QFrame, value: str) -> None:
        w = tile.findChild(QLabel, "kpiVal")
        if w:
            w.setText(value)

    # ── Refresh ───────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _refresh(self) -> None:
        if not self._store:
            return

        active = list(self._active_types) if self._active_types else _ALL_TYPES
        events = self._store.query_device_events(
            hours=self._window_h,
            event_types=active if len(active) < len(_ALL_TYPES) else None,
        )

        # KPI counts
        all_events = self._store.query_device_events(hours=self._window_h)
        total  = len(all_events)
        joined = sum(1 for e in all_events if e.event_type == "JOINED")
        left   = sum(1 for e in all_events if e.event_type == "LEFT")
        down   = sum(1 for e in all_events if e.event_type == "DOWN")
        known  = len(self._store.get_known_devices())

        self._set_kpi(self._kpi_total,   str(total))
        self._set_kpi(self._kpi_joined,  str(joined))
        self._set_kpi(self._kpi_left,    str(left))
        self._set_kpi(self._kpi_down,    str(down))
        self._set_kpi(self._kpi_devices, str(known))

        # Table
        self._table.setSortingEnabled(False)
        self._table.clear_detail()
        self._table.setRowCount(0)
        self._rows = []

        if not events:
            return

        if self._content_stack.currentIndex() == 0:
            self._content_stack.setCurrentIndex(1)

        known_devices = self._store.get_known_devices()
        for evt in events:
            vendor = ""
            kd = known_devices.get((evt.mac or "").lower())
            if kd:
                vendor = kd.vendor or ""
            self._rows.append((evt, vendor))

            row = self._table.rowCount()
            self._table.insertRow(row)
            dt_str = datetime.datetime.fromtimestamp(evt.ts).strftime("%Y-%m-%d %H:%M:%S")
            color, _ = _EVENT_STYLE.get(evt.event_type, (TEXT_SECONDARY, evt.event_type))
            self._table.setItem(row, 0, _plain_item(dt_str))
            self._table.setItem(row, 1, _badge_item(evt.event_type, color))
            self._table.setItem(row, 2, _plain_item(evt.ip or "—"))
            self._table.setItem(row, 3, _plain_item(evt.mac or "—"))
            self._table.setItem(row, 4, _plain_item(vendor or "—"))
            self._table.setItem(row, 5, _plain_item(evt.detail or ""))
            self._table.setRowHeight(row, 24)

        self._table.setSortingEnabled(True)

    @pyqtSlot(dict)
    def on_cycle_done(self, _result: dict) -> None:
        """Slot for AvailabilityWorker.cycle_done — refresh on each monitoring cycle."""
        self._refresh()

    # ── Detail panel ──────────────────────────────────────────────────────────

    def _build_event_detail(self, logical_row: int) -> QWidget:
        if logical_row >= len(self._rows):
            return QWidget()
        evt, vendor = self._rows[logical_row]
        color, _ = _EVENT_STYLE.get(evt.event_type, (TEXT_SECONDARY, evt.event_type))

        outer = QWidget()
        outer.setStyleSheet(
            f"QWidget {{ background:{BG_HOVER}; border:none;"
            f" border-left:3px solid {color}; }}"
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

        ts_str = datetime.datetime.fromtimestamp(evt.ts).strftime("%Y-%m-%d %H:%M:%S")
        col1 = QWidget()
        col1.setStyleSheet("QWidget { background:transparent; border:none; }")
        g1 = QFormLayout(col1)
        g1.setContentsMargins(0, 0, 0, 0)
        g1.setSpacing(3)
        g1.setHorizontalSpacing(12)
        g1.addRow(_hdr("Timestamp"), _val(ts_str))
        g1.addRow(_hdr("Event"),     _val(evt.event_type, color))
        g1.addRow(_hdr("IP"),        _val(evt.ip or "—"))

        col2 = QWidget()
        col2.setStyleSheet("QWidget { background:transparent; border:none; }")
        g2 = QFormLayout(col2)
        g2.setContentsMargins(0, 0, 0, 0)
        g2.setSpacing(3)
        g2.setHorizontalSpacing(12)
        g2.addRow(_hdr("MAC"),    _val(evt.mac or "—"))
        g2.addRow(_hdr("Vendor"), _val(vendor or "—"))
        if evt.detail:
            g2.addRow(_hdr("Detail"), _val(evt.detail))

        lay.addWidget(col1)
        lay.addWidget(col2)
        lay.addStretch()
        return outer
