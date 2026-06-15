"""
ui/pages/troubleshoot_page.py — Symptom-First Troubleshooting Hub (Sprint 3, S3-1 + S3-2)

Eight user-language symptom tiles that route to the correct existing tool with the
right context pre-set — no duplication of the diagnosis engine, purely a routing hub.

Signals
-------
navigate_to      : pyqtSignal(str)  — page label to navigate to directly
diagnose_symptom : pyqtSignal(str)  — symptom key to preset on DiagnosisPage
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, BG_CARD, BG_DARK, BG_HOVER, BORDER,
    RED, TEXT_PRIMARY, TEXT_SECONDARY,
)
from ui.widgets.page_header import PageHeaderBar

# ── Tile definitions ──────────────────────────────────────────────────────────
# (label, description, icon, action_type, action_arg, color_hint)
# action_type: "diagnose" → diagnose_symptom signal; "navigate" → navigate_to signal

_TILES: list[tuple[str, str, str, str, str, str]] = [
    (
        "Streaming is buffering or won't play",
        "Netflix, Disney+, YouTube, Spotify",
        "▶",
        "navigate",
        "Service Diagnostics",
        ACCENT,
    ),
    (
        "Gaming lag, high ping or disconnects",
        "Xbox, PlayStation, Steam, online multiplayer",
        "◈",
        "navigate",
        "Service Diagnostics",
        RED,
    ),
    (
        "My internet is slow",
        "Pages load slowly, downloads take too long",
        "⟳",
        "diagnose",
        "slow",
        AMBER,
    ),
    (
        "A website or app isn't loading",
        "Error page, timeout, can't reach a service",
        "◆",
        "navigate",
        "Service Diagnostics",
        AMBER,
    ),
    (
        "Device won't connect to the network",
        "Can't get on Wi-Fi or Ethernet, no IP",
        "○",
        "diagnose",
        "noconn",
        RED,
    ),
    (
        "Wi-Fi keeps dropping",
        "Connection falls off repeatedly",
        "◉",
        "diagnose",
        "dropping",
        AMBER,
    ),
    (
        "Something is using all my bandwidth",
        "Other devices are slow, network feels congested",
        "■",
        "navigate",
        "App Traffic",
        AMBER,
    ),
    (
        "There's a suspicious device on my network",
        "Unknown device, unexpected activity",
        "▲",
        "navigate",
        "Devices",
        RED,
    ),
]


class TroubleshootPage(QWidget):
    """User-language routing hub — pick a symptom, get sent to the right tool."""

    navigate_to      = pyqtSignal(str)
    diagnose_symptom = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"QWidget {{ background:{BG_DARK}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addWidget(
            PageHeaderBar(
                "Troubleshoot",
                subtitle="What's happening on your network? Pick the closest description — NetSentinel will route you straight to the right tool.",
            )
        )

        # "Not sure?" helper strip
        unsure_row = QHBoxLayout()
        unsure_lbl = QLabel("Not sure what the problem is?")
        unsure_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        unsure_btn = QPushButton("Run a full diagnosis →")
        unsure_btn.setFlat(True)
        unsure_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        unsure_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; text-align:left; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:{BG_HOVER}; }}"
        )
        unsure_btn.clicked.connect(lambda: self.navigate_to.emit("What's Wrong?"))
        unsure_row.addWidget(unsure_lbl)
        unsure_row.addWidget(unsure_btn)
        unsure_row.addStretch()
        root.addLayout(unsure_row)

        # Scrollable tile grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG_DARK}; border:none; }}")

        grid_container = QWidget()
        grid_container.setStyleSheet(f"background:{BG_DARK};")
        grid = QGridLayout(grid_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        cols = 2
        for i, (label, desc, icon, action_type, action_arg, color) in enumerate(_TILES):
            card = self._make_tile(label, desc, icon, action_type, action_arg, color)
            grid.addWidget(card, i // cols, i % cols)

        scroll.setWidget(grid_container)
        root.addWidget(scroll, 1)

        # Footer ISP shortcut
        footer = QHBoxLayout()
        footer_lbl = QLabel("Want to know if it's your ISP or your router?")
        footer_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        isp_btn = QPushButton("Quick ISP test on What's Wrong? →")
        isp_btn.setFlat(True)
        isp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        isp_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; text-align:left; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:{BG_HOVER}; }}"
        )
        isp_btn.clicked.connect(lambda: self.navigate_to.emit("What's Wrong?"))
        footer.addWidget(footer_lbl)
        footer.addWidget(isp_btn)
        footer.addStretch()
        root.addLayout(footer)

    def _make_tile(
        self,
        label: str,
        desc: str,
        icon: str,
        action_type: str,
        action_arg: str,
        color: str,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("troubleshootTile")
        card.setStyleSheet(
            f"QFrame#troubleshootTile {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:6px; }}"
            f"QFrame#troubleshootTile:hover {{ border-color:{color}; }}"
        )

        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)

        header_row = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(22)
        icon_lbl.setStyleSheet(
            f"font-size:16px; color:{color}; background:transparent; border:none;"
        )
        title_lbl = QLabel(label)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" background:transparent; border:none;"
        )
        header_row.addWidget(icon_lbl)
        header_row.addWidget(title_lbl, 1)
        lay.addLayout(header_row)

        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        lay.addWidget(desc_lbl)

        if action_type == "diagnose":
            action_label = "Diagnose this →"
        else:
            _nav_labels = {
                "Service Diagnostics": "Run Service Diagnostics →",
                "App Traffic":         "Check App Traffic →",
                "Devices":             "View Devices →",
            }
            action_label = _nav_labels.get(action_arg, f"Open {action_arg} →")

        btn = QPushButton(action_label)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ color:{color}; font-size:11px; background:transparent;"
            f" border:none; padding:0; text-align:left; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:{BG_HOVER}; }}"
        )

        if action_type == "diagnose":
            btn.clicked.connect(
                lambda _=False, k=action_arg: self.diagnose_symptom.emit(k)
            )
        else:
            btn.clicked.connect(
                lambda _=False, t=action_arg: self.navigate_to.emit(t)
            )

        lay.addWidget(btn)
        return card
