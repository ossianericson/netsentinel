"""Ratchet test for P6 -- QSS style-snippet recipe layer.

Five inline-QSS shapes (plain text label, card/banner QFrame wrapper, pill
chip/badge, flat "X" dismiss button, and its press-highlight sibling) were
re-typed by hand at hundreds of call sites across ui/, each needing a
parallel edit if the recipe ever changed (e.g. the RULE-QSS2 hex-alpha fix
or a hover/pressed colour correction). ui/styles.py now exposes named
recipe functions for each -- qss_label()/qss_muted_label(), qss_frame(),
qss_chip(), and qss_dismiss_button() -- and home_page.py, overview_tile.py,
and settings_cards.py (the three heaviest files, ~300 setStyleSheet calls
between them) were migrated onto them.

This is a scoped pass, not a wholesale migration: only these three files are
guarded here. New code anywhere should still prefer the recipe functions,
but the ratchet below only prevents *regression* in the files already
cleaned up -- reintroducing the raw literal shape in one of them means using
a hand-rolled string where a one-line recipe call already exists.

Baselines may only go down (fixing a remaining raw instance) or stay flat --
never up. If a new raw match is a genuinely distinct variant the recipe
functions can't express (as with the four home_page.py `dismiss_b` matches:
they mix in border-radius, text-align, or a different hover treatment),
add/adjust the baseline entry with a comment explaining why.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

_TARGET_FILES = [
    ROOT / "ui" / "pages" / "home_page.py",
    ROOT / "ui" / "widgets" / "overview_tile.py",
    ROOT / "ui" / "pages" / "settings_cards.py",
]

# Matches a raw `color:{X}; font-size:Npx; border:none;` label recipe (either
# property order, with or without an explicit `background:transparent;`) --
# the shape now covered by ui.styles.qss_label()/qss_muted_label().
_LABEL_RE = re.compile(
    r'f"(?:color:\{[A-Z_]+\};\s*font-size:\d+px|font-size:\d+px;\s*color:\{[A-Z_]+\})'
    r'(?:;\s*font-weight:\w+)?;\s*(?:background:transparent;\s*)?border:none;"'
)

# Matches the opening clause of a raw `QFrame#name { background:...;
# border:1px solid ...; ... }` card wrapper -- the shape now covered by
# ui.styles.qss_frame().
_CARD_FRAME_RE = re.compile(
    r'f"QFrame#\w+\s*\{\{\s*background:\{[A-Z_]+\};\s*border:1px solid \{[A-Z_]+\};'
)

# Matches the two raw "X" dismiss-button opening clauses now covered by
# ui.styles.qss_dismiss_button() -- the plain transparent-throughout variant
# (A) and the property-reordered variant (B) that qss_dismiss_button's
# press_bg= parameter also serves.
_DISMISS_A_RE = re.compile(
    r'f"QPushButton \{\{ color:\{[A-Z_]+\}; background:transparent; border:none; font-size:\d+px;'
)
_DISMISS_B_RE = re.compile(
    r'f"QPushButton \{\{ background:transparent; color:\{[A-Z_]+\}; border:none;'
)

# Matches the raw chip/badge recipe now covered by ui.styles.qss_chip().
_CHIP_RE = re.compile(
    r"font-size:10px; font-weight:bold; color:\{[A-Z_]+\}; background:\{[A-Z_]+\};"
    r" border:1px solid \{[A-Z_]+\}; border-radius:10px;"
)

_PATTERNS = {
    "label": _LABEL_RE,
    "card_frame": _CARD_FRAME_RE,
    "dismiss_a": _DISMISS_A_RE,
    "dismiss_b": _DISMISS_B_RE,
    "chip": _CHIP_RE,
}

# Per-file, per-pattern baseline. Anything not listed defaults to 0.
_BASELINE: dict[str, dict[str, int]] = {
    # home_page.py's four `dismiss_b` matches dropped to 0 in the Instant Theme
    # Switching Phase 4a conversion: those f-string setStyleSheet calls became
    # themed_ss() plain-string templates (the `f` prefix the regex keys on is
    # gone), so the raw-literal shape no longer appears. Defaults to 0.
}


def test_no_raw_qss_recipe_duplication_in_p6_targets():
    offenders = []
    for path in _TARGET_FILES:
        text = path.read_text(encoding="utf-8-sig")
        file_baseline = _BASELINE.get(path.name, {})
        for pattern_name, regex in _PATTERNS.items():
            n = len(regex.findall(text))
            baseline = file_baseline.get(pattern_name, 0)
            if n > baseline:
                offenders.append(
                    f"{path.relative_to(ROOT).as_posix()}: {pattern_name} found {n}, "
                    f"baseline {baseline}"
                )
            elif n < baseline:
                offenders.append(
                    f"{path.relative_to(ROOT).as_posix()}: {pattern_name} baseline says "
                    f"{baseline} but found {n} -- lower the baseline, don't leave it stale"
                )

    assert not offenders, (
        "New raw QSS recipe duplication found in a P6-migrated file: "
        f"{offenders}. Use ui.styles.qss_label()/qss_muted_label() for plain "
        "text labels, qss_frame() for card/banner QFrame wrappers, "
        "qss_chip() for pill badges, or qss_dismiss_button() for flat 'X' "
        "close buttons instead of composing the QSS f-string by hand."
    )
