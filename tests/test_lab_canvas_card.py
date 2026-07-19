"""Tests for ui/widgets/lab_canvas_card.py (Lab Mode Upgrade Phase L1)."""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

_NET_INFO = {
    "gateway": "192.168.1.1",
    "gateway_mac": "aa:bb:cc:dd:ee:ff",
    "local_ips": [{"ip": "192.168.1.100"}],
    "dns_servers": ["8.8.8.8"],
}


@pytest.fixture
def card():
    from ui.widgets.lab_canvas_card import LabCanvasCard
    c = LabCanvasCard()
    yield c
    try:
        c.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_import():
    from ui.widgets.lab_canvas_card import LabCanvasCard  # noqa: F401


def test_instantiation(card):
    assert card is not None


def test_set_scene_shows_nodes_and_title(card):
    from modules.protocol_animator import build_arp_scene
    scene = build_arp_scene(_NET_INFO, [])
    card.set_scene(scene)
    assert card._canvas._scene is scene
    assert len(scene.nodes) >= 1
    assert card._title.text() == scene.title
    assert card._subtitle.text() == scene.subtitle


def test_set_scene_populates_frame_panel_for_first_step(card):
    from modules.protocol_animator import build_arp_scene
    scene = build_arp_scene(_NET_INFO, [])
    card.set_scene(scene)
    assert card._frame_panel._layers == scene.steps[0].layers


def test_set_scene_with_missing_data_shows_message_not_crash(card):
    from modules.protocol_animator import build_arp_scene
    scene = build_arp_scene({}, [])
    assert scene.missing_data_msg
    card.set_scene(scene)
    assert card._subtitle.text() == scene.missing_data_msg


def test_toggle_speed_cycles_and_updates_canvas(card):
    from modules.protocol_animator import build_arp_scene
    scene = build_arp_scene(_NET_INFO, [])
    card.set_scene(scene)
    assert card._speed_idx == 0
    card._toggle_speed()
    assert card._speed_idx == 1
    assert card._canvas._speed == 2.0
    assert card._btn_speed.text() == "2×"
