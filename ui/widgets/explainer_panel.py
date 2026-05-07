"""
ExplainerPanel — collapsible "What just happened, technically?" panel.

Usage:
    panel = ExplainerPanel("rogue_device")
    panel.navigate_to.connect(dashboard._nav_rail_go_to)
    lay.addWidget(panel)

page_id keys: "rogue_device", "dns_stability", "broadcast_storm", "stp_rogue"
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ui.styles import ACCENT, BG_CARD, BG_DARK, BORDER, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY


# ── Per-page content ──────────────────────────────────────────────────────────
# (explanation_text, protocol_key_for_visualizer)

_CONTENT: dict[str, tuple[str, str]] = {
    "rogue_device": (
        "ARP is how devices on your network discover each other's hardware addresses. "
        "Every device broadcasts an ARP request ('who has IP x?') and the owner replies with its MAC. "
        "There is no authentication — any device can claim any IP, which is how ARP spoofing works. "
        "NetSentinel reads your ARP table to map every IP-to-MAC binding and flags any MAC whose "
        "manufacturer doesn't match a known device, or that appeared unexpectedly since the last scan.",
        "ARP",
    ),
    "dns_stability": (
        "DNS is the internet's address book — it translates hostnames like 'google.com' into IP addresses. "
        "Every web request, email, and app connection starts with a DNS lookup. "
        "When DNS is slow or fails, everything feels broken even if your connection is fine. "
        "NetSentinel measures your system DNS resolver's latency on each ping cycle "
        "and records the exact timestamps of any failures so you can correlate them with outages.",
        "DNS",
    ),
    "broadcast_storm": (
        "Ethernet broadcasts are short announcements sent to every device on a subnet. "
        "Normally, broadcasts are rare. A broadcast storm occurs when a network loop causes frames "
        "to circulate endlessly — each frame generating more broadcasts until bandwidth is saturated. "
        "STP (Spanning Tree Protocol) prevents loops by blocking redundant paths, but a misbehaving "
        "switch or a rogue bridge can overwhelm STP and trigger storms anyway.",
        "STP",
    ),
    "stp_rogue": (
        "STP (Spanning Tree Protocol) prevents Layer 2 loops by electing one 'root bridge' — "
        "the switch with the lowest Bridge ID. All other switches route traffic through the root. "
        "A rogue bridge is a device that wins the root election unexpectedly, forcing all traffic "
        "through itself. This creates a hidden single point of failure, causes periodic drops as "
        "STP reconverges (typically 30–50 seconds), and gives the rogue device visibility into all traffic.",
        "STP",
    ),
    "tcp_connections": (
        "Every TCP connection goes through a three-way handshake: SYN → SYN-ACK → ACK. "
        "The Active Connections view shows the state of every open socket on this machine "
        "and which process owns it. ESTABLISHED means data is flowing; CLOSE_WAIT means the "
        "remote side closed the connection but this machine hasn't acknowledged it yet. "
        "Unexpected connections to unusual ports or foreign IPs are worth investigating.",
        "TCP",
    ),
}


# ── Widget ────────────────────────────────────────────────────────────────────

class ExplainerPanel(QFrame):
    """Collapsible 'What just happened, technically?' strip for detection pages."""

    navigate_to = pyqtSignal(str)  # emit page label when user clicks "See diagram"

    def __init__(self, page_id: str, parent=None):
        super().__init__(parent)
        content, protocol = _CONTENT.get(page_id, ("", ""))
        self._protocol = protocol

        self.setObjectName("explainerPanel")
        self.setStyleSheet(
            f"QFrame#explainerPanel {{ background:{BG_DARK}; border-top:1px solid {BORDER};"
            " border-radius:0px; }"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toggle bar ────────────────────────────────────────────────────────
        self._toggle_btn = QPushButton("  ▸  What just happened, technically?")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_DARK}; border:none; border-top:1px solid {BORDER};"
            f" color:{TEXT_MUTED}; font-size:11px; font-weight:600;"
            f" text-align:left; padding:6px 12px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:{BG_CARD}; }}"
            f"QPushButton:checked {{ color:{TEXT_PRIMARY}; }}"
        )
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.toggled.connect(self._on_toggle)
        root.addWidget(self._toggle_btn)

        # ── Expanded content ──────────────────────────────────────────────────
        self._body = QWidget()
        self._body.setVisible(False)
        self._body.setStyleSheet(f"background:{BG_CARD}; border-top:1px solid {BORDER};")
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(16, 12, 16, 12)
        body_lay.setSpacing(8)

        if content:
            text_lbl = QLabel(content)
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet(
                f"font-size:12px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
            )
            body_lay.addWidget(text_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        if protocol:
            viz_btn = QPushButton(f"▶  See {protocol} animated diagram")
            viz_btn.setFixedHeight(28)
            viz_btn.setStyleSheet(
                f"QPushButton {{ background:transparent; border:1px solid {ACCENT};"
                f" color:{ACCENT}; border-radius:4px; font-size:11px; font-weight:600;"
                f" padding:0 12px; }}"
                f"QPushButton:hover {{ background:{ACCENT}; color:#FFFFFF; }}"
            )
            viz_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            viz_btn.clicked.connect(lambda: self.navigate_to.emit("Protocol Visualizer"))
            btn_row.addWidget(viz_btn)

        btn_row.addStretch()
        body_lay.addLayout(btn_row)
        root.addWidget(self._body)

        # Hide the whole panel if no content is configured for this page
        if not content:
            self.hide()

    def _on_toggle(self, checked: bool) -> None:
        self._toggle_btn.setText(
            "  ▾  What just happened, technically?"
            if checked else
            "  ▸  What just happened, technically?"
        )
        self._body.setVisible(checked)
