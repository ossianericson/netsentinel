"""test_qss_no_cursor.py — guard against the CSS ``cursor`` property in Qt QSS.

MECHANISM (why this matters):
Qt's stylesheet engine implements a subset of CSS and has **no** ``cursor``
property. A rule like ``QPushButton { ... cursor:default; }`` parses far enough for
Qt to reach the unknown property, then emits ``Unknown property cursor`` to stderr
on **every** application of that stylesheet — theme switches, tile rebuilds, etc.
Over a long session this floods the log (82 occurrences in the 2026-07 Store chaos
run) while doing nothing: the pointer shape is unchanged. The correct way to set a
cursor in Qt is the widget API ``w.setCursor(Qt.CursorShape.…)`` — never QSS.

This guard scans the whole ``ui/`` tree for the QSS property form ``cursor:`` and
fails if any reappears. It intentionally does not match the Qt enum names
(``…PointingHandCursor``) or ``setCursor(`` calls — only ``cursor`` immediately
followed by a colon, which is unique to the (unsupported) stylesheet property.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_DIR = ROOT / "ui"

# Lowercase ``cursor`` immediately followed by a colon = the QSS property form.
# Qt enum members end in ``Cursor`` (capital C, no colon); ``setCursor(`` uses a
# paren; neither matches. Case-sensitive on purpose.
PAT = re.compile(r"\bcursor\s*:")


def test_no_cursor_property_in_qss():
    offenders: list[str] = []
    for path in sorted(UI_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8-sig")
        for i, line in enumerate(text.splitlines(), start=1):
            if PAT.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{i}  {line.strip()}")

    assert not offenders, (
        "The QSS `cursor:` property is not supported by Qt's stylesheet engine — it "
        "emits `Unknown property cursor` to stderr on every stylesheet apply and has "
        "no effect. Remove it; set a pointer shape with `w.setCursor(Qt.CursorShape.…)` "
        "instead. Offenders:\n  " + "\n  ".join(offenders)
    )
