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
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget
from ui.styles import (
    ACCENT_DARK, OVERLAY_BG, OVERLAY_BG3, OVERLAY_BLUE,
    OVERLAY_BLUE2, OVERLAY_FG2, STATUS_OFFLINE, WHITE,
)

_AUTO_DISMISS_MS = 12_000   # dismiss automatically after 12 s of inactivity


class _HighlightRing(QWidget):
    """Transparent overlay that draws a bright border ring around the target widget."""

    _BORDER = 2.5
    _RADIUS = 7.0
    _MARGIN = 4    # extra padding around the target

    def __init__(self, target: QWidget, parent: QWidget) -> None:
        super().__init__(parent)
        self._target = target
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent; border: none;")
        self._update_geometry()

    def _update_geometry(self) -> None:
        p = self.parent()
        if p is None:
            return
        try:
            if not self._target.isVisible() or self._target.width() == 0:
                self.setGeometry(0, 0, 0, 0)
                return
            m = self._MARGIN
            tl = self._target.mapTo(p, self._target.rect().topLeft())
            self.setGeometry(
                tl.x() - m,
                tl.y() - m,
                self._target.width() + 2 * m,
                self._target.height() + 2 * m,
            )
        except Exception:
            pass  # non-fatal — target may be unmapped or deleted

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        b = self._BORDER / 2
        rect = QRectF(self.rect()).adjusted(b, b, -b, -b)
        pen = QPen(QColor(OVERLAY_BLUE), self._BORDER)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, self._RADIUS, self._RADIUS)


class CoachMarkOverlay(QWidget):
    """
    Non-blocking floating hint panel — no dim overlay, no mouse interception.

    Rendered as a small card positioned next to the target widget (or bottom-right
    corner of the parent window if no target is set).
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
        auto_dismiss_ms: int = _AUTO_DISMISS_MS,
    ):
        super().__init__(parent)
        self._is_last = is_last
        self._auto_dismiss_ms = auto_dismiss_ms
        self._target_widget = target_widget

        # WA_TranslucentBackground keeps corners transparent; paintEvent fills the background
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self._W, self._H)
        # Transparent stylesheet — background drawn via paintEvent so WA_Translucent works
        self.setStyleSheet("background: transparent; border: none;")

        # Highlight ring around the target widget (sibling of parent, not child of overlay)
        self._ring: _HighlightRing | None = None
        if target_widget is not None:
            try:
                self._ring = _HighlightRing(target_widget, parent)
            except Exception:
                self._ring = None  # non-fatal

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

        # Auto-dismiss timer — skipped when auto_dismiss_ms <= 0
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.setInterval(max(auto_dismiss_ms, 0))
        if auto_dismiss_ms > 0:
            self._auto_timer.timeout.connect(self.dismissed)

        # Fade animation
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(180)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._position()

    def show_animated(self) -> None:
        self._position()
        # Show highlight ring around target before the overlay fades in
        if self._ring is not None:
            self._ring._update_geometry()
            self._ring.show()
            self._ring.raise_()
        self.show()
        self.raise_()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()
        if self._auto_dismiss_ms > 0:
            self._auto_timer.start()

    def hide_animated(self, callback=None) -> None:
        self._auto_timer.stop()
        # Remove highlight ring immediately when the step is dismissed
        if self._ring is not None:
            self._ring.deleteLater()
            self._ring = None
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        if callback:
            self._fade_anim.finished.connect(callback)
        self._fade_anim.start()

    def _position(self) -> None:
        """Position next to target_widget if set; otherwise bottom-right of parent."""
        p = self.parent()
        if p is None:
            return
        pw, ph = p.width(), p.height()

        if self._target_widget is not None:
            try:
                tw = self._target_widget
                if tw.isVisible() and tw.width() > 0:
                    tl = tw.mapTo(p, tw.rect().topLeft())
                    tx, ty = tl.x(), tl.y()
                    tw_w = tw.width()
                    # Prefer right of target; fall back to left
                    x = tx + tw_w + self._MARGIN
                    if x + self._W > pw - self._MARGIN:
                        x = tx - self._W - self._MARGIN
                    x = max(self._MARGIN, min(x, pw - self._W - self._MARGIN))
                    # Vertically align with target top, clamped to window
                    y = max(self._MARGIN, min(ty, ph - self._H - self._MARGIN))
                    self.move(x, y)
                    return
            except Exception:
                pass  # target may be deleted or unmapped; fall through

        # Default: bottom-right corner
        self.move(pw - self._W - self._MARGIN, ph - self._H - self._MARGIN)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # Solid dark background with rounded corners
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(OVERLAY_BG))
        painter.drawRoundedRect(rect, 12.0, 12.0)
        # Border
        painter.setPen(QPen(QColor(OVERLAY_BG3), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 12.0, 12.0)


# ── Chain sequencer ───────────────────────────────────────────────────────────

class CoachMarkChain:
    """Sequences a list of non-blocking hint panels."""

    def __init__(self, parent_window: QWidget, marks: list[dict],
                 on_done=None,
                 auto_dismiss_ms: int = _AUTO_DISMISS_MS) -> None:
        self._parent          = parent_window
        self._marks           = marks
        self._overlay: CoachMarkOverlay | None = None
        self._on_done         = on_done
        self._auto_dismiss_ms = auto_dismiss_ms

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
        target = spec.get("target")
        try:
            target_widget = target() if callable(target) else target
        except Exception:
            target_widget = None  # lambda may fail if widget not yet created
        overlay = CoachMarkOverlay(
            parent=self._parent,
            target_rect=None,
            title=spec["title"],
            body=spec["body"],
            is_last=is_last,
            auto_dismiss_ms=int(spec.get("auto_dismiss_ms", self._auto_dismiss_ms)),
            target_widget=target_widget,
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
