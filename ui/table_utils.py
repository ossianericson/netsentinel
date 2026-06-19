"""
ui/table_utils.py — shared table helpers used across multiple pages.

Provides:
  save_column_widths / restore_column_widths  — FILTER-6 column persistence
  kpi_tile                                    — POLISH-13 standardized KPI tile
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QFrame, QLabel, QTableWidget, QVBoxLayout

from ui.styles import ACCENT, BG_CARD, BORDER, TEXT_PRIMARY, TEXT_SECONDARY
from ui.widgets.animated_kpi import AnimatedKpi


# ── Column width persistence ──────────────────────────────────────────────────

def save_column_widths(table: QTableWidget, key: str) -> None:
    qs = QSettings("NetSentinel", "NetSentinel")
    widths = [table.columnWidth(i) for i in range(table.columnCount())]
    qs.setValue(f"table/{key}/col_widths", widths)


def restore_column_widths(table: QTableWidget, key: str) -> None:
    qs = QSettings("NetSentinel", "NetSentinel")
    widths = qs.value(f"table/{key}/col_widths", [])
    if widths:
        for i, w in enumerate(widths):
            if i < table.columnCount() and int(w) > 0:
                table.setColumnWidth(i, int(w))


# ── Standardized KPI tile ─────────────────────────────────────────────────────

def kpi_tile(label: str, value: str = "0", accent: str = ACCENT) -> tuple[QFrame, AnimatedKpi]:
    """Return (tile_widget, value_label).

    value_label is an AnimatedKpi (QLabel subclass) — call set_value(int) for animation
    or setText(str) for a plain update.
    """
    tile = QFrame()
    tile.setFixedHeight(56)
    tile.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {accent}; border-radius:0; }}"
    )
    lay = QVBoxLayout(tile)
    lay.setContentsMargins(12, 6, 12, 6)
    lay.setSpacing(2)

    lbl = QLabel(label.upper())
    lbl.setStyleSheet(
        f"font-size:9px; font-weight:600; color:{TEXT_SECONDARY};"
        f" letter-spacing:0.5px; border:none; background:transparent;"
    )

    val = AnimatedKpi(value)
    val.setStyleSheet(
        f"font-size:22px; font-weight:700; color:{TEXT_PRIMARY};"
        f" border:none; background:transparent;"
    )
    val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    lay.addWidget(lbl)
    lay.addWidget(val)
    return tile, val
