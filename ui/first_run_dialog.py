"""
FirstRunDialog — 3-step action wizard shown on first launch.

Step 1: Scan your network  (auto-triggers Run Scan via parent Dashboard)
Step 2: Run a speed test   (opens Speed Test page)
Step 3: See your Network Grade (opens Network Grade page)

After finishing the wizard the user lands on the HomePage with all
3 mini-cards populated.  Skippable at any step.

Architecture rules:
  • All colours from ui.styles — no hardcoded hex values.
  • No blocking I/O.  All actions dispatched via the parent Dashboard.
  • QSettings key: "ui/first_run_done"
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, BG_CARD, BG_DARK, BORDER, GREEN, TEXT_PRIMARY, TEXT_SECONDARY,
    NAV_BAR, AMBER, BG_HOVER,
)

_FIRST_RUN_KEY = "ui/first_run_done"


def should_show_first_run() -> bool:
    """Return True if the first-run wizard has never been completed."""
    qs = QSettings("NetSentinel", "NetSentinel")
    return not qs.value(_FIRST_RUN_KEY, False, type=bool)


def mark_first_run_done() -> None:
    """Persist that the first-run wizard has been completed."""
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue(_FIRST_RUN_KEY, True)


# ── Step definitions ──────────────────────────────────────────────────────────

_STEPS = [
    {
        "number": "1",
        "colour": ACCENT,
        "title": "Scan your network",
        "body": (
            "NetSentinel will sweep your subnet using ARP and ICMP to discover "
            "every device — phones, laptops, smart TVs, and IoT gadgets.\n\n"
            "This takes 10–30 seconds on most home networks."
        ),
        "action_label": "\u25b6\u2002Start scan",
        "action_key": "scan",
        "action_nav": None,
    },
    {
        "number": "2",
        "colour": AMBER,
        "title": "Run a speed test",
        "body": (
            "Measure your actual download and upload speeds. Results populate "
            "the Speed card on your Home page."
        ),
        "action_label": "\u26a1\u2002Open Speed Test",
        "action_key": "speed",
        "action_nav": "Speed Test",
    },
    {
        "number": "3",
        "colour": GREEN,
        "title": "See your Network Grade",
        "body": (
            "NetSentinel grades your network A\u2013F across latency, packet loss, "
            "DNS reliability, device security, uptime, open ports, and more."
        ),
        "action_label": "\u25fc\u2002View Network Grade",
        "action_key": "grade",
        "action_nav": "Network Grade",
    },
]


# ── Step card ─────────────────────────────────────────────────────────────────

class _StepCard(QFrame):
    action_clicked = pyqtSignal(str)

    def __init__(self, step: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._key = step["action_key"]
        self._done = False
        self.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(8)

        # Badge + title
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        badge = QLabel(step["number"])
        badge.setFixedSize(28, 28)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"font-size:14px; font-weight:bold; color:{BG_CARD};"
            f" background:{step['colour']}; border-radius:14px; border:none;"
        )
        title = QLabel(step["title"])
        title.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        hdr.addWidget(badge)
        hdr.addWidget(title, 1)
        lay.addLayout(hdr)

        # Body
        body = QLabel(step["body"])
        body.setWordWrap(True)
        body.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none; padding-left:38px;"
        )
        lay.addWidget(body)

        # Action button
        btn_row = QHBoxLayout()
        btn_row.addSpacing(38)
        self._btn = QPushButton(step["action_label"])
        self._btn.setFixedHeight(26)
        self._btn.setStyleSheet(
            f"QPushButton {{ background:{step['colour']}; color:{BG_CARD};"
            f" border:none; border-radius:3px;"
            f" font-size:11px; font-weight:bold; padding:0 14px; }}"
            f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_SECONDARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._btn.clicked.connect(lambda: self.action_clicked.emit(self._key))

        self._done_lbl = QLabel("\u2713\u2002Done")
        self._done_lbl.setStyleSheet(
            f"font-size:11px; color:{GREEN}; background:transparent; border:none;"
        )
        self._done_lbl.setVisible(False)

        btn_row.addWidget(self._btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(self._done_lbl)
        btn_row.addStretch()
        lay.addLayout(btn_row)

    def mark_done(self) -> None:
        self._done = True
        self._btn.setEnabled(False)
        self._done_lbl.setVisible(True)


# ── Main dialog ───────────────────────────────────────────────────────────────

class FirstRunDialog(QDialog):
    """
    3-step action wizard.  Parent must be the Dashboard window.

    Usage::
        if should_show_first_run():
            FirstRunDialog(parent=window).exec()
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Get started with NetSentinel")
        self.setModal(True)
        self.setFixedSize(560, 545)
        self.setStyleSheet(
            f"QDialog {{ background:{BG_DARK}; border:1px solid {BORDER}; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(50)
        hdr.setStyleSheet(f"background:{NAV_BAR};")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("Welcome to NetSentinel")
        title_lbl.setStyleSheet(
            f"color:{BG_CARD}; font-size:13px; font-weight:bold; background:transparent;"
        )
        sub_lbl = QLabel("Three steps to populate your Home page")
        sub_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent;"
        )
        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()
        hdr_lay.addWidget(sub_lbl)
        outer.addWidget(hdr)

        # Cards
        cards_w = QWidget()
        cards_w.setStyleSheet(f"background:{BG_DARK};")
        cards_lay = QVBoxLayout(cards_w)
        cards_lay.setContentsMargins(16, 14, 16, 8)
        cards_lay.setSpacing(10)

        self._cards: list[_StepCard] = []
        for step in _STEPS:
            card = _StepCard(step, parent=cards_w)
            card.action_clicked.connect(self._on_action)
            self._cards.append(card)
            cards_lay.addWidget(card)

        # GeoLite2 info note
        geo_frame = QFrame()
        geo_frame.setStyleSheet(
            f"QFrame {{ background:{BG_HOVER}; border:1px solid {BORDER}; }}"
        )
        geo_lay = QHBoxLayout(geo_frame)
        geo_lay.setContentsMargins(12, 8, 12, 8)
        geo_lay.setSpacing(8)
        geo_icon = QLabel("⬡")
        geo_icon.setStyleSheet(
            f"font-size:14px; color:{ACCENT}; background:transparent; border:none;"
        )
        geo_text = QLabel(
            f"<b>Geo Map</b> &mdash; requires the free MaxMind GeoLite2-City database "
            f"(<tt>GeoLite2-City.mmdb</tt>). "
            f"A \"Download DB\" button on the Geo Map page will guide you through it."
        )
        geo_text.setWordWrap(True)
        geo_text.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        geo_lay.addWidget(geo_icon)
        geo_lay.addWidget(geo_text, 1)
        cards_lay.addWidget(geo_frame)

        cards_lay.addStretch()
        outer.addWidget(cards_w, 1)

        # Footer
        footer = QFrame()
        footer.setFixedHeight(52)
        footer.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border-top:1px solid {BORDER}; }}"
        )
        foot_lay = QHBoxLayout(footer)
        foot_lay.setContentsMargins(20, 0, 20, 0)
        foot_lay.setSpacing(8)

        self._status_lbl = QLabel(
            "You\u2019re in Home mode \u2014 only the essentials are shown. "
            "Click the mode pill in the sidebar to unlock more."
        )
        self._status_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._status_lbl.setWordWrap(True)
        foot_lay.addWidget(self._status_lbl, 1)

        btn_skip = QPushButton("Skip")
        btn_skip.setFixedHeight(26)
        btn_skip.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; border-radius:3px;"
            f" font-size:11px; padding:0 12px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}"
        )
        btn_skip.clicked.connect(self._finish)
        foot_lay.addWidget(btn_skip)

        btn_finish = QPushButton("Finish \u2192")
        btn_finish.setFixedHeight(26)
        btn_finish.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{BG_CARD};"
            f" border:none; border-radius:3px;"
            f" font-size:11px; font-weight:bold; padding:0 16px; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        btn_finish.clicked.connect(self._finish)
        foot_lay.addWidget(btn_finish)

        outer.addWidget(footer)

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _on_action(self, key: str) -> None:
        p = self.parent()
        step = next((s for s in _STEPS if s["action_key"] == key), None)
        card = next((c for c in self._cards if c._key == key), None)

        if p is not None and step is not None:
            if key == "scan" and hasattr(p, "_start_full_scan"):
                p._start_full_scan()
            elif step["action_nav"] and hasattr(p, "_nav_go_to"):
                # Standard mode has all nav labels; switch out of Home mode first
                if getattr(p, "_nav_mode", "standard") == "home" and hasattr(p, "_set_mode"):
                    p._set_mode("standard")
                p._nav_go_to(step["action_nav"])

        if card is not None:
            card.mark_done()

        if all(c._done for c in self._cards):
            self._status_lbl.setText(
                "All steps complete! Your Home page is now populated."
            )

    def _finish(self) -> None:
        mark_first_run_done()
        p = self.parent()
        if p is not None and hasattr(p, "_nav_go_to"):
            p._nav_go_to("Home")
        self.accept()

