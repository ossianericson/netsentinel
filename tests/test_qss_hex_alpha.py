"""test_qss_hex_alpha.py — enforcement guard against 8-digit-hex alpha in QSS.

MECHANISM (why this matters):
Qt Style Sheets parse an 8-digit hex colour as ``#AARRGGBB`` (alpha FIRST), not
the CSS ``#RRGGBBAA`` (alpha LAST) that the syntax visually suggests. So writing
``f"background:{ACCENT}22"`` — intending "the accent colour at ~13% opacity" —
produces the literal string ``#0078D422``, which Qt reads as
``alpha=0x00, r=0x78, g=0xD4, b=0x22`` → a FULLY TRANSPARENT green, i.e. nothing
renders. Worse, a colour whose first byte is high renders opaque and wrong:
``{AMBER}22`` → ``#F59E0B22`` → ``alpha=0xF5, rgb=(158,11,34)`` = an opaque dark
crimson. That is exactly how the home "live challenge" banner shipped bright red
instead of translucent amber (July 2026).

CORRECT PATTERN — use ``alpha()`` from ui/styles.py, which emits a proper
``rgba(r,g,b,a)`` string, or a pre-defined ``*_BG`` token:

    from ui.styles import alpha, AMBER, AMBER_BG
    w.setStyleSheet(f"background:{alpha(ACCENT, 0x22)};")   # translucent accent
    w.setStyleSheet(f"background:{AMBER_BG};")              # named translucent amber

Zero-tolerance: the whole ui/ tree must contain no ``{TOKEN}<2 hex>`` alpha-append
in any stylesheet string. ui/styles.py is excluded because the ``alpha()``
docstring intentionally shows the antipattern as a counter-example.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_DIR = ROOT / "ui"

# A style-token name in braces, immediately followed by exactly two hex digits,
# then a QSS delimiter (quote / whitespace / semicolon). The lookahead keeps the
# match anchored to a real "append alpha to a colour" site. Matches both
# uppercase style-module tokens (e.g. {AMBER}22) and lowercase/mixed-case local
# variables holding a colour string (e.g. {color}40, {dot_color}22) — Qt parses
# the 8-digit hex the same broken way regardless of the variable's naming case.
PAT = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}([0-9a-fA-F]{2})(?=["\s;])')

# ui/styles.py hosts alpha() and documents the antipattern on purpose.
EXCLUDE = {UI_DIR / "styles.py"}


def test_no_hex_alpha_append_in_qss():
    offenders: list[str] = []
    for path in sorted(UI_DIR.rglob("*.py")):
        if path in EXCLUDE:
            continue
        text = path.read_text(encoding="utf-8-sig")
        for i, line in enumerate(text.splitlines(), start=1):
            for m in PAT.finditer(line):
                rel = path.relative_to(ROOT).as_posix()
                offenders.append(f"{rel}:{i}  {{{m.group(1)}}}{m.group(2)}")

    assert not offenders, (
        "8-digit-hex alpha in QSS — Qt parses these as #AARRGGBB (alpha-first), "
        "so the colour is scrambled (usually invisible or a wrong opaque hue). "
        "Replace `{TOKEN}NN` with `{alpha(TOKEN, 0xNN)}` (from ui.styles) or a "
        "named `*_BG` token. Offenders:\n  " + "\n  ".join(offenders)
    )


def test_alpha_helper_emits_rgba():
    from ui.styles import alpha
    # int 0-255 alpha
    assert alpha("#F59E0B", 0x22) == "rgba(245,158,11,0.133)"
    # float 0-1 alpha
    assert alpha("#0078D4", 0.12) == "rgba(0,120,212,0.120)"
    # full opacity
    assert alpha("#2E7D32", 255) == "rgba(46,125,50,1.000)"


def test_alpha_helper_passes_through_non_hex():
    from ui.styles import alpha
    # rgba() tokens (e.g. BORDER) cannot take layered alpha — returned unchanged.
    assert alpha("rgba(255,255,255,0.08)", 0x22) == "rgba(255,255,255,0.08)"
