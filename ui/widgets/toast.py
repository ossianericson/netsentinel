"""
ui/widgets/toast.py — slide-in toast notification system (POLISH-3)

ToastManager singleton renders stacked toasts in the bottom-right corner of
a parent QWidget (typically the main window). Toasts stack upward.

Usage:
    ToastManager.instance().attach(main_window)
    ToastManager.show("Export saved", "success")
    ToastManager.show("Connection failed", "error")
    ToastManager.show("Scanning…", "info")
    ToastManager.show("Blocked — Undo", "action", action_label="Undo",
                      action_callback=undo_fn)

Types:
    success  — GREEN border, 3s auto-dismiss
    error    — RED border, stays until clicked
    info     — ACCENT border, 4s auto-dismiss
    action   — ACCENT border, message + one button, stays until dismissed
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer,
)
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from ui import styles as _s
from ui.widgets.device_detail_pane import _wire_close_icon

# ── Constants ──────────────────────────────────────────────────────────────────

_MARGIN   = 16          # px from window edge
_SPACING  = 8           # px between toasts
_WIDTH    = 300         # fixed toast width
_SLIDE_MS = 150         # slide-in animation duration


def _type_border(kind: str) -> str:
    """Left-accent colour per toast kind, read live so a theme switch is picked
    up by the next toast (toasts are transient — see conversion shape G)."""
    return {
        "success": _s.GREEN,
        "error":   _s.RED,
        "info":    _s.ACCENT,
        "action":  _s.ACCENT,
    }.get(kind, _s.ACCENT)


_AUTO_DISMISS_MS = {
    "success": 3000,
    "error":   0,
    "info":    4000,
    "action":  0,
}


# ── Single toast widget ────────────────────────────────────────────────────────

class _Toast(QFrame):
    def __init__(self, message: str, kind: str,
                 action_label: str = "", action_callback: Optional[Callable] = None,
                 parent: QWidget = None):
        super().__init__(parent)
        self._kind = kind
        color = _type_border(kind)

        self.setFixedWidth(_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"_Toast {{ background:{_s.BG_CARD}; border:1px solid {_s.BORDER};"
            f" border-left:3px solid {color}; border-radius:4px; }}"
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 8, 8)
        root.setSpacing(8)

        icon_map = {"success": "✓", "error": "✗", "info": "ℹ", "action": "ℹ"}
        icon_lbl = QLabel(icon_map.get(kind, "ℹ"))
        icon_lbl.setStyleSheet(
            f"color:{color}; font-weight:bold; font-size:13px;"
            " background:transparent; border:none;"
        )
        icon_lbl.setFixedWidth(16)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            f"color:{_s.TEXT_PRIMARY}; font-size:11px; background:transparent; border:none;"
        )

        root.addWidget(icon_lbl)
        root.addWidget(msg_lbl, 1)

        if kind == "action" and action_label and action_callback:
            act_btn = QPushButton(action_label)
            act_btn.setFixedHeight(22)
            act_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            act_btn.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{_s.ACCENT};"
                f" border:1px solid {_s.ACCENT}; border-radius:3px;"
                f" font-size:10px; padding:0 8px; }}"
                f"QPushButton:hover {{ background:{_s.alpha(_s.ACCENT, 0x22)}; }}"
                f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.ACCENT}; }}"
            )
            act_btn.clicked.connect(action_callback)
            act_btn.clicked.connect(self._dismiss)
            root.addWidget(act_btn)

        close_btn = QPushButton()
        close_btn.setFixedSize(18, 18)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _wire_close_icon(close_btn)
        close_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; border:none; padding:0; }}"
            f"QPushButton:hover {{ background:transparent; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; }}"
        )
        close_btn.clicked.connect(self._dismiss)
        root.addWidget(close_btn)

        self.adjustSize()

        dismiss_ms = _AUTO_DISMISS_MS.get(kind, 0)
        if dismiss_ms > 0:
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self._dismiss)
            _t.start(dismiss_ms)

    def _dismiss(self) -> None:
        mgr = ToastManager.instance()
        if mgr:
            mgr._remove_toast(self)


# ── Singleton manager ─────────────────────────────────────────────────────────

class ToastManager:
    """Singleton that owns and positions all active toasts."""

    _inst: "ToastManager | None" = None

    def __init__(self):
        self._parent: Optional[QWidget] = None
        self._toasts: list[_Toast] = []

    @classmethod
    def instance(cls) -> "ToastManager":
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def attach(self, parent: QWidget) -> None:
        self._parent = parent

    @classmethod
    def show(cls, message: str, kind: str = "info",
             action_label: str = "", action_callback: Optional[Callable] = None) -> None:
        cls.instance()._show(message, kind, action_label, action_callback)

    def _show(self, message: str, kind: str,
              action_label: str, action_callback: Optional[Callable]) -> None:
        if self._parent is None:
            return
        if len(self._toasts) >= 3:
            self._remove_toast(self._toasts[0])

        t = _Toast(message, kind, action_label, action_callback, self._parent)
        t.adjustSize()
        t.show()
        self._toasts.append(t)
        self._restack(animate_last=True)

    def _remove_toast(self, toast: _Toast) -> None:
        if toast not in self._toasts:
            return
        self._toasts.remove(toast)
        toast.hide()
        toast.deleteLater()
        self._restack(animate_last=False)

    def _restack(self, animate_last: bool = False) -> None:
        if not self._parent:
            return
        pw = self._parent
        pw_h = pw.height()
        pw_w = pw.width()
        y = pw_h - _MARGIN

        for i, t in enumerate(reversed(self._toasts)):
            t.adjustSize()
            th = t.height()
            y -= th
            tx = pw_w - _WIDTH - _MARGIN
            target = QRect(tx, y, _WIDTH, th)
            y -= _SPACING

            is_newest = (i == 0) and animate_last
            if is_newest:
                # Slide in from right
                start = QRect(tx + _WIDTH + _MARGIN, target.y(), _WIDTH, th)
                t.setGeometry(start)
                anim = QPropertyAnimation(t, b"geometry", t)
                anim.setDuration(_SLIDE_MS)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                anim.setStartValue(start)
                anim.setEndValue(target)
                anim.start()
            else:
                t.setGeometry(target)

    def reposition(self) -> None:
        """Call when parent window is resized."""
        self._restack(animate_last=False)
