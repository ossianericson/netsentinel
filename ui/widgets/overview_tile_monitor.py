"""
overview_tile_monitor.py — Monitoring-domain tile classes for the Overview dashboard.

Extracted from ui/widgets/overview_tile.py (Sprint 13) to keep that file within budget.
overview_tile.py imports all classes back from here.
"""
from __future__ import annotations

import datetime
from typing import Callable, List, Optional

from PyQt6.QtCore import Qt, QSettings, QSize, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QCursor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from modules.metric_store import MetricStore
from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE, AMBER,
    BG_CARD, BG_DARK, BG_HOVER, BORDER,
    CARD_HDR_BORDER, CHART_DOWN, CHART_UP,
    GREEN, PRO_WARN_BG, RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)

# Base class and animation helper live in overview_tile.py
from ui.widgets.overview_tile import _BaseTile, _AnimatedNumberLabel

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
            f"font-size:20px; font-weight:bold; color:{CHART_UP}; border:none;"
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
            f"font-size:20px; font-weight:bold; color:{CHART_DOWN}; border:none;"
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
            pass  # non-fatal

    def _stop_worker(self) -> None:
        w = getattr(self, "_worker", None)
        if w is not None:
            try:
                w.stop()
                w.quit()
                w.wait(2000)
            except Exception:
                pass  # non-fatal
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

    clicked = pyqtSignal()  # emitted when the tile is clicked and data is present
    _data_active: bool = False

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
        self._hint_lbl = QLabel("Import a modem plugin via Hardware →")
        self._hint_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; border:none; font-style:italic;"
        )
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
        self._empty_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_MUTED}; border:none; font-style:italic;"
        )
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
        if w is not None:
            try:
                w.stop(); w.quit(); w.wait(2000)
            except Exception:
                pass  # non-fatal
            self._worker = None

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
            total_mb = d["down_mb"] + d["up_mb"]
            label_text = (
                f"{iface[:18]}  ↓{d['down_mb']:.1f} MB  ↑{d['up_mb']:.1f} MB"
            )
            row_lbl = QLabel(label_text)
            row_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_PRIMARY}; border:none; border-bottom:1px solid {BORDER};"
                f" padding:2px 0;"
            )
            self._body_layout.insertWidget(
                self._body_layout.count() - 1, row_lbl
            )
            self._row_widgets.append(row_lbl)
        self._set_health(ACCENT)

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
    _NAV_LABEL = "Timeline"

    _EVENT_ICONS = {
        "NEW":     ("◆", ACCENT),
        "GONE":    ("◇", AMBER),
        "ROGUE":   ("▲", RED),
        "CHANGE":  ("●", AMBER),
        "UP":      ("●", GREEN),
        "DOWN":    ("●", RED),
    }

    def _build_body(self) -> None:
        self._row_labels: list = []
        self._empty_lbl = QLabel("No device events in the last 24 h.")
        self._empty_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_MUTED}; border:none; font-style:italic;"
        )
        self._body_layout.addWidget(self._empty_lbl)
        self._body_layout.addStretch()

        self._link_btn = QPushButton("View all →")
        self._link_btn.setFlat(True)
        self._link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._link_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:10px; border:none;"
            f" background:transparent; text-align:left; padding:0; }}"
            f"QPushButton:hover {{ text-decoration:underline; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._link_btn.clicked.connect(lambda: self.navigate_requested.emit("Timeline"))
        self._link_btn.hide()
        self._body_layout.addWidget(self._link_btn)

    def mousePressEvent(self, event) -> None:
        if (not self._edit_mode
                and event.button() == Qt.MouseButton.LeftButton
                and self._row_labels):
            self.navigate_requested.emit("Timeline")
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
                evt.event_type.upper(), ("●", TEXT_SECONDARY)
            )
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
            icon_lbl.setStyleSheet(f"color:{color}; font-size:10px; border:none;")
            desc_lbl = QLabel(f"{ip_short}  {evt.event_type}")
            desc_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_PRIMARY}; border:none;")
            time_lbl = QLabel(elapsed)
            time_lbl.setStyleSheet(f"font-size:9px; color:{TEXT_MUTED}; border:none;")
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

        self._set_health(GREEN if events else BORDER)
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
        self._summary_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_MUTED}; border:none; font-style:italic;"
        )
        self._body_layout.addWidget(self._summary_lbl)

        row = QHBoxLayout()
        row.setSpacing(20)

        crit_col = QVBoxLayout()
        crit_col.setSpacing(0)
        self._crit_num = QLabel("–")
        self._crit_num.setStyleSheet(
            f"font-size:28px; font-weight:bold; color:{RED}; border:none;"
        )
        self._crit_sub = QLabel("Critical")
        self._crit_sub.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{RED}; border:none;"
        )
        crit_col.addWidget(self._crit_num)
        crit_col.addWidget(self._crit_sub)

        warn_col = QVBoxLayout()
        warn_col.setSpacing(0)
        self._warn_num = QLabel("–")
        self._warn_num.setStyleSheet(
            f"font-size:28px; font-weight:bold; color:{AMBER}; border:none;"
        )
        self._warn_sub = QLabel("Warning")
        self._warn_sub.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{AMBER}; border:none;"
        )
        warn_col.addWidget(self._warn_num)
        warn_col.addWidget(self._warn_sub)

        clean_col = QVBoxLayout()
        clean_col.setSpacing(0)
        self._clean_num = QLabel("–")
        self._clean_num.setStyleSheet(
            f"font-size:28px; font-weight:bold; color:{GREEN}; border:none;"
        )
        self._clean_sub = QLabel("Clean")
        self._clean_sub.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{GREEN}; border:none;"
        )
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
            self._set_health(RED)
        elif n_warn:
            self._set_health(AMBER)
        else:
            self._set_health(GREEN)
        self.mark_scanned()

    def refresh(self, store=None) -> None:
        pass  # pushed data only


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
        ("Port Scan (TCP)",      "Port Scan (TCP) ⚠",   False, True),
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
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
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
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" font-size:11px; font-weight:bold; padding:0 14px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; }}"
            f"QPushButton:disabled {{ background:{TEXT_SECONDARY}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
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
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
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
