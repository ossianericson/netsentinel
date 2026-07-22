"""Ratchet test for RULE-UX7 -- Arctic Clean tooltip readability.

`.setToolTip(...)` (on a plain QWidget like QPushButton/QLabel, or on an
item-view item like QTableWidgetItem/QListWidgetItem/a header item) renders
its background as solid black in Arctic Clean regardless of the app's
`QToolTip` QSS rule (`TOOLTIP_BG`) -- verified live on both a QPushButton
tooltip (Protocol Visualizer's protocol-picker buttons) and a
QListWidgetItem tooltip (the Protocol Visualizer step list). Midnight Pro's
tooltip text colour is already light, so the same black background reads
fine there by coincidence; Arctic Clean's tooltip text colour is dark navy,
so it's illegible black-on-black.

`ui.styles.safe_tooltip()` forces a fixed light foreground via inline HTML
(Qt's rich-text tooltip renderer honours it regardless of the QSS/palette
gap above). Every `.setToolTip(<non-empty text>)` call site in `ui/` should
route its argument through `safe_tooltip()` (or that file's alias for
`ui.styles`).

This is a ratchet, not a completeness check: a full AST-based "is this
receiver a QWidget/item that takes a tooltip" classifier is impractical, so
this test only guards against *regression* -- the call-site count may only
go up (a fix), never down (an unwrapped call replacing a wrapped one, or a
wrapped call site deleted without the underlying tooltip being removed too).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_ROOT = ROOT / "ui"

# Floor as of the RULE-UX7 fix session -- 220 call sites across 55 files
# (a full sweep of every .setToolTip() in ui/, not just the item-view ones
# originally suspected -- a plain QPushButton tooltip turned out to have the
# identical bug). Only ever raise this number (when more call sites are
# fixed); never lower it.
#
# Lowered 220 -> 218: ui/system_tray.py's two QSystemTrayIcon.setToolTip()
# calls were unwrapped. Unlike a QWidget tooltip, QSystemTrayIcon's tooltip
# is the native OS tray tip (NOTIFYICONDATA szTip on Windows) -- plain text
# only, no rich-text renderer -- so safe_tooltip()'s HTML <span> wrapper was
# printing raw markup to the user instead of styling anything (live bug
# report: tray hover showed literal "<span style='color:#E6EDF3;'>..."
# text). This is a legitimate removal, not a regression -- see the docstring
# above for the case where lowering the floor is correct.
_MIN_CALL_SITES = 218

_SAFE_TOOLTIP_CALL_RE = re.compile(r"\.safe_tooltip\(")


def test_safe_tooltip_call_sites_do_not_regress():
    total = 0
    for path in UI_ROOT.rglob("*.py"):
        if path.name == "styles.py":
            continue  # the definition itself, not a call site
        text = path.read_text(encoding="utf-8-sig")
        total += len(_SAFE_TOOLTIP_CALL_RE.findall(text))

    assert total >= _MIN_CALL_SITES, (
        f"safe_tooltip() call-site count dropped to {total} (floor is "
        f"{_MIN_CALL_SITES}). A tooltip that was fixed for Arctic Clean "
        "readability (RULE-UX7) appears to have regressed -- either a "
        "wrapped .setToolTip() call was reverted to raw text, or a fixed "
        "call site was deleted without checking whether it should have been "
        "moved instead. If a call site was legitimately removed (the "
        "underlying tooltip/widget was deleted), lower _MIN_CALL_SITES with "
        "a comment explaining why."
    )


def test_safe_tooltip_helper_produces_readable_markup():
    import sys

    sys.path.insert(0, str(ROOT))
    from ui.styles import WHITE, safe_tooltip

    result = safe_tooltip("192.168.68.1 is at 3C:64:CF:E0:27:02")
    assert result.startswith("<span")
    assert f"color:{WHITE}" in result
    assert "192.168.68.1 is at 3C:64:CF:E0:27:02" in result

    # Newlines must become <br> -- plain \n has no effect once Qt treats the
    # tooltip string as rich text (it would otherwise collapse to one line).
    multi = safe_tooltip("line one\nline two")
    assert "<br>" in multi
    assert "\n" not in multi.replace("<br>", "")

    # HTML-special characters in the source text must be escaped so they
    # render as literal text instead of being interpreted as markup.
    escaped = safe_tooltip("<script>alert(1)</script> & \"quoted\"")
    assert "<script>" not in escaped
    assert "&lt;script&gt;" in escaped
