"""
overview_tile.py — Tile widget classes for the Overview dashboard.

Extracted from ui/pages/overview_page.py (Sprint 4, S3-2).
OverviewPage is defined in overview_page.py and imports from here.
"""
from __future__ import annotations

import datetime
from typing import Callable, Dict, List, Optional

from PyQt6.QtCore    import QEasingCurve, QMimeData, QPoint, QPropertyAnimation, Qt, QThread, QTimer, QVariantAnimation, pyqtSignal, pyqtSlot
from PyQt6.QtGui     import QColor, QCursor, QDrag, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from modules.metric_store import MetricStore
from ui.nav.labels import NavLabel as L
from ui import styles as _s
from ui.styles import (
    CHART_DOWN, CHART_UP,
)
from ui.widgets.device_detail_pane import _wire_close_icon

_MIME_TYPE    = "application/x-netsentinel-tile"
_COLS         = 3
_SETTINGS_KEY = "overview/tile_order"
_TILE_HEIGHT      = 175   # uniform fixed height for every tile
_EXPANDED_HEIGHT  = 280   # height when tile is expanded (OVERVIEW-1)
_LAYOUT_VER   = 4     # bump when _DEFAULT_ORDER changes; triggers a one-time reset


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
    _NAV_LABEL = ""   # nav page to open with "View full →" (empty = no link)

    expand_toggled    = pyqtSignal(object)  # emits self when expanding
    navigate_requested = pyqtSignal(str)   # emits nav label for "View full →"

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
        self._expanded:       bool                  = False
        self._detail_widget:  Optional[QWidget]     = None
        self._expand_anim:    Optional[QVariantAnimation] = None
        self._hover_anim:     Optional[QPropertyAnimation] = None
        self._base_pos:       Optional[QPoint]             = None

        self.setObjectName("overviewTile")
        self.setFixedHeight(_TILE_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAcceptDrops(True)
        self._setup_frame()
        self._build_body()

    # ── Frame ─────────────────────────────────────────────────────────────────

    def _setup_frame(self) -> None:
        _s.themed_ss(self, lambda: _s.qss_frame("overviewTile", _s.BG_CARD, _s.BORDER, radius=None, hover_border=_s.ACCENT))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        _s.themed_ss(title_bar, "QWidget {{ background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER}; }}")
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(10, 0, 8, 0)
        tb.setSpacing(4)

        _icon_lbl = QLabel(self.TILE_ICON)
        _icon_lbl.setFixedSize(20, 20)
        _icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(_icon_lbl, "color:{ACCENT}; font-size:13px; border:none; background:transparent;")
        tb.addWidget(_icon_lbl)

        self._title_lbl = QLabel(self.TILE_LABEL)
        _s.themed_ss(self._title_lbl, "font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
            " border:none; background:transparent;")
        tb.addWidget(self._title_lbl, 1)

        self._ts_lbl = QLabel("")
        _s.themed_ss(self._ts_lbl, "font-size:9px; color:{TEXT_SECONDARY}; border:none; background:transparent;")
        self._ts_lbl.hide()
        tb.addWidget(self._ts_lbl)

        self._rerun_btn = QPushButton("↺")
        self._rerun_btn.setFixedSize(20, 20)
        self._rerun_btn.setToolTip(_s.safe_tooltip("Re-run scan"))
        self._rerun_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._rerun_btn, "QPushButton {{ background:transparent; border:1px solid {BORDER};"
            " color:{ACCENT}; font-size:12px; font-weight:bold; padding:0;"
            " border-radius:3px; }}"
            "QPushButton:hover {{ background:{BG_HOVER}; border-color:{ACCENT}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
        self._rerun_btn.hide()
        if self._rerun_cb:
            self._rerun_btn.clicked.connect(self._rerun_cb)
        tb.addWidget(self._rerun_btn)

        self._drag_handle = QLabel("⠿")
        self._drag_handle.setFixedSize(18, 18)
        self._drag_handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(self._drag_handle, "color:{TEXT_SECONDARY}; font-size:14px; border:none; background:transparent;")
        self._drag_handle.setToolTip(_s.safe_tooltip("Drag to reorder"))
        self._drag_handle.hide()
        tb.addWidget(self._drag_handle)

        self._remove_btn = QPushButton()
        self._remove_btn.setFixedSize(22, 22)
        _wire_close_icon(self._remove_btn, "RED")
        _s.themed_ss(self._remove_btn, "QPushButton {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " padding:0; border-radius:3px; }}"
            "QPushButton:hover {{ background:{PRO_WARN_BG}; border-color:{RED}; }}"
            "QPushButton:pressed {{ background:{BG_CARD}; }}")
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.setToolTip(_s.safe_tooltip("Remove from overview"))
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
        _s.themed_ss(self._health_bar, "background:{BORDER}; border:none;")
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
            self._ts_lbl.setVisible(True)
            self._rerun_btn.setVisible(not enabled and bool(self._rerun_cb))
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor if enabled
                               else Qt.CursorShape.ArrowCursor))

    # ── Drag ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        elif not self._edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self.toggle_expand()
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
            _s.themed_ss(self, "QFrame#overviewTile {{ background:{BG_HOVER};"
                " border:2px solid {ACCENT}; }}")

    def dragLeaveEvent(self, event):
        self._reset_style()

    def dropEvent(self, event):
        self._reset_style()
        if event.mimeData().hasFormat(_MIME_TYPE):
            src_id = event.mimeData().data(_MIME_TYPE).data().decode()
            self._swap_cb(src_id, self.TILE_ID)
            event.acceptProposedAction()

    def _reset_style(self) -> None:
        _s.themed_ss(self, lambda: _s.qss_frame("overviewTile", _s.BG_CARD, _s.BORDER, radius=None, hover_border=_s.ACCENT))

    # ── ANIM-7: hover lift ────────────────────────────────────────────────────

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        from ui.theme import _reduce_motion
        if _reduce_motion() or self._edit_mode:
            return
        self._base_pos = self.pos()
        if self._hover_anim is not None:
            self._hover_anim.stop()
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(120)
        anim.setEasingCurve(QEasingCurve.Type.OutQuart)
        anim.setStartValue(self.pos())
        anim.setEndValue(QPoint(self.pos().x(), self.pos().y() - 2))
        anim.start()
        self._hover_anim = anim

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        from ui.theme import _reduce_motion
        if _reduce_motion() or self._base_pos is None:
            return
        if self._hover_anim is not None:
            self._hover_anim.stop()
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(80)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(self._base_pos)
        anim.start()
        self._hover_anim = anim

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
        if delta >= 86400:
            days = delta // 86400
            text = f"Data from {days} day{'s' if days != 1 else ''} ago — rescan?"
            color = _s.AMBER
            font_size = "10px"
        else:
            if delta < 60:
                text = "Just now"
            elif delta < 3600:
                text = f"{delta // 60} min ago"
            else:
                text = f"{delta // 3600} h ago"
            if delta >= 7200:
                color = _s.RED
            elif delta >= 1800:
                color = _s.AMBER
            else:
                color = _s.TEXT_SECONDARY
            font_size = "9px"
        self._ts_lbl.setText(text)
        _s.themed_ss(self._ts_lbl, lambda font_size=font_size, color=color: f"font-size:{font_size}; color:{color}; border:none; background:transparent;")

    def _set_health(self, color: str) -> None:
        _s.themed_ss(self._health_bar, lambda color=color: f"background:{color}; border:none;")

    # ── Expand / collapse (OVERVIEW-1) ────────────────────────────────────────

    def _build_detail(self) -> Optional[QWidget]:
        """Return a detail sub-panel widget, or None if no detail is available."""
        if not self._NAV_LABEL:
            return None
        w = QWidget()
        w.setStyleSheet("background:transparent; border:none;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 4, 12, 6)
        btn = QPushButton(f"View full  {self._NAV_LABEL} →")
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(btn, "QPushButton {{ color:{ACCENT}; font-size:10px; border:none;"
            " background:transparent; text-align:left; padding:0; }}"
            "QPushButton:hover {{ text-decoration:underline; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        btn.clicked.connect(lambda: self.navigate_requested.emit(self._NAV_LABEL))
        lay.addWidget(btn)
        lay.addStretch()
        return w

    def toggle_expand(self) -> None:
        """Expand or collapse this tile (OVERVIEW-1)."""
        from ui.theme import _reduce_motion
        going_expanded = not self._expanded

        if going_expanded:
            if self._detail_widget is None:
                self._detail_widget = self._build_detail()
                if self._detail_widget is not None:
                    # Insert before health bar (last item in outer layout)
                    outer = self.layout()
                    outer.insertWidget(outer.count() - 1, self._detail_widget)
            if self._detail_widget is not None:
                self._detail_widget.setVisible(True)
            self._expanded = True
            self.expand_toggled.emit(self)
            target_h = _EXPANDED_HEIGHT
        else:
            self._expanded = False
            if self._detail_widget is not None:
                self._detail_widget.setVisible(False)
            target_h = _TILE_HEIGHT

        if _reduce_motion():
            self.setFixedHeight(target_h)
            return

        if self._expand_anim is not None:
            self._expand_anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self.height())
        anim.setEndValue(target_h)
        anim.setDuration(280)
        anim.setEasingCurve(QEasingCurve.Type.OutQuart)
        anim.valueChanged.connect(lambda v: self.setFixedHeight(int(v)))
        anim.start()
        self._expand_anim = anim


# ── Concrete tiles ────────────────────────────────────────────────────────────

class DeviceCountTile(_BaseTile):
    TILE_ID    = "device_count"
    TILE_LABEL = "Devices on Network"
    TILE_ICON  = "⬡"
    _NAV_LABEL = "Availability History"

    def _build_body(self) -> None:
        self._count_lbl = _AnimatedNumberLabel("–", parent=self)
        _s.themed_ss(self._count_lbl, "font-size:38px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")
        self._sub_lbl = QLabel("Waiting for scan…")
        _s.themed_ss(self._sub_lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 11, transparent=False))
        self._body_layout.addWidget(self._count_lbl)
        self._body_layout.addWidget(self._sub_lbl)
        self._body_layout.addStretch()
        self._last_states: dict = {}

    def update_cycle(self, states: dict) -> None:
        total = len(states)
        up    = sum(1 for s in states.values() if s == "UP")
        down  = sum(1 for s in states.values() if s == "DOWN")
        self._last_states = dict(states)
        self._count_lbl.animate_to(total)
        parts = []
        if up:   parts.append(f"{up} up")
        if down: parts.append(f"{down} ↓ down")
        self._sub_lbl.setText("  ·  ".join(parts) if parts else "No devices monitored")
        colour = _s.RED if down else (_s.AMBER if total == 0 else _s.GREEN)
        self._set_health(colour)

    def _build_detail(self) -> Optional[QWidget]:
        w = QWidget()
        w.setStyleSheet("background:transparent; border:none;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 2, 12, 4)
        lay.setSpacing(2)
        items = list(self._last_states.items())[:5]
        if not items:
            lbl = QLabel("No devices monitored yet")
            _s.themed_ss(lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 10, transparent=False))
            lay.addWidget(lbl)
        else:
            for ip, state in items:
                row = QHBoxLayout()
                row.setSpacing(6)
                color = _s.GREEN if state == "UP" else _s.RED
                dot = QLabel("●")
                dot.setFixedWidth(12)
                _s.themed_ss(dot, lambda color=color: f"color:{color}; font-size:9px; border:none;")
                ip_lbl = QLabel(ip)
                _s.themed_ss(ip_lbl, lambda: _s.qss_label(_s.TEXT_PRIMARY, 10, transparent=False))
                st_lbl = QLabel(state)
                _s.themed_ss(st_lbl, lambda color=color: f"color:{color}; font-size:10px; font-weight:bold; border:none;")
                row.addWidget(dot)
                row.addWidget(ip_lbl, 1)
                row.addWidget(st_lbl)
                lay.addLayout(row)
        lay.addStretch()
        return w




class ServiceStatusTile(_BaseTile):
    TILE_ID    = "service_status"
    TILE_LABEL = "Service Heartbeat"
    TILE_ICON  = "◆"

    def _build_body(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)

        up_col = QVBoxLayout()
        self._up_lbl = _AnimatedNumberLabel("–", parent=self)
        _s.themed_ss(self._up_lbl, "font-size:30px; font-weight:bold; color:{GREEN}; border:none;")
        up_sub = QLabel("UP")
        _s.themed_ss(up_sub, "font-size:10px; font-weight:bold; color:{GREEN}; border:none;")
        up_col.addWidget(self._up_lbl)
        up_col.addWidget(up_sub)

        dn_col = QVBoxLayout()
        self._dn_lbl = _AnimatedNumberLabel("–", parent=self)
        _s.themed_ss(self._dn_lbl, "font-size:30px; font-weight:bold; color:{RED}; border:none;")
        dn_sub = QLabel("DOWN")
        _s.themed_ss(dn_sub, "font-size:10px; font-weight:bold; color:{RED}; border:none;")
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
        self._set_health(_s.RED if dn > 0 else _s.GREEN)


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
            _s.themed_ss(num_lbl, lambda colour=colour: f"font-size:22px; font-weight:bold; color:{colour}; border:none;")
            sub = QLabel(text)
            _s.themed_ss(sub, lambda: _s.qss_label(_s.TEXT_SECONDARY, 10, transparent=False))
            grid.addWidget(num_lbl, row_idx, 0)
            grid.addWidget(sub,     row_idx, 1)

        _row(self._ok_lbl,       _s.GREEN, "OK",            0)
        _row(self._expiring_lbl, _s.AMBER, "Expiring soon", 1)
        _row(self._expired_lbl,  _s.RED,   "Expired",       2)
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
            pass  # non-fatal


class RttSummaryTile(_BaseTile):
    TILE_ID    = "rtt_summary"
    TILE_LABEL = "Network Latency"
    TILE_ICON  = "◷"
    _NAV_LABEL = "DNS & Stability"

    def _build_body(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)

        rtt_col = QVBoxLayout()
        self._rtt_lbl = QLabel("–")
        _s.themed_ss(self._rtt_lbl, "font-size:30px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")
        rtt_sub = QLabel("Avg RTT")
        _s.themed_ss(rtt_sub, lambda: _s.qss_label(_s.TEXT_SECONDARY, 10, transparent=False))
        rtt_sub.setToolTip(_s.safe_tooltip("RTT — Round-Trip Time: how long a ping takes to travel to a host and back, in milliseconds. Under 20 ms is excellent."))
        rtt_col.addWidget(self._rtt_lbl)
        rtt_col.addWidget(rtt_sub)

        loss_col = QVBoxLayout()
        self._loss_lbl = QLabel("–")
        _s.themed_ss(self._loss_lbl, "font-size:30px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")
        loss_sub = QLabel("Packet loss")
        _s.themed_ss(loss_sub, lambda: _s.qss_label(_s.TEXT_SECONDARY, 10, transparent=False))
        loss_col.addWidget(self._loss_lbl)
        loss_col.addWidget(loss_sub)

        row.addLayout(rtt_col)
        row.addLayout(loss_col)
        row.addStretch()
        self._body_layout.addLayout(row)
        self._body_layout.addStretch()
        self._last_rtts: dict = {}

    def update_cycle(self, rtts: dict) -> None:
        self._last_rtts = dict(rtts)
        valid = [v for v in rtts.values() if v is not None and v >= 0]
        total = len(rtts)
        lost  = sum(1 for v in rtts.values() if v is None or v < 0)
        if valid:
            avg    = sum(valid) / len(valid)
            colour = _s.GREEN if avg < 50 else _s.AMBER if avg < 150 else _s.RED
            self._rtt_lbl.setText(f"{avg:.0f} ms")
            _s.themed_ss(self._rtt_lbl, lambda colour=colour: f"font-size:30px; font-weight:bold; color:{colour}; border:none;")
        else:
            self._rtt_lbl.setText("–")
        if total:
            pct    = (lost / total) * 100
            colour = _s.GREEN if pct == 0 else _s.AMBER if pct < 10 else _s.RED
            self._loss_lbl.setText(f"{pct:.0f}%")
            _s.themed_ss(self._loss_lbl, lambda colour=colour: f"font-size:30px; font-weight:bold; color:{colour}; border:none;")

    def _build_detail(self) -> Optional[QWidget]:
        w = QWidget()
        w.setStyleSheet("background:transparent; border:none;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 2, 12, 4)
        lay.setSpacing(3)
        valid = {ip: v for ip, v in self._last_rtts.items() if v is not None and v >= 0}
        top3 = sorted(valid.items(), key=lambda x: x[1], reverse=True)[:3]
        if not top3:
            lbl = QLabel("No RTT data yet")
            _s.themed_ss(lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 10, transparent=False))
            lay.addWidget(lbl)
        else:
            mx = max(v for _, v in top3)
            for ip, rtt in top3:
                color = _s.GREEN if rtt < 50 else _s.AMBER if rtt < 150 else _s.RED
                row = QHBoxLayout()
                row.setSpacing(6)
                ip_lbl = QLabel(ip)
                _s.themed_ss(ip_lbl, lambda: _s.qss_label(_s.TEXT_PRIMARY, 10, transparent=False))
                ip_lbl.setMinimumWidth(110)
                bar = QFrame()
                bar_w = max(4, int((rtt / mx) * 60)) if mx > 0 else 4
                bar.setFixedSize(bar_w, 8)
                _s.themed_ss(bar, lambda color=color: f"background:{color}; border:none; border-radius:2px;")
                rtt_lbl = QLabel(f"{rtt:.0f} ms")
                _s.themed_ss(rtt_lbl, lambda color=color: f"color:{color}; font-size:10px; font-weight:bold; border:none;")
                row.addWidget(ip_lbl)
                row.addWidget(bar)
                row.addWidget(rtt_lbl)
                row.addStretch()
                lay.addLayout(row)
        lay.addStretch()
        return w


class NetworkGradeTile(_BaseTile):
    TILE_ID    = "network_grade"
    TILE_LABEL = "Network Grade"
    TILE_ICON  = "◈"
    MIN_HEIGHT = 160
    _GRADE_COLOUR = {   # token NAMES resolved live via getattr(_s, …) at call time
        "A": "GREEN", "B": "GREEN", "C": "AMBER", "D": "RED", "F": "RED",
    }
    _GRADE_TIPS = {
        "A": "A — Excellent: no significant issues detected.",
        "B": "B — Good: minor issues found; review the Security section.",
        "C": "C — Fair: several issues detected; investigation recommended.",
        "D": "D — Poor: significant problems found; action needed.",
        "F": "F — Critical: severe issues detected; immediate action required.",
    }

    def _build_body(self) -> None:
        self._grade_lbl = QLabel("–")
        self._grade_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(self._grade_lbl, "font-size:56px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;")
        self._grade_lbl.setToolTip(_s.safe_tooltip("Run a Network Grade scan to see your score (A–F)."))
        self._sub_lbl = QPushButton("Run Network Grade →")
        self._sub_lbl.setFlat(True)
        self._sub_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._sub_lbl, "QPushButton {{ font-size:10px; color:{ACCENT}; border:none;"
            " background:transparent; padding:0; }}"
            "QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._sub_lbl.clicked.connect(lambda: self._rerun_cb() if self._rerun_cb else None)
        self._body_layout.addWidget(
            self._grade_lbl, alignment=Qt.AlignmentFlag.AlignCenter
        )
        self._body_layout.addWidget(
            self._sub_lbl, alignment=Qt.AlignmentFlag.AlignCenter
        )
        self._body_layout.addStretch()

    def update_grade(self, grade: str, score: float = 0.0) -> None:
        letter = grade[:1].upper() if grade else "–"
        colour = getattr(_s, self._GRADE_COLOUR.get(letter, "TEXT_SECONDARY"))
        self._grade_lbl.setText(letter)
        _s.themed_ss(self._grade_lbl, lambda colour=colour: f"font-size:56px; font-weight:bold; color:{colour}; border:none;")
        self._grade_lbl.setToolTip(_s.safe_tooltip(
            self._GRADE_TIPS.get(letter, "Run a Network Grade scan to see your score (A–F).")
        ))
        if grade:
            self._sub_lbl.setText(f"Score: {score:.0f} / 100" if score else "")
            _s.themed_ss(self._sub_lbl, "QPushButton {{ font-size:10px; color:{TEXT_SECONDARY}; border:none;"
                " background:transparent; padding:0; }}"
                "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}")
            self._sub_lbl.setEnabled(False)
        else:
            self._sub_lbl.setText("Run Network Grade →")
            _s.themed_ss(self._sub_lbl, "QPushButton {{ font-size:10px; color:{ACCENT}; border:none;"
                " background:transparent; padding:0; }}"
                "QPushButton:hover {{ color:{ACCENT_DARK}; }}"
                "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
            self._sub_lbl.setEnabled(True)


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
        _s.themed_ss(self.bar, lambda: _s.qss_label(_s.TEXT_SECONDARY, 14, transparent=False))
        self.msg = QLabel("–")
        _s.themed_ss(self.msg, lambda: _s.qss_label(_s.TEXT_SECONDARY, 11, transparent=False))
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
            # Read BG_HOVER at hover time (not via themed_ss, which would register
            # this transient style for live re-application on a theme switch).
            # A hardcoded white-alpha tint is invisible on Arctic Clean's light surface.
            self.setStyleSheet(f"background: {_s.BG_HOVER}; border-radius:3px;")
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self.setStyleSheet("")
        super().leaveEvent(e)


class AlertFeedTile(_BaseTile):
    TILE_ID    = "alert_feed"
    TILE_LABEL = "Recent Alerts"
    TILE_ICON  = "◬"
    MIN_HEIGHT = 165
    _SEV_COLOUR = {"CRITICAL": "RED", "WARNING": "AMBER", "INFO": "ACCENT"}  # token names

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
                colour = getattr(_s, self._SEV_COLOUR.get(a.get("severity", "INFO"), "TEXT_SECONDARY"))
                text   = a.get("message", "")
                _s.themed_ss(row.bar, lambda colour=colour: f"font-size:14px; color:{colour}; border:none;")
                row.msg.setText(text[:55] + "…" if len(text) > 55 else text)
                _s.themed_ss(row.msg, lambda: _s.qss_label(_s.TEXT_PRIMARY, 11, transparent=False))
                row.set_active(True)
            else:
                _s.themed_ss(row.bar, lambda: _s.qss_label(_s.TEXT_SECONDARY, 14, transparent=False))
                row.msg.setText("–")
                _s.themed_ss(row.msg, lambda: _s.qss_label(_s.TEXT_SECONDARY, 11, transparent=False))
                row.set_active(False)

    def _build_detail(self) -> Optional[QWidget]:
        w = QWidget()
        w.setStyleSheet("background:transparent; border:none;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 2, 12, 4)
        lay.setSpacing(2)
        if not self._alerts:
            lbl = QLabel("No recent alerts")
            _s.themed_ss(lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 10, transparent=False))
            lay.addWidget(lbl)
        else:
            import datetime as _dt
            for a in self._alerts:
                ts = a.get("ts", 0)
                ts_str = _dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "–"
                sev = (a.get("severity") or "INFO").upper()
                color = getattr(_s, self._SEV_COLOUR.get(sev, "TEXT_SECONDARY"))
                row_lay = QHBoxLayout()
                row_lay.setSpacing(6)
                ts_lbl = QLabel(ts_str)
                ts_lbl.setFixedWidth(54)
                _s.themed_ss(ts_lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 9, transparent=False))
                msg_lbl = QLabel(a.get("message", "")[:45])
                _s.themed_ss(msg_lbl, lambda color=color: f"color:{color}; font-size:9px; border:none;")
                row_lay.addWidget(ts_lbl)
                row_lay.addWidget(msg_lbl, 1)
                lay.addLayout(row_lay)
        lay.addStretch()
        return w


class EventFeedTile(_BaseTile):
    """Live event feed: merges device-state events and fired alerts, newest first."""

    TILE_ID    = "event_feed"
    TILE_LABEL = "Live Event Feed"
    TILE_ICON  = "◉"
    MIN_HEIGHT = 165

    viewall_clicked = pyqtSignal()   # user clicked "View all → Network Logger"

    # Severity / event-type → colour
    _TYPE_COLOUR = {   # token names resolved live via getattr(_s, …)
        "APPEARED":    "GREEN",
        "DISAPPEARED": "RED",
        "CRITICAL":    "RED",
        "WARNING":     "AMBER",
        "INFO":        "ACCENT",
    }

    def _build_body(self) -> None:
        # Scrollable inner container for up to 20 rows
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Handle tint derives from TEXT_SECONDARY so it stays visible in both
        # themes; a hardcoded white-alpha handle vanished on Arctic Clean.
        _handle = _s.alpha(_s.TEXT_SECONDARY, 0x60)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: " + _handle
            + "; border-radius:2px; }"
        )
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._inner_lay = QVBoxLayout(inner)
        self._inner_lay.setContentsMargins(0, 0, 0, 0)
        self._inner_lay.setSpacing(2)
        self._inner_lay.addStretch()
        self._scroll.setWidget(inner)
        self._body_layout.setContentsMargins(8, 6, 8, 6)
        self._body_layout.addWidget(self._scroll, 1)

        self._event_labels: list[QLabel] = []

        # "View all" footer — styled as link button
        self._viewall_btn = QPushButton("View all →  Network Logger")
        self._viewall_btn.setFlat(True)
        self._viewall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._viewall_btn, "QPushButton {{ color:{ACCENT}; font-size:10px; border:none;"
            " background:transparent; text-align:left; padding:0; }}"
            "QPushButton:hover {{ text-decoration:underline; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._viewall_btn.clicked.connect(self.viewall_clicked)
        self._body_layout.addWidget(self._viewall_btn)

    def refresh(self, store: Optional[MetricStore] = None) -> None:
        s = store or self._store
        if s is None:
            return

        unified: list[tuple[int, str, str]] = []  # (ts, colour, text)

        # Device-state events
        try:
            for e in s.query_device_events(48.0):
                ip    = e.ip if hasattr(e, "ip") else e.get("ip", "")
                etype = e.event_type if hasattr(e, "event_type") else e.get("event_type", "")
                ts    = int(e.ts if hasattr(e, "ts") else e.get("ts", 0))
                colour = getattr(_s, self._TYPE_COLOUR.get(etype, "ACCENT"))
                label  = etype.replace("_", " ").lower()
                unified.append((ts, colour, f"[device]  {ip}  {label}"))
        except Exception:
            pass  # non-fatal

        # Fired alerts
        try:
            for a in s.get_recent_alerts(48.0, limit=40):
                ts     = int(a.get("ts", 0))
                sev    = (a.get("severity") or "INFO").upper()
                rtype  = a.get("rule_type") or a.get("rule_name") or "alert"
                host   = a.get("host") or ""
                colour = getattr(_s, self._TYPE_COLOUR.get(sev, "ACCENT"))
                msg    = f"{sev.lower()}  {rtype}"
                if host:
                    msg += f"  ({host})"
                unified.append((ts, colour, f"[alert]  {msg}"))
        except Exception:
            pass  # non-fatal

        # Sort newest-first, cap at 20
        unified.sort(key=lambda x: x[0], reverse=True)
        unified = unified[:20]

        # Rebuild rows
        for lbl in self._event_labels:
            self._inner_lay.removeWidget(lbl)
            lbl.deleteLater()
        self._event_labels.clear()

        if not unified:
            lbl = QLabel("No events in the last 48 hours.")
            _s.themed_ss(lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 11, transparent=False))
            self._inner_lay.insertWidget(0, lbl)
            self._event_labels.append(lbl)
            return

        for idx, (ts, colour, text) in enumerate(unified):
            t_str = (datetime.datetime.fromtimestamp(ts).strftime("%b %d %H:%M")
                     if ts else "")
            row_lbl = QLabel(f"{t_str}  {text}" if t_str else text)
            _s.themed_ss(row_lbl, lambda colour=colour: f"font-size:10px; color:{colour}; border:none; padding:1px 0;")
            row_lbl.setWordWrap(False)
            self._inner_lay.insertWidget(idx, row_lbl)
            self._event_labels.append(row_lbl)


class HaDevicesTile(_BaseTile):
    """Shows pinned Home Automation devices with live status dots."""

    TILE_ID    = "ha_devices"
    TILE_LABEL = "Home Automation"
    TILE_ICON  = "⌂"
    MIN_HEIGHT = 160

    def _build_body(self) -> None:
        self._rows: List[QLabel] = []
        self._placeholder = QLabel("No pinned HA devices yet")
        _s.themed_ss(self._placeholder, lambda: _s.qss_label(_s.TEXT_SECONDARY, 11, transparent=False))
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
                _s.themed_ss(label, lambda: _s.qss_label(_s.TEXT_PRIMARY, 11, transparent=False))
                label.setToolTip(_s.safe_tooltip(
                    f"IP: {kd.ip or '?'}  |  "
                    f"Room: {kd.room or '?'}  |  "
                    f"MAC: {kd.mac}"
                ))
                self._rows.append(label)
                # Insert before stretch (last item)
                self._body_layout.insertWidget(
                    self._body_layout.count() - 1, label
                )
        except Exception:
            pass  # non-fatal

    def update_ha_states(self, states: dict) -> None:
        """states: {ip: UP/DOWN/DEGRADED/UNKNOWN} — called from dashboard.

        We refresh on next store poll; live update done through normal refresh cycle.
        """


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
        _s.themed_ss(up_lbl, "font-size:9px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;")
        self._up_val = QLabel("—")
        _s.themed_ss(self._up_val, lambda CHART_UP=CHART_UP: f"font-size:20px; font-weight:bold; color:{CHART_UP}; border:none;")
        self._up_unit = QLabel("Mbps")
        _s.themed_ss(self._up_unit, lambda: _s.qss_label(_s.TEXT_SECONDARY, 10, transparent=False))
        up_col.addWidget(up_lbl)
        up_col.addWidget(self._up_val)
        up_col.addWidget(self._up_unit)

        # Download
        dn_col = QVBoxLayout()
        dn_col.setSpacing(2)
        dn_lbl = QLabel("↓ DOWNLOAD")
        _s.themed_ss(dn_lbl, "font-size:9px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;")
        self._dn_val = QLabel("—")
        _s.themed_ss(self._dn_val, lambda CHART_DOWN=CHART_DOWN: f"font-size:20px; font-weight:bold; color:{CHART_DOWN}; border:none;")
        self._dn_unit = QLabel("Mbps")
        _s.themed_ss(self._dn_unit, lambda: _s.qss_label(_s.TEXT_SECONDARY, 10, transparent=False))
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
            pass  # non-fatal

    def _stop_worker(self) -> None:
        w = getattr(self, "_worker", None)
        self._worker = None            # null first so a re-entrant showEvent starts one worker
        _detach_poller(w)

    def _on_stats(self, stats: dict) -> None:
        up   = sum(d["up_mbps"]   for d in stats.values())
        down = sum(d["down_mbps"] for d in stats.values())
        self._up_val.setText(f"{up:.2f}")
        self._dn_val.setText(f"{down:.2f}")

    def refresh(self, store=None) -> None:
        pass  # live data — no store needed


# ── Non-blocking poller teardown ───────────────────────────────────────────────

def _detach_poller(worker) -> None:
    """Non-blocking teardown for a tile's background poller (RULE-4).

    Stop it, drop its data-signal connections so a late emission can't touch the
    (persistent) tile, and schedule self-deletion once run() returns. Returns
    immediately — never wait() on the UI thread. This is what keeps navigating
    to/from the Dashboard from freezing: the page switch delivers hideEvent to
    each live tile, and a blocking wait() here would stall the crossfade.

    The tile KEEPS the worker's Qt parent on purpose: with a parent the C++
    object outlives the nulled Python attribute, so PyQt won't garbage-collect
    the wrapper and destroy a still-running QThread ("QThread: Destroyed while
    thread is still running" -> abort).
    """
    if worker is None:
        return
    try:
        worker.stop()
    except Exception:
        pass  # non-fatal — worker may already be stopping
    try:
        worker.disconnect()            # drop stats_ready/result -> tile slot
    except (TypeError, RuntimeError):
        pass  # non-fatal — nothing was connected
    try:
        if worker.isRunning():
            worker.finished.connect(worker.deleteLater)  # frees after run() returns
        else:
            worker.deleteLater()
    except Exception:
        pass  # non-fatal — worker already gone


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
            # Sleep the interval in ~100 ms chunks so stop() is honoured promptly
            # (an in-flight getaddrinfo can't be interrupted, but teardown no
            # longer wait()s on this thread, so that no longer matters).
            deadline = time.monotonic() + self._interval
            while not self._stop and time.monotonic() < deadline:
                time.sleep(0.1)


class DnsStabilityTile(_BaseTile):
    TILE_ID    = "dns_stability"
    TILE_LABEL = "DNS Stability"
    TILE_ICON  = "◎"
    MIN_HEIGHT = 140

    def _build_body(self) -> None:
        self._lat_lbl = QLabel("—")
        _s.themed_ss(self._lat_lbl, "font-size:32px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")
        self._status_lbl = QLabel("Measuring…")
        _s.themed_ss(self._status_lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 11, transparent=False))
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
        self._worker = None            # null first so a re-entrant showEvent starts one worker
        _detach_poller(w)
        super().hideEvent(event)

    def _on_result(self, ms: float) -> None:
        if ms < 0:
            self._fail_count += 1
            self._lat_lbl.setText("FAIL")
            _s.themed_ss(self._lat_lbl, "font-size:32px; font-weight:bold; color:{RED}; border:none;")
            self._set_health(_s.RED)
        else:
            self._readings.append(ms)
            self._readings = self._readings[-5:]
            self._fail_count = 0
            colour = _s.GREEN if ms < 50 else _s.AMBER if ms < 200 else _s.RED
            self._lat_lbl.setText(f"{ms:.0f} ms")
            _s.themed_ss(self._lat_lbl, lambda colour=colour: f"font-size:32px; font-weight:bold; color:{colour}; border:none;")
            self._set_health(colour)
        avg = (sum(self._readings) / len(self._readings)) if self._readings else 0
        if self._fail_count:
            self._status_lbl.setText(f"{self._fail_count} failure(s) — resolver unreachable")
            _s.themed_ss(self._status_lbl, lambda: _s.qss_label(_s.RED, 11, transparent=False))
        elif self._readings:
            self._status_lbl.setText(f"Avg {avg:.0f} ms over last {len(self._readings)} probe(s)")
            _s.themed_ss(self._status_lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 11, transparent=False))

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

    clicked = pyqtSignal()  # emitted when the tile is clicked and data is present
    _data_active: bool = False

    def _build_body(self) -> None:
        # Top row: network type badge + RSRP value
        top = QHBoxLayout()
        top.setSpacing(10)

        self._type_lbl = QLabel("—")
        _s.themed_ss(self._type_lbl, "font-size:11px; font-weight:bold; color:{TEXT_SECONDARY};"
            " background:{BG_HOVER}; border:1px solid {BORDER};"
            " border-radius:3px; padding:1px 8px; border:none;")

        self._rsrp_lbl = QLabel("—")
        _s.themed_ss(self._rsrp_lbl, "font-size:28px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")

        self._qual_lbl = QLabel("")
        _s.themed_ss(self._qual_lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 11, transparent=False))

        top.addWidget(self._type_lbl)
        top.addWidget(self._rsrp_lbl)
        top.addStretch()

        # Bottom row: band + bars
        bot = QHBoxLayout()
        bot.setSpacing(16)

        self._band_lbl = QLabel("—")
        _s.themed_ss(self._band_lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 11, transparent=False))
        self._bars_lbl = QLabel("")
        _s.themed_ss(self._bars_lbl, lambda: _s.qss_label(_s.TEXT_SECONDARY, 11, transparent=False))
        bot.addWidget(self._band_lbl)
        bot.addWidget(self._bars_lbl)
        bot.addStretch()

        self._body_layout.addLayout(top)
        self._body_layout.addWidget(self._qual_lbl)
        self._body_layout.addLayout(bot)
        self._body_layout.addStretch()

        # Placeholder hint
        self._hint_lbl = QLabel("Import a modem plugin via Hardware →")
        _s.themed_ss(self._hint_lbl, "font-size:10px; color:{TEXT_SECONDARY}; border:none; font-style:italic;")
        self._body_layout.addWidget(self._hint_lbl)

    def mousePressEvent(self, event) -> None:
        if self._data_active and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    @pyqtSlot(dict)
    def on_modem_signal(self, data: dict) -> None:
        """Receive a ZteSignalData dict from the dashboard."""
        self._hint_lbl.hide()
        if not self._data_active:
            self._data_active = True
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

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
            _s.themed_ss(self._rsrp_lbl, lambda colour=colour: f"font-size:28px; font-weight:bold; color:{colour}; border:none;")
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
        return _s.GREEN
    if rsrp >= -90:
        return _s.AMBER
    if rsrp >= -100:
        return _s.AMBER
    return _s.RED


# ── Top Talkers tile (OVERVIEW-2) ─────────────────────────────────────────────

class TopTalkersTile(_BaseTile):
    """
    Shows the top-3 network interfaces by cumulative session bandwidth.
    Accumulates IfaceBwPoller stats while visible; empty state until first sample.
    """
    TILE_ID    = "top_talkers"
    TILE_LABEL = "Top Talkers"
    TILE_ICON  = "▲"
    _NAV_LABEL = "Live Bandwidth"

    def _build_body(self) -> None:
        self._totals: dict = {}   # iface -> {"down_mb": float, "up_mb": float}
        self._worker = None
        self._row_widgets: list = []

        self._empty_lbl = QLabel("Start Live Bandwidth to see top talkers.")
        self._empty_lbl.setWordWrap(True)
        _s.themed_ss(self._empty_lbl, "font-size:11px; color:{TEXT_MUTED}; border:none; font-style:italic;")
        self._body_layout.addWidget(self._empty_lbl)
        self._body_layout.addStretch()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._worker is None:
            self._start_worker()

    def hideEvent(self, event) -> None:
        self._stop_worker()
        super().hideEvent(event)

    def _start_worker(self) -> None:
        try:
            from workers.iface_bw_worker import IfaceBwPoller
            self._worker = IfaceBwPoller(interval_s=2.0, parent=self)
            self._worker.stats_ready.connect(self._on_stats)
            self._worker.start()
        except Exception:
            pass  # non-fatal

    def _stop_worker(self) -> None:
        w = getattr(self, "_worker", None)
        self._worker = None            # null first so a re-entrant showEvent starts one worker
        _detach_poller(w)

    def _on_stats(self, stats: dict) -> None:
        for iface, d in stats.items():
            if iface not in self._totals:
                self._totals[iface] = {"down_mb": 0.0, "up_mb": 0.0}
            self._totals[iface]["down_mb"] += d.get("down_mbps", 0.0) * 2.0 / 8.0
            self._totals[iface]["up_mb"]   += d.get("up_mbps",   0.0) * 2.0 / 8.0
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        ranked = sorted(
            self._totals.items(),
            key=lambda x: x[1]["down_mb"] + x[1]["up_mb"],
            reverse=True,
        )[:3]

        for w in self._row_widgets:
            w.deleteLater()
        self._row_widgets.clear()

        if not ranked:
            self._empty_lbl.show()
            return
        self._empty_lbl.hide()

        for iface, d in ranked:
            label_text = (
                f"{iface[:18]}  ↓{d['down_mb']:.1f} MB  ↑{d['up_mb']:.1f} MB"
            )
            row_lbl = QLabel(label_text)
            _s.themed_ss(row_lbl, "font-size:10px; color:{TEXT_PRIMARY}; border:none; border-bottom:1px solid {BORDER};"
                " padding:2px 0;")
            self._body_layout.insertWidget(
                self._body_layout.count() - 1, row_lbl
            )
            self._row_widgets.append(row_lbl)
        self._set_health(_s.ACCENT)

    def refresh(self, store=None) -> None:
        pass  # live accumulation only


# ── Recent Events tile (OVERVIEW-3) ──────────────────────────────────────────

class RecentEventsTile(_BaseTile):
    """
    Shows the 5 most recent device-state events from MetricStore.
    Clicking the tile navigates to the Timeline page.
    """
    TILE_ID    = "recent_events"
    TILE_LABEL = "Recent Events"
    TILE_ICON  = "◷"
    _NAV_LABEL = "Network Timeline"

    _EVENT_ICONS = {   # (glyph, token-name resolved live via getattr(_s, …))
        "NEW":     ("◆", "ACCENT"),
        "GONE":    ("◇", "AMBER"),
        "ROGUE":   ("▲", "RED"),
        "CHANGE":  ("●", "AMBER"),
        "UP":      ("●", "GREEN"),
        "DOWN":    ("●", "RED"),
    }

    def _build_body(self) -> None:
        self._row_labels: list = []
        self._empty_lbl = QLabel("No device events in the last 24 h.")
        _s.themed_ss(self._empty_lbl, "font-size:11px; color:{TEXT_MUTED}; border:none; font-style:italic;")
        self._body_layout.addWidget(self._empty_lbl)
        self._body_layout.addStretch()

        self._link_btn = QPushButton("View all →")
        self._link_btn.setFlat(True)
        self._link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._link_btn, "QPushButton {{ color:{ACCENT}; font-size:10px; border:none;"
            " background:transparent; text-align:left; padding:0; }}"
            "QPushButton:hover {{ text-decoration:underline; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._link_btn.clicked.connect(lambda: self.navigate_requested.emit(L.NETWORK_TIMELINE))
        self._link_btn.hide()
        self._body_layout.addWidget(self._link_btn)

    def mousePressEvent(self, event) -> None:
        if (not self._edit_mode
                and event.button() == Qt.MouseButton.LeftButton
                and self._row_labels):
            self.navigate_requested.emit(L.NETWORK_TIMELINE)
        else:
            super().mousePressEvent(event)

    def refresh(self, store=None) -> None:
        s = store or self._store
        if s is None:
            return
        import time as _t
        try:
            events = s.query_device_events(hours=24.0)[:5]
        except Exception:
            return

        for w in self._row_labels:
            w.deleteLater()
        self._row_labels.clear()

        if not events:
            self._empty_lbl.show()
            self._link_btn.hide()
            return
        self._empty_lbl.hide()
        self._link_btn.show()

        now = _t.time()
        for evt in events:
            icon, color = self._EVENT_ICONS.get(
                evt.event_type.upper(), ("●", "TEXT_SECONDARY")
            )
            color = getattr(_s, color)
            delta = int(now - evt.ts)
            if delta < 60:
                elapsed = "just now"
            elif delta < 3600:
                elapsed = f"{delta // 60} min ago"
            else:
                elapsed = f"{delta // 3600} h ago"

            ip_short = (evt.ip or "?")[:15]
            row = QHBoxLayout()
            row.setSpacing(4)
            icon_lbl = QLabel(icon)
            icon_lbl.setFixedWidth(12)
            _s.themed_ss(icon_lbl, lambda color=color: f"color:{color}; font-size:10px; border:none;")
            desc_lbl = QLabel(f"{ip_short}  {evt.event_type}")
            _s.themed_ss(desc_lbl, lambda: _s.qss_label(_s.TEXT_PRIMARY, 10, transparent=False))
            time_lbl = QLabel(elapsed)
            _s.themed_ss(time_lbl, lambda: _s.qss_label(_s.TEXT_MUTED, 9, transparent=False))
            row.addWidget(icon_lbl)
            row.addWidget(desc_lbl, 1)
            row.addWidget(time_lbl)

            container = QWidget()
            container.setStyleSheet("background:transparent; border:none;")
            container.setLayout(row)
            self._body_layout.insertWidget(
                self._body_layout.count() - 2, container
            )
            self._row_labels.append(container)

        self._set_health(_s.GREEN if events else _s.BORDER)
        self.mark_scanned()


# ── Trend Status tile (OVERVIEW-4) ────────────────────────────────────────────

class TrendStatusTile(_BaseTile):
    """
    Shows a summary of the latest TrendReport: X critical · Y warning · Z clean.
    Data is pushed by OverviewPage.on_trend_result().
    """
    TILE_ID    = "trend_status"
    TILE_LABEL = "Trend Forecast"
    TILE_ICON  = "↗"
    _NAV_LABEL = "Trend Forecasts"

    def _build_body(self) -> None:
        self._summary_lbl = QLabel("No trend data yet.")
        _s.themed_ss(self._summary_lbl, "font-size:11px; color:{TEXT_MUTED}; border:none; font-style:italic;")
        self._body_layout.addWidget(self._summary_lbl)

        row = QHBoxLayout()
        row.setSpacing(20)

        crit_col = QVBoxLayout()
        crit_col.setSpacing(0)
        self._crit_num = QLabel("–")
        _s.themed_ss(self._crit_num, "font-size:28px; font-weight:bold; color:{RED}; border:none;")
        self._crit_sub = QLabel("Critical")
        _s.themed_ss(self._crit_sub, "font-size:9px; font-weight:bold; color:{RED}; border:none;")
        crit_col.addWidget(self._crit_num)
        crit_col.addWidget(self._crit_sub)

        warn_col = QVBoxLayout()
        warn_col.setSpacing(0)
        self._warn_num = QLabel("–")
        _s.themed_ss(self._warn_num, "font-size:28px; font-weight:bold; color:{AMBER}; border:none;")
        self._warn_sub = QLabel("Warning")
        _s.themed_ss(self._warn_sub, "font-size:9px; font-weight:bold; color:{AMBER}; border:none;")
        warn_col.addWidget(self._warn_num)
        warn_col.addWidget(self._warn_sub)

        clean_col = QVBoxLayout()
        clean_col.setSpacing(0)
        self._clean_num = QLabel("–")
        _s.themed_ss(self._clean_num, "font-size:28px; font-weight:bold; color:{GREEN}; border:none;")
        self._clean_sub = QLabel("Clean")
        _s.themed_ss(self._clean_sub, "font-size:9px; font-weight:bold; color:{GREEN}; border:none;")
        clean_col.addWidget(self._clean_num)
        clean_col.addWidget(self._clean_sub)

        row.addLayout(crit_col)
        row.addLayout(warn_col)
        row.addLayout(clean_col)
        row.addStretch()
        self._body_layout.addLayout(row)
        self._body_layout.addStretch()

        # Hide number columns until data arrives
        self._numbers_row_widget = None

    def on_trend_result(self, report) -> None:
        """Receive a TrendReport from the dashboard."""
        self._summary_lbl.hide()
        n_crit  = len(report.critical)
        n_warn  = len(report.warnings)
        n_clean = len([r for r in report.results
                       if r.severity not in ("CRITICAL", "WARNING")])
        self._crit_num.setText(str(n_crit))
        self._warn_num.setText(str(n_warn))
        self._clean_num.setText(str(n_clean))
        if n_crit:
            self._set_health(_s.RED)
        elif n_warn:
            self._set_health(_s.AMBER)
        else:
            self._set_health(_s.GREEN)
        self.mark_scanned()

    def refresh(self, store=None) -> None:
        pass  # pushed data only


# ── Security scan panel ───────────────────────────────────────────────────────

class _SecurityScanPanel(QWidget):
    """Collapsible panel below the tile grid for launching security tools."""

    run_clicked = pyqtSignal(list)   # emits list of selected nav-label strings

    # (nav_label, display_name, checked_by_default, is_active_probe, requirement)
    # requirement: "" = none | "admin" = needs Run as Administrator | "Npcap" = needs Npcap driver
    _TOOLS = [
        ("Threat Intel",         "Threat Intel",        True,  False, ""),
        ("TLS & Exposure",       "TLS & Exposure",      True,  False, ""),
        ("Device Risk Score",    "Device Risk Score",   True,  False, ""),
        ("CVE Lookup",           "CVE Lookup",          True,  False, ""),
        ("Port Scan (TCP)",      "Port Scan (TCP)",     False, True,  "admin"),
        ("Exposed to Internet",  "Exposed to Internet", False, True,  ""),
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
        _s.themed_ss(self._toggle_btn, "QPushButton {{ background:{BG_CARD}; color:{RED};"
            " border:1px solid {BORDER}; border-left:3px solid {RED};"
            " border-radius:0px; text-align:left;"
            " padding:0 12px; font-size:12px; font-weight:bold; }}"
            "QPushButton:hover {{ background:{BG_HOVER}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        self._toggle_btn.clicked.connect(self._toggle)
        outer.addWidget(self._toggle_btn)

        # Body (expanded by default)
        self._body = QFrame()
        _s.themed_ss(self._body, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-top:none; border-bottom-left-radius:4px;"
            " border-bottom-right-radius:4px; }}")
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(12, 10, 12, 12)
        body_lay.setSpacing(8)

        # Warning strip
        warn_frame = QFrame()
        _s.themed_ss(warn_frame, "QFrame {{ background:transparent; border:1px solid {AMBER}; border-radius:3px; }}")
        warn_inner = QVBoxLayout(warn_frame)
        warn_inner.setContentsMargins(8, 5, 8, 5)
        warn_inner.setSpacing(3)
        warn_lbl = QLabel(
            "⚠  These tools actively probe devices on your network. "
            "Only use on networks you own or have permission to test."
        )
        warn_lbl.setWordWrap(True)
        _s.themed_ss(warn_lbl, "font-size:10px; color:{AMBER}; border:none; background:transparent;")
        legend_lbl = QLabel(
            f"<span style='background:{_s.AUDIT_RED}; color:{_s.WHITE}; border-radius:3px;"
            f" padding:0 3px; font-size:9px; font-weight:bold;'>admin</span>"
            f" &nbsp;= Run as Administrator required&nbsp;&nbsp;&nbsp;"
            f"<span style='background:{_s.AMBER}; color:{_s.WHITE}; border-radius:3px;"
            f" padding:0 3px; font-size:9px; font-weight:bold;'>Npcap</span>"
            f" &nbsp;= Npcap driver required"
        )
        legend_lbl.setTextFormat(Qt.TextFormat.RichText)
        _s.themed_ss(legend_lbl, "font-size:10px; color:{TEXT_SECONDARY}; border:none; background:transparent;")
        warn_inner.addWidget(warn_lbl)
        warn_inner.addWidget(legend_lbl)
        body_lay.addWidget(warn_frame)

        # Tool checkboxes — 2 column grid
        chk_grid = QGridLayout()
        chk_grid.setSpacing(4)
        chk_grid.setContentsMargins(0, 0, 0, 0)
        for i, (nav_lbl, display, checked, is_active, req) in enumerate(self._TOOLS):
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(4)
            chk = QCheckBox(display)
            chk.setChecked(checked)
            colour = _s.AMBER if is_active else _s.TEXT_PRIMARY
            _s.themed_ss(chk, lambda colour=colour: f"QCheckBox {{ font-size:11px; color:{colour}; background:transparent; spacing:5px; }}"
                f"QCheckBox::indicator {{ width:13px; height:13px; }}")
            chk.stateChanged.connect(self._on_check_changed)
            self._checkboxes[nav_lbl] = chk
            row_lay.addWidget(chk)
            if req:
                badge_color = _s.AUDIT_RED if req == "admin" else _s.AMBER
                badge_lbl = QLabel(req)
                _s.themed_ss(badge_lbl, lambda badge_color=badge_color: f"font-size:8px; font-weight:bold; color:{_s.WHITE};"
                    f" background:{badge_color}; border-radius:3px; padding:0 3px;")
                row_lay.addWidget(badge_lbl)
            row_lay.addStretch()
            chk_grid.addWidget(row_w, i // 2, i % 2)
        body_lay.addLayout(chk_grid)

        # Run row
        run_row = QHBoxLayout()
        run_row.setSpacing(8)
        self._status_lbl = QLabel("")
        _s.themed_ss(self._status_lbl, lambda: _s.qss_muted_label(10))
        self._run_btn = QPushButton("Run Selected")
        self._run_btn.setFixedHeight(28)
        self._run_btn.setMinimumWidth(110)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._run_btn, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " font-size:11px; font-weight:bold; padding:0 14px; border-radius:4px; }}"
            "QPushButton:hover {{ background:{ACCENT_LITE}; }}"
            "QPushButton:disabled {{ background:{TEXT_SECONDARY}; color:{WHITE}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
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
        _s.themed_ss(self._toggle_btn, "QPushButton {{ background:{BG_CARD}; color:{RED};"
            " border:1px solid {BORDER}; border-left:3px solid {RED};"
            " border-radius:0px; text-align:left;"
            " padding:0 12px; font-size:12px; font-weight:bold; }}"
            "QPushButton:hover {{ background:{BG_HOVER}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")

    def _on_check_changed(self) -> None:
        any_checked = any(c.isChecked() for c in self._checkboxes.values())
        self._run_btn.setEnabled(any_checked)

    def _on_run(self) -> None:
        selected = [lbl for lbl, chk in self._checkboxes.items() if chk.isChecked()]
        if selected:
            self._status_lbl.setText(f"Opening {selected[0]}…")
            self.run_clicked.emit(selected)


# ── _ScanStatusTile ───────────────────────────────────────────────────────────

class _ScanStatusTile(_BaseTile):
    """Compact 5-row scan status tile: dot + category + age for each scan type."""

    TILE_ID    = "scan_status"
    TILE_LABEL = "Scan Status"
    TILE_ICON  = "◉"

    def _build_body(self) -> None:
        _ROWS: List[tuple] = [
            ("Device Scan",    "Devices",             "Devices"),
            ("Security Audit", "_security_aggregate", "Security Overview"),
            ("Speed Test",     "Speed Test",          "Speed Test"),
            ("Service Health", "Service Diagnostics", "Service Diagnostics"),
            ("Network Logger", "_logger",             "Network Logger"),
        ]
        self._sc_dots: List[QLabel] = []
        self._sc_ages: List[QLabel] = []
        self._sc_keys: List[str]    = [r[1] for r in _ROWS]

        from ui.tabs_helpers import _scan_age_str as _sas
        self._scan_age_str = _sas

        for display, _reg_key, _nav in _ROWS:
            row = QHBoxLayout()
            row.setSpacing(6)
            row.setContentsMargins(0, 2, 0, 2)

            dot = QLabel("●")
            dot.setFixedWidth(12)
            _s.themed_ss(dot, lambda: _s.qss_label(_s.TEXT_MUTED, 9, transparent=False))

            nm = QLabel(display)
            nm.setFixedWidth(102)
            _s.themed_ss(nm, lambda: _s.qss_label(_s.TEXT_PRIMARY, 10, transparent=False))

            age = QLabel("Never")
            _s.themed_ss(age, lambda: _s.qss_label(_s.TEXT_MUTED, 9, transparent=False))

            row.addWidget(dot)
            row.addWidget(nm)
            row.addWidget(age, 1)
            self._body_layout.addLayout(row)

            self._sc_dots.append(dot)
            self._sc_ages.append(age)

        self._body_layout.addStretch()

    def refresh(self, store=None) -> None:
        if not hasattr(self, "_sc_dots"):
            return
        import json as _j
        from PyQt6.QtCore import QSettings
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            registry: dict = _j.loads(qs.value("scan_registry/state", "{}", type=str))
        except Exception:
            registry = {}

        _SEC = [
            "Port Scan (TCP)", "Port Scan (UDP)", "CVE Lookup", "OS Detection",
            "Login Test", "Threat Intel", "TLS & Exposure",
            "Exposed to Internet", "Full Device Discovery",
        ]
        _sec_ts, _sec_state = 0.0, "never"
        for lbl in _SEC:
            e = registry.get(lbl, {})
            st, ts = e.get("state", "never"), e.get("ts", 0.0) or 0.0
            if st == "fresh" and (_sec_state != "fresh" or ts > _sec_ts):
                _sec_ts, _sec_state = ts, "fresh"
            elif st == "stale" and _sec_state == "never":
                _sec_ts, _sec_state = ts, "stale"

        _COLOR = {
            "fresh": _s.GREEN, "stale": _s.AMBER,
            "running": _s.ACCENT, "error": _s.RED, "never": _s.TEXT_MUTED,
        }
        for i, reg_key in enumerate(self._sc_keys):
            if reg_key == "_security_aggregate":
                state, ts = _sec_state, _sec_ts
            elif reg_key == "_logger":
                # Network Logger is a continuous monitor, not a one-shot scan —
                # "running" is a genuine live state here, not an interrupted
                # scan, so (unlike the generic branch below) it must not be
                # downgraded to "never".
                e = registry.get("Network Logger", {})
                state = e.get("state", "never")
                ts = e.get("ts", 0.0) or 0.0
            else:
                e = registry.get(reg_key, {})
                state, ts = e.get("state", "never"), e.get("ts", 0.0) or 0.0
                if state == "running":
                    state = "never"  # scan interrupted before startup normalization ran
            color = _COLOR.get(state, _s.TEXT_MUTED)
            _s.themed_ss(self._sc_dots[i], lambda color=color: f"font-size:9px; color:{color}; border:none;")
            self._sc_ages[i].setText(self._scan_age_str(ts) if ts else "Never")


# ── Tile registry & defaults ──────────────────────────────────────────────────

_TILE_CLASSES: Dict[str, type] = {
    cls.TILE_ID: cls for cls in [
        DeviceCountTile, ServiceStatusTile, TlsStatusTile,
        RttSummaryTile, NetworkGradeTile, AlertFeedTile, EventFeedTile,
        HaDevicesTile, LiveBandwidthTile, DnsStabilityTile,
        ModemSignalTile, TopTalkersTile, RecentEventsTile, TrendStatusTile,
        _ScanStatusTile,
    ]
}

# All tiles shown by default — each has a graceful empty state when data is absent.
_DEFAULT_ORDER: List[str] = [
    "scan_status",
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
    "top_talkers",
    "recent_events",
    "trend_status",
]

# Import-time integrity check: every tile in the default order must be registered.
# Also reads _LAYOUT_VER so both exports are recognised as used by static analysis.
assert all(t in _TILE_CLASSES for t in _DEFAULT_ORDER), (
    f"_DEFAULT_ORDER (layout v{_LAYOUT_VER}) contains unregistered tile IDs: "
    f"{[t for t in _DEFAULT_ORDER if t not in _TILE_CLASSES]}"
)


# ── Overview page ─────────────────────────────────────────────────────────────

