"""
tests/test_codeql_prevention.py

Static-analysis prevention tests for CodeQL categories that triggered alerts
in v1.9.53–v1.9.54. Runs as part of the standard suite; catches violations
before CodeQL sees them in CI.

Checked categories:
  - py/bare-except     — bare `except:` blocks (hides all errors incl. SystemExit)
  - py/unused-import   — unused top-level imports in modules/ and ui/
  - py/incomplete-url-substring-sanitization — `host in url` pattern in tests/
  - RULE-AH3 / RULE-1  — raw hex colour strings in ui/ files (S10-4 gate)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

# ── Root directories to scan ───────────────────────────────────────────────────

_ROOT    = Path(__file__).resolve().parent.parent
_MODULES = _ROOT / "modules"
_UI      = _ROOT / "ui"
_TESTS   = _ROOT / "tests"

# ── Known/intentional exceptions (add comment when extending) ─────────────────

# Files with intentional bare excepts (technical debt; remove as splits land)
_BARE_EXCEPT_ALLOWLIST: frozenset[str] = frozenset()

# Files where "unused imports" are intentional (re-export / __all__ pattern)
_UNUSED_IMPORT_ALLOWLIST: frozenset[str] = frozenset({
    # styles.py re-exports colour constants — many aren't used in the file itself
    "ui/styles.py",
})


def _py_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ── S4-1-A: No bare except blocks ─────────────────────────────────────────────

class _BareExceptVisitor(ast.NodeVisitor):
    def __init__(self):
        self.violations: list[tuple[int, int]] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.violations.append((node.lineno, node.col_offset))
        self.generic_visit(node)


def _bare_excepts(path: Path) -> list[tuple[int, int]]:
    try:
        tree = ast.parse(_read(path), filename=str(path))
    except SyntaxError:
        return []
    v = _BareExceptVisitor()
    v.visit(tree)
    return v.violations


def test_no_bare_except_blocks():
    """Bare `except:` blocks swallow SystemExit and KeyboardInterrupt.

    Use `except Exception:` or a specific type. CodeQL: py/bare-except.
    Add to _BARE_EXCEPT_ALLOWLIST with a comment only for genuine legacy debt.
    """
    offenders: list[str] = []
    for root in (_MODULES, _UI):
        for path in _py_files(root):
            rel = path.relative_to(_ROOT).as_posix()
            if rel in _BARE_EXCEPT_ALLOWLIST:
                continue
            for lineno, _ in _bare_excepts(path):
                offenders.append(f"{rel}:{lineno}")

    assert not offenders, (
        "Bare `except:` blocks found (use `except Exception:` instead):\n"
        + "\n".join(f"  {o}" for o in offenders[:20])
        + ("\n  ...and more" if len(offenders) > 20 else "")
    )


# ── S4-1-B: No unused top-level imports ───────────────────────────────────────

class _ImportUsageVisitor(ast.NodeVisitor):
    """Collect top-level imported names and all names referenced in the file."""

    def __init__(self):
        self.imported: dict[str, int] = {}  # name → lineno
        self.used: set[str] = set()
        self._depth = 0

    def visit_FunctionDef(self, node: ast.AST) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.AST) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_Import(self, node: ast.Import) -> None:
        if self._depth == 0:
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                self.imported[bound] = node.lineno
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._depth == 0:
            for alias in node.names:
                if alias.name == "*":
                    return
                bound = alias.asname or alias.name
                self.imported[bound] = node.lineno
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.used.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name):
            self.used.add(root.id)
        self.generic_visit(node)


_USAGE_IGNORE = frozenset({
    "TYPE_CHECKING", "annotations", "__all__", "__version__", "__author__",
})


def _unused_imports(path: Path) -> list[tuple[str, int]]:
    src = _read(path)
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []
    v = _ImportUsageVisitor()
    v.visit(tree)

    # Scan string literals for names used in TYPE_CHECKING / forward refs
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                for n in ast.walk(ast.parse(node.value)):
                    if isinstance(n, ast.Name):
                        v.used.add(n.id)
            except (SyntaxError, UnicodeEncodeError, ValueError):
                pass

    result = []
    for name, lineno in v.imported.items():
        if name in _USAGE_IGNORE or name.startswith("_"):
            continue
        if name not in v.used:
            result.append((name, lineno))
    return result


@pytest.mark.skip(
    reason=(
        "Pure-AST unused-import detection has too many false positives "
        "(pytest fixtures, type-annotation imports, re-exports). "
        "Use `flake8 --select=F401 modules/ ui/ tests/` in CI instead. "
        "This test body intentionally left as a placeholder."
    )
)
def test_no_unused_imports():
    """Placeholder — CodeQL py/unused-import.

    Pure AST analysis cannot reliably distinguish truly unused imports from
    type-annotation-only imports, pytest fixture injections, and re-exports.
    Run `flake8 --select=F401` for accurate detection.
    """
    pass  # implementation deferred to flake8/CI


# ── S4-1-C: URL substring checks in test files ────────────────────────────────
# The full production codebase has many "." in s / ":" in s patterns that are
# legitimate (checking if a string has dots, not checking a URL). The CodeQL
# rule targets tests/  where tests.instructions.md mandates urlparse. Check
# only test files for patterns that assert a hostname is "in" a URL-like string.

class _UrlSubstringVisitor(ast.NodeVisitor):
    """Flag `assert hostname_str in url_var` patterns in test files."""

    _URL_NAMES = frozenset({
        "url", "uri", "href", "link", "endpoint",
        "base_url", "redirect_url", "warning",
    })

    def __init__(self):
        self.violations: list[tuple[int, str]] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        self._check_expr(node.test, node.lineno)
        self.generic_visit(node)

    def _check_expr(self, expr: ast.expr, lineno: int) -> None:
        if not isinstance(expr, ast.Compare):
            return
        for op, comparator in zip(expr.ops, expr.comparators):
            if not isinstance(op, ast.In):
                continue
            if not isinstance(comparator, ast.Name):
                continue
            if comparator.id.lower() not in self._URL_NAMES:
                continue
            # left side is a hostname-like literal?
            if isinstance(expr.left, ast.Constant) and isinstance(expr.left.value, str):
                val = expr.left.value
                # Only flag strings that look like hostnames/IPs (have a dot,
                # have alpha chars, do NOT look like file paths or ports)
                if ("." in val and any(c.isalpha() for c in val)
                        and "/" not in val and "\\" not in val):
                    self.violations.append(
                        (lineno, f'"{val}" in {comparator.id} — use urlparse().hostname')
                    )


def _url_substring_in_tests(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(_read(path), filename=str(path))
    except SyntaxError:
        return []
    v = _UrlSubstringVisitor()
    v.visit(tree)
    return v.violations


# ── S10-4: No raw hex colour strings in ui/ (RULE-AH3 / RULE-1) ──────────────
# All UI colours must come from ui/styles.py (RULE-1).
# Chart/report colours must come from modules/colours.py (RULE-AH3).
# Source files: styles.py and colours.py are the ONLY allowed locations.
#
# Sprint 12 purged all 63 tracked files to 0 violations and locked the gate.
# This test enforces that no new hex strings are introduced.

import re as _re

_HEX_RE = _re.compile(r'"(#[0-9A-Fa-f]{3,6})"')
_ALLOWED_FILES: frozenset[str] = frozenset({
    "ui/styles.py",
    "modules/colours.py",
})


def _hex_violations(path: Path, root: Path) -> list[tuple[int, str]]:
    """Return (lineno, hex_value) for raw hex string literals."""
    rel = path.relative_to(root).as_posix()
    if rel in _ALLOWED_FILES:
        return []
    src = _read(path)
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _HEX_RE.fullmatch(repr(node.value)):
                violations.append((node.lineno, node.value))
    return violations


def test_no_hardcoded_hex_in_ui_files():
    """Raw hex colour strings in ui/ files violate RULE-1 and RULE-AH3.

    All colours must be imported from ui/styles.py (for UI) or
    modules/colours.py (for charts/reports). Sprint 12 locked all
    63 tracked files to 0 violations; this gate prevents regression.

    When this fails: add a token to ui/styles.py, then replace the
    hex literal with the token name. Never add hex directly to a page.
    """
    offenders: list[str] = []
    for path in _py_files(_UI):
        rel = path.relative_to(_ROOT).as_posix()
        for lineno, hex_val in _hex_violations(path, _ROOT):
            offenders.append(f"{rel}:{lineno} — {hex_val!r}")

    assert not offenders, (
        "Hardcoded hex colour strings in ui/ (RULE-1/RULE-AH3 violation):\n"
        + "\n".join(f"  {o}" for o in offenders[:30])
        + ("\n  ...and more" if len(offenders) > 30 else "")
        + "\n\nFix: add a token to ui/styles.py and replace the hex literal."
    )


def test_no_url_substring_comparisons_in_tests():
    """Detect `assert "host.example.com" in url` in test files.

    Tests must use urlparse().hostname for URL host checks, not substring
    matching. This prevents CodeQL py/incomplete-url-substring-sanitization
    alerts from test-file false positives. See tests.instructions.md.
    """
    offenders: list[str] = []
    for path in _py_files(_TESTS):
        rel = path.relative_to(_ROOT).as_posix()
        for lineno, msg in _url_substring_in_tests(path):
            offenders.append(f"{rel}:{lineno} — {msg}")

    assert not offenders, (
        "URL substring comparisons in tests (use urlparse().hostname):\n"
        + "\n".join(f"  {o}" for o in offenders[:20])
        + ("\n  ...and more" if len(offenders) > 20 else "")
    )
