"""
Static analysis: every inline QPushButton stylesheet that declares a
`color:` in its base (non-pseudo-state) rule MUST also declare an explicit
`QPushButton:pressed` rule containing a `color:` declaration.

WHY: In Qt, a widget's own setStyleSheet() overrides the application-level
stylesheet — including the global `QPushButton:pressed` fallback.  When an
inline stylesheet covers the base state but NOT :pressed, Qt falls back to
the local base rule for the pressed state.  If that base rule sets
`color:{WHITE}` (which equals BG_CARD in the Arctic Clean theme), pressing
the button renders white text on a white/transparent background — invisible.

This test requires NO QApplication — it is pure source-text analysis.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Locate all Python source files under ui/
# ---------------------------------------------------------------------------
_UI_ROOT = Path(__file__).parent.parent / "ui"


def _ui_py_files() -> list[Path]:
    return sorted(_UI_ROOT.rglob("*.py"))


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# Matches a QPushButton base rule that contains a color: declaration.
# Intentionally lenient — captures the rule body to let us inspect it.
_BASE_RULE_WITH_COLOR = re.compile(
    r'QPushButton\s*\{[^}]*color\s*:[^}]+\}',
    re.DOTALL,
)

# Matches a :pressed pseudo-state rule that contains a color: declaration.
_PRESSED_RULE_WITH_COLOR = re.compile(
    r'QPushButton\s*:pressed\s*\{[^}]*color\s*:[^}]+\}',
    re.DOTALL,
)

# Matches a :pressed pseudo-state rule (with or without color).
_PRESSED_RULE_ANY = re.compile(
    r'QPushButton\s*:pressed\s*\{',
    re.DOTALL,
)


def _extract_setStyleSheet_strings(source: str) -> list[tuple[int, str]]:
    """
    Return (line_number, concatenated_string_value) for every
    setStyleSheet(...) call in the source.  Only covers f-string and plain
    string literals — sufficient for this codebase.
    """
    results: list[tuple[int, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return results

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "setStyleSheet"):
            continue

        # Collect raw text from all string literal arguments
        parts: list[str] = []
        for arg in node.args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    parts.append(sub.value)
        if parts:
            results.append((node.lineno, " ".join(parts)))

    return results


# ---------------------------------------------------------------------------
# Violation detector
# ---------------------------------------------------------------------------

def _find_violations(path: Path) -> list[str]:
    """
    Return a list of human-readable violation strings found in *path*.
    An empty list means the file is clean.
    """
    source = path.read_text(encoding="utf-8", errors="replace")
    violations: list[str] = []

    for lineno, ss_text in _extract_setStyleSheet_strings(source):
        # Does this inline stylesheet contain a QPushButton base rule with color?
        if not _BASE_RULE_WITH_COLOR.search(ss_text):
            continue  # No QPushButton base rule with color — nothing to check

        # It has a colored base rule.  Does it also have a :pressed rule
        # that explicitly sets color?
        if not _PRESSED_RULE_WITH_COLOR.search(ss_text):
            violations.append(
                f"  {path.relative_to(path.parent.parent)}:{lineno} — "
                f"QPushButton inline stylesheet sets color in base rule "
                f"but has no QPushButton:pressed rule with color "
                f"(RULE-AX1 violation)"
            )

    return violations


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestInlineButtonInteractiveStates:
    @pytest.mark.parametrize("ui_path", _ui_py_files(), ids=lambda p: p.name)
    def test_pressed_state_declared_when_base_has_color(self, ui_path: Path):
        """
        Every QPushButton inline stylesheet with a base color: declaration
        must also have an explicit :pressed rule with color:.
        """
        violations = _find_violations(ui_path)
        assert not violations, (
            f"RULE-AX1 violations in {ui_path.name}:\n"
            + "\n".join(violations)
            + "\n\nFix: add a QPushButton:pressed rule with explicit "
            "background-color and color using theme tokens from ui/styles.py."
        )
