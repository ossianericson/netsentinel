"""
SnmpTrapPage — live SNMP trap viewer (T2#10).

Shows a live table of received SNMPv1/v2c traps with:
  • KPI tiles: Total Traps, v1 Traps, v2c Traps, Parse Errors
  • Live table: Time / Source IP / Version / Community / Trap Type / OID
  • Double-click row → varbind detail panel

Architecture rules:
  • Light content area, cards, no dark backgrounds
  • 24px row height (RULE 3)
  • No blocking I/O on main thread (RULE 4)
  • parent=w at all banner/widget constructions (RULE 17)
"""

from __future__ import annotations

import datetime
from typing import Optional

from PyQt6.QtCore    import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QSizePolicy,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QPushButton,
    QFrame, QTextEdit,
)

from modules.metric_store import MetricStore
from ui.styles import (
    ACCENT, BG_CARD, BG_DARK, BORDER, GREEN, RED, AMBER,
    TEXT_PRIMARY, TEXT_SECONDARY, TH_BG, TH_TEXT, BG_HOVER, BG_ALT_ROW,
)


# ── Helpers (mirrors dashboard helpers, no dependency on dashboard) ───────────

def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(True)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setStyleSheet(
        f"QTableWidget {{ background:{BG_CARD}; border:none; font-size:11px; color:{TEXT_PRIMARY}; }}"
        f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT}; font-size:11px;"
        f" font-weight:bold; padding:4px 8px; border:none; }}"
        f"QTableWidget::item:selected {{ background:#CCE4F7; color:{TEXT_PRIMARY}; }}"
        f"QTableWidget::item:hover {{ background:{BG_HOVER}; }}"
        f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
    )
    return t


def _card(title: str) -> tuple[QWidget, QVBoxLayout]:
    outer = QFrame()
    outer.setObjectName("card")
    outer.setStyleSheet(
        f"QFrame#card {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0px; }}"
    )
    outer_lay = QVBoxLayout(outer)
    outer_lay.setContentsMargins(0, 0, 0, 0)
    outer_lay.setSpacing(0)

    title_bar = QLabel(title)
    title_bar.setStyleSheet(
        f"QLabel {{ background:{BG_CARD}; border-bottom:1px solid #ECECEC;"
        f" padding:4px 12px; font-size:13px; font-weight:bold; color:{TEXT_PRIMARY}; }}"
    )
    outer_lay.addWidget(title_bar)

    body = QWidget()
    body.setStyleSheet(f"background:{BG_CARD}; border:none;")
    body_lay = QVBoxLayout(body)
    body_lay.setContentsMargins(0, 0, 0, 0)
    body_lay.setSpacing(0)
    outer_lay.addWidget(body)
    return outer, body_lay


def _kpi_tile(label: str, value: str = "0") -> tuple[QWidget, QLabel]:
    tile = QWidget()
    tile.setStyleSheet(
        f"QWidget {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {ACCENT}; }}"
    )
    tile.setMinimumWidth(110)
    tile.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    lay = QVBoxLayout(tile)
    lay.setContentsMargins(8, 4, 8, 4)
    lay.setSpacing(2)
    lbl = QLabel(label.upper())
    lbl.setStyleSheet(f"font-size:9px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;")
    val = QLabel(value)
    val.setStyleSheet(f"font-size:22px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")
    lay.addWidget(lbl)
    lay.addWidget(val)
    return tile, val


# ── Page ──────────────────────────────────────────────────────────────────────

_MAX_ROWS = 500    # cap live table at 500 rows to prevent memory growth


class SnmpTrapPage(QWidget):
    """Live SNMP trap viewer page."""

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store     = store
        self._total     = 0
        self._v1_count  = 0
        self._v2c_count = 0
        self._err_count = 0
        self._listen_port: int = 0
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"QWidget {{ background:{BG_DARK}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Page title
        title = QLabel("SNMP Trap Receiver")
        title.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;"
        )
        sub = QLabel("Passive UDP listener — receives SNMPv1 and SNMPv2c traps from routers and switches.")
        sub.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        root.addWidget(title)
        root.addWidget(sub)

        # Status bar
        self._status_lbl = QLabel("Not listening.")
        self._status_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        root.addWidget(self._status_lbl)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)
        tile_total, self._kpi_total   = _kpi_tile("Total Traps")
        tile_v1,    self._kpi_v1      = _kpi_tile("v1 Traps")
        tile_v2c,   self._kpi_v2c     = _kpi_tile("v2c Traps")
        tile_err,   self._kpi_errors  = _kpi_tile("Parse Errors")
        kpi_row.addWidget(tile_total)
        kpi_row.addWidget(tile_v1)
        kpi_row.addWidget(tile_v2c)
        kpi_row.addWidget(tile_err)
        kpi_row.addStretch()
        root.addLayout(kpi_row)

        # Trap table card
        card, card_body = _card("Received Traps")
        self._table = _table([
            "Time", "Source IP", "Version", "Community", "Trap Type", "OID"
        ])
        self._table.setColumnWidth(0, 80)
        self._table.setColumnWidth(1, 130)
        self._table.setColumnWidth(2, 50)
        self._table.setColumnWidth(3, 90)
        self._table.setColumnWidth(4, 150)
        self._table.doubleClicked.connect(self._show_detail)
        card_body.addWidget(self._table)
        root.addWidget(card, 1)

        # Empty state label (hidden when rows exist)
        self._empty_lbl = QLabel(
            "No traps received yet.\n"
            "Configure your router/switch to send traps to this host on UDP port 162."
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(f"font-size:11px; color:#9BA8B4; padding:20px;")
        root.addWidget(self._empty_lbl)

        self._sync_empty()

    # ── Slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def on_trap_received(self, trap: dict) -> None:
        self._total += 1
        version = trap.get("version", "?")
        if version == "v1":
            self._v1_count += 1
        elif version == "v2c":
            self._v2c_count += 1
        if trap.get("raw_error"):
            self._err_count += 1

        self._kpi_total.setText(str(self._total))
        self._kpi_v1.setText(str(self._v1_count))
        self._kpi_v2c.setText(str(self._v2c_count))
        self._kpi_errors.setText(str(self._err_count))

        ts_str = datetime.datetime.fromtimestamp(trap.get("ts", 0)).strftime("%H:%M:%S")
        row = self._table.rowCount()
        # Prune oldest rows to keep table bounded
        if row >= _MAX_ROWS:
            self._table.removeRow(0)
            row = self._table.rowCount()
        self._table.insertRow(row)

        cols = [
            ts_str,
            trap.get("src_ip", "?"),
            trap.get("version", "?"),
            trap.get("community", "?"),
            trap.get("trap_type", "?"),
            trap.get("trap_oid", "?"),
        ]
        for col, val in enumerate(cols):
            item = QTableWidgetItem(str(val))
            # Colour error rows amber
            if trap.get("raw_error"):
                item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(AMBER))
            self._table.setItem(row, col, item)

        # Store full trap data for detail view
        self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, trap)
        self._table.scrollToBottom()
        self._sync_empty()

    @pyqtSlot(str)
    def on_status(self, msg: str) -> None:
        self._listen_port = _parse_port(msg)
        self._status_lbl.setText(f"● {msg}")
        self._status_lbl.setStyleSheet(
            f"font-size:11px; color:{GREEN}; background:transparent;"
        )

    @pyqtSlot(str)
    def on_error(self, msg: str) -> None:
        self._status_lbl.setText(f"⚠ {msg}")
        self._status_lbl.setStyleSheet(
            f"font-size:11px; color:{RED}; background:transparent;"
        )

    # ── Detail dialog ─────────────────────────────────────────────────────────

    def _show_detail(self, index) -> None:
        item = self._table.item(index.row(), 0)
        if not item:
            return
        trap = item.data(Qt.ItemDataRole.UserRole)
        if not trap:
            return
        dlg = _TrapDetailDialog(trap, parent=self)
        dlg.exec()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _sync_empty(self) -> None:
        has_rows = self._table.rowCount() > 0
        self._table.setVisible(has_rows)
        self._empty_lbl.setVisible(not has_rows)


class _TrapDetailDialog(QDialog):
    def __init__(self, trap: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Trap Detail — {trap.get('src_ip','?')} ({trap.get('trap_type','?')})")
        self.setMinimumSize(520, 340)
        lay = QVBoxLayout(self)
        lay.setSpacing(6)

        info = (
            f"Time:       {datetime.datetime.fromtimestamp(trap.get('ts',0)).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Source:     {trap.get('src_ip','?')}:{trap.get('src_port','?')}\n"
            f"Version:    {trap.get('version','?')}\n"
            f"Community:  {trap.get('community','?')}\n"
            f"Trap Type:  {trap.get('trap_type','?')}\n"
            f"OID:        {trap.get('trap_oid','?')}\n"
        )
        if trap.get("raw_error"):
            info += f"\nParse error: {trap['raw_error']}\n"

        info_lbl = QLabel(info)
        info_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; font-family:'Consolas','Courier New',monospace;"
        )
        lay.addWidget(info_lbl)

        vb_lbl = QLabel("Variable Bindings:")
        vb_lbl.setStyleSheet(f"font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};")
        lay.addWidget(vb_lbl)

        vb_text = QTextEdit()
        vb_text.setReadOnly(True)
        vb_text.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:{BG_CARD};"
            f" border:1px solid {BORDER}; font-family:'Consolas','Courier New',monospace;"
        )
        varbinds = trap.get("varbinds", [])
        if varbinds:
            vb_text.setPlainText("\n".join(f"  {oid}  =  {val}" for oid, val in varbinds))
        else:
            vb_text.setPlainText("  (none)")
        lay.addWidget(vb_text, 1)

        btn = QPushButton("Close")
        btn.setFixedHeight(30)
        btn.setStyleSheet(
            f"font-size:11px; color:{ACCENT}; border:1px solid {ACCENT};"
            f" background:white; padding:0 16px; border-radius:4px;"
        )
        btn.clicked.connect(self.accept)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)


def _parse_port(status_msg: str) -> int:
    """Extract port number from status string like 'Listening on UDP :162'."""
    try:
        return int(status_msg.rsplit(":", 1)[-1])
    except (ValueError, IndexError):
        return 0
