"""
fix_ax1.py — Batch fixer for RULE-AX1 violations.

Finds every inline QPushButton setStyleSheet() that has `color:` in its
base rule but no `QPushButton:pressed` rule with `color:`, and injects an
appropriate pressed rule at the end of the stylesheet string.

Usage:
    python tools/fix_ax1.py [--dry-run]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

UI_ROOT = Path(__file__).parent.parent / "ui"

# ── Same patterns as the test ────────────────────────────────────────────────
_BASE_RULE_WITH_COLOR    = re.compile(r'QPushButton\s*\{[^}]*color\s*:[^}]+\}', re.DOTALL)
_PRESSED_RULE_WITH_COLOR = re.compile(r'QPushButton\s*:pressed\s*\{[^}]*color\s*:[^}]+\}', re.DOTALL)

# Detect color and background tokens — \}? captures the closing brace of {TOKEN} forms
_COLOR_IN_BASE = re.compile(
    r'QPushButton\s*\{[^}]*?\bcolor\s*:\s*([^;}\s,]+\}?)', re.DOTALL
)
_BG_IN_BASE = re.compile(
    r'QPushButton\s*\{[^}]*?background(?:-color)?\s*:\s*([^;}\s,]+\}?)', re.DOTALL
)

_WHITE_TOKENS = frozenset({
    '#fff', '#FFF', '#ffffff', '#FFFFFF', '{WHITE}', '{white}', 'white',
})

# Lines previously inserted by a broken version of this fixer — remove them
_BAD_INSERTION_RE = re.compile(r'^\s*["\']QPushButton:pressed \{\{')


def _build_pressed_rule(source_snippet: str) -> str:
    """
    Return a Python source snippet (an f-string literal) for the :pressed rule
    to inject into the setStyleSheet call.  The returned string, when written to
    a .py file, must be a valid Python f-string that passes the AST analysis in
    test_interactive_states.py.
    """
    color_m = _COLOR_IN_BASE.search(source_snippet)
    bg_m    = _BG_IN_BASE.search(source_snippet)

    color_tok = color_m.group(1).strip() if color_m else '{TEXT_PRIMARY}'
    bg_tok    = bg_m.group(1).strip()    if bg_m    else 'transparent'

    def _var(tok: str) -> str:
        """Extract Python variable name from {TOKEN}, or fall back to TEXT_PRIMARY."""
        if tok.startswith('{') and tok.endswith('}'):
            return tok[1:-1]
        return 'TEXT_PRIMARY'

    if color_tok in _WHITE_TOKENS:
        # White text on a coloured background — use ACCENT_DARK for pressed bg.
        # Returns an f-string source snippet:
        #   f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        return 'f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"'

    elif bg_tok in ('transparent', 'transparent;'):
        # Flat / link-style button — tint bg slightly.
        cv = _var(color_tok)
        # Returns e.g.: f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        return f'f"QPushButton:pressed {{{{ background:{{BG_HOVER}}; color:{{{cv}}}; }}}}"'

    else:
        # Generic: keep same text colour.
        cv = _var(color_tok)
        # Returns e.g.: f"QPushButton:pressed {{ color:{ACCENT}; }}"
        return f'f"QPushButton:pressed {{{{ color:{{{cv}}}; }}}}"'


def _find_violations(path: Path) -> list[int]:
    """Return sorted list of line numbers (1-based) of violating setStyleSheet calls."""
    source = path.read_text(encoding='utf-8', errors='replace')
    results: list[int] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return results
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == 'setStyleSheet'):
            continue
        parts: list[str] = []
        for arg in node.args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    parts.append(sub.value)
        joined = ' '.join(parts)
        if _BASE_RULE_WITH_COLOR.search(joined) and not _PRESSED_RULE_WITH_COLOR.search(joined):
            results.append(node.lineno)
    return sorted(set(results))


def _fix_file(path: Path, dry_run: bool = False) -> int:
    """
    Patch all RULE-AX1 violations in *path*.  Returns number of fixes applied.
    """
    source = path.read_text(encoding='utf-8')
    lines  = source.splitlines(keepends=True)

    # Remove previously-inserted bad plain-string pressed rules
    lines = [ln for ln in lines if not _BAD_INSERTION_RE.match(ln)]

    # Re-detect violations on the cleaned source
    clean_source = ''.join(lines)
    violation_lines: list[int] = []
    try:
        tree = ast.parse(clean_source)
    except SyntaxError:
        return 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == 'setStyleSheet'):
            continue
        parts: list[str] = []
        for arg in node.args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    parts.append(sub.value)
        joined = ' '.join(parts)
        if _BASE_RULE_WITH_COLOR.search(joined) and not _PRESSED_RULE_WITH_COLOR.search(joined):
            violation_lines.append(node.lineno)

    violation_lines = sorted(set(violation_lines))
    if not violation_lines:
        if not dry_run:
            path.write_text(clean_source, encoding='utf-8')
        return 0

    total  = len(lines)
    patches: list[tuple[int, str, str]] = []

    for vline in violation_lines:
        idx = vline - 1
        if idx >= total:
            continue

        depth = 0
        call_lines: list[str] = []
        end_idx = idx
        for i in range(idx, min(idx + 60, total)):
            ln = lines[i]
            call_lines.append(ln)
            depth += ln.count('(') - ln.count(')')
            if depth <= 0:
                end_idx = i
                break

        call_text = ''.join(call_lines)

        if _PRESSED_RULE_WITH_COLOR.search(call_text):
            continue

        pressed_rule = _build_pressed_rule(call_text)
        patches.append((end_idx, pressed_rule, call_text))

    if not patches:
        if not dry_run:
            path.write_text(clean_source, encoding='utf-8')
        return 0

    new_lines = list(lines)
    applied = 0
    for end_idx, pressed_rule, _call_text in reversed(patches):
        closing_line = new_lines[end_idx]
        indent = len(closing_line) - len(closing_line.lstrip())
        spaces = ' ' * (indent + 4)
        new_rule_line = f'{spaces}{pressed_rule}\n'
        new_lines.insert(end_idx, new_rule_line)
        applied += 1

    if not dry_run:
        path.write_text(''.join(new_lines), encoding='utf-8')
    return applied


def main():
    dry_run = '--dry-run' in sys.argv
    total_fixed = 0
    for py_file in sorted(UI_ROOT.rglob('*.py')):
        n = _fix_file(py_file, dry_run=dry_run)
        if n:
            label = 'dry-run' if dry_run else 'fixed'
            print(f'  {label} {n:2d} violation(s)  {py_file.relative_to(py_file.parent.parent.parent)}')
            total_fixed += n
    print(f'\nTotal: {total_fixed} violations {"(dry-run)" if dry_run else "fixed"}')


if __name__ == '__main__':
    main()
