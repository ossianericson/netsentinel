"""Every ``ToastManager`` attribute a call site names must exist (RULE-SURF1 corollary, S6.0).

A misspelled toast method is invisible until it runs, and a confirmation toast usually runs
inside the ``try`` that guards the work — so the ``AttributeError`` is caught as a failure of
the work. Four sites called ``ToastManager.instance().show_toast(...)``, which never existed:
a successful Export All Data and two clipboard copies each showed a "failed" modal, and a
successful Network Map PNG save showed nothing.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_ROOTS = ("ui", "modules", "workers")
_ENTRY_POINTS = ("app.py", "cli.py", "svc.py")


def _production_files():
    for root in _ROOTS:
        yield from sorted((REPO / root).rglob("*.py"))
    for name in _ENTRY_POINTS:
        yield REPO / name


def _named_toast_attributes():
    """(path, line, attr) for ``ToastManager.X`` and ``ToastManager.instance().X``."""
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            base = node.value
            if isinstance(base, ast.Call) and isinstance(base.func, ast.Attribute):
                if base.func.attr == "instance" and ast.unparse(base.func.value) == "ToastManager":
                    yield path.relative_to(REPO).as_posix(), node.lineno, node.attr, "instance"
            elif isinstance(base, ast.Name) and base.id == "ToastManager":
                yield path.relative_to(REPO).as_posix(), node.lineno, node.attr, "class"


def test_the_scan_finds_the_real_call_sites():
    names = {attr for _p, _l, attr, _k in _named_toast_attributes()}
    assert {"show", "instance"} <= names, "the AST scan no longer recognises ToastManager calls"


def test_every_toast_attribute_a_call_site_names_exists():
    from ui.widgets.toast import ToastManager

    missing = [
        f"{path}:{line} ToastManager{'.instance()' if kind == 'instance' else ''}.{attr}"
        for path, line, attr, kind in _named_toast_attributes()
        if not hasattr(ToastManager, attr)
    ]
    assert not missing, (
        "These call sites name a ToastManager attribute that does not exist. Inside a try, the "
        "AttributeError reports the finished work as FAILED. Use ToastManager.show(message, kind), "
        "and put the confirmation in the try's else: branch:\n  " + "\n  ".join(missing)
    )
