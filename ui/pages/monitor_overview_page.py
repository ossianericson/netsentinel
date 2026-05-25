"""
MonitorOverviewPage — single-glance security posture for the Analysis section.

Shows one tile per active monitor so a recurring user can confirm "all green"
without visiting six separate pages.  No new logic — purely aggregates state
pushed by dashboard.py via the public setter methods below.

Tile grid:
  Network Grade  (top, full-width accent tile)
  ARP Spoof Watch · DHCP Rogue Monitor · Broadcast Storm
  IoT Anomalies  · Open Ports (last scan) · CVE Matches
"""
from __future__ import annotations

import datetime
import time
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT,
    AMBER,
    BG_CARD,
    BG_DARK,
    BORDER,
    CARD_RADIUS,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from ui.widgets.animated_kpi import AnimatedKpi


class _EventSparkline(QWidget):
    """
    VIZ-6: 80×16 QPainter bar chart showing event counts for the last 6 hours.

    Each bar = 1 hour (oldest left, newest right).
    Call set_counts(list[int]) with 6 integer values to update.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 16)
        self._counts: list = []

    def set_counts(self, counts: list) -> None:
        self._counts = list(counts[-6:])
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        counts = self._counts or [0] * 6
        w, h = self.width(), self.height()
        n = len(counts)
        if n == 0:
            p.end()
            return
        mx = max(counts) or 1
        bar_w = max(1, w // n - 1)
        gap = (w - bar_w * n) // max(n - 1, 1)
        for i, v in enumerate(counts):
            bh = max(2, int((v / mx) * (h - 2)))
            x = i * (bar_w + gap)
            alpha = "CC" if i == n - 1 else "66"
            color_hex = ACCENT + alpha
            p.setBrush(QColor(color_hex))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(x, h - bh, bar_w, bh)
        p.end()


def _status_tile(
    icon: str,
    title: str,
    value: str,
    sub: str,
    color: str,
    target: str,
) -> tuple["_StatusTile", "_StatusTile"]:
    """Return a _StatusTile instance ready to insert into the grid."""
    tile = _StatusTile(icon, title, value, sub, color, target)
    return tile


def _age_string(ts: float) -> str:
    """Human-readable 'X ago' from a Unix timestamp."""
    delta = time.time() - ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


def _health_color(ts: Optional[float]) -> str:
    """Green < 5 min, amber < 1 h, grey = no data or > 1 h."""
    if ts is None:
        return TEXT_MUTED
    delta = time.time() - ts
    if delta < 300:
        return GREEN
    if delta < 3600:
        return AMBER
    return TEXT_MUTED


class _StatusTile(QFrame):
    """Clickable status tile — icon, title, value, subtitle, health dot, age."""

    clicked = pyqtSignal(str)  # nav target

    def __init__(
        self,
        icon: str,
        title: str,
        value: str,
        sub: str,
        color: str,
        target: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._target = target
        self._last_event_ts: Optional[float] = None
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._base_style = (
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
            f"QFrame:hover {{ border-color:{ACCENT}; }}"
        )
        self.setStyleSheet(self._base_style)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.setContentsMargins(0, 0, 0, 0)
        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setStyleSheet(
            f"font-size:13px; color:{color}; background:transparent; border:none;"
        )
        self._icon_lbl.setFixedWidth(18)
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"font-size:10px; font-weight:600; color:{TEXT_SECONDARY};"
            " background:transparent; border:none; letter-spacing:0.5px;"
        )
        self._dot_lbl = QLabel("●")
        self._dot_lbl.setFixedWidth(12)
        self._dot_lbl.setStyleSheet(
            f"font-size:8px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        title_row.addWidget(self._icon_lbl)
        title_row.addWidget(self._title_lbl, 1)
        title_row.addWidget(self._dot_lbl)
        lay.addLayout(title_row)

        self._value_lbl = AnimatedKpi(value)
        self._value_lbl.setStyleSheet(
            f"font-size:22px; font-weight:bold; color:{color};"
            " background:transparent; border:none;"
        )
        lay.addWidget(self._value_lbl)

        self._sub_lbl = QLabel(sub)
        self._sub_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        lay.addWidget(self._sub_lbl)

        self._age_lbl = QLabel("")
        self._age_lbl.setStyleSheet(
            f"font-size:9px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        lay.addWidget(self._age_lbl)

        # VIZ-6: hourly event sparkline
        self._evtsparkline = _EventSparkline(self)
        lay.addWidget(self._evtsparkline)

    def set_hourly_counts(self, counts: list) -> None:
        """Push 6-hourly event counts to the sparkline."""
        self._evtsparkline.set_counts(counts)

    def set_active(self, active: bool) -> None:
        if active:
            self.setStyleSheet(
                f"QFrame {{ background:{ACCENT}1A; border:1px solid {ACCENT}44;"
                f" border-left:3px solid {ACCENT}; border-radius:{CARD_RADIUS}; }}"
                f"QFrame:hover {{ border-color:{ACCENT}; border-left:3px solid {ACCENT}; }}"
            )
        else:
            self.setStyleSheet(self._base_style)

    def update(self, value: str, sub: str, color: str) -> None:
        self._value_lbl.setStyleSheet(
            f"font-size:22px; font-weight:bold; color:{color};"
            " background:transparent; border:none;"
        )
        try:
            self._value_lbl.set_value(int(value))
        except (ValueError, TypeError):
            self._value_lbl.setText(value)
        self._icon_lbl.setStyleSheet(
            f"font-size:13px; color:{color}; background:transparent; border:none;"
        )
        self._sub_lbl.setText(sub)

    def set_last_event_ts(self, ts: Optional[float]) -> None:
        self._last_event_ts = ts
        self.refresh_age()

    def refresh_age(self) -> None:
        """Refresh the 'last event X ago' label and health dot."""
        dot_color = _health_color(self._last_event_ts)
        self._dot_lbl.setStyleSheet(
            f"font-size:8px; color:{dot_color}; background:transparent; border:none;"
        )
        if self._last_event_ts is not None:
            self._age_lbl.setText(f"Last event: {_age_string(self._last_event_ts)}")
        else:
            self._age_lbl.setText("")

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self._target)
        super().mousePressEvent(event)


class _GradeTile(QFrame):
    """Full-width Network Grade tile with accent border."""

    clicked = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {ACCENT}44;"
            f" border-radius:{CARD_RADIUS}; }}"
            f"QFrame:hover {{ border-color:{ACCENT}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(16)

        self._grade_circle = QLabel("–")
        self._grade_circle.setFixedSize(56, 56)
        self._grade_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grade_circle.setStyleSheet(
            f"font-size:24px; font-weight:bold; color:{TEXT_SECONDARY};"
            f" border:3px solid {BORDER}; border-radius:28px; background:{BG_CARD};"
        )
        lay.addWidget(self._grade_circle)

        right = QVBoxLayout()
        right.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title = QLabel("Network Grade")
        title.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        self._details_btn = QPushButton("?")
        self._details_btn.setFixedSize(18, 16)
        self._details_btn.setVisible(False)
        self._details_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._details_btn.setToolTip("Show grade breakdown")
        self._details_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:none;"
            f" font-size:9px; border-radius:3px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        self._details_btn.clicked.connect(self._on_details_clicked)
        title_row.addWidget(title)
        title_row.addWidget(self._details_btn)
        title_row.addStretch()
        self._sub_lbl = QLabel("Run a network grade scan to see your security score →")
        self._sub_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        right.addLayout(title_row)
        right.addWidget(self._sub_lbl)
        lay.addLayout(right, 1)
        self._dimensions: list = []

    def update(self, grade: str, sub: str, color: str) -> None:
        self._grade_circle.setText(grade)
        self._grade_circle.setStyleSheet(
            f"font-size:24px; font-weight:bold; color:{color};"
            f" border:3px solid {color}; border-radius:28px; background:{BG_CARD};"
        )
        self._sub_lbl.setText(sub)

    def set_dimensions(self, dimensions: list) -> None:
        self._dimensions = dimensions or []
        self._details_btn.setVisible(bool(dimensions))

    def _on_details_clicked(self) -> None:
        from ui.pages.home_page import _GradeBreakdownDialog
        grade = self._grade_circle.text()
        dlg = _GradeBreakdownDialog(grade, self._dimensions, parent=self)
        dlg.exec()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit("Network Grade")
        super().mousePressEvent(event)


class MonitorOverviewPage(QWidget):
    """Single-glance view of every active detection monitor."""

    navigate_to = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._last_scan_ts: Optional[datetime.datetime] = None
        self._store = None
        self._build_ui()
        self._age_timer = QTimer(self)
        self._age_timer.setInterval(60_000)
        self._age_timer.timeout.connect(self._refresh_ages)
        self._age_timer.start()
        # VIZ-6: refresh sparklines every 5 minutes
        self._sparkline_timer = QTimer(self)
        self._sparkline_timer.setInterval(300_000)
        self._sparkline_timer.timeout.connect(self._refresh_event_sparklines)

    def set_store(self, store) -> None:
        """Inject MetricStore for VIZ-6 sparkline queries."""
        self._store = store
        self._sparkline_timer.start()
        self._refresh_event_sparklines()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"QWidget {{ background:{BG_DARK}; }}")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # ── Page header ───────────────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(0)
        page_title = QLabel("Monitor Overview")
        page_title.setStyleSheet(
            f"font-size:14px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        self._last_scan_lbl = QLabel("")
        self._last_scan_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        self._last_scan_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        hdr_row.addWidget(page_title)
        hdr_row.addStretch()
        hdr_row.addWidget(self._last_scan_lbl)
        lay.addLayout(hdr_row)

        sub = QLabel(
            "Status of every active detection monitor — click any tile to go to that page."
        )
        sub.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        lay.addWidget(sub)

        # ── Grade tile (full width) ───────────────────────────────────────────
        self._grade_tile = _GradeTile()
        self._grade_tile.clicked.connect(self.navigate_to.emit)
        lay.addWidget(self._grade_tile)

        # ── Section label ─────────────────────────────────────────────────────
        sec_lbl = QLabel("DETECTION MONITORS")
        sec_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; letter-spacing:1px; padding-top:2px;"
        )
        lay.addWidget(sec_lbl)

        # ── 3×2 tile grid ─────────────────────────────────────────────────────
        grid_w = QWidget()
        grid_w.setStyleSheet("background:transparent;")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        self._tile_arp   = _StatusTile("◉", "ARP SPOOF WATCH",    "Off", "Not running", TEXT_MUTED,      "ARP Spoof Watch")
        self._tile_dhcp  = _StatusTile("◉", "DHCP ROGUE MONITOR", "Off", "Not running", TEXT_MUTED,      "DHCP Rogue Monitor")
        self._tile_storm = _StatusTile("◈", "BROADCAST STORM",    "–",   "Not measured",TEXT_MUTED,      "Broadcast Storm")
        self._tile_iot   = _StatusTile("◎", "IOT ANOMALIES",      "–",   "Not measured",TEXT_MUTED,      "IoT Behaviour")
        self._tile_ports = _StatusTile("⊙", "OPEN PORTS",         "–",   "No scan yet", TEXT_MUTED,      "Port Scan (TCP)")
        self._tile_cve   = _StatusTile("⚠", "CVE MATCHES",        "–",   "No data yet", TEXT_MUTED,      "CVE Lookup")
        self._tile_auto  = _StatusTile("⚡", "AUTOMATION",         "–",   "No rules",    TEXT_MUTED,      "Automation Hooks")

        for tile in (self._tile_arp, self._tile_dhcp, self._tile_storm,
                     self._tile_iot, self._tile_ports, self._tile_cve,
                     self._tile_auto):
            tile.clicked.connect(self.navigate_to.emit)

        grid.addWidget(self._tile_arp,   0, 0)
        grid.addWidget(self._tile_dhcp,  0, 1)
        grid.addWidget(self._tile_storm, 0, 2)
        grid.addWidget(self._tile_iot,   1, 0)
        grid.addWidget(self._tile_ports, 1, 1)
        grid.addWidget(self._tile_cve,   1, 2)
        grid.addWidget(self._tile_auto,  2, 0)

        lay.addWidget(grid_w)
        lay.addStretch()

    # ── Age refresh ──────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:  # type: ignore[override]
        self._refresh_ages()
        super().showEvent(event)

    def _refresh_ages(self) -> None:
        for tile in (self._tile_arp, self._tile_dhcp, self._tile_storm,
                     self._tile_iot, self._tile_ports, self._tile_cve,
                     self._tile_auto):
            tile.refresh_age()

    def _refresh_event_sparklines(self) -> None:
        """VIZ-6: Query per-hour event counts and push to each tile sparkline."""
        if self._store is None:
            return
        try:
            events = self._store.query_device_events(hours=6.0)
        except Exception:
            return
        now = time.time()
        counts = [0] * 6
        for evt in events:
            bucket = int((now - evt.ts) / 3600)
            if 0 <= bucket < 6:
                counts[5 - bucket] += 1
        for tile in (self._tile_arp, self._tile_dhcp, self._tile_storm,
                     self._tile_iot, self._tile_ports, self._tile_cve,
                     self._tile_auto):
            tile.set_hourly_counts(counts)

    def set_monitor_event_times(
        self,
        arp: Optional[float] = None,
        dhcp: Optional[float] = None,
        storm: Optional[float] = None,
        iot: Optional[float] = None,
        ports: Optional[float] = None,
        cve: Optional[float] = None,
    ) -> None:
        """Set last-event timestamps (Unix seconds) for each monitor tile."""
        self._tile_arp.set_last_event_ts(arp)
        self._tile_dhcp.set_last_event_ts(dhcp)
        self._tile_storm.set_last_event_ts(storm)
        self._tile_iot.set_last_event_ts(iot)
        self._tile_ports.set_last_event_ts(ports)
        self._tile_cve.set_last_event_ts(cve)

    # ── Public setters called by dashboard.py ─────────────────────────────────

    def set_grade(self, grade: str, score: float) -> None:  # noqa: ARG002
        if grade in ("A", "B"):
            color = GREEN
        elif grade == "C":
            color = AMBER
        else:
            color = RED
        sub = f"Score {score:.0f}/100 — click (?) for dimension breakdown"
        self._grade_tile.update(grade, sub, color)

    def set_grade_details(self, grade: str, score: float, dimensions: list) -> None:
        self.set_grade(grade, score)
        self._grade_tile.set_dimensions(dimensions)

    def set_arp_status(self, running: bool, alerted: bool) -> None:
        if alerted:
            self._tile_arp.update("Alert", "Spoof detected", RED)
        elif running:
            self._tile_arp.update("On", "Monitoring",      GREEN)
        else:
            self._tile_arp.update("Off", "Not running",    TEXT_MUTED)
        self._tile_arp.set_active(running or alerted)

    def set_dhcp_status(self, running: bool) -> None:
        if running:
            self._tile_dhcp.update("On",  "Monitoring",    GREEN)
        else:
            self._tile_dhcp.update("Off", "Not running",   TEXT_MUTED)
        self._tile_dhcp.set_active(running)

    def set_storm_status(self, level: str) -> None:
        if level == "STORM":
            self._tile_storm.update("Storm", "Flooding detected",  RED)
        elif level == "WARNING":
            self._tile_storm.update("Warn",  "Elevated broadcast", AMBER)
        else:
            self._tile_storm.update("Clean", "No storm",           GREEN)
        self._tile_storm.set_active(level in ("STORM", "WARNING"))

    def set_iot_anomaly_count(self, count: int) -> None:
        if count > 0:
            self._tile_iot.update(str(count), f"anomal{'y' if count == 1 else 'ies'}", AMBER)
        else:
            self._tile_iot.update("0", "No anomalies", GREEN)
        self._tile_iot.set_active(count > 0)

    def set_open_port_count(self, count: int) -> None:
        if count > 0:
            color = AMBER if count < 5 else RED
            self._tile_ports.update(str(count), f"open port{'s' if count != 1 else ''}", color)
        elif count == 0:
            self._tile_ports.update("0", "No open ports", GREEN)
        else:
            self._tile_ports.update("–", "No scan yet", TEXT_MUTED)
        self._tile_ports.set_active(count >= 0)

    def set_cve_count(self, count: int) -> None:
        if count > 0:
            self._tile_cve.update(str(count), f"match{'es' if count != 1 else ''} found", RED)
        elif count == 0:
            self._tile_cve.update("0", "No matches", GREEN)
        else:
            self._tile_cve.update("–", "No data yet", TEXT_MUTED)
        self._tile_cve.set_active(count >= 0)

    def set_automation_status(self, rule_count: int, last_triggered_ts: float) -> None:
        import time as _time
        if rule_count == 0:
            self._tile_auto.update("–", "No rules", TEXT_MUTED)
        elif last_triggered_ts > 0 and (_time.time() - last_triggered_ts) < 86400:
            self._tile_auto.update(str(rule_count), "Fired in last 24h", GREEN)
            self._tile_auto.set_last_event_ts(last_triggered_ts)
        else:
            self._tile_auto.update(str(rule_count), f"rule{'s' if rule_count != 1 else ''} enabled", ACCENT)
        self._tile_auto.set_active(rule_count > 0)

    def set_last_scan_time(self, ts: Optional[datetime.datetime]) -> None:
        self._last_scan_ts = ts
        if ts is None:
            self._last_scan_lbl.setText("")
        else:
            self._last_scan_lbl.setText(f"Last scan: {ts.strftime('%H:%M')}")
