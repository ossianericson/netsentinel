"""
NpcapMissingBanner — thin warning bar shown on pages that require
Npcap (Windows) or libpcap (macOS/Linux) when the driver is absent.

Conforms to the NetSentinel design system:
  • Height: 28px fixed (Rule 7 — admin warning is thin, never a card)
  • Background: ADMIN_WARN_BG, bottom border ADMIN_WARN_BORDER
  • ⚠ icon + message text + clickable download link (QDesktopServices)

Usage::

    from ui.npcap_banner import NpcapMissingBanner
    banner = NpcapMissingBanner()
    lay.addWidget(banner)            # always add it
    # Banner auto-hides itself when the driver is present.
"""

from __future__ import annotations

import platform

from PyQt6.QtCore    import QUrl, Qt
from PyQt6.QtGui     import QDesktopServices
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy

from modules.utils   import is_npcap_available, is_store_app
from ui.styles       import (
    ADMIN_WARN_BG, ADMIN_WARN_BORDER, ADMIN_WARN_FG, ADMIN_WARN_HOVER,
    BG_HOVER,
)

_NPCAP_URL = "https://npcap.com/#download"

# Platform-specific install hint shown in the message
_INSTALL_HINT: dict[str, str] = {
    "Windows": "Npcap is required for packet capture.",
    "Darwin":  "libpcap is required.  Install via: brew install libpcap",
    "Linux":   "libpcap-dev is required.  Install via: sudo apt install libpcap-dev",
}
# Store variant: makes clear the user must install outside the Store sandbox
_INSTALL_HINT_STORE = (
    "Npcap must be installed manually — "
    "Windows Store apps cannot install system drivers."
)
_DOWNLOAD_LABEL: dict[str, str] = {
    "Windows": "Download Npcap →",
    "Darwin":  "View download →",
    "Linux":   "View download →",
}


class NpcapMissingBanner(QFrame):
    """
    Thin 28 px amber warning bar.  Hides itself automatically if the
    packet-capture driver is already installed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        available = is_npcap_available()
        self.setVisible(not available)
        if available:
            return   # nothing to build — widget will be invisible

        self.setFixedHeight(28)
        self.setStyleSheet(
            f"QFrame {{ background:{ADMIN_WARN_BG};"
            f" border:none; border-bottom:1px solid {ADMIN_WARN_BORDER}; }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 16, 0)
        lay.setSpacing(8)

        icon = QLabel("⚠")
        icon.setStyleSheet(
            f"font-size:12px; color:{ADMIN_WARN_FG}; background:transparent; border:none;"
        )

        sys_name = platform.system()
        if sys_name == "Windows" and is_store_app():
            msg_text = _INSTALL_HINT_STORE
            dl_label = "Get Npcap at npcap.com →"
        else:
            msg_text = _INSTALL_HINT.get(sys_name, "Packet capture library is required.")
            dl_label = _DOWNLOAD_LABEL.get(sys_name, "View download →")
        msg = QLabel(msg_text)
        msg.setStyleSheet(
            f"font-size:11px; color:{ADMIN_WARN_FG}; background:transparent; border:none;"
        )

        btn = QPushButton(dl_label)
        btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ border:none; background:transparent; font-size:11px;"
            f" font-weight:bold; color:{ADMIN_WARN_FG}; text-decoration:underline; }}"
            f"QPushButton:hover {{ color:{ADMIN_WARN_HOVER}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ADMIN_WARN_FG}; }}"
        )
        btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(_NPCAP_URL)))

        lay.addWidget(icon)
        lay.addWidget(msg)
        lay.addStretch()
        lay.addWidget(btn)
