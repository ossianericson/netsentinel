"""
CI gate: detect mojibake (double-encoded UTF-8) in Python source files.

Mojibake happens when a UTF-8 source file is opened in a Latin-1 / Windows-1252
editor that misreads multi-byte sequences as individual characters and saves them
back as UTF-8.  The result: characters like —, →, ·, ☀, ×, ⚠ are replaced by
sequences of Latin supplement and Windows-1252 code points.

Canonical signatures (all three must appear together to flag a sequence):
  • U+00C3 (Ã) or U+00E2 (â) followed immediately by a Windows-1252 code point
    in the range 0x80–0x9F (mapped to special chars like €, ‚, ƒ, „, …, †, ‡,
    ˆ, ‰, Š, ‹, Œ, Ž, ', ', ", ", •, –, —, ˜, ™, š, ›, œ, ž, Ÿ).
  • OR: Latin capital with tilde/ring (Ã) followed by Latin-1 byte values
    (°, ², ³, ¶, ·, ¸, ¹, º, etc.).

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
    r'Ã[ƒ†‡ˆ‰Š‹ŒŽ''""•–—˜™š›œžŸ]',  # Ã + Windows-1252 specials
    # Common close-button mojibake: Ã + ƒ (triple-encoded ×)
    r'Ãƒ',
    # ── Sequences starting with Å (U+00C5) ──────────────────────────────────
    r'Å[¸\x92]',                  # Å¸ or Å + RIGHT SINGLE QUOTE
    r'Å[''""•–—˜™š›œžŸ]',
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
        source = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
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
