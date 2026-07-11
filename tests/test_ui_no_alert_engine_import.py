"""Architectural invariant (ARCH RULE 1, item #22): the UI layer must not import
from modules/alert_engine.py.

`modules.alert_engine` drags in the whole alert engine (all _AlertChecksMixin*,
MetricStore, routing). The only two symbols the UI actually needs from it —
`AlertFired` and `rule_settings_key` — are re-exports; they are DEFINED in
PyQt-free leaf modules:
  - `AlertFired`        → modules/alert_types.py      (pure dataclasses)
  - `rule_settings_key` → modules/alert_suppressor.py (dataclasses + alert_types only)

Import those directly. This test AST-walks every ui/**/*.py and fails on any
`import modules.alert_engine` / `from modules.alert_engine import ...` — top-level
OR lazy inside a function/method.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"

_FORBIDDEN = "modules.alert_engine"


def _imports_alert_engine(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == _FORBIDDEN:
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _FORBIDDEN:
                    return True
    return False


def test_ui_does_not_import_alert_engine():
    offenders = []
    for path in UI_ROOT.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, SyntaxError, OSError):
            continue
        if _imports_alert_engine(tree):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "ui/ files import from modules.alert_engine (ARCH RULE 1 layer violation).\n"
        "Repoint to the PyQt-free source modules:\n"
        "  AlertFired        -> from modules.alert_types import AlertFired\n"
        "  rule_settings_key -> from modules.alert_suppressor import rule_settings_key\n"
        + "\n".join(f"  {f}" for f in offenders)
    )
