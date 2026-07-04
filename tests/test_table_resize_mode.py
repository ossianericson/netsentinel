"""test_table_resize_mode.py — enforcement guard against whole-table ResizeToContents.

MECHANISM (why this matters):
``header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)`` — the
single-argument overload, which sets the DEFAULT resize mode for every column —
tells Qt to recompute every column's ideal width (a full ``sizeHintForColumn()``
pass, calling ``QStyledItemDelegate::sizeHint()`` per cell, which for text cells
calls into DirectWrite font-metrics/glyph-layout) on every relevant model change:
row insert, ``dataChanged``, and critically ``sortByColumn()``. For a table with
hundreds-to-thousands of rows this is multiple seconds of synchronous main-thread
work, during which Qt cannot process input or repaint — Windows reports the whole
app as "Not Responding" for the duration.

This was confirmed live (2026-07-04) as the actual root cause of an intermittent
"whole app freezes for a few seconds, always recovers" bug via a memory dump
captured mid-freeze with ``procdump -h``: the main thread's stack was stuck in
``QHeaderView::resizeSections`` -> ``sizeHintForColumn`` ->
``QStyledItemDelegate::sizeHint`` -> DirectWrite glyph metrics, called from
``QAbstractItemModel::dataChanged``. See RULE-PERF1.

The two-argument overload — ``setSectionResizeMode(column_index, mode)`` — only
resizes that one column and is fine; it is excluded from this check.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_DIR = ROOT / "ui"

# Matches the single-argument (whole-header) overload only: the resize-mode
# constant appears as the first/only thing between the parens, optionally
# split across a line break (as `foo(\n    QHeaderView...)`). A leading
# integer/column-index argument (the safe two-arg overload) is excluded by
# requiring the "(" to be followed (allowing whitespace/newline) directly by
# "QHeaderView.ResizeMode.ResizeToContents".
PAT = re.compile(
    r"setSectionResizeMode\(\s*QHeaderView\.ResizeMode\.ResizeToContents\s*\)",
    re.MULTILINE,
)


def test_no_whole_table_resize_to_contents():
    offenders: list[str] = []
    for path in sorted(UI_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8-sig")
        for m in PAT.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            rel = path.relative_to(ROOT).as_posix()
            offenders.append(f"{rel}:{line_no}")

    assert not offenders, (
        "Whole-table QHeaderView.ResizeMode.ResizeToContents freezes the main "
        "thread for seconds on tables with more than a handful of rows (RULE-PERF1) "
        "-- it recomputes every column's width via per-cell sizeHint() on every "
        "model change (insert/dataChanged/sort). Use "
        "QHeaderView.ResizeMode.Interactive instead (optionally call "
        "resizeColumnsToContents() once after populating). Offenders:\n  "
        + "\n  ".join(offenders)
    )
