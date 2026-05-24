"""
ui/widgets/context_menu.py — shared right-click menu for QTableWidget / ExpandingTable.

Usage:
    from ui.widgets.context_menu import install_copy_menu
    install_copy_menu(self._table)                       # Copy Cell + Copy Row only
    install_copy_menu(self._table, [                     # with page-specific extras
        ("separator", None),
        ("Open in Inventory →", lambda: ...),
    ])

Extra actions list items:
    ("separator", None)            — draws a separator line
    ("label", callable_or_None)   — menu action; disabled when callable is None
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QMenu, QTableWidget

from ui.styles import BG_CARD, BORDER, TABLE_SEL, TEXT_PRIMARY


def install_copy_menu(
    table: QTableWidget,
    extra_actions: Optional[list[tuple[str, Optional[Callable]]]] = None,
) -> None:
    """Wire Copy Cell + Copy Row (+ optional extras) to *table*'s right-click menu."""
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    _extras = extra_actions or []
    table.customContextMenuRequested.connect(
        lambda pos, t=table, ex=_extras: _show(t, pos, ex)
    )


def _show(
    table: QTableWidget,
    pos,
    extra_actions: list[tuple[str, Optional[Callable]]],
) -> None:
    item = table.itemAt(pos)
    if item is None:
        return

    row = item.row()
    col = item.column()

    menu = QMenu(table)
    menu.setStyleSheet(
        f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; }}"
        f"QMenu::item:selected {{ background:{TABLE_SEL}; }}"
        f"QMenu::separator {{ background:{BORDER}; height:1px; margin:3px 6px; }}"
    )

    copy_cell_act = menu.addAction("Copy cell")
    copy_row_act  = menu.addAction("Copy row")

    if extra_actions:
        for label, cb in extra_actions:
            if label == "separator":
                menu.addSeparator()
            else:
                act = menu.addAction(label)
                if cb is None:
                    act.setEnabled(False)

    chosen = menu.exec(QCursor.pos())
    if chosen is None:
        return

    if chosen == copy_cell_act:
        cell_item = table.item(row, col)
        text = cell_item.text() if cell_item else ""
        # Prefer cell widget text (e.g. QPushButton label) if item is absent
        if not text:
            w = table.cellWidget(row, col)
            if w:
                text = getattr(w, "text", lambda: "")()
        QApplication.clipboard().setText(text)
        return

    if chosen == copy_row_act:
        parts = []
        for c in range(table.columnCount()):
            it = table.item(row, c)
            if it:
                parts.append(it.text())
            else:
                w = table.cellWidget(row, c)
                parts.append(getattr(w, "text", lambda: "")() if w else "")
        QApplication.clipboard().setText("\t".join(parts))
        return

    # Dispatch extra actions
    for label, cb in extra_actions:
        if label != "separator" and cb is not None:
            if chosen.text() == label:
                cb()
                break
