"""Architectural invariant (ARCH RULE 1, item D#13): the module layer is PyQt-free.

`modules/*.py` is pure business logic — no PyQt6 imports. This keeps modules
independently testable without a Qt application and enforces the UI/module
boundary (UI owns QSettings/QWidget; modules own logic + persistence contracts).

Detection is AST-based (walks Import/ImportFrom nodes, top-level OR lazy inside a
function) so a docstring that merely *mentions* "PyQt6" is not a false positive.

Baseline is intentionally EMPTY: as of this sprint, settings_io.py — previously the
only module importing QSettings — was made pure, and a sweep confirmed no other
module imports PyQt6 (availability_monitor.py only references it in prose). Do not
add entries here; fix the offending module instead.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES_ROOT = ROOT / "modules"

# Grandfathered pre-existing violations. Keep this EMPTY — fix new violations.
_GRANDFATHERED: frozenset[str] = frozenset()


def _imports_pyqt(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in ("PyQt6", "PyQt5", "PySide6", "PySide2"):
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in ("PyQt6", "PyQt5", "PySide6", "PySide2"):
                    return True
    return False


def test_modules_are_pyqt_free():
    offenders = []
    for path in sorted(MODULES_ROOT.glob("*.py")):
        if path.name in _GRANDFATHERED:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, SyntaxError, OSError):
            continue
        if _imports_pyqt(tree):
            offenders.append(path.name)
    assert not offenders, (
        "modules/ must be PyQt-free (ARCH RULE 1). These modules import a Qt binding — "
        "move the Qt I/O to the UI caller and thread the plain data through:\n"
        + "\n".join(f"  modules/{f}" for f in offenders)
    )
