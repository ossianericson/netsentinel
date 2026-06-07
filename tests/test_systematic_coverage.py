"""Tests that systematic_test.py always covers every non-admin page in the nav.

Runs in CI (no pywinauto needed — only re + pathlib).
Catches the class of bug where a page is added to _build_pro_nav() but
systematic_test._discover_pages() fails to parse it.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
BUILDER = REPO / "ui" / "nav" / "builder.py"
SYSTEMATIC = REPO / "tools" / "systematic_test.py"

_ADMIN_PAGES = {"Port Scan (TCP)", "Port Scan (UDP)", "Login Test"}


def _parse_builder_labels(skip_admin: bool = True) -> list:
    src = BUILDER.read_text(encoding="utf-8")
    labels = []
    for m in re.finditer(
        r'_nav_add_rail_item\(\s*"([^"]+)"([^)]*)\)', src, re.DOTALL
    ):
        label = m.group(1)
        args = m.group(2)
        if skip_admin and "admin_required=True" in args:
            continue
        labels.append(label)
    return labels


def test_discover_pages_finds_known_pages():
    """_discover_pages() regex must match at least 40 pages including known anchors."""
    labels = _parse_builder_labels()
    assert len(labels) >= 40, f"Expected ≥40 pages, got {len(labels)}: {labels}"
    for expected in [
        "Home", "Overview", "Speed Test", "Network Grade",
        "Security Overview", "Protocol Visualizer", "Hardware",
    ]:
        assert expected in labels, f"{expected!r} missing from discovered pages"


def test_admin_pages_excluded_by_default():
    """admin_required=True pages must not appear in the default (skip_admin) list."""
    labels = set(_parse_builder_labels(skip_admin=True))
    for page in _ADMIN_PAGES:
        assert page not in labels, f"Admin page {page!r} leaked into non-admin list"


def test_admin_pages_present_when_requested():
    """admin_required pages must appear when skip_admin=False."""
    labels = set(_parse_builder_labels(skip_admin=False))
    for page in _ADMIN_PAGES:
        assert page in labels, f"Admin page {page!r} missing from full list"


def test_systematic_all_pages_matches_builder():
    """_ALL_PAGES in systematic_test.py must equal the live parsed list from builder.py.

    Fails whenever a page is added/renamed in _build_pro_nav() but the
    _discover_pages() regex stops matching it.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("systematic_test", SYSTEMATIC)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit as e:
        pytest.skip(f"systematic_test deps not installed: {e}")
    except RuntimeError as e:
        pytest.fail(str(e))

    builder_labels = set(_parse_builder_labels())
    systematic_labels = set(mod._ALL_PAGES)

    missing = builder_labels - systematic_labels
    extra = systematic_labels - builder_labels

    assert not missing, (
        f"Pages registered in _build_pro_nav() but missing from _ALL_PAGES: {missing}\n"
        "Add these pages to builder.py so _discover_pages() can find them, or check "
        "that _nav_add_rail_item() call format hasn't changed."
    )
    assert not extra, (
        f"Pages in _ALL_PAGES that are not in _build_pro_nav(): {extra}\n"
        "These were probably renamed or removed — _discover_pages() auto-corrects on "
        "next run, but _SKIP_PAGES may have a stale entry."
    )
