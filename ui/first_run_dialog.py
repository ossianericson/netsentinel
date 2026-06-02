"""
WelcomeOverlay — shown on first ever launch.

One screen.  One action.  User clicks "Scan my network →" and they are done.
The home page suggestions (speed test, network grade) handle the rest.

Architecture:
  • No QDialog / exec() — the overlay is a QWidget child of the main window.
  • Fade-in animation matches the CoachMarkOverlay pattern.
  • Marks both "ui/first_run_done" and "onboarding_v6_done" on dismiss.
  • All colours from ui.styles — no hardcoded hex.

Backward-compatible exports:
  should_show_first_run()  — used by app.py and dashboard.py
  mark_first_run_done()    — used internally and by tests
  WelcomeOverlay           — the new primary class
  FirstRunDialog           — thin alias kept so existing imports don't break
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSettings,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, BG_CARD, BORDER,
    GREEN, OVERLAY_BG, OVERLAY_BG2, OVERLAY_BG3,
    OVERLAY_BLUE2, OVERLAY_FG2, OVERLAY_FG3, OVERLAY_ORANGE,
    STATUS_OFFLINE, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)

_FIRST_RUN_KEY = "ui/first_run_done"
_COACH_KEY     = "onboarding_v6_done"


# ── Public helpers (used by app.py, dashboard.py, tests) ─────────────────────

def should_show_first_run() -> bool:
    """Return True if the welcome overlay has never been completed."""
    qs = QSettings("NetSentinel", "NetSentinel")
    return not qs.value(_FIRST_RUN_KEY, False, type=bool)


def mark_first_run_done() -> None:
    """Persist that onboarding is complete (both keys)."""
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue(_FIRST_RUN_KEY, True)
    qs.setValue(_COACH_KEY, True)


# ── Welcome overlay ───────────────────────────────────────────────────────────

_SLIDES = [
    {
        "icon":  "◆",
        "color": ACCENT,
        "title": "Welcome to NetSentinel",
        "body":  (
            "A professional-grade network scanner for your home or office. "
            "Map every device, spot security issues, and monitor performance — "
            "no prior knowledge required."
        ),
    },
    {
        "icon":  "◉",
        "color": GREEN,
        "title": "Discover & protect",
        "body":  (
            "Every phone, TV, smart speaker and printer appears on your map in "
            "seconds. Rogue devices, open ports and weak credentials are flagged "
            "the moment they appear."
        ),
    },
    {
        "icon":  "▶",
        "color": OVERLAY_ORANGE,
        "title": "Monitor over time",
        "body":  (
            "Track internet speed, latency, 5G signal and uptime continuously. "
            "Get a plain-English weekly summary of what changed — and what to "
            "do about it."
        ),
    },
]

# Total slide count including the interactive notification slide
_TOTAL_SLIDES = len(_SLIDES) + 1
_NOTIF_SLIDE_IDX = len(_SLIDES)   # index 3


class WelcomeOverlay(QWidget):
    """
    Full-window welcome overlay shown on first launch.

    Three slides (Discover, Protect, Monitor) with Back/Next navigation and
    progress dots.  The final slide has "Scan my network →" as the CTA.

    Signals
    -------
    start_scan_requested — user clicked "Scan my network →"
    dismissed            — user clicked "Skip"
    """

    start_scan_requested = pyqtSignal()
    dismissed            = pyqtSignal()

    _CARD_W = 440
    _CARD_H = 440

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setGeometry(parent.rect())
        self._slide_idx = 0
        self._card = self._build_card()
        self._position_card()

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(280)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("welcomeCard")
        card.setFixedSize(self._CARD_W, self._CARD_H)
        card.setStyleSheet(
            "QFrame#welcomeCard { background:OVERLAY_BG; border:1px solid OVERLAY_BG3;"
            " border-radius:16px; }"
        )

        root = QVBoxLayout(card)
        root.setContentsMargins(36, 32, 36, 24)
        root.setSpacing(0)

        # ── App brand strip ───────────────────────────────────────────────────
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)

        logo_lbl = QLabel()
        logo_lbl.setFixedSize(28, 28)
        logo_lbl.setStyleSheet("background:transparent; border:none;")
        try:
            base = (
                Path(sys._MEIPASS)
                if getattr(sys, "frozen", False)
                else Path(__file__).parent.parent
            )
            px = QPixmap(str(base / "assets" / "icons" / "netsentinel.png"))
            if not px.isNull():
                logo_lbl.setPixmap(
                    px.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )
        except Exception:
            logo_lbl.setText("◆")
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_lbl.setStyleSheet(
                f"color:{ACCENT}; font-size:18px; background:transparent; border:none;"
            )

        app_name_lbl = QLabel("NetSentinel")
        app_name_lbl.setStyleSheet(
            "color:OVERLAY_FG3; font-size:12px; font-weight:600;"
            " background:transparent; border:none;"
        )
        brand_row.addWidget(logo_lbl)
        brand_row.addWidget(app_name_lbl)
        brand_row.addStretch()

        # Skip link (top-right)
        self._skip_btn = QPushButton("Skip")
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.setStyleSheet(
            "QPushButton { background:transparent; color:STATUS_OFFLINE; border:none;"
            " font-size:12px; }"
            "QPushButton:hover { color:OVERLAY_FG3; }"
            "QPushButton:pressed { color:STATUS_OFFLINE; }"
        )
        self._skip_btn.clicked.connect(self._on_skip)
        brand_row.addWidget(self._skip_btn)
        root.addLayout(brand_row)
        root.addSpacing(28)

        # ── Slide content area ────────────────────────────────────────────────
        from PyQt6.QtWidgets import QStackedWidget
        self._slide_stack = QStackedWidget()
        self._slide_stack.setStyleSheet("background:transparent; border:none;")
        for slide in _SLIDES:
            self._slide_stack.addWidget(self._build_slide(slide))
        self._slide_stack.addWidget(self._build_notif_slide())
        root.addWidget(self._slide_stack)
        root.addSpacing(24)

        # ── Progress dots ─────────────────────────────────────────────────────
        dots_row = QHBoxLayout()
        dots_row.setSpacing(8)
        dots_row.addStretch()
        self._dots: list[QLabel] = []
        for i in range(_TOTAL_SLIDES):
            dot = QLabel("●")
            dot.setStyleSheet(
                f"color:{ACCENT}; font-size:10px; background:transparent; border:none;"
                if i == 0 else
                "color:OVERLAY_BG3; font-size:10px; background:transparent; border:none;"
            )
            self._dots.append(dot)
            dots_row.addWidget(dot)
        dots_row.addStretch()
        root.addLayout(dots_row)
        root.addSpacing(20)

        # ── Navigation buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._back_btn = QPushButton("← Back")
        self._back_btn.setFixedHeight(38)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(
            f"QPushButton {{ background:{OVERLAY_BG2}; color:{OVERLAY_FG3}; border:none;"
            f" border-radius:8px; font-size:13px; }}"
            f"QPushButton:hover {{ background:{OVERLAY_BG3}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{OVERLAY_BG}; color:{OVERLAY_FG3}; }}"
        )
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.setVisible(False)

        self._next_btn = QPushButton("Next  →")
        self._next_btn.setFixedHeight(38)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:8px; font-size:13px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{OVERLAY_BLUE2}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        self._next_btn.clicked.connect(self._go_next)

        btn_row.addWidget(self._back_btn)
        btn_row.addWidget(self._next_btn)
        root.addLayout(btn_row)

        return card

    def _build_slide(self, slide: dict) -> QWidget:
        """Build one slide: large icon, title, body text."""
        w = QWidget()
        w.setStyleSheet("background:transparent; border:none;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        icon_lbl = QLabel(slide["icon"])
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"color:{slide['color']}; font-size:48px;"
            " background:transparent; border:none;"
        )
        lay.addWidget(icon_lbl)
        lay.addSpacing(18)

        title_lbl = QLabel(slide["title"])
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "color:WHITE; font-size:20px; font-weight:700;"
            " background:transparent; border:none;"
        )
        lay.addWidget(title_lbl)
        lay.addSpacing(12)

        body_lbl = QLabel(slide["body"])
        body_lbl.setWordWrap(True)
        body_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_lbl.setStyleSheet(
            "color:OVERLAY_FG2; font-size:13px; line-height:1.5;"
            " background:transparent; border:none;"
        )
        lay.addWidget(body_lbl)
        lay.addStretch()

        return w

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go_next(self) -> None:
        last = _TOTAL_SLIDES - 1
        if self._slide_idx < last:
            self._slide_idx += 1
            self._slide_stack.setCurrentIndex(self._slide_idx)
            self._sync_nav()
        else:
            self._save_notif_prefs()
            self._on_scan()

    def _go_back(self) -> None:
        if self._slide_idx > 0:
            self._slide_idx -= 1
            self._slide_stack.setCurrentIndex(self._slide_idx)
            self._sync_nav()

    def _sync_nav(self) -> None:
        last = _TOTAL_SLIDES - 1
        self._back_btn.setVisible(self._slide_idx > 0)
        self._next_btn.setText(
            "Scan my network  →" if self._slide_idx == last else "Next  →"
        )
        for i, dot in enumerate(self._dots):
            dot.setStyleSheet(
                f"color:{ACCENT}; font-size:10px; background:transparent; border:none;"
                if i == self._slide_idx else
                "color:OVERLAY_BG3; font-size:10px; background:transparent; border:none;"
            )

    def _build_notif_slide(self) -> QWidget:
        """Fourth slide: notification preferences (desktop / email / skip)."""
        w = QWidget()
        w.setStyleSheet("background:transparent; border:none;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        icon_lbl = QLabel("◆")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"color:{ACCENT}; font-size:48px; background:transparent; border:none;"
        )
        lay.addWidget(icon_lbl)
        lay.addSpacing(14)

        title_lbl = QLabel("Get notified when something changes")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            "color:WHITE; font-size:18px; font-weight:700;"
            " background:transparent; border:none;"
        )
        lay.addWidget(title_lbl)
        lay.addSpacing(16)

        self._notif_desktop_chk = QCheckBox("Desktop notifications (recommended)")
        self._notif_desktop_chk.setChecked(True)
        self._notif_desktop_chk.setStyleSheet(
            f"color:{OVERLAY_FG2}; font-size:12px; background:transparent; border:none;"
        )
        lay.addWidget(self._notif_desktop_chk)
        lay.addSpacing(10)

        email_row = QHBoxLayout()
        self._notif_email_chk = QCheckBox("Email alerts — send to:")
        self._notif_email_chk.setStyleSheet(
            f"color:{OVERLAY_FG2}; font-size:12px; background:transparent; border:none;"
        )
        self._notif_email_edit = QLineEdit()
        self._notif_email_edit.setPlaceholderText("you@example.com")
        self._notif_email_edit.setFixedWidth(170)
        self._notif_email_edit.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:{BG_CARD};"
            f" border:1px solid {BORDER}; border-radius:4px; padding:3px 6px;"
        )
        self._notif_email_chk.stateChanged.connect(
            lambda s: self._notif_email_edit.setEnabled(
                s == 2  # Qt.CheckState.Checked == 2
            )
        )
        self._notif_email_edit.setEnabled(False)
        email_row.addWidget(self._notif_email_chk)
        email_row.addWidget(self._notif_email_edit)
        email_row.addStretch()
        lay.addLayout(email_row)

        skip_lbl = QLabel("You can always change these in Notifications settings.")
        skip_lbl.setWordWrap(True)
        skip_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        skip_lbl.setStyleSheet(
            f"color:{OVERLAY_FG2}; font-size:10px; background:transparent; border:none;"
        )
        lay.addSpacing(12)
        lay.addWidget(skip_lbl)
        lay.addStretch()

        return w

    def _save_notif_prefs(self) -> None:
        """Persist notification preferences from the onboarding slide."""
        qs = QSettings("NetSentinel", "NetSentinel")
        if hasattr(self, "_notif_desktop_chk"):
            qs.setValue("notif/toast_enabled", self._notif_desktop_chk.isChecked())
        if hasattr(self, "_notif_email_chk") and self._notif_email_chk.isChecked():
            addr = self._notif_email_edit.text().strip()
            if addr:
                qs.setValue("notif/email_enabled", True)
                qs.setValue("notif/email_to", addr)

    # ── Animation ─────────────────────────────────────────────────────────────

    def show_animated(self) -> None:
        self.show()
        self.raise_()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def hide_animated(self, callback=None) -> None:
        self._fade_anim.stop()
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        if callback:
            self._fade_anim.finished.connect(callback)
        self._fade_anim.start()

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(0, 0, 0, 180))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(self.rect())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_card()

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _on_scan(self) -> None:
        mark_first_run_done()
        self.hide_animated(callback=lambda: (self.start_scan_requested.emit(),
                                             self.deleteLater()))

    def _on_skip(self) -> None:
        mark_first_run_done()
        self.hide_animated(callback=lambda: (self.dismissed.emit(),
                                             self.deleteLater()))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _position_card(self) -> None:
        w, h = self.width(), self.height()
        bx = (w - self._CARD_W) // 2
        by = max(24, (h - self._CARD_H) // 2 - 20)
        self._card.move(bx, by)


# ── Backward-compatibility alias ──────────────────────────────────────────────
# app.py and tests import FirstRunDialog; keep it importable but non-functional.

class FirstRunDialog:                           # type: ignore[no-redef]
    """Deprecated.  Use WelcomeOverlay instead.  Kept for import compatibility."""

    def __init__(self, parent=None) -> None:
        pass                                    # no-op — WelcomeOverlay handles this

    def exec(self) -> int:                      # noqa: A003
        return 0                                # no-op
