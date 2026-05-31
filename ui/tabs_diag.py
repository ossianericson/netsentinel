"""
tabs_diag.py — _DiagTabsMixin: diagnostics, logger, MTR, tools, and event handlers.

Extracted from ui/tabs.py (Sprint 8). Contains the diagnostics tab, network
logger tab, MTR tab, advanced tools tab, and all associated event handler methods.
"""
from __future__ import annotations

import webbrowser

from PyQt6.QtCore import Qt, QSettings, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BORDER, CARD_RADIUS,
    GREEN, RED,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)
from ui.tabs_helpers import _make_card, _table


class _DiagTabsMixin:
    """Mixin providing diagnostics/logger/tools tab builders + event handlers.

    Extracted from ui/tabs.py (Sprint 8).
    """

    # ── Diagnostics tab ───────────────────────────────────────────────────────

    def _build_diagnostics_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Top bar
        top = QHBoxLayout()
        title = QLabel("⚡  Network Health & Diagnostics")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        top.addWidget(title)
        top.addStretch()
        self._btn_diag = QPushButton("⚡  Run Diagnostics")
        self._btn_diag.setObjectName("btnDiag")
        self._btn_diag.setFixedHeight(34)
        self._btn_diag.clicked.connect(self._start_diagnostics)
        top.addWidget(self._btn_diag)
        lay.addLayout(top)

        self._diag_status_lbl = QLabel("Click 'Run Diagnostics' to test connectivity and performance.")
        self._diag_status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._diag_status_lbl)

        # Summary row
        summary_row = QHBoxLayout()
        self._diag_speed_lbl  = self._stat_label("Download", "—")
        self._diag_public_lbl = self._stat_label("Public IP", "—")
        self._diag_dns_lbl    = self._stat_label("System DNS", "—")
        self._diag_gw_lbl     = self._stat_label("Gateway RTT", "—")
        for w2 in (self._diag_gw_lbl, self._diag_speed_lbl,
                   self._diag_dns_lbl, self._diag_public_lbl):
            summary_row.addWidget(w2)
        summary_row.addStretch()
        lay.addLayout(summary_row)

        # Two-column detail: Ping | DNS
        cols = QHBoxLayout()
        cols.setSpacing(10)

        left = QVBoxLayout()
        left.addWidget(QLabel("  Ping Tests"))
        self._diag_ping_table = _table(["Host", "IP", "RTT (ms)", "Status"])
        self._diag_ping_table.setColumnWidth(0, 120)
        self._diag_ping_table.setColumnWidth(1, 120)
        self._diag_ping_table.setColumnWidth(2, 70)
        left.addWidget(self._diag_ping_table)

        right = QVBoxLayout()
        right.addWidget(QLabel("  DNS Speed"))
        self._diag_dns_table = _table(["DNS Server", "Latency (ms)", "Resolved IP", "Status"])
        self._diag_dns_table.setColumnWidth(0, 110)
        self._diag_dns_table.setColumnWidth(1, 100)
        self._diag_dns_table.setColumnWidth(2, 110)
        right.addWidget(self._diag_dns_table)

        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        lay.addLayout(cols)

        # HTTP connectivity
        http_row = QHBoxLayout()
        http_lbl = QLabel("  Internet Connectivity:")
        http_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        http_row.addWidget(http_lbl)
        self._diag_http_labels: list = []
        for name, _ in [("Google 204", ""), ("Cloudflare", ""), ("Apple captive", "")]:
            lbl = QLabel(f"● {name}: —")
            lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding:0 10px;")
            self._diag_http_labels.append(lbl)
            http_row.addWidget(lbl)
        http_row.addStretch()
        lay.addLayout(http_row)

        # DNS Leak
        leak_row = QHBoxLayout()
        leak_lbl_hdr = QLabel("  DNS Leak Test:")
        leak_lbl_hdr.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        leak_row.addWidget(leak_lbl_hdr)
        self._diag_leak_lbl = QLabel("—")
        self._diag_leak_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-left:10px;")
        self._diag_leak_lbl.setWordWrap(True)
        leak_row.addWidget(self._diag_leak_lbl, 1)
        lay.addLayout(leak_row)
        self._diag_leak_table = _table(["Resolver IP", "Country", "ASN / Org"])
        self._diag_leak_table.setColumnWidth(0, 130)
        self._diag_leak_table.setColumnWidth(1, 120)
        self._diag_leak_table.setMaximumHeight(110)
        lay.addWidget(self._diag_leak_table)

        # Traceroute
        trace_lbl = QLabel("  Traceroute to 8.8.8.8:")
        trace_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(trace_lbl)
        self._diag_trace_table = _table(["Hop", "IP Address", "RTT (ms)"])
        self._diag_trace_table.setColumnWidth(0, 50)
        self._diag_trace_table.setColumnWidth(1, 160)
        lay.addWidget(self._diag_trace_table, 1)
        return w

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

    # ── MTR tab (Advanced) ────────────────────────────────────────────────────

    def _build_mtr_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("🔁  Continuous Traceroute  (MTR)")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        top.addWidget(title)
        top.addStretch()
        tgt_lbl = QLabel("Target:")
        tgt_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._mtr_target = QLineEdit("8.8.8.8")
        self._mtr_target.setFixedWidth(130)
        self._btn_mtr = QPushButton("▶  Start MTR")
        self._btn_mtr.setObjectName("btnDiag")
        self._btn_mtr.setFixedHeight(30)
        self._btn_mtr.clicked.connect(self._toggle_mtr)
        top.addWidget(tgt_lbl)
        top.addWidget(self._mtr_target)
        top.addWidget(self._btn_mtr)
        lay.addLayout(top)

        self._mtr_status = QLabel("Click Start MTR to run a continuous hop-by-hop trace.")
        self._mtr_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._mtr_status)

        self._mtr_table = _table(["Hop", "IP Address", "Sent", "Loss %", "Avg RTT (ms)", "Last RTT"])
        self._mtr_table.setColumnWidth(0, 45)
        self._mtr_table.setColumnWidth(1, 160)
        self._mtr_table.setColumnWidth(2, 60)
        self._mtr_table.setColumnWidth(3, 70)
        self._mtr_table.setColumnWidth(4, 110)
        lay.addWidget(self._mtr_table, 1)
        self._mtr_worker = None
        # {hop: {ip, sent, lost, total_rtt}}
        self._mtr_stats: dict = {}
        self._mtr_cycle = 0
        return w

    # ── Advanced Tools tab ────────────────────────────────────────────────────

    def _build_advanced_tools_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        title = QLabel("🔧  Advanced Tools")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        lay.addWidget(title)

        # Port Scanner card
        ps_frame = QFrame()
        ps_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        ps_l = QVBoxLayout(ps_frame)
        ps_l.setContentsMargins(16, 12, 16, 12)
        ps_l.setSpacing(6)
        ps_title = QLabel("🔍  Port Scanner")
        ps_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ps_title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        ps_l.addWidget(ps_title)
        ps_desc = QLabel(
            "TCP connect-scan of common ports on any host.  "
            "No admin required.  Right-click a device in Device Fingerprinter → Port Scan."
        )
        ps_desc.setWordWrap(True)
        ps_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        ps_l.addWidget(ps_desc)
        ps_row = QHBoxLayout()
        self._ps_host = QLineEdit()
        self._ps_host.setPlaceholderText("IP or hostname…")
        self._ps_host.setFixedWidth(180)
        from PyQt6.QtWidgets import QComboBox
        self._ps_mode = QComboBox()
        self._ps_mode.addItems(["Normal", "Fast", "Low Impact"])
        self._ps_mode.setFixedWidth(90)
        self._ps_mode.setToolTip(
            "Fast: 100 threads, 0.35s timeout\n"
            "Normal: 50 threads, 0.60s timeout\n"
            "Low Impact: 8 threads, 1.20s timeout, 50ms delay"
        )
        self._btn_ps = QPushButton("Scan Ports")
        self._btn_ps.setObjectName("btnDiag")
        self._btn_ps.setFixedHeight(30)
        self._btn_ps.clicked.connect(
            lambda: self._run_port_scan(self._ps_host.text().strip())
        )
        self._ps_status = QLabel("")
        self._ps_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        ps_row.addWidget(self._ps_host)
        ps_row.addWidget(self._ps_mode)
        ps_row.addWidget(self._btn_ps)
        ps_row.addWidget(self._ps_status, 1)
        ps_l.addLayout(ps_row)
        self._ps_table = _table(["Port", "Service", "Version", "Banner", "Risk"])
        self._ps_table.setColumnWidth(0, 60)
        self._ps_table.setColumnWidth(1, 170)
        self._ps_table.setColumnWidth(2, 180)
        self._ps_table.setColumnWidth(3, 200)
        self._ps_table.setMaximumHeight(220)
        ps_l.addWidget(self._ps_table)
        lay.addWidget(ps_frame)

        # Wake-on-LAN card
        wol_frame = QFrame()
        wol_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        wol_l = QVBoxLayout(wol_frame)
        wol_l.setContentsMargins(16, 12, 16, 12)
        wol_l.setSpacing(6)
        wol_title = QLabel("⚡  Wake-on-LAN")
        wol_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        wol_title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        wol_l.addWidget(wol_title)
        wol_row = QHBoxLayout()
        self._wol_mac = QLineEdit()
        self._wol_mac.setPlaceholderText("MAC address  aa:bb:cc:dd:ee:ff")
        self._wol_mac.setFixedWidth(220)
        self._btn_wol = QPushButton("Send WoL Packet")
        self._btn_wol.setObjectName("btnNetRefresh")
        self._btn_wol.setFixedHeight(30)
        self._btn_wol.clicked.connect(
            lambda: self._send_wol(self._wol_mac.text().strip())
        )
        self._wol_status = QLabel("")
        self._wol_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        wol_row.addWidget(QLabel("MAC:"))
        wol_row.addWidget(self._wol_mac)
        wol_row.addWidget(self._btn_wol)
        wol_row.addWidget(self._wol_status, 1)
        wol_l.addLayout(wol_row)
        lay.addWidget(wol_frame)

        # Device Baseline card
        bl_frame = QFrame()
        bl_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        bl_l = QVBoxLayout(bl_frame)
        bl_l.setContentsMargins(16, 12, 16, 12)
        bl_l.setSpacing(6)
        bl_title = QLabel("📋  New Device Alerts  (baseline diff)")
        bl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        bl_title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        bl_l.addWidget(bl_title)
        bl_desc = QLabel(
            "After each scan, devices not seen before are highlighted here.  "
            "Baseline is saved to ~/Documents/NetSentinel/device_baseline.json."
        )
        bl_desc.setWordWrap(True)
        bl_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        bl_l.addWidget(bl_desc)
        self._bl_new_lbl = QLabel("No scan run yet.")
        self._bl_new_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        bl_l.addWidget(self._bl_new_lbl)
        self._bl_table = _table(["IP", "Hostname", "MAC", "Vendor", "First Seen"])
        self._bl_table.setMaximumHeight(160)
        bl_l.addWidget(self._bl_table)
        lay.addWidget(bl_frame)

        lay.addStretch()
        return w

    # ── MTR handlers ──────────────────────────────────────────────────────────

    @pyqtSlot()
    def _toggle_mtr(self):
        if self._mtr_worker and self._mtr_worker.isRunning():
            self._mtr_worker.stop()
            self._btn_mtr.setText("▶  Start MTR")
            self._mtr_status.setText("MTR stopped.")
            self._mtr_worker = None
        else:
            target = self._mtr_target.text().strip() or "8.8.8.8"
            self._record_recent_action(
                action_id=f"mtr:{target}",
                label=f"Hop-by-hop trace · {target}",
                page="Hop-by-Hop Trace",
                params={"target": target},
            )
            from workers.scan_worker import MTRWorker
            self._mtr_stats = {}
            self._mtr_table.setRowCount(0)
            self._mtr_cycle = 0
            self._mtr_worker = MTRWorker(target=target)
            self._mtr_worker.hop_result.connect(self._on_mtr_hop)
            self._mtr_worker.cycle_done.connect(self._on_mtr_cycle)
            self._mtr_worker.status.connect(self._mtr_status.setText)
            self._mtr_worker.error.connect(self._mtr_status.setText)
            self._mtr_worker.start()
            self._btn_mtr.setText("⏹  Stop MTR")

    @pyqtSlot(int, str, float)
    def _on_mtr_hop(self, hop_n: int, ip: str, rtt: float):
        if hop_n not in self._mtr_stats:
            self._mtr_stats[hop_n] = {"ip": ip, "sent": 0, "lost": 0, "total": 0.0}
        s = self._mtr_stats[hop_n]
        s["sent"] += 1
        if rtt < 0:
            s["lost"] += 1
        else:
            s["total"] += rtt
        s["last"] = rtt

    @pyqtSlot(int)
    def _on_mtr_cycle(self, cycle: int):
        from PyQt6.QtGui import QColor
        self._mtr_cycle = cycle
        self._mtr_table.setRowCount(0)
        for hop_n in sorted(self._mtr_stats):
            s = self._mtr_stats[hop_n]
            sent = s["sent"]
            lost = s["lost"]
            ok = sent - lost
            loss_pct = (lost / sent * 100) if sent else 0
            avg_rtt = (s["total"] / ok) if ok else -1
            last = s.get("last", -1)
            loss_color = RED if loss_pct > 10 else (AMBER if loss_pct > 0 else GREEN)
            row = self._mtr_table.rowCount()
            self._mtr_table.insertRow(row)
            vals = [
                str(hop_n), s["ip"], str(sent),
                f"{loss_pct:.0f}%",
                f"{avg_rtt:.0f} ms" if avg_rtt >= 0 else "—",
                f"{last:.0f} ms" if last >= 0 else "—",
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(loss_color if col == 3 else TEXT_PRIMARY))
                self._mtr_table.setItem(row, col, item)

    # ── Port scan handlers ────────────────────────────────────────────────────

    def _run_port_scan(self, host: str):
        if not host:
            return
        self._record_recent_action(
            action_id=f"ps:{host}",
            label=f"Port scan · {host}",
            page="Tools & Wake-on-LAN",
            params={"host": host},
        )
        from workers.scan_worker import PortScanWorker
        if hasattr(self, "_ps_host"):
            self._ps_host.setText(host)
        self._nav_rail_go_to("Tools & Wake-on-LAN")
        self._ps_table.setRowCount(0)
        mode = self._ps_mode.currentText().lower() if hasattr(self, "_ps_mode") else "normal"
        if hasattr(self, "_ps_status"):
            self._ps_status.setText(f"Scanning {host} ({mode} mode)…")
        self._ps_worker = PortScanWorker(host=host, mode=mode)
        self._ps_worker.result.connect(self._on_port_scan_result)
        self._ps_worker.status.connect(lambda m: self._ps_status.setText(m) if hasattr(self, "_ps_status") else None, Qt.ConnectionType.QueuedConnection)
        self._ps_worker.error.connect(lambda e: self._ps_status.setText(f"Error: {e}") if hasattr(self, "_ps_status") else None, Qt.ConnectionType.QueuedConnection)
        self._ps_worker.start()

    # ── WoL handler ───────────────────────────────────────────────────────────

    def _send_wol(self, mac: str):
        from modules.utils import send_wol
        ok = send_wol(mac)
        msg = f"WoL magic packet sent to {mac}" if ok else f"Invalid MAC address: {mac}"
        color = GREEN if ok else RED
        if hasattr(self, "_wol_status"):
            self._wol_status.setStyleSheet(f"color:{color}; font-size:11px;")
            self._wol_status.setText(msg)
        else:
            self._set_status(msg)

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
        """Show an amber suggestion card on Home when a live lab scenario is ready."""
        self._pending_live_scenario = scenario
        if hasattr(self, "_home_page"):
            self._home_page.set_suggestions([{
                "text": f"Something just happened — {scenario.title.lower()}",
                "action_label": "Investigate →",
                "target": "__live__",
                "priority": "medium",
            }])

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
    def _on_alert_view_requested(self, alert) -> None:
        """Navigate to the most relevant page for the alert that was clicked."""
        # Dict alerts come from the Home action-needed card rows — open the drawer directly
        if isinstance(alert, dict):
            self._nav_rail_go_to("Notifications")
            try:
                if hasattr(self, "_notifications_page"):
                    self._notifications_page._alert_drawer.open(alert)
            except Exception:
                pass
            return
        rule_type = getattr(alert, "rule_type", "") or ""
        host = getattr(alert, "host", "") or ""
        if rule_type == "PORT_SCAN" and host:
            if hasattr(self, "_syn_host"):
                self._syn_host.setText(host)
            self._nav_rail_go_to("Port Scan (TCP)")
        elif rule_type in ("THREAT_INTEL", "CVE") and host:
            if hasattr(self, "_threat_intel_page"):
                self._threat_intel_page.check_ip(host)
            self._nav_rail_go_to("Threat Intelligence")
        elif rule_type == "RATE_SPIKE" and host:
            if hasattr(self, "_live_bandwidth_page"):
                self._live_bandwidth_page.annotate_event("Rate spike", RED)
            self._nav_rail_go_to("Live Bandwidth")
        elif host:
            self._on_inventory_device_selected(host)
        else:
            self._nav_rail_go_to("Notifications")

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
                    "text": f"{high} high-risk device{s} found — review security findings",
                    "action_label": "View Overview →",
                    "target": "Overview",
                    "priority": "high",
                })

        # Stability logger not running
        if not (self._logger_worker and self._logger_worker.isRunning()):
            suggestions.append({
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
                    "text": f"Your network grade is {grade} — run a health check for recommendations",
                    "action_label": "View Overview →",
                    "target": "Overview",
                    "priority": "medium",
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

            self._home_page.set_last_visit_summary(joined_count, outage_count, last_str)
        except Exception:
            pass

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

        # Outage table — AMBER < 5 min, RED ≥ 5 min
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
