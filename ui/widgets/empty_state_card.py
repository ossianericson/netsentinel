"""
EmptyStateCard — reusable empty state widget (Sprint A2).

Structure:
    [icon]
    What this page shows  (bold title)
    One sentence describing the data visible after a scan.

    Why it matters
    One sentence on the problem it helps catch.

    [Primary CTA button]

Usage::

    from ui.widgets.empty_state_card import EmptyStateCard

    card = EmptyStateCard(
        icon="◆",
        title="Device Inventory",
        what_it_shows="Every device connected to your network — phones, laptops, smart TVs, routers — with IP, MAC, and manufacturer.",
        why_it_matters="You can't secure a device you don't know exists.",
        btn_label="Scan Network",
    )
    card.clicked.connect(self.scan_requested.emit)
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import styles as _s


class EmptyStateCard(QWidget):
    """
    Informative empty state shown when a page has no scan data yet.

    Signals
    -------
    clicked : ()
        Emitted when the CTA button is clicked.
    """

    clicked = pyqtSignal()

    def __init__(
        self,
        icon: str,
        title: str,
        what_it_shows: str,
        why_it_matters: str,
        btn_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._build(icon, title, what_it_shows, why_it_matters, btn_label)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(
        self,
        icon: str,
        title: str,
        what_it_shows: str,
        why_it_matters: str,
        btn_label: str,
    ) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        # Card frame
        card = QWidget()
        _s.themed_ss(card, "QWidget {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:8px; }}")
        card.setFixedWidth(480)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(32, 28, 32, 28)
        card_lay.setSpacing(12)

        # Icon
        icon_lbl = QLabel(icon)
        _s.themed_ss(icon_lbl, "font-size:32px; color:{ACCENT}; border:none; background:transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(icon_lbl)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setWordWrap(True)
        _s.themed_ss(title_lbl, "font-size:15px; font-weight:bold; color:{TEXT_PRIMARY};"
            " border:none; background:transparent;")
        card_lay.addWidget(title_lbl)

        card_lay.addSpacing(4)

        # "What this page shows"
        show_hdr = QLabel("What this page shows")
        _s.themed_ss(show_hdr, "font-size:10px; font-weight:600; color:{TEXT_SECONDARY}; text-transform:uppercase;"
            " letter-spacing:0.5px; border:none; background:transparent;")
        card_lay.addWidget(show_hdr)

        show_body = QLabel(what_it_shows)
        show_body.setWordWrap(True)
        show_body.setAlignment(Qt.AlignmentFlag.AlignLeft)
        _s.themed_ss(show_body, "font-size:12px; color:{TEXT_PRIMARY}; border:none; background:transparent;")
        card_lay.addWidget(show_body)

        card_lay.addSpacing(4)

        # "Why it matters"
        why_hdr = QLabel("Why it matters")
        _s.themed_ss(why_hdr, "font-size:10px; font-weight:600; color:{TEXT_SECONDARY}; text-transform:uppercase;"
            " letter-spacing:0.5px; border:none; background:transparent;")
        card_lay.addWidget(why_hdr)

        why_body = QLabel(why_it_matters)
        why_body.setWordWrap(True)
        why_body.setAlignment(Qt.AlignmentFlag.AlignLeft)
        _s.themed_ss(why_body, "font-size:12px; color:{TEXT_PRIMARY}; border:none; background:transparent;")
        card_lay.addWidget(why_body)

        card_lay.addSpacing(8)

        # CTA button
        btn = QPushButton(btn_label)
        btn.setFixedHeight(34)
        _s.themed_ss(btn, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:4px; font-size:12px; font-weight:bold;"
            " padding:0 20px; }}"
            "QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            "QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}")
        btn.clicked.connect(self.clicked.emit)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn)
        btn_row.addStretch()
        card_lay.addLayout(btn_row)

        # Centre the card horizontally
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(card)
        h.addStretch()
        outer.addLayout(h)
        outer.addStretch()
