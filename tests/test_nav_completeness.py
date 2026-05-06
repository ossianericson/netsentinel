"""
test_nav_completeness.py

RULE-NAV1/NAV2 compliance tests.

There is one nav builder: _build_pro_nav(). New pages are registered there via
_nav_add_rail_item() — that is the only registration needed. _build_tabs() /
_nav_add_page() is legacy dead code for the old flat nav and must not be used
for new pages.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC  = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body(method_name: str) -> str:
    """Return the full source of a method (up to the next same-indent def)."""
    pattern = rf"(    def {re.escape(method_name)}\(.*?)(?=\n    def |\Z)"
    m = re.search(pattern, SRC, re.DOTALL)
    assert m, f"Method {method_name!r} not found in ui/dashboard.py"
    return m.group(1)


def test_no_duplicate_labels_in_pro_nav():
    """
    RULE-NAV1: _build_pro_nav() must not register the same label twice.
    Two entries for the same label would show a duplicate sidebar item.
    """
    body   = _method_body("_build_pro_nav")
    labels = re.findall(r'_nav_add_rail_item\(\s*"([^"]+)"', body)
    seen:  set[str]  = set()
    dupes: list[str] = []
    for lbl in labels:
        if lbl in seen:
            dupes.append(lbl)
        seen.add(lbl)
    assert not dupes, (
        f"_build_pro_nav() contains duplicate nav labels: {dupes}\n"
        "Each page must appear only once."
    )


def test_build_home_and_standard_nav_do_not_exist():
    """
    RULE-NAV2: _build_home_nav() and _build_standard_nav() must not exist.
    There is one nav mode. Recreating these methods causes the multi-mode bug
    where items added to one builder are invisible in the actual running app.
    """
    for dead_method in ("_build_home_nav", "_build_standard_nav"):
        assert f"def {dead_method}" not in SRC, (
            f"{dead_method}() was recreated in ui/dashboard.py.\n"
            "There is only one nav builder: _build_pro_nav(). "
            "Delete the dead method and add any pages to _build_pro_nav() instead."
        )
