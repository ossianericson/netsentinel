"""
test_nav_completeness.py

RULE-NAV1/NAV2 compliance tests (S11-4 parity gates added in Sprint 3).

There is one nav builder: _build_pro_nav(). New pages are registered there via
_nav_add_rail_item() — that is the only registration needed. _build_tabs() /
_nav_add_page() is legacy dead code for the old flat nav and must not be used
for new pages.

S11-4 gates (added Sprint 3):
  - test_all_nav_labels_have_page_help: every static nav label has a _PAGE_HELP entry
  - test_features_page_refs_are_valid_nav_labels: every _FEATURES "page" is a valid
    nav label or None
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC  = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _static_nav_labels() -> list[str]:
    """Return the ordered list of static string labels from _build_pro_nav()."""
    body = _method_body("_build_pro_nav")
    return re.findall(r'_nav_add_rail_item\(\s*"([^"]+)"', body)


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


# ── S11-4 parity gates ────────────────────────────────────────────────────────

def test_all_nav_labels_have_page_help():
    """S11-4-1: Every static nav label has a non-empty _PAGE_HELP entry (RULE-D1)."""
    sys.path.insert(0, str(ROOT))
    from ui.help import _PAGE_HELP  # no Qt deps — pure data module

    missing = [lbl for lbl in _static_nav_labels() if lbl not in _PAGE_HELP]
    assert not missing, (
        f"Nav labels missing _PAGE_HELP entries: {missing}\n"
        'Add them to ui/help.py using the {"what": ..., "hidden": [...]} format.'
    )


def test_features_page_refs_are_valid_nav_labels():
    """S11-4-2: Every _FEATURES 'page' value is a valid nav label or None (RULE-D2)."""
    DISCOVER_SRC = (ROOT / "ui" / "pages" / "discover_page.py").read_text(encoding="utf-8")
    nav_labels = set(_static_nav_labels())

    # Capture the full quoted label or the bare keyword None
    page_refs_raw = re.findall(r'"page"\s*:\s*("(?:[^"]+)"|None)', DISCOVER_SRC)

    stale = [
        ref.strip('"')
        for ref in page_refs_raw
        if ref != "None" and ref.strip('"') not in nav_labels
    ]
    assert not stale, (
        f"_FEATURES entries reference non-existent nav labels: {stale}\n"
        "Fix the 'page' field to match an exact _nav_add_rail_item() label, or set to None."
    )
