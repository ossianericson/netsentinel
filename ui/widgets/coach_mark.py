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
    ACCENT_DARK, CANVAS_AMBER, OVERLAY_BG, OVERLAY_BG3, OVERLAY_BLUE,
    OVERLAY_BLUE2, OVERLAY_FG2, STATUS_OFFLINE, WHITE,
)

_AUTO_DISMISS_MS = 12_000   # dismiss automatically after 12 s of inactivity


class _HighlightRing(QWidget):
    """Transparent overlay that draws a bright border ring around the target widget."""

    _BORDER = 3.5   # amber ring stroke width
    _RADIUS = 8.0
    _MARGIN = 6     # extra padding around the target

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
        # Dark shadow ring — ensures visibility on light/white backgrounds
        b_shadow = (self._BORDER + 3) / 2
        rect_shadow = QRectF(self.rect()).adjusted(b_shadow, b_shadow, -b_shadow, -b_shadow)
        painter.setPen(QPen(QColor(0, 0, 0, 70), self._BORDER + 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect_shadow, self._RADIUS + 1, self._RADIUS + 1)
        # Amber ring — visible on dark and blue backgrounds
        b = self._BORDER / 2
        rect = QRectF(self.rect()).adjusted(b + 1, b + 1, -(b + 1), -(b + 1))
        painter.setPen(QPen(QColor(CANVAS_AMBER), self._BORDER))
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
        target_rect: QRect | None,   # kept for API compat; unused
        title: str,
        body: str,
        is_last: bool = False,
        target_widget: QWidget | None = None,
        auto_dismiss_ms: int = _AUTO_DISMISS_MS,
        action_text: str | None = None,
        extra_target_widgets: list | None = None,
        prefer_side: str | None = None,
        position_widget: QWidget | None = None,
    ):
        super().__init__(parent)
        self._is_last = is_last
        self._auto_dismiss_ms = auto_dismiss_ms
        self._target_widget = target_widget
        self._prefer_side = prefer_side
        # Separate widget used for card placement (ring still uses target_widget)
        self._position_widget = position_widget if position_widget is not None else target_widget

        # WA_TranslucentBackground keeps corners transparent; paintEvent fills the background
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self._W, self._H)
        # Transparent stylesheet — background drawn via paintEvent so WA_Translucent works
        self.setStyleSheet("background: transparent; border: none;")

        # Highlight rings around all target widgets (primary + any extras)
        self._rings: list[_HighlightRing] = []
        all_targets = [w for w in ([target_widget] + list(extra_target_widgets or [])) if w is not None]
        for tw in all_targets:
            try:
                self._rings.append(_HighlightRing(tw, parent))
            except Exception:
                pass  # non-fatal

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

        # Action button — use custom text if provided, otherwise default
        _btn_label = action_text or ("Got it" if is_last else "Next →")
        action_btn = QPushButton(_btn_label, self)
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
        # Show highlight rings around all targets
        for ring in self._rings:
            ring._update_geometry()
            ring.show()
            ring.raise_()
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
        # Remove all highlight rings immediately when the step is dismissed
        for ring in self._rings:
            ring.deleteLater()
        self._rings = []
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        if callback:
            self._fade_anim.finished.connect(callback)
        self._fade_anim.start()

    def _position(self) -> None:
        """Position the card relative to the position_widget; respects prefer_side."""
        p = self.parent()
        if p is None:
            return
        pw, ph = p.width(), p.height()
        m = self._MARGIN

        ref = self._position_widget
        if ref is not None:
            try:
                if ref.isVisible() and ref.width() > 0:
                    tl = ref.mapTo(p, ref.rect().topLeft())
                    tx, ty = tl.x(), tl.y()
                    tw_w, tw_h = ref.width(), ref.height()

                    below = (tx + tw_w // 2 - self._W // 2,  ty + tw_h + m)
                    right = (tx + tw_w + m,                   ty + tw_h // 2 - self._H // 2)
                    left  = (tx - self._W - m,                ty + tw_h // 2 - self._H // 2)
                    above = (tx + tw_w // 2 - self._W // 2,  ty - self._H - m)

                    if self._prefer_side == "right":
                        # Force clamped-right regardless of fit — consistent right-side placement
                        cx = max(m, min(right[0], pw - self._W - m))
                        cy = max(m, min(right[1], ph - self._H - m))
                        self.move(cx, cy)
                        return

                    # Default order: below → right → left → above; fallback = clamped below
                    candidates = [below, right, left, above]
                    for cx, cy in candidates:
                        if m <= cx and cx + self._W <= pw - m and m <= cy and cy + self._H <= ph - m:
                            self.move(cx, cy)
                            return

                    cx = max(m, min(below[0], pw - self._W - m))
                    cy = max(m, min(below[1], ph - self._H - m))
                    self.move(cx, cy)
                    return
            except Exception:
                pass  # target may be deleted or unmapped; fall through

        # Default: bottom-right corner
        self.move(pw - self._W - m, ph - self._H - m)

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
                 on_skip=None,
                 auto_dismiss_ms: int = _AUTO_DISMISS_MS) -> None:
        self._parent                 = parent_window
        self._marks                  = marks
        self._overlay: CoachMarkOverlay | None = None
        self._on_done                = on_done
        self._on_skip                = on_skip
        self._auto_dismiss_ms        = auto_dismiss_ms
        self._current_index          = 0

    def start(self) -> None:
        self._show_mark(0)

    def _show_mark(self, index: int) -> None:
        if index >= len(self._marks):
            self._complete()
            return

        self._current_index = index
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

        extra_target_widgets: list = []
        for et in spec.get("extra_targets", []):
            try:
                tw = et() if callable(et) else et
                if tw is not None:
                    extra_target_widgets.append(tw)
            except Exception:
                pass  # non-fatal

        # card_target — separate widget to anchor card placement (ring still uses target)
        card_target_fn = spec.get("card_target")
        try:
            position_widget = card_target_fn() if callable(card_target_fn) else card_target_fn
        except Exception:
            position_widget = None

        overlay = CoachMarkOverlay(
            parent=self._parent,
            target_rect=None,
            title=spec["title"],
            body=spec["body"],
            is_last=is_last,
            auto_dismiss_ms=int(spec.get("auto_dismiss_ms", self._auto_dismiss_ms)),
            target_widget=target_widget,
            action_text=spec.get("action_text"),
            extra_target_widgets=extra_target_widgets or None,
            prefer_side=spec.get("prefer_side"),
            position_widget=position_widget,
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
        # Last step "Got it" = natural completion; mid-chain × = user skip.
        is_last = self._current_index >= len(self._marks) - 1
        if self._overlay:
            if is_last:
                self._overlay.hide_animated(callback=self._cleanup)
            else:
                self._overlay.hide_animated(callback=self._cleanup_skip)

    def _cleanup(self) -> None:
        if self._overlay:
            self._overlay.deleteLater()
            self._overlay = None
        if callable(self._on_done):
            _cb = self._on_done
            self._on_done = None
            _cb()

    def _cleanup_skip(self) -> None:
        """Called when × is pressed before reaching the last step."""
        if self._overlay:
            self._overlay.deleteLater()
            self._overlay = None
        cb = self._on_skip if callable(self._on_skip) else self._on_done
        if callable(cb):
            if cb is self._on_skip:
                self._on_skip = None
            else:
                self._on_done = None
            cb()

    def _complete(self) -> None:
        from PyQt6.QtCore import QSettings
        QSettings("NetSentinel", "NetSentinel").setValue("onboarding_v6_done", True)
        self._cleanup()
