"""
Coach mark overlay for first-run onboarding (POLISH-5).

Usage::

    from ui.widgets.coach_mark import CoachMarkChain

    chain = CoachMarkChain(
        main_window,
        [
            {
                "target":  lambda: main_window.findChild(QWidget, "home_content"),
                "title":   "Your network, on a map.",
                "body":    "After a scan, NetSentinel plots every device on the world map.",
            },
            ...
        ],
    )
    chain.start()

Each mark is dismissed by "Got it →" / "Next →" or the × button.
Keyed to QSettings "onboarding_v6_done" — the chain marks it True on full completion.
"""
from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget
from ui.styles import (
    ACCENT_DARK, BG_HOVER, OVERLAY_BG, OVERLAY_BG3, OVERLAY_BLUE,
    OVERLAY_BLUE2, OVERLAY_FG2, STATUS_OFFLINE, TEXT_PRIMARY, WHITE,
)


# ── Single overlay ────────────────────────────────────────────────────────────

class CoachMarkOverlay(QWidget):
    """Full-window semi-transparent overlay with a callout bubble."""

    dismissed = pyqtSignal()   # fired by × or "Got it" on the last mark
    advanced  = pyqtSignal()   # fired by "Next →" on non-last marks

    _BG_ALPHA   = 170          # 0-255
    _BUBBLE_W   = 320
    _BUBBLE_H   = 178
    _PADDING    = 16
    _HOLE_PAD   = 12           # extra space around target rect
    _HOLE_R     = 10           # rounded-rect corner radius for the hole

    def __init__(
        self,
        parent: QWidget,
        target_rect: QRect | None,
        title: str,
        body: str,
        is_last: bool = False,
        target_widget: QWidget | None = None,
    ):
        super().__init__(parent)
        self._target_rect   = QRectF(target_rect) if target_rect else None
        self._target_widget = target_widget   # kept for live position tracking
        self._title = title
        self._body  = body
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setGeometry(parent.rect())

        # Refresh the target rect every 250 ms so the hole stays on the widget
        # even when surrounding content shifts (e.g. VerdictPanel appearing).
        self._track_timer = QTimer(self)
        self._track_timer.setInterval(250)
        self._track_timer.timeout.connect(self._refresh_target)
        if target_widget is not None:
            self._track_timer.start()

        # Build bubble widget (child of overlay)
        self._bubble = QWidget(self)
        self._bubble.setFixedSize(self._BUBBLE_W, self._BUBBLE_H)
        self._bubble.setStyleSheet(
            f"QWidget {{ background: {OVERLAY_BG}; border: 1px solid {OVERLAY_BG3};"
            f" border-radius: 12px; }}"
        )

        # Title
        title_lbl = QLabel(title, self._bubble)
        title_lbl.setGeometry(
            self._PADDING, self._PADDING,
            self._BUBBLE_W - 2 * self._PADDING - 30, 22,
        )
        title_lbl.setStyleSheet(
            f"QLabel {{ background: transparent; border: none;"
            f" color: {WHITE}; font-size: 14px; font-weight: 600; }}"
        )

        # Body
        body_lbl = QLabel(body, self._bubble)
        body_lbl.setGeometry(
            self._PADDING, 44,
            self._BUBBLE_W - 2 * self._PADDING, 82,
        )
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(
            f"QLabel {{ background: transparent; border: none;"
            f" color: {OVERLAY_FG2}; font-size: 12px; }}"
        )

        # Dismiss × button — oversized hit area for easy clicking
        close_btn = QPushButton("×", self._bubble)
        close_btn.setGeometry(self._BUBBLE_W - 36, 4, 32, 32)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {STATUS_OFFLINE}; font-size: 18px; }}"
            f"QPushButton:hover {{ color: {WHITE}; }}"
            f"QPushButton:pressed {{ background: {BG_HOVER}; color: {TEXT_PRIMARY}; }}"
        )
        close_btn.clicked.connect(self.dismissed)

        # Action button — tall for easy clicking
        action_text = "Got it" if is_last else "Next →"
        action_btn = QPushButton(action_text, self._bubble)
        action_btn.setGeometry(
            self._BUBBLE_W - self._PADDING - 108, self._BUBBLE_H - 48, 108, 34,
        )
        action_btn.setStyleSheet(
            f"QPushButton {{ background: {OVERLAY_BLUE}; border: none; border-radius: 6px;"
            f" color: {WHITE}; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {OVERLAY_BLUE2}; color: {WHITE}; }}"
            f"QPushButton:pressed {{ background: {ACCENT_DARK}; color: {WHITE}; }}"
        )
        if is_last:
            action_btn.clicked.connect(self.dismissed)
        else:
            action_btn.clicked.connect(self.advanced)

        self._position_bubble()

        # Fade-in animation on the overlay (not the bubble — the bubble is opaque)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def show_animated(self) -> None:
        self.show()
        self.raise_()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def hide_animated(self, callback=None) -> None:
        self._track_timer.stop()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        if callback:
            self._fade_anim.finished.connect(callback)
        self._fade_anim.start()

    def _refresh_target(self) -> None:
        """Recompute the target rect from the live widget position and repaint if moved."""
        w = self._target_widget
        if w is None:
            return
        try:
            if not w.isVisible():
                return
            global_rect = QRect(w.mapToGlobal(QPoint(0, 0)), w.size())
            new_rect = QRectF(
                QRect(self.parent().mapFromGlobal(global_rect.topLeft()), global_rect.size())
            )
            if new_rect != self._target_rect:
                self._target_rect = new_rect
                self._position_bubble()
                self.update()
        except Exception:
            pass

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dark overlay with hole cut out for target
        full_path = QPainterPath()
        full_path.addRect(QRectF(self.rect()))

        if self._target_rect:
            hole_rect = self._target_rect.adjusted(
                -self._HOLE_PAD, -self._HOLE_PAD,
                self._HOLE_PAD,  self._HOLE_PAD,
            )
            hole = QPainterPath()
            hole.addRoundedRect(hole_rect, self._HOLE_R, self._HOLE_R)
            full_path = full_path.subtracted(hole)

            # Highlight ring around the hole
            p.setPen(QPen(QColor(OVERLAY_BLUE), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(hole_rect, self._HOLE_R, self._HOLE_R)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, self._BG_ALPHA))
        p.drawPath(full_path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_bubble()

    def mousePressEvent(self, event):
        # Intentionally do not dismiss on outside click — use the × or action button.
        # Clicking outside was too easy to trigger accidentally when aiming for a button.
        pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _position_bubble(self) -> None:
        """Place the bubble near the target rect, staying inside the overlay."""
        w, h = self.width(), self.height()
        bw, bh = self._BUBBLE_W, self._BUBBLE_H
        margin = 24

        if self._target_rect:
            tr = self._target_rect.toRect()

            # Horizontal: centre on the target, but cap at 68% of window width so
            # the bubble never drifts into the far-right corner on wide screens.
            ideal_bx = tr.center().x() - bw // 2
            max_bx   = min(w - bw - margin, int(w * 0.68) - bw)
            bx       = max(margin, min(ideal_bx, max_bx))

            # Vertical: prefer below the target
            by = tr.bottom() + self._HOLE_PAD + 16
            if by + bh > h - margin:
                by = tr.top() - self._HOLE_PAD - bh - 16
            if by < margin:
                by = margin
        else:
            # No target — centre of window
            bx = (w - bw) // 2
            by = (h - bh) // 2

        self._bubble.move(bx, by)


# ── Chain sequencer ───────────────────────────────────────────────────────────

class CoachMarkChain:
    """Sequences a list of coach marks and saves completion to QSettings."""

    def __init__(self, parent_window: QWidget, marks: list[dict],
                 on_done=None) -> None:
        self._parent  = parent_window
        self._marks   = marks
        self._current = 0
        self._overlay: CoachMarkOverlay | None = None
        self._on_done = on_done  # optional callable — fired once when chain ends

    def start(self) -> None:
        self._show_mark(0)

    def _show_mark(self, index: int) -> None:
        if index >= len(self._marks):
            self._complete()
            return

        spec = self._marks[index]
        is_last = (index == len(self._marks) - 1)

        # Fire navigation / prep callback immediately so the destination is
        # ready before we resolve widget positions.
        on_show = spec.get("on_show")
        if callable(on_show):
            on_show()

        # Optional delay (ms) — gives animations time to settle before the
        # target widget's screen position is resolved.
        delay_ms = int(spec.get("delay_ms", 0))
        if delay_ms > 0:
            from PyQt6.QtCore import QTimer as _QT
            _QT.singleShot(delay_ms, lambda: self._create_overlay(spec, index, is_last))
        else:
            self._create_overlay(spec, index, is_last)

    def _create_overlay(self, spec: dict, index: int, is_last: bool) -> None:
        """Resolve target rect and display the overlay bubble."""
        target_rect   = None
        target_widget = None
        target_fn = spec.get("target")
        if callable(target_fn):
            try:
                target_widget = target_fn()
                if target_widget and target_widget.isVisible():
                    global_rect = QRect(
                        target_widget.mapToGlobal(QPoint(0, 0)),
                        target_widget.size(),
                    )
                    target_rect = QRect(
                        self._parent.mapFromGlobal(global_rect.topLeft()),
                        global_rect.size(),
                    )
            except Exception:
                target_widget = None

        overlay = CoachMarkOverlay(
            parent=self._parent,
            target_rect=target_rect,
            title=spec["title"],
            body=spec["body"],
            is_last=is_last,
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
            self._on_done = None  # fire once only
            _cb()

    def _complete(self) -> None:
        from PyQt6.QtCore import QSettings
        QSettings("NetSentinel", "NetSentinel").setValue("onboarding_v6_done", True)
        self._cleanup()
