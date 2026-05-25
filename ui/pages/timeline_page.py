"""
TimelinePage — reverse-chronological unified event feed (TIMELINE-1/2).

Synthesises events from existing MetricStore tables:
  • device_event  — device join/leave/change
  • alert_log     — fired alert rules
  • cve_lifecycle — CVE state changes
  • speed_test    — speed test completions

Source filter chips at the top let the user hide/show categories.
A "Today at a glance" pinned summary header shows counts for the current day.
"""
from __future__ import annotations

import datetime
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore    import Qt, QSettings, QTimer, pyqtSlot
from PyQt6.QtGui     import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BG_HOVER, BORDER, GREEN, RED,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)

if TYPE_CHECKING:
    from modules.metric_store import MetricStore


# ── Source tags ────────────────────────────────────────────────────────────────

_SOURCE_DEVICE = "Devices"
_SOURCE_ALERTS = "Alerts"
_SOURCE_CVE    = "CVEs"
_SOURCE_SPEED  = "Speed Tests"

_SOURCE_COLORS = {
    _SOURCE_DEVICE: ACCENT,
    _SOURCE_ALERTS: AMBER,
    _SOURCE_CVE:    RED,
    _SOURCE_SPEED:  GREEN,
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_ts(ts: float) -> str:
    dt = datetime.datetime.fromtimestamp(ts)
    now = datetime.datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    elif (now.date() - dt.date()).days == 1:
        return f"Yesterday {dt.strftime('%H:%M')}"
    elif (now.date() - dt.date()).days < 7:
        return dt.strftime("%a %H:%M")
    return dt.strftime("%b %d, %H:%M")


def _date_label(ts: float) -> str:
    dt = datetime.datetime.fromtimestamp(ts)
    now = datetime.datetime.now()
    if dt.date() == now.date():
        return "Today"
    elif (now.date() - dt.date()).days == 1:
        return "Yesterday"
    return dt.strftime("%A, %B %d")


# ── Event data class ───────────────────────────────────────────────────────────

class _Ev:
    __slots__ = ("ts", "source", "title", "detail", "severity")

    def __init__(self, ts: float, source: str, title: str,
                 detail: str = "", severity: str = "info"):
        self.ts       = ts
        self.source   = source
        self.title    = title
        self.detail   = detail
        self.severity = severity


# ── Page ──────────────────────────────────────────────────────────────────────

class TimelinePage(QWidget):
    def __init__(self, store: "MetricStore", parent=None):
        super().__init__(parent)
        self._store   = store
        self._active_sources: set[str] = {
            _SOURCE_DEVICE, _SOURCE_ALERTS, _SOURCE_CVE, _SOURCE_SPEED
        }
        self._events: list[_Ev] = []
        self._setup_ui()

        # Auto-refresh every 60 s
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self._reload)
        self._timer.start()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("TimelinePage")
        self.setStyleSheet(f"QWidget#TimelinePage {{ background:{BG_DARK}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 0)
        outer.setSpacing(10)

        # Title
        from ui.widgets.page_header import PageHeaderBar
        outer.addWidget(PageHeaderBar("Network Timeline"))

        # ── TIMELINE-2: Today at a glance ─────────────────────────────────────
        self._glance = QFrame()
        self._glance.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:4px; }}"
        )
        glance_lay = QHBoxLayout(self._glance)
        glance_lay.setContentsMargins(14, 8, 14, 8)
        glance_lay.setSpacing(20)

        _today_hdr = QLabel("TODAY AT A GLANCE")
        _today_hdr.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{TEXT_MUTED}; background:transparent;"
        )
        glance_lay.addWidget(_today_hdr)

        self._glance_labels: dict[str, QLabel] = {}
        for key, label, color in [
            ("alerts",  "Alerts",      AMBER),
            ("devices", "New Devices", ACCENT),
            ("cves",    "CVEs",        RED),
            ("speed",   "Speed Tests", GREEN),
        ]:
            tile = QLabel(f"<b>—</b> {label}")
            tile.setStyleSheet(
                f"font-size:11px; color:{color}; background:transparent; border:none;"
            )
            glance_lay.addWidget(tile)
            self._glance_labels[key] = tile

        glance_lay.addStretch()
        outer.addWidget(self._glance)

        # ── Source filter chips ───────────────────────────────────────────────
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        chip_lbl = QLabel("Show:")
        chip_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_MUTED}; background:transparent;")
        chip_row.addWidget(chip_lbl)

        self._chip_btns: dict[str, QPushButton] = {}
        for src in (_SOURCE_DEVICE, _SOURCE_ALERTS, _SOURCE_CVE, _SOURCE_SPEED):
            btn = QPushButton(src)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedHeight(24)
            btn.setStyleSheet(self._chip_style(src, True))
            btn.toggled.connect(lambda checked, s=src: self._on_chip_toggled(s, checked))
            chip_row.addWidget(btn)
            self._chip_btns[src] = btn

        chip_row.addStretch()
        outer.addLayout(chip_row)

        # ── Scrollable event feed ─────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        self._feed_container = QWidget()
        self._feed_container.setStyleSheet("background:transparent;")
        self._feed_layout = QVBoxLayout(self._feed_container)
        self._feed_layout.setContentsMargins(0, 0, 0, 20)
        self._feed_layout.setSpacing(0)
        self._feed_layout.addStretch()

        scroll.setWidget(self._feed_container)
        outer.addWidget(scroll, 1)

        self._reload()

    # ── Data loading ──────────────────────────────────────────────────────────

    def _reload(self) -> None:
        self._events = self._fetch_events()
        self._render()
        self._update_glance()

    def _fetch_events(self) -> list[_Ev]:
        events: list[_Ev] = []

        # Device events
        if _SOURCE_DEVICE in self._active_sources:
            try:
                for e in self._store.query_device_events(hours=168):
                    verb = {"join": "joined", "leave": "left", "new": "first seen"}.get(
                        e.event_type, e.event_type
                    )
                    events.append(_Ev(
                        ts     = e.ts,
                        source = _SOURCE_DEVICE,
                        title  = f"Device {verb}: {e.ip or e.mac or '?'}",
                        detail = e.detail or "",
                        severity = "info" if e.event_type == "join" else "warn",
                    ))
            except Exception:
                pass

        # Alerts
        if _SOURCE_ALERTS in self._active_sources:
            try:
                for a in self._store.get_recent_alerts(hours=168, limit=500):
                    sev = str(a.get("severity", "info")).lower()
                    events.append(_Ev(
                        ts     = float(a.get("ts", 0)),
                        source = _SOURCE_ALERTS,
                        title  = f"{a.get('rule_name','Alert')}: {a.get('host','')}",
                        detail = a.get("message", ""),
                        severity = sev,
                    ))
            except Exception:
                pass

        # CVEs
        if _SOURCE_CVE in self._active_sources:
            try:
                for c in (self._store.list_cve_lifecycles() or []):
                    ts_val = c.get("discovered_ts") or c.get("ts") or 0
                    try:
                        ts_val = float(ts_val)
                    except Exception:
                        ts_val = 0.0
                    if ts_val == 0.0:
                        continue
                    events.append(_Ev(
                        ts     = ts_val,
                        source = _SOURCE_CVE,
                        title  = f"CVE {c.get('cve_id','?')}: {c.get('service','')}",
                        detail = f"Severity: {c.get('severity','?')}  Status: {c.get('status','?')}",
                        severity = "critical",
                    ))
            except Exception:
                pass

        # Speed tests
        if _SOURCE_SPEED in self._active_sources:
            try:
                for p in self._store.query_speed_test_history(hours=168, limit=50):
                    dl = f"{p.download_mbps:.1f}" if p.download_mbps else "?"
                    ul = f"{p.upload_mbps:.1f}"   if p.upload_mbps   else "?"
                    events.append(_Ev(
                        ts     = p.ts,
                        source = _SOURCE_SPEED,
                        title  = f"Speed test: ↓{dl} ↑{ul} Mbps",
                        detail = p.server_name or "",
                        severity = "info",
                    ))
            except Exception:
                pass

        events.sort(key=lambda e: e.ts, reverse=True)
        return events[:200]

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self) -> None:
        # Remove old items (keep the trailing stretch)
        while self._feed_layout.count() > 1:
            item = self._feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        visible = [e for e in self._events if e.source in self._active_sources]

        if not visible:
            empty = QLabel("No events in the last 7 days.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"font-size:12px; color:{TEXT_MUTED}; padding:40px; background:transparent;"
            )
            self._feed_layout.insertWidget(0, empty)
            return

        last_date = ""
        for i, ev in enumerate(visible):
            date_str = _date_label(ev.ts)
            if date_str != last_date:
                last_date = date_str
                date_hdr = QLabel(date_str.upper())
                date_hdr.setStyleSheet(
                    f"font-size:9px; font-weight:bold; color:{TEXT_MUTED};"
                    f" background:transparent; padding:12px 0 4px 0;"
                )
                self._feed_layout.insertWidget(i, date_hdr)

            row = self._make_event_row(ev)
            self._feed_layout.insertWidget(self._feed_layout.count() - 1, row)

    def _make_event_row(self, ev: _Ev) -> QFrame:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:none;"
            f" border-bottom:1px solid {BORDER}; }}"
            f"QFrame:hover {{ background:{BG_HOVER}; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(0)

        # Source colour bar
        bar = QFrame()
        bar.setFixedWidth(3)
        src_color = _SOURCE_COLORS.get(ev.source, TEXT_MUTED)
        bar.setStyleSheet(f"background:{src_color}; border:none;")
        lay.addWidget(bar)

        # Timestamp
        ts_lbl = QLabel(_fmt_ts(ev.ts))
        ts_lbl.setFixedWidth(80)
        ts_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ts_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; padding:0 8px;"
        )
        lay.addWidget(ts_lbl)

        # Source chip
        src_chip = QLabel(ev.source)
        src_chip.setFixedWidth(84)
        src_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        src_chip.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{src_color};"
            f" background:{src_color}18; border:1px solid {src_color}44;"
            f" border-radius:8px; padding:1px 6px; margin:4px 6px;"
        )
        lay.addWidget(src_chip)

        # Title + detail
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 6, 0, 6)
        text_col.setSpacing(1)
        title_lbl = QLabel(ev.title)
        title_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        text_col.addWidget(title_lbl)
        if ev.detail:
            detail_lbl = QLabel(ev.detail)
            detail_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_MUTED}; background:transparent;"
            )
            text_col.addWidget(detail_lbl)

        lay.addLayout(text_col, 1)
        return row

    # ── Today at a glance ─────────────────────────────────────────────────────

    def _update_glance(self) -> None:
        today_start = datetime.datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()

        today = [e for e in self._events if e.ts >= today_start]
        alerts  = sum(1 for e in today if e.source == _SOURCE_ALERTS)
        devices = sum(1 for e in today if e.source == _SOURCE_DEVICE)
        cves    = sum(1 for e in today if e.source == _SOURCE_CVE)
        speed   = sum(1 for e in today if e.source == _SOURCE_SPEED)

        self._glance_labels["alerts"].setText(f"<b>{alerts}</b> Alerts")
        self._glance_labels["devices"].setText(f"<b>{devices}</b> Device Events")
        self._glance_labels["cves"].setText(f"<b>{cves}</b> CVEs")
        self._glance_labels["speed"].setText(f"<b>{speed}</b> Speed Tests")

    # ── Chip interaction ──────────────────────────────────────────────────────

    def _on_chip_toggled(self, source: str, checked: bool) -> None:
        if checked:
            self._active_sources.add(source)
        else:
            self._active_sources.discard(source)
        self._chip_btns[source].setStyleSheet(self._chip_style(source, checked))
        self._render()
        self._update_glance()

    def _chip_style(self, source: str, active: bool) -> str:
        color = _SOURCE_COLORS.get(source, TEXT_MUTED)
        if active:
            return (
                f"QPushButton {{ font-size:10px; font-weight:bold; color:{color};"
                f" background:{color}18; border:1px solid {color}; border-radius:10px;"
                f" padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{color}30; }}"
            )
        return (
            f"QPushButton {{ font-size:10px; color:{TEXT_MUTED};"
            f" background:transparent; border:1px solid {BORDER}; border-radius:10px;"
            f" padding:1px 10px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
        )

    # ── showEvent ─────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload()
