"""Tests for ui/widgets/protocol_storyboard.py (Phase A3 — Shareability)."""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _synthetic_scene(n_steps: int = 3):
    from modules.protocol_animator import AnimNode, AnimStep, ProtocolSceneData

    nodes = [
        AnimNode("a", "Client",  "client",  0.1, 0.5),
        AnimNode("b", "Gateway", "gateway", 0.9, 0.5),
    ]
    steps = [
        AnimStep(
            "a", "b", f"Step {i + 1}", f"detail {i + 1}",
            "A reasonably long explanation sentence describing what happens in this "
            "step of the exchange, long enough that it should wrap across more than "
            "one line when rendered into the storyboard panel.",
            is_reply=(i % 2 == 1),
        )
        for i in range(n_steps)
    ]
    return ProtocolSceneData(
        protocol="TEST", title="Test Scene", subtitle="synthetic provenance",
        nodes=nodes, steps=steps,
    )


@pytest.fixture
def canvas():
    from ui.widgets.protocol_canvas import ProtocolCanvas
    c = ProtocolCanvas()
    c.resize(400, 300)
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
    from ui.widgets.protocol_storyboard import build_storyboard_pixmap  # noqa: F401


def test_pixmap_taller_for_more_steps(canvas):
    from ui.widgets.protocol_storyboard import build_storyboard_pixmap

    canvas.set_scene(_synthetic_scene(2))
    short = build_storyboard_pixmap(canvas, canvas._scene)

    canvas.set_scene(_synthetic_scene(5))
    tall = build_storyboard_pixmap(canvas, canvas._scene)

    assert not short.isNull() and not tall.isNull()
    assert short.width() == tall.width()
    # Each extra step contributes at least a full canvas-frame height.
    assert tall.height() >= short.height() + 3 * canvas.height()


def test_leaves_canvas_on_original_step(canvas):
    from ui.widgets.protocol_storyboard import build_storyboard_pixmap

    scene = _synthetic_scene(4)
    canvas.set_scene(scene)
    canvas.go_to_step(2)

    build_storyboard_pixmap(canvas, scene)

    assert canvas.current_step() == 2


def test_resumes_playback_if_it_was_playing(canvas):
    from ui.widgets.protocol_storyboard import build_storyboard_pixmap

    scene = _synthetic_scene(3)
    canvas.set_scene(scene)
    canvas.play()
    assert canvas.is_playing()

    build_storyboard_pixmap(canvas, scene)

    assert canvas.is_playing()


def test_export_writes_decodable_png(canvas, tmp_path):
    from PyQt6.QtGui import QPixmap
    from ui.widgets.protocol_storyboard import build_storyboard_pixmap

    scene = _synthetic_scene(3)
    canvas.set_scene(scene)
    pixmap = build_storyboard_pixmap(canvas, scene)

    out_path = tmp_path / "storyboard.png"
    assert pixmap.save(str(out_path), "PNG")

    reloaded = QPixmap(str(out_path))
    assert not reloaded.isNull()
    assert reloaded.width() == pixmap.width()
    assert reloaded.height() == pixmap.height()
