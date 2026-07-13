"""ui/widgets/column_visibility_toggle.py — Quick / Full column-visibility toggle (Sprint 7, S7-2).

Wraps a QTableWidget. Stores preference in QSettings under
``columns/{table_key}`` so each table remembers its own choice independently.

Full  (default) = every column visible — technical data is never hidden by default.
Quick           = only the columns listed in ``quick_columns`` (by index) remain visible;
                   simplification is an explicit, persisted, per-user opt-in.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QTableWidget

from ui import styles as _s

_SS_ACTIVE = (
    "QPushButton{{background:{ACCENT_DARK};color:{WHITE};border:none;"
    "border-radius:3px;padding:0 8px;font-size:10px;}}"
    "QPushButton:hover{{background:{ACCENT};}}"
)
_SS_INACTIVE = (
    "QPushButton{{background:transparent;color:{TEXT_MUTED};border:none;"
    "border-radius:3px;padding:0 8px;font-size:10px;}}"
    "QPushButton:hover{{background:{BG_DARK};color:{TEXT_PRIMARY};}}"
)


class ColumnVisibilityToggle(QFrame):
    """⊟ Quick / ⊞ Full segmented button for table column visibility."""

    def __init__(
        self,
        table_key: str,
        table: QTableWidget,
        quick_columns: list[int],
        parent=None,
    ):
        super().__init__(parent)
        self._key = f"columns/{table_key}"
        self._table = table
        self._quick_columns = set(quick_columns)
        self.setFixedHeight(24)
        _s.themed_ss(self, "QFrame{{background:{BG_DARK};border:1px solid {BORDER};border-radius:4px;}}")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        self._btn_quick = QPushButton("⊟  Quick")
        self._btn_quick.setFixedHeight(22)
        self._btn_quick.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_quick.setToolTip("Show only Name, Status, Device Type")
        self._btn_quick.clicked.connect(lambda: self._apply("quick"))

        self._btn_full = QPushButton("⊞  Full")
        self._btn_full.setFixedHeight(22)
        self._btn_full.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_full.setToolTip("Show every column — IP, MAC, manufacturer, risk, and more")
        self._btn_full.clicked.connect(lambda: self._apply("full"))

        lay.addWidget(self._btn_quick)
        lay.addWidget(self._btn_full)

        # Restore persisted state (default: full — technical data never hidden by default)
        saved = QSettings("NetSentinel", "NetSentinel").value(self._key, "full")
        self._refresh_styles(saved)
        self._set_columns(saved)

    # ── Private ───────────────────────────────────────────────────────────────

    def _apply(self, mode: str) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(self._key, mode)
        self._refresh_styles(mode)
        self._set_columns(mode)

    def _refresh_styles(self, mode: str) -> None:
        _s.themed_ss(self._btn_quick, _SS_ACTIVE if mode == "quick" else _SS_INACTIVE)
        _s.themed_ss(self._btn_full, _SS_ACTIVE if mode == "full" else _SS_INACTIVE)

    def _set_columns(self, mode: str) -> None:
        full = mode == "full"
        for col in range(self._table.columnCount()):
            self._table.setColumnHidden(col, (not full) and col not in self._quick_columns)
