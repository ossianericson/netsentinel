"""Keyboard navigation audit tests (UX Sprint 10, S10-3).

Verifies that the main navigation widgets have visible focus indicators,
that no page widget block-intercepts Tab unnecessarily, and that tables
that intentionally drop keyboard focus have a documented reason.
"""
from __future__ import annotations

import ast
from pathlib import Path

# ── Focus-ring presence in nav rail ──────────────────────────────────────────

def test_rail_button_has_focus_style():
    src = Path("ui/nav/rail.py").read_text(encoding="utf-8")
    assert "QPushButton:focus" in src, (
        "_RailButton must have a :focus style so keyboard users can see focus"
    )


def test_flyout_item_has_focus_style():
    src = Path("ui/nav/rail.py").read_text(encoding="utf-8")
    count = src.count("QPushButton:focus")
    assert count >= 2, (
        "Both _RailButton and _FlyoutItem must include a QPushButton:focus rule; "
        f"found {count} occurrence(s)"
    )


# ── NoFocus audit — every instance must be intentional ────────────────────────

# These are the known, intentional NoFocus usages with documented reasons:
_ALLOWED_NOFOCUS: dict[str, str] = {
    "ui/command_palette.py":      "list view has custom keyboard handling via the search field",
    "ui/header.py":               "window chrome buttons (min/max/close) are not part of tab order",
    "ui/help_tab.py":             "reference table is read-only; keyboard not needed",
    "ui/pages/ip_calculator_page.py": "output-only result tables; no interactive cells",
}


def test_no_undocumented_nofocus():
    """Any new NoFocus call must be added to _ALLOWED_NOFOCUS with a reason."""
    offenders = []
    for py_file in sorted(Path("ui").rglob("*.py")):
        src = py_file.read_text(encoding="utf-8")
        if "NoFocus" not in src:
            continue
        rel = py_file.as_posix()
        if rel not in _ALLOWED_NOFOCUS:
            offenders.append(rel)
    assert not offenders, (
        f"Undocumented NoFocus in: {offenders}\n"
        "Add an entry to _ALLOWED_NOFOCUS in test_keyboard_nav.py with a reason."
    )


# ── QPushButton subclasses inherit StrongFocus by default ────────────────────

def _classes_inheriting_qpushbutton(path: Path) -> list[str]:
    """Return class names that directly inherit QPushButton in a source file."""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                if name == "QPushButton":
                    result.append(node.name)
    return result


def test_rail_and_flyout_inherit_qpushbutton():
    classes = _classes_inheriting_qpushbutton(Path("ui/nav/rail.py"))
    assert "_RailButton" in classes
    assert "_FlyoutItem" in classes
