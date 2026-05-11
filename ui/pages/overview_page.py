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

from PyQt6.QtCore    import QMimeData, QPoint, QSettings, QSize, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui     import QColor, QCursor, QDrag, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QMenu,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from modules.metric_store import MetricStore
from ui.styles import (
    ACCENT, ACCENT_LITE, ACCENT_DARK, AMBER,
    BG_CARD, BG_DARK, BG_HOVER, BORDER,
    GREEN, RED, TEXT_PRIMARY, TEXT_SECONDARY,
)

_MIME_TYPE    = "application/x-netsentinel-tile"
_COLS         = 3
_SETTINGS_KEY = "overview/tile_order"
_TILE_HEIGHT  = 175   # uniform fixed height for every tile
_LAYOUT_VER   = 2     # bump when _DEFAULT_ORDER changes; triggers a one-time reset


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
    TILE_ICON  = "◈"
    MIN_HEIGHT = 140

    def __init__(
        self,
        store: Optional[MetricStore] = None,
        swap_cb: Optional[Callable[[str, str], None]] = None,
        remove_cb: Optional[Callable[[str], None]] = None,
        rerun_cb: Optional[Callable] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._store     = store
        self._swap_cb   = swap_cb or (lambda a, b: None)
        self._remove_cb = remove_cb or (lambda _: None)
        self._rerun_cb  = rerun_cb
        self._edit_mode  = False
        self._drag_start: Optional[QPoint] = None
        self._scanned_at: Optional[float]  = None
        self._ts_timer:   Optional[QTimer] = None

        self.setObjectName("overviewTile")
        self.setFixedHeight(_TILE_HEIGHT)
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

        _icon_lbl = QLabel(self.TILE_ICON)
        _icon_lbl.setFixedSize(20, 20)
        _icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _icon_lbl.setStyleSheet(
            f"color:{ACCENT}; font-size:13px; border:none; background:transparent;"
        )
        tb.addWidget(_icon_lbl)

        self._title_lbl = QLabel(self.TILE_LABEL)
        self._title_lbl.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" border:none; background:transparent;"
        )
        tb.addWidget(self._title_lbl, 1)

        self._ts_lbl = QLabel("")
        self._ts_lbl.setStyleSheet(
            f"font-size:9px; color:{TEXT_SECONDARY}; border:none; background:transparent;"
        )
        self._ts_lbl.hide()
        tb.addWidget(self._ts_lbl)

        self._rerun_btn = QPushButton("↺")
        self._rerun_btn.setFixedSize(20, 20)
        self._rerun_btn.setToolTip("Re-run scan")
        self._rerun_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rerun_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; border:1px solid {BORDER};"
            f" color:{ACCENT}; font-size:12px; font-weight:bold; padding:0;"
            f" border-radius:3px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; border-color:{ACCENT}; }}"
        )
        self._rerun_btn.hide()
        if self._rerun_cb:
            self._rerun_btn.clicked.connect(self._rerun_cb)
        tb.addWidget(self._rerun_btn)

        self._drag_handle = QLabel("⠿")
        self._drag_handle.setFixedSize(18, 18)
        self._drag_handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drag_handle.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:14px; border:none; background:transparent;"
        )
        self._drag_handle.setToolTip("Drag to reorder")
        self._drag_handle.hide()
        tb.addWidget(self._drag_handle)

        self._remove_btn = QPushButton("×")
        self._remove_btn.setFixedSize(22, 22)
        self._remove_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" color:{RED}; font-size:13px; font-weight:bold; padding:0;"
            f" border-radius:3px; }}"
            f"QPushButton:hover {{ background:#fff0f0; border-color:{RED}; }}"
        )
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.setToolTip("Remove from overview")
        self._remove_btn.hide()
        self._remove_btn.clicked.connect(lambda: self._remove_cb(self.TILE_ID))
        tb.addWidget(self._remove_btn)

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
        self._remove_btn.setVisible(enabled)
        if self._scanned_at is not None:
            self._ts_lbl.setVisible(not enabled)
            self._rerun_btn.setVisible(not enabled and bool(self._rerun_cb))
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

    def mark_scanned(self) -> None:
        """Record current time as last-scan timestamp and show the ts/rerun controls."""
        import time as _t
        self._scanned_at = _t.time()
        self._update_ts_display()
        if not self._edit_mode:
            self._ts_lbl.show()
            if self._rerun_cb:
                self._rerun_btn.show()
        if self._ts_timer is None:
            self._ts_timer = QTimer(self)
            self._ts_timer.setInterval(60_000)
            self._ts_timer.timeout.connect(self._update_ts_display)
            self._ts_timer.start()

    def _update_ts_display(self) -> None:
        if self._scanned_at is None:
            return
        import time as _t
        delta = int(_t.time() - self._scanned_at)
        if delta < 60:
            text = "Just now"
        elif delta < 3600:
            text = f"{delta // 60} min ago"
        else:
            text = f"{delta // 3600} h ago"
        self._ts_lbl.setText(text)

    def _set_health(self, color: str) -> None:
        self._health_bar.setStyleSheet(f"background:{color}; border:none;")


# ── Concrete tiles ────────────────────────────────────────────────────────────

class DeviceCountTile(_BaseTile):
    TILE_ID    = "device_count"
    TILE_LABEL = "Devices on Network"
    TILE_ICON  = "⬡"

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




class ServiceStatusTile(_BaseTile):
    TILE_ID    = "service_status"
    TILE_LABEL = "Service Heartbeat"
    TILE_ICON  = "◆"

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
    TILE_ICON  = "◍"

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
    TILE_ICON  = "◷"

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
    TILE_ICON  = "◈"
    MIN_HEIGHT = 160
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


class _AlertRow(QFrame):
    """Single clickable alert row in the AlertFeedTile."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout(self)
        row.setSpacing(6)
        row.setContentsMargins(4, 1, 4, 1)
        self.bar = QLabel("▌")
        self.bar.setFixedWidth(10)
        self.bar.setStyleSheet(f"font-size:14px; color:{TEXT_SECONDARY}; border:none;")
        self.msg = QLabel("–")
        self.msg.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; border:none;")
        row.addWidget(self.bar)
        row.addWidget(self.msg, 1)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if active else Qt.CursorShape.ArrowCursor
        )

    def mousePressEvent(self, e) -> None:
        if self._active and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def enterEvent(self, e) -> None:
        if self._active:
            self.setStyleSheet("background: rgba(255,255,255,0.06); border-radius:3px;")
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self.setStyleSheet("")
        super().leaveEvent(e)


class AlertFeedTile(_BaseTile):
    TILE_ID    = "alert_feed"
    TILE_LABEL = "Recent Alerts"
    TILE_ICON  = "◬"
    MIN_HEIGHT = 165
    _SEV_COLOUR = {"CRITICAL": RED, "WARNING": AMBER, "INFO": ACCENT}

    #: Emitted when the user clicks an active alert row. (rule_type, host)
    alert_clicked = pyqtSignal(str, str)

    def _build_body(self) -> None:
        self._rows: list[_AlertRow] = []
        for i in range(5):
            row = _AlertRow(self)
            row.clicked.connect(lambda checked=False, idx=i: self._on_row_click(idx))
            self._body_layout.addWidget(row)
            self._rows.append(row)
        self._body_layout.addStretch()
        self._alerts: list[dict] = []

    def _on_row_click(self, idx: int) -> None:
        if idx < len(self._alerts):
            a = self._alerts[idx]
            self.alert_clicked.emit(a.get("rule_type", ""), a.get("host", ""))

    def push_alert(self, alert) -> None:
        if isinstance(alert, dict):
            d = alert
        else:
            d = {
                "severity":  alert.severity,
                "message":   alert.message,
                "ts":        alert.ts,
                "rule_type": getattr(alert, "rule_type", ""),
                "host":      getattr(alert, "host", ""),
            }
        self._alerts.insert(0, d)
        self._alerts = self._alerts[:5]
        self._redraw()

    def _redraw(self) -> None:
        for i, row in enumerate(self._rows):
            if i < len(self._alerts):
                a      = self._alerts[i]
                colour = self._SEV_COLOUR.get(a.get("severity", "INFO"), TEXT_SECONDARY)
                text   = a.get("message", "")
                row.bar.setStyleSheet(f"font-size:14px; color:{colour}; border:none;")
                row.msg.setText(text[:55] + "…" if len(text) > 55 else text)
                row.msg.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; border:none;")
                row.set_active(True)
            else:
                row.bar.setStyleSheet(f"font-size:14px; color:{TEXT_SECONDARY}; border:none;")
                row.msg.setText("–")
                row.msg.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; border:none;")
                row.set_active(False)


class EventFeedTile(_BaseTile):
    TILE_ID    = "event_feed"
    TILE_LABEL = "Device Events"
    TILE_ICON  = "◉"
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
    TILE_ICON  = "⌂"
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
    TILE_ICON  = "⇅"
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


# ── DNS poller ────────────────────────────────────────────────────────────────

class _DnsPoller(QThread):
    """Probes system DNS resolver every interval_s seconds; emits latency in ms or -1 on failure."""
    result = pyqtSignal(float)

    def __init__(self, interval_s: int = 15, parent=None):
        super().__init__(parent)
        self._stop = False
        self._interval = interval_s

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        import socket
        import time
        while not self._stop:
            try:
                t0 = time.monotonic()
                socket.getaddrinfo("google.com", 80)
                self.result.emit((time.monotonic() - t0) * 1000.0)
            except Exception:
                self.result.emit(-1.0)
            for _ in range(self._interval):
                if self._stop:
                    return
                time.sleep(1)


class DnsStabilityTile(_BaseTile):
    TILE_ID    = "dns_stability"
    TILE_LABEL = "DNS Stability"
    TILE_ICON  = "◎"
    MIN_HEIGHT = 140

    def _build_body(self) -> None:
        self._lat_lbl = QLabel("—")
        self._lat_lbl.setStyleSheet(
            f"font-size:32px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;"
        )
        self._status_lbl = QLabel("Measuring…")
        self._status_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
        )
        self._body_layout.addWidget(self._lat_lbl)
        self._body_layout.addWidget(self._status_lbl)
        self._body_layout.addStretch()
        self._readings: list = []
        self._fail_count: int = 0
        self._worker = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._worker is None:
            self._worker = _DnsPoller(interval_s=15, parent=self)
            self._worker.result.connect(self._on_result)
            self._worker.start()

    def hideEvent(self, event) -> None:
        w = self._worker
        if w is not None:
            w.stop()
            w.quit()
            w.wait(2000)
            self._worker = None
        super().hideEvent(event)

    def _on_result(self, ms: float) -> None:
        if ms < 0:
            self._fail_count += 1
            self._lat_lbl.setText("FAIL")
            self._lat_lbl.setStyleSheet(
                f"font-size:32px; font-weight:bold; color:{RED}; border:none;"
            )
            self._set_health(RED)
        else:
            self._readings.append(ms)
            self._readings = self._readings[-5:]
            self._fail_count = 0
            colour = GREEN if ms < 50 else AMBER if ms < 200 else RED
            self._lat_lbl.setText(f"{ms:.0f} ms")
            self._lat_lbl.setStyleSheet(
                f"font-size:32px; font-weight:bold; color:{colour}; border:none;"
            )
            self._set_health(colour)
        avg = (sum(self._readings) / len(self._readings)) if self._readings else 0
        if self._fail_count:
            self._status_lbl.setText(f"{self._fail_count} failure(s) — resolver unreachable")
            self._status_lbl.setStyleSheet(
                f"font-size:11px; color:{RED}; border:none;"
            )
        elif self._readings:
            self._status_lbl.setText(f"Avg {avg:.0f} ms over last {len(self._readings)} probe(s)")
            self._status_lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
            )

    def refresh(self, store=None) -> None:
        pass  # live data — no store needed


# ── Modem Signal tile ─────────────────────────────────────────────────────────

class ModemSignalTile(_BaseTile):
    """
    Shows live 5G/LTE signal quality from the configured WAN modem.

    Data is pushed by the dashboard via on_modem_signal(); this tile
    never polls directly so it needs no credentials of its own.
    Shows a placeholder until the first sample arrives.
    """

    TILE_ID    = "modem_signal"
    TILE_LABEL = "Modem Signal"
    TILE_ICON  = "⊕"
    MIN_HEIGHT = 140

    def _build_body(self) -> None:
        # Top row: network type badge + RSRP value
        top = QHBoxLayout()
        top.setSpacing(10)

        self._type_lbl = QLabel("—")
        self._type_lbl.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{TEXT_SECONDARY};"
            f" background:{BG_HOVER}; border:1px solid {BORDER};"
            f" border-radius:3px; padding:1px 8px; border:none;"
        )

        self._rsrp_lbl = QLabel("—")
        self._rsrp_lbl.setStyleSheet(
            f"font-size:28px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;"
        )

        self._qual_lbl = QLabel("")
        self._qual_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
        )

        top.addWidget(self._type_lbl)
        top.addWidget(self._rsrp_lbl)
        top.addStretch()

        # Bottom row: band + bars
        bot = QHBoxLayout()
        bot.setSpacing(16)

        self._band_lbl = QLabel("—")
        self._band_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
        )
        self._bars_lbl = QLabel("")
        self._bars_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none;"
        )
        bot.addWidget(self._band_lbl)
        bot.addWidget(self._bars_lbl)
        bot.addStretch()

        self._body_layout.addLayout(top)
        self._body_layout.addWidget(self._qual_lbl)
        self._body_layout.addLayout(bot)
        self._body_layout.addStretch()

        # Placeholder hint
        self._hint_lbl = QLabel("Connect a modem in the Modem tab →")
        self._hint_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; border:none; font-style:italic;"
        )
        self._body_layout.addWidget(self._hint_lbl)

    @pyqtSlot(dict)
    def on_modem_signal(self, data: dict) -> None:
        """Receive a ZteSignalData dict from the dashboard."""
        self._hint_lbl.hide()

        nr_rsrp  = data.get("nr5g_rsrp_dbm")
        lte_rsrp = data.get("lte_rsrp_dbm")
        # Prefer 5G RSRP; fall back to LTE
        rsrp = nr_rsrp if nr_rsrp is not None else lte_rsrp

        net_type = data.get("network_type") or "—"
        self._type_lbl.setText(net_type)

        if rsrp is not None:
            self._rsrp_lbl.setText(f"{rsrp:.0f}")
            from modules.zte_client import ZteMC889Client
            quality = ZteMC889Client.signal_quality_label(rsrp)
            colour = _rsrp_colour(rsrp)
            self._rsrp_lbl.setStyleSheet(
                f"font-size:28px; font-weight:bold; color:{colour}; border:none;"
            )
            self._qual_lbl.setText(f"dBm  ·  {quality}")
            self._set_health(colour)
        else:
            self._rsrp_lbl.setText("—")
            self._qual_lbl.setText("")

        nr_band  = data.get("nr5g_band") or ""
        lte_band = data.get("lte_band")  or ""
        bands = "  +  ".join(b for b in [nr_band, lte_band] if b)
        self._band_lbl.setText(bands or "—")

        bars = data.get("signal_bars")
        self._bars_lbl.setText(f"{bars}/5 bars" if bars is not None else "")

        self.mark_scanned()

    def refresh(self, store=None) -> None:
        pass  # pushed data only


def _rsrp_colour(rsrp: float) -> str:
    if rsrp >= -80:
        return GREEN
    if rsrp >= -90:
        return AMBER
    if rsrp >= -100:
        return AMBER
    return RED


# ── Security scan panel ───────────────────────────────────────────────────────

class _SecurityScanPanel(QWidget):
    """Collapsible panel below the tile grid for launching security tools."""

    run_clicked = pyqtSignal(list)   # emits list of selected nav-label strings

    # (nav_label, display_name, checked_by_default, is_active_probe)
    _TOOLS = [
        ("Threat Intelligence",  "Threat Intelligence",  True,  False),
        ("TLS & exposure",       "TLS & Certificates",   True,  False),
        ("Device Risk Score",    "Device Risk Score",    True,  False),
        ("Known CVEs",           "Known CVEs",           True,  False),
        ("Port Scan (SYN)",      "Port Scan (SYN) ⚠",   False, True),
        ("Exposed to Internet",  "Exposed to Internet ⚠",False, True),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checkboxes: Dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 0)
        outer.setSpacing(0)

        # Header — acts as collapse/expand toggle
        self._toggle_btn = QPushButton("▾  🔐  Security Scan")
        self._toggle_btn.setFixedHeight(36)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{RED};"
            f" border:1px solid {BORDER}; border-left:3px solid {RED};"
            f" border-radius:0px; text-align:left;"
            f" padding:0 12px; font-size:12px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
        )
        self._toggle_btn.clicked.connect(self._toggle)
        outer.addWidget(self._toggle_btn)

        # Body (expanded by default)
        self._body = QFrame()
        self._body.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-top:none; border-bottom-left-radius:4px;"
            f" border-bottom-right-radius:4px; }}"
        )
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(12, 10, 12, 12)
        body_lay.setSpacing(8)

        # Warning strip
        warn_frame = QFrame()
        warn_frame.setStyleSheet(
            f"QFrame {{ background:transparent; border:1px solid {AMBER}; border-radius:3px; }}"
        )
        warn_inner = QHBoxLayout(warn_frame)
        warn_inner.setContentsMargins(8, 5, 8, 5)
        warn_lbl = QLabel(
            "⚠  These tools actively probe devices on your network. "
            "Only use on networks you own or have permission to test."
        )
        warn_lbl.setWordWrap(True)
        warn_lbl.setStyleSheet(
            f"font-size:10px; color:{AMBER}; border:none; background:transparent;"
        )
        warn_inner.addWidget(warn_lbl)
        body_lay.addWidget(warn_frame)

        # Tool checkboxes — 2 column grid
        chk_grid = QGridLayout()
        chk_grid.setSpacing(4)
        chk_grid.setContentsMargins(0, 0, 0, 0)
        for i, (nav_lbl, display, checked, is_active) in enumerate(self._TOOLS):
            chk = QCheckBox(display)
            chk.setChecked(checked)
            colour = AMBER if is_active else TEXT_PRIMARY
            chk.setStyleSheet(
                f"QCheckBox {{ font-size:11px; color:{colour}; background:transparent; spacing:5px; }}"
                f"QCheckBox::indicator {{ width:13px; height:13px; }}"
            )
            chk.stateChanged.connect(self._on_check_changed)
            self._checkboxes[nav_lbl] = chk
            chk_grid.addWidget(chk, i // 2, i % 2)
        body_lay.addLayout(chk_grid)

        # Run row
        run_row = QHBoxLayout()
        run_row.setSpacing(8)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._run_btn = QPushButton("Run Selected")
        self._run_btn.setFixedHeight(28)
        self._run_btn.setMinimumWidth(110)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" font-size:11px; font-weight:bold; padding:0 14px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; }}"
            f"QPushButton:disabled {{ background:{TEXT_SECONDARY}; color:#fff; }}"
        )
        self._run_btn.clicked.connect(self._on_run)
        run_row.addWidget(self._status_lbl, 1)
        run_row.addWidget(self._run_btn)
        body_lay.addLayout(run_row)

        outer.addWidget(self._body)

    def _toggle(self) -> None:
        expanded = not self._body.isVisible()
        self._body.setVisible(expanded)
        self._toggle_btn.setText(
            "▾  🔐  Security Scan" if expanded else "▸  🔐  Security Scan"
        )
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{RED};"
            f" border:1px solid {BORDER}; border-left:3px solid {RED};"
            f" border-radius:0px; text-align:left;"
            f" padding:0 12px; font-size:12px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
        )

    def _on_check_changed(self) -> None:
        any_checked = any(c.isChecked() for c in self._checkboxes.values())
        self._run_btn.setEnabled(any_checked)

    def _on_run(self) -> None:
        selected = [lbl for lbl, chk in self._checkboxes.items() if chk.isChecked()]
        if selected:
            self._status_lbl.setText(f"Opening {selected[0]}…")
            self.run_clicked.emit(selected)


# ── Tile registry & defaults ──────────────────────────────────────────────────

_TILE_CLASSES: Dict[str, type] = {
    cls.TILE_ID: cls for cls in [
        DeviceCountTile, ServiceStatusTile, TlsStatusTile,
        RttSummaryTile, NetworkGradeTile, AlertFeedTile, EventFeedTile,
        HaDevicesTile, LiveBandwidthTile, DnsStabilityTile,
        ModemSignalTile,
    ]
}

# All tiles shown by default — each has a graceful empty state when data is absent.
_DEFAULT_ORDER: List[str] = [
    "device_count",
    "live_bandwidth",
    "modem_signal",
    "dns_stability",
    "rtt_summary",
    "network_grade",
    "alert_feed",
    "event_feed",
    "service_status",
    "ha_devices",
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
    #: Emitted when the user requests a Quick Network Assessment (M1–M5 bundle).
    scan_requested = pyqtSignal()
    #: Emitted when the user requests security tool runs; carries list of nav labels.
    security_scan_requested = pyqtSignal(list)

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store      = store
        self._edit_mode  = False
        self._scanning   = False
        self._hidden: set = self._load_hidden()
        self._tile_order = self._load_order()
        self._tiles: Dict[str, _BaseTile] = {}
        self._filler: Optional[QWidget]   = None
        self._card_data  = None  # CardData instance; None until first benchmark
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

        _btn_qss = (
            f"QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid {ACCENT}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:disabled {{ color:{TEXT_SECONDARY}; border-color:{TEXT_SECONDARY}; }}"
        )
        self._share_btn = QPushButton("Share Card ▾")
        self._share_btn.setStyleSheet(_btn_qss)
        self._share_btn.setToolTip("Export network health card as PNG or HTML")
        self._share_btn.clicked.connect(self._show_share_menu)
        hdr.addWidget(self._share_btn, alignment=Qt.AlignmentFlag.AlignBottom)

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

        # Hero summary strip — always visible, 4 stat pills
        hero = QHBoxLayout()
        hero.setSpacing(8)
        _pill_qss = (
            f"QLabel {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:4px; padding:4px 14px;"
            f" font-size:11px; color:{TEXT_PRIMARY}; }}"
        )
        self._hero_devices = QLabel("⬡  Devices: —")
        self._hero_grade   = QLabel("◈  Grade: —")
        self._hero_alerts  = QLabel("◬  Alerts: 0")
        self._hero_svc     = QLabel("◆  Services: —")
        for _pill in (self._hero_devices, self._hero_grade,
                      self._hero_alerts, self._hero_svc):
            _pill.setStyleSheet(_pill_qss)
            hero.addWidget(_pill)
        hero.addStretch()
        root.addLayout(hero)

        # Add-tile strip — only visible in edit mode when tiles are hidden
        self._add_strip = QWidget()
        self._add_strip.setStyleSheet(
            f"QWidget {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:4px; }}"
        )
        self._add_strip_layout = QHBoxLayout(self._add_strip)
        self._add_strip_layout.setContentsMargins(10, 6, 10, 6)
        self._add_strip_layout.setSpacing(8)
        _add_lbl = QLabel("Add tile:")
        _add_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none; background:transparent;"
        )
        self._add_strip_layout.addWidget(_add_lbl)
        self._add_strip_layout.addStretch()
        self._add_strip.hide()
        root.addWidget(self._add_strip)

        # ── CTA bar — full-width Quick Network Assessment launcher ────────────
        _cta = QFrame()
        _cta.setObjectName("ctaBar")
        _cta.setStyleSheet(
            f"QFrame#ctaBar {{ background:{BG_CARD}; border:1px solid {ACCENT};"
            f" border-radius:6px; }}"
        )
        _cta_lay = QHBoxLayout(_cta)
        _cta_lay.setContentsMargins(16, 10, 12, 10)
        _cta_lay.setSpacing(12)

        _cta_text = QVBoxLayout()
        _cta_text.setSpacing(2)
        _cta_head = QLabel("Quick Network Assessment")
        _cta_head.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" border:none; background:transparent;"
        )
        self._scan_sub = QLabel("Discover devices  ·  check stability  ·  detect threats")
        self._scan_sub.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; border:none; background:transparent;"
        )
        _cta_text.addWidget(_cta_head)
        _cta_text.addWidget(self._scan_sub)

        self._scan_btn = QPushButton("▶  Scan Network")
        self._scan_btn.setFixedHeight(34)
        self._scan_btn.setMinimumWidth(145)
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" font-size:12px; font-weight:bold; padding:0 18px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; }}"
            f"QPushButton:disabled {{ background:{TEXT_SECONDARY}; color:#fff; }}"
        )
        self._scan_btn.clicked.connect(self._on_scan_clicked)
        _cta_lay.addLayout(_cta_text, 1)
        _cta_lay.addWidget(self._scan_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(_cta)

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

        # ── Security scan panel — collapsed by default ────────────────────────
        self._security_panel = _SecurityScanPanel(self)
        self._security_panel.run_clicked.connect(
            lambda labels: self.security_scan_requested.emit(labels)
        )
        root.addWidget(self._security_panel)

    # ── Tile management ───────────────────────────────────────────────────────

    def _build_tiles(self) -> None:
        _rerun_ids = {"device_count", "rtt_summary", "service_status", "tls_status", "network_grade"}
        for tile_id, cls in _TILE_CLASSES.items():
            if tile_id not in self._tiles:
                # RULE 17: parent=grid_container; RULE 18: named local var
                _rcb = (lambda: self.scan_requested.emit()) if tile_id in _rerun_ids else None
                tile = cls(
                    store=self._store,
                    swap_cb=self.swap_tiles,
                    remove_cb=self._remove_tile,
                    rerun_cb=_rcb,
                    parent=self._grid_container,
                )
                self._tiles[tile_id] = tile
        alert_tile = self._tiles.get("alert_feed")
        if alert_tile is not None:
            alert_tile.alert_clicked.connect(self._on_alert_navigate)
        self._reflow()

    def _on_scan_clicked(self) -> None:
        if not self._scanning:
            self.scan_requested.emit()

    def set_scanning(self, running: bool) -> None:
        self._scanning = running
        self._scan_btn.setEnabled(not running)
        if running:
            self._scan_btn.setText("Scanning…")
            self._scan_sub.setText("Scan in progress — tiles will update as each module completes.")
        else:
            self._scan_btn.setText("▶  Scan Network")
            self._scan_sub.setText("Discover devices  ·  check stability  ·  detect threats")

    def _on_alert_navigate(self, rule_type: str, host: str) -> None:
        if rule_type == "SERVICE_DOWN":
            self.navigate_to.emit("Service Heartbeat")
        elif rule_type == "CERT_EXPIRY":
            self.navigate_to.emit("TLS & exposure")
        else:
            self.navigate_to.emit("Devices on Network")

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

        # Hide every tile unconditionally — catches tiles that were never added to the
        # layout (e.g. tiles removed from _DEFAULT_ORDER but still in _TILE_CLASSES).
        # Without this, parented-but-unlayout'd widgets render at (0,0) of the container.
        for tile in self._tiles.values():
            tile.hide()

        visible = [self._tiles[tid] for tid in self._tile_order if tid in self._tiles]
        for idx, tile in enumerate(visible):
            self._grid_layout.addWidget(tile, idx // _COLS, idx % _COLS)
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
        if checked:
            self._refresh_add_strip()
        else:
            self._add_strip.hide()
            self._save_order()

    # ── Data slots ────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def on_cycle_done(self, result: dict) -> None:
        states = result.get("states", {})
        rtts   = result.get("rtts",   {})
        t = self._tiles.get("device_count")
        if t:
            t.update_cycle(states)
            t.mark_scanned()
        t = self._tiles.get("rtt_summary")
        if t:
            t.update_cycle(rtts)
            t.mark_scanned()
        total = len(states)
        down  = sum(1 for s in states.values() if s == "DOWN")
        pill_colour = RED if down else (AMBER if total == 0 else GREEN)
        self._hero_devices.setStyleSheet(
            f"QLabel {{ background:{BG_CARD}; border:1px solid {pill_colour};"
            f" border-radius:4px; padding:4px 14px;"
            f" font-size:11px; color:{TEXT_PRIMARY}; }}"
        )
        self._hero_devices.setText(
            f"⬡  Devices: {total}" + (f"  ({down} ↓)" if down else "")
        )

    @pyqtSlot(list)
    def on_cert_done(self, _results: list) -> None:
        t = self._tiles.get("tls_status")
        if t:
            t.refresh(self._store)
            t.mark_scanned()

    @pyqtSlot(list)
    def on_svc_done(self, results: list) -> None:
        t = self._tiles.get("service_status")
        if t:
            t.update_services(results)
            t.mark_scanned()
        if results:
            up  = sum(1 for r in results if (r.get("status") if isinstance(r, dict) else getattr(r, "status", "")) == "UP")
            dn  = len(results) - up
            pill_colour = RED if dn else GREEN
            self._hero_svc.setStyleSheet(
                f"QLabel {{ background:{BG_CARD}; border:1px solid {pill_colour};"
                f" border-radius:4px; padding:4px 14px;"
                f" font-size:11px; color:{TEXT_PRIMARY}; }}"
            )
            self._hero_svc.setText(
                f"◆  Services: {up} up" + (f" / {dn} ↓" if dn else "")
            )

    def on_alert(self, alert) -> None:
        t = self._tiles.get("alert_feed")
        if t:
            t.push_alert(alert)
        # Update hero pill alert count
        count_text = self._hero_alerts.text()
        try:
            n = int(count_text.split(":")[-1].strip().split()[0])
        except (ValueError, IndexError):
            n = 0
        n += 1
        sev = alert.get("severity", "INFO") if isinstance(alert, dict) else getattr(alert, "severity", "INFO")
        pill_colour = RED if sev == "CRITICAL" else AMBER if sev == "WARNING" else ACCENT
        self._hero_alerts.setStyleSheet(
            f"QLabel {{ background:{BG_CARD}; border:1px solid {pill_colour};"
            f" border-radius:4px; padding:4px 14px;"
            f" font-size:11px; color:{TEXT_PRIMARY}; }}"
        )
        self._hero_alerts.setText(f"◬  Alerts: {n}")

    @pyqtSlot(dict)
    def on_modem_signal(self, data: dict) -> None:
        """Route modem signal data to ModemSignalTile."""
        t = self._tiles.get("modem_signal")
        if t:
            t.on_modem_signal(data)

    def set_card_data(self, card_data) -> None:
        """Receive a CardData instance from the dashboard after each benchmark."""
        self._card_data = card_data

    def _show_share_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Save PNG…",  self._export_png)
        menu.addAction("Copy PNG",   self._copy_png)
        menu.addAction("Save HTML…", self._export_html)
        menu.exec(self._share_btn.mapToGlobal(self._share_btn.rect().bottomLeft()))

    def _render_pixmap(self):
        from modules.diagnostic_card import render_card_widget, build_card_data
        card = self._card_data or build_card_data(None, None, self._store)
        widget = render_card_widget(card)
        widget.show()          # must be visible for grab() to paint correctly
        widget.hide()
        return widget.grab()

    def _export_png(self) -> None:
        if not self._card_data:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Card as PNG",
            f"netsentinel_card_{self._card_data.generated_at[:10]}.png",
            "PNG images (*.png)",
        )
        if path:
            self._render_pixmap().save(path, "PNG")

    def _copy_png(self) -> None:
        if not self._card_data:
            return
        QApplication.clipboard().setPixmap(self._render_pixmap())

    def _export_html(self) -> None:
        if not self._card_data:
            return
        from pathlib import Path
        from modules.report_exporter import save_card_html
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Card as HTML",
            f"netsentinel_card_{self._card_data.generated_at[:10]}.html",
            "HTML files (*.html)",
        )
        if path:
            out = save_card_html(self._card_data.to_dict(), Path(path))
            import webbrowser
            webbrowser.open(out.as_uri())

    def on_grade(self, grade: str, score: float = 0.0) -> None:
        t = self._tiles.get("network_grade")
        if t:
            t.update_grade(grade, score)
            t.mark_scanned()
        letter = grade[:1].upper() if grade else "–"
        _grade_colours = {"A": GREEN, "B": GREEN, "C": AMBER, "D": RED, "F": RED}
        pill_colour = _grade_colours.get(letter, BORDER)
        self._hero_grade.setStyleSheet(
            f"QLabel {{ background:{BG_CARD}; border:1px solid {pill_colour};"
            f" border-radius:4px; padding:4px 14px;"
            f" font-size:11px; color:{TEXT_PRIMARY}; }}"
        )
        self._hero_grade.setText(f"◈  Grade: {letter}")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_order(self) -> List[str]:
        qs = QSettings("NetSentinel", "NetSentinel")
        # One-time migration: reset to current _DEFAULT_ORDER when layout version changes.
        try:
            stored_ver = int(qs.value("overview/layout_version", "1") or "1")
        except (ValueError, TypeError):
            stored_ver = 1
        if stored_ver < _LAYOUT_VER:
            qs.setValue("overview/layout_version", str(_LAYOUT_VER))
            qs.remove(_SETTINGS_KEY)
            qs.remove("overview/hidden_tiles")
            self._hidden = set()
            return list(_DEFAULT_ORDER)
        saved = qs.value(_SETTINGS_KEY, None)
        if saved:
            order = [s for s in str(saved).split(",") if s in _TILE_CLASSES]
            for tid in _DEFAULT_ORDER:
                if tid not in order and tid not in self._hidden:
                    order.append(tid)
            return order
        return [tid for tid in _DEFAULT_ORDER if tid not in self._hidden]

    def _save_order(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue(_SETTINGS_KEY, ",".join(self._tile_order))
        qs.setValue("overview/hidden_tiles", ",".join(sorted(self._hidden)))

    def _load_hidden(self) -> set:
        qs = QSettings("NetSentinel", "NetSentinel")
        saved = qs.value("overview/hidden_tiles", None)
        if saved:
            return {s for s in str(saved).split(",") if s in _TILE_CLASSES}
        return set()

    def _remove_tile(self, tile_id: str) -> None:
        if tile_id not in _TILE_CLASSES:
            return
        self._hidden.add(tile_id)
        if tile_id in self._tile_order:
            self._tile_order.remove(tile_id)
        self._save_order()
        self._reflow()
        self._refresh_add_strip()

    def _add_tile(self, tile_id: str) -> None:
        if tile_id not in _TILE_CLASSES:
            return
        self._hidden.discard(tile_id)
        if tile_id not in self._tile_order:
            self._tile_order.append(tile_id)
        self._save_order()
        self._reflow()
        self._refresh_add_strip()

    def _refresh_add_strip(self) -> None:
        # Clear tile buttons between label (index 0) and stretch (last item)
        while self._add_strip_layout.count() > 2:
            item = self._add_strip_layout.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self._hidden or not self._edit_mode:
            self._add_strip.hide()
            return

        for tile_id in _DEFAULT_ORDER:
            if tile_id not in self._hidden:
                continue
            cls = _TILE_CLASSES.get(tile_id)
            if cls is None:
                continue
            btn = QPushButton(f"＋  {cls.TILE_LABEL}")
            btn.setFixedHeight(24)
            btn.setStyleSheet(
                f"QPushButton {{ background:transparent; border:1px solid {ACCENT};"
                f" color:{ACCENT}; border-radius:4px; font-size:10px; padding:0 8px; }}"
                f"QPushButton:hover {{ background:{ACCENT}; color:#fff; }}"
            )
            btn.clicked.connect(lambda _checked, tid=tile_id: self._add_tile(tid))
            self._add_strip_layout.insertWidget(
                self._add_strip_layout.count() - 1, btn
            )

        self._add_strip.show()

    def _refresh_store_tiles(self) -> None:
        try:
            self.objectName()   # raises RuntimeError if C++ object already deleted
        except RuntimeError:
            return
        for tid in ("tls_status", "event_feed"):
            t = self._tiles.get(tid)
            if t:
                t.refresh(self._store)
