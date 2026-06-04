"""
onboarding_overlay.py — Full-screen Apple-like onboarding overlay (Sprint I1).

Sits above the entire Dashboard window as a solid white widget.  The dashboard
content is fully rendered behind it so there is no flicker when the overlay
dismisses.

Screen sequence
---------------
  0  Welcome          — "Get Started" or "Skip setup"
  1  Permission       — "Scan my network" (emits scan_requested) or Skip
  2  Scanning         — live progress bar  (Sprint I2 placeholder)
  3  Results reveal   — device count, grade, verdict  (Sprint I2 placeholder)
  4  Devices page     — "Every device, in plain English"  (Sprint I3 placeholder)
  5  Logger running   — "Done — Start exploring"  (Sprint I3 placeholder)
  6  Done             — green checkmark, auto-dismisses after 1.5 s

QSettings key: ui/onboarding_v2_done  (reused — existing users are not reshown)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    ACCENT_LITE,
    BG_CARD,
    BORDER,
    GREEN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WHITE,
)

_SETTINGS_KEY = "ui/onboarding_v2_done"
_TOUR_KEY     = "tour/v1_done"


class OnboardingOverlay(QWidget):
    """Full-screen first-run onboarding overlay."""

    # Emitted when the user clicks "Scan my network" on Screen 1.
    # Connect to dashboard._start_full_scan().
    scan_requested = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        # Solid white background so the dashboard is invisible behind the overlay
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(BG_CARD))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        # Cover the full parent window immediately
        self.setGeometry(parent.rect())
        self.raise_()

        # Keep covering the parent when it resizes
        parent.installEventFilter(self)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Central stacked widget (one page per screen)
        self._stack = QStackedWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._stack)

        self._build_screen_0()
        self._build_screen_1()
        self._build_placeholder(2, "Scanning your network…",
                                "Sprint I2 will show a live progress bar here.")
        self._build_placeholder(3, "Scan complete",
                                "Sprint I2 will show the results reveal here.")
        self._build_placeholder(4, "Every device, in plain English",
                                "Sprint I3 will show a device table preview here.")
        self._build_placeholder(5, "Your connection is being watched",
                                "Sprint I3 will show the RTT sparkline here.")
        self._build_screen_6()

        self._stack.setCurrentIndex(0)

    # ── Parent resize tracking ─────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parent().rect())
        return False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._do_skip()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            idx = self._stack.currentIndex()
            if idx == 1:
                self._on_scan_clicked()
            elif 2 <= idx <= 5:
                self._go_to_screen(idx + 1)
        else:
            super().keyPressEvent(e)

    # ── Screen builders ────────────────────────────────────────────────────────

    def _build_screen_0(self) -> None:
        """Screen 0: Welcome."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        card = _CentreCard(360)
        lay  = card.inner

        # Brand icon
        _base = (
            Path(sys._MEIPASS)
            if getattr(sys, "frozen", False)
            else Path(__file__).parent.parent.parent
        )
        _pix = QPixmap(str(_base / "assets" / "icons" / "netsentinel.png"))
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(64, 64)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background:transparent;")
        if not _pix.isNull():
            icon_lbl.setPixmap(
                _pix.scaled(
                    64, 64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            icon_lbl.setText("N")
            icon_lbl.setStyleSheet(
                f"background:{ACCENT}; color:{WHITE}; border-radius:12px;"
                " font-size:28px; font-weight:bold;"
            )
        lay.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(24)

        title = QLabel("Welcome to NetSentinel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"font-size:28px; font-weight:600; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(title)
        lay.addSpacing(10)

        sub = QLabel("Your network, visible and secured")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"font-size:14px; color:{TEXT_MUTED};"
            " background:transparent; border:none;"
        )
        lay.addWidget(sub)
        lay.addSpacing(44)

        btn_start = _AccentButton("Get Started")
        btn_start.clicked.connect(lambda: self._go_to_screen(1))
        lay.addWidget(btn_start)
        lay.addSpacing(14)

        skip_lbl = _SkipLink("Skip setup →")
        skip_lbl.clicked.connect(self._do_skip)
        lay.addWidget(skip_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

    def _build_screen_1(self) -> None:
        """Screen 1: Permission to scan."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_TopBar(active_dot=0, on_skip=self._do_skip))
        outer.addStretch(1)

        card = _CentreCard(360)
        lay  = card.inner

        from ui.widgets.scan_animation import ScanAnimationWidget
        anim = ScanAnimationWidget(mode="rings")
        anim.setFixedSize(140, 140)
        lay.addWidget(anim, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(28)

        heading = QLabel("Let’s see what’s on\nyour network")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-size:22px; font-weight:600; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(heading)
        lay.addSpacing(12)

        body = QLabel(
            "NetSentinel will scan your local network to\n"
            "find connected devices.  Nothing leaves your device."
        )
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setStyleSheet(
            f"font-size:13px; color:{TEXT_MUTED};"
            " background:transparent; border:none;"
        )
        lay.addWidget(body)
        lay.addSpacing(40)

        self._scan_btn = _AccentButton("Scan my network")
        self._scan_btn.clicked.connect(self._on_scan_clicked)
        lay.addWidget(self._scan_btn)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

    def _build_placeholder(self, idx: int, title: str, body: str) -> None:
        """Placeholder for Screens 2–5 (implemented in Sprints I2/I3)."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_TopBar(active_dot=idx - 1, on_skip=self._do_skip))
        outer.addStretch(1)

        card = _CentreCard(400)
        lay  = card.inner

        t = QLabel(title)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(
            f"font-size:20px; font-weight:600; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(t)
        lay.addSpacing(12)

        b = QLabel(body)
        b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b.setStyleSheet(
            f"font-size:13px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        lay.addWidget(b)
        lay.addSpacing(40)

        # Next button — advances to Screen idx+1; Screen 5 goes to Screen 6 (Done)
        next_target = idx + 1
        label = "Done — Start exploring" if idx == 5 else "Next  →"
        btn_qss_bg = GREEN if idx == 5 else ACCENT
        btn = QPushButton(label)
        btn.setFixedHeight(48)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background:{btn_qss_bg}; color:{WHITE};"
            f" border:none; border-radius:8px; font-size:15px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        btn.clicked.connect(lambda checked=False, t=next_target: self._go_to_screen(t))
        lay.addWidget(btn)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

    def _build_screen_6(self) -> None:
        """Screen 6: Done — auto-dismisses after 1.5 s."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        card = _CentreCard(360)
        lay  = card.inner

        check = QLabel("✓")
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check.setStyleSheet(
            f"font-size:80px; font-weight:700; color:{GREEN};"
            " background:transparent; border:none;"
        )
        lay.addWidget(check)
        lay.addSpacing(18)

        done_lbl = QLabel("You’re all set")
        done_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        done_lbl.setStyleSheet(
            f"font-size:22px; font-weight:600; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(done_lbl)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

    # ── Navigation ─────────────────────────────────────────────────────────────

    def _go_to_screen(self, n: int) -> None:
        self._stack.setCurrentIndex(n)
        if n == 6:
            QTimer.singleShot(1500, self._finish)

    def _on_scan_clicked(self) -> None:
        self.scan_requested.emit()
        self._go_to_screen(2)

    def _do_skip(self) -> None:
        self._go_to_screen(6)

    def _finish(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue(_SETTINGS_KEY, True)
        qs.setValue(_TOUR_KEY, True)
        if self.parent():
            self.parent().removeEventFilter(self)
        # Stop animation timers before deletion
        try:
            from ui.widgets.scan_animation import ScanAnimationWidget
            for w in self.findChildren(ScanAnimationWidget):
                w.stop()
        except Exception:
            pass
        self.hide()
        self.deleteLater()


# ── Private helper widgets ─────────────────────────────────────────────────────

class _CentreCard(QWidget):
    """Fixed-width card that centres itself horizontally inside a parent layout."""

    def __init__(self, width: int, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(width)
        self.inner = QVBoxLayout(self)
        self.inner.setContentsMargins(0, 0, 0, 0)
        self.inner.setSpacing(0)
        self.inner.setAlignment(Qt.AlignmentFlag.AlignTop)


def _add_centre(parent_layout: QVBoxLayout, widget: QWidget) -> None:
    """Add *widget* centred horizontally into *parent_layout*."""
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(widget)
    row.addStretch(1)
    parent_layout.addLayout(row)


class _AccentButton(QPushButton):
    """Standard accent-coloured primary action button (full width)."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE};"
            f" border:none; border-radius:8px; font-size:15px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )


class _SkipLink(QLabel):
    """Muted clickable "Skip setup →" label that emits a clicked() signal pattern."""

    clicked = pyqtSignal()

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"font-size:13px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class _TopBar(QWidget):
    """
    Progress dots + Skip link shown at the top of Screens 1–5.

    active_dot: 0-based index of the highlighted dot (Screen 1 = 0, Screen 5 = 4).
    """

    def __init__(self, active_dot: int, on_skip, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(28, 0, 28, 0)
        lay.setSpacing(8)

        for i in range(5):
            is_active = i == active_dot
            dot = QLabel("●" if is_active else "○")
            dot.setStyleSheet(
                f"font-size:9px; color:{ACCENT if is_active else BORDER};"
                " background:transparent; border:none;"
            )
            lay.addWidget(dot)

        lay.addStretch(1)

        skip = _SkipLink("Skip")
        skip.clicked.connect(on_skip)
        lay.addWidget(skip)
