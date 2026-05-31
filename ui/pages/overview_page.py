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

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSettings, QSize, Qt, QThread, QTimer, QVariantAnimation, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QCursor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QMenu,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from modules.metric_store import MetricStore
from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE, AMBER,
    BG_CARD, BG_DARK, BG_HOVER, BORDER,
    CRITICAL, GREEN, RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from ui.widgets.overview_tile import (
    _MIME_TYPE, _COLS, _SETTINGS_KEY, _TILE_HEIGHT, _EXPANDED_HEIGHT, _LAYOUT_VER,
    _AnimatedNumberLabel, _BaseTile,
    DeviceCountTile, ServiceStatusTile, TlsStatusTile, RttSummaryTile,
    NetworkGradeTile, AlertFeedTile, EventFeedTile, HaDevicesTile,
    LiveBandwidthTile, DnsStabilityTile, ModemSignalTile, TopTalkersTile,
    RecentEventsTile, TrendStatusTile, _DnsPoller, _SecurityScanPanel,
    _TILE_CLASSES, _DEFAULT_ORDER,
)


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
    #: Emitted when the Modem Signal tile is clicked (modem plugin active).
    modem_tile_clicked = pyqtSignal()
    #: Emitted when the user requests a Quick Network Assessment (M1–M5 bundle).
    scan_requested = pyqtSignal()
    #: Emitted when the user clicks "▣ Report" — run all modules + open HTML report.
    report_requested = pyqtSignal()
    #: Emitted when the user clicks "⬇ Export…" — export last scan results.
    export_requested = pyqtSignal()
    #: Emitted when the user requests security tool runs; carries list of nav labels.
    security_scan_requested = pyqtSignal(list)

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store      = store
        self._edit_mode  = False
        self._scanning   = False
        self._has_results = False
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
        # OVERVIEW-5: refresh all tile age labels every 60 s
        self._age_timer = QTimer(self)
        self._age_timer.setInterval(60_000)
        self._age_timer.timeout.connect(self._refresh_tile_ages)
        self._age_timer.start()

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
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
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
            f"QPushButton:checked {{ background:{ACCENT}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._edit_btn.toggled.connect(self._on_edit_toggled)
        hdr.addWidget(self._edit_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        self._report_btn = QPushButton("▣  Report")
        self._report_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid {ACCENT}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:disabled {{ color:{TEXT_SECONDARY}; border-color:{TEXT_SECONDARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._report_btn.setToolTip(
            "Run all modules + diagnostics and auto-open the full HTML report"
        )
        self._report_btn.clicked.connect(self.report_requested.emit)
        hdr.addWidget(self._report_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        self._export_btn = QPushButton("⬇  Export…")
        self._export_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid {ACCENT}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:disabled {{ color:{TEXT_SECONDARY}; border-color:{TEXT_SECONDARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._export_btn.setToolTip("Export last scan results as HTML, JSON, or CSV")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self.export_requested.emit)
        hdr.addWidget(self._export_btn, alignment=Qt.AlignmentFlag.AlignBottom)

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
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" font-size:12px; font-weight:bold; padding:0 18px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; }}"
            f"QPushButton:disabled {{ background:{TEXT_SECONDARY}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
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
        for tile in self._tiles.values():
            tile.expand_toggled.connect(self._on_tile_expand_toggled)
            tile.navigate_requested.connect(self.navigate_to)
        alert_tile = self._tiles.get("alert_feed")
        if alert_tile is not None:
            alert_tile.alert_clicked.connect(self._on_alert_navigate)
        event_tile = self._tiles.get("event_feed")
        if event_tile is not None:
            event_tile.viewall_clicked.connect(
                lambda: self.navigate_to.emit("Monitor")
            )
        modem_tile = self._tiles.get("modem_signal")
        if modem_tile is not None:
            modem_tile.clicked.connect(self.modem_tile_clicked.emit)
        self._reflow()

    def _on_tile_expand_toggled(self, expanding_tile) -> None:
        """Collapse all other tiles when one expands (OVERVIEW-1)."""
        for tile in self._tiles.values():
            if tile is not expanding_tile and tile._expanded:
                tile.toggle_expand()

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
            self._scan_btn.setText("▶  Rescan" if self._has_results else "▶  Scan Network")
            self._scan_sub.setText("Discover devices  ·  check stability  ·  detect threats")

    def set_has_results(self, has_data: bool) -> None:
        self._has_results = has_data
        if not self._scanning:
            self._scan_btn.setText("▶  Rescan" if has_data else "▶  Scan Network")

    def set_report_running(self, running: bool) -> None:
        """Disable/re-enable the Report button while a full report is in progress."""
        self._report_btn.setEnabled(not running)
        self._report_btn.setText("▣  Running…" if running else "▣  Report")

    def set_export_enabled(self, enabled: bool) -> None:
        """Enable the Export button once scan results are available."""
        self._export_btn.setEnabled(enabled)

    def _on_alert_navigate(self, rule_type: str, host: str) -> None:
        _MAP = {
            "SERVICE_DOWN":   "Service Heartbeat",
            "CERT_EXPIRY":    "TLS & Exposure",
            "CERT_EXPIRED":   "TLS & Exposure",
            "RTT_THRESHOLD":  "DNS & Stability",
            "LOSS_THRESHOLD": "DNS & Stability",
            "HOST_DOWN":      "Availability History",
            "HOST_DEGRADED":  "Availability History",
            "FLAP":           "Availability History",
            "NEW_DEVICE":     "Devices",
            "DEVICE_GONE":    "Devices",
        }
        self.navigate_to.emit(_MAP.get(rule_type, "Devices"))

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

    def on_trend_result(self, report) -> None:
        """Receive a TrendReport from the dashboard and push to TrendStatusTile."""
        t = self._tiles.get("trend_status")
        if t:
            t.on_trend_result(report)

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
                f"QPushButton:hover {{ background:{ACCENT}; color:{WHITE}; }}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            )
            btn.clicked.connect(lambda _checked, tid=tile_id: self._add_tile(tid))
            self._add_strip_layout.insertWidget(
                self._add_strip_layout.count() - 1, btn
            )

        self._add_strip.show()

    def _refresh_tile_ages(self) -> None:
        """OVERVIEW-5: refresh the data-age label on every scanned tile."""
        for tile in self._tiles.values():
            tile._update_ts_display()

    def _refresh_store_tiles(self) -> None:
        try:
            self.objectName()   # raises RuntimeError if C++ object already deleted
        except RuntimeError:
            return
        for tid in ("tls_status", "event_feed", "recent_events"):
            t = self._tiles.get(tid)
            if t:
                t.refresh(self._store)
        if self._store:
            try:
                devices = self._store.get_known_devices()
                self.set_has_results(len(devices) > 0)
            except Exception:
                pass
