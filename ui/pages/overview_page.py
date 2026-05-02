"""
Overview Page — configurable live dashboard (Backlog #1).

Users arrange a set of live data tiles in a 3-column grid.
Tiles auto-refresh from MetricStore and worker signals.
Drag-and-drop reordering is available in "Edit Layout" mode.
Tile order is persisted in QSettings under "overview/tile_order".

Tile types
----------
device_count    — devices found in the last availability cycle
fleet_uptime    — average 24 h uptime % across all monitored hosts
service_status  — TCP service heartbeat summary (up / down)
tls_status      — TLS certificate health (OK / expiring / expired)
rtt_summary     — average RTT and packet-loss from the last cycle
network_grade   — letter grade from the last benchmark run
alert_feed      — last 5 fired alerts
event_feed      — last 5 device-state events from MetricStore

Architecture rules observed:
  • Light content area, white cards — no dark backgrounds (design system)
  • No blocking I/O on main thread (RULE 4)
  • parent=grid_container for all tile construction (RULE 17)
  • Tile parent widget kept in named local var, never via .parent() (RULE 18)
  • All colours imported from ui.styles (RULE 1)
"""

from __future__ import annotations

import datetime
from typing import Callable, Dict, List, Optional

from PyQt6.QtCore    import QMimeData, QPoint, QSettings, QSize, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui     import QColor, QCursor, QDrag, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from modules.metric_store import MetricStore
from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BG_HOVER, BORDER,
    GREEN, RED, TEXT_PRIMARY, TEXT_SECONDARY,
)

_MIME_TYPE    = "application/x-netsentinel-tile"
_COLS         = 3
_SETTINGS_KEY = "overview/tile_order"


# ── Animated count label ──────────────────────────────────────────────────────

class _AnimatedNumberLabel(QLabel):
    """QLabel that count-up animates when its numeric value changes."""

    def __init__(self, text: str = "–", fmt: str = "{}", parent=None):
        super().__init__(text, parent)
        self._target: float  = 0.0
        self._current: float = 0.0
        self._fmt = fmt
        self._timer = QTimer(self)
        self._timer.setInterval(20)  # ~50 fps
        self._timer.timeout.connect(self._step)

    def animate_to(self, value: float) -> None:
        self._target = float(value)
        if not self._timer.isActive():
            self._timer.start()

    def _step(self) -> None:
        diff = self._target - self._current
        if abs(diff) < 0.5:
            self._current = self._target
            self.setText(self._fmt.format(int(round(self._current))))
            self._timer.stop()
        else:
            self._current += diff * 0.25  # ease-out
            self.setText(self._fmt.format(int(round(self._current))))


# ── Base tile ─────────────────────────────────────────────────────────────────

class _BaseTile(QFrame):
    """
    Base class for all overview tiles.

    Subclasses must define:
      TILE_ID    : str   — unique key used for persistence
      TILE_LABEL : str   — displayed in the title bar

    And optionally override:
      _build_body() — populate self._body_layout with content widgets
      refresh(store) — pull fresh data from MetricStore
    """

    TILE_ID    = "base"
    TILE_LABEL = "Tile"
    MIN_HEIGHT = 140

    def __init__(
        self,
        store: Optional[MetricStore] = None,
        swap_cb: Optional[Callable[[str, str], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._store    = store
        self._swap_cb  = swap_cb or (lambda a, b: None)
        self._edit_mode  = False
        self._drag_start: Optional[QPoint] = None

        self.setObjectName("overviewTile")
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAcceptDrops(True)
        self._setup_frame()
        self._build_body()

    # ── Frame ─────────────────────────────────────────────────────────────────

    def _setup_frame(self) -> None:
        self.setStyleSheet(
            f"QFrame#overviewTile {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
            f"QFrame#overviewTile:hover {{ border-color:{ACCENT}; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet(
            f"QWidget {{ background:{BG_CARD}; border-bottom:1px solid #ECECEC; }}"
        )
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(10, 0, 8, 0)
        tb.setSpacing(4)

        self._title_lbl = QLabel(self.TILE_LABEL)
        self._title_lbl.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" border:none; background:transparent;"
        )
        tb.addWidget(self._title_lbl, 1)

        self._drag_handle = QLabel("⠿")
        self._drag_handle.setFixedSize(18, 18)
        self._drag_handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drag_handle.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:14px; border:none; background:transparent;"
        )
        self._drag_handle.setToolTip("Drag to reorder")
        self._drag_handle.hide()
        tb.addWidget(self._drag_handle)

        outer.addWidget(title_bar)

        # Body
        body = QWidget()
        body.setStyleSheet("background:transparent; border:none;")
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(12, 8, 12, 10)
        self._body_layout.setSpacing(4)
        outer.addWidget(body, 1)

        # Health bar — 3 px coloured bottom strip reflecting tile status
        self._health_bar = QFrame()
        self._health_bar.setFixedHeight(3)
        self._health_bar.setStyleSheet(f"background:{BORDER}; border:none;")
        outer.addWidget(self._health_bar)

    def _build_body(self) -> None:
        pass

    def refresh(self, store: Optional[MetricStore] = None) -> None:
        pass

    def set_edit_mode(self, enabled: bool) -> None:
        self._edit_mode = enabled
        self._drag_handle.setVisible(enabled)
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor if enabled
                               else Qt.CursorShape.ArrowCursor))

    # ── Drag ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._edit_mode and self._drag_start is not None
                and (event.pos() - self._drag_start).manhattanLength() > 8):
            self._begin_drag()
        super().mouseMoveEvent(event)

    def _begin_drag(self) -> None:
        self._drag_start = None
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_MIME_TYPE, self.TILE_ID.encode())
        drag.setMimeData(mime)

        px = QPixmap(self.size())
        px.fill(QColor(0, 0, 0, 0))
        painter = QPainter(px)
        painter.setOpacity(0.65)
        self.render(painter)
        painter.end()
        drag.setPixmap(px)
        drag.setHotSpot(self.rect().center())
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_MIME_TYPE):
            event.acceptProposedAction()
            self.setStyleSheet(
                f"QFrame#overviewTile {{ background:{BG_HOVER};"
                f" border:2px solid {ACCENT}; }}"
            )

    def dragLeaveEvent(self, event):
        self._reset_style()

    def dropEvent(self, event):
        self._reset_style()
        if event.mimeData().hasFormat(_MIME_TYPE):
            src_id = event.mimeData().data(_MIME_TYPE).data().decode()
            self._swap_cb(src_id, self.TILE_ID)
            event.acceptProposedAction()

    def _reset_style(self) -> None:
        self.setStyleSheet(
            f"QFrame#overviewTile {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
            f"QFrame#overviewTile:hover {{ border-color:{ACCENT}; }}"
        )

    def _set_health(self, color: str) -> None:
        self._health_bar.setStyleSheet(f"background:{color}; border:none;")


# ── Concrete tiles ────────────────────────────────────────────────────────────

class DeviceCountTile(_BaseTile):
    TILE_ID    = "device_count"
    TILE_LABEL = "Devices on Network"

    def _build_body(self) -> None:
        self._count_lbl = _AnimatedNumberLabel("–", parent=self)
        self._count_lbl.setStyleSheet(
            f"font-size:38px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;"
        )
        self._sub_lbl = QLabel("Waiting for scan…")
        self._sub_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
        )
        self._body_layout.addWidget(self._count_lbl)
        self._body_layout.addWidget(self._sub_lbl)
        self._body_layout.addStretch()

    def update_cycle(self, states: dict) -> None:
        total = len(states)
        up    = sum(1 for s in states.values() if s == "UP")
        down  = sum(1 for s in states.values() if s == "DOWN")
        self._count_lbl.animate_to(total)
        parts = []
        if up:   parts.append(f"{up} up")
        if down: parts.append(f"{down} ↓ down")
        self._sub_lbl.setText("  ·  ".join(parts) if parts else "No devices monitored")
        colour = RED if down else (AMBER if total == 0 else GREEN)
        self._set_health(colour)


class FleetUptimeTile(_BaseTile):
    TILE_ID    = "fleet_uptime"
    TILE_LABEL = "Fleet Uptime (24 h)"

    def _build_body(self) -> None:
        self._pct_lbl = QLabel("–", parent=self)
        self._pct_lbl.setStyleSheet(
            f"font-size:38px; font-weight:bold; color:{GREEN}; border:none;"
        )
        self._sub_lbl = QLabel("No data yet")
        self._sub_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
        )
        self._body_layout.addWidget(self._pct_lbl)
        self._body_layout.addWidget(self._sub_lbl)
        self._body_layout.addStretch()

    def refresh(self, store: Optional[MetricStore] = None) -> None:
        s = store or self._store
        if s is None:
            return
        try:
            rows = s.query_uptime_table()
            if not rows:
                return
            avgs = [r.get("24.0", 100.0) for r in rows]
            avg  = sum(avgs) / len(avgs)
            colour = GREEN if avg >= 95 else AMBER if avg >= 80 else RED
            self._pct_lbl.setText(f"{avg:.1f}%")
            self._pct_lbl.setStyleSheet(
                f"font-size:38px; font-weight:bold; color:{colour}; border:none;"
            )
            n = len(rows)
            self._sub_lbl.setText(f"across {n} monitored host{'s' if n != 1 else ''}")
            self._set_health(colour)
        except Exception:
            pass


class ServiceStatusTile(_BaseTile):
    TILE_ID    = "service_status"
    TILE_LABEL = "Service Heartbeat"

    def _build_body(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)

        up_col = QVBoxLayout()
        self._up_lbl = _AnimatedNumberLabel("–", parent=self)
        self._up_lbl.setStyleSheet(
            f"font-size:30px; font-weight:bold; color:{GREEN}; border:none;"
        )
        up_sub = QLabel("UP")
        up_sub.setStyleSheet(
            f"font-size:10px; font-weight:bold; color:{GREEN}; border:none;"
        )
        up_col.addWidget(self._up_lbl)
        up_col.addWidget(up_sub)

        dn_col = QVBoxLayout()
        self._dn_lbl = _AnimatedNumberLabel("–", parent=self)
        self._dn_lbl.setStyleSheet(
            f"font-size:30px; font-weight:bold; color:{RED}; border:none;"
        )
        dn_sub = QLabel("DOWN")
        dn_sub.setStyleSheet(
            f"font-size:10px; font-weight:bold; color:{RED}; border:none;"
        )
        dn_col.addWidget(self._dn_lbl)
        dn_col.addWidget(dn_sub)

        row.addLayout(up_col)
        row.addLayout(dn_col)
        row.addStretch()
        self._body_layout.addLayout(row)
        self._body_layout.addStretch()

    def update_services(self, results: list) -> None:
        up = sum(1 for r in results if
                 (r.get("up") if isinstance(r, dict) else getattr(r, "up", False)))
        dn = len(results) - up
        self._up_lbl.animate_to(up)
        self._dn_lbl.animate_to(dn)
        self._set_health(RED if dn > 0 else GREEN)


class TlsStatusTile(_BaseTile):
    TILE_ID    = "tls_status"
    TILE_LABEL = "TLS Certificates"

    def _build_body(self) -> None:
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        self._ok_lbl       = QLabel("–")
        self._expiring_lbl = QLabel("–")
        self._expired_lbl  = QLabel("–")

        def _row(num_lbl, colour, text, row_idx):
            num_lbl.setStyleSheet(
                f"font-size:22px; font-weight:bold; color:{colour}; border:none;"
            )
            sub = QLabel(text)
            sub.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY}; border:none;"
            )
            grid.addWidget(num_lbl, row_idx, 0)
            grid.addWidget(sub,     row_idx, 1)

        _row(self._ok_lbl,       GREEN, "OK",            0)
        _row(self._expiring_lbl, AMBER, "Expiring soon", 1)
        _row(self._expired_lbl,  RED,   "Expired",       2)
        self._body_layout.addLayout(grid)
        self._body_layout.addStretch()

    def refresh(self, store: Optional[MetricStore] = None) -> None:
        s = store or self._store
        if s is None:
            return
        try:
            rows = s.query_cert_status(hours=168)
            ok = expiring = expired = 0
            for r in rows:
                is_exp = r.is_expired if hasattr(r, "is_expired") else r.get("is_expired", False)
                days   = r.days_remaining if hasattr(r, "days_remaining") else r.get("days_remaining")
                if is_exp:
                    expired += 1
                elif days is not None and days < 30:
                    expiring += 1
                else:
                    ok += 1
            self._ok_lbl.setText(str(ok))
            self._expiring_lbl.setText(str(expiring))
            self._expired_lbl.setText(str(expired))
        except Exception:
            pass


class RttSummaryTile(_BaseTile):
    TILE_ID    = "rtt_summary"
    TILE_LABEL = "Network Latency"

    def _build_body(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)

        rtt_col = QVBoxLayout()
        self._rtt_lbl = QLabel("–")
        self._rtt_lbl.setStyleSheet(
            f"font-size:30px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;"
        )
        rtt_sub = QLabel("Avg RTT")
        rtt_sub.setStyleSheet(f"font-size:10px; color:{TEXT_SECONDARY}; border:none;")
        rtt_col.addWidget(self._rtt_lbl)
        rtt_col.addWidget(rtt_sub)

        loss_col = QVBoxLayout()
        self._loss_lbl = QLabel("–")
        self._loss_lbl.setStyleSheet(
            f"font-size:30px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;"
        )
        loss_sub = QLabel("Packet loss")
        loss_sub.setStyleSheet(f"font-size:10px; color:{TEXT_SECONDARY}; border:none;")
        loss_col.addWidget(self._loss_lbl)
        loss_col.addWidget(loss_sub)

        row.addLayout(rtt_col)
        row.addLayout(loss_col)
        row.addStretch()
        self._body_layout.addLayout(row)
        self._body_layout.addStretch()

    def update_cycle(self, rtts: dict) -> None:
        valid = [v for v in rtts.values() if v is not None and v >= 0]
        total = len(rtts)
        lost  = sum(1 for v in rtts.values() if v is None or v < 0)
        if valid:
            avg    = sum(valid) / len(valid)
            colour = GREEN if avg < 50 else AMBER if avg < 150 else RED
            self._rtt_lbl.setText(f"{avg:.0f} ms")
            self._rtt_lbl.setStyleSheet(
                f"font-size:30px; font-weight:bold; color:{colour}; border:none;"
            )
        else:
            self._rtt_lbl.setText("–")
        if total:
            pct    = (lost / total) * 100
            colour = GREEN if pct == 0 else AMBER if pct < 10 else RED
            self._loss_lbl.setText(f"{pct:.0f}%")
            self._loss_lbl.setStyleSheet(
                f"font-size:30px; font-weight:bold; color:{colour}; border:none;"
            )


class NetworkGradeTile(_BaseTile):
    TILE_ID    = "network_grade"
    TILE_LABEL = "Network Grade"
    _GRADE_COLOUR = {
        "A": GREEN, "B": GREEN, "C": AMBER, "D": RED, "F": RED,
    }

    def _build_body(self) -> None:
        self._grade_lbl = QLabel("–")
        self._grade_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grade_lbl.setStyleSheet(
            f"font-size:56px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;"
        )
        self._sub_lbl = QLabel("Run Network Grade for a score")
        self._sub_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; border:none;"
        )
        self._sub_lbl.setWordWrap(True)
        self._body_layout.addWidget(
            self._grade_lbl, alignment=Qt.AlignmentFlag.AlignCenter
        )
        self._body_layout.addWidget(
            self._sub_lbl, alignment=Qt.AlignmentFlag.AlignCenter
        )
        self._body_layout.addStretch()

    def update_grade(self, grade: str, score: float = 0.0) -> None:
        letter = grade[:1].upper() if grade else "–"
        colour = self._GRADE_COLOUR.get(letter, TEXT_SECONDARY)
        self._grade_lbl.setText(letter)
        self._grade_lbl.setStyleSheet(
            f"font-size:56px; font-weight:bold; color:{colour}; border:none;"
        )
        self._sub_lbl.setText(f"Score: {score:.0f} / 100" if score else "")


class AlertFeedTile(_BaseTile):
    TILE_ID    = "alert_feed"
    TILE_LABEL = "Recent Alerts"
    MIN_HEIGHT = 165
    _SEV_COLOUR = {"CRITICAL": RED, "WARNING": AMBER, "INFO": ACCENT}

    def _build_body(self) -> None:
        self._row_widgets: list[tuple[QLabel, QLabel]] = []
        for _ in range(5):
            dot = QLabel("●")
            dot.setFixedWidth(14)
            dot.setStyleSheet(
                f"font-size:9px; color:{TEXT_SECONDARY}; border:none;"
            )
            msg = QLabel("–")
            msg.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
            )
            row = QHBoxLayout()
            row.setSpacing(4)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(dot)
            row.addWidget(msg, 1)
            self._body_layout.addLayout(row)
            self._row_widgets.append((dot, msg))
        self._body_layout.addStretch()
        self._alerts: list[dict] = []

    def push_alert(self, alert) -> None:
        if isinstance(alert, dict):
            d = alert
        else:
            d = {
                "severity": alert.severity,
                "message":  alert.message,
                "ts":       alert.ts,
            }
        self._alerts.insert(0, d)
        self._alerts = self._alerts[:5]
        self._redraw()

    def _redraw(self) -> None:
        for i, (dot, msg) in enumerate(self._row_widgets):
            if i < len(self._alerts):
                a      = self._alerts[i]
                colour = self._SEV_COLOUR.get(a.get("severity", "INFO"), TEXT_SECONDARY)
                text   = a.get("message", "")
                dot.setStyleSheet(f"font-size:9px; color:{colour}; border:none;")
                msg.setText(text[:58] + "…" if len(text) > 58 else text)
                msg.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; border:none;")
            else:
                dot.setStyleSheet(
                    f"font-size:9px; color:{TEXT_SECONDARY}; border:none;"
                )
                msg.setText("–")
                msg.setStyleSheet(
                    f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
                )


class EventFeedTile(_BaseTile):
    TILE_ID    = "event_feed"
    TILE_LABEL = "Device Events"
    MIN_HEIGHT = 165

    def _build_body(self) -> None:
        self._rows: list[QLabel] = []
        for _ in range(5):
            lbl = QLabel("–")
            lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
            )
            self._body_layout.addWidget(lbl)
            self._rows.append(lbl)
        self._body_layout.addStretch()

    def refresh(self, store: Optional[MetricStore] = None) -> None:
        s = store or self._store
        if s is None:
            return
        try:
            events = s.query_device_events(24.0)
            for i, lbl in enumerate(self._rows):
                if i < len(events):
                    e       = events[i]
                    ip      = e.ip if hasattr(e, "ip") else e.get("ip", "")
                    etype   = e.event_type if hasattr(e, "event_type") else e.get("event_type", "")
                    ts      = e.ts if hasattr(e, "ts") else e.get("ts", 0)
                    t_str   = (datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
                               if ts else "")
                    colour  = (GREEN if etype == "APPEARED"
                               else RED if etype == "DISAPPEARED"
                               else ACCENT)
                    lbl.setStyleSheet(
                        f"font-size:11px; color:{colour}; border:none;"
                    )
                    lbl.setText(f"{t_str}  {ip}  {etype.lower()}")
                else:
                    lbl.setText("–")
                    lbl.setStyleSheet(
                        f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
                    )
        except Exception:
            pass


class HaDevicesTile(_BaseTile):
    """Shows pinned Home Automation devices with live status dots."""

    TILE_ID    = "ha_devices"
    TILE_LABEL = "Home Automation"
    MIN_HEIGHT = 160

    def _build_body(self) -> None:
        self._rows: List[QLabel] = []
        self._placeholder = QLabel("No pinned HA devices yet")
        self._placeholder.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
        )
        self._body_layout.addWidget(self._placeholder)
        self._body_layout.addStretch()

    def refresh(self, store: Optional[MetricStore] = None) -> None:
        s = store or self._store
        if s is None:
            return
        try:
            pinned = s.query_ha_devices()
            pinned = [d for d in pinned if d.is_pinned]

            # Clear previous rows
            for lbl in self._rows:
                self._body_layout.removeWidget(lbl)
                lbl.deleteLater()
            self._rows.clear()

            self._placeholder.setVisible(len(pinned) == 0)

            for kd in pinned[:8]:   # cap at 8 in overview tile
                name  = kd.custom_name or kd.hostname or kd.mac
                label = QLabel(f"● {name[:28]}")
                label.setStyleSheet(
                    f"font-size:11px; color:{TEXT_PRIMARY}; border:none;"
                )
                label.setToolTip(
                    f"IP: {kd.ip or '?'}  |  "
                    f"Room: {kd.room or '?'}  |  "
                    f"MAC: {kd.mac}"
                )
                self._rows.append(label)
                # Insert before stretch (last item)
                self._body_layout.insertWidget(
                    self._body_layout.count() - 1, label
                )
        except Exception:
            pass

    def update_ha_states(self, states: dict) -> None:
        """states: {ip: UP/DOWN/DEGRADED/UNKNOWN} — called from dashboard."""
        from ui.styles import GREEN, RED, AMBER, TEXT_MUTED
        _colors = {"UP": GREEN, "DOWN": RED, "DEGRADED": AMBER, "UNKNOWN": TEXT_MUTED}
        # We refresh on next store poll; live update done through normal refresh cycle


class LiveBandwidthTile(_BaseTile):
    """Shows current aggregate upload/download Mbps, updated every second."""

    TILE_ID    = "live_bandwidth"
    TILE_LABEL = "Live Bandwidth"
    MIN_HEIGHT = 120

    def _build_body(self) -> None:
        self._worker = None

        row = QHBoxLayout()
        row.setSpacing(16)

        # Upload
        up_col = QVBoxLayout()
        up_col.setSpacing(2)
        up_lbl = QLabel("↑ UPLOAD")
        up_lbl.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;"
        )
        self._up_val = QLabel("—")
        self._up_val.setStyleSheet(
            f"font-size:20px; font-weight:bold; color:#4CAF50; border:none;"
        )
        self._up_unit = QLabel("Mbps")
        self._up_unit.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; border:none;"
        )
        up_col.addWidget(up_lbl)
        up_col.addWidget(self._up_val)
        up_col.addWidget(self._up_unit)

        # Download
        dn_col = QVBoxLayout()
        dn_col.setSpacing(2)
        dn_lbl = QLabel("↓ DOWNLOAD")
        dn_lbl.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;"
        )
        self._dn_val = QLabel("—")
        self._dn_val.setStyleSheet(
            f"font-size:20px; font-weight:bold; color:#2196F3; border:none;"
        )
        self._dn_unit = QLabel("Mbps")
        self._dn_unit.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; border:none;"
        )
        dn_col.addWidget(dn_lbl)
        dn_col.addWidget(self._dn_val)
        dn_col.addWidget(self._dn_unit)

        row.addLayout(up_col)
        row.addLayout(dn_col)
        row.addStretch()
        self._body_layout.addLayout(row)
        self._body_layout.addStretch()
        # Worker is started lazily in showEvent — never started in hidden/test context.

    def showEvent(self, event) -> None:       # type: ignore[override]
        super().showEvent(event)
        if self._worker is None:
            self._start_worker()

    def hideEvent(self, event) -> None:       # type: ignore[override]
        self._stop_worker()
        super().hideEvent(event)

    def _start_worker(self) -> None:
        try:
            from workers.iface_bw_worker import IfaceBwPoller
            self._worker = IfaceBwPoller(interval_s=1.0, parent=self)
            self._worker.stats_ready.connect(self._on_stats)
            self._worker.start()
        except Exception:
            pass

    def _stop_worker(self) -> None:
        w = getattr(self, "_worker", None)
        if w is not None:
            try:
                w.stop()
                w.quit()
                w.wait(2000)
            except Exception:
                pass
            self._worker = None

    def _on_stats(self, stats: dict) -> None:
        up   = sum(d["up_mbps"]   for d in stats.values())
        down = sum(d["down_mbps"] for d in stats.values())
        self._up_val.setText(f"{up:.2f}")
        self._dn_val.setText(f"{down:.2f}")

    def refresh(self, store=None) -> None:
        pass  # live data — no store needed


# ── Tile registry & defaults ──────────────────────────────────────────────────

_TILE_CLASSES: Dict[str, type] = {
    cls.TILE_ID: cls for cls in [
        DeviceCountTile, FleetUptimeTile, ServiceStatusTile, TlsStatusTile,
        RttSummaryTile, NetworkGradeTile, AlertFeedTile, EventFeedTile,
        HaDevicesTile, LiveBandwidthTile,
    ]
}

_DEFAULT_ORDER: List[str] = [
    "device_count",
    "fleet_uptime",
    "live_bandwidth",
    "ha_devices",
    "service_status",
    "rtt_summary",
    "tls_status",
    "network_grade",
    "alert_feed",
    "event_feed",
]


# ── Overview page ─────────────────────────────────────────────────────────────

class OverviewPage(QWidget):
    """
    Configurable live dashboard — drag-and-drop tile grid.

    Signal routes expected from app.py:
      on_cycle_done(result_dict: dict)
      on_cert_done(results: list)
      on_svc_done(results: list)
      on_alert(alert)
      on_grade(grade: str, score: float)
    """

    #: Emitted when the user clicks "What's Wrong?"; carries the target page label.
    navigate_to = pyqtSignal(str)

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store      = store
        self._edit_mode  = False
        self._tile_order = self._load_order()
        self._tiles: Dict[str, _BaseTile] = {}
        self._filler: Optional[QWidget]   = None
        self._setup_ui()
        self._build_tiles()
        # Defer store-backed refresh — parented timer so it is destroyed with
        # this widget and never fires after the C++ object is gone (RULE UX6).
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(self._refresh_store_tiles)
        _t.start(1500)

    # ── UI shell ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"QWidget {{ background:{BG_DARK}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)
        root.setSpacing(10)

        # Header row
        hdr = QHBoxLayout()
        title_lbl = QLabel("Overview")
        title_lbl.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" background:transparent;"
        )
        sub_lbl = QLabel("Live dashboard — drag tiles to rearrange in Edit Layout mode.")
        sub_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        hdr.addLayout(title_col, 1)

        self._diagnose_btn = QPushButton("What's Wrong?")
        self._diagnose_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid {ACCENT}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
        )
        self._diagnose_btn.setToolTip("Run a full diagnosis to find out what is wrong")
        self._diagnose_btn.clicked.connect(
            lambda: self.navigate_to.emit("What's Wrong?")
        )
        hdr.addWidget(self._diagnose_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        self._edit_btn = QPushButton("Edit Layout")
        self._edit_btn.setCheckable(True)
        self._edit_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid {ACCENT}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:checked {{ background:{ACCENT}; color:#fff; }}"
        )
        self._edit_btn.toggled.connect(self._on_edit_toggled)
        hdr.addWidget(self._edit_btn, alignment=Qt.AlignmentFlag.AlignBottom)
        root.addLayout(hdr)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background:{BG_DARK}; border:none; }}"
        )

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet(f"background:{BG_DARK};")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(10)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        for c in range(_COLS):
            self._grid_layout.setColumnStretch(c, 1)

        scroll.setWidget(self._grid_container)
        root.addWidget(scroll, 1)

    # ── Tile management ───────────────────────────────────────────────────────

    def _build_tiles(self) -> None:
        for tile_id in _DEFAULT_ORDER:
            cls = _TILE_CLASSES.get(tile_id)
            if cls and tile_id not in self._tiles:
                # RULE 17: parent=grid_container; RULE 18: named local var
                self._tiles[tile_id] = cls(
                    store=self._store,
                    swap_cb=self.swap_tiles,
                    parent=self._grid_container,
                )
        self._reflow()

    def _reflow(self) -> None:
        """Remove all grid items (hide tiles, delete filler), then re-add in order."""
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w is None:
                continue
            if w is self._filler:
                self._filler = None
                w.deleteLater()
            else:
                w.hide()

        for idx, tile_id in enumerate(self._tile_order):
            tile = self._tiles.get(tile_id)
            if tile is None:
                continue
            row = idx // _COLS
            col = idx % _COLS
            self._grid_layout.addWidget(tile, row, col)
            tile.show()

        # Filler row to absorb vertical stretch
        self._filler = QWidget(self._grid_container)
        self._filler.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._filler.setStyleSheet("background:transparent; border:none;")
        fill_row = (len(self._tile_order) + _COLS - 1) // _COLS
        self._grid_layout.addWidget(self._filler, fill_row, 0, 1, _COLS)
        self._grid_layout.setRowStretch(fill_row, 1)

    def swap_tiles(self, src_id: str, dst_id: str) -> None:
        if src_id == dst_id:
            return
        if src_id not in self._tile_order or dst_id not in self._tile_order:
            return
        i = self._tile_order.index(src_id)
        j = self._tile_order.index(dst_id)
        self._tile_order[i], self._tile_order[j] = (
            self._tile_order[j], self._tile_order[i]
        )
        self._save_order()
        self._reflow()

    # ── Edit mode ─────────────────────────────────────────────────────────────

    def _on_edit_toggled(self, checked: bool) -> None:
        self._edit_mode = checked
        self._edit_btn.setText("Save Layout" if checked else "Edit Layout")
        for tile in self._tiles.values():
            tile.set_edit_mode(checked)
        if not checked:
            self._save_order()

    # ── Data slots ────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def on_cycle_done(self, result: dict) -> None:
        states = result.get("states", {})
        rtts   = result.get("rtts",   {})
        t = self._tiles.get("device_count")
        if t:
            t.update_cycle(states)
        t = self._tiles.get("rtt_summary")
        if t:
            t.update_cycle(rtts)

    @pyqtSlot(list)
    def on_cert_done(self, _results: list) -> None:
        t = self._tiles.get("tls_status")
        if t:
            t.refresh(self._store)

    @pyqtSlot(list)
    def on_svc_done(self, results: list) -> None:
        t = self._tiles.get("service_status")
        if t:
            t.update_services(results)

    def on_alert(self, alert) -> None:
        t = self._tiles.get("alert_feed")
        if t:
            t.push_alert(alert)

    def on_grade(self, grade: str, score: float = 0.0) -> None:
        t = self._tiles.get("network_grade")
        if t:
            t.update_grade(grade, score)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_order(self) -> List[str]:
        qs    = QSettings("NetSentinel", "NetSentinel")
        saved = qs.value(_SETTINGS_KEY, None)
        if saved:
            order = [s for s in str(saved).split(",") if s in _TILE_CLASSES]
            for tid in _DEFAULT_ORDER:
                if tid not in order:
                    order.append(tid)
            return order
        return list(_DEFAULT_ORDER)

    def _save_order(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue(_SETTINGS_KEY, ",".join(self._tile_order))

    def _refresh_store_tiles(self) -> None:
        try:
            self.objectName()   # raises RuntimeError if C++ object already deleted
        except RuntimeError:
            return
        for tid in ("fleet_uptime", "tls_status", "event_feed"):
            t = self._tiles.get(tid)
            if t:
                t.refresh(self._store)
