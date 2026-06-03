"""
tabs_logger.py — _LoggerTabMixin: network logger tab builder + handlers + retention helpers.

Extracted from ui/tabs_diag.py (Sprint 15). Contains the Network Logger tab UI,
logger start/stop, log-entry handlers, live-challenge handlers, and the retention
helper methods that feed the Home page (suggestions strip, last-visit summary,
weekly digest).
"""
from __future__ import annotations

import webbrowser

from PyQt6.QtCore import Qt, QSettings, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    AMBER, BG_CARD, BORDER, CARD_RADIUS,
    GREEN, RED,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)
from ui.tabs_helpers import _make_card, _table


class _LoggerTabMixin:
    """Mixin providing the Network Logger tab builder + all logger event handlers.

    Extracted from ui/tabs_diag.py (Sprint 15).
    _DiagTabsMixin inherits from this mixin.
    """

    # ── Logger tab ────────────────────────────────────────────────────────────

    def _build_logger_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QTextEdit
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        _qs = QSettings("NetSentinel", "NetSentinel")

        # ── Page header ───────────────────────────────────────────────────────
        title = QLabel("📋  Network Logger")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        lay.addWidget(title)

        # ── Log Sources card ──────────────────────────────────────────────────
        src_card, src_body = _make_card("Log Sources")

        def _section_lbl(text: str) -> QLabel:
            lbl = QLabel(text.upper())
            lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
                "letter-spacing:0.8px; background:transparent; border:none;"
            )
            return lbl

        def _chk(text: str, tooltip: str = "") -> QCheckBox:
            c = QCheckBox(text)
            c.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px;")
            if tooltip:
                c.setToolTip(tooltip)
            return c

        def _spin(lo: int, hi: int, val: int, suffix: str, w: int = 72) -> QSpinBox:
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setValue(val)
            s.setSuffix(suffix)
            s.setFixedWidth(w)
            s.setStyleSheet(
                f"QSpinBox {{ background:{BG_CARD}; border:1px solid {BORDER};"
                f" border-radius:4px; padding:1px 4px; font-size:11px; color:{TEXT_PRIMARY}; }}"
                f"QSpinBox:disabled {{ color:{TEXT_MUTED}; }}"
            )
            return s

        # ── Active Pollers ────────────────────────────────────────────────────
        src_body.addWidget(_section_lbl("Active Pollers"))

        # Ping RTT row
        ping_row = QHBoxLayout()
        ping_row.setSpacing(6)
        ping_lbl = QLabel("Ping RTT")
        ping_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; font-weight:600;")
        int_lbl = QLabel("Interval:")
        int_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._log_interval = _spin(5, 3600, _qs.value("logger/interval_s", 60, type=int), " s", 72)
        self._log_interval.setToolTip("How often to ping each host")
        self._log_interval.valueChanged.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/interval_s", v)
        )
        ping_row.addWidget(ping_lbl)
        ping_row.addSpacing(8)
        ping_row.addWidget(int_lbl)
        ping_row.addWidget(self._log_interval)
        ping_row.addStretch()
        src_body.addLayout(ping_row)

        # Ping optional sub-measurements
        opt_row = QHBoxLayout()
        opt_row.setSpacing(12)
        opt_row.setContentsMargins(0, 0, 0, 0)
        self._log_chk_jitter = _chk("Jitter  (3× ping)", "Measure RTT variance — adds 2 extra pings per cycle")
        self._log_chk_dns    = _chk("DNS latency",       "Time a DNS lookup each cycle")
        self._log_chk_http   = _chk("HTTP check",        "Check HTTP reachability each cycle")
        self._log_chk_jitter.setChecked(_qs.value("logger/chk_jitter", False, type=bool))
        self._log_chk_dns   .setChecked(_qs.value("logger/chk_dns",    False, type=bool))
        self._log_chk_http  .setChecked(_qs.value("logger/chk_http",   False, type=bool))
        self._log_chk_jitter.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/chk_jitter", v))
        self._log_chk_dns.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/chk_dns", v))
        self._log_chk_http.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/chk_http", v))
        opt_row.addSpacing(16)
        for c in (self._log_chk_jitter, self._log_chk_dns, self._log_chk_http):
            opt_row.addWidget(c)
        opt_row.addStretch()
        src_body.addLayout(opt_row)

        src_body.addSpacing(4)

        # 5G Modem row
        modem_row = QHBoxLayout()
        modem_row.setSpacing(6)
        self._log_chk_modem = _chk(
            "5G Modem signal",
            "Log modem signal metrics (RSRP, SINR, band…) to the database at the set interval.\n"
            "Requires modem credentials saved on the Modem page."
        )
        self._log_chk_modem.setChecked(_qs.value("logging/modem_enabled", False, type=bool))
        modem_int_lbl = QLabel("Log every:")
        modem_int_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._log_modem_interval = _spin(
            1, 60, _qs.value("logging/modem_interval_min", 5, type=int), " min"
        )
        self._log_modem_interval.setEnabled(self._log_chk_modem.isChecked())
        self._log_modem_interval.setToolTip("How often to write modem signal data to the database")
        self._log_chk_modem.toggled.connect(
            lambda v: (
                QSettings("NetSentinel", "NetSentinel").setValue("logging/modem_enabled", v),
                self._log_modem_interval.setEnabled(v),
            )
        )
        self._log_modem_interval.valueChanged.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logging/modem_interval_min", v)
        )
        modem_row.addWidget(self._log_chk_modem)
        modem_row.addSpacing(8)
        modem_row.addWidget(modem_int_lbl)
        modem_row.addWidget(self._log_modem_interval)
        modem_row.addStretch()
        src_body.addLayout(modem_row)

        # Mesh row
        mesh_row = QHBoxLayout()
        mesh_row.setSpacing(6)
        self._log_chk_mesh = _chk(
            "Mesh router status",
            "Log mesh node status (online count, worst RSSI…) to the database at the set interval.\n"
            "Requires Deco credentials saved on the Hardware Integration page."
        )
        self._log_chk_mesh.setChecked(_qs.value("logging/mesh_enabled", False, type=bool))
        mesh_int_lbl = QLabel("Log every:")
        mesh_int_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._log_mesh_interval = _spin(
            1, 60, _qs.value("logging/mesh_interval_min", 5, type=int), " min"
        )
        self._log_mesh_interval.setEnabled(self._log_chk_mesh.isChecked())
        self._log_mesh_interval.setToolTip("How often to write mesh status data to the database")
        self._log_chk_mesh.toggled.connect(
            lambda v: (
                QSettings("NetSentinel", "NetSentinel").setValue("logging/mesh_enabled", v),
                self._log_mesh_interval.setEnabled(v),
            )
        )
        self._log_mesh_interval.valueChanged.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logging/mesh_interval_min", v)
        )
        mesh_row.addWidget(self._log_chk_mesh)
        mesh_row.addSpacing(8)
        mesh_row.addWidget(mesh_int_lbl)
        mesh_row.addWidget(self._log_mesh_interval)
        mesh_row.addStretch()
        src_body.addLayout(mesh_row)

        src_body.addSpacing(6)

        # ── Passive Listeners ─────────────────────────────────────────────────
        src_body.addWidget(_section_lbl("Passive Listeners"))

        passive_row = QHBoxLayout()
        passive_row.setSpacing(16)
        self._log_chk_arp = _chk(
            "ARP watch",
            "Flag new or changed ARP entries — new devices, MAC changes, possible spoofing."
        )
        self._log_chk_arp.setChecked(_qs.value("logger/chk_arp", False, type=bool))
        self._log_chk_arp.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/chk_arp", v)
        )
        self._log_chk_syslog = _chk(
            "Syslog receiver",
            "Listen for syslog messages (UDP 514) from routers and other devices."
        )
        self._log_chk_syslog.setChecked(_qs.value("logging/syslog_enabled", True, type=bool))
        self._log_chk_syslog.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logging/syslog_enabled", v)
        )
        self._log_chk_snmp = _chk(
            "SNMP trap receiver",
            "Listen for SNMPv1/v2c traps (UDP 162) from managed devices."
        )
        self._log_chk_snmp.setChecked(_qs.value("logging/snmp_enabled", True, type=bool))
        self._log_chk_snmp.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logging/snmp_enabled", v)
        )
        for c in (self._log_chk_arp, self._log_chk_syslog, self._log_chk_snmp):
            passive_row.addWidget(c)
        passive_row.addStretch()
        src_body.addLayout(passive_row)

        lay.addWidget(src_card)

        # ── Logger controls row ───────────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        self._btn_log_start = QPushButton("▶  Start Logger")
        self._btn_log_start.setObjectName("btnDiag")
        self._btn_log_start.setFixedHeight(34)
        self._btn_log_start.clicked.connect(self._toggle_logger)

        self._btn_log_open = QPushButton("📂  Open Log File")
        self._btn_log_open.setFixedHeight(34)
        self._btn_log_open.setEnabled(False)
        self._btn_log_open.clicked.connect(self._open_log_file)

        self._btn_log_analyse = QPushButton("⊕  Load & Analyse")
        self._btn_log_analyse.setFixedHeight(34)
        self._btn_log_analyse.clicked.connect(self._load_log_file)

        self._btn_log_chart = QPushButton("◎  View Chart")
        self._btn_log_chart.setFixedHeight(34)
        self._btn_log_chart.setEnabled(False)
        self._btn_log_chart.setToolTip("Render loaded log as RTT chart (opens interactive window)")
        self._btn_log_chart.clicked.connect(self._view_log_chart)

        rot_lbl = QLabel("Rotate file:")
        rot_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._log_rotation = QComboBox()
        self._log_rotation.addItems(["Off", "1 hour", "6 hours", "12 hours", "24 hours"])
        self._log_rotation.setFixedWidth(90)
        self._log_rotation.setToolTip(
            "Start a new CSV file after this interval — keeps files to a manageable size.\n"
            "12 h is best practice."
        )
        _rot_vals = [0, 1, 6, 12, 24]
        self._log_rotation_vals = _rot_vals
        _saved_rot = _qs.value("logger/rotation_hours", 12, type=int)
        self._log_rotation.setCurrentIndex(
            _rot_vals.index(_saved_rot) if _saved_rot in _rot_vals else 3
        )
        self._log_rotation.currentIndexChanged.connect(
            lambda i, v=_rot_vals: QSettings("NetSentinel", "NetSentinel").setValue(
                "logger/rotation_hours", v[i]
            )
        )

        self._log_chk_autostart = QCheckBox("Auto-start on launch")
        self._log_chk_autostart.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; font-weight:600;")
        self._log_chk_autostart.setToolTip(
            "Logger will start immediately each time the app launches — no manual step required."
        )
        self._log_chk_autostart.setChecked(_qs.value("logger/auto_start", False, type=bool))
        self._log_chk_autostart.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/auto_start", v)
        )

        ctrl_row.addWidget(self._btn_log_start)
        ctrl_row.addWidget(self._btn_log_open)
        ctrl_row.addWidget(self._btn_log_analyse)
        ctrl_row.addWidget(self._btn_log_chart)
        ctrl_row.addSpacing(12)
        ctrl_row.addWidget(rot_lbl)
        ctrl_row.addWidget(self._log_rotation)
        ctrl_row.addSpacing(12)
        ctrl_row.addWidget(self._log_chk_autostart)
        ctrl_row.addStretch()
        lay.addLayout(ctrl_row)

        # ── Status + summary stats ────────────────────────────────────────────
        self._log_status_lbl = QLabel(
            "Logger not running.  Start it, then leave the app running in the background."
        )
        self._log_status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._log_status_lbl)

        stats_row = QHBoxLayout()
        self._log_stat_total   = self._stat_label("Total Pings", "—")
        self._log_stat_uptime  = self._stat_label("Uptime", "—")
        self._log_stat_avgrtt  = self._stat_label("Avg RTT", "—")
        self._log_stat_outages = self._stat_label("Outages", "—")
        for s in (self._log_stat_total, self._log_stat_uptime,
                  self._log_stat_avgrtt, self._log_stat_outages):
            stats_row.addWidget(s)
        stats_row.addStretch()
        lay.addLayout(stats_row)

        # ── Log analysis results panel ────────────────────────────────────────
        analysis_lbl = QLabel("  Log Analysis:")
        analysis_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(analysis_lbl)
        self._log_analysis_box = QTextEdit()
        self._log_analysis_box.setReadOnly(True)
        self._log_analysis_box.setMaximumHeight(160)
        self._log_analysis_box.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; font-size:11px;"
            f"border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; padding:6px;"
        )
        self._log_analysis_box.setPlaceholderText(
            "Load a log file to see automatic diagnostic findings here."
        )
        lay.addWidget(self._log_analysis_box)

        # ── Outage summary ────────────────────────────────────────────────────
        outage_lbl = QLabel("  Detected Outages:")
        outage_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(outage_lbl)
        self._log_outage_table = _table([
            "Host", "Outage Start", "Outage End", "Duration (s)", "Consecutive Fails"
        ])
        self._log_outage_table.setMaximumHeight(160)
        lay.addWidget(self._log_outage_table)

        # ── Live ping log ─────────────────────────────────────────────────────
        live_lbl = QLabel("  Live log (most recent pings):")
        live_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(live_lbl)
        self._log_live_table = _table([
            "Timestamp", "Host", "RTT (ms)", "Jitter", "DNS (ms)", "HTTP", "ARP Event", "Status"
        ])
        self._log_live_table.setColumnWidth(0, 155)
        self._log_live_table.setColumnWidth(1, 120)
        self._log_live_table.setColumnWidth(2, 70)
        self._log_live_table.setColumnWidth(3, 65)
        self._log_live_table.setColumnWidth(4, 70)
        self._log_live_table.setColumnWidth(5, 50)
        self._log_live_table.setColumnWidth(6, 180)
        lay.addWidget(self._log_live_table, 1)

        return w

    # ── Logger handlers ───────────────────────────────────────────────────────

    @pyqtSlot()
    def _toggle_logger(self):
        if self._logger_worker and self._logger_worker.isRunning():
            # Stop
            self._logger_worker.stop_logger()
            self._btn_log_start.setText("▶  Start Logger")
            self._log_status_lbl.setText("Logger stopped.")
            self._btn_log_open.setEnabled(True)
            self._home_page.set_monitoring_status(False)
        else:
            # Start
            import time as _time
            from workers.scan_worker import LoggerWorker
            interval = self._log_interval.value()
            rotation_h = self._log_rotation_vals[self._log_rotation.currentIndex()]
            self._logger_worker = LoggerWorker(
                interval_s=interval,
                enable_jitter=self._log_chk_jitter.isChecked(),
                enable_dns=self._log_chk_dns.isChecked(),
                enable_http=self._log_chk_http.isChecked(),
                enable_arp=self._log_chk_arp.isChecked(),
                rotation_hours=rotation_h,
            )
            self._logger_start_ts = _time.time()
            self._logger_outage_count = 0
            self._logger_worker.entry_received.connect(self._on_log_entry)
            self._logger_worker.status.connect(self._log_status_lbl.setText)
            self._logger_worker.rotated.connect(self._on_log_rotate)
            self._logger_worker.error.connect(
                lambda e: self._log_status_lbl.setText(f"Error: {e}"),
                Qt.ConnectionType.QueuedConnection,
            )
            self._logger_worker.start()
            self._btn_log_start.setText("⏹  Stop Logger")
            self._btn_log_open.setEnabled(False)
            self._log_live_table.setRowCount(0)
            self._log_outage_table.setRowCount(0)
            self._home_page.set_monitoring_status(True, "", 0)
            # Show a non-blocking toast on first-ever logger start
            _qs2 = QSettings("NetSentinel", "NetSentinel")
            if not _qs2.value("logger/first_start_prompted", False, type=bool):
                _qs2.setValue("logger/first_start_prompted", True)
                from ui.widgets.toast import ToastManager
                ToastManager.show("Background logging started — data appears in Network Logger.")

    @pyqtSlot(object)
    def _on_log_entry(self, entry):
        """Called from LoggerWorker for each new ping result."""
        self._last_log_status = entry.status
        self._refresh_pulse_bar()
        if hasattr(self, "_log_hub_page"):
            self._log_hub_page.add_log_entry(entry)

    @pyqtSlot(object)
    def _on_live_challenge(self, scenario) -> None:
        """Show amber banner on Home and store scenario for Lab Mode injection."""
        self._pending_live_scenario = scenario
        if hasattr(self, "_home_page"):
            self._home_page.on_live_challenge(scenario)

    def _on_investigate_live(self) -> None:
        """Navigate to Lab Mode and inject the pending live challenge scenario."""
        scenario = self._pending_live_scenario
        self._pending_live_scenario = None
        if scenario is None:
            return
        self._nav_rail_go_to("Lab Mode")
        if hasattr(self, "_lab_mode_page"):
            self._lab_mode_page.inject_live_challenge(scenario)

    @pyqtSlot(object)
    def _on_animate_log_entry(self, entry) -> None:
        """Navigate to Protocol Visualizer and pre-load the protocol for this log entry."""
        self._nav_rail_go_to("Protocol Visualizer")
        if hasattr(self, "_protocol_viz_page"):
            self._protocol_viz_page.load_from_event(entry)
        from PyQt6.QtGui import QColor
        color_map = {"OK": GREEN, "SLOW": AMBER, "FAIL": RED}
        status_color = color_map.get(entry.status, TEXT_SECONDARY)
        rtt_str    = f"{entry.rtt_ms:.0f}"    if entry.rtt_ms    >= 0 else "—"
        jitter_str = f"{entry.jitter_ms:.0f}" if entry.jitter_ms >= 0 else ""
        dns_str    = f"{entry.dns_ms:.0f}"    if entry.dns_ms    >= 0 else ""
        http_str   = str(entry.http_status)   if entry.http_status >= 0 else ""
        arp_str    = entry.arp_event or ""

        # Prepend new row (keep max 500 rows visible)
        self._log_live_table.insertRow(0)
        row_vals = [entry.timestamp, entry.host, rtt_str, jitter_str,
                    dns_str, http_str, arp_str, entry.status]
        for col, val in enumerate(row_vals):
            item = QTableWidgetItem(str(val))
            c = status_color if col == 7 else (AMBER if col == 6 and val else TEXT_PRIMARY)
            item.setForeground(QColor(c))
            self._log_live_table.setItem(0, col, item)
        if self._log_live_table.rowCount() > 500:
            self._log_live_table.setRowCount(500)

        # Update live stats
        if self._logger_worker:
            summary = self._logger_worker.get_summary()
            if summary:
                self._update_stat(self._log_stat_total,
                                  str(summary.total_pings))
                self._update_stat(self._log_stat_uptime,
                                  f"{summary.uptime_pct:.1f}%",
                                  GREEN if summary.uptime_pct >= 99 else (AMBER if summary.uptime_pct >= 95 else RED))
                self._update_stat(self._log_stat_avgrtt,
                                  f"{summary.avg_rtt_ms:.0f} ms" if summary.avg_rtt_ms > 0 else "—")
                self._update_stat(self._log_stat_outages,
                                  str(len(summary.outages)),
                                  RED if summary.outages else GREEN)
                # Update home page monitoring card
                import time as _t
                elapsed_s = int(_t.time() - getattr(self, "_logger_start_ts", _t.time()))
                h, rem = divmod(elapsed_s, 3600)
                m = rem // 60
                elapsed_str = (f"{h} h {m} m" if h else f"{m} m") if elapsed_s >= 60 else ""
                self._logger_outage_count = len(summary.outages)
                self._home_page.set_monitoring_status(True, elapsed_str, self._logger_outage_count)
                self._log_chart_summary = summary
                self._btn_log_chart.setEnabled(True)

                # Rebuild outage table
                self._log_outage_table.setRowCount(0)
                for o in summary.outages:
                    row = self._log_outage_table.rowCount()
                    self._log_outage_table.insertRow(row)
                    for col, val in enumerate([
                        o.host, o.start, o.end,
                        f"{o.duration_s:.0f}", str(o.consecutive_fails)
                    ]):
                        item = QTableWidgetItem(str(val))
                        item.setForeground(
                            __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(RED)
                        )
                        self._log_outage_table.setItem(row, col, item)

    @pyqtSlot(str, int)
    def _on_log_rotate(self, filename: str, segment: int):
        """Called when NetworkLogger starts a new CSV segment."""
        self._log_status_lbl.setText(
            f"Segment {segment} started — now logging to {filename}"
        )

    def _open_log_file(self):
        """Open the log CSV in the default text editor / Excel."""
        if self._logger_worker and self._logger_worker.log_file:
            path = self._logger_worker.log_file
            if path.exists():
                webbrowser.open(path.as_uri())

    # ── Retention helpers ─────────────────────────────────────────────────────

    def _compute_suggestions(self) -> None:
        """Compute actionable next-steps and push them to the home page."""
        if not hasattr(self, "_home_page"):
            return
        suggestions: list = []

        # High-risk devices from last scan
        if getattr(self, "_m1_result", None):
            high = self._m1_result.get("high_risk_count", 0)
            if high > 0:
                s = "s" if high != 1 else ""
                suggestions.append({
                    "action_key": "high_risk_check",
                    "text": f"{high} high-risk device{s} found — review security findings",
                    "action_label": "View Overview →",
                    "target": "Overview",
                    "priority": "high",
                })

        # Stability logger not running
        if not (self._logger_worker and self._logger_worker.isRunning()):
            suggestions.append({
                "action_key": "start_logger",
                "text": "Network stability is not being monitored — start logging to detect outages",
                "action_label": "Start Monitoring →",
                "target": None,
                "priority": "medium",
            })

        # No speed test in the last 7 days
        if self._store is not None:
            try:
                speed_rows = self._store.query_speed_test_history(hours=168, limit=1)
                if not speed_rows:
                    suggestions.append({
                        "action_key": "run_speed_test",
                        "text": "No speed test in the last 7 days — check your internet performance",
                        "action_label": "Run Speed Test →",
                        "target": "Speed Test",
                        "priority": "low",
                    })
            except Exception:
                pass

        # Open CVEs
        if self._store is not None:
            try:
                open_cves = self._store.list_cve_lifecycles(state_filter="Open")
                n = len(open_cves)
                if n > 0:
                    s = "s" if n != 1 else ""
                    suggestions.append({
                        "action_key": "view_open_cves",
                        "text": f"{n} open CVE{s} need remediation",
                        "action_label": "View CVEs →",
                        "target": "CVE Tracker",
                        "priority": "high",
                    })
            except Exception:
                pass

        # Poor grade
        bm = getattr(self, "_last_benchmark_result", None)
        if bm is not None:
            grade = getattr(bm, "overall_grade", None)
            if grade in ("C", "D", "F"):
                suggestions.append({
                    "action_key": "fix_network_grade",
                    "text": f"Your network grade is {grade} — run a health check for recommendations",
                    "action_label": "View Overview →",
                    "target": "Overview",
                    "priority": "medium",
                })

        # Fallback: always show ≥1 entry after first scan when no other suggestions
        if not suggestions:
            from PyQt6.QtCore import QSettings as _QS
            _qs = _QS("NetSentinel", "NetSentinel")
            if not _qs.value("logger_started_once", False, type=bool):
                suggestions.append({
                    "action_key": "start_logger_fallback",
                    "text": "Enable the Network Logger to track stability over time",
                    "action_label": "Start →",
                    "target": "Log Hub",
                    "priority": "low",
                })

        self._home_page.set_suggestions(suggestions)

    def _compute_last_visit_summary(self) -> None:
        """Show 'Since you were last here' on the home page using MetricStore + QSettings."""
        if not hasattr(self, "_home_page") or self._store is None:
            return
        try:
            import time as _time
            from PyQt6.QtCore import QSettings as _QS
            _s = _QS("NetSentinel", "NetSentinel")
            last_ts = int(_s.value("app/last_visit_ts", 0, type=int))
            now = int(_time.time())

            # Update the visit timestamp so next launch measures from now
            _s.setValue("app/last_visit_ts", str(now))

            if last_ts == 0:
                return  # First ever launch — nothing to compare

            hours_since = (now - last_ts) / 3600.0
            if hours_since < 0.5:
                return  # Relaunched within 30 min — not worth showing

            # Format "last visit" string
            if hours_since < 2:
                last_str = "about an hour ago"
            elif hours_since < 24:
                last_str = f"{int(hours_since)} hours ago"
            elif hours_since < 48:
                last_str = "yesterday"
            else:
                last_str = f"{int(hours_since / 24)} days ago"

            joined_events = self._store.query_device_events(
                hours=hours_since, event_types=["JOINED"]
            )
            joined_count = len({e.ip for e in joined_events})

            outage_events = self._store.query_device_events(
                hours=hours_since, event_types=["DOWN"]
            )
            outage_count = len(outage_events)

            # Enrich with logger RTT data if available
            logger_summary = self._build_logger_summary(hours_since)

            self._home_page.set_last_visit_summary(
                joined_count, outage_count, last_str, logger_summary
            )
        except Exception:
            pass

    def _build_logger_summary(self, hours_since: float) -> str:
        """Return a one-line logger insight string for the 'since you were away' banner."""
        try:
            hosts = self._store.query_all_rtt_hosts(hours=hours_since)
            if not hosts:
                return ""
            host = hosts[0]
            points = self._store.query_rtt_history(host=host, hours=hours_since)
            if not points:
                return ""

            total = len(points)
            fails = sum(1 for p in points if p.loss_pct is not None and p.loss_pct >= 100)

            # Check for ≥3 consecutive complete failures
            consecutive = 0
            max_consecutive = 0
            for p in points:
                if p.loss_pct is not None and p.loss_pct >= 100:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0
            if max_consecutive >= 3:
                return f"{fails} of {total} pings failed while away"

            # Check for RTT regression vs baseline (first quarter vs last quarter)
            valid_rtts = [p.rtt_ms for p in points if p.rtt_ms is not None and p.rtt_ms > 0]
            if len(valid_rtts) >= 8:
                mid = len(valid_rtts) // 4
                baseline_avg = sum(valid_rtts[:mid]) / mid
                recent_avg = sum(valid_rtts[-mid:]) / mid
                if baseline_avg > 0 and recent_avg > baseline_avg * 1.5:
                    return (
                        f"RTT higher than usual "
                        f"({recent_avg:.0f} ms vs {baseline_avg:.0f} ms baseline)"
                    )

            # All clear
            return f"{total} pings logged, no issues"
        except Exception:
            return ""

    def _maybe_send_weekly_digest(self) -> None:
        """Show a tray digest notification if 7+ days since the last one."""
        try:
            import time as _time
            from PyQt6.QtCore import QSettings as _QS
            _s = _QS("NetSentinel", "NetSentinel")
            last_ts = int(_s.value("app/last_digest_ts", 0, type=int))
            now = int(_time.time())
            if now - last_ts < 7 * 86400:
                return
            if not self._tray_manager.is_available():
                return

            parts: list[str] = []
            if self._store is not None:
                try:
                    speed_rows = self._store.query_speed_test_history(hours=168, limit=1)
                    if speed_rows:
                        dl = speed_rows[0].download_mbps or 0.0
                        parts.append(f"Speed: {dl:.0f} Mbps download")
                    joined = self._store.query_device_events(hours=168, event_types=["JOINED"])
                    if joined:
                        n = len({e.ip for e in joined})
                        s = "s" if n != 1 else ""
                        parts.append(f"{n} new device{s} joined")
                    g = self._store.query_last_grade()
                    if g:
                        parts.append(f"Network grade: {g['grade']}")
                except Exception:
                    pass

            if not parts:
                parts.append("Network has been running smoothly")

            self._tray_manager.show_notification(
                "NetSentinel Weekly Digest",
                "  ·  ".join(parts),
                "INFO",
            )
            _s.setValue("app/last_digest_ts", str(now))
        except Exception:
            pass

    def _load_log_file(self):
        """Let the user pick any existing log CSV and show its analysis."""
        from PyQt6.QtWidgets import QFileDialog
        from modules.network_logger import load_log_file
        from pathlib import Path

        log_dir = str(Path.home() / "Documents" / "NetSentinel" / "logs")
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open NetSentinel Log", log_dir, "CSV Log Files (*.csv);;All Files (*)"
        )
        if not path_str:
            return
        summary = load_log_file(Path(path_str))

        # Populate stats
        self._update_stat(self._log_stat_total, str(summary.total_pings))
        self._update_stat(self._log_stat_uptime,
                          f"{summary.uptime_pct:.1f}%",
                          GREEN if summary.uptime_pct >= 99 else (AMBER if summary.uptime_pct >= 95 else RED))
        self._update_stat(self._log_stat_avgrtt,
                          f"{summary.avg_rtt_ms:.0f} ms" if summary.avg_rtt_ms > 0 else "—")
        self._update_stat(self._log_stat_outages,
                          str(len(summary.outages)),
                          RED if summary.outages else GREEN)

        # Populate live table with loaded entries (newest first) — all 8 columns
        from PyQt6.QtGui import QColor as _QColor
        self._log_live_table.setRowCount(0)
        for entry in reversed(summary.entries[-500:]):
            status_color = {"OK": GREEN, "SLOW": AMBER, "FAIL": RED}.get(entry.status, TEXT_SECONDARY)
            rtt_str    = f"{entry.rtt_ms:.0f}"    if entry.rtt_ms    >= 0 else "—"
            jitter_str = f"{entry.jitter_ms:.0f}" if entry.jitter_ms >= 0 else ""
            dns_str    = f"{entry.dns_ms:.0f}"    if entry.dns_ms    >= 0 else ""
            http_str   = str(entry.http_status)   if entry.http_status >= 0 else ""
            arp_str    = entry.arp_event or ""
            row = self._log_live_table.rowCount()
            self._log_live_table.insertRow(row)
            for col, val in enumerate([
                entry.timestamp, entry.host, rtt_str, jitter_str,
                dns_str, http_str, arp_str, entry.status,
            ]):
                item = QTableWidgetItem(str(val))
                c = status_color if col == 7 else (AMBER if col == 6 and val else TEXT_PRIMARY)
                item.setForeground(_QColor(c))
                self._log_live_table.setItem(row, col, item)

        # Outage table — AMBER < 5 min, RED >= 5 min
        self._log_outage_table.setRowCount(0)
        for o in summary.outages:
            row = self._log_outage_table.rowCount()
            self._log_outage_table.insertRow(row)
            out_color = AMBER if o.duration_s < 300 else RED
            for col, val in enumerate([
                o.host, o.start, o.end, f"{o.duration_s:.0f}", str(o.consecutive_fails)
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(_QColor(out_color))
                self._log_outage_table.setItem(row, col, item)

        self._log_status_lbl.setText(
            f"Loaded {summary.total_pings} entries from {Path(path_str).name}  "
            f"— {len(summary.outages)} outage(s), {summary.uptime_pct:.1f}% uptime"
        )

        # Store summary and enable the chart button
        self._log_chart_summary = summary
        self._btn_log_chart.setEnabled(True)

        # ── Automated analysis ────────────────────────────────────────────────
        try:
            from modules.network_logger import analyse_log
            findings = analyse_log(summary)
            _sev_color = {"HIGH": RED, "WARN": AMBER, "INFO": GREEN}
            html_parts = []
            for f in findings:
                fc = _sev_color.get(f.severity, TEXT_SECONDARY)
                html_parts.append(
                    f"<p style='margin:4px 0'>"
                    f"<span style='color:{fc};font-weight:bold'>[{f.severity}] {f.category}: {f.title}</span>"
                    f"<br><span style='color:{TEXT_SECONDARY}'>{f.detail}</span></p>"
                )
            self._log_analysis_box.setHtml("".join(html_parts))
        except Exception as _exc:
            self._log_analysis_box.setPlainText(f"Analysis failed: {_exc}")
