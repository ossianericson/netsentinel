"""ui/widgets/density_toggle.py — Compact / Comfortable row-density toggle.

Wraps a QTableWidget or QTableView.  Stores preference in QSettings under
``density/{table_key}`` so each table remembers its own choice independently.

Compact    = 24 px rows  (matches historical default)
Comfortable = 36 px rows (breathing room on large screens)
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QTableView

from ui.styles import ACCENT, ACCENT_DARK, BG_DARK, BORDER, TEXT_MUTED, TEXT_PRIMARY, WHITE

_COMPACT_PX     = 24
_COMFORTABLE_PX = 36

_SS_ACTIVE = (
    f"QPushButton{{background:{ACCENT_DARK};color:{WHITE};border:none;"
    f"border-radius:3px;padding:0 8px;font-size:10px;}}"
    f"QPushButton:hover{{background:{ACCENT};}}"
)
_SS_INACTIVE = (
    f"QPushButton{{background:transparent;color:{TEXT_MUTED};border:none;"
    f"border-radius:3px;padding:0 8px;font-size:10px;}}"
    f"QPushButton:hover{{background:{BG_DARK};color:{TEXT_PRIMARY};}}"
)


class DensityToggle(QFrame):
    """⊟ Compact / ⊞ Comfortable segmented button for table row height."""

    def __init__(self, table_key: str, table: QTableView, parent=None):
        super().__init__(parent)
        self._key   = f"density/{table_key}"
        self._table = table
        self.setFixedHeight(24)
        self.setStyleSheet(
            f"QFrame{{background:{BG_DARK};border:1px solid {BORDER};border-radius:4px;}}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        self._btn_compact = QPushButton("⊟  Compact")
        self._btn_compact.setFixedHeight(22)
        self._btn_compact.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_compact.setToolTip("Compact rows (24 px)")
        self._btn_compact.clicked.connect(lambda: self._apply("compact"))

        self._btn_comfortable = QPushButton("⊞  Comfortable")
        self._btn_comfortable.setFixedHeight(22)
        self._btn_comfortable.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_comfortable.setToolTip("Comfortable rows (36 px)")
        self._btn_comfortable.clicked.connect(lambda: self._apply("comfortable"))

        lay.addWidget(self._btn_compact)
        lay.addWidget(self._btn_comfortable)

        # Restore persisted state (default: compact)
        saved = QSettings("NetSentinel", "NetSentinel").value(self._key, "compact")
        self._refresh_styles(saved)
        self._set_row_height(saved)

    # ── Private ───────────────────────────────────────────────────────────────

    def _apply(self, mode: str) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(self._key, mode)
        self._refresh_styles(mode)
        self._set_row_height(mode)

    def _refresh_styles(self, mode: str) -> None:
        self._btn_compact.setStyleSheet(
            _SS_ACTIVE if mode == "compact" else _SS_INACTIVE
        )
        self._btn_comfortable.setStyleSheet(
            _SS_ACTIVE if mode == "comfortable" else _SS_INACTIVE
        )

    def _set_row_height(self, mode: str) -> None:
        px = _COMPACT_PX if mode == "compact" else _COMFORTABLE_PX
        self._table.verticalHeader().setDefaultSectionSize(px)
