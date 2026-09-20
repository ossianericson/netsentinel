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
    ToastManager.show("The file could not be saved.", "error",
                      action_label="Choose another location", action_callback=retry,
                      detail=raw_exception_text)

Types:
    success  — GREEN border, 3s auto-dismiss
    error    — RED border, stays until clicked
    warning  — AMBER border, 6s auto-dismiss
    info     — ACCENT border, 4s auto-dismiss
    action   — ACCENT border, message + one button, stays until dismissed

Any kind may carry one action button (``action_label`` + ``action_callback``) — an error that has
a next step offers it (S6). ``detail`` is raw technical text (an exception, a path): it becomes
the message's tooltip and never part of the message itself (RULE-A2).

A kind that is not listed here falls through to the info defaults, so adding a
new one means adding it to `_type_border`, `_AUTO_DISMISS_MS` and the icon map —
`tests/test_error_surfacing_ratchet.py` derives the valid set from this module
and fails any call site using a kind that was never defined.

Toasts whose auto-dismiss is 0 are "sticky": they wait on a click, so `_show()`
never evicts one to make room for a newer toast. Toasts raised before `attach()`
are queued and replayed, not dropped.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer,
)
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
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
        "warning": _s.AMBER,
        "info":    _s.ACCENT,
        "action":  _s.ACCENT,
    }.get(kind, _s.ACCENT)


_AUTO_DISMISS_MS = {
    "success": 3000,
    "error":   0,
    "warning": 6000,
    "info":    4000,
    "action":  0,
}

#: Kinds the user must dismiss themselves (auto-dismiss 0). These are never
#: evicted to make room for a newer toast — see ToastManager._show().
_STICKY_KINDS = frozenset(k for k, ms in _AUTO_DISMISS_MS.items() if ms == 0)


# ── Single toast widget ────────────────────────────────────────────────────────

class _Toast(QFrame):
    def __init__(self, message: str, kind: str,
                 action_label: str = "", action_callback: Optional[Callable] = None,
                 parent: QWidget = None, detail: str = ""):
        super().__init__(parent)
        self._kind = kind
        color = _type_border(kind)

        self.setFixedWidth(_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"_Toast {{ background:{_s.BG_CARD}; border:1px solid {_s.BORDER};"
            f" border-left:3px solid {color}; border-radius:4px; }}"
        )

        # Icon | message | close on one row; an action button gets its own row below, because
        # inline it takes the width a long message needs to wrap into (RULE-UI2).
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 8, 8)
        root.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(8)
        root.addLayout(row)

        icon_map = {"success": "✓", "error": "✗", "warning": "⚠", "info": "ℹ", "action": "ℹ"}
        icon_lbl = QLabel(icon_map.get(kind, "ℹ"))
        icon_lbl.setStyleSheet(
            f"color:{color}; font-weight:bold; font-size:13px;"
            " background:transparent; border:none;"
        )
        icon_lbl.setFixedWidth(16)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        if detail:
            msg_lbl.setToolTip(_s.safe_tooltip(detail))
        msg_lbl.setStyleSheet(
            f"color:{_s.TEXT_PRIMARY}; font-size:11px; background:transparent; border:none;"
        )

        row.addWidget(icon_lbl)
        row.addWidget(msg_lbl, 1)

        act_btn = None
        if action_label and action_callback:
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
        row.addWidget(close_btn)

        if act_btn is not None:
            act_row = QHBoxLayout()
            act_row.addStretch()
            act_row.addWidget(act_btn)
            root.addLayout(act_row)

        self.resize(_WIDTH, self.fitted_height())

        dismiss_ms = _AUTO_DISMISS_MS.get(kind, 0)
        if dismiss_ms > 0:
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self._dismiss)
            _t.start(dismiss_ms)

    def fitted_height(self) -> int:
        """The height the message needs at the fixed ``_WIDTH`` (RULE-UI2). ``sizeHint()`` is
        computed at the message's unconstrained width, where it wraps into fewer lines."""
        h = self.heightForWidth(_WIDTH)
        return h if h > 0 else self.sizeHint().height()

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
        # Toasts raised before attach(). Startup failures land in that window,
        # and returning early used to discard them silently.
        self._pending: list[tuple] = []

    @classmethod
    def instance(cls) -> "ToastManager":
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def attach(self, parent: QWidget) -> None:
        self._parent = parent
        pending, self._pending = self._pending, []
        for message, kind, action_label, action_callback, detail in pending:
            self._show(message, kind, action_label, action_callback, detail)

    @classmethod
    def show(cls, message: str, kind: str = "info",
             action_label: str = "", action_callback: Optional[Callable] = None,
             detail: str = "") -> None:
        cls.instance()._show(message, kind, action_label, action_callback, detail)

    def _show(self, message: str, kind: str,
              action_label: str, action_callback: Optional[Callable],
              detail: str = "") -> None:
        if self._parent is None:
            # Queue rather than drop — replayed by attach(). Bounded so a
            # pre-attach failure loop cannot grow without limit.
            if len(self._pending) < 8:
                self._pending.append((message, kind, action_label, action_callback, detail))
            return
        if len(self._toasts) >= 3:
            # Evict the oldest NON-sticky toast. A sticky kind (error/action)
            # waits on a click the user has not made yet, so discarding it to
            # make room for a routine success throws away the one message that
            # required attention.
            victim = next((t for t in self._toasts if t._kind not in _STICKY_KINDS), None)
            if victim is not None:
                self._remove_toast(victim)
            elif len(self._toasts) >= 5:
                # All sticky and piling up — drop the oldest so the stack stays
                # readable rather than covering the window.
                self._remove_toast(self._toasts[0])

        t = _Toast(message, kind, action_label, action_callback, self._parent, detail)
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
            th = t.fitted_height()
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
