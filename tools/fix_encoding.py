"""
Repair mojibake in ui/pages/home_page.py.

Strategy:
 1. Start from HEAD.
 2. One full repair pass (fixes single-corruption).
 3. Direct lookup table for patterns that survive one pass (double/triple corruption).
 4. Strip C1 control chars.
 5. Write result.
"""
import subprocess
import sys

out = sys.stdout.buffer

_CP1252_SPECIAL = {
    0x20AC: 0x80, 0x0081: 0x81, 0x201A: 0x82, 0x0192: 0x83,
    0x201E: 0x84, 0x2026: 0x85, 0x2020: 0x86, 0x2021: 0x87,
    0x02C6: 0x88, 0x2030: 0x89, 0x0160: 0x8A, 0x2039: 0x8B,
    0x0152: 0x8C, 0x008D: 0x8D, 0x017D: 0x8E, 0x008F: 0x8F,
    0x0090: 0x90, 0x2018: 0x91, 0x2019: 0x92, 0x201C: 0x93,
    0x201D: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97,
    0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A, 0x203A: 0x9B,
    0x0153: 0x9C, 0x009D: 0x9D, 0x017E: 0x9E, 0x0178: 0x9F,
}


def _to_cp1252_byte(cp):
    if cp <= 0x7F:
        return cp
    if cp in _CP1252_SPECIAL:
        return _CP1252_SPECIAL[cp]
    if 0xA0 <= cp <= 0xFF:
        return cp
    return None


def repair_one_pass(text):
    buf = bytearray()
    for ch in text:
        cp = ord(ch)
        b = _to_cp1252_byte(cp)
        if b is not None:
            buf.append(b)
        else:
            buf.extend(ch.encode("utf-8"))
    return buf.decode("utf-8", errors="replace")


def _repair_match(s):
    """Apply one repair pass to a short mojibake string."""
    buf = bytearray()
    for ch in s:
        cp = ord(ch)
        b = _to_cp1252_byte(cp)
        if b is not None:
            buf.append(b)
        else:
            buf.extend(ch.encode("utf-8"))
    try:
        return buf.decode("utf-8")
    except UnicodeDecodeError:
        return s  # can't fix, leave as-is


# Patterns still present after one repair pass (double/triple corruption).
# These are exact strings mapped to their correct Unicode equivalents.
_DIRECT_FIXES = {
    # double-encoded x (U+00D7): one pass gives A-tilde + em-dash
    "Ã—": "×",         # Ã + em-dash -> x
    # double-encoded middle-dot
    "Â·": "·",         # Â + middot (though often fixed in one pass)
    # triple-encoded bullet (U+2022): one pass gives a-hat + euro + cent
    "â€¢": "•",   # â€¢ -> bullet
    # triple-encoded em-dash (U+2014) survivors
    "â€”": "—",   # â€" -> em dash
    # triple-encoded gear (U+2699): after one pass becomes âš™
    "âš™": "⚙",   # âš™ -> gear
    # triple-encoded keyboard (U+2328): after one pass becomes âŒ¨
    "âŒ¨": "⌨",   # âŒ¨ -> keyboard
    # triple-encoded right-pointing triangle (U+25B7): one pass -> â–·
    "â–·": "▷",   # â-· -> white triangle
    # triple-encoded black circle (U+25CF): one pass -> â—\x8f (handled by C1 strip)
    # triple-encoded moon emoji (if present)
    "ðŸ’Â\x90": "\U0001f319",  # moon
}


def apply_direct_fixes(text):
    for bad, good in _DIRECT_FIXES.items():
        text = text.replace(bad, good)
    return text


def strip_c1_controls(text):
    return "".join(ch for ch in text if not (0x80 <= ord(ch) <= 0x9F))


def main():
    path = "ui/pages/home_page.py"

    result = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True)
    if result.returncode != 0:
        out.write(b"ERROR: git show failed\n" + result.stderr)
        sys.exit(1)

    head_text = result.stdout.decode("utf-8")
    out.write(f"HEAD: {len(head_text)} chars\n".encode())

    repaired = repair_one_pass(head_text)
    out.write(f"After one pass: {len(repaired)} chars\n".encode())

    repaired = apply_direct_fixes(repaired)
    repaired = strip_c1_controls(repaired)
    out.write(f"After direct fixes + C1 strip: {len(repaired)} chars\n".encode())

    repl = repaired.count("—")
    out.write(f"WRONG - counting em dashes: {repl}\n".encode())
    repl = sum(1 for ch in repaired if ord(ch) == 0xFFFD)
    out.write(f"True replacement chars (U+FFFD): {repl}\n".encode())

    # Verify key chars
    for cp, name in [
        (0x25CF, "black circle"), (0x2014, "em dash"), (0x2192, "arrow"),
        (0x00D7, "times X"), (0x25B6, "play"), (0x2699, "gear"),
        (0x2328, "keyboard"), (0x00B7, "middle dot"),
    ]:
        ch = chr(cp)
        ok = "OK " if ch in repaired else "---"
        out.write(f"  {ok} U+{cp:04X} {name}\n".encode())

    for line in repaired.splitlines():
        if "_mon_dot = QLabel" in line:
            out.write(f"mon_dot: {repr(line.strip())}\n".encode("utf-8"))

    with open(path, "w", encoding="utf-8") as f:
        f.write(repaired)
    out.write(b"\nWrote repaired file.\n")


if __name__ == "__main__":
    main()
