"""
Protocol Visualizer page — interactive animated protocol diagrams.

Shows five protocols animated using real addresses from the last scan:
  ARP resolution, DNS lookup, TCP three-way handshake, DHCP lease, STP election.

Auto-plays on protocol selection with play/pause, reset, and manual step controls.
"""
from __future__ import annotations

import re as _re
from typing import Any, Dict, List, Optional

_IP_RE = _re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")

from PyQt6.QtCore import Qt, pyqtSignal
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
    ACCENT, ACCENT_DARK, BG_CARD, BG_HOVER,
    BORDER, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    WHITE,
)
from ui.widgets.protocol_canvas import ProtocolCanvas
from ui.widgets.jargon_tooltip import get_definition

# ── Protocol descriptors ───────────────────────────────────────────────────────

_PROTOCOLS = [
    ("ARP",  "ARP Resolution",          "Layer 2 — Address Resolution Protocol"),
    ("DNS",  "DNS Lookup",              "Layer 7 — Domain Name System"),
    ("TCP",  "TCP Three-Way Handshake", "Layer 4 — Transmission Control Protocol"),
    ("DHCP", "DHCP Lease (DORA)",       "Layer 7 — Dynamic Host Configuration Protocol"),
    ("STP",  "STP Root Election",       "Layer 2 — Spanning Tree Protocol"),
]

# "Why this protocol matters" content shown below the step description.
# Tuple: (why_it_exists, what_goes_wrong, netsentinel_scan_label)
_PROTOCOL_CONTEXT: dict[str, tuple[str, str, str]] = {
    "ARP": (
        "ARP (Address Resolution Protocol) is how every device on your local network discovers "
        "hardware addresses. Before any packet can be delivered, the sender broadcasts 'who has IP x?' "
        "and the owner replies with its MAC address. Without ARP, local communication is impossible.",
        "ARP has no authentication — any device can claim any IP address. ARP spoofing exploits this "
        "to intercept traffic destined for another device (a man-in-the-middle attack). "
        "NetSentinel's Rogue Device scanner reads the ARP table to detect unexpected IP-to-MAC bindings.",
        "Devices",
    ),
    "DNS": (
        "DNS (Domain Name System) translates human-readable names like 'google.com' into IP addresses. "
        "Every connection your computer makes starts with a DNS lookup — even if you never see it. "
        "Your DNS resolver is typically provided by your ISP or configured manually (e.g. 8.8.8.8).",
        "Slow or failing DNS makes the entire internet feel broken even if your physical connection is fine. "
        "DNS can also be hijacked to redirect you to malicious sites (DNS spoofing). "
        "NetSentinel measures DNS latency on each ping cycle and flags resolver failures.",
        "DNS & Stability",
    ),
    "TCP": (
        "TCP (Transmission Control Protocol) is the reliable delivery layer used by HTTP, SSH, email, "
        "and most internet applications. Before any data flows, both sides complete a three-way handshake "
        "(SYN → SYN-ACK → ACK) to establish a connection and agree on sequence numbers.",
        "A port scan works by sending SYN packets and observing which ports reply with SYN-ACK (open) "
        "versus RST (closed) or no reply (filtered). Unexpected open ports on your devices indicate "
        "services you didn't intend to expose. NetSentinel's Port Scanner maps all open TCP ports.",
        "Devices",
    ),
    "DHCP": (
        "DHCP (Dynamic Host Configuration Protocol) automatically assigns IP addresses when devices "
        "join a network. The four-step exchange — Discover, Offer, Request, Acknowledge (DORA) — "
        "happens in seconds and is invisible to the user.",
        "A rogue DHCP server can give devices a fake default gateway or DNS server, "
        "silently redirecting all their traffic. This is one of the most dangerous local network attacks. "
        "NetSentinel's DHCP Lease scanner detects unauthorized DHCP servers on your subnet.",
        "DHCP Leases",
    ),
    "STP": (
        "STP (Spanning Tree Protocol) prevents Ethernet broadcast storms by blocking redundant links "
        "between switches. Switches exchange BPDU frames to elect a 'root bridge' — the switch "
        "with the lowest Bridge ID — and then block all paths except the shortest tree to the root.",
        "A rogue bridge can win the root election unexpectedly, forcing all traffic through itself "
        "and causing 30–50 second outages every time STP reconverges. Mesh WiFi nodes connected "
        "via Ethernet are a common source. NetSentinel's Rogue Bridge scanner captures BPDU frames "
        "and flags any switch that has claimed the root role unexpectedly.",
        "Rogue Bridge (STP)",
    ),
}


class _ContextPanel(QFrame):
    """Collapsible 'Why this protocol matters' panel shown below the step description."""

    navigate_to: "pyqtSignal"  # declared as class attr so mypy sees it

    def __init__(self, parent=None):
        from PyQt6.QtCore import pyqtSignal as _ps
        # pyqtSignal must be on the class, not the instance — use a thin wrapper
        super().__init__(parent)
        self.setObjectName("ctxPanel")
        self.setStyleSheet(
            f"QFrame#ctxPanel {{ background:transparent; border:none; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toggle bar
        self._toggle = QPushButton("  ▸  Why this protocol matters")
        self._toggle.setCheckable(True)
        self._toggle.setStyleSheet(
            f"QPushButton {{ background:transparent; border:none;"
            f" border-top:1px solid {BORDER}; color:{TEXT_MUTED}; font-size:11px;"
            f" font-weight:600; text-align:left; padding:6px 12px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:checked {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        self._toggle.toggled.connect(self._on_toggle)
        root.addWidget(self._toggle)

        # Expanded body
        self._body = QFrame()
        self._body.setVisible(False)
        self._body.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0; }}"
        )
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(16, 12, 16, 12)
        body_lay.setSpacing(8)

        self._why_lbl = QLabel()
        self._why_lbl.setWordWrap(True)
        self._why_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        body_lay.addWidget(self._why_lbl)

        self._wrong_lbl = QLabel()
        self._wrong_lbl.setWordWrap(True)
        self._wrong_lbl.setStyleSheet(
            f"font-size:12px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        body_lay.addWidget(self._wrong_lbl)

        self._nav_btn = QPushButton()
        self._nav_btn.setFixedHeight(28)
        self._nav_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; border:1px solid {ACCENT};"
            f" color:{ACCENT}; border-radius:4px; font-size:11px; font-weight:600;"
            f" padding:0 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        self._nav_btn.setVisible(False)
        body_lay.addWidget(self._nav_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        root.addWidget(self._body)
        self._nav_target = ""

    def set_protocol(self, key: str, on_navigate) -> None:
        why, wrong, nav_label = _PROTOCOL_CONTEXT.get(key, ("", "", ""))
        self._why_lbl.setText(why)
        self._wrong_lbl.setText(wrong)
        self._nav_target = nav_label
        if nav_label:
            self._nav_btn.setText(f"▶  Open {nav_label} scan")
            self._nav_btn.setVisible(True)
            try:
                self._nav_btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._nav_btn.clicked.connect(lambda: on_navigate(nav_label))
        else:
            self._nav_btn.setVisible(False)

    def _on_toggle(self, checked: bool) -> None:
        self._toggle.setText(
            "  ▾  Why this protocol matters" if checked else "  ▸  Why this protocol matters"
        )
        self._body.setVisible(checked)


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

    navigate_to = pyqtSignal(str)  # emitted when context panel nav button is clicked

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

    def load_from_event(self, entry) -> None:
        """Pre-select a protocol based on a log entry's event type and switch to it."""
        if getattr(entry, "arp_event", "") and entry.arp_event:
            self._select_protocol("ARP")
        elif getattr(entry, "dns_ms", -1) >= 0:
            self._select_protocol("DNS")
        else:
            self._select_protocol("ARP")

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
            _defn = get_definition(key)
            btn.setToolTip(f"{sub}\n\n{_defn}" if _defn else sub)
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
        # Curriculum badges placeholder — populated in _select_protocol
        self._badge_row = QHBoxLayout()
        self._badge_row.setSpacing(4)
        tb_lay.addLayout(self._badge_row)
        tb_lay.addStretch()
        canvas_lay.addWidget(title_bar)

        # Empty state shown when scan data is missing for selected protocol
        self._placeholder = QWidget()
        _ph_lay = QVBoxLayout(self._placeholder)
        _ph_lay.setContentsMargins(32, 32, 32, 32)
        _ph_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _ph_icon = QLabel("◎")
        _ph_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _ph_icon.setStyleSheet(
            f"font-size:32px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        self._placeholder_msg = QLabel("No capture session active")
        self._placeholder_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder_msg.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" background:transparent; border:none;"
        )
        _ph_sub = QLabel("Animated diagram of the protocols your network is speaking right now.")
        _ph_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _ph_sub.setWordWrap(True)
        _ph_sub.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        _ph_cta = QPushButton("▶  Start Scan")
        _ph_cta.setFixedHeight(30)
        _ph_cta.setCursor(Qt.CursorShape.PointingHandCursor)
        _ph_cta.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; font-size:11px; font-weight:600; padding:0 16px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        _ph_cta.clicked.connect(lambda: self.navigate_to.emit("Home"))
        _ph_lay.addWidget(_ph_icon)
        _ph_lay.addWidget(self._placeholder_msg)
        _ph_lay.addSpacing(4)
        _ph_lay.addWidget(_ph_sub)
        _ph_lay.addSpacing(10)
        _ph_cta_row = QHBoxLayout()
        _ph_cta_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _ph_cta_row.addWidget(_ph_cta)
        _ph_lay.addLayout(_ph_cta_row)
        self._placeholder.setVisible(False)
        canvas_lay.addWidget(self._placeholder)

        # The animation canvas
        self._canvas = ProtocolCanvas()
        self._canvas.setMinimumHeight(120)
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

        # "Why this matters" collapsible panel
        self._context_panel = _ContextPanel()
        bl.addWidget(self._context_panel)

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
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        return btn

    def _style_proto_btns(self) -> None:
        for key, btn in self._proto_btns.items():
            active = (key == self._active_key)
            btn.setStyleSheet(
                f"QPushButton {{ border-radius:4px; font-size:11px; font-weight:bold; padding:0 8px;"
                f" background:{'%s' % ACCENT if active else 'transparent'};"
                f" color:{WHITE if active else TEXT_SECONDARY};"
                f" border:1px solid {'%s' % ACCENT if active else BORDER}; }}"
                f"QPushButton:hover {{ background:{ACCENT}; color:{WHITE}; }}"
                f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
            )
            btn.setChecked(active)

    # ── Protocol selection ─────────────────────────────────────────────────────

    def select_protocol(self, key: str) -> None:
        """Public API: navigate to and pre-select a protocol by key (e.g. "ARP", "DNS")."""
        self._select_protocol(key)

    def _select_protocol(self, key: str) -> None:
        self._active_key = key
        self._style_proto_btns()
        if hasattr(self, "_context_panel"):
            self._context_panel.set_protocol(key, self._on_context_navigate)
        # Refresh curriculum badges for selected protocol
        self._refresh_protocol_badges(key)

        scene = self._build_scene(key)

        if scene.missing_data_msg:
            self._placeholder_msg.setText(scene.missing_data_msg)
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

    def _refresh_protocol_badges(self, key: str) -> None:
        """Update curriculum objective badges in the canvas title bar."""
        if not hasattr(self, "_badge_row"):
            return
        # Clear existing badges
        while self._badge_row.count():
            item = self._badge_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        try:
            from ui.widgets.objective_badge import ObjectiveBadge
            for badge in ObjectiveBadge.for_protocol(key, self):
                self._badge_row.addWidget(badge)
        except Exception:
            pass

    def _build_scene(self, key: str) -> ProtocolSceneData:
        if key == "ARP":
            scene = build_arp_scene(self._net_info, self._devices)
        elif key == "DNS":
            scene = build_dns_scene(self._net_info, self._diag_result)
        elif key == "TCP":
            scene = build_tcp_scene(self._net_info, self._devices)
        elif key == "DHCP":
            scene = build_dhcp_scene(self._net_info)
        elif key == "STP":
            scene = build_stp_scene(self._m2_result)
        else:
            scene = build_arp_scene(self._net_info, self._devices)
        self._enrich_scene_nodes(scene)
        return scene

    # ── Inventory name overlay (VIZ-7) ────────────────────────────────────────

    def _build_ip_name_map(self) -> Dict[str, str]:
        """Return ip → best-known hostname from last scan device list."""
        result: Dict[str, str] = {}
        for d in self._devices:
            if isinstance(d, dict):
                ip   = d.get("ip", "") or ""
                name = d.get("hostname", "") or d.get("vendor", "") or ""
            else:
                ip   = getattr(d, "ip",       "") or ""
                name = (getattr(d, "hostname", "") or
                        getattr(d, "vendor",   "") or "")
            if ip and name and name != ip:
                result[ip] = name
        return result

    def _enrich_scene_nodes(self, scene: ProtocolSceneData) -> None:
        """Overlay scan hostnames onto node labels where the IP is known (in-place)."""
        name_map = self._build_ip_name_map()
        if not name_map:
            return
        for node in scene.nodes:
            m = _IP_RE.search(node.label)
            if not m:
                continue
            ip = m.group(1)
            hostname = name_map.get(ip, "")
            if not hostname:
                continue
            # Replace node label: hostname on line 1, IP on line 2
            node.label = f"{hostname}\n{ip}"

    # ── Playback controls ──────────────────────────────────────────────────────

    def _on_context_navigate(self, label: str) -> None:
        self.navigate_to.emit(label)

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
