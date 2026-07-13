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
from typing import TYPE_CHECKING

from PyQt6.QtCore    import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ui.widgets.empty_state_card import EmptyStateCard
from ui import styles as _s


_SOURCE_PAGE_MAP = {
    "Devices":          "Devices",
    "Alerts":           "Notifications",
    "CVEs":             "CVE Tracker",
    "Speed Tests":      "Speed Test",
    "Device Changes":   "Devices",
    "Network Logger":   "Network Logger",
}

if TYPE_CHECKING:
    from modules.metric_store import MetricStore


# ── Source tags ────────────────────────────────────────────────────────────────

_SOURCE_DEVICE  = "Devices"
_SOURCE_ALERTS  = "Alerts"
_SOURCE_CVE     = "CVEs"
_SOURCE_SPEED   = "Speed Tests"
_SOURCE_CHANGES = "Device Changes"
_SOURCE_LOGGER  = "Network Logger"

# Token NAME strings (resolved live via getattr(_s, name)) — a bare-token dict
# would freeze at import and never follow a theme switch.
_SOURCE_COLORS = {
    _SOURCE_DEVICE:  "ACCENT",
    _SOURCE_ALERTS:  "AMBER",
    _SOURCE_CVE:     "RED",
    _SOURCE_SPEED:   "GREEN",
    _SOURCE_CHANGES: "TEXT_MUTED",
    _SOURCE_LOGGER:  "RED",
}


def _source_color(source: str) -> str:
    """Live theme colour for a timeline source tag."""
    return getattr(_s, _SOURCE_COLORS.get(source, "TEXT_MUTED"))


def _chip_style(source: str, active: bool) -> str:
    """Live QSS for a source filter chip (state-dependent, theme-live)."""
    if active:
        color = _source_color(source)
        return (
            f"QPushButton {{ font-size:10px; font-weight:bold; color:{color};"
            f" background:{color}18; border:1px solid {color}; border-radius:10px;"
            f" padding:1px 10px; }}"
            f"QPushButton:hover {{ background:{color}30; }}"
        )
    return (
        f"QPushButton {{ font-size:10px; color:{_s.TEXT_MUTED};"
        f" background:transparent; border:1px solid {_s.BORDER}; border-radius:10px;"
        f" padding:1px 10px; }}"
        f"QPushButton:hover {{ background:{_s.BG_HOVER}; }}"
    )


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
    navigate_to    = pyqtSignal(str)
    scan_requested = pyqtSignal()

    def __init__(self, store: "MetricStore", parent=None):
        super().__init__(parent)
        self._store   = store
        self._active_sources: set[str] = {
            _SOURCE_DEVICE, _SOURCE_ALERTS, _SOURCE_CVE, _SOURCE_SPEED,
            _SOURCE_CHANGES, _SOURCE_LOGGER,
        }
        self._events: list[_Ev] = []
        self._label_map: dict[str, str] = {}
        self._tl_search_timer = QTimer(self)
        self._tl_search_timer.setSingleShot(True)
        self._tl_search_timer.setInterval(200)
        self._tl_search_timer.timeout.connect(self._render)
        self._setup_ui()

        # Auto-refresh every 60 s
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self._reload)
        self._timer.start()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("TimelinePage")
        _s.themed_ss(self, "QWidget#TimelinePage {{ background:{BG_DARK}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 0)
        outer.setSpacing(10)

        # Title
        from ui.widgets.page_header import PageHeaderBar
        _hdr = PageHeaderBar("Network Timeline", subtitle="A chronological log of all network events across all monitoring sources.")
        _hdr.show_first_visit_banner(
            "network_timeline",
            "Every device join/leave, alert, and CVE discovery lands here in one "
            "reverse-chronological feed — useful for reconstructing what happened around a "
            "specific time.",
        )
        outer.addWidget(_hdr)

        # ── TIMELINE-2: Today at a glance ─────────────────────────────────────
        self._glance = QFrame()
        _s.themed_ss(self._glance, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:4px; }}")
        glance_lay = QHBoxLayout(self._glance)
        glance_lay.setContentsMargins(14, 8, 14, 8)
        glance_lay.setSpacing(20)

        _today_hdr = QLabel("TODAY AT A GLANCE")
        _s.themed_ss(_today_hdr, "font-size:9px; font-weight:bold; color:{TEXT_MUTED}; background:transparent;")
        glance_lay.addWidget(_today_hdr)

        self._glance_labels: dict[str, QLabel] = {}
        for key, label, cname in [
            ("alerts",   "Alerts",          "AMBER"),
            ("devices",  "Device Events",   "ACCENT"),
            ("cves",     "CVEs",            "RED"),
            ("speed",    "Speed Tests",     "GREEN"),
            ("changes",  "Device Changes",  "TEXT_MUTED"),
            ("outages",  "Log Outages",     "RED"),
        ]:
            tile = QLabel(f"<b>—</b> {label}")
            _s.themed_ss(tile, lambda c=cname: (
                f"font-size:11px; color:{getattr(_s, c)}; background:transparent; border:none;"
            ))
            glance_lay.addWidget(tile)
            self._glance_labels[key] = tile

        glance_lay.addStretch()
        outer.addWidget(self._glance)

        # ── Source filter chips ───────────────────────────────────────────────
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        chip_lbl = QLabel("Show:")
        _s.themed_ss(chip_lbl, "font-size:11px; color:{TEXT_MUTED}; background:transparent;")
        chip_row.addWidget(chip_lbl)

        self._chip_btns: dict[str, QPushButton] = {}
        for src in (_SOURCE_DEVICE, _SOURCE_ALERTS, _SOURCE_CVE, _SOURCE_SPEED,
                    _SOURCE_CHANGES, _SOURCE_LOGGER):
            btn = QPushButton(src)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedHeight(24)
            _s.themed_ss(btn, lambda s=src: _chip_style(s, True))
            btn.toggled.connect(lambda checked, s=src: self._on_chip_toggled(s, checked))
            chip_row.addWidget(btn)
            self._chip_btns[src] = btn

        chip_row.addStretch()

        self._tl_search = QLineEdit()
        self._tl_search.setPlaceholderText("Search events…")
        self._tl_search.setFixedHeight(24)
        self._tl_search.setFixedWidth(180)
        _s.themed_ss(self._tl_search, "QLineEdit {{ border:1px solid {BORDER}; border-radius:3px; padding:0 6px;"
            " font-size:10px; color:{TEXT_PRIMARY}; background:{WHITE}; }}"
            "QLineEdit:focus {{ border-color:{ACCENT}; }}")
        self._tl_search.textChanged.connect(lambda: self._tl_search_timer.start())
        chip_row.addWidget(self._tl_search)

        self._tl_match_lbl = QLabel("")
        _s.themed_ss(self._tl_match_lbl, "font-size:10px; color:{TEXT_MUTED}; background:transparent;")
        chip_row.addWidget(self._tl_match_lbl)

        outer.addLayout(chip_row)

        # ── Content stack: page 0 = empty state, page 1 = event feed ────────────
        self._feed_stack = QStackedWidget()

        # Page 0 — empty state
        _empty = EmptyStateCard(
            icon="≡",
            title="No events yet",
            what_it_shows=(
                "A reverse-chronological log of device joins/leaves, fired alerts, "
                "CVE discoveries, and speed test completions — all in one place."
            ),
            why_it_matters=(
                "The timeline is your audit trail — run a scan to populate it "
                "and leave the logger on to capture events as they happen."
            ),
            btn_label="Run a scan →",
        )
        _empty.clicked.connect(self.scan_requested.emit)
        self._feed_stack.addWidget(_empty)

        # Page 1 — scrollable event feed
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
        self._feed_stack.addWidget(scroll)

        outer.addWidget(self._feed_stack, 1)

        self._reload()

    # ── External label map (from scan result) ───────────────────────────────

    def set_label_map(self, label_map: dict) -> None:
        """Pass MAC→display-name mapping from latest scan result."""
        self._label_map = dict(label_map)
        self._reload()

    # ── Data loading ──────────────────────────────────────────────────────────

    def _reload(self) -> None:
        self._events = self._fetch_events()
        if self._events:
            self._feed_stack.setCurrentIndex(1)
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
                pass  # non-fatal

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
                pass  # non-fatal

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
                pass  # non-fatal

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
                pass  # non-fatal

        # Device change audit events
        if _SOURCE_CHANGES in self._active_sources:
            try:
                from modules.device_tracker import get_all_device_events as _get_dev_ev
                _CHANGE_LABELS = {
                    "ip_changed":        "IP changed",
                    "hostname_changed":  "Hostname changed",
                    "class_changed":     "Type identified",
                    "vendor_changed":    "Vendor resolved",
                    "first_seen":        "First seen",
                    "went_offline":      "Went offline",
                    "came_online":       "Came online",
                    "annotation_changed": "Annotation updated",
                }
                for ev in _get_dev_ev(self._store, limit=500, hours=168):
                    _ts_str = ev.get("ts", "")
                    try:
                        _ts = datetime.datetime.strptime(str(_ts_str), "%Y-%m-%d %H:%M:%S").timestamp()
                    except Exception:
                        continue
                    _etype = ev.get("event_type", "")
                    _label = _CHANGE_LABELS.get(_etype, _etype)
                    _mac   = ev.get("mac", "?")
                    _old   = ev.get("old_value", "")
                    _new   = ev.get("new_value", "")
                    _src   = ev.get("source", "")
                    _detail = (f"{_old} → {_new}" if _old and _new else (_new or _src))
                    _name  = self._label_map.get(_mac.lower(), _mac[:17]) if _mac != "?" else _mac
                    events.append(_Ev(
                        ts     = _ts,
                        source = _SOURCE_CHANGES,
                        title  = f"{_label}: {_name}",
                        detail = _detail,
                        severity = "info",
                    ))
            except Exception:
                pass  # non-fatal

        # Network Logger outages
        if _SOURCE_LOGGER in self._active_sources:
            try:
                from modules.network_log_writer import list_log_files, load_log_file
                _cutoff = datetime.datetime.now().timestamp() - 7 * 86400
                for _lf in list_log_files()[:14]:  # at most ~2 weeks of files
                    try:
                        _summary = load_log_file(_lf)
                        for _o in _summary.outages:
                            try:
                                _ts = datetime.datetime.strptime(
                                    str(_o.start), "%Y-%m-%d %H:%M:%S"
                                ).timestamp()
                            except Exception:
                                continue
                            if _ts < _cutoff:
                                continue
                            _dur = int(_o.duration_s)
                            _dur_str = (f"{_dur // 60}m {_dur % 60}s" if _dur >= 60
                                        else f"{_dur}s")
                            events.append(_Ev(
                                ts       = _ts,
                                source   = _SOURCE_LOGGER,
                                title    = f"Outage: {_o.host} — {_dur_str}",
                                detail   = (
                                    f"{_o.consecutive_fails} consecutive failures"
                                    + (f", peak {_o.peak_latency_ms:.0f} ms"
                                       if _o.peak_latency_ms > 0 else "")
                                ),
                                severity = "critical",
                            ))
                    except Exception:
                        pass  # skip unreadable log files
            except Exception:
                pass  # non-fatal — log dir may not exist yet

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

        q = self._tl_search.text().strip().lower() if hasattr(self, "_tl_search") else ""
        if q:
            visible = [
                e for e in visible
                if q in e.title.lower() or q in e.detail.lower()
            ]
            total = sum(1 for e in self._events if e.source in self._active_sources)
            self._tl_match_lbl.setText(f"{len(visible)} / {total}")
        else:
            if hasattr(self, "_tl_match_lbl"):
                self._tl_match_lbl.setText("")

        if not visible:
            msg = "No events match your search." if q else "No events in the last 7 days."
            empty = QLabel(msg)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _s.themed_ss(empty, "font-size:12px; color:{TEXT_MUTED}; padding:40px; background:transparent;")
            self._feed_layout.insertWidget(0, empty)
            return

        last_date = ""
        for i, ev in enumerate(visible):
            date_str = _date_label(ev.ts)
            if date_str != last_date:
                last_date = date_str
                date_hdr = QLabel(date_str.upper())
                _s.themed_ss(date_hdr, "font-size:9px; font-weight:bold; color:{TEXT_MUTED};"
                    " background:transparent; padding:12px 0 4px 0;")
                self._feed_layout.insertWidget(i, date_hdr)

            row = self._make_event_row(ev)
            self._feed_layout.insertWidget(self._feed_layout.count() - 1, row)

    def _make_event_row(self, ev: _Ev) -> QFrame:
        dest = _SOURCE_PAGE_MAP.get(ev.source, "")
        row = QFrame()
        _s.themed_ss(row, "QFrame {{ background:{BG_CARD}; border:none;"
            " border-bottom:1px solid {BORDER}; }}"
            "QFrame:hover {{ background:{BG_HOVER}; }}")
        if dest:
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.mousePressEvent = lambda _ev, d=dest: self.navigate_to.emit(d)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(0)

        # Source colour bar
        bar = QFrame()
        bar.setFixedWidth(3)
        src_color = _source_color(ev.source)
        bar.setStyleSheet(f"background:{src_color}; border:none;")
        lay.addWidget(bar)

        # Timestamp
        ts_lbl = QLabel(_fmt_ts(ev.ts))
        ts_lbl.setFixedWidth(80)
        ts_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        _s.themed_ss(ts_lbl, "font-size:10px; color:{TEXT_MUTED}; background:transparent; padding:0 8px;")
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
        _s.themed_ss(title_lbl, "font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
        text_col.addWidget(title_lbl)
        if ev.detail:
            detail_lbl = QLabel(ev.detail)
            _s.themed_ss(detail_lbl, "font-size:10px; color:{TEXT_MUTED}; background:transparent;")
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
        changes = sum(1 for e in today if e.source == _SOURCE_CHANGES)
        outages = sum(1 for e in today if e.source == _SOURCE_LOGGER)

        self._glance_labels["alerts"].setText(f"<b>{alerts}</b> Alerts")
        self._glance_labels["devices"].setText(f"<b>{devices}</b> Device Events")
        self._glance_labels["cves"].setText(f"<b>{cves}</b> CVEs")
        self._glance_labels["speed"].setText(f"<b>{speed}</b> Speed Tests")
        self._glance_labels["changes"].setText(f"<b>{changes}</b> Device Changes")
        self._glance_labels["outages"].setText(f"<b>{outages}</b> Log Outages")

    # ── Chip interaction ──────────────────────────────────────────────────────

    def _on_chip_toggled(self, source: str, checked: bool) -> None:
        if checked:
            self._active_sources.add(source)
        else:
            self._active_sources.discard(source)
        _s.themed_ss(self._chip_btns[source],
                     lambda s=source, a=checked: _chip_style(s, a))
        self._render()
        self._update_glance()

    # ── Theme ─────────────────────────────────────────────────────────────────

    def refresh_theme(self) -> None:
        """Rebuild the transient event feed so per-row colours follow the theme.

        Persistent chrome (chips, glance tiles, headers) re-styles itself via
        themed_ss; the event rows are rebuilt on each _render(), so re-render.
        """
        self._render()

    # ── showEvent ─────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload()
