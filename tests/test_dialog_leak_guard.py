"""test_dialog_leak_guard.py — enforcement guard for RULE-WIN8 (general case).

MECHANISM (why this matters):
A QDialog/QMessageBox constructed with a live-widget parent
(`SomeDialog(..., parent=self)`) is owned by that parent in C++. Calling
`.exec()` directly and letting the local variable go out of scope does NOT
free it — the parent keeps a child pointer, so the whole dialog (its layouts,
cached values, any large text it holds) lives until the parent itself is
destroyed, in practice the app's lifetime. A page whose dialog is opened
repeatedly (a right-click "Edit"/"Compare"/"Add Rule" action) leaks one full
instance per open.

This exact mechanism was first found and fixed for the Ctrl+K command palette
(see test_command_palette_leak.py) but that fix was scoped to the palette's
own toggle-reopen logic. A live repro (dialog_leak_repro.py, 500 opens of a
representative dialog) measured the general cost: ~521 KB retained per
un-cleaned-up dialog instance, RSS flat when `deleteLater()` is called.
A static sweep of `ui/` found ~47 more call sites with the identical shape
across 26 files (Inventory, Automation, Trigger Builder, Home Automation,
Maintenance, CVE, etc.) — all migrated to `ui.dialog_utils.run_dialog()` in
the same session that added this guard.

This is a heuristic, not full data-flow analysis: it flags a bare
`<name>.exec()` call (no arguments — so it does not match `QMenu.exec(pos)`,
which takes a position argument and has a much lighter-weight lifecycle) where
`<name>` is a locally-conventional dialog variable name in this codebase
(every real instance found used one of these). `ui/dialog_utils.py` itself is
exempt — `run_dialog()` legitimately calls `dlg.exec()` once, that is the
implementation the whole codebase now routes through.

CORRECT PATTERN:

    from ui.dialog_utils import run_dialog
    dlg = SomeDialog(..., parent=self)
    if run_dialog(dlg) == QDialog.DialogCode.Accepted:
        ...
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_DIR = ROOT / "ui"

_DIALOG_VAR_NAMES = {"dlg", "box", "msg", "dialog"}
_EXEMPT_FILES = {"dialog_utils.py"}


def find_bare_dialog_exec_calls(root: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name in _EXEMPT_FILES:
            continue
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and not node.args
                and not node.keywords
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "exec"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in _DIALOG_VAR_NAMES
            ):
                continue
            rel = path.relative_to(root.parent)
            violations.append(
                f"{rel}:{node.lineno}: bare `{node.func.value.id}.exec()` call — "
                "route through ui.dialog_utils.run_dialog() so the dialog is "
                "deleteLater()'d instead of leaking as a permanent C++ child "
                "of its parent (RULE-WIN8)."
            )
    return violations


def test_no_bare_dialog_exec_calls_in_ui():
    offenders = find_bare_dialog_exec_calls(UI_DIR)
    assert not offenders, "\n".join(offenders)
