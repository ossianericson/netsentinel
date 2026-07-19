"""test_startup_repaint_guard.py — enforcement guard for RULE-STARTUP2.

MECHANISM (why this matters):
Any `QApplication.setStyleSheet()` call forces Qt to recursively re-polish every
top-level widget in the process — including a `QSplashScreen`, which is a bare
QWidget and therefore matches selector-less rules like `MAIN_STYLE`'s opening
`QWidget { background-color: ... }`. The re-polish queues a repaint that Qt does
not flush immediately; it is flushed by whatever `processEvents()` call happens
to run next. If that next flush lands after the main window has already been
revealed (e.g. the `processEvents()` inside `_splash_msg()` in `app.py`, which
runs after `showMaximized()`), the stale queued frame paints over the now-visible
window as a visible flash.

`ui/styles.py::_suspend_repaints()` disables `setUpdatesEnabled()` on every
top-level widget for the duration of the `with` block, which prevents the queued
repaint from landing regardless of what the stylesheet actually contains — cheap,
content-agnostic protection. RULE-STARTUP2 requires every app-level
`setStyleSheet()` call in `ui/` and `app.py` to be wrapped in it, universally
(no "this one's content is harmless" exceptions — a future edit could add a
matching selector to a QSS string that is safe today).

CORRECT PATTERN:
    with _suspend_repaints():
        QApplication.instance().setStyleSheet(...)

This is an AST-based structural scan, not a regex — the invariant is "the call is
a lexical descendant of a `with _suspend_repaints():` block", which needs real
scope tracking (`with` nesting) to check correctly.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_DIR = ROOT / "ui"
APP_PY = ROOT / "app.py"


def _is_qapp_instance_call(node: ast.AST) -> bool:
    """True for `<something>.instance()` where <something>'s name mentions QApplication
    (covers `QApplication.instance()` and aliased imports like `_QApp_init.instance()`)."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "instance"):
        return False
    base = node.func.value
    name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
    return "QApp" in name


def _is_qapp_constructor_call(node: ast.AST) -> bool:
    """True for `QApplication(...)` — the one-time construction in app.py's main()."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    return name == "QApplication"


def _is_suspend_repaints_ctx(item: ast.withitem) -> bool:
    expr = item.context_expr
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    return name == "_suspend_repaints"


class _Guard(ast.NodeVisitor):
    def __init__(self) -> None:
        self.app_vars: set[str] = set()
        self.suspend_depth = 0
        self.violations: list[int] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        if _is_qapp_instance_call(node.value) or _is_qapp_constructor_call(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self.app_vars.add(t.id)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        entering = any(_is_suspend_repaints_ctx(item) for item in node.items)
        if entering:
            self.suspend_depth += 1
        self.generic_visit(node)
        if entering:
            self.suspend_depth -= 1

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "setStyleSheet":
            recv = node.func.value
            targets_app = _is_qapp_instance_call(recv) or (
                isinstance(recv, ast.Name) and recv.id in self.app_vars
            )
            if targets_app and self.suspend_depth == 0:
                self.violations.append(node.lineno)
        self.generic_visit(node)


def _scan(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    guard = _Guard()
    guard.visit(tree)
    return guard.violations


def test_qapplication_setstylesheet_always_suspends_repaints():
    offenders: list[str] = []
    paths = sorted(UI_DIR.rglob("*.py")) + [APP_PY]
    for path in paths:
        for lineno in _scan(path):
            rel = path.relative_to(ROOT).as_posix()
            offenders.append(f"{rel}:{lineno}")

    assert not offenders, (
        "QApplication.setStyleSheet() call not wrapped in `with _suspend_repaints():` "
        "(RULE-STARTUP2) — an app-level stylesheet re-polishes every top-level widget, "
        "including a visible QSplashScreen, and the queued repaint can flush after the "
        "main window is already shown, producing a startup flash. Wrap the call in "
        "`_suspend_repaints()` (ui/styles.py). Offenders:\n  " + "\n  ".join(offenders)
    )
