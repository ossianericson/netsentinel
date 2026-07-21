"""
home_widgets.py — Reusable helper widgets for the Home page.

Extracted from ui/pages/home_page.py (Sprint 4, S3-3).
Sprint 7 (S14-1): FreshnessStrip, GettingStartedCard, _GradeBreakdownDialog,
StandardWelcomePage, ProWelcomePage moved here.
"""
from __future__ import annotations

import json

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QSettings, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import styles as _s


class _GradeRing(QWidget):
    """
    HOME-1: 68×68 animated grade ring.

    Draws a 4 px arc proportional to the grade score (0–100).
    On grade update: arc sweeps from 0 to target in 600 ms (OutExpo),
    score counts up below the letter, letter crossfades in 300 ms.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(68, 68)
        self._grade  = "–"
        self._score  = 0.0
        self._arc_pct  = 0.0   # 0.0–1.0 animated value
        self._disp_score = 0.0  # animated score display
        # Store the colour *role*, not a frozen hex, so paintEvent resolves the
        # live theme value on every repaint (self-heals on theme switch).
        self._colour_role = "neutral"

        self._arc_anim: QVariantAnimation | None = None
        self._score_anim: QVariantAnimation | None = None
        self.setToolTip(_s.safe_tooltip(
            "Network Grade — A–F score across 8 health dimensions."
        ))

    def set_grade(self, grade: str, score: float) -> None:
        from ui.theme import _reduce_motion
        if grade in ("A", "B"):
            self._colour_role = "good"
        elif grade == "C":
            self._colour_role = "warn"
        else:
            self._colour_role = "bad"

        self._grade = grade[:1].upper() if grade else "–"

        if _reduce_motion():
            self._arc_pct  = max(0.0, min(1.0, score / 100.0))
            self._disp_score = score
            self._score = score
            self.update()
            return

        target_pct = max(0.0, min(1.0, score / 100.0))

        # Arc sweep animation (600 ms OutExpo)
        if self._arc_anim is not None:
            self._arc_anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(target_pct)
        anim.setDuration(600)
        anim.setEasingCurve(QEasingCurve.Type.OutExpo)
        anim.valueChanged.connect(self._on_arc)
        anim.start()
        self._arc_anim = anim

        # Score count-up animation (600 ms)
        if self._score_anim is not None:
            self._score_anim.stop()
        sanim = QVariantAnimation(self)
        sanim.setStartValue(0.0)
        sanim.setEndValue(float(score))
        sanim.setDuration(600)
        sanim.setEasingCurve(QEasingCurve.Type.OutExpo)
        sanim.valueChanged.connect(self._on_score)
        sanim.start()
        self._score_anim = sanim
        self._score = score

    def text(self) -> str:
        """Backwards-compat shim — returns the current grade letter."""
        return self._grade

    def _role_colour(self) -> str:
        """Resolve the current colour role to a live theme hex value."""
        return {
            "good":    _s.GREEN,
            "warn":    _s.AMBER,
            "bad":     _s.RED,
            "neutral": _s.TEXT_SECONDARY,
        }[self._colour_role]

    def _on_arc(self, v: float) -> None:
        self._arc_pct = v
        self.update()

    def _on_score(self, v: float) -> None:
        self._disp_score = v
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r = min(w, h) / 2.0 - 4
        thickness = 4.0

        # Track circle (dim)
        pen_track = QPen(QColor(_s.CHART_SPINE), thickness)
        pen_track.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen_track)
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))

        _role_hex = self._role_colour()
        # Filled arc
        if self._arc_pct > 0:
            pen_arc = QPen(QColor(_role_hex), thickness)
            pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen_arc)
            span_angle = int(self._arc_pct * 360 * 16)
            p.drawArc(
                QRectF(cx - r, cy - r, 2 * r, 2 * r),
                90 * 16,
                -span_angle,
            )

        # Grade letter (centre)
        p.setPen(QPen(QColor(_role_hex), 1))
        font = p.font()
        font.setPointSize(18)
        font.setBold(True)
        p.setFont(font)
        letter_rect = QRectF(0, cy - 18, w, 22)
        p.drawText(letter_rect, Qt.AlignmentFlag.AlignCenter, self._grade)

        # Score (small, below letter)
        if self._score > 0:
            p.setPen(QPen(QColor(_s.TEXT_MUTED), 1))
            score_font = p.font()
            score_font.setPointSize(7)
            score_font.setBold(False)
            p.setFont(score_font)
            score_rect = QRectF(0, cy + 4, w, 14)
            p.drawText(score_rect, Qt.AlignmentFlag.AlignCenter,
                       f"{int(round(self._disp_score))}")

        p.end()


class _MiniSparkline(QWidget):
    """HOME-4: 72×16 QPainter bar sparkline for _MiniCard value trend."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(72, 16)
        self._points: list[float] = []
        self._colour = _s.ACCENT

    def set_data(self, points: list[float], colour: str | None = None) -> None:
        self._points = list(points)
        self._colour = colour if colour is not None else _s.ACCENT
        self.update()

    def paintEvent(self, event) -> None:
        pts = self._points
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(pts) < 2:
            p.setPen(QColor(_s.CHART_SPINE))
            p.drawLine(0, self.height() // 2, self.width(), self.height() // 2)
            p.end()
            return

        w, h = self.width(), self.height()
        mn, mx = min(pts), max(pts)
        span = mx - mn if mx != mn else 1.0
        bar_w = max(1, w // len(pts) - 1)
        gap = (w - bar_w * len(pts)) // max(len(pts) - 1, 1)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._colour + "88"))
        for i, v in enumerate(pts):
            bh = max(2, int(((v - mn) / span) * (h - 2)))
            x = i * (bar_w + gap)
            p.drawRect(x, h - bh, bar_w, bh)

        # Highlight last bar
        if pts:
            last_h = max(2, int(((pts[-1] - mn) / span) * (h - 2)))
            x = (len(pts) - 1) * (bar_w + gap)
            p.setBrush(QColor(self._colour))
            p.drawRect(x, h - last_h, bar_w, last_h)
        p.end()


class _GradeSparkline(QWidget):
    """80×28 QPainter sparkline showing grade score trend over last N runs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 32)
        self._points: list[float] = []  # list of score values 0–100

    def set_points(self, points: list[float]) -> None:
        self._points = list(points)
        self.update()

    def paintEvent(self, event) -> None:
        pts = self._points
        if len(pts) < 2:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QColor(_s.TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "—")
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("transparent"))

        w, h = self.width(), self.height()
        pad = 4
        usable_w = w - 2 * pad
        usable_h = h - 2 * pad

        mn, mx = min(pts), max(pts)
        span = mx - mn if mx != mn else 1.0

        def _x(i: int) -> float:
            return pad + (i / (len(pts) - 1)) * usable_w

        def _y(v: float) -> float:
            return pad + (1.0 - (v - mn) / span) * usable_h

        path = QPainterPath()
        path.moveTo(QPointF(_x(0), _y(pts[0])))
        for i, v in enumerate(pts[1:], 1):
            path.lineTo(QPointF(_x(i), _y(v)))

        last_score = pts[-1]
        color = _s.GREEN if last_score >= 70 else (_s.AMBER if last_score >= 50 else _s.RED)
        pen = QPen(QColor(color), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        # dot at last point
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(_x(len(pts) - 1), _y(pts[-1])), 3, 3)
        painter.end()


class _EventsTicker(QFrame):
    """
    HOME-3: Slim 28 px ticker bar showing the last 3 MetricStore device events.

    Displays "HH:MM · device · event" entries. Clicking navigates to Timeline.
    Hidden if there are no events in the last 24 h.
    """

    #: Emitted when the ticker is clicked; carries the nav target label.
    navigate_to = pyqtSignal(str)

    def __init__(self, store=None, parent=None):
        super().__init__(parent)
        self._store = store
        self.setObjectName("statusTicker")
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(
            self,
            "QFrame#statusTicker {{ background:{BG_HOVER}; border:1px solid {BORDER};"
            " border-radius:4px; }}"
            "QFrame#statusTicker:hover {{ border-color:{ACCENT}; }}",
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)

        icon_lbl = QLabel("◷")
        icon_lbl.setFixedWidth(14)
        _s.themed_ss(icon_lbl, "font-size:11px; color:{ACCENT}; border:none; background:transparent;")
        lay.addWidget(icon_lbl)

        self._content_lbl = QLabel("–")
        _s.themed_ss(
            self._content_lbl,
            "font-size:10px; color:{TEXT_SECONDARY}; border:none; background:transparent;",
        )
        lay.addWidget(self._content_lbl, 1)

        nav_lbl = QLabel("Timeline →")
        _s.themed_ss(
            nav_lbl, "font-size:10px; color:{ACCENT}; border:none; background:transparent;"
        )
        lay.addWidget(nav_lbl)

        self.hide()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.navigate_to.emit("Network Timeline")
        super().mousePressEvent(event)

    def refresh(self, store=None) -> None:
        s = store or self._store
        if s is None:
            return
        try:
            events = s.query_device_events(hours=24.0)[:3]
        except Exception:
            return

        if not events:
            self.hide()
            return

        parts = []
        for evt in events:
            import datetime as _dt
            ts_str = _dt.datetime.fromtimestamp(evt.ts).strftime("%H:%M")
            ip_short = (evt.ip or "?")[:12]
            parts.append(f"{ts_str} · {ip_short} · {evt.event_type}")

        self._content_lbl.setText("   |   ".join(parts))
        self.show()

    def set_store(self, store) -> None:
        self._store = store
        self.refresh()


_GRADE_HISTORY_KEY = "grade/history_json"
_GRADE_HISTORY_MAX = 14


def _append_grade_history(grade: str, score: float) -> None:
    import time as _time
    qs = QSettings("NetSentinel", "NetSentinel")
    try:
        history: list = json.loads(qs.value(_GRADE_HISTORY_KEY, "[]", type=str))
    except Exception:
        history = []
    history.append({"ts": int(_time.time()), "grade": grade, "score": score})
    if len(history) > _GRADE_HISTORY_MAX:
        history = history[-_GRADE_HISTORY_MAX:]
    qs.setValue(_GRADE_HISTORY_KEY, json.dumps(history))


def _load_grade_history() -> list[float]:
    qs = QSettings("NetSentinel", "NetSentinel")
    try:
        history: list = json.loads(qs.value(_GRADE_HISTORY_KEY, "[]", type=str))
        return [float(e["score"]) for e in history if "score" in e]
    except Exception:
        return []


def _bundled_plugin_path(filename: str) -> str:
    """Return the absolute path of a bundled plugin script."""
    from pathlib import Path as _P
    return str(_P(__file__).parent.parent.parent / "plugins" / filename)


# ── Stat cards extracted from HomePage (Sprint 15) ───────────────────────────

class _MiniCard(QFrame):
    """One of the three top-line metric summary cards on the Home page."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit()
        super().mousePressEvent(event)

    def __init__(self, icon: str, title: str, val: str, sub: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(100)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(
            self,
            "QFrame#statCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:{CARD_RADIUS}; }}",
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)

        self._icon_lbl = QLabel(icon)
        _s.themed_ss(
            self._icon_lbl,
            "font-size:13px; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;",
        )
        self._title_lbl = QLabel(title)
        _s.themed_ss(
            self._title_lbl,
            "font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;",
        )
        self._val_lbl = QLabel(val)
        # Placeholder colour; set_value re-registers with the live status colour.
        _s.themed_ss(
            self._val_lbl,
            "font-size:20px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;",
        )
        self._sub_lbl = QLabel(sub)
        _s.themed_ss(
            self._sub_lbl,
            "font-size:10px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;",
        )

        self._dot_lbl = QLabel("●")
        _s.themed_ss(
            self._dot_lbl,
            "font-size:8px; color:{GREEN}; background:transparent; border:none;",
        )
        self._dot_lbl.setFixedWidth(12)
        self._status_lbl = QLabel("")
        _s.themed_ss(
            self._status_lbl,
            "font-size:10px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;",
        )
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(3)
        status_row.addWidget(self._dot_lbl)
        status_row.addWidget(self._status_lbl)
        status_row.addStretch()

        self._sparkline = _MiniSparkline(self)
        self._sparkline.hide()

        lay.addWidget(self._icon_lbl)
        lay.addWidget(self._title_lbl)
        lay.addWidget(self._val_lbl)
        lay.addWidget(self._sparkline)
        lay.addWidget(self._sub_lbl)
        lay.addLayout(status_row)

    def set_value(self, val: str, sub: str, status: str, colour: str) -> None:
        """Update the card's main value, subtitle, status dot and label."""
        self._val_lbl.setText(val)
        # Re-register so a theme switch keeps the status hue (HomePage.refresh_theme
        # re-derives the exact live shade from cached data). Callable captures only
        # the colour string — never self/the widget — to avoid a registry leak.
        _s.themed_ss(
            self._val_lbl,
            lambda c=colour: f"font-size:20px; font-weight:bold; color:{c};"
            " background:transparent; border:none;",
        )
        self._sub_lbl.setText(sub)
        _s.themed_ss(
            self._dot_lbl,
            lambda c=colour: f"font-size:8px; color:{c};"
            " background:transparent; border:none;",
        )
        self._status_lbl.setText(status)

    def set_sparkline_data(self, points: list, colour: str | None = None) -> None:
        """Show the mini sparkline with the given data points."""
        if len(points) >= 2:
            self._sparkline.set_data(points, colour)
            self._sparkline.show()
        else:
            self._sparkline.hide()


class _AlertRow(QFrame):
    """Single row in the recent-alerts strip on the Home page."""

    clicked = pyqtSignal(object)  # carries the raw alert object

    def __init__(self, colour: str, msg: str, time_str: str,
                 alert: object = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._alert = alert
        self.setObjectName("alertRow")
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QFrame#alertRow { background:transparent; border:none; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        dot = QLabel("●")
        dot.setFixedWidth(12)
        _s.themed_ss(
            dot,
            lambda c=colour: f"font-size:8px; color:{c};"
            " background:transparent; border:none;",
        )
        msg_lbl = QLabel(msg)
        _s.themed_ss(
            msg_lbl,
            "font-size:11px; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;",
        )
        msg_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        time_lbl = QLabel(time_str)
        _s.themed_ss(
            time_lbl,
            "font-size:10px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;",
        )
        time_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        lay.addWidget(dot)
        lay.addWidget(msg_lbl, 1)
        lay.addWidget(time_lbl)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self._alert)
        super().mousePressEvent(event)
