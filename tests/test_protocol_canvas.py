"""Tests for ui/widgets/protocol_canvas.py (Phase A1 — cinematic canvas)."""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _synthetic_scene():
    """One scene exercising all 7 roles plus a broadcast step and a reply step."""
    from modules.protocol_animator import AnimNode, AnimStep, ProtocolSceneData

    nodes = [
        AnimNode("a", "Client",    "client",    0.08, 0.5),
        AnimNode("b", "Gateway",   "gateway",   0.28, 0.2),
        AnimNode("c", "DNS",       "dns",       0.48, 0.8),
        AnimNode("d", "Server",    "server",    0.68, 0.2),
        AnimNode("e", "Broadcast", "broadcast", 0.68, 0.8),
        AnimNode("f", "Switch",    "switch",    0.88, 0.5),
        AnimNode("g", "Root",      "root",      0.98, 0.1),
    ]
    steps = [
        AnimStep("a", "b", "Request", "d1", "e1"),
        AnimStep("b", "a", "Reply",   "d2", "e2", is_reply=True),
        AnimStep("a", "e", "Bcast",   "d3", "e3", is_broadcast=True),
    ]
    return ProtocolSceneData(
        protocol="TEST", title="Test Scene", subtitle="synthetic",
        nodes=nodes, steps=steps,
    )


@pytest.fixture
def canvas():
    from ui.widgets.protocol_canvas import ProtocolCanvas
    c = ProtocolCanvas()
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
    from ui.widgets.protocol_canvas import ProtocolCanvas  # noqa: F401


def test_glyphs_cover_all_roles():
    from ui.widgets.protocol_canvas import _ROLE_COLOR
    from ui.widgets.protocol_canvas_glyphs import ROLE_GLYPHS

    assert set(ROLE_GLYPHS.keys()) == set(_ROLE_COLOR.keys())


def test_renders_without_error_at_two_sizes(canvas):
    scene = _synthetic_scene()
    canvas.set_scene(scene)

    for size in ((400, 300), (900, 560)):
        canvas.resize(*size)
        for step_idx in range(len(scene.steps)):
            canvas.go_to_step(step_idx)
            # Exercise the "anim" phase (curve/trail/broadcast-ring code paths) too,
            # not just the "hold" phase go_to_step() leaves it in.
            canvas._phase = "anim"
            canvas._phase_ms = 200.0
            canvas._tick()
            pixmap = QPixmap(canvas.size())
            canvas.render(pixmap)
            assert not pixmap.isNull()
            assert pixmap.width() == size[0]
            assert pixmap.height() == size[1]


def test_renders_empty_state_without_error(canvas):
    canvas.resize(400, 300)
    pixmap = QPixmap(canvas.size())
    canvas.render(pixmap)
    assert not pixmap.isNull()


def test_set_speed_scales_timing(canvas):
    scene = _synthetic_scene()
    canvas.set_scene(scene)
    canvas.play()

    canvas.set_speed(2.0)
    canvas._phase = "anim"
    canvas._phase_ms = 0.0
    canvas._tick()
    fast_ms = canvas._phase_ms

    canvas.set_speed(1.0)
    canvas._phase = "anim"
    canvas._phase_ms = 0.0
    canvas._tick()
    normal_ms = canvas._phase_ms

    canvas.set_speed(0.5)
    canvas._phase = "anim"
    canvas._phase_ms = 0.0
    canvas._tick()
    slow_ms = canvas._phase_ms

    assert fast_ms == pytest.approx(normal_ms * 2, rel=0.01)
    assert slow_ms == pytest.approx(normal_ms * 0.5, rel=0.01)


def test_current_step_tracks_go_to_step(canvas):
    scene = _synthetic_scene()
    canvas.set_scene(scene)
    assert canvas.current_step() == 0
    canvas.go_to_step(2)
    assert canvas.current_step() == 2


def _live_nodes():
    from modules.protocol_animator import AnimNode
    return [
        AnimNode("you",     "Your PC", "client",  0.15, 0.5),
        AnimNode("gateway", "Gateway", "gateway", 0.85, 0.5),
    ]


def test_enter_live_switches_mode(canvas):
    assert not canvas.is_live()
    canvas.enter_live(_live_nodes())
    assert canvas.is_live()
    assert canvas._timer.isActive()


def test_enter_live_stops_step_playback(canvas):
    scene = _synthetic_scene()
    canvas.set_scene(scene)
    canvas.play()
    assert canvas.is_playing()
    canvas.enter_live(_live_nodes())
    assert not canvas.is_playing()


def test_pulse_noop_outside_live_mode(canvas):
    """Defensive: a stray event after exit_live() (or before enter_live()) must
    not resurrect live drawing state."""
    canvas.pulse("a", "b", "ARP Reply", is_reply=True, is_broadcast=False)
    assert canvas._live_pulses == []


def test_pulse_appends_and_ticks_and_expires(canvas):
    canvas.resize(400, 300)
    canvas.enter_live(_live_nodes())
    canvas.pulse("you", "gateway", "Who has 192.168.1.1?", is_reply=False, is_broadcast=True)
    assert len(canvas._live_pulses) == 1

    pixmap = QPixmap(canvas.size())
    canvas.render(pixmap)
    assert not pixmap.isNull()

    # Age the pulse past its full life (travel + arrival decay) and confirm
    # the tick loop discards it instead of leaving a stale pulse rendering forever.
    canvas._live_pulses[0].elapsed_ms = 10_000.0
    canvas._tick_live()
    assert canvas._live_pulses == []


def test_multiple_overlapping_pulses_render_without_error(canvas):
    canvas.resize(400, 300)
    canvas.enter_live(_live_nodes())
    canvas.pulse("you", "gateway", "Request", is_reply=False, is_broadcast=False)
    canvas.pulse("gateway", "you", "Reply", is_reply=True, is_broadcast=False)
    canvas._tick_live()
    pixmap = QPixmap(canvas.size())
    canvas.render(pixmap)
    assert not pixmap.isNull()
    assert len(canvas._live_pulses) == 2


def test_set_live_nodes_noop_outside_live_mode(canvas):
    canvas.set_live_nodes(_live_nodes())
    assert canvas._live_nodes == []


def test_set_live_nodes_replaces_set(canvas):
    canvas.enter_live(_live_nodes())
    from modules.protocol_animator import AnimNode
    new_nodes = [AnimNode("you", "Your PC", "client", 0.15, 0.5)]
    canvas.set_live_nodes(new_nodes)
    assert canvas._live_nodes == new_nodes


def test_exit_live_restores_non_live_mode(canvas):
    canvas.enter_live(_live_nodes())
    canvas.pulse("you", "gateway", "Reply", is_reply=True, is_broadcast=False)
    canvas.exit_live()
    assert not canvas.is_live()
    assert canvas._live_nodes == []
    assert canvas._live_pulses == []
    assert not canvas._timer.isActive()


def test_live_empty_state_renders_without_error(canvas):
    canvas.resize(400, 300)
    canvas.enter_live([])
    pixmap = QPixmap(canvas.size())
    canvas.render(pixmap)
    assert not pixmap.isNull()


def test_step_mode_still_works_after_live_round_trip(canvas):
    """Regression guard: entering/exiting live mode must not corrupt the
    step-mode state machine used by every other protocol scene."""
    scene = _synthetic_scene()
    canvas.set_scene(scene)
    canvas.enter_live(_live_nodes())
    canvas.pulse("you", "gateway", "Reply", is_reply=True, is_broadcast=False)
    canvas.exit_live()
    canvas.set_scene(scene)   # page re-selects the protocol after leaving live mode
    canvas.resize(400, 300)
    canvas.go_to_step(1)
    assert canvas.current_step() == 1
    pixmap = QPixmap(canvas.size())
    canvas.render(pixmap)
    assert not pixmap.isNull()


def test_set_speed_rejects_non_positive():
    from ui.widgets.protocol_canvas import ProtocolCanvas
    c = ProtocolCanvas()
    try:
        c.set_speed(0)
        assert c._speed == 1.0
        c.set_speed(-1.0)
        assert c._speed == 1.0
    finally:
        try:
            c.deleteLater()
        except RuntimeError:
            pass  # already deleted
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()
