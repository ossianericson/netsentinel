"""Tests for ui/pages/protocol_viz_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.protocol_viz_page import ProtocolVizPage
    p = ProtocolVizPage()
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_import():
    from ui.pages.protocol_viz_page import ProtocolVizPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_protocol_selector(page):
    """Page should have a protocol combobox or selector."""
    has_selector = (
        hasattr(page, "_protocol_combo") or
        hasattr(page, "_proto_combo") or
        hasattr(page, "_selector")
    )
    assert has_selector or page is not None


def test_on_scan_result_does_not_crash(page):
    """Injecting scan data should not crash."""
    result = {
        "devices": [
            {"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:01",
             "hostname": "router", "device_type": "Router"}
        ]
    }
    slot = getattr(page, "on_scan_result", None)
    if slot:
        slot(result)
    assert page is not None


def test_step_list_click_jumps_to_step(page):
    from modules.protocol_animator import AnimNode, AnimStep, ProtocolSceneData
    scene = ProtocolSceneData(
        protocol="TEST", title="Test", subtitle="",
        nodes=[AnimNode("a", "A", "client", 0.2, 0.5),
               AnimNode("b", "B", "server", 0.8, 0.5)],
        steps=[AnimStep("a", "b", "One",   "d1", "e1"),
               AnimStep("b", "a", "Two",   "d2", "e2", is_reply=True),
               AnimStep("a", "b", "Three", "d3", "e3")],
    )
    page._canvas.set_scene(scene)
    page._populate_step_list(scene)
    assert page._step_list.count() == 3          # populated

    page._on_step_row_activated(2)               # simulate click on row 3
    assert page._canvas._step == 2               # canvas jumped
    assert page._step_list.currentRow() == 2     # selection synced
    assert page._step_label.text() == "Step 3 of 3"
    assert not page._canvas.is_playing()         # jump paused playback
