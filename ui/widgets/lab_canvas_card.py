"""
LabCanvasCard — compact protocol-animation card embedded in the Lab Mode
runner (Lab Mode Upgrade Phase L1).

Wraps the existing ProtocolCanvas (ui/widgets/protocol_canvas.py) with a
minimal playback row (play/pause, step back/forward, 1x/2x speed) and a
FrameAnatomyPanel collapsed by default. Pure reuse of the Protocol
Visualizer's rendering engine and scene builders — no new rendering code.

Usage::

    card = LabCanvasCard()
    layout.addWidget(card)
    card.set_scene(scene)   # ProtocolSceneData from build_scene_for_key(); auto-plays
"""
from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from modules.protocol_animator import ProtocolSceneData
from ui import styles as _s
from ui.widgets.frame_anatomy_panel import FrameAnatomyPanel
from ui.widgets.protocol_canvas import ProtocolCanvas

_SPEED_OPTIONS = (1.0, 2.0)


class LabCanvasCard(QFrame):
    """Card hosting a live ProtocolCanvas + minimal playback row for a lab step."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("labCanvasCard")
        _s.themed_ss(self, lambda: _s.qss_frame("labCanvasCard", radius=8))

        self._speed_idx = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(14, 10, 14, 4)
        self._title = QLabel()
        _s.themed_ss(self._title, "font-size:12px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;")
        self._subtitle = QLabel()
        _s.themed_ss(self._subtitle, "font-size:10px; color:{TEXT_MUTED}; background:transparent;")
        title_row.addWidget(self._title)
        title_row.addStretch()
        title_row.addWidget(self._subtitle)
        root.addLayout(title_row)

        self._canvas = ProtocolCanvas()
        self._canvas.setMinimumHeight(180)
        self._canvas.step_changed.connect(self._on_step_changed)
        root.addWidget(self._canvas)

        ctrl_bar = QWidget()
        ctrl_bar.setObjectName("labCanvasCtrlBar")
        _s.themed_ss(ctrl_bar, "QWidget#labCanvasCtrlBar {{ background:transparent;"
            " border-top:1px solid {BORDER}; }}")
        ctrl_lay = QHBoxLayout(ctrl_bar)
        ctrl_lay.setContentsMargins(14, 6, 14, 6)
        ctrl_lay.setSpacing(6)

        self._btn_back  = self._ctrl_btn("◀◀", "Previous step")
        self._btn_play  = self._ctrl_btn("⏸  Pause", "Play / pause animation")
        self._btn_fwd   = self._ctrl_btn("▶▶", "Next step")
        self._btn_speed = self._ctrl_btn("1×", "Toggle playback speed")

        self._btn_back.clicked.connect(self._canvas.step_back)
        self._btn_play.clicked.connect(self._toggle_play)
        self._btn_fwd.clicked.connect(self._canvas.step_forward)
        self._btn_speed.clicked.connect(self._toggle_speed)

        ctrl_lay.addWidget(self._btn_back)
        ctrl_lay.addWidget(self._btn_play)
        ctrl_lay.addWidget(self._btn_fwd)
        ctrl_lay.addWidget(self._btn_speed)
        ctrl_lay.addStretch()
        root.addWidget(ctrl_bar)

        self._frame_panel = FrameAnatomyPanel()
        root.addWidget(self._frame_panel)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_scene(self, scene: ProtocolSceneData) -> None:
        """Load a scene, reset playback controls, and auto-play from step 1."""
        self._title.setText(scene.title or "")
        self._frame_panel.set_layers([])
        self._btn_speed.setText(f"{_SPEED_OPTIONS[self._speed_idx]:g}×")
        if scene.missing_data_msg:
            self._subtitle.setText(scene.missing_data_msg)
            self._canvas.set_scene(scene)
            self._btn_play.setText("▶  Play")
            return
        self._subtitle.setText(scene.subtitle)
        self._canvas.set_scene(scene)
        self._canvas.set_speed(_SPEED_OPTIONS[self._speed_idx])
        self._btn_play.setText("⏸  Pause")
        self._canvas.play()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _ctrl_btn(self, text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setFixedHeight(26)
        _s.themed_ss(btn, "QPushButton {{ background:transparent; border:1px solid {BORDER};"
            " border-radius:4px; color:{TEXT_PRIMARY}; font-size:11px; padding:0 8px; }}"
            "QPushButton:hover {{ background:{BORDER}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
        return btn

    def _toggle_play(self) -> None:
        if self._canvas.is_playing():
            self._canvas.pause()
            self._btn_play.setText("▶  Play")
        else:
            self._canvas.play()
            self._btn_play.setText("⏸  Pause")

    def _toggle_speed(self) -> None:
        self._speed_idx = (self._speed_idx + 1) % len(_SPEED_OPTIONS)
        value = _SPEED_OPTIONS[self._speed_idx]
        self._canvas.set_speed(value)
        self._btn_speed.setText(f"{value:g}×")

    def _on_step_changed(self, idx: int, total: int) -> None:
        scene = self._canvas._scene
        if scene and idx < len(scene.steps):
            self._frame_panel.set_layers(scene.steps[idx].layers)
