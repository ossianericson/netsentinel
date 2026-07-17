"""
CI gate: detect mojibake (double-encoded UTF-8) in Python source files.

Mojibake happens when a UTF-8 source file is opened in a Latin-1 / Windows-1252
editor that misreads multi-byte sequences as individual characters and saves them
back as UTF-8.  The result: characters like —, →, ·, ☀, ×, ⚠ are replaced by
sequences of Latin supplement and Windows-1252 code points.

Two classes of mojibake are detected:

2–3-byte UTF-8 sequences (BMP characters):
  U+00C3 (Ã) or U+00E2 (â) followed immediately by a Windows-1252 code point
  in the range 0x80–0x9F (mapped to special chars like €, ‚, ƒ, „, …, †, ‡,
  ˆ, ‰, Š, ‹, Œ, Ž, ', ', ", ", •, –, —, ˜, ™, š, ›, œ, ž, Ÿ).

4-byte UTF-8 sequences (emoji and supplementary plane characters):
  Byte F0 9F... (U+1Fxxx emoji range, e.g. 🌙 🔌 📌 ⚡) is misread as cp1252:
    F0 → ð (U+00F0 LATIN SMALL LETTER ETH)
    9F → Ÿ (cp1252 0x9F → U+0178 LATIN CAPITAL LETTER Y WITH DIAERESIS)
  The two-char prefix ðŸ (U+00F0 + U+0178) is a reliable signature for this class.

This test scans all .py source files in ui/ and modules/ for known mojibake
sequences inside string literals.  Comments are excluded from the check.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── Mojibake signatures ───────────────────────────────────────────────────────
# These regex patterns match the most common double-encoded UTF-8 sequences
# found in Windows-1252 / Latin-1 corruption of NetSentinel source files.
#
# The patterns are character-level (matching Unicode code points as they appear
# after correct UTF-8 decoding), not byte-level.

_MOJIBAKE_PATTERNS: list[str] = [
    # ── Sequences starting with Ã (U+00C3) ──────────────────────────────────
    # Ã followed by a Windows-1252 special char in 0x80–0x9F range
    r'Ã[\x80-\x9f\xa0-\xbf]',    # Ã + any Latin-1 supplement
    'Ã[ƒ†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ]',  # Ã + Windows-1252 specials
    # Common close-button mojibake: Ã + ƒ (triple-encoded ×)
    r'Ãƒ',
    # ── Sequences starting with Å (U+00C5) ──────────────────────────────────
    r'Å[¸\x92]',                  # Å¸ or Å + RIGHT SINGLE QUOTE
    'Å[‘’“”•–—˜™š›œžŸ]',
    # ── Sequences starting with â (U+00E2) ──────────────────────────────────
    # â followed by € (U+20AC, cp1252 byte 0x80) — em dash / arrow / quote families
    r'â€["“”‘’‚„†…•]',
    r'â€"',   # â + € + RIGHT DOUBLE QUOTATION MARK — classic em dash mojibake
    r'â€¦',   # â + € + ¦ — ellipsis mojibake
    r'â†',    # â + † — arrow family mojibake
    r'âœ',    # â + LATIN SMALL LIGATURE OE — icon mojibake
    r'â˜',    # â + SMALL TILDE — sun/star mojibake
    r'âš',    # â + š — warning/gear mojibake
    # ── Sequences starting with Â (U+00C2) ──────────────────────────────────
    r'Â[·°¨]',  # Â + middle dot / degree / diaeresis — middle-dot mojibake
    # ── 4-byte emoji mojibake (F0 9F... → U+1Fxxx range) ────────────────────
    # UTF-8 byte F0 maps to ð (U+00F0) in cp1252; the following byte 9F maps to
    # Ÿ (U+0178).  Together "ðŸ" is the canonical prefix for any U+1Fxxx emoji
    # that has been double-encoded.  Examples: 🌙→ðŸŒ™, 📌→ðŸ"Œ, 🔌→ðŸ"Œ
    'ðŸ',  # U+00F0 + U+0178 — 4-byte emoji mojibake prefix
]

_COMBINED = re.compile('|'.join(_MOJIBAKE_PATTERNS))


def _extract_string_literals(source: str) -> list[str]:
    """Return all string literal values from a Python source file."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    literals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.append(node.value)
    return literals


def _scan_file(path: Path) -> list[str]:
    """Return list of mojibake sequences found in string literals of *path*."""
    try:
        # errors='strict', NOT 'replace' — 'replace' would manufacture U+FFFD from
        # invalid bytes, which is exactly what _scan_replacement_chars() looks for.
        source = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return []
    hits = []
    for literal in _extract_string_literals(source):
        for m in _COMBINED.finditer(literal):
            hits.append(f"{path.relative_to(ROOT)}  literal contains: {m.group(0)!r}")
    return hits


# ── Files that are allowed to have mojibake (grandfathered violations) ────────
# Lower this list as files are fixed. Never raise it.
_EXEMPT: set[str] = set()


def test_no_mojibake_in_ui_string_literals():
    """No string literal in ui/**/*.py may contain mojibake sequences."""
    offenders: list[str] = []
    for path in sorted((ROOT / "ui").rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        if rel in _EXEMPT:
            continue
        offenders.extend(_scan_file(path))

    assert not offenders, (
        "Mojibake (double-encoded UTF-8) detected in string literals.\n"
        "This happens when a file is opened in an editor set to Windows-1252\n"
        "encoding and saved — the UTF-8 multi-byte sequences are double-encoded.\n\n"
        "Offending sequences:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n\nFix: run tools/fix_mojibake.py or replace the garbled chars with\n"
        "their correct Unicode equivalents (—, →, ·, ☀, ×, ⚠, etc.)."
    )


def test_no_mojibake_in_modules_string_literals():
    """No string literal in modules/**/*.py may contain mojibake sequences."""
    offenders: list[str] = []
    for path in sorted((ROOT / "modules").rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        if rel in _EXEMPT:
            continue
        offenders.extend(_scan_file(path))

    assert not offenders, (
        "Mojibake detected in modules/ string literals.\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


# ── Lossy mojibake: U+FFFD REPLACEMENT CHARACTER ──────────────────────────────
# The tests above catch *reversible* double-encoding (â€", ðŸ...), where the
# original bytes survive and leave a matchable signature.  They are structurally
# blind to the *lossy* class: once a character has been replaced by U+FFFD the
# original byte is destroyed, so there is no signature left to pattern-match.
#
# That blindness shipped three QPushButton("�") dismiss buttons on the Home
# page for 20 releases (v2.1.13 -> v2.1.33) while this file passed green.  A
# glyph-only, transparent, borderless button whose glyph is U+FFFD has no visual
# affordance at all — and each sat on a setVisible(False) strip, so the UIA chaos
# runs could never reach it either.  See RULE-ENC1.

_REPLACEMENT_CHAR = "�"


def _scan_replacement_chars(path: Path) -> list[str]:
    """Return U+FFFD hits inside *string literals* of *path*.

    Scoped to string literals (not comments) because only literals reach the UI.
    Comment-level U+FFFD is cosmetic source rot — real, but not user-visible, and
    gating on it would block commits on unrelated files.
    """
    try:
        source = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return []
    hits = []
    for literal in _extract_string_literals(source):
        if _REPLACEMENT_CHAR in literal:
            hits.append(f"{path.relative_to(ROOT)}  literal contains U+FFFD: {literal!r}")
    return hits


def test_no_replacement_char_in_ui_string_literals():
    """No string literal in ui/**/*.py may contain U+FFFD (lossy mojibake)."""
    offenders: list[str] = []
    for path in sorted((ROOT / "ui").rglob("*.py")):
        offenders.extend(_scan_replacement_chars(path))

    assert not offenders, (
        "U+FFFD REPLACEMENT CHARACTER found in ui/ string literals.\n\n"
        "This is LOSSY mojibake: the original character was destroyed by an\n"
        "encoding conversion that could not represent it. Unlike the â€\" class,\n"
        "it is NOT recoverable — not from the file, and not from git if the file\n"
        "was committed already corrupted.\n\n"
        "A literal like QPushButton(\"\\ufffd\") renders as a tofu box. When the\n"
        "button is styled via qss_dismiss_button() (transparent, no border), that\n"
        "glyph is its ONLY affordance — the control is effectively unusable.\n\n"
        "Offending literals:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n\nFix: restore the character from in-file convention (look at sibling\n"
        "widgets; RULE-I4 for icon glyphs) and state in-session that the value is\n"
        "an inference, not a recovery. Save UTF-8, no BOM (RULE-ENC3)."
    )


def test_no_replacement_char_in_modules_string_literals():
    """No string literal in modules/**/*.py may contain U+FFFD."""
    offenders: list[str] = []
    for path in sorted((ROOT / "modules").rglob("*.py")):
        offenders.extend(_scan_replacement_chars(path))

    assert not offenders, (
        "U+FFFD REPLACEMENT CHARACTER found in modules/ string literals "
        "(lossy mojibake — see RULE-ENC1).\n"
        + "\n".join(f"  {o}" for o in offenders)
    )
