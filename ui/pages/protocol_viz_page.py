"""
Protocol Visualizer page — interactive animated protocol diagrams.

Shows five protocols animated using real addresses from the last scan:
  ARP resolution, DNS lookup, TCP three-way handshake, DHCP lease, STP election.

Auto-plays on protocol selection with play/pause, reset, and manual step controls.
"""
from __future__ import annotations

from typing import Any, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from modules.protocol_animator import (
    ProtocolSceneData,
    build_arp_scene,
    build_dhcp_scene,
    build_dns_scene,
    build_stp_scene,
    build_tcp_scene,
)
from ui.styles import (
    ACCENT, BG_CARD, BORDER, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)
from ui.widgets.protocol_canvas import ProtocolCanvas

# ── Protocol descriptors ───────────────────────────────────────────────────────

_PROTOCOLS = [
    ("ARP",  "ARP Resolution",          "Layer 2 — Address Resolution Protocol"),
    ("DNS",  "DNS Lookup",              "Layer 7 — Domain Name System"),
    ("TCP",  "TCP Three-Way Handshake", "Layer 4 — Transmission Control Protocol"),
    ("DHCP", "DHCP Lease (DORA)",       "Layer 7 — Dynamic Host Configuration Protocol"),
    ("STP",  "STP Root Election",       "Layer 2 — Spanning Tree Protocol"),
]


def _card_frame() -> QFrame:
    f = QFrame()
    f.setObjectName("contentArea")
    f.setStyleSheet(
        f"QFrame#contentArea {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-radius:8px; }}"
    )
    return f


def _label(text: str, size: int = 12, color: str = TEXT_PRIMARY,
           bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(
        f"font-size:{size}px; color:{color};"
        + (" font-weight:bold;" if bold else "")
    )
    return lbl


class ProtocolVizPage(QWidget):
    """
    Interactive protocol visualizer.

    Call set_context() after each scan to refresh the underlying data.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")

        self._net_info:   dict        = {}
        self._devices:    list        = []
        self._diag_result: Any        = None
        self._m2_result:  Optional[dict] = None
        self._active_key: str         = "ARP"

        self._build_ui()
        self._select_protocol("ARP")

    # ── Public interface ───────────────────────────────────────────────────────

    def set_context(
        self,
        net_info: dict,
        devices: list,
        diag_result: Any = None,
        m2_result: Optional[dict] = None,
    ) -> None:
        self._net_info    = net_info   or {}
        self._devices     = devices    or []
        self._diag_result = diag_result
        self._m2_result   = m2_result
        # Refresh the currently displayed protocol
        self._select_protocol(self._active_key)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Page header
        hdr = QWidget()
        hdr.setStyleSheet(f"background:{BG_CARD}; border-bottom:1px solid {BORDER};")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 14, 20, 14)
        hdr_lay.setSpacing(2)
        hdr_lay.addWidget(_label("Protocol Visualizer", 16, TEXT_PRIMARY, bold=True))
        hdr_lay.addWidget(_label(
            "Animated step-by-step diagrams of five protocols using your network's real addresses.",
            11, TEXT_SECONDARY,
        ))
        outer.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        body = QWidget()
        body.setObjectName("contentArea")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 16, 16, 20)
        bl.setSpacing(14)

        # Protocol picker row
        picker_card = _card_frame()
        picker_lay  = QVBoxLayout(picker_card)
        picker_lay.setContentsMargins(16, 12, 16, 12)
        picker_lay.setSpacing(6)
        picker_lay.addWidget(_label("Choose a protocol", 11, TEXT_SECONDARY))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._proto_btns: dict[str, QPushButton] = {}
        for key, title, sub in _PROTOCOLS:
            btn = QPushButton(title)
            btn.setCheckable(True)
            btn.setToolTip(sub)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda _checked, k=key: self._select_protocol(k))
            self._proto_btns[key] = btn
            btn_row.addWidget(btn)
        picker_lay.addLayout(btn_row)
        bl.addWidget(picker_card)
        self._style_proto_btns()

        # Canvas card
        canvas_card = _card_frame()
        canvas_lay  = QVBoxLayout(canvas_card)
        canvas_lay.setContentsMargins(0, 0, 0, 0)
        canvas_lay.setSpacing(0)

        # Canvas title bar
        title_bar = QWidget()
        title_bar.setStyleSheet(
            f"background:transparent; border-bottom:1px solid {BORDER};"
        )
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(16, 10, 16, 10)
        tb_lay.setSpacing(8)
        self._canvas_title    = _label("", 13, TEXT_PRIMARY, bold=True)
        self._canvas_subtitle = _label("", 10, TEXT_MUTED)
        tb_lay.addWidget(self._canvas_title)
        tb_lay.addWidget(self._canvas_subtitle)
        tb_lay.addStretch()
        canvas_lay.addWidget(title_bar)

        # Placeholder shown when data is missing
        self._placeholder = QLabel()
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:12px; padding:32px;"
        )
        self._placeholder.setVisible(False)
        canvas_lay.addWidget(self._placeholder)

        # The animation canvas
        self._canvas = ProtocolCanvas()
        self._canvas.setMinimumHeight(280)
        self._canvas.step_changed.connect(self._on_step_changed)
        self._canvas.finished.connect(self._on_anim_finished)
        canvas_lay.addWidget(self._canvas, 1)

        # Playback controls
        ctrl_bar = QWidget()
        ctrl_bar.setStyleSheet(
            f"background:transparent; border-top:1px solid {BORDER};"
        )
        ctrl_lay = QHBoxLayout(ctrl_bar)
        ctrl_lay.setContentsMargins(16, 8, 16, 8)
        ctrl_lay.setSpacing(8)

        self._btn_back  = self._ctrl_btn("◀◀", "Previous step")
        self._btn_play  = self._ctrl_btn("▶  Play",  "Play / pause animation")
        self._btn_fwd   = self._ctrl_btn("▶▶", "Next step")
        self._btn_reset = self._ctrl_btn("↺  Reset", "Restart from step 1")

        self._step_label = _label("Step 1 of 1", 11, TEXT_MUTED)

        ctrl_lay.addWidget(self._btn_back)
        ctrl_lay.addWidget(self._btn_play)
        ctrl_lay.addWidget(self._btn_fwd)
        ctrl_lay.addWidget(self._btn_reset)
        ctrl_lay.addStretch()
        ctrl_lay.addWidget(self._step_label)

        self._btn_back.clicked.connect(self._canvas.step_back)
        self._btn_play.clicked.connect(self._toggle_play)
        self._btn_fwd.clicked.connect(self._canvas.step_forward)
        self._btn_reset.clicked.connect(self._on_reset)

        canvas_lay.addWidget(ctrl_bar)
        bl.addWidget(canvas_card)

        # Description panel
        desc_card = _card_frame()
        desc_lay  = QVBoxLayout(desc_card)
        desc_lay.setContentsMargins(16, 12, 16, 14)
        desc_lay.setSpacing(6)

        desc_hdr = QHBoxLayout()
        self._step_title = _label("", 12, TEXT_PRIMARY, bold=True)
        self._step_index = _label("", 11, TEXT_MUTED)
        desc_hdr.addWidget(self._step_title)
        desc_hdr.addStretch()
        desc_hdr.addWidget(self._step_index)
        desc_lay.addLayout(desc_hdr)

        self._step_detail = _label("", 11, TEXT_SECONDARY)
        desc_lay.addWidget(self._step_detail)

        self._step_explanation = _label("", 12, TEXT_PRIMARY)
        self._step_explanation.setStyleSheet(
            f"font-size:12px; color:{TEXT_PRIMARY}; line-height:1.6;"
        )
        desc_lay.addWidget(self._step_explanation)
        bl.addWidget(desc_card)

        bl.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    def _ctrl_btn(self, text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setFixedHeight(28)
        btn.setStyleSheet(
            f"QPushButton {{ background:transparent; border:1px solid {BORDER};"
            f" border-radius:4px; color:{TEXT_PRIMARY}; font-size:11px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{BORDER}; }}"
        )
        return btn

    def _style_proto_btns(self) -> None:
        for key, btn in self._proto_btns.items():
            active = (key == self._active_key)
            btn.setStyleSheet(
                f"QPushButton {{ border-radius:4px; font-size:11px; font-weight:bold; padding:0 8px;"
                f" background:{'%s' % ACCENT if active else 'transparent'};"
                f" color:{'#ffffff' if active else TEXT_SECONDARY};"
                f" border:1px solid {'%s' % ACCENT if active else BORDER}; }}"
                f"QPushButton:hover {{ background:{ACCENT}; color:#ffffff; }}"
            )
            btn.setChecked(active)

    # ── Protocol selection ─────────────────────────────────────────────────────

    def _select_protocol(self, key: str) -> None:
        self._active_key = key
        self._style_proto_btns()

        scene = self._build_scene(key)

        if scene.missing_data_msg:
            self._placeholder.setText(scene.missing_data_msg)
            self._placeholder.setVisible(True)
            self._canvas.setVisible(False)
            self._canvas_title.setText(scene.title or key)
            self._canvas_subtitle.setText("")
            self._step_title.setText("")
            self._step_explanation.setText("")
            self._step_detail.setText("")
            self._step_label.setText("")
            return

        self._placeholder.setVisible(False)
        self._canvas.setVisible(True)
        self._canvas_title.setText(scene.title)
        self._canvas_subtitle.setText(scene.subtitle)
        self._canvas.set_scene(scene)
        self._show_step(0, scene)

        # Auto-play
        self._btn_play.setText("⏸  Pause")
        self._canvas.play()

    def _build_scene(self, key: str) -> ProtocolSceneData:
        if key == "ARP":
            return build_arp_scene(self._net_info, self._devices)
        if key == "DNS":
            return build_dns_scene(self._net_info, self._diag_result)
        if key == "TCP":
            return build_tcp_scene(self._net_info, self._devices)
        if key == "DHCP":
            return build_dhcp_scene(self._net_info)
        if key == "STP":
            return build_stp_scene(self._m2_result)
        return build_arp_scene(self._net_info, self._devices)

    # ── Playback controls ──────────────────────────────────────────────────────

    def _toggle_play(self) -> None:
        if self._canvas.is_playing():
            self._canvas.pause()
            self._btn_play.setText("▶  Play")
        else:
            self._canvas.play()
            self._btn_play.setText("⏸  Pause")

    def _on_reset(self) -> None:
        self._canvas.reset()
        self._btn_play.setText("▶  Play")
        if self._canvas._scene and self._canvas._scene.steps:
            self._show_step(0, self._canvas._scene)

    def _on_anim_finished(self) -> None:
        self._btn_play.setText("▶  Play")

    # ── Step description ───────────────────────────────────────────────────────

    def _on_step_changed(self, idx: int, total: int) -> None:
        scene = self._canvas._scene
        if scene:
            self._show_step(idx, scene)

    def _show_step(self, idx: int, scene: ProtocolSceneData) -> None:
        total = len(scene.steps)
        self._step_label.setText(f"Step {idx + 1} of {total}")
        if idx >= total:
            return
        step = scene.steps[idx]
        self._step_title.setText(step.packet_label)
        self._step_index.setText(f"Step {idx + 1} / {total}")
        self._step_detail.setText(step.frame_detail)
        self._step_explanation.setText(step.explanation)
