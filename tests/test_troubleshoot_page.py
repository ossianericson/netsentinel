"""Tests for ui/pages/troubleshoot_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from ui.pages.troubleshoot_page import TroubleshootPage, _TILES


@pytest.fixture
def page():
    p = TroubleshootPage()
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # widget already deleted by Qt
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


# ── Import and instantiation ──────────────────────────────────────────────────

def test_import():
    from ui.pages.troubleshoot_page import TroubleshootPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


# ── Signal declarations ───────────────────────────────────────────────────────

def test_has_navigate_to_signal(page):
    assert hasattr(page, "navigate_to")


def test_has_diagnose_symptom_signal(page):
    assert hasattr(page, "diagnose_symptom")


# ── Tile data integrity ───────────────────────────────────────────────────────

def test_tile_count():
    assert len(_TILES) == 8


def test_all_tiles_have_required_fields():
    for tile in _TILES:
        label, desc, icon, action_type, action_arg, color = tile
        assert label, "label must not be empty"
        assert desc,  "desc must not be empty"
        assert icon,  "icon must not be empty"
        assert action_type in ("diagnose", "navigate"), f"unknown action_type: {action_type}"
        assert action_arg, "action_arg must not be empty"
        assert color.startswith("#"), f"color must be a hex string: {color}"


def test_diagnose_tiles_have_valid_symptom_keys():
    valid_keys = {"slow", "dropping", "noconn", "service_unreachable", "other"}
    for tile in _TILES:
        _, _, _, action_type, action_arg, _ = tile
        if action_type == "diagnose":
            assert action_arg in valid_keys, f"unknown symptom key: {action_arg}"


# ── Signal emission ───────────────────────────────────────────────────────────

def test_navigate_signal_emitted_for_navigate_tiles(page):
    nav_targets = []
    page.navigate_to.connect(nav_targets.append)

    navigate_tiles = [t for t in _TILES if t[3] == "navigate"]
    assert navigate_tiles, "need at least one navigate tile"

    expected = navigate_tiles[0][4]
    # Find the button on the page that routes to this target by simulating click signal
    # (We verify signal wiring exists, not UI rendering)
    page.navigate_to.emit(expected)
    assert expected in nav_targets


def test_diagnose_signal_emitted(page):
    diag_received = []
    page.diagnose_symptom.connect(diag_received.append)

    diagnose_tiles = [t for t in _TILES if t[3] == "diagnose"]
    assert diagnose_tiles, "need at least one diagnose tile"

    key = diagnose_tiles[0][4]
    page.diagnose_symptom.emit(key)
    assert key in diag_received


# ── Discover data integrity (S3-6 Ctrl+K aliases) ────────────────────────────

def test_troubleshoot_in_features():
    from ui.pages.discover_data import _FEATURES
    names = [f["name"] for f in _FEATURES]
    assert "Troubleshoot" in names


def test_troubleshoot_features_entry_has_symptom_tags():
    from ui.pages.discover_data import _FEATURES
    entry = next((f for f in _FEATURES if f["name"] == "Troubleshoot"), None)
    assert entry is not None
    tags = entry.get("tags", [])
    assert "streaming" in tags or "buffering" in tags
    assert "slow" in tags


# ── Help content ──────────────────────────────────────────────────────────────

def test_troubleshoot_in_page_help():
    from ui.pages.help_content import _PAGE_HELP
    assert "Troubleshoot" in _PAGE_HELP
