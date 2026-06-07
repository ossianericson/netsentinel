"""
Coach mark hint panel for first-run onboarding (POLISH-5).

Design rule: coach marks MUST NEVER block or dim any content.
The hint appears as a small floating panel anchored to the bottom-right corner of the
main window.  The rest of the window remains fully interactive at all times.

Usage::

    from ui.widgets.coach_mark import CoachMarkChain

    chain = CoachMarkChain(
        main_window,
        [
            {
                "title": "Scan your network",
                "body":  "Click Scan Now to discover every device and check your grade.",
            },
            ...
        ],
    )
    chain.start()

Each hint is dismissed by "Got it" / "Next →", the × button, or clicking anywhere
outside the panel.  The chain marks QSettings "onboarding_v6_done" True on completion.
"""
from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget
from ui.styles import (
    ACCENT_DARK, BG_HOVER, OVERLAY_BG, OVERLAY_BG3, OVERLAY_BLUE,
    OVERLAY_BLUE2, OVERLAY_FG2, STATUS_OFFLINE, TEXT_PRIMARY, WHITE,
)

_AUTO_DISMISS_MS = 12_000   # dismiss automatically after 12 s of inactivity


class CoachMarkOverlay(QWidget):
    """
    Non-blocking floating hint panel — no dim overlay, no mouse interception.

    Rendered as a small card in the bottom-right corner of the parent window.
    The rest of the UI remains fully interactive at all times.
    """

    dismissed = pyqtSignal()
    advanced  = pyqtSignal()

    _W       = 300
    _H       = 160
    _MARGIN  = 20
    _PADDING = 14

    def __init__(
        self,
        parent: QWidget,
        target_rect: QRect | None,   # kept for API compat; not used for dimming
        title: str,
        body: str,
        is_last: bool = False,
        target_widget: QWidget | None = None,
    ):
        super().__init__(parent)
        self._is_last = is_last

        # Floating, always-on-top, no frame — but still a child so it moves with the window
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self._W, self._H)
        self.setStyleSheet(
            f"QWidget {{ background: {OVERLAY_BG}; border: 1px solid {OVERLAY_BG3};"
            f" border-radius: 12px; }}"
        )

        # Title
        title_lbl = QLabel(title, self)
        title_lbl.setGeometry(self._PADDING, self._PADDING,
                               self._W - 2 * self._PADDING - 28, 22)
        title_lbl.setStyleSheet(
            f"QLabel {{ background: transparent; border: none;"
            f" color: {WHITE}; font-size: 13px; font-weight: 600; }}"
        )

        # Body
        body_lbl = QLabel(body, self)
        body_lbl.setGeometry(self._PADDING, 42,
                              self._W - 2 * self._PADDING, 72)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(
            f"QLabel {{ background: transparent; border: none;"
            f" color: {OVERLAY_FG2}; font-size: 11px; line-height: 1.4; }}"
        )

        # × dismiss button
        close_btn = QPushButton("×", self)
        close_btn.setGeometry(self._W - 32, 4, 28, 28)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {STATUS_OFFLINE}; font-size: 17px; }}"
            f"QPushButton:hover {{ color: {WHITE}; }}"
            f"QPushButton:pressed {{ color: {WHITE}; }}"
        )
        close_btn.clicked.connect(self.dismissed)

        # Action button
        action_text = "Got it" if is_last else "Next →"
        action_btn = QPushButton(action_text, self)
        action_btn.setGeometry(self._W - self._PADDING - 96, self._H - 40, 96, 28)
        action_btn.setStyleSheet(
            f"QPushButton {{ background: {OVERLAY_BLUE}; border: none; border-radius: 5px;"
            f" color: {WHITE}; font-size: 11px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {OVERLAY_BLUE2}; color: {WHITE}; }}"
            f"QPushButton:pressed {{ background: {ACCENT_DARK}; color: {WHITE}; }}"
        )
        action_btn.clicked.connect(self.dismissed if is_last else self.advanced)

        # Auto-dismiss timer
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.setInterval(_AUTO_DISMISS_MS)
        self._auto_timer.timeout.connect(self.dismissed)

        # Fade animation
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(180)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._position()

    def show_animated(self) -> None:
        self._position()
        self.show()
        self.raise_()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()
        self._auto_timer.start()

    def hide_animated(self, callback=None) -> None:
        self._auto_timer.stop()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        if callback:
            self._fade_anim.finished.connect(callback)
        self._fade_anim.start()

    def _position(self) -> None:
        """Anchor the panel to the bottom-right of the parent window."""
        p = self.parent()
        if p is None:
            return
        pw, ph = p.width(), p.height()
        x = pw - self._W - self._MARGIN
        y = ph - self._H - self._MARGIN
        self.move(x, y)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position()

    def paintEvent(self, event) -> None:
        # No dim overlay — just let the styled background paint the card.
        super().paintEvent(event)


# ── Chain sequencer ───────────────────────────────────────────────────────────

class CoachMarkChain:
    """Sequences a list of non-blocking hint panels."""

    def __init__(self, parent_window: QWidget, marks: list[dict],
                 on_done=None) -> None:
        self._parent  = parent_window
        self._marks   = marks
        self._overlay: CoachMarkOverlay | None = None
        self._on_done = on_done

    def start(self) -> None:
        self._show_mark(0)

    def _show_mark(self, index: int) -> None:
        if index >= len(self._marks):
            self._complete()
            return

        spec     = self._marks[index]
        is_last  = (index == len(self._marks) - 1)

        on_show = spec.get("on_show")
        if callable(on_show):
            on_show()

        delay_ms = int(spec.get("delay_ms", 0))
        if delay_ms > 0:
            from PyQt6.QtCore import QTimer as _QT
            _QT.singleShot(delay_ms, lambda: self._create_overlay(spec, index, is_last))
        else:
            self._create_overlay(spec, index, is_last)

    def _create_overlay(self, spec: dict, index: int, is_last: bool) -> None:
        overlay = CoachMarkOverlay(
            parent=self._parent,
            target_rect=None,
            title=spec["title"],
            body=spec["body"],
            is_last=is_last,
        )
        self._overlay = overlay
        overlay.dismissed.connect(self._on_dismissed)
        overlay.advanced.connect(lambda i=index: self._on_advanced(i))
        overlay.show_animated()

    def _on_advanced(self, current_index: int) -> None:
        if self._overlay:
            self._overlay.hide_animated(
                callback=lambda: self._advance(current_index + 1)
            )

    def _advance(self, next_index: int) -> None:
        if self._overlay:
            self._overlay.deleteLater()
            self._overlay = None
        self._show_mark(next_index)

    def _on_dismissed(self) -> None:
        if self._overlay:
            self._overlay.hide_animated(callback=self._cleanup)

    def _cleanup(self) -> None:
        if self._overlay:
            self._overlay.deleteLater()
            self._overlay = None
        if callable(self._on_done):
            _cb = self._on_done
            self._on_done = None
            _cb()

    def _complete(self) -> None:
        from PyQt6.QtCore import QSettings
        QSettings("NetSentinel", "NetSentinel").setValue("onboarding_v6_done", True)
        self._cleanup()
