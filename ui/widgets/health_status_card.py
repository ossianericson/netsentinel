"""
ui/widgets/health_status_card.py — Ambient network health status card.

Displays the current health score (from HealthWorker) as a full-width card
near the top of the home page.  Includes:
  - Large state indicator (green check / amber warning / red X)
  - One-sentence plain-English headline
  - Sub-text detail line
  - Last-checked timestamp
  - CTA button ("View Details" or "Fix now")
  - 7-day health sparkline (S2-6) painted below the main content

Data is persisted to QSettings for the sparkline history.
"""
from __future__ import annotations

import json
import time

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui import styles as _s
from ui.styles import CARD_RADIUS

# ── History persistence ───────────────────────────────────────────────────────

_HISTORY_KEY    = "ambient/health_history"
_HISTORY_MAX    = 168    # hourly samples × 7 days
_MIN_ENTRY_GAP  = 3300   # seconds — skip storage if last entry is <55 min old


def _load_history() -> list[dict]:
    raw = QSettings("NetSentinel", "NetSentinel").value(_HISTORY_KEY, "[]")
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return data
    except Exception:
        pass  # non-fatal — corrupt JSON
    return []


def _save_history(entries: list[dict]) -> None:
    QSettings("NetSentinel", "NetSentinel").setValue(
        _HISTORY_KEY, json.dumps(entries[-_HISTORY_MAX:])
    )


def _append_snapshot(snapshot) -> None:
    """Persist a HealthSnapshot at most once per hour."""
    entries = _load_history()
    now_ts  = time.time()
    if entries:
        last_ts = entries[-1].get("ts", 0)
        if now_ts - last_ts < _MIN_ENTRY_GAP:
            return
    entries.append({
        "ts":    int(now_ts),
        "score": snapshot.score,
        "state": snapshot.state,
    })
    _save_history(entries)


# ── Sparkline widget ──────────────────────────────────────────────────────────

_STATE_COLOUR = {
    "green":   "GREEN",
    "amber":   "AMBER",
    "red":     "RED",
    "unknown": "TEXT_MUTED",
}


class _HealthSparkline(QWidget):
    """
    7-day health sparkline.

    Paints a thin line chart using QPainter.  Each data point is a (ts, score)
    pair loaded from QSettings.  Coloured segments reflect state (green/amber/red).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._entries: list[dict] = []

    def refresh(self) -> None:
        self._entries = _load_history()
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        entries = self._entries
        if not entries:
            self._paint_empty()
            return

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.fillRect(0, 0, w, h, QColor(_s.BG_CARD))

        pad_top, pad_bot, pad_left, pad_right = 4, 8, 4, 4
        chart_w = w - pad_left - pad_right
        chart_h = h - pad_top - pad_bot

        if len(entries) < 2:
            # Single dot
            e = entries[0]
            colour = QColor(getattr(_s, _STATE_COLOUR.get(e.get("state", "unknown"), "TEXT_MUTED")))
            cx = pad_left + chart_w // 2
            cy = pad_top + chart_h // 2
            p.setBrush(colour)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - 3, cy - 3, 6, 6)
            p.end()
            return

        now_ts  = time.time()
        span    = now_ts - entries[0]["ts"]
        if span <= 0:
            span = 1.0

        # Compute (x, y) positions
        pts: list[tuple[int, int, str]] = []
        for e in entries:
            age  = now_ts - e["ts"]
            frac = 1.0 - (age / span)
            x    = pad_left + int(frac * chart_w)
            score = max(0, min(100, e.get("score", 50)))
            y     = pad_top + int((1.0 - score / 100.0) * chart_h)
            pts.append((x, y, e.get("state", "unknown")))

        # Draw coloured line segments
        for i in range(1, len(pts)):
            x0, y0, _ = pts[i - 1]
            x1, y1, state = pts[i]
            colour = QColor(getattr(_s, _STATE_COLOUR.get(state, "TEXT_MUTED")))
            pen = QPen(colour, 1.5)
            p.setPen(pen)
            p.drawLine(x0, y0, x1, y1)

        # Dot at the latest point
        lx, ly, lst = pts[-1]
        colour = QColor(getattr(_s, _STATE_COLOUR.get(lst, "TEXT_MUTED")))
        p.setBrush(colour)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(lx - 3, ly - 3, 6, 6)

        # "7 days" label on the left
        p.setPen(QColor(_s.TEXT_MUTED))
        p.drawText(pad_left, h - 1, "7d")

        p.end()

    def _paint_empty(self) -> None:
        p = QPainter(self)
        p.fillRect(0, 0, self.width(), self.height(), QColor(_s.BG_CARD))
        p.setPen(QColor(_s.TEXT_MUTED))
        p.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "  No history yet",
        )
        p.end()


# ── Health status card ────────────────────────────────────────────────────────

_STATE_BORDER = {
    "green":   "GREEN",
    "amber":   "AMBER",
    "red":     "RED",
    "unknown": "BORDER",
}
_STATE_BG = {
    "green":   "GREEN_BG",
    "amber":   "AMBER_BG",
    "red":     "RED_BG",
    "unknown": "BG_CARD",
}
_STATE_ICON = {
    "green":   "✓",
    "amber":   "⚠",
    "red":     "✗",
    "unknown": "○",
}
_STATE_ICON_COLOUR = {
    "green":   "GREEN",
    "amber":   "AMBER",
    "red":     "RED",
    "unknown": "TEXT_MUTED",
}
_CTA_LABEL = {
    "green":   "View Dashboard →",
    "amber":   "View alerts →",
    "red":     "Fix now →",
    "unknown": "Run a scan →",
}
_CTA_PAGE = {
    "green":   "Dashboard",
    "amber":   "Notifications",
    "red":     "What's Wrong?",
    "unknown": "Home",
}


class HealthStatusCard(QWidget):
    """
    Full-width ambient health status card for the home page.

    Receives HealthSnapshot objects via ``on_health_update(snapshot)`` and
    refreshes its display without any new I/O.
    """

    navigate_to = pyqtSignal(str)   # emitted when CTA is clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state: str        = "unknown"
        self._cta_page: str     = "Home"
        self._setup_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("healthStatusCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Card frame
        self._frame = QFrame()
        self._frame.setObjectName("healthFrame")
        self._apply_state_style("unknown")
        frame_lay = QVBoxLayout(self._frame)
        frame_lay.setContentsMargins(14, 10, 14, 8)
        frame_lay.setSpacing(4)

        # ── Top row: indicator | text | CTA ─────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self._icon_lbl = QLabel("○")
        self._icon_lbl.setFixedWidth(28)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_icon_style("TEXT_MUTED")

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self._headline_lbl = QLabel("Gathering health data…")
        _s.themed_ss(
            self._headline_lbl,
            "font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;",
        )
        self._headline_lbl.setWordWrap(True)

        self._sub_lbl = QLabel(
            "NetSentinel is reading from its monitors. This updates every 60 seconds."
        )
        _s.themed_ss(
            self._sub_lbl,
            "font-size:11px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;",
        )
        self._sub_lbl.setWordWrap(True)

        self._ts_lbl = QLabel("")
        _s.themed_ss(
            self._ts_lbl,
            "font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;",
        )

        text_col.addWidget(self._headline_lbl)
        text_col.addWidget(self._sub_lbl)
        text_col.addWidget(self._ts_lbl)

        self._cta_btn = QPushButton("View Dashboard →")
        self._cta_btn.setFixedHeight(28)
        self._cta_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cta_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self._apply_cta_style("ACCENT")
        self._cta_btn.clicked.connect(self._on_cta)

        top_row.addWidget(self._icon_lbl)
        top_row.addLayout(text_col, 1)
        top_row.addWidget(self._cta_btn)
        frame_lay.addLayout(top_row)

        # ── Sparkline (S2-6) ─────────────────────────────────────────────────
        self._sparkline = _HealthSparkline(self._frame)
        self._sparkline.refresh()
        frame_lay.addWidget(self._sparkline)

        outer.addWidget(self._frame)

    # ── Public slot ───────────────────────────────────────────────────────────

    def on_health_update(self, snapshot) -> None:
        """Called by app.py whenever HealthWorker emits result_ready."""
        _append_snapshot(snapshot)
        self._sparkline.refresh()
        self._state    = snapshot.state
        self._cta_page = _CTA_PAGE.get(snapshot.state, "Home")

        self._apply_state_style(snapshot.state)

        icon_colour_name = _STATE_ICON_COLOUR.get(snapshot.state, "TEXT_MUTED")
        self._icon_lbl.setText(_STATE_ICON.get(snapshot.state, "○"))
        self._set_icon_style(icon_colour_name)

        self._headline_lbl.setText(snapshot.headline)
        self._sub_lbl.setText(snapshot.sub_text)

        ts = snapshot.checked_at.strftime("Last checked %H:%M")
        if snapshot.state != "unknown":
            ts += f"  ·  Score: {snapshot.score}/100"
        self._ts_lbl.setText(ts)

        cta_label = _CTA_LABEL.get(snapshot.state, "View Dashboard →")
        self._cta_btn.setText(cta_label)

        btn_colour_name = _STATE_ICON_COLOUR.get(snapshot.state, "ACCENT")
        if snapshot.state == "unknown":
            btn_colour_name = "ACCENT"
        self._apply_cta_style(btn_colour_name)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _on_cta(self) -> None:
        self.navigate_to.emit(self._cta_page)

    def _set_icon_style(self, colour_name: str) -> None:
        _s.themed_ss(self._icon_lbl, lambda cn=colour_name: (
            f"font-size:20px; font-weight:bold; color:{getattr(_s, cn)};"
            " background:transparent; border:none;"
        ))

    def _apply_state_style(self, state: str) -> None:
        border_name = _STATE_BORDER.get(state, "BORDER")
        bg_name     = _STATE_BG.get(state, "BG_CARD")
        # Crisp neutral border on all four sides; the coloured left accent + internal
        # status icon convey state (avoids the washed-out translucent-colour border).
        _s.themed_ss(self._frame, lambda bn=border_name, gn=bg_name: (
            f"QFrame#healthFrame {{"
            f" background:{getattr(_s, gn)};"
            f" border:1px solid {_s.BORDER};"
            f" border-left:3px solid {getattr(_s, bn)};"
            f" border-radius:{CARD_RADIUS};"
            f"}}"
        ))

    def _apply_cta_style(self, colour_name: str) -> None:
        _s.themed_ss(self._cta_btn, lambda cn=colour_name: (
            f"QPushButton {{ background:transparent; color:{getattr(_s, cn)};"
            f" border:1px solid {getattr(_s, cn)}88; border-radius:4px;"
            f" font-size:11px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{_s.BG_HOVER}; color:{getattr(_s, cn)}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{getattr(_s, cn)}; }}"
        ))

    # ── Optional: expose sparkline for testing ────────────────────────────────

    def sparkline(self) -> _HealthSparkline:
        return self._sparkline

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def get_current_state(self) -> str:
        return self._state

    def get_current_headline(self) -> str:
        return self._headline_lbl.text()


def _format_stable(hours: float) -> str:
    """Convert hours to a human-readable stable duration string."""
    if hours >= 48:
        days = int(hours / 24)
        return f"{days} day{'s' if days != 1 else ''}"
    if hours >= 2:
        return f"{int(hours)} hour{'s' if int(hours) != 1 else ''}"
    mins = int(hours * 60)
    return f"{mins} minute{'s' if mins != 1 else ''}"
