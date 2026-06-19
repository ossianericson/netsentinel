"""ExpandingTable — inline master-detail row expansion for QTableWidget.

Drop-in replacement for QTableWidget.  Clicking a data row expands an
inline detail panel below it; clicking the same row again collapses it.
Only one row can be open at a time.

Usage
-----
    tbl = ExpandingTable(
        0, len(cols),
        detail_builder=lambda logical: self._build_detail(logical),
        detail_height=120,
    )

    # Before repopulating the table, call:
    tbl.clear_detail()

The ``detail_builder`` receives the *logical* row index (0-based within
the currently displayed data, ignoring the injected detail row).  Store
your data list as an instance attribute and index into it from the builder.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget


class ExpandingTable(QTableWidget):
    def __init__(self, rows: int, cols: int,
                 detail_builder=None,
                 detail_height: int = 110,
                 parent=None):
        super().__init__(rows, cols, parent)
        self._detail_builder      = detail_builder
        self._detail_height       = detail_height
        self._detail_row          = -1   # display-row index of the open detail (-1 = closed)
        self._expanded_logical    = -1   # logical data-row index currently expanded
        self._sorting_before_detail = False  # was sorting on before we opened a detail?
        self.cellClicked.connect(self._on_cell_clicked)

    # ── Row index conversions ─────────────────────────────────────────────────

    def _display_to_logical(self, display: int) -> int:
        """Return the logical data-row for a display row, or -1 if it is the detail row."""
        if self._detail_row < 0 or display < self._detail_row:
            return display
        if display == self._detail_row:
            return -1
        return display - 1

    # ── Public API ────────────────────────────────────────────────────────────

    def clear_detail(self) -> None:
        """Collapse and remove any open detail row.  Call before repopulating."""
        if self._detail_row >= 0 and self._detail_row < self.rowCount():
            self.removeRow(self._detail_row)
        self._detail_row      = -1
        self._expanded_logical = -1
        # Restore sorting if it was disabled only to protect the detail insertion
        if self._sorting_before_detail:
            self._sorting_before_detail = False
            self.setSortingEnabled(True)

    # ── Click handler ─────────────────────────────────────────────────────────

    def _on_cell_clicked(self, display_row: int, _col: int) -> None:
        if self._detail_builder is None:
            return
        logical = self._display_to_logical(display_row)
        if logical < 0:
            return  # user clicked on the detail row itself — ignore

        toggling = (logical == self._expanded_logical)

        # Collapse any currently open detail first (also restores sorting if needed)
        self.clear_detail()

        if toggling:
            return  # same row clicked twice → collapse only

        # Disable sorting before inserting the detail row.  With sorting enabled Qt
        # immediately tries to rank the new (item-less) row, hits a null item in the
        # sort comparator, and crashes.  We re-enable sorting in clear_detail().
        if self.isSortingEnabled():
            self._sorting_before_detail = True
            self.setSortingEnabled(False)

        # After clear_detail(), display == logical for all rows (no injected row).
        detail_pos = logical + 1
        self.insertRow(detail_pos)
        self.setSpan(detail_pos, 0, 1, self.columnCount())
        widget = self._detail_builder(logical)
        self.setCellWidget(detail_pos, 0, widget)
        self.setRowHeight(detail_pos, self._detail_height)
        self._detail_row      = detail_pos
        self._expanded_logical = logical

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        key = event.key()
        if key in (Qt.Key.Key_J, Qt.Key.Key_K):
            current = self.currentRow()
            step = 1 if key == Qt.Key.Key_J else -1
            target = max(0, min(self.rowCount() - 1, current + step))
            self.setCurrentCell(target, self.currentColumn())
            return
        super().keyPressEvent(event)
