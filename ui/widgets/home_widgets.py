"""
home_widgets.py — Reusable helper widgets for the Home page.

Extracted from ui/pages/home_page.py (Sprint 4, S3-3).
Sprint 7 (S14-1): FreshnessStrip, GettingStartedCard, _GradeBreakdownDialog,
StandardWelcomePage, ProWelcomePage moved here.
"""
from __future__ import annotations

import datetime
import json

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QSettings, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE, AMBER,
    BG_CARD, BG_DARK, BG_HOVER, BORDER,
    CARD_RADIUS, GRADE_B_COLOR, GREEN, NAV_BAR,
    PRO_WARN_BG, RED, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, UPDATE_BAR_BG, UPDATE_BAR_BORDER, UPDATE_BAR_FG,
    WHITE,
)


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
        self._colour = TEXT_SECONDARY

        self._arc_anim: QVariantAnimation | None = None
        self._score_anim: QVariantAnimation | None = None
        self.setToolTip(
            "Network Grade — A–F score across 8 health dimensions."
        )

    def set_grade(self, grade: str, score: float) -> None:
        from ui.theme import _reduce_motion
        if grade in ("A", "B"):
            self._colour = GREEN
        elif grade == "C":
            self._colour = AMBER
        else:
            self._colour = RED

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
        pen_track = QPen(QColor(BORDER), thickness)
        pen_track.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen_track)
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))

        # Filled arc
        if self._arc_pct > 0:
            pen_arc = QPen(QColor(self._colour), thickness)
            pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen_arc)
            span_angle = int(self._arc_pct * 360 * 16)
            p.drawArc(
                QRectF(cx - r, cy - r, 2 * r, 2 * r),
                90 * 16,
                -span_angle,
            )

        # Grade letter (centre)
        p.setPen(QPen(QColor(self._colour), 1))
        font = p.font()
        font.setPointSize(18)
        font.setBold(True)
        p.setFont(font)
        letter_rect = QRectF(0, cy - 18, w, 22)
        p.drawText(letter_rect, Qt.AlignmentFlag.AlignCenter, self._grade)

        # Score (small, below letter)
        if self._score > 0:
            p.setPen(QPen(QColor(TEXT_MUTED), 1))
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
        self._colour = ACCENT

    def set_data(self, points: list[float], colour: str = ACCENT) -> None:
        self._points = list(points)
        self._colour = colour
        self.update()

    def paintEvent(self, event) -> None:
        pts = self._points
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(pts) < 2:
            p.setPen(QColor(BORDER))
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
            painter.setPen(QColor(TEXT_MUTED))
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
        color = GREEN if last_score >= 70 else (AMBER if last_score >= 50 else RED)
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
        self.setStyleSheet(
            f"QFrame#statusTicker {{ background:{BG_HOVER}; border:1px solid {BORDER};"
            f" border-radius:4px; }}"
            f"QFrame#statusTicker:hover {{ border-color:{ACCENT}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)

        icon_lbl = QLabel("◷")
        icon_lbl.setFixedWidth(14)
        icon_lbl.setStyleSheet(f"font-size:11px; color:{ACCENT}; border:none; background:transparent;")
        lay.addWidget(icon_lbl)

        self._content_lbl = QLabel("–")
        self._content_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; border:none; background:transparent;"
        )
        lay.addWidget(self._content_lbl, 1)

        nav_lbl = QLabel("Timeline →")
        nav_lbl.setStyleSheet(
            f"font-size:10px; color:{ACCENT}; border:none; background:transparent;"
        )
        lay.addWidget(nav_lbl)

        self.hide()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.navigate_to.emit("Timeline")
        super().mousePressEvent(event)

    def refresh(self, store=None) -> None:
        s = store or self._store
        if s is None:
            return
        import time as _t
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


# ── FreshnessStrip ────────────────────────────────────────────────────────────

class FreshnessStrip(QFrame):
    """Top-of-page strip: last-scan timestamp, monitor status pills, scan progress."""

    rescan_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("freshnessStrip")
        self.setFixedHeight(30)
        self.setStyleSheet(
            f"QFrame#freshnessStrip {{ background:{NAV_BAR}; border-bottom:1px solid {BORDER}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 8, 0)
        row.setSpacing(12)

        self._fs_scan_lbl = QLabel("Last scan: —")
        self._fs_scan_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        row.addWidget(self._fs_scan_lbl)

        _sep = QLabel("|")
        _sep.setStyleSheet(f"font-size:11px; color:{BORDER}; background:transparent; border:none;")
        row.addWidget(_sep)

        self._fs_pill_arp   = self._make_fs_pill("ARP")
        self._fs_pill_dhcp  = self._make_fs_pill("DHCP")
        self._fs_pill_storm = self._make_fs_pill("Storm")
        self._fs_pill_log   = self._make_fs_pill("Logger")
        for pill in (self._fs_pill_arp, self._fs_pill_dhcp, self._fs_pill_storm, self._fs_pill_log):
            row.addWidget(pill)

        _sep2 = QLabel("|")
        _sep2.setStyleSheet(f"font-size:11px; color:{BORDER}; background:transparent; border:none;")
        row.addWidget(_sep2)

        self._fs_next_scan_lbl = QLabel("")
        self._fs_next_scan_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        row.addWidget(self._fs_next_scan_lbl)
        self.refresh_next_scan_label()

        row.addStretch()

        self._scan_progress_lbl = QLabel("")
        self._scan_progress_lbl.setStyleSheet(
            f"font-size:10px; color:{AMBER}; background:transparent; border:none;"
        )
        self._scan_progress_lbl.setVisible(False)
        row.addWidget(self._scan_progress_lbl)

        _btn = QPushButton("↻")
        _btn.setFixedSize(24, 22)
        _btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _btn.setToolTip("Rescan network")
        _btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:none;"
            f" font-size:14px; border-radius:3px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:{BORDER}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:{BORDER}; }}"
        )
        _btn.clicked.connect(self.rescan_requested)
        row.addWidget(_btn)

        qs = QSettings("NetSentinel", "NetSentinel")
        _ts = qs.value("home/last_scan_ts", "")
        if _ts:
            try:
                _dt = datetime.datetime.fromisoformat(_ts)
                self._fs_scan_lbl.setText(f"Last scan: {self._fmt_age(_dt)}")
            except ValueError:
                pass

    @staticmethod
    def _make_fs_pill(label: str) -> QLabel:
        lbl = QLabel(f"○ {label}")
        lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        return lbl

    @staticmethod
    def _fmt_age(dt: datetime.datetime) -> str:
        delta = datetime.datetime.now() - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{secs // 60} min ago"
        if secs < 86400:
            h = secs // 3600
            return f"{h} hour{'s' if h != 1 else ''} ago"
        d = secs // 86400
        return f"{d} day{'s' if d != 1 else ''} ago"

    def update_freshness(self, arp: bool = False, dhcp: bool = False,
                          storm: bool = False, logger: bool = False) -> None:
        def _set_pill(pill: QLabel, active: bool, name: str) -> None:
            if active:
                pill.setText(f"● {name}")
                pill.setStyleSheet(
                    f"font-size:10px; color:{GREEN}; background:transparent; border:none;"
                )
            else:
                pill.setText(f"○ {name}")
                pill.setStyleSheet(
                    f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
                )
        _set_pill(self._fs_pill_arp,   arp,    "ARP")
        _set_pill(self._fs_pill_dhcp,  dhcp,   "DHCP")
        _set_pill(self._fs_pill_storm, storm,  "Storm")
        _set_pill(self._fs_pill_log,   logger, "Logger")

    def refresh_next_scan_label(self) -> None:
        import time as _t
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("sched_scan/enabled", False, bool):
            self._fs_next_scan_lbl.setVisible(False)
            return
        next_ts = float(qs.value("sched_scan/next_ts", 0))
        self._fs_next_scan_lbl.setVisible(True)
        if next_ts > _t.time():
            nxt = datetime.datetime.fromtimestamp(next_ts)
            now = datetime.datetime.now()
            if nxt.date() == now.date():
                self._fs_next_scan_lbl.setText(f"Next scan: today {nxt.strftime('%H:%M')}")
            elif (nxt.date() - now.date()).days == 1:
                self._fs_next_scan_lbl.setText(f"Next scan: tomorrow {nxt.strftime('%H:%M')}")
            else:
                self._fs_next_scan_lbl.setText(f"Next scan: {nxt.strftime('%a %H:%M')}")
        else:
            self._fs_next_scan_lbl.setText("Next scan: pending")

    def set_scan_progress(self, message: str) -> None:
        if not message:
            self._scan_progress_lbl.setVisible(False)
            self._scan_progress_lbl.setText("")
            return
        text = message if len(message) <= 60 else message[:57] + "…"
        self._scan_progress_lbl.setText(text)
        self._scan_progress_lbl.setVisible(True)

    def set_scan_timestamp(self, text: str, style: str = "") -> None:
        self._fs_scan_lbl.setText(text)
        if style:
            self._fs_scan_lbl.setStyleSheet(style)


# ── GettingStartedCard ────────────────────────────────────────────────────────

class GettingStartedCard(QFrame):
    """Onboarding checklist: hardware connections + core setup steps."""

    add_plugin_requested = pyqtSignal(str)
    navigate_to = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("gettingStartedCard")
        self.setStyleSheet(
            f"QFrame#gettingStartedCard {{"
            f" background:{BG_CARD};"
            f" border:1px solid {BORDER};"
            f" border-left:3px solid {ACCENT};"
            f" border-radius:{CARD_RADIUS};"
            f"}}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 12, 12)
        outer.setSpacing(0)

        self._setup_collapsed = False
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(8)

        self._setup_hdr_lbl = QLabel("GETTING STARTED")
        self._setup_hdr_lbl.setStyleSheet(
            f"font-size:10px; font-weight:700; color:{ACCENT};"
            " background:transparent; border:none; letter-spacing:1.5px;"
        )
        self._setup_progress_lbl = QLabel("")
        self._setup_progress_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        self._setup_collapse_btn = QPushButton("▼")
        self._setup_collapse_btn.setFixedSize(18, 18)
        self._setup_collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_collapse_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:10px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        self._setup_collapse_btn.clicked.connect(self._toggle_collapse)
        hdr_row.addWidget(self._setup_hdr_lbl)
        hdr_row.addWidget(self._setup_progress_lbl)
        hdr_row.addStretch()
        hdr_row.addWidget(self._setup_collapse_btn)
        outer.addLayout(hdr_row)

        self._setup_body = QWidget()
        self._setup_body.setStyleSheet("background:transparent;")
        body_lay = QVBoxLayout(self._setup_body)
        body_lay.setContentsMargins(0, 8, 0, 0)
        body_lay.setSpacing(0)

        zte_path  = _bundled_plugin_path("zte_plugin.py")
        deco_path = _bundled_plugin_path("deco_plugin.py")

        _STEPS = [
            ("hw_zte",  "Connect 5G Modem",       "ZTE MC889 — signal data in every speed test",  zte_path,  None),
            ("hw_deco", "Connect Mesh Router",     "Deco XE75 — real hostnames in Devices & Map", deco_path, None),
            ("scan",    "Run your first scan",     "Discover all devices on your network",              None,     "Devices"),
            ("grade",   "Run a Network Grade",     "Score your network across 8 dimensions",            None,     "Network Grade"),
            ("arp",     "Turn on ARP Spoof Watch", "Detect address spoofing in real time",               None,     "ARP Spoof Watch"),
        ]

        self._setup_check_lbls: dict[str, QLabel]       = {}
        self._setup_step_rows:  dict[str, QWidget]      = {}
        self._setup_step_btns:  dict[str, QPushButton]  = {}
        _hw_keys = {"hw_zte", "hw_deco"}
        prev_section = None

        for key, title, subtitle, plugin_path, nav_target in _STEPS:
            section = "hw" if key in _hw_keys else "core"
            if section != prev_section:
                if prev_section == "hw":
                    sep = QFrame()
                    sep.setFrameShape(QFrame.Shape.HLine)
                    sep.setStyleSheet(f"border:none; border-top:1px solid {BORDER};")
                    sep.setFixedHeight(1)
                    body_lay.addSpacing(4)
                    body_lay.addWidget(sep)
                    body_lay.addSpacing(4)
                sec_lbl = QLabel("HARDWARE CONNECTIONS" if section == "hw" else "CORE SETUP")
                sec_lbl.setStyleSheet(
                    f"font-size:9px; font-weight:600; color:{TEXT_MUTED};"
                    " background:transparent; border:none; letter-spacing:0.8px;"
                    " padding-bottom:2px;"
                )
                body_lay.addWidget(sec_lbl)
                prev_section = section

            row = QWidget()
            row.setObjectName(f"setupRow_{key}")
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 3, 0, 3)
            rl.setSpacing(8)

            chk = QLabel("○")
            chk.setFixedWidth(14)
            chk.setStyleSheet(
                f"font-size:13px; color:{TEXT_MUTED}; background:transparent; border:none;"
            )
            self._setup_check_lbls[key] = chk

            text_col = QVBoxLayout()
            text_col.setSpacing(1)
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(
                f"font-size:11px; font-weight:500; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
            )
            text_col.addWidget(title_lbl)
            text_col.addWidget(sub_lbl)

            if plugin_path:
                btn = QPushButton("Add →")
                btn.setFixedHeight(24)
                btn.setFixedWidth(72)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
                    f" border-radius:3px; font-size:10px; font-weight:600; padding:0 8px; }}"
                    f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
                    f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
                )
                _p = plugin_path
                btn.clicked.connect(lambda _=False, p=_p: self.add_plugin_requested.emit(p))
            else:
                btn = QPushButton("→")
                btn.setFlat(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    f"QPushButton {{ color:{ACCENT}; font-size:14px; background:transparent;"
                    f" border:none; padding:0 4px; }}"
                    f"QPushButton:hover {{ color:{ACCENT_DARK}; background:transparent; }}"
                    f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:transparent; }}"
                )
                _t = nav_target
                btn.clicked.connect(lambda _=False, t=_t: self.navigate_to.emit(t))

            self._setup_step_btns[key] = btn
            self._setup_step_rows[key] = row

            rl.addWidget(chk)
            rl.addLayout(text_col, 1)
            rl.addWidget(btn)
            body_lay.addWidget(row)

        outer.addWidget(self._setup_body)

    def _toggle_collapse(self) -> None:
        self._setup_collapsed = not self._setup_collapsed
        self._setup_body.setVisible(not self._setup_collapsed)
        self._setup_collapse_btn.setText("▶" if self._setup_collapsed else "▼")

    def ensure_expanded(self) -> None:
        self.setVisible(True)
        if self._setup_collapsed:
            self._toggle_collapse()

    def _checklist_states(self, device_count: int = 0) -> dict:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            imported = set(_json.loads(qs.value("hardware/custom_scripts", "[]") or "[]"))
        except Exception:
            imported = set()
        zte_path  = _bundled_plugin_path("zte_plugin.py")
        deco_path = _bundled_plugin_path("deco_plugin.py")
        return {
            "hw_zte":  zte_path  in imported,
            "hw_deco": deco_path in imported,
            "scan":    device_count > 0,
            "grade":   qs.value("grade/last_run", False, type=bool),
            "arp":     qs.value("home/setup/arp_started", False, type=bool),
        }

    def refresh_checklist(self, device_count: int = 0) -> None:
        if not hasattr(self, "_setup_check_lbls"):
            return
        states = self._checklist_states(device_count)
        done_count = sum(states.values())
        total = len(states)
        for key, chk in self._setup_check_lbls.items():
            done = states.get(key, False)
            if done:
                chk.setText("✓")
                chk.setStyleSheet(
                    f"font-size:13px; color:{GREEN}; background:transparent; border:none;"
                )
                btn = self._setup_step_btns.get(key)
                if btn:
                    btn.setEnabled(False)
                    if key.startswith("hw_"):
                        btn.setText("✓ Added")
                    btn.setStyleSheet(
                        f"QPushButton {{ color:{GREEN}; font-size:10px; background:transparent;"
                        f" border:none; padding:0 4px; }}"
                        f"QPushButton:hover   {{ color:{GREEN}; background:transparent; }}"
                        f"QPushButton:pressed {{ color:{GREEN}; background:transparent; }}"
                        f"QPushButton:disabled {{ color:{GREEN}; background:transparent; }}"
                    )
            else:
                chk.setText("○")
                chk.setStyleSheet(
                    f"font-size:13px; color:{TEXT_MUTED}; background:transparent; border:none;"
                )
        self._setup_progress_lbl.setText(f"{done_count}/{total} done")
        if done_count == total:
            self._setup_hdr_lbl.setText("✓ SETUP COMPLETE")
            self._setup_hdr_lbl.setStyleSheet(
                f"font-size:10px; font-weight:700; color:{GREEN};"
                " background:transparent; border:none; letter-spacing:1.5px;"
            )
            from PyQt6.QtCore import QTimer as _QT
            _QT.singleShot(2000, lambda: self.setVisible(False))
        else:
            self._setup_hdr_lbl.setText("GETTING STARTED")
            self._setup_hdr_lbl.setStyleSheet(
                f"font-size:10px; font-weight:700; color:{ACCENT};"
                " background:transparent; border:none; letter-spacing:1.5px;"
            )


# ── _GradeBreakdownDialog ─────────────────────────────────────────────────────

class _GradeBreakdownDialog:
    """QDialog showing the grade sub-score breakdown."""

    def __new__(cls, grade: str, dimensions: list, parent=None):
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QScrollArea, QWidget, QFrame, QPushButton,
        )
        from PyQt6.QtCore import Qt
        from ui.styles import (
            ACCENT, AMBER, BG_CARD, BG_DARK, BORDER, GREEN, RED,
            TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
        )

        _GRADE_COLOR = {
            "A": GREEN, "B": GRADE_B_COLOR, "C": AMBER, "D": RED, "F": RED,
        }

        dlg = QDialog(parent)
        dlg.setWindowTitle("Network Grade Breakdown")
        dlg.setMinimumWidth(440)
        dlg.setStyleSheet(f"QDialog {{ background:{BG_DARK}; }}")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        hdr_row = QHBoxLayout()
        overall_lbl = QLabel(grade)
        _fg = _GRADE_COLOR.get(grade, TEXT_SECONDARY)
        overall_lbl.setStyleSheet(
            f"font-size:36px; font-weight:bold; color:{_fg};"
            f" background:{BG_CARD}; border:3px solid {_fg}; border-radius:28px;"
            f" min-width:56px; min-height:56px;"
        )
        overall_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overall_lbl.setFixedSize(56, 56)
        hdr_text = QLabel(
            "<b>Network Grade Breakdown</b><br>"
            f"<span style='font-size:11px; color:{TEXT_SECONDARY};'>"
            "Hover each row for thresholds. The lowest score determines the overall grade.</span>"
        )
        hdr_text.setTextFormat(Qt.TextFormat.RichText)
        hdr_text.setWordWrap(True)
        hdr_text.setStyleSheet(f"background:transparent; border:none; color:{TEXT_PRIMARY};")
        hdr_row.addWidget(overall_lbl)
        hdr_row.addSpacing(12)
        hdr_row.addWidget(hdr_text, 1)
        lay.addLayout(hdr_row)

        _grade_rank = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "N/A": 5}
        worst_dim = max(dimensions, key=lambda d: _grade_rank.get(getattr(d, "grade", "N/A"), 5)) if dimensions else None
        _DIM_NAV = {
            "Connection Uptime":          "DNS & Stability",
            "Average Latency":            "DNS & Stability",
            "Jitter (Call Quality)":      "Bandwidth Usage",
            "DNS Response Speed":         "DNS & Stability",
            "Download Speed":             "Speed Test",
            "Device Safety":              "Security Overview",
            "STP Health":                 "Broadcast Storm",
            "Broadcast Storm Level":      "Broadcast Storm",
        }
        if worst_dim is not None:
            tip_name = getattr(worst_dim, "name", "")
            tip_nav  = _DIM_NAV.get(tip_name, "")
            tip_grade = getattr(worst_dim, "grade", "")
            if tip_grade not in ("A", "B", "N/A") and tip_name:
                tip_frame = QFrame()
                tip_frame.setObjectName("breakdownTip")
                tip_frame.setStyleSheet(
                    f"QFrame#breakdownTip {{ background:{BG_CARD}; border:1px solid {AMBER}44;"
                    f" border-left:3px solid {AMBER}; border-radius:4px; }}"
                )
                tip_lay = QHBoxLayout(tip_frame)
                tip_lay.setContentsMargins(10, 6, 10, 6)
                tip_lay.setSpacing(8)
                tip_lbl = QLabel(
                    f"<b>Biggest improvement:</b> {tip_name} is grade "
                    f"<b style='color:{_GRADE_COLOR.get(tip_grade, AMBER)}'>{tip_grade}</b>"
                )
                tip_lbl.setTextFormat(Qt.TextFormat.RichText)
                tip_lbl.setStyleSheet(
                    f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
                )
                tip_lay.addWidget(tip_lbl, 1)
                if tip_nav:
                    go_btn = QPushButton(f"Go to {tip_nav} →")
                    go_btn.setFlat(True)
                    go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    go_btn.setStyleSheet(
                        f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
                        f" border:none; padding:0; }}"
                        f"QPushButton:hover {{ color:{ACCENT}; text-decoration:underline; }}"
                        f"QPushButton:pressed {{ color:{ACCENT}; }}"
                    )
                    go_btn.clicked.connect(dlg.accept)
                    tip_lay.addWidget(go_btn)
                lay.addWidget(tip_frame)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(340)
        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(4)
        scroll.setWidget(inner)

        _THRESHOLDS = {
            "Connection Uptime":     ("A: ≥99%", "B: ≥97%", "C: ≥95%", "D: ≥90%", "F: <90%"),
            "Average Latency":       ("A: <20ms", "B: <40ms", "C: <80ms", "D: <150ms", "F: ≥150ms"),
            "Jitter (Call Quality)": ("A: <5ms", "B: <10ms", "C: <20ms", "D: <40ms", "F: ≥40ms"),
            "DNS Response Speed":    ("A: <30ms", "B: <60ms", "C: <120ms", "D: <200ms", "F: ≥200ms"),
            "Download Speed":        ("A: ≥100Mbps", "B: ≥25Mbps", "C: ≥10Mbps", "D: ≥2Mbps", "F: <2Mbps"),
            "Device Safety":         ("A: 0 high-risk", "B: 0 rogue", "C: 1 medium-risk", "D/F: 2+"),
            "STP Health":            ("A: no rogue bridge", "C: 1 bridge event", "F: active storm"),
            "Broadcast Storm Level": ("A: <1%", "B: <5%", "C: <15%", "D: <30%", "F: ≥30%"),
        }
        for dim in dimensions:
            name  = getattr(dim, "name",  "")
            dgrade = getattr(dim, "grade", "N/A")
            value = getattr(dim, "value", "")
            msg   = getattr(dim, "message", "")

            row = QFrame()
            row.setObjectName("breakdownRow")
            row.setStyleSheet(
                f"QFrame#breakdownRow {{ background:{BG_CARD}; border:1px solid {BORDER};"
                f" border-radius:3px; }}"
            )
            _fg2 = _GRADE_COLOR.get(dgrade, TEXT_SECONDARY)
            _th  = " | ".join(_THRESHOLDS.get(name, ()))
            if _th:
                row.setToolTip(f"Thresholds: {_th}")

            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 5, 8, 5)
            rl.setSpacing(8)

            grade_badge = QLabel(dgrade)
            grade_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grade_badge.setFixedSize(28, 28)
            grade_badge.setStyleSheet(
                f"font-size:13px; font-weight:bold; color:{_fg2};"
                f" background:{BG_DARK}; border:2px solid {_fg2}; border-radius:14px;"
            )

            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(
                f"font-size:11px; font-weight:500; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )

            right_col = QVBoxLayout()
            right_col.setSpacing(1)
            val_lbl = QLabel(str(value))
            val_lbl.setStyleSheet(
                f"font-size:10px; color:{_fg2}; background:transparent; border:none;"
            )
            msg_lbl = QLabel(msg)
            msg_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
            )
            msg_lbl.setWordWrap(True)
            right_col.addWidget(val_lbl)
            right_col.addWidget(msg_lbl)

            rl.addWidget(grade_badge)
            rl.addWidget(name_lbl, 1)
            rl.addLayout(right_col, 2)
            inner_lay.addWidget(row)

        lay.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; font-size:11px; padding:0 16px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        return dlg


# ── StandardWelcomePage ───────────────────────────────────────────────────────

class StandardWelcomePage(QWidget):
    """
    Landing page shown when 'Home' is selected in Standard mode.
    Displays a 2-column feature card grid: 'WHAT EACH SECTION GIVES YOU'.
    """

    _FEATURES = [
        ("⚡", "Speed test",      AMBER,        ["Download / upload speed",
                                                      "Ookla or fallback backends",
                                                      "Historical trend chart"]),
        ("◎", "DNS & Stability", ACCENT,        ["Live ping + DNS latency graph",
                                                      "Outage detection & log",
                                                      "STP reconvergence signature"]),
        ("⊕", "Devices",         TEXT_PRIMARY,  ["IP, MAC, vendor, model",
                                                      "Right-click How to Fix",
                                                      "Availability history per device"]),
        ("▲", "Live Bandwidth",  TEXT_PRIMARY,  ["Per-device rx/tx Mbps",
                                                      "60-second rolling area chart",
                                                      "Session totals table"]),
        ("◼", "Network Grade",   TEXT_PRIMARY,  ["A–F across 8 dimensions",
                                                      "Colour-coded verdict per metric",
                                                      "Actionable fix tip per grade"]),
        ("↗", "Network Health Report", TEXT_PRIMARY, ["Self-contained HTML export",
                                                           "MTR hop table + outage log",
                                                           "Great for ISP support tickets"]),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setObjectName("homepageInner")
        inner.setStyleSheet(f"QWidget#homepageInner {{ background:{BG_DARK}; }}")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        hdr = QLabel("WHAT EACH SECTION GIVES YOU")
        hdr.setStyleSheet(
            f"font-size:10px; font-weight:700; color:{TEXT_SECONDARY};"
            " background:transparent; border:none; letter-spacing:1.5px;"
        )
        lay.addWidget(hdr)

        grid_w = QWidget()
        grid_w.setStyleSheet(f"background:{BG_DARK};")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        for i, (icon, title, icon_colour, bullets) in enumerate(self._FEATURES):
            card = self._make_card(icon, title, icon_colour, bullets)
            grid.addWidget(card, i // 2, i % 2)

        lay.addWidget(grid_w)
        lay.addStretch()

    @staticmethod
    def _make_card(icon: str, title: str, icon_colour: str,
                   bullets: list[str]) -> QFrame:
        card = QFrame()
        card.setObjectName("stdCapabilityCard")
        card.setStyleSheet(
            f"QFrame#stdCapabilityCard {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(12, 10, 12, 10)
        card_lay.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"font-size:14px; color:{icon_colour}; background:transparent; border:none;"
        )
        icon_lbl.setFixedWidth(18)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title_lbl, 1)
        card_lay.addLayout(title_row)

        for bullet in bullets:
            b = QLabel(bullet)
            b.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none; padding-left:4px;"
            )
            card_lay.addWidget(b)

        return card


# ── ProWelcomePage ────────────────────────────────────────────────────────────

class ProWelcomePage(QWidget):
    """
    Landing page shown when 'Home' is selected in Pro mode.
    Shows an admin-required warning and security audit capability cards.
    """

    _CAPABILITIES = [
        ("◎", "Port scanning",       ["• TCP connect + SYN (Scapy)",
                                           "• UDP scanner (DNS/SNMP/NTP)",
                                           "• Stealth / normal / fast modes"]),
        ("◎", "CVE tracker",         ["• NVD API v2 lookup per host",
                                           "• Lifecycle state machine",
                                           "• Days-open counter, owner field"]),
        ("◎", "Threat Intelligence", ["• Feodo Tracker + Emerging Threats",
                                           "• AbuseIPDB v2 lookup",
                                           "• Blocklist KPI tiles"]),
        ("◼", "TLS & exposure",      ["• Per-host cert expiry monitor",
                                           "• WAN / CGNAT / UPnP exposure",
                                           "• Cloud metadata probe"]),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setObjectName("homepageInner")
        inner.setStyleSheet(f"QWidget#homepageInner {{ background:{BG_DARK}; }}")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        hdr = QLabel("SECURITY AUDIT CAPABILITIES")
        hdr.setStyleSheet(
            f"font-size:10px; font-weight:700; color:{TEXT_SECONDARY};"
            " background:transparent; letter-spacing:1.5px; border:none;"
        )
        lay.addWidget(hdr)

        grid_w = QWidget()
        grid_w.setStyleSheet(f"background:{BG_DARK};")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        for i, (icon, title, bullets) in enumerate(self._CAPABILITIES):
            card = self._make_card(icon, title, bullets)
            grid.addWidget(card, i // 2, i % 2)

        lay.addWidget(grid_w)
        lay.addStretch()

    @staticmethod
    def _make_card(icon: str, title: str, bullets: list[str]) -> QFrame:
        card = QFrame()
        card.setObjectName("secCapabilityCard")
        card.setStyleSheet(
            f"QFrame#secCapabilityCard {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(12, 10, 12, 10)
        card_lay.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"font-size:14px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        icon_lbl.setFixedWidth(18)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title_lbl, 1)
        card_lay.addLayout(title_row)

        for bullet in bullets:
            b = QLabel(bullet)
            b.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none; padding-left:4px;"
            )
            card_lay.addWidget(b)

        return card
