"""
Static analysis: every style token referenced in ui/pages/*.py must be imported.

How it works:
  1. Load all public names exported by ui.styles (the canonical token set).
  2. For each page file, find which style tokens it imports from ui.styles.
  3. Scan the source for bare {TOKEN} references in f-strings and format calls.
  4. Fail if any used token was never imported.

This catches the "NameError: name 'TABLE_SEL' is not defined" class of bug
before it reaches a user — the kind that passes the smoke test because it only
triggers when a widget is constructed at runtime.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Discover the canonical set of style token names
# ---------------------------------------------------------------------------
_STYLES_PATH = Path(__file__).parent.parent / "ui" / "styles.py"
_PAGES_DIR   = Path(__file__).parent.parent / "ui" / "pages"

# All uppercase names in ui/styles that pages might import
_STYLES_SRC = _STYLES_PATH.read_text(encoding="utf-8")
_ALL_TOKENS: set[str] = set(
    re.findall(r'^([A-Z][A-Z0-9_]{2,})\s*[:=]', _STYLES_SRC, re.MULTILINE)
)
# Add names that appear as dict keys in palettes (e.g. "TABLE_SEL")
_ALL_TOKENS |= set(re.findall(r'"([A-Z][A-Z0-9_]{2,})"', _STYLES_SRC))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _imported_tokens(source: str) -> set[str]:
    """Return all names imported from ui.styles in this source file."""
    imported: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return imported
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        # Match: from ui.styles import ...  OR  import ui.styles as _styles
        if node.module in ("ui.styles", "ui.styles as _styles"):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
    return imported


def _referenced_tokens(source: str) -> set[str]:
    """
    Return all UPPER_CASE identifiers that appear as {NAME} inside
    f-string expressions or format()-style placeholders.

    We match:
      {IDENTIFIER}   — inside any string in the file
      {IDENTIFIER:   — with format spec
    """
    # Regex: opening brace, then an uppercase identifier (no dots / calls)
    return set(re.findall(r'\{([A-Z][A-Z0-9_]{2,})(?:[}:!])', source))


def _page_files() -> list[Path]:
    return sorted(_PAGES_DIR.glob("*.py"))


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestStyleTokenImports:
    @pytest.mark.parametrize("page_path", _page_files(), ids=lambda p: p.name)
    def test_all_used_tokens_are_imported(self, page_path: Path):
        source = page_path.read_text(encoding="utf-8")

        imported  = _imported_tokens(source)
        referenced = _referenced_tokens(source) & _ALL_TOKENS  # only style tokens

        # Tokens used in this file but never imported from ui.styles
        missing = referenced - imported

        # Allow tokens that are accessed via the _styles module alias
        # e.g. _styles.get_active_theme_name() — these aren't imported directly
        if "import ui.styles as _styles" in source or "import ui.styles" in source:
            pass  # module-level access is fine alongside direct imports

        assert not missing, (
            f"{page_path.name} uses style token(s) without importing them: "
            f"{sorted(missing)}\n"
            f"Add to the 'from ui.styles import (...)' block."
        )
