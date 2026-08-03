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

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from ui import styles as _s

_SKELETON_TAG = "__skeleton__"


class _PulseController(QObject):
    """Drives the pulse animation, but only while the table is really visible.

    A self-starting QTimer here runs for the entire app session on a table
    nobody can see (RULE-WIN18): the lazy page-builder constructs every page
    shortly after startup whether or not the user opens it, and a caller whose
    refresh bails out on `not self.isVisible()` never reaches
    clear_skeleton_rows() — so the rows, and the pulse, stay forever. Each tick
    allocates a QBrush + QColor per skeleton cell, which are C++ objects and so
    invisible to tracemalloc.

    Visibility is tracked with an event filter rather than a hideEvent override
    because this widget does not own the table it animates — one controller
    covers every caller (the RULE-WIN17 shared-widget precedent).
    """

    def __init__(self, table: QTableWidget, pulse) -> None:
        super().__init__(table)
        self._timer = QTimer(self)
        self._timer.setInterval(650)
        self._timer.timeout.connect(pulse)
        table.installEventFilter(self)
        if table.isVisible():
            self._timer.start()

    def eventFilter(self, obj, event) -> bool:
        etype = event.type()
        if etype == QEvent.Type.Show:
            if not self._timer.isActive():
                self._timer.start()
        elif etype == QEvent.Type.Hide:
            self._timer.stop()
        return False   # never consume — this filter only observes visibility

    def dispose(self) -> None:
        """Stop pulsing and detach from the table.

        Removing the filter is defensive rather than load-bearing today: the
        registry holds the only Python reference, so dropping it also drops the
        wrapper PyQt needs to dispatch `eventFilter` back into Python, and the
        timer would stay stopped either way. Do not rely on that — it is an
        artifact of who holds the reference, not of this class's contract.
        """
        self._timer.stop()
        parent = self.parent()
        if parent is not None:
            parent.removeEventFilter(self)
        self.deleteLater()


# Pulse registry: table id → _PulseController (kept alive while rows exist)
_pulses: dict[int, _PulseController] = {}


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

    key = id(table)
    _pulses[key] = _PulseController(table, _pulse)
    # If the table is destroyed while skeleton rows are still present (e.g. the
    # scan that would supply real data never completes and clear_skeleton_rows()
    # is never called), drop the registry entry here -- before Qt deletes the
    # QTimer child and before CPython can ever reuse this id() for a new table.
    # Without this, the entry leaks forever (the _pulse closure keeps `table`
    # alive) and a later id() collision can call .stop() on an already-deleted
    # QTimer.
    table.destroyed.connect(lambda _obj=None, k=key: _pulses.pop(k, None))


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
    pulse = _pulses.pop(id(table), None)
    if pulse is not None:
        try:
            pulse.dispose()
        except RuntimeError:
            pass  # Qt already deleted it (e.g. its parent table was destroyed)
