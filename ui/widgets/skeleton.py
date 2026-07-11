"""Skeleton placeholder rows for QTableWidget async loads.

Usage
-----
    from ui.widgets.skeleton import insert_skeleton_rows, clear_skeleton_rows

    # Before kicking off the async fetch:
    insert_skeleton_rows(self._table, count=6)

    # In the slot that receives the data:
    clear_skeleton_rows(self._table)
    # ... populate real rows ...

Rows are tagged with UserRole == _SKELETON_TAG so they can be identified
and removed without callers needing to track row indices.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from ui import styles as _s

_SKELETON_TAG = "__skeleton__"

# Timer registry: table id → QTimer (kept alive while rows exist)
_timers: dict[int, QTimer] = {}


def insert_skeleton_rows(table: QTableWidget, count: int = 6) -> None:
    """Insert *count* skeleton placeholder rows at the top of *table*."""
    clear_skeleton_rows(table)  # idempotent — remove any existing skeleton first

    cols = table.columnCount()
    for r in range(count):
        table.insertRow(r)
        table.setRowHeight(r, 32)
        for c in range(cols):
            item = QTableWidgetItem("")
            item.setData(Qt.ItemDataRole.UserRole, _SKELETON_TAG)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setBackground(QBrush(QColor(_s.BG_ALT_ROW)))
            table.setItem(r, c, item)

    # Pulse animation: swap background every 650 ms
    phase = [False]

    def _pulse() -> None:
        if not _is_skeleton_present(table):
            _stop_timer(table)
            return
        shade = _s.BG_HOVER if phase[0] else _s.BG_ALT_ROW
        phase[0] = not phase[0]
        rows = table.rowCount()
        for r in range(rows):
            item0 = table.item(r, 0)
            if item0 and item0.data(Qt.ItemDataRole.UserRole) == _SKELETON_TAG:
                for c in range(table.columnCount()):
                    it = table.item(r, c)
                    if it:
                        it.setBackground(QBrush(QColor(shade)))

    timer = QTimer(table)
    timer.setInterval(650)
    timer.timeout.connect(_pulse)
    timer.start()
    _timers[id(table)] = timer


def clear_skeleton_rows(table: QTableWidget) -> None:
    """Remove all skeleton rows from *table*."""
    _stop_timer(table)
    r = 0
    while r < table.rowCount():
        item = table.item(r, 0)
        if item and item.data(Qt.ItemDataRole.UserRole) == _SKELETON_TAG:
            table.removeRow(r)
        else:
            r += 1


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_skeleton_present(table: QTableWidget) -> bool:
    for r in range(table.rowCount()):
        item = table.item(r, 0)
        if item and item.data(Qt.ItemDataRole.UserRole) == _SKELETON_TAG:
            return True
    return False


def _stop_timer(table: QTableWidget) -> None:
    timer = _timers.pop(id(table), None)
    if timer is not None:
        timer.stop()
