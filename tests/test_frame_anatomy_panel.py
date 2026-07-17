"""Tests for ui/widgets/frame_anatomy_panel.py (Phase A2 — Frame Anatomy inspector)."""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _layers():
    from modules.protocol_animator import FrameLayer
    return [
        FrameLayer("Ethernet II", [("Src MAC", "AA:BB:CC:DD:EE:FF"), ("Dst MAC", "FF:FF:FF:FF:FF:FF")]),
        FrameLayer("ARP", [("Opcode", "1 (Request)"), ("Sender IP", "192.168.1.100")]),
    ]


@pytest.fixture
def panel():
    from ui.widgets.frame_anatomy_panel import FrameAnatomyPanel
    p = FrameAnatomyPanel()
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
    from ui.widgets.frame_anatomy_panel import FrameAnatomyPanel  # noqa: F401


def test_instantiation(panel):
    assert panel is not None


def test_starts_with_no_segments(panel):
    assert panel._segment_btns == []
    assert panel._table.rowCount() == 0


def test_set_layers_shows_panel_with_segments(panel):
    panel.show()
    panel.set_layers(_layers())
    assert panel.isVisible()
    assert len(panel._segment_btns) == 2
    assert panel._segment_btns[0].text() == "Ethernet II"
    assert panel._segment_btns[1].text() == "ARP"


def test_default_segment_is_first_layer(panel):
    panel.set_layers(_layers())
    assert panel._table.rowCount() == 2
    assert panel._table.item(0, 0).text() == "Src MAC"
    assert panel._table.item(0, 1).text() == "AA:BB:CC:DD:EE:FF"


def test_clicking_second_segment_populates_its_fields(panel):
    panel.set_layers(_layers())
    panel._segment_btns[1].click()
    assert panel._table.rowCount() == 2
    assert panel._table.item(0, 0).text() == "Opcode"
    assert panel._table.item(0, 1).text() == "1 (Request)"


def test_set_layers_empty_hides_panel_and_clears_table(panel):
    panel.show()
    panel.set_layers(_layers())
    panel.set_layers([])
    assert not panel.isVisible()
    assert panel._table.rowCount() == 0
    assert panel._segment_btns == []


def test_selected_index_preserved_across_step_change(panel):
    """Stepping through an exchange while inspecting a later layer should
    keep that same layer selected on the next step, clamped to its count."""
    from modules.protocol_animator import FrameLayer

    panel.set_layers(_layers())
    panel._segment_btns[1].click()
    assert panel._selected_index == 1

    three_layers = _layers() + [FrameLayer("UDP", [("Src Port", "68"), ("Dst Port", "67")])]
    panel.set_layers(three_layers)
    assert panel._selected_index == 1
    assert panel._table.item(0, 0).text() == "Opcode"


def test_selected_index_clamped_when_new_step_has_fewer_layers(panel):
    """A step with 3 layers selects index 2; a following step with only 2 layers
    must clamp to the last valid index (1), not silently reset to 0."""
    from modules.protocol_animator import FrameLayer

    three_layers = _layers() + [FrameLayer("UDP", [("Src Port", "68"), ("Dst Port", "67")])]
    panel.set_layers(three_layers)
    panel._segment_btns[2].click()
    assert panel._selected_index == 2

    panel.set_layers(_layers())   # only 2 layers now
    assert panel._selected_index == 1
    assert panel._table.item(0, 0).text() == "Opcode"


def test_field_tooltip_uses_glossary_when_available(panel):
    """TTL is a real glossary.json term; the tooltip should show its definition."""
    from modules.protocol_animator import FrameLayer

    panel.set_layers([FrameLayer("IPv4", [("TTL", "64"), ("Src IP", "192.168.1.100")])])
    ttl_item = panel._table.item(0, 0)
    assert ttl_item.text() == "TTL"
    assert ttl_item.toolTip() != ""
