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


def _relative_luminance(hex_colour: str) -> float:
    """WCAG relative luminance of a #RRGGBB string."""
    h = hex_colour.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = sorted((_relative_luminance(fg), _relative_luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def test_safe_tooltip_helper_produces_readable_markup():
    import re
    import sys

    sys.path.insert(0, str(ROOT))
    from ui.styles import safe_tooltip

    result = safe_tooltip("192.168.68.1 is at 3C:64:CF:E0:27:02")
    assert result.startswith("<span")
    assert "192.168.68.1 is at 3C:64:CF:E0:27:02" in result

    # The span must pin BOTH ground and ink, not just the ink. Forcing only a
    # foreground is correct only while the background behind it happens to be
    # what you assumed -- the original fix pinned color:WHITE against an
    # assumed-black tooltip background, and rendered white-on-near-white on a
    # Devices-page row in Arctic Clean, where Qt paints the themed TOOLTIP_BG.
    bg_match = re.search(r"background-color:\s*(#[0-9A-Fa-f]{6})", result)
    fg_match = re.search(r"(?<!-)\bcolor:\s*(#[0-9A-Fa-f]{6})", result)
    assert bg_match, f"safe_tooltip() must set its own background: {result!r}"
    assert fg_match, f"safe_tooltip() must set its own foreground: {result!r}"

    # And the pair must actually be legible against itself, in whichever theme
    # is active -- asserting a specific colour would just re-pin the next
    # remedy the same way the last one was pinned.
    ratio = _contrast_ratio(fg_match.group(1), bg_match.group(1))
    assert ratio >= 4.5, (
        f"safe_tooltip() ink pair {fg_match.group(1)} on {bg_match.group(1)} has "
        f"contrast {ratio:.2f}:1, below the WCAG AA floor of 4.5:1"
    )

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
