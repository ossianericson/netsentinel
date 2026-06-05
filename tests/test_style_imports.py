"""
WIRING-3A: AST-based enforcement that every dynamic style constant used as a
bare name in any ui/**/*.py file is explicitly imported from ui.styles.

Background
----------
ui/styles.py injects all per-theme colour constants into its own module globals
via ``globals().update(THEMES[_ACTIVE_THEME])`` at import time.  Static
analysers cannot see these names — only runtime can.  If a UI file writes
``f"color:{AMBER_BG}"`` but never imports ``AMBER_BG``, Python raises
``NameError`` the first time that code path runs (often only on a specific page
navigation, not at startup).

This test:
1. Collects the dynamic constant names from all four theme dicts in styles.py.
2. For every ui/**/*.py file (excluding styles.py itself):
   a. Walks the AST to find all names imported from ui.styles.
   b. Walks the AST to find all bare Name nodes that match a dynamic constant,
      excluding import statement lines.
   c. Fails if any such bare name is not in the imported set — unless the file
      does a module-level ``import ui.styles`` (in which case all names are
      accessible via attribute access and no per-name import is needed).

Coverage scope: all of ui/**/*.py — not just ui/pages/*.py.
Complements test_style_token_imports.py which does a regex-based check
limited to ui/pages/*.py f-string templates.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Derive the dynamic constant names from the theme dicts in styles.py
# ---------------------------------------------------------------------------
_STYLES_PATH = Path(__file__).parent.parent / "ui" / "styles.py"
_UI_ROOT = Path(__file__).parent.parent / "ui"

_styles_src = _STYLES_PATH.read_text(encoding="utf-8")

# Extract keys from all _*_CLEAN / _DARK_PRO / _OBSIDIAN_NEON / _ABYSS dicts.
# These are the names injected by globals().update() — invisible to static analysis.
_DYNAMIC_CONSTANTS: frozenset[str] = frozenset(
    re.findall(r'"([A-Z][A-Z0-9_]{2,})":', _styles_src)
)

assert len(_DYNAMIC_CONSTANTS) >= 30, (
    f"Only {len(_DYNAMIC_CONSTANTS)} dynamic constants found — "
    "regex may have broken; check ui/styles.py theme dict format"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_import_lines(tree: ast.Module) -> set[int]:
    """Return the set of line numbers occupied by import statements."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for ln in range(node.lineno, node.end_lineno + 1):
                lines.add(ln)
    return lines


def _styles_imported_names(tree: ast.Module) -> set[str]:
    """Return names explicitly imported from ui.styles in this module."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module in ("ui.styles",):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _has_module_import(tree: ast.Module) -> bool:
    """Return True if the module does ``import ui.styles`` (any form)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("ui.styles"):
                    return True
        if isinstance(node, ast.ImportFrom):
            if node.module == "ui.styles" and any(
                a.name == "*" for a in node.names
            ):
                return True
    return False


def _bare_name_uses(tree: ast.Module, import_lines: set[int]) -> dict[str, list[int]]:
    """
    Return mapping of dynamic-constant-name → [line numbers] where the name
    appears as a bare Name node outside of import statements.
    """
    uses: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name):
            continue
        if node.id not in _DYNAMIC_CONSTANTS:
            continue
        if node.lineno in import_lines:
            continue
        uses.setdefault(node.id, []).append(node.lineno)
    return uses


def _ui_files() -> list[Path]:
    return sorted(
        p for p in _UI_ROOT.rglob("*.py") if p.name != "styles.py"
    )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestStyleImports:
    @pytest.mark.parametrize("ui_path", _ui_files(), ids=lambda p: str(p.relative_to(_UI_ROOT.parent)))
    def test_dynamic_constants_are_imported(self, ui_path: Path):
        source = ui_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            pytest.skip(f"SyntaxError in {ui_path.name}: {exc}")
            return

        # If the file imports the entire module, all names are accessible.
        if _has_module_import(tree):
            return

        import_lines = _collect_import_lines(tree)
        imported = _styles_imported_names(tree)
        uses = _bare_name_uses(tree, import_lines)

        missing = {name: lines for name, lines in uses.items() if name not in imported}

        assert not missing, (
            f"{ui_path.relative_to(_UI_ROOT.parent)} uses dynamic style "
            f"constant(s) without importing them from ui.styles:\n"
            + "\n".join(
                f"  {name!r} at lines {lines} — add to 'from ui.styles import (...)'"
                for name, lines in sorted(missing.items())
            )
        )
