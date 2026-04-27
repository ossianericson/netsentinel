"""
Main Dashboard — NetSentinel network security scanner and monitor.
"""

import datetime
import html
import webbrowser
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.live_graph import LiveGraphWidget
from ui.styles import (
    ACCENT, ACCENT_LITE, AMBER, AMBER_BG, BG_CARD, BG_DARK,
    BLUE, GREEN, GREEN_BG, MAIN_STYLE, RED, RED_BG, RISK_BG, RISK_COLORS,
    TEXT_PRIMARY, TEXT_SECONDARY,
)
from modules.utils import get_offenders_path, is_admin


def _color_for_level(level: str) -> str:
    return RISK_COLORS.get(level.upper(), TEXT_SECONDARY)


def _bg_for_level(level: str) -> str:
    return RISK_BG.get(level.upper(), BG_CARD)


class RiskBadge(QLabel):
    def __init__(self, level: str, parent=None):
        super().__init__(level.upper(), parent)
        color = _color_for_level(level)
        bg    = _bg_for_level(level)
        self.setStyleSheet(
            f"color:{color}; background:{bg}; border:1px solid {color};"
            "border-radius:10px; padding:2px 10px; font-weight:bold; font-size:11px;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class VerdictPanel(QFrame):
    """Traffic-light coloured plain-English verdict box."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("verdictFrame")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel("Overall Verdict")
        self._title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))

        self._text = QLabel("Run a scan to see results.")
        self._text.setObjectName("verdictText")
        self._text.setWordWrap(True)
        self._text.setFont(QFont("Segoe UI", 11))
        self._text.setTextFormat(Qt.TextFormat.PlainText)

        self._layout.addWidget(self._title)
        self._layout.addWidget(self._text)
        self._set_level("UNKNOWN")

    def _set_level(self, level: str):
        color = _color_for_level(level)
        bg    = _bg_for_level(level)
        self.setStyleSheet(
            f"QFrame#verdictFrame {{ background:{bg}; border:2px solid {color};"
            "border-radius:12px; padding:4px; }}"
        )
        self._title.setStyleSheet(f"color:{color}; padding:8px 12px 2px 12px;")
        self._text.setStyleSheet(f"color:{TEXT_PRIMARY}; padding:2px 12px 12px 12px;")

    def update(self, text: str, level: str = "UNKNOWN"):
        self._set_level(level)
        self._text.setText(text)


# ─── Module Tab Helpers ─────────────────────────────────────────────────────

def _make_scroll_area(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.setStyleSheet("QScrollArea { border: none; }")
    return sa


def _table(headers: list) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(True)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    return t


def _add_row(table: QTableWidget, values: list, level: str = "CLEAN"):
    row = table.rowCount()
    table.insertRow(row)
    color = _color_for_level(level)
    for col, val in enumerate(values):
        item = QTableWidgetItem(str(val))
        item.setForeground(
            __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(color)
            if level in ("HIGH", "STORM") else
            __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(TEXT_PRIMARY)
        )
        table.setItem(row, col, item)


# ─── Main Window ─────────────────────────────────────────────────────────────

class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetSentinel  —  Network Security Scanner & Monitor")
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(MAIN_STYLE)

        self._offenders_path = get_offenders_path()
        self._admin = is_admin()

        # Scan results cache
        self._m1_result = None
        self._m2_result = None
        self._m3_result = None
        self._m4_result = None
        self._m5_result = None

        # Active workers
        self._workers = []
        self._active_count = 0
        self._prescan_worker = None
        self._diag_worker = None
        self._logger_worker = None

        # Cached results
        self._net_info: dict = {}
        self._diag_result = None

        # Graph update timer
        self._graph_timer = QTimer()
        self._graph_timer.setInterval(500)
        self._graph_timer.timeout.connect(self._refresh_graph)

        # Matrix rain Easter egg
        self._matrix_rain = None

        self._build_ui()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Header
        root.addWidget(self._build_header())

        # Admin warning
        if not self._admin:
            root.addWidget(self._build_admin_warning())

        # Main splitter: tabs (top) + verdict (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_tabs())
        splitter.addWidget(self._build_verdict_area())
        splitter.setSizes([520, 140])
        splitter.setStyleSheet("QSplitter::handle { background: #2a2a4a; height: 2px; }")
        root.addWidget(splitter, 1)

        # Status bar
        self._status_bar = QStatusBar()
        self._status_bar.setStyleSheet(
            f"QStatusBar {{ background:{BG_CARD}; color:{TEXT_SECONDARY}; font-size:11px; }}"
        )
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setFixedHeight(6)
        self._progress.setVisible(False)
        self._status_bar.addPermanentWidget(self._progress)
        self.setStatusBar(self._status_bar)
        self._set_status("Ready. Click RUN FULL SCAN to begin.")
        # Load network info in background on startup
        self._refresh_network_info()
        # Matrix rain overlay (created after window is built)
        from ui.matrix_rain import MatrixRainWidget
        self._matrix_rain = MatrixRainWidget(self.centralWidget())
        # Keyboard shortcut Ctrl+Shift+M
        from PyQt6.QtGui import QKeySequence, QShortcut
        _shortcut = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        _shortcut.activated.connect(self._toggle_matrix_rain)
        # Restore full settings (mode, scan hosts, etc.) after UI is built
        self._restore_settings()

    @pyqtSlot()
    def _toggle_matrix_rain(self):
        if self._matrix_rain:
            self._matrix_rain.toggle()

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background:{BG_CARD}; border-radius:10px;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 14, 20, 14)

        left = QVBoxLayout()
        title = QLabel("NetSentinel")
        title.setObjectName("lblTitle")
        subtitle = QLabel("Network Security Scanner  •  Rogue Device Detector  •  Connectivity Monitor")
        subtitle.setObjectName("lblSubtitle")
        left.addWidget(title)
        left.addWidget(subtitle)

        lay.addLayout(left, 1)
        lay.addStretch()

        # Settings
        settings_box = QGroupBox("Scan Settings")
        settings_box.setStyleSheet(
            f"QGroupBox {{ color:{ACCENT_LITE}; font-size:11px; }}"
        )
        slayout = QHBoxLayout(settings_box)
        slayout.setSpacing(14)

        # STP duration
        lbl_stp = QLabel("STP scan (s):")
        lbl_stp.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._stp_duration = QSpinBox()
        self._stp_duration.setRange(10, 120)
        self._stp_duration.setValue(30)
        self._stp_duration.setFixedWidth(72)
        self._stp_duration.setToolTip("How long to listen for STP/BPDU frames")

        # Storm duration
        lbl_storm = QLabel("Storm (s):")
        lbl_storm.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._storm_duration = QSpinBox()
        self._storm_duration.setRange(5, 60)
        self._storm_duration.setValue(10)
        self._storm_duration.setFixedWidth(72)

        # Module toggles
        self._chk_stp   = QCheckBox("STP")
        self._chk_storm = QCheckBox("Storm")
        self._chk_wifi  = QCheckBox("WiFi")
        self._chk_dns   = QCheckBox("DNS")
        for chk in (self._chk_stp, self._chk_storm, self._chk_wifi, self._chk_dns):
            chk.setChecked(True)
            chk.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")

        slayout.addWidget(lbl_stp)
        slayout.addWidget(self._stp_duration)
        slayout.addWidget(lbl_storm)
        slayout.addWidget(self._storm_duration)
        slayout.addWidget(self._chk_stp)
        slayout.addWidget(self._chk_storm)
        slayout.addWidget(self._chk_wifi)
        slayout.addWidget(self._chk_dns)

        lay.addWidget(settings_box)
        lay.addSpacing(20)

        # Scan button
        self._btn_scan = QPushButton("⚡  RUN FULL SCAN")
        self._btn_scan.setObjectName("btnScan")
        self._btn_scan.setFixedHeight(54)
        self._btn_scan.setMinimumWidth(200)
        self._btn_scan.clicked.connect(self._start_full_scan)
        lay.addWidget(self._btn_scan)

        # Export button
        self._btn_export = QPushButton("📄  Export Report")
        self._btn_export.setObjectName("btnExport")
        self._btn_export.setFixedHeight(54)
        self._btn_export.setMinimumWidth(150)
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export_report)
        lay.addWidget(self._btn_export)

        # Standard / Advanced mode toggle
        self._btn_mode = QPushButton("⚙  Advanced Mode")
        self._btn_mode.setObjectName("btnNetRefresh")
        self._btn_mode.setFixedHeight(54)
        self._btn_mode.setCheckable(True)
        self._btn_mode.setToolTip(
            "Advanced Mode shows MTR, Port Scanner, DNS Leak, and device baseline diff tabs"
        )
        self._btn_mode.toggled.connect(self._on_mode_toggle)
        lay.addWidget(self._btn_mode)

        # Recon mode toggle
        self._btn_recon = QPushButton("🔎  Security Audit Mode")
        self._btn_recon.setObjectName("btnNetRefresh")
        self._btn_recon.setFixedHeight(54)
        self._btn_recon.setCheckable(True)
        self._btn_recon.setToolTip(
            "Security Audit Mode adds SYN stealth scan, UDP scan, full 1000-port range, "
            "deep OS fingerprinting, and per-device risk scoring.\n"
            "Requires administrator privileges and Npcap (Windows)."
        )
        self._btn_recon.toggled.connect(self._on_recon_toggle)
        lay.addWidget(self._btn_recon)

        # OUI database reload
        btn_reload_oui = QPushButton("↺  Reload OUI DB")
        btn_reload_oui.setObjectName("btnNetRefresh")
        btn_reload_oui.setFixedHeight(54)
        btn_reload_oui.setToolTip("Re-read offenders.json without restarting the app")
        btn_reload_oui.clicked.connect(self._reload_oui_db)
        lay.addWidget(btn_reload_oui)

        # About
        btn_about = QPushButton("ℹ  About")
        btn_about.setObjectName("btnNetRefresh")
        btn_about.setFixedHeight(54)
        btn_about.setToolTip("About NetSentinel")
        btn_about.clicked.connect(self._show_about)
        lay.addWidget(btn_about)

        return w

    def _build_admin_warning(self) -> QWidget:
        container = QWidget()
        container.setObjectName("adminWarningBar")
        container.setStyleSheet(
            f"QWidget#adminWarningBar {{ background:{AMBER_BG}; border:1px solid {AMBER}; border-radius:8px; }}"
        )
        row = QHBoxLayout(container)
        row.setContentsMargins(14, 8, 10, 8)
        row.setSpacing(8)

        lbl = QLabel(
            "⚠  Not running as Administrator / root. "
            "Modules 2 (STP) and 3 (Storm) require elevated privileges — they will be skipped. "
            "Re-launch as Admin for full diagnostics."
        )
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{AMBER}; font-size:12px; background:transparent; border:none;")
        row.addWidget(lbl, 1)

        btn_dismiss = QPushButton("✕")
        btn_dismiss.setFixedSize(22, 22)
        btn_dismiss.setToolTip("Dismiss")
        btn_dismiss.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{AMBER}; border:none; font-size:14px; }}"
            f"QPushButton:hover {{ color:#ffffff; }}"
        )
        btn_dismiss.clicked.connect(container.hide)
        row.addWidget(btn_dismiss)

        return container

    # ── Sidebar navigation helpers ───────────────────────────────────────────

    def _nav_add_section(self, label: str):
        """Add a non-selectable section separator to the nav list."""
        item = QListWidgetItem(f"  {label.upper()}")
        item.setFlags(Qt.ItemFlag.NoItemFlags)  # not selectable
        item.setForeground(
            __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("#555570")
        )
        f = item.font()
        f.setPointSize(9)
        f.setBold(True)
        item.setFont(f)
        item.setSizeHint(__import__("PyQt6.QtCore", fromlist=["QSize"]).QSize(0, 26))
        self._nav.addItem(item)
        # Store as separator so we never map it to a page
        self._nav_separators.add(self._nav.count() - 1)

    def _nav_add_page(self, icon_label: str, widget: QWidget, hidden: bool = False) -> int:
        """Add a page to both the nav list and the stacked widget. Returns nav row index."""
        item = QListWidgetItem(f"  {icon_label}")
        item.setSizeHint(__import__("PyQt6.QtCore", fromlist=["QSize"]).QSize(0, 34))
        self._nav.addItem(item)
        page_idx = self._stack.addWidget(widget)
        nav_row  = self._nav.count() - 1
        self._nav_row_to_page[nav_row] = page_idx
        if hidden:
            item.setHidden(True)
        return nav_row

    def _nav_set_page(self, nav_row: int):
        if nav_row in self._nav_row_to_page:
            self._stack.setCurrentIndex(self._nav_row_to_page[nav_row])

    def _nav_show_group(self, nav_rows, visible: bool):
        for row in nav_rows:
            item = self._nav.item(row)
            if item:
                item.setHidden(not visible)

    def _build_tabs(self) -> QWidget:
        # ── Build all page widgets ────────────────────────────────────────────
        m1  = self._build_m1_tab()
        m2  = self._build_m2_tab()
        m3  = self._build_m3_tab()
        m4  = self._build_m4_tab()
        m5  = self._build_m5_tab()
        net = self._build_network_info_tab()
        dia = self._build_diagnostics_tab()
        log = self._build_logger_tab()

        self._mtr_tab_widget      = self._build_mtr_tab()
        self._adv_tab_widget      = self._build_advanced_tools_tab()
        self._topology_tab_widget = self._build_topology_tab()
        self._arp_tab_widget      = self._build_arp_monitor_tab()
        self._dhcp_tab_widget     = self._build_dhcp_tab()
        self._bw_tab_widget       = self._build_bandwidth_tab()
        self._sched_tab_widget    = self._build_scheduler_tab()
        self._snmp_tab_widget     = self._build_snmp_tab()

        self._recon_syn_tab_widget       = self._build_recon_syn_tab()
        self._recon_udp_tab_widget       = self._build_recon_udp_tab()
        self._recon_os_tab_widget        = self._build_recon_os_tab()
        self._recon_risk_tab_widget      = self._build_recon_risk_tab()
        self._recon_cve_tab_widget       = self._build_recon_cve_tab()
        self._recon_exposure_tab_widget  = self._build_recon_exposure_tab()
        self._recon_cred_tab_widget      = self._build_recon_cred_tab()
        self._recon_discovery_tab_widget = self._build_recon_discovery_tab()
        self._recon_smb_tab_widget       = self._build_recon_smb_tab()
        self._recon_plugin_tab_widget    = self._build_recon_plugin_tab()
        self._recon_pe_tab_widget        = self._build_recon_pe_tab()
        self._recon_cloud_tab_widget     = self._build_recon_cloud_metadata_tab()
        self._ipv6_tab_widget            = self._build_ipv6_tab()
        self._correlator_tab_widget      = self._build_correlator_tab()
        self._iot_baseline_tab_widget    = self._build_iot_baseline_tab()
        self._benchmark_tab_widget       = self._build_benchmark_tab()

        # ── Worker refs ───────────────────────────────────────────────────────
        self._arp_worker:        Optional[object] = None
        self._dhcp_worker:       Optional[object] = None
        self._bw_worker:         Optional[object] = None
        self._sched_worker:      Optional[object] = None
        self._snmp_worker:       Optional[object] = None
        self._syn_worker:        Optional[object] = None
        self._udp_worker:        Optional[object] = None
        self._cve_worker:        Optional[object] = None
        self._exposure_worker:   Optional[object] = None
        self._os_worker:         Optional[object] = None
        self._cred_worker:       Optional[object] = None
        self._discovery_worker:  Optional[object] = None
        self._smb_worker:        Optional[object] = None
        self._pe_worker:         Optional[object] = None
        self._ipv6_worker:       Optional[object] = None
        self._cloud_worker:      Optional[object] = None
        self._log_chart_summary: Optional[object] = None   # last loaded LogSummary
        self._last_benchmark_result: Optional[object] = None  # last BenchmarkResult

        # ── Sidebar list + stacked content ────────────────────────────────────
        self._nav = QListWidget()
        self._nav.setFixedWidth(200)
        self._nav.setStyleSheet(
            f"QListWidget {{"
            f"  background: #0f0f22;"
            f"  border: none;"
            f"  outline: none;"
            f"}}"
            f"QListWidget::item {{"
            f"  color: #888899;"
            f"  padding: 0px 8px;"
            f"  border-radius: 6px;"
            f"  margin: 1px 6px;"
            f"  font-size: 12px;"
            f"}}"
            f"QListWidget::item:selected {{"
            f"  background: #2a1a5a;"
            f"  color: #a78bfa;"
            f"  font-weight: bold;"
            f"}}"
            f"QListWidget::item:hover:!selected {{"
            f"  background: #1a1a35;"
            f"  color: #e0e0f0;"
            f"}}"
        )
        self._stack = QStackedWidget()
        self._nav_row_to_page: dict = {}   # nav list row -> stack page index
        self._nav_separators:  set  = set()

        # ── Standard pages ────────────────────────────────────────────────────
        self._nav_add_section("Standard")
        self._nav_add_page("🔍  Devices on Network",    m1)
        self._nav_add_page("🌉  Rogue Bridge (STP)",    m2)
        self._nav_add_page("🌊  Broadcast Storm",        m3)
        self._nav_add_page("📶  WiFi Networks",          m4)
        self._nav_add_page("📡  DNS & Outages",          m5)
        self._nav_add_page("🌐  My Network Info",        net)
        self._nav_add_page("⚡  Health Check",           dia)
        self._nav_add_page("📋  Stability Log",          log)
        self._nav_add_page("🔷  IPv6 Devices",           self._ipv6_tab_widget)
        self._nav_add_page("🧩  Root Cause Analysis",    self._correlator_tab_widget)
        self._nav_add_page("🤖  IoT Behaviour",          self._iot_baseline_tab_widget)
        self._nav_add_page("📊  Network Grade",           self._benchmark_tab_widget)

        # ── Advanced pages (hidden until Advanced Mode) ───────────────────────
        self._nav_adv_sep = self._nav.count()
        self._nav_add_section("Advanced")
        self._nav_adv_rows = [
            self._nav_add_page("🔁  Hop-by-Hop Trace",  self._mtr_tab_widget,      hidden=True),
            self._nav_add_page("🔧  Tools & Wake-on-LAN",self._adv_tab_widget,     hidden=True),
            self._nav_add_page("🗺  Network Map",        self._topology_tab_widget, hidden=True),
            self._nav_add_page("🛡  ARP Spoof Watch",    self._arp_tab_widget,      hidden=True),
            self._nav_add_page("📦  DHCP Leases",        self._dhcp_tab_widget,     hidden=True),
            self._nav_add_page("📊  Bandwidth Usage",    self._bw_tab_widget,       hidden=True),
            self._nav_add_page("🕐  Scheduled Scans",    self._sched_tab_widget,    hidden=True),
            self._nav_add_page("📡  SNMP Device Info",   self._snmp_tab_widget,     hidden=True),
        ]
        # Hide the Advanced section separator too
        adv_sep_item = self._nav.item(self._nav_adv_sep)
        if adv_sep_item:
            adv_sep_item.setHidden(True)
        self._nav_separators.add(self._nav_adv_sep)

        # Track the nav row of Advanced Tools (for port-scan auto-navigate)
        self._adv_tab_index_adv = self._nav_adv_rows[1]   # "🔧  Advanced Tools"
        self._adv_tab_index_mtr = self._nav_adv_rows[0]   # kept for compat

        # ── Recon pages (hidden until Recon Mode) ─────────────────────────────
        self._nav_recon_sep = self._nav.count()
        self._nav_add_section("Security Audit")
        self._nav_recon_rows = [
            self._nav_add_page("⚡  Port Scan (SYN)",        self._recon_syn_tab_widget,       hidden=True),
            self._nav_add_page("📻  Port Scan (UDP)",         self._recon_udp_tab_widget,       hidden=True),
            self._nav_add_page("🖥  OS Detection",            self._recon_os_tab_widget,        hidden=True),
            self._nav_add_page("🎯  Device Risk Score",       self._recon_risk_tab_widget,      hidden=True),
            self._nav_add_page("🛡  Known CVEs",              self._recon_cve_tab_widget,       hidden=True),
            self._nav_add_page("🌐  Exposed to Internet",     self._recon_exposure_tab_widget,  hidden=True),
            self._nav_add_page("🔑  Login Test (SSH/SMB)",    self._recon_cred_tab_widget,      hidden=True),
            self._nav_add_page("🚀  Full Device Discovery",   self._recon_discovery_tab_widget, hidden=True),
            self._nav_add_page("🗂  Windows Shares (SMB)",    self._recon_smb_tab_widget,       hidden=True),
            self._nav_add_page("🔌  Plugin Modules",          self._recon_plugin_tab_widget,    hidden=True),
            self._nav_add_page("🔒  Private Endpoint Check",  self._recon_pe_tab_widget,        hidden=True),
            self._nav_add_page("☁  Cloud Metadata Probe",    self._recon_cloud_tab_widget,     hidden=True),
        ]
        recon_sep_item = self._nav.item(self._nav_recon_sep)
        if recon_sep_item:
            recon_sep_item.setHidden(True)
        self._nav_separators.add(self._nav_recon_sep)
        self._recon_tab_start_index = -1  # kept for compat

        # ── Wire selection signal ─────────────────────────────────────────────
        self._nav.currentRowChanged.connect(self._on_nav_row_changed)
        # Select first real page
        self._nav.setCurrentRow(1)

        # ── Assemble sidebar + content ────────────────────────────────────────
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._nav)
        # thin divider line
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet("background: #2a2a4a; max-width: 1px;")
        h.addWidget(div)
        h.addWidget(self._stack, 1)

        # Copy-to-clipboard right-click menus
        for tbl in (
            self._m1_table, self._m2_table, self._m3_table, self._m4_table,
            self._m5_outage_table, self._net_devices_table, self._adapters_table,
            self._diag_ping_table, self._diag_dns_table, self._diag_trace_table,
            self._diag_leak_table, self._log_live_table, self._log_outage_table,
            self._mtr_table, self._ps_table, self._bl_table,
            self._arp_table, self._dhcp_table, self._bw_table, self._snmp_table,
            self._recon_syn_table, self._recon_udp_table,
            self._recon_os_table, self._recon_risk_table, self._recon_cve_table,
            self._recon_exposure_table,
            self._recon_cred_sw_table, self._recon_cred_svc_table,
            self._recon_cred_user_table, self._recon_disc_table,
            self._recon_smb_shares_table, self._recon_smb_users_table,
            self._ipv6_table, self._cloud_network_table,
        ):
            self._enable_copy_menu(tbl)

        # Keep self._tabs pointing at something for any legacy code that checks it
        self._tabs = container
        return container

    @pyqtSlot(int)
    def _on_nav_row_changed(self, row: int):
        """Skip separator rows and switch the stacked page."""
        if row in self._nav_separators or row < 0:
            # Jump to the next real row below
            for next_row in range(row + 1, self._nav.count()):
                if next_row not in self._nav_separators:
                    item = self._nav.item(next_row)
                    if item and not item.isHidden():
                        self._nav.setCurrentRow(next_row)
                        return
            return
        self._nav_set_page(row)

    @pyqtSlot(bool)
    def _on_mode_toggle(self, advanced: bool):
        if advanced:
            self._btn_mode.setText("⚙  Standard Mode")
            adv_sep = self._nav.item(self._nav_adv_sep)
            if adv_sep:
                adv_sep.setHidden(False)
            self._nav_show_group(self._nav_adv_rows, True)
        else:
            self._btn_mode.setText("⚙  Advanced Mode")
            adv_sep = self._nav.item(self._nav_adv_sep)
            if adv_sep:
                adv_sep.setHidden(True)
            self._nav_show_group(self._nav_adv_rows, False)
            # Also disable Recon if it was on
            if self._btn_recon.isChecked():
                self._btn_recon.setChecked(False)
            # If current page is an advanced/recon one, jump back to page 1
            cur = self._nav.currentRow()
            if cur in self._nav_adv_rows or cur in self._nav_recon_rows:
                self._nav.setCurrentRow(1)

    @pyqtSlot(bool)
    def _on_recon_toggle(self, recon: bool):
        if recon:
            if not self._btn_mode.isChecked():
                self._btn_mode.setChecked(True)
            self._btn_recon.setText("🔎  Security Audit Mode")
            recon_sep = self._nav.item(self._nav_recon_sep)
            if recon_sep:
                recon_sep.setHidden(False)
            self._nav_show_group(self._nav_recon_rows, True)
        else:
            self._btn_recon.setText("🔍  Security Audit Mode")
            recon_sep = self._nav.item(self._nav_recon_sep)
            if recon_sep:
                recon_sep.setHidden(True)
            self._nav_show_group(self._nav_recon_rows, False)
            cur = self._nav.currentRow()
            if cur in self._nav_recon_rows:
                self._nav.setCurrentRow(1)

    # ── Module 1 ──────────────────────────────────────────────────────────────

    def _build_m1_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        self._m1_status = QLabel("Not yet scanned.")
        self._m1_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        # ── NL query search bar ───────────────────────────────────────────────
        self._m1_search = QLineEdit()
        self._m1_search.setPlaceholderText(
            '🔍  Filter: "show risky devices"  ·  "find cameras"  ·  "list RDP"  ·  (clear to reset)'
        )
        self._m1_search.setStyleSheet(
            f"background:#0d0d1e; color:{TEXT_PRIMARY}; border:1px solid #2a2a4a;"
            "border-radius:6px; padding:5px 8px; font-size:12px;"
        )
        self._m1_search.textChanged.connect(self._filter_m1_by_nl)
        lay.addWidget(self._m1_search)

        self._m1_table = _table([
            "IP Address", "Hostname", "MAC Address", "Vendor", "Risk", "Device Type", "Verdict"
        ])
        self._m1_table.setColumnWidth(0, 120)
        self._m1_table.setColumnWidth(1, 160)
        self._m1_table.setColumnWidth(2, 145)
        self._m1_table.setColumnWidth(3, 180)
        self._m1_table.setColumnWidth(4, 70)
        self._m1_table.setColumnWidth(5, 145)

        # Right-click context menu
        self._m1_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m1_table.customContextMenuRequested.connect(self._m1_context_menu)

        lay.addWidget(self._m1_status)
        lay.addWidget(self._m1_table)
        return w

    def _m1_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m1_table.rowAtIndex(pos) if hasattr(self._m1_table, 'rowAtIndex') \
              else self._m1_table.rowAt(pos.y())
        if row < 0:
            return
        ip  = (self._m1_table.item(row, 0) or QTableWidgetItem()).text()
        mac = (self._m1_table.item(row, 2) or QTableWidgetItem()).text()
        menu = QMenu(self)
        menu.setStyleSheet(f"background:#1e1e3a; color:{TEXT_PRIMARY}; border:1px solid #2a2a4a;")
        act_scan = menu.addAction(f"🔍  Port scan  {ip}")
        act_wol  = menu.addAction(f"⚡  Wake-on-LAN  →  {mac}")
        menu.addSeparator()
        act_fix  = menu.addAction("🔧  How to Fix")
        menu.addSeparator()
        act_copy_ip  = menu.addAction("📋  Copy IP")
        act_copy_mac = menu.addAction("📋  Copy MAC")
        act_copy_row = menu.addAction("📋  Copy full row")
        chosen = menu.exec(self._m1_table.viewport().mapToGlobal(pos))
        if chosen == act_scan:
            self._run_port_scan(ip)
        elif chosen == act_wol:
            self._send_wol(mac)
        elif chosen == act_fix:
            # find remediation from stored result
            rem = ""
            if self._m1_result:
                for d in self._m1_result.get("devices", []):
                    d_ip = getattr(d, "ip", d.get("ip","")) if not isinstance(d, dict) else d.get("ip","")
                    if d_ip == ip:
                        rem = getattr(d, "remediation", d.get("remediation","")) if not isinstance(d, dict) else d.get("remediation","")
                        break
            self._show_how_to_fix(ip, rem or "No specific remediation available for this device.")
        elif chosen == act_copy_ip:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(ip)
        elif chosen == act_copy_mac:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(mac)
        elif chosen == act_copy_row:
            from PyQt6.QtWidgets import QApplication
            parts = []
            for col in range(self._m1_table.columnCount()):
                item = self._m1_table.item(row, col)
                parts.append(item.text() if item else "")
            QApplication.clipboard().setText("\t".join(parts))

    # ── Module 2 ──────────────────────────────────────────────────────────────

    def _build_m2_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        self._m2_status = QLabel("Not yet scanned.")
        self._m2_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        self._m2_table = _table([
            "Source MAC", "BPDU Type", "Root MAC", "Bridge Priority",
            "Hello (s)", "MaxAge (s)", "FwdDelay (s)", "Rogue?"
        ])
        self._m2_table.setColumnWidth(0, 150)
        self._m2_table.setColumnWidth(1, 80)
        self._m2_table.setColumnWidth(2, 150)
        self._m2_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m2_table.customContextMenuRequested.connect(self._m2_context_menu)

        lay.addWidget(self._m2_status)
        lay.addWidget(self._m2_table)
        return w

    def _m2_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m2_table.rowAt(pos.y())
        if row < 0:
            return
        src_mac = (self._m2_table.item(row, 0) or QTableWidgetItem()).text()
        is_rogue = (self._m2_table.item(row, 7) or QTableWidgetItem()).text().strip().upper() in ("YES", "TRUE", "ROGUE")
        menu = QMenu(self)
        menu.setStyleSheet(f"background:#1e1e3a; color:{TEXT_PRIMARY}; border:1px solid #2a2a4a;")
        act_fix  = menu.addAction("🔧  How to Fix")
        menu.addSeparator()
        act_copy = menu.addAction("📋  Copy MAC")
        chosen = menu.exec(self._m2_table.viewport().mapToGlobal(pos))
        if chosen == act_fix:
            if is_rogue:
                rem = (
                    f"A rogue STP Root Bridge was detected from {src_mac}. "
                    "Disconnect the Ethernet cable from this device immediately. "
                    "If it is a mesh satellite (e.g. Google Nest, TP-Link Deco), it must use "
                    "Wi-Fi backhaul only — do not connect it via Ethernet. "
                    "After disconnecting, wait 60 seconds for the real router to reclaim the Root Bridge role, "
                    "then re-run this scan to confirm the network is stable."
                )
            else:
                rem = (
                    f"Device {src_mac} is sending STP BPDUs but is not currently rated as rogue. "
                    "This is expected for your main router or managed switch. "
                    "If you see repeated outages, verify this MAC belongs to your router."
                )
            self._show_how_to_fix(src_mac, rem)
        elif chosen == act_copy:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(src_mac)

    # ── Module 3 ──────────────────────────────────────────────────────────────

    def _build_m3_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        self._m3_status = QLabel("Not yet scanned.")
        self._m3_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        # Stats row
        stats = QHBoxLayout()
        self._m3_bcast_lbl  = self._stat_label("Broadcast/s", "—")
        self._m3_mcast_lbl  = self._stat_label("Multicast/s", "—")
        self._m3_ratio_lbl  = self._stat_label("Bcast ratio", "—")
        self._m3_level_lbl  = self._stat_label("Storm level", "—")
        for w2 in (self._m3_bcast_lbl, self._m3_mcast_lbl,
                   self._m3_ratio_lbl, self._m3_level_lbl):
            stats.addWidget(w2)
        stats.addStretch()

        self._m3_table = _table(["Source MAC", "Broadcast Packets", "Rogue Match?"])
        self._m3_table.setColumnWidth(0, 160)
        self._m3_table.setColumnWidth(1, 160)
        self._m3_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m3_table.customContextMenuRequested.connect(self._m3_context_menu)

        lay.addWidget(self._m3_status)
        lay.addLayout(stats)
        lay.addWidget(self._m3_table)
        return w

    def _m3_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m3_table.rowAt(pos.y())
        if row < 0:
            return
        src_mac = (self._m3_table.item(row, 0) or QTableWidgetItem()).text()
        bcast   = (self._m3_table.item(row, 1) or QTableWidgetItem()).text()
        menu = QMenu(self)
        menu.setStyleSheet(f"background:#1e1e3a; color:{TEXT_PRIMARY}; border:1px solid #2a2a4a;")
        act_fix  = menu.addAction("🔧  How to Fix")
        act_copy = menu.addAction("📋  Copy MAC")
        chosen = menu.exec(self._m3_table.viewport().mapToGlobal(pos))
        if chosen == act_fix:
            rem = (
                f"Device {src_mac} sent {bcast} broadcast packets. "
                "To resolve a broadcast storm: "
                "1. Identify the physical device using the MAC address "
                "(check your router's DHCP table). "
                "2. Restart or reboot that device. "
                "3. Check for firmware updates — faulty firmware is a common cause. "
                "4. If the storm continues, disconnect the device from the network "
                "and move it to a separate VLAN or guest network. "
                "5. High broadcast rates from IoT devices (cameras, smart plugs) often indicate "
                "a failing device that needs replacement."
            )
            self._show_how_to_fix(src_mac, rem)
        elif chosen == act_copy:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(src_mac)

    # ── Module 4 ──────────────────────────────────────────────────────────────

    def _build_m4_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        self._m4_status = QLabel("Not yet scanned.")
        self._m4_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        self._m4_table = _table([
            "SSID", "BSSID", "Channel", "Band", "Signal (dBm)",
            "Hidden?", "Rogue SSID?", "Co-Channel?"
        ])
        self._m4_table.setColumnWidth(0, 180)
        self._m4_table.setColumnWidth(1, 150)

        lay.addWidget(self._m4_status)
        lay.addWidget(self._m4_table)
        return w

    # ── Module 5 ──────────────────────────────────────────────────────────────

    def _build_m5_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        self._m5_status = QLabel("Not yet scanned.")
        self._m5_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        self._graph = LiveGraphWidget()
        self._graph.setMinimumHeight(220)

        self._m5_outage_table = _table([
            "Target", "Duration (s)", "Consecutive Drops", "STP Signature?", "Severity"
        ])

        lay.addWidget(self._m5_status)
        lay.addWidget(self._graph, 2)
        lay.addWidget(QLabel("Detected Outages:"))
        lay.addWidget(self._m5_outage_table, 1)
        return w

    # ── Network Info tab ──────────────────────────────────────────────────────

    def _build_network_info_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Header row
        hdr = QHBoxLayout()
        hdr_lbl = QLabel("🌐  Network Configuration")
        hdr_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        hdr_lbl.setStyleSheet(f"color:{ACCENT_LITE};")
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        self._btn_net_refresh = QPushButton("↺  Refresh")
        self._btn_net_refresh.setObjectName("btnNetRefresh")
        self._btn_net_refresh.clicked.connect(self._refresh_network_info)
        hdr.addWidget(self._btn_net_refresh)
        lay.addLayout(hdr)

        # Info card
        self._net_info_card = QFrame()
        self._net_info_card.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid #2a2a4a; border-radius:10px;"
        )
        self._net_card_layout = QVBoxLayout(self._net_info_card)
        self._net_card_layout.setContentsMargins(18, 14, 18, 14)
        self._net_card_layout.setSpacing(8)

        self._net_info_label = QLabel("Loading network information…")
        self._net_info_label.setWordWrap(True)
        self._net_info_label.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        self._net_card_layout.addWidget(self._net_info_label)

        lay.addWidget(self._net_info_card)

        # Router links card
        router_frame = QFrame()
        router_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid #2a2a4a; border-radius:10px;"
        )
        rl = QVBoxLayout(router_frame)
        rl.setContentsMargins(18, 14, 18, 14)
        rl.setSpacing(6)
        rl_title = QLabel("🔗  Router / Modem Admin Panel")
        rl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        rl_title.setStyleSheet(f"color:{ACCENT_LITE};")
        rl.addWidget(rl_title)
        rl_desc = QLabel(
            "Click a link below to open your router's admin page in a browser.\n"
            "Most home routers use http://192.168.x.1 — Huawei 5G modems also "
            "have /html/index.html"
        )
        rl_desc.setWordWrap(True)
        rl_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        rl.addWidget(rl_desc)

        self._router_links_layout = QHBoxLayout()
        self._router_links_layout.setSpacing(10)
        rl.addLayout(self._router_links_layout)
        lay.addWidget(router_frame)

        # ── OS network settings shortcuts ─────────────────────────────────────
        os_frame = QFrame()
        os_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid #2a2a4a; border-radius:10px;"
        )
        os_l = QVBoxLayout(os_frame)
        os_l.setContentsMargins(18, 12, 18, 12)
        os_l.setSpacing(6)
        os_title = QLabel("⚙️  Network Settings Shortcuts")
        os_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        os_title.setStyleSheet(f"color:{ACCENT_LITE};")
        os_l.addWidget(os_title)
        os_btn_row = QHBoxLayout()
        os_btn_row.setSpacing(8)
        self._os_setting_btns: list = []
        import platform as _plat
        _sys = _plat.system()
        if _sys == "Windows":
            _shortcuts = [
                ("📶  Wi-Fi Settings",       "ms-settings:network-wifi"),
                ("🔌  Ethernet Settings",    "ms-settings:network-ethernet"),
                ("🌐  Network Status",       "ms-settings:network-status"),
                ("🔒  VPN Settings",         "ms-settings:network-vpn"),
                ("🛡  Firewall & Security",  "ms-settings:windowsdefender"),
            ]
        elif _sys == "Darwin":
            _shortcuts = [
                ("📶  Network Preferences",  "x-apple.systempreferences:com.apple.preference.network"),
                ("📋  Wireless Diagnostics", "open://"),  # fallback — handled below
            ]
        else:
            _shortcuts = []
        for label, uri in _shortcuts:
            btn = QPushButton(label)
            btn.setObjectName("btnNetRefresh")
            btn.setFixedHeight(30)
            btn.setToolTip(f"Open {uri}")
            if uri.startswith("ms-settings:"):
                btn.clicked.connect(lambda _c=False, u=uri: __import__('os').startfile(u))
            elif uri.startswith("x-apple"):
                btn.clicked.connect(
                    lambda _c=False, u=uri: __import__('subprocess').run(
                        ["open", u], capture_output=True
                    )
                )
            os_btn_row.addWidget(btn)
        os_btn_row.addStretch()
        os_l.addLayout(os_btn_row)
        lay.addWidget(os_frame)

        # ── DHCP lease card ───────────────────────────────────────────────────
        dhcp_frame = QFrame()
        dhcp_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid #2a2a4a; border-radius:10px;"
        )
        dhcp_l = QVBoxLayout(dhcp_frame)
        dhcp_l.setContentsMargins(18, 12, 18, 12)
        dhcp_l.setSpacing(4)
        dhcp_title = QLabel("🕐  DHCP Lease  &  Adapter Details")
        dhcp_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        dhcp_title.setStyleSheet(f"color:{ACCENT_LITE};")
        dhcp_l.addWidget(dhcp_title)
        self._dhcp_label = QLabel("Loading…")
        self._dhcp_label.setWordWrap(True)
        self._dhcp_label.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        dhcp_l.addWidget(self._dhcp_label)
        lay.addWidget(dhcp_frame)

        # ── Adapters table ────────────────────────────────────────────────────
        adp_lbl = QLabel("  Network Adapters")
        adp_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(adp_lbl)
        self._adapters_table = _table([
            "Adapter Name", "Type", "IPv4", "MAC Address", "Speed", "WiFi Signal", "SSID", "Status"
        ])
        self._adapters_table.setColumnWidth(0, 180)
        self._adapters_table.setColumnWidth(1, 70)
        self._adapters_table.setColumnWidth(2, 115)
        self._adapters_table.setColumnWidth(3, 140)
        self._adapters_table.setColumnWidth(4, 80)
        self._adapters_table.setColumnWidth(5, 90)
        self._adapters_table.setColumnWidth(6, 140)
        self._adapters_table.setMaximumHeight(130)
        lay.addWidget(self._adapters_table)

        # ── All-devices table (populated after scan) ──────────────────────────
        dev_lbl = QLabel("  All Devices Seen on This Network  (populated after scan)")
        dev_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(dev_lbl)

        self._net_devices_table = _table([
            "IP Address", "Hostname", "MAC Address", "Vendor", "Risk"
        ])
        self._net_devices_table.setColumnWidth(0, 120)
        self._net_devices_table.setColumnWidth(1, 180)
        self._net_devices_table.setColumnWidth(2, 145)
        self._net_devices_table.setColumnWidth(3, 200)
        lay.addWidget(self._net_devices_table, 1)
        return w

    def _update_net_info_ui(self, info: dict):
        """Populate the Network Info tab from a get_network_info() dict."""
        self._net_info = info

        lines = []
        for entry in info.get("local_ips", []):
            mask = f" / {entry['mask']}" if entry.get("mask") else ""
            lines.append(
                f"<b>Local IP:</b>  {entry['ip']}{mask}"
                f"  <span style='color:{TEXT_SECONDARY}'>(adapter: {entry['adapter']})</span>"
            )
        gw = info.get("gateway")
        if gw:
            lines.append(f"<b>Default Gateway:</b>  {gw}")
        dns = info.get("dns_servers", [])
        if dns:
            lines.append(f"<b>DNS Servers:</b>  {',  '.join(dns)}")
        domain = info.get("domain", "")
        if domain:
            lines.append(f"<b>Domain:</b>  {domain}")

        self._net_info_label.setTextFormat(Qt.TextFormat.RichText)
        self._net_info_label.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:12px; line-height:1.8;")
        self._net_info_label.setText("<br>".join(lines) if lines else "No network information available.")

        # Rebuild router links
        while self._router_links_layout.count():
            item = self._router_links_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if gw:
            for label, url in [
                (f"http://{gw}/",                    f"http://{gw}/"),
                (f"http://{gw}/html/index.html",     f"http://{gw}/html/index.html"),
                (f"https://{gw}/",                   f"https://{gw}/"),
            ]:
                btn = QPushButton(label)
                btn.setObjectName("btnRouterLink")
                btn.setToolTip(f"Open {url} in your browser")
                btn.clicked.connect(lambda _checked, u=url: webbrowser.open(u))
                self._router_links_layout.addWidget(btn)
        self._router_links_layout.addStretch()

        # ── Populate DHCP lease ──────────────────────────────────────────────
        dhcp = info.get("dhcp", {})
        dhcp_parts = []
        if dhcp.get("dhcp_enabled"):
            if dhcp.get("dhcp_server"):
                dhcp_parts.append(f"<b>DHCP Server:</b>  {dhcp['dhcp_server']}")
            if dhcp.get("lease_obtained"):
                dhcp_parts.append(f"<b>Lease Obtained:</b>  {dhcp['lease_obtained']}")
            if dhcp.get("lease_expires"):
                dhcp_parts.append(f"<b>Lease Expires:</b>  {dhcp['lease_expires']}")
            if dhcp.get("lease_duration_h"):
                dhcp_parts.append(
                    f"<b>Lease Duration:</b>  {dhcp['lease_duration_h']:.0f} h"
                )
        elif dhcp.get("dhcp_enabled") is False:
            dhcp_parts.append("DHCP is disabled on this adapter (static IP)")
        else:
            dhcp_parts.append("DHCP lease information not available.")
        self._dhcp_label.setTextFormat(Qt.TextFormat.RichText)
        self._dhcp_label.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; line-height:1.8;")
        self._dhcp_label.setText("  " + "&nbsp;&nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;".join(dhcp_parts))

        # ── Populate adapters table ──────────────────────────────────────────
        from PyQt6.QtGui import QColor
        self._adapters_table.setRowCount(0)
        for a in info.get("adapters", []):
            row = self._adapters_table.rowCount()
            self._adapters_table.insertRow(row)
            connected = a.get("connected", False)
            row_color = TEXT_PRIMARY if connected else TEXT_SECONDARY
            speed = a.get("speed_mbps", 0)
            speed_str = f"{speed} Mbps" if speed else "—"
            sig = a.get("signal_pct", -1)
            sig_str = f"{sig}%" if sig >= 0 else "—"
            status_str = "Connected" if connected else "Disconnected"
            status_color = GREEN if connected else RED
            vals = [
                a.get("name", ""),
                a.get("type", ""),
                a.get("ipv4", "—"),
                a.get("mac", "—"),
                speed_str,
                sig_str,
                a.get("ssid", ""),
                status_str,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                c = status_color if col == 7 else row_color
                item.setForeground(QColor(c))
                self._adapters_table.setItem(row, col, item)

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
        title.setStyleSheet(f"color:{ACCENT_LITE};")
        top.addWidget(title)
        top.addStretch()
        self._btn_diag = QPushButton("⚡  Run Diagnostics")
        self._btn_diag.setObjectName("btnDiag")
        self._btn_diag.setFixedHeight(38)
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
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ── Top controls ──────────────────────────────────────────────────────
        top = QHBoxLayout()
        title = QLabel("📋  Background Network Logger")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{ACCENT_LITE};")
        top.addWidget(title)
        top.addStretch()

        # Interval spinner
        int_lbl = QLabel("Interval (s):")
        int_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._log_interval = QSpinBox()
        self._log_interval.setRange(5, 3600)
        self._log_interval.setValue(60)
        self._log_interval.setFixedWidth(70)
        self._log_interval.setToolTip("How often to ping each host (seconds)")

        self._btn_log_start = QPushButton("▶  Start Logger")
        self._btn_log_start.setObjectName("btnDiag")
        self._btn_log_start.setFixedHeight(34)
        self._btn_log_start.clicked.connect(self._toggle_logger)

        self._btn_log_open = QPushButton("📂  Open Log File")
        self._btn_log_open.setFixedHeight(34)
        self._btn_log_open.setEnabled(False)
        self._btn_log_open.clicked.connect(self._open_log_file)

        self._btn_log_analyse = QPushButton("🔍  Load & Analyse Log")
        self._btn_log_analyse.setFixedHeight(34)
        self._btn_log_analyse.clicked.connect(self._load_log_file)

        self._btn_log_chart = QPushButton("📊  View Chart")
        self._btn_log_chart.setFixedHeight(34)
        self._btn_log_chart.setEnabled(False)
        self._btn_log_chart.setToolTip("Render loaded log as RTT chart (opens interactive window)")
        self._btn_log_chart.clicked.connect(self._view_log_chart)

        top.addWidget(int_lbl)
        top.addWidget(self._log_interval)
        top.addSpacing(10)
        top.addWidget(self._btn_log_start)
        top.addWidget(self._btn_log_open)
        top.addWidget(self._btn_log_analyse)
        top.addWidget(self._btn_log_chart)
        lay.addLayout(top)

        # ── Optional measurement checkboxes ────────────────────────────────────
        opt_row = QHBoxLayout()
        opt_lbl = QLabel("Optional measurements each cycle:")
        opt_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        opt_row.addWidget(opt_lbl)
        self._log_chk_jitter = QCheckBox("Jitter  (3× ping)")
        self._log_chk_dns    = QCheckBox("DNS latency")
        self._log_chk_http   = QCheckBox("HTTP check")
        self._log_chk_arp    = QCheckBox("ARP watch")
        for chk in (self._log_chk_jitter, self._log_chk_dns,
                    self._log_chk_http, self._log_chk_arp):
            chk.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
            opt_row.addWidget(chk)
        opt_row.addStretch()
        lay.addLayout(opt_row)

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
            "border:1px solid #2a2a4a; border-radius:6px; padding:6px;"
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
        self._log_live_table = _table(["Timestamp", "Host", "RTT (ms)", "Jitter", "DNS (ms)", "HTTP", "ARP Event", "Status"])
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
        title.setStyleSheet(f"color:{ACCENT_LITE};")
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
        title.setStyleSheet(f"color:{ACCENT_LITE};")
        lay.addWidget(title)

        # Port Scanner card
        ps_frame = QFrame()
        ps_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid #2a2a4a; border-radius:10px;"
        )
        ps_l = QVBoxLayout(ps_frame)
        ps_l.setContentsMargins(16, 12, 16, 12)
        ps_l.setSpacing(6)
        ps_title = QLabel("🔍  Port Scanner")
        ps_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ps_title.setStyleSheet(f"color:{ACCENT_LITE};")
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
            f"background:{BG_CARD}; border:1px solid #2a2a4a; border-radius:10px;"
        )
        wol_l = QVBoxLayout(wol_frame)
        wol_l.setContentsMargins(16, 12, 16, 12)
        wol_l.setSpacing(6)
        wol_title = QLabel("⚡  Wake-on-LAN")
        wol_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        wol_title.setStyleSheet(f"color:{ACCENT_LITE};")
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
            f"background:{BG_CARD}; border:1px solid #2a2a4a; border-radius:10px;"
        )
        bl_l = QVBoxLayout(bl_frame)
        bl_l.setContentsMargins(16, 12, 16, 12)
        bl_l.setSpacing(6)
        bl_title = QLabel("📋  New Device Alerts  (baseline diff)")
        bl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        bl_title.setStyleSheet(f"color:{ACCENT_LITE};")
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
        from workers.scan_worker import PortScanWorker
        self._ps_table.setRowCount(0)
        mode = self._ps_mode.currentText().lower() if hasattr(self, "_ps_mode") else "normal"
        if hasattr(self, "_ps_status"):
            self._ps_status.setText(f"Scanning {host} ({mode} mode)…")
        self._ps_worker = PortScanWorker(host=host, mode=mode)
        self._ps_worker.result.connect(self._on_port_scan_result)
        self._ps_worker.status.connect(lambda m: self._ps_status.setText(m) if hasattr(self, "_ps_status") else None)
        self._ps_worker.error.connect(lambda e: self._ps_status.setText(f"Error: {e}") if hasattr(self, "_ps_status") else None)
        self._ps_worker.start()

    @pyqtSlot(object)
    def _on_port_scan_result(self, data):
        from PyQt6.QtGui import QColor
        self._last_portscan_result = data   # cache for Nmap XML export
        self._ps_table.setRowCount(0)
        for p in data.open_ports:
            row = self._ps_table.rowCount()
            self._ps_table.insertRow(row)
            risk_color = RED if p.risk == "HIGH" else TEXT_PRIMARY
            for col, val in enumerate([str(p.port), p.name, p.service_version or "", p.banner or "", p.risk]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(risk_color if col in (1, 4) else TEXT_PRIMARY))
                self._ps_table.setItem(row, col, item)
        if hasattr(self, "_ps_status"):
            self._ps_status.setText(data.plain_verdict)
        if self._adv_tab_index_adv >= 0:
            self._nav.setCurrentRow(self._adv_tab_index_adv)

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
        else:
            # Start
            from workers.scan_worker import LoggerWorker
            interval = self._log_interval.value()
            self._logger_worker = LoggerWorker(
                interval_s=interval,
                enable_jitter=self._log_chk_jitter.isChecked(),
                enable_dns=self._log_chk_dns.isChecked(),
                enable_http=self._log_chk_http.isChecked(),
                enable_arp=self._log_chk_arp.isChecked(),
            )
            self._logger_worker.entry_received.connect(self._on_log_entry)
            self._logger_worker.status.connect(self._log_status_lbl.setText)
            self._logger_worker.error.connect(
                lambda e: self._log_status_lbl.setText(f"Error: {e}")
            )
            self._logger_worker.start()
            self._btn_log_start.setText("⏹  Stop Logger")
            self._btn_log_open.setEnabled(False)
            self._log_live_table.setRowCount(0)
            self._log_outage_table.setRowCount(0)

    @pyqtSlot(object)
    def _on_log_entry(self, entry):
        """Called from LoggerWorker for each new ping result."""
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
                # Update MatrixRain colour from live stability score
                if self._matrix_rain:
                    self._matrix_rain.set_stability_score(summary.uptime_pct)
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

    def _open_log_file(self):
        """Open the log CSV in the default text editor / Excel."""
        if self._logger_worker and self._logger_worker.log_file:
            path = self._logger_worker.log_file
            if path.exists():
                webbrowser.open(path.as_uri())

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

    # ── IPv6 tab ──────────────────────────────────────────────────────────────

    def _build_ipv6_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("🔷  IPv6 Devices")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{ACCENT_LITE};")
        top.addWidget(title)
        top.addStretch()
        self._btn_ipv6_scan = QPushButton("▶  Scan IPv6")
        self._btn_ipv6_scan.setObjectName("btnDiag")
        self._btn_ipv6_scan.setFixedHeight(34)
        self._btn_ipv6_scan.clicked.connect(self._start_ipv6_scan)
        top.addWidget(self._btn_ipv6_scan)
        lay.addLayout(top)

        self._ipv6_status = QLabel(
            "Reads the OS IPv6 neighbour cache, then actively pings fe80::/8 on each interface."
        )
        self._ipv6_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._ipv6_status)

        self._ipv6_table = _table(["IPv6 Address", "MAC Address", "State", "Source"])
        self._ipv6_table.setColumnWidth(0, 340)
        self._ipv6_table.setColumnWidth(1, 150)
        self._ipv6_table.setColumnWidth(2, 110)
        self._ipv6_table.setColumnWidth(3, 80)
        lay.addWidget(self._ipv6_table, 1)
        return w

    @pyqtSlot()
    def _start_ipv6_scan(self):
        if self._ipv6_worker and self._ipv6_worker.isRunning():
            return
        from workers.scan_worker import IPv6Worker
        self._ipv6_table.setRowCount(0)
        self._btn_ipv6_scan.setEnabled(False)
        self._ipv6_worker = IPv6Worker()
        self._ipv6_worker.result.connect(self._on_ipv6_result)
        self._ipv6_worker.status.connect(self._ipv6_status.setText)
        self._ipv6_worker.error.connect(
            lambda e: self._ipv6_status.setText(f"⚠ {e}")
        )
        self._ipv6_worker.finished.connect(
            lambda: self._btn_ipv6_scan.setEnabled(True)
        )
        self._ipv6_worker.start()

    @pyqtSlot(list)
    def _on_ipv6_result(self, devices: list):
        from PyQt6.QtGui import QColor
        self._ipv6_table.setRowCount(0)
        for d in devices:
            row = self._ipv6_table.rowCount()
            self._ipv6_table.insertRow(row)
            source_color = ACCENT_LITE if d.get("source") == "active" else TEXT_SECONDARY
            state_color  = GREEN if d.get("state", "").upper() == "REACHABLE" else TEXT_SECONDARY
            for col, val in enumerate([
                d.get("ip6", ""), d.get("mac", ""),
                d.get("state", ""), d.get("source", ""),
            ]):
                item = QTableWidgetItem(str(val))
                if col == 2:
                    item.setForeground(QColor(state_color))
                elif col == 3:
                    item.setForeground(QColor(source_color))
                else:
                    item.setForeground(QColor(TEXT_PRIMARY))
                self._ipv6_table.setItem(row, col, item)
        self._ipv6_status.setText(
            f"{len(devices)} IPv6 device(s) found  "
            f"({sum(1 for d in devices if d.get('source')=='active')} via active sweep, "
            f"{sum(1 for d in devices if d.get('source')=='cache')} from cache)"
        )

    # ── Cloud Metadata tab (Recon) ────────────────────────────────────────────

    def _build_recon_cloud_metadata_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("☁  Cloud Metadata Detection")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{ACCENT_LITE};")
        top.addWidget(title)
        top.addStretch()
        self._btn_cloud_scan = QPushButton("▶  Run Check")
        self._btn_cloud_scan.setObjectName("btnDiag")
        self._btn_cloud_scan.setFixedHeight(34)
        self._btn_cloud_scan.clicked.connect(self._start_cloud_metadata)
        top.addWidget(self._btn_cloud_scan)
        lay.addLayout(top)

        self._cloud_status = QLabel(
            "Probes 169.254.169.254 (AWS/Azure/GCP) to detect if this machine is inside a cloud VM. "
            "Also checks network devices for SSRF metadata-proxy exposure."
        )
        self._cloud_status.setWordWrap(True)
        self._cloud_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._cloud_status)

        # Local IMDS result card
        self._cloud_local_box = QTextEdit()
        self._cloud_local_box.setReadOnly(True)
        self._cloud_local_box.setMaximumHeight(180)
        self._cloud_local_box.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; font-size:11px;"
            "border:1px solid #2a2a4a; border-radius:6px; padding:6px;"
        )
        self._cloud_local_box.setPlaceholderText(
            "IMDS probe result will appear here — runs in < 1 second per provider."
        )
        lay.addWidget(self._cloud_local_box)

        net_lbl = QLabel("  Network SSRF Exposure  (devices that proxy 169.254.169.254):")
        net_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(net_lbl)
        self._cloud_network_table = _table(
            ["Device IP", "MAC", "Hostname", "Exposed?", "Risk", "Finding"]
        )
        self._cloud_network_table.setColumnWidth(0, 120)
        self._cloud_network_table.setColumnWidth(1, 140)
        self._cloud_network_table.setColumnWidth(2, 140)
        self._cloud_network_table.setColumnWidth(3, 75)
        self._cloud_network_table.setColumnWidth(4, 70)
        lay.addWidget(self._cloud_network_table, 1)
        return w

    @pyqtSlot()
    def _start_cloud_metadata(self):
        if self._cloud_worker and self._cloud_worker.isRunning():
            return
        from workers.scan_worker import CloudMetadataWorker
        self._cloud_local_box.clear()
        self._cloud_network_table.setRowCount(0)
        self._btn_cloud_scan.setEnabled(False)
        self._cloud_status.setText("Probing IMDS endpoints…")
        # Pass in last known devices if available
        devices = getattr(self, "_last_scan_devices", [])
        self._cloud_worker = CloudMetadataWorker(devices=devices)
        self._cloud_worker.local_result.connect(self._on_cloud_local_result)
        self._cloud_worker.network_result.connect(self._on_cloud_network_result)
        self._cloud_worker.status.connect(self._cloud_status.setText)
        self._cloud_worker.error.connect(
            lambda e: self._cloud_status.setText(f"⚠ {e}")
        )
        self._cloud_worker.finished.connect(
            lambda: self._btn_cloud_scan.setEnabled(True)
        )
        self._cloud_worker.start()

    @pyqtSlot(object)
    def _on_cloud_local_result(self, result):
        risk_color = {"NONE": GREEN, "INFO": AMBER, "HIGH": RED}.get(result.risk_level, TEXT_SECONDARY)
        risk_icon  = {"NONE": "✔", "INFO": "ℹ", "HIGH": "⚠"}.get(result.risk_level, "?")
        lines = [
            f"<b style='color:{risk_color}'>{risk_icon} [{result.risk_level}]  {result.plain_verdict}</b>",
        ]
        if result.provider:
            lines.append(f"<br><b>Provider:</b> {result.provider}")
            if result.instance_id:
                lines.append(f"<b>Instance:</b> {result.instance_id}")
            if result.region:
                lines.append(f"<b>Region:</b> {result.region}")
            if result.account_id:
                lines.append(f"<b>Account:</b> {result.account_id}")
            if result.public_ip:
                lines.append(f"<b>Public IP:</b> {result.public_ip}")
            if result.ami_id:
                lines.append(f"<b>AMI:</b> {result.ami_id}")
            if result.project_id:
                lines.append(f"<b>Project:</b> {result.project_id}")
            if result.imdsv2_enforced is not None:
                v2_color = GREEN if result.imdsv2_enforced else RED
                v2_txt   = "enforced (secure)" if result.imdsv2_enforced else "NOT enforced — HIGH RISK"
                lines.append(f"<b>IMDSv2:</b> <span style='color:{v2_color}'>{v2_txt}</span>")
        for finding in result.findings:
            lines.append(f"<br><span style='color:{AMBER}'>⚠ {finding}</span>")
        self._cloud_local_box.setHtml("<br>".join(lines))

    @pyqtSlot(list)
    def _on_cloud_network_result(self, results: list):
        from PyQt6.QtGui import QColor
        self._cloud_network_table.setRowCount(0)
        for r in results:
            row = self._cloud_network_table.rowCount()
            self._cloud_network_table.insertRow(row)
            exposed_color = RED if r.exposed else GREEN
            row_color = RED if r.exposed else TEXT_SECONDARY
            finding_str = r.findings[0][:100] if r.findings else "—"
            for col, val in enumerate([
                r.device_ip, r.device_mac, r.hostname,
                "YES" if r.exposed else "no",
                r.risk_level, finding_str,
            ]):
                item = QTableWidgetItem(str(val))
                if col == 3:
                    item.setForeground(QColor(exposed_color))
                elif col in (4, 5):
                    item.setForeground(QColor(row_color))
                else:
                    item.setForeground(QColor(TEXT_SECONDARY if not r.exposed else RED))
                self._cloud_network_table.setItem(row, col, item)

    # ── Log chart handler ─────────────────────────────────────────────────────

    @pyqtSlot()
    def _view_log_chart(self):
        if not self._log_chart_summary:
            return
        try:
            from modules.log_chart import render_chart
            self._btn_log_chart.setEnabled(False)
            self._log_status_lbl.setText("Rendering chart…")
            saved = render_chart(self._log_chart_summary, show=True)
            self._log_status_lbl.setText(f"Chart saved: {saved}")
        except Exception as exc:
            self._log_status_lbl.setText(f"Chart error: {exc}")
        finally:
            self._btn_log_chart.setEnabled(True)

    # ── Root Cause Analysis (Correlator) tab ─────────────────────────────────

    def _build_correlator_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Automatically links findings from all scans — STP, Storm, Diagnostics, and the "
            "Stability Log — to identify the single root cause of your network problems. "
            "Distinguishes between a fault in your home network versus a problem at your ISP. "
            "Run at least one scan first, then click Analyse."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        self._corr_status = QLabel("No analysis yet — run scans first, then click Analyse.")
        self._corr_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._corr_status.setWordWrap(True)

        # Verdict banner
        self._corr_verdict = QLabel("Run a scan to see the root cause summary.")
        self._corr_verdict.setWordWrap(True)
        self._corr_verdict.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:2px solid #2a2a4a; "
            "border-radius:10px; padding:10px 14px; font-size:13px; font-weight:bold;"
        )

        ctrl = QHBoxLayout()
        btn_analyse = QPushButton("🧩  Analyse Root Cause Now")
        btn_analyse.setObjectName("btnScan")
        btn_analyse.setToolTip("Correlate all scan results and produce a prioritised root-cause list.")
        btn_analyse.clicked.connect(self._run_correlator)
        ctrl.addWidget(btn_analyse)
        ctrl.addStretch()

        # Findings table
        self._corr_table = _table([
            "Severity", "Category", "Source", "What's Wrong", "How to Fix It"
        ])
        self._corr_table.setColumnWidth(0, 80)
        self._corr_table.setColumnWidth(1, 200)
        self._corr_table.setColumnWidth(2, 160)
        self._corr_table.setColumnWidth(3, 300)

        lay.addWidget(info)
        lay.addWidget(self._corr_verdict)
        lay.addWidget(self._corr_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._corr_table, 1)
        return w

    @pyqtSlot()
    def _run_correlator(self):
        from PyQt6.QtGui import QColor
        try:
            from modules.root_cause_correlator import correlate

            # Gather available results — everything is optional
            diag   = self._diag_result
            m3_res = self._m3_result   # StormResult
            m1_dev = self._m1_result.get("devices", []) if self._m1_result else []
            gw_mac = self._net_info.get("gateway_mac", None) if self._net_info else None

            # Collect BPDU list from m2 result if present
            bpdus = []
            if self._m2_result and "bpdus" in self._m2_result:
                bpdus = self._m2_result["bpdus"]

            # Log summary from logger worker
            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass

            result = correlate(
                diag_result=diag,
                storm_result=m3_res,
                stp_bpdus=bpdus,
                fingerprint_devices=m1_dev,
                log_summary=log_summary,
                gateway_mac=gw_mac,
            )

            # Update verdict banner colour
            sev_colors = {
                "CRITICAL": RED, "HIGH": RED, "MEDIUM": AMBER,
                "LOW": GREEN, "INFO": TEXT_SECONDARY,
            }
            banner_color = sev_colors.get(result.global_severity, TEXT_SECONDARY)
            self._corr_verdict.setStyleSheet(
                f"background:{BG_CARD}; color:{banner_color}; "
                f"border:2px solid {banner_color}; border-radius:10px; "
                "padding:10px 14px; font-size:13px; font-weight:bold;"
            )
            self._corr_verdict.setText(result.plain_summary)

            # Populate findings table
            self._corr_table.setRowCount(0)
            for f in result.findings:
                row = self._corr_table.rowCount()
                self._corr_table.insertRow(row)
                color = sev_colors.get(f.severity, TEXT_SECONDARY)
                for col, val in enumerate([
                    f.severity, f.category, f.source, f.headline, f.remediation
                ]):
                    item = QTableWidgetItem(str(val))
                    if col in (0, 1):
                        item.setForeground(QColor(color))
                    self._corr_table.setItem(row, col, item)

            isp_tag = " [ISP issue — local alerts suppressed]" if result.suppress_local_alerts else ""
            self._corr_status.setText(
                f"Analysis complete — {result.finding_count} finding(s), "
                f"global severity: {result.global_severity}{isp_tag}"
            )

        except Exception as exc:
            self._corr_status.setText(f"⚠ Correlation failed: {exc}")

    # ── IoT Behavioural Baseline tab ─────────────────────────────────────────

    def _build_iot_baseline_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "NetSentinel learns what traffic is normal for each IoT device on your network "
            "(smart speakers, cameras, TVs, etc.) and alerts you if one behaves differently — "
            "e.g. suddenly port-scanning, contacting an unusual server, or flooding traffic. "
            "Run a Devices scan first, then click Learn to capture a baseline."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        self._iot_status = QLabel("No baseline loaded. Run 'Devices on Network' scan first.")
        self._iot_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._iot_status.setWordWrap(True)

        ctrl = QHBoxLayout()
        btn_learn = QPushButton("📖  Learn Normal Behaviour (60 s)")
        btn_learn.setObjectName("btnNetRefresh")
        btn_learn.setToolTip(
            "Sniffs traffic for 60 seconds to record which servers and ports each IoT device normally uses."
        )
        btn_learn.clicked.connect(self._run_iot_learn)

        btn_monitor = QPushButton("👁  Start Anomaly Monitor")
        btn_monitor.setObjectName("btnScan")
        btn_monitor.setToolTip("Continuously watches IoT device traffic and alerts on deviations from the baseline.")
        btn_monitor.clicked.connect(self._run_iot_monitor)

        btn_stop = QPushButton("⏹  Stop Monitor")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_iot_monitor)

        self._iot_learn_duration = QSpinBox()
        self._iot_learn_duration.setRange(30, 600)
        self._iot_learn_duration.setValue(60)
        self._iot_learn_duration.setSuffix(" s")
        self._iot_learn_duration.setToolTip("How many seconds to observe traffic during the learning phase")
        self._iot_learn_duration.setFixedWidth(80)

        ctrl.addWidget(btn_learn)
        ctrl.addWidget(self._iot_learn_duration)
        ctrl.addSpacing(12)
        ctrl.addWidget(btn_monitor)
        ctrl.addWidget(btn_stop)
        ctrl.addStretch()

        # Baseline summary table
        self._iot_baseline_table = _table([
            "Device", "IP", "MAC", "Type", "Known IPs", "Known Ports", "Avg pps", "Learned"
        ])
        self._iot_baseline_table.setColumnWidth(0, 200)
        self._iot_baseline_table.setColumnWidth(1, 110)
        self._iot_baseline_table.setColumnWidth(2, 145)
        self._iot_baseline_table.setColumnWidth(3, 150)
        self._iot_baseline_table.setColumnWidth(4, 60)
        self._iot_baseline_table.setColumnWidth(5, 70)
        self._iot_baseline_table.setColumnWidth(6, 65)

        # Live alert table
        alerts_lbl = QLabel("Live Anomaly Alerts")
        alerts_lbl.setStyleSheet(f"color:{ACCENT_LITE};font-size:12px;font-weight:bold;padding:6px 0 2px 0;")
        self._iot_alert_table = _table([
            "Time", "Device", "Alert Type", "Severity", "Detail", "Remediation"
        ])
        self._iot_alert_table.setColumnWidth(0, 75)
        self._iot_alert_table.setColumnWidth(1, 170)
        self._iot_alert_table.setColumnWidth(2, 130)
        self._iot_alert_table.setColumnWidth(3, 75)
        self._iot_alert_table.setColumnWidth(4, 350)

        lay.addWidget(info)
        lay.addWidget(self._iot_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._iot_baseline_table)
        lay.addWidget(alerts_lbl)
        lay.addWidget(self._iot_alert_table, 1)

        self._iot_monitor_obj = None
        return w

    def _populate_iot_baseline_table(self, baselines: dict) -> None:
        from PyQt6.QtGui import QColor
        self._iot_baseline_table.setRowCount(0)
        for mac, b in baselines.items():
            row = self._iot_baseline_table.rowCount()
            self._iot_baseline_table.insertRow(row)
            label = b.model or b.vendor or mac
            for col, val in enumerate([
                label, b.ip, mac, b.device_type,
                str(len(b.known_ips)), str(len(b.known_ports)),
                f"{b.avg_pps:.1f}", b.learned_at[:10] if b.learned_at else "—",
            ]):
                self._iot_baseline_table.setItem(row, col, QTableWidgetItem(str(val)))

    @pyqtSlot()
    def _run_iot_learn(self):
        if not self._m1_result:
            self._iot_status.setText("⚠ Run 'Devices on Network' scan first.")
            return
        devices = self._m1_result.get("devices", [])
        duration = self._iot_learn_duration.value()
        self._iot_status.setText(f"Learning for {duration} s — keep devices active…")
        try:
            from modules.iot_baseline import learn
            from pathlib import Path
            def _do_learn():
                baselines = learn(
                    devices=devices, duration_s=duration,
                    progress_cb=lambda m: self._iot_status.setText(m),
                )
                self._populate_iot_baseline_table(baselines)
                self._iot_status.setText(
                    f"Baseline learned for {len(baselines)} IoT device(s). "
                    "Click 'Start Anomaly Monitor' to watch for deviations."
                )
            import threading
            threading.Thread(target=_do_learn, daemon=True).start()
        except Exception as exc:
            self._iot_status.setText(f"⚠ Learn failed: {exc}")

    @pyqtSlot()
    def _run_iot_monitor(self):
        try:
            from modules.iot_baseline import load_or_create, IoTMonitor
            from PyQt6.QtGui import QColor
            import time

            if not self._m1_result:
                self._iot_status.setText("⚠ Run 'Devices on Network' scan first.")
                return

            devices = self._m1_result.get("devices", [])

            def _start():
                baselines = load_or_create(
                    devices=devices,
                    progress_cb=lambda m: self._iot_status.setText(m),
                )
                if not baselines:
                    self._iot_status.setText("⚠ No IoT baselines — run Learn first.")
                    return
                self._populate_iot_baseline_table(baselines)

                def _on_alert(alert):
                    row = self._iot_alert_table.rowCount()
                    self._iot_alert_table.insertRow(row)
                    sev_color = RED if alert.severity == "CRITICAL" else (AMBER if alert.severity == "HIGH" else BLUE)
                    for col, val in enumerate([
                        alert.timestamp[11:19], alert.device_label,
                        alert.alert_type.replace("_", " ").title(),
                        alert.severity, alert.detail, alert.remediation,
                    ]):
                        item = QTableWidgetItem(str(val))
                        if col in (2, 3):
                            item.setForeground(QColor(sev_color))
                        self._iot_alert_table.setItem(row, col, item)
                    self._iot_alert_table.scrollToBottom()
                    self._iot_status.setText(
                        f"⚠ Alert: {alert.alert_type} on {alert.device_label}"
                    )

                self._iot_monitor_obj = IoTMonitor(
                    baselines=baselines,
                    on_alert=_on_alert,
                    on_error=lambda m: self._iot_status.setText(f"⚠ {m}"),
                )
                self._iot_monitor_obj.start()
                self._iot_status.setText(
                    f"Monitoring {len(baselines)} IoT device(s) — watching for anomalies…"
                )

            import threading
            threading.Thread(target=_start, daemon=True).start()

        except Exception as exc:
            self._iot_status.setText(f"⚠ Monitor failed: {exc}")

    @pyqtSlot()
    def _stop_iot_monitor(self):
        if self._iot_monitor_obj:
            self._iot_monitor_obj.stop()
            self._iot_monitor_obj = None
            self._iot_status.setText("Anomaly monitor stopped.")

    # ── Network Grade (Benchmark) tab ─────────────────────────────────────────

    def _build_benchmark_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Compares your network against a 'Perfect Home Network' baseline and gives "
            "an A–F letter grade across Uptime, Latency, Jitter, DNS Speed, Download Speed, "
            "Device Safety, STP Health, and Broadcast Storm Level. "
            "Run scans and/or the Stability Logger first, then click Grade My Network."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        # Grade display
        grade_row = QHBoxLayout()
        self._bm_grade_label = QLabel("—")
        self._bm_grade_label.setFixedSize(90, 90)
        self._bm_grade_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bm_grade_label.setStyleSheet(
            "font-size:40px; font-weight:bold; border-radius:45px; "
            f"background:{BG_CARD}; border:3px solid #2a2a4a; color:{TEXT_PRIMARY};"
        )
        self._bm_score_label = QLabel("Score: —")
        self._bm_score_label.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:16px; font-weight:bold;"
        )
        self._bm_verdict_label = QLabel("Run scans first, then click Grade My Network.")
        self._bm_verdict_label.setWordWrap(True)
        self._bm_verdict_label.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; max-width:500px;"
        )
        grade_text = QVBoxLayout()
        grade_text.addWidget(self._bm_score_label)
        grade_text.addWidget(self._bm_verdict_label)
        grade_row.addWidget(self._bm_grade_label)
        grade_row.addSpacing(16)
        grade_row.addLayout(grade_text)
        grade_row.addStretch()

        ctrl = QHBoxLayout()
        btn_grade = QPushButton("📊  Grade My Network")
        btn_grade.setObjectName("btnScan")
        btn_grade.setToolTip("Score your network health across all available dimensions.")
        btn_grade.clicked.connect(self._run_benchmark)
        btn_isp = QPushButton("📤  Generate ISP Report")
        btn_isp.setObjectName("btnNetRefresh")
        btn_isp.setToolTip(
            "Export an ISP Accountability Report — hop table, outages, grade — "
            "as HTML you can print to PDF and attach to a support ticket."
        )
        btn_isp.clicked.connect(self._export_isp_report)
        ctrl.addWidget(btn_grade)
        ctrl.addWidget(btn_isp)
        ctrl.addStretch()

        # Dimension breakdown table
        self._bm_table = _table(["Dimension", "Grade", "Your Value", "Ideal", "Verdict", "Fix Tip"])
        self._bm_table.setColumnWidth(0, 190)
        self._bm_table.setColumnWidth(1, 50)
        self._bm_table.setColumnWidth(2, 100)
        self._bm_table.setColumnWidth(3, 90)
        self._bm_table.setColumnWidth(4, 280)

        lay.addWidget(info)
        lay.addLayout(grade_row)
        lay.addSpacing(6)
        lay.addLayout(ctrl)
        lay.addWidget(self._bm_table, 1)
        return w

    @pyqtSlot()
    def _run_benchmark(self):
        from PyQt6.QtGui import QColor
        try:
            from modules.network_benchmark import grade as bm_grade

            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass

            result = bm_grade(
                log_summary=log_summary,
                diag_result=self._diag_result,
                m1_result=self._m1_result,
                m2_result=self._m2_result,
                m3_result=self._m3_result,
            )
            self._last_benchmark_result = result

            # Update grade circle
            grade_styles = {
                "A": (GREEN, "#14532d"),
                "B": ("#4ade80", "#1a3a1a"),
                "C": (AMBER, "#451a03"),
                "D": (RED, "#7f1d1d"),
                "F": ("#ff4444", "#3b0000"),
                "N/A": (TEXT_SECONDARY, BG_CARD),
            }
            fg, bg = grade_styles.get(result.overall_grade, (TEXT_SECONDARY, BG_CARD))
            self._bm_grade_label.setText(result.overall_grade)
            self._bm_grade_label.setStyleSheet(
                f"font-size:40px; font-weight:bold; border-radius:45px; "
                f"background:{bg}; border:3px solid {fg}; color:{fg};"
            )
            self._bm_score_label.setText(f"Score: {result.overall_score:.0f}/100")
            self._bm_score_label.setStyleSheet(f"color:{fg}; font-size:16px; font-weight:bold;")
            self._bm_verdict_label.setText(result.overall_verdict)

            # Populate dimension table
            self._bm_table.setRowCount(0)
            for d in result.dimensions:
                row = self._bm_table.rowCount()
                self._bm_table.insertRow(row)
                grade_color = {
                    "A": GREEN, "B": "#4ade80", "C": AMBER, "D": RED, "F": "#ff4444"
                }.get(d.grade, TEXT_SECONDARY)
                for col, val in enumerate([
                    d.name, d.grade, d.value_label, d.ideal_label, d.verdict, d.tip
                ]):
                    item = QTableWidgetItem(str(val))
                    if col == 1:
                        item.setForeground(QColor(grade_color))
                    self._bm_table.setItem(row, col, item)

        except Exception as exc:
            self._bm_verdict_label.setText(f"⚠ Grading failed: {exc}")

    @pyqtSlot()
    def _export_isp_report(self):
        try:
            from modules.report_exporter import save_isp_report
            from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit as _QLE

            # Collect optional ISP name & account ref from user
            dlg = QDialog(self)
            dlg.setWindowTitle("ISP Report — Optional Details")
            dlg.setMinimumWidth(380)
            dlg.setStyleSheet(f"background:{BG_DARK}; color:{TEXT_PRIMARY};")
            form = QFormLayout(dlg)
            isp_edit = _QLE()
            isp_edit.setPlaceholderText("e.g. BT, Virgin Media, Comcast…")
            isp_edit.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid #2a2a4a; border-radius:4px; padding:4px;")
            ref_edit = _QLE()
            ref_edit.setPlaceholderText("e.g. REF-123456 (optional)")
            ref_edit.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid #2a2a4a; border-radius:4px; padding:4px;")
            form.addRow("ISP Name:", isp_edit)
            form.addRow("Account / Ticket Ref:", ref_edit)
            btns = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            form.addRow(btns)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            isp_name   = isp_edit.text().strip()
            account_ref = ref_edit.text().strip()

            # Gather data
            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass
            bm_result = getattr(self, "_last_benchmark_result", None)

            # Pick save path
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"ISP_Report_{ts}.html"
            docs_dir = Path.home() / "Documents" / "NetSentinel" / "reports"
            docs_dir.mkdir(parents=True, exist_ok=True)
            path_str, _ = QFileDialog.getSaveFileName(
                self, "Save ISP Report", str(docs_dir / default_name),
                "HTML Report (*.html);;All Files (*)"
            )
            if not path_str:
                return

            out = save_isp_report(
                output_path=Path(path_str),
                log_summary=log_summary,
                diag_result=self._diag_result,
                benchmark_result=bm_result,
                m1_result=self._m1_result,
                isp_name=isp_name,
                account_ref=account_ref,
            )
            webbrowser.open(out.as_uri())
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "ISP Report Error", str(exc))

    # ── How to Fix dialog (shared by M1 / M2 / M3 context menus) ─────────────

    def _show_how_to_fix(self, title: str, remediation: str):
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QScrollArea as _SA

        dlg = QDialog(self)
        dlg.setWindowTitle(f"How to Fix — {title}")
        dlg.setMinimumWidth(500)
        dlg.setStyleSheet(f"background:{BG_DARK}; color:{TEXT_PRIMARY};")
        lay = QVBoxLayout(dlg)

        heading = QLabel(f"<b>Remediation steps for: {title}</b>")
        heading.setStyleSheet(f"color:{ACCENT_LITE}; font-size:13px; padding-bottom:4px;")
        heading.setWordWrap(True)
        lay.addWidget(heading)

        # Split on ". " or "\\n" for numbered steps
        import re
        raw = remediation.strip() if remediation else "No specific fix information available."
        parts = [p.strip() for p in re.split(r'\. (?=[A-Z0-9])', raw) if p.strip()]
        if len(parts) <= 1 and "\n" in raw:
            parts = [p.strip() for p in raw.split("\n") if p.strip()]

        steps_html = ""
        for i, step in enumerate(parts, 1):
            s = html.escape(step)
            if not s.endswith("."):
                s += "."
            steps_html += f"<li style='margin-bottom:8px'><b>Step {i}:</b> {s}</li>"
        if not steps_html:
            steps_html = f"<li>{html.escape(raw)}</li>"

        txt = QLabel(f"<ol style='padding-left:18px;line-height:1.8'>{steps_html}</ol>")
        txt.setWordWrap(True)
        txt.setTextFormat(Qt.TextFormat.RichText)
        txt.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:12px; padding:4px;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.addWidget(txt)
        inner_lay.addStretch()
        scroll.setWidget(inner)
        scroll.setStyleSheet(f"background:{BG_CARD}; border:1px solid #2a2a4a; border-radius:6px;")
        scroll.setMinimumHeight(160)

        lay.addWidget(scroll, 1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        dlg.exec()

    # ── Window lifecycle ──────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Stop any background workers gracefully before closing."""
        self._save_window_state()
        # Stop long-running dedicated workers
        if self._logger_worker and self._logger_worker.isRunning():
            self._logger_worker.stop_logger()
            self._logger_worker.wait(2000)
        if self._mtr_worker and self._mtr_worker.isRunning():
            self._mtr_worker.stop()
            self._mtr_worker.wait(2000)
        # Stop any active scan module workers
        for w in list(self._workers):
            if w.isRunning():
                if hasattr(w, "stop"):
                    w.stop()
                w.wait(1500)
        # Stop new-feature workers
        for w in (self._arp_worker, self._dhcp_worker, self._bw_worker,
                  self._sched_worker, self._snmp_worker,
                  self._syn_worker, self._udp_worker, self._cve_worker,
                  self._exposure_worker, self._os_worker, self._cred_worker,
                  self._discovery_worker, self._smb_worker,
                  self._pe_worker):
            if w is not None and w.isRunning():
                if hasattr(w, "stop"):
                    w.stop()
                w.wait(1500)
        super().closeEvent(event)

    # ── Verdict area ─────────────────────────────────────────────────────────

    def _build_verdict_area(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)

        self._verdict = VerdictPanel()
        lay.addWidget(self._verdict)
        return w

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _stat_label(self, title: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid #2a2a4a; border-radius:8px; padding:4px;"
        )
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(10, 6, 10, 6)
        fl.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        v = QLabel(value)
        v.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:18px;font-weight:bold;")
        v.setObjectName(f"stat_{title.replace('/','_').replace(' ','_')}")
        fl.addWidget(t)
        fl.addWidget(v)
        return frame

    def _find_stat_value(self, frame: QFrame) -> Optional[QLabel]:
        for child in frame.findChildren(QLabel):
            if child.objectName().startswith("stat_"):
                return child
        return None

    def _update_stat(self, frame: QFrame, value: str, color: str = TEXT_PRIMARY):
        lbl = self._find_stat_value(frame)
        if lbl:
            lbl.setText(value)
            lbl.setStyleSheet(f"color:{color};font-size:18px;font-weight:bold;")

    def _set_status(self, msg: str):
        self._status_bar.showMessage(f"  {msg}")

    def _set_scanning(self, scanning: bool):
        self._btn_scan.setEnabled(not scanning)
        self._progress.setVisible(scanning)
        if not scanning:
            self._btn_export.setEnabled(
                any(x is not None for x in [
                    self._m1_result, self._m2_result, self._m3_result,
                    self._m4_result, self._m5_result
                ])
            )

    # ── Shared copy-to-clipboard for tables ──────────────────────────────────

    @staticmethod
    def _enable_copy_menu(table: QTableWidget):
        """Wire a right-click 'Copy row' action to any QTableWidget."""
        from PyQt6.QtCore import Qt as _Qt
        table.setContextMenuPolicy(_Qt.ContextMenuPolicy.CustomContextMenu)

        def _show_menu(pos):
            from PyQt6.QtWidgets import QMenu as _QMenu
            from PyQt6.QtGui import QClipboard as _QClipboard
            from PyQt6.QtWidgets import QApplication as _QApp
            rows_selected = sorted({i.row() for i in table.selectedIndexes()})
            if not rows_selected:
                return
            menu = _QMenu(table)
            act_row  = menu.addAction("Copy selected row(s)")
            act_cell = menu.addAction("Copy selected cell")
            chosen = menu.exec(table.viewport().mapToGlobal(pos))
            if chosen == act_row:
                lines = []
                for r in rows_selected:
                    parts = [
                        (table.item(r, c).text() if table.item(r, c) else "")
                        for c in range(table.columnCount())
                    ]
                    lines.append("\t".join(parts))
                _QApp.clipboard().setText("\n".join(lines))
            elif chosen == act_cell:
                item = table.currentItem()
                if item:
                    _QApp.clipboard().setText(item.text())

        table.customContextMenuRequested.connect(_show_menu)

    # ── Window state persistence ──────────────────────────────────────────────

    @staticmethod
    def _settings_path() -> "Path":
        """
        Return the path to NetSentinel.ini.

        Priority:
          1. Same directory as the running executable / script (portable use —
             settings travel with the exe on a USB stick or shared folder).
          2. Fallback: ~/.config/NetSentinel/NetSentinel.ini (if the exe dir
             is not writable, e.g. installed in Program Files).
        """
        import sys as _sys
        exe_dir = Path(_sys.executable).parent if getattr(_sys, "frozen", False) \
            else Path(__file__).resolve().parent.parent
        candidate = exe_dir / "NetSentinel.ini"
        try:
            # Quick write-test
            candidate.touch(exist_ok=True)
            return candidate
        except OSError:
            fallback = Path.home() / ".config" / "NetSentinel" / "NetSentinel.ini"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback

    def _save_settings(self):
        from PyQt6.QtCore import QSettings
        s = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        # Window geometry
        s.setValue("window/geometry", self.saveGeometry().toBase64().data().decode())
        # Mode state
        s.setValue("ui/advanced_mode", self._btn_mode.isChecked())
        s.setValue("ui/recon_mode",    self._btn_recon.isChecked())
        # Last scan settings
        if hasattr(self, "_ps_host"):
            s.setValue("scan/last_port_scan_host", self._ps_host.text())
        if hasattr(self, "_ps_mode"):
            s.setValue("scan/port_scan_mode", self._ps_mode.currentText())
        if hasattr(self, "_syn_host"):
            s.setValue("scan/last_syn_host", self._syn_host.text())
        if hasattr(self, "_syn_ports_combo"):
            s.setValue("scan/syn_port_range", self._syn_ports_combo.currentText())
        if hasattr(self, "_syn_rate"):
            s.setValue("scan/syn_rate_pps", self._syn_rate.value())
        if hasattr(self, "_udp_host"):
            s.setValue("scan/last_udp_host", self._udp_host.text())
        s.sync()

    def _restore_settings(self):
        from PyQt6.QtCore import QSettings
        from PyQt6.QtCore import QByteArray
        s = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        # Window geometry
        geom_b64 = s.value("window/geometry", "")
        if geom_b64:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geom_b64.encode()))
            except Exception:
                pass
        # Mode — restore Advanced first (Recon depends on it)
        adv = s.value("ui/advanced_mode", False, type=bool)
        rec = s.value("ui/recon_mode",    False, type=bool)
        if adv or rec:
            self._btn_mode.setChecked(True)
        if rec:
            self._btn_recon.setChecked(True)
        # Last scan settings
        if hasattr(self, "_ps_host"):
            host = s.value("scan/last_port_scan_host", "")
            if host:
                self._ps_host.setText(host)
        if hasattr(self, "_ps_mode"):
            mode = s.value("scan/port_scan_mode", "")
            if mode:
                idx = self._ps_mode.findText(mode)
                if idx >= 0:
                    self._ps_mode.setCurrentIndex(idx)
        if hasattr(self, "_syn_host"):
            syn_host = s.value("scan/last_syn_host", "")
            if syn_host:
                self._syn_host.setText(syn_host)
        if hasattr(self, "_syn_ports_combo"):
            syn_range = s.value("scan/syn_port_range", "")
            if syn_range:
                idx = self._syn_ports_combo.findText(syn_range)
                if idx >= 0:
                    self._syn_ports_combo.setCurrentIndex(idx)
        if hasattr(self, "_syn_rate"):
            rate = s.value("scan/syn_rate_pps", 500, type=int)
            self._syn_rate.setValue(rate)
        if hasattr(self, "_udp_host"):
            udp_host = s.value("scan/last_udp_host", "")
            if udp_host:
                self._udp_host.setText(udp_host)

    # Keep old names as aliases so any external code still works
    def _save_window_state(self):
        self._save_settings()

    def _restore_window_state(self):
        self._restore_settings()

    # ── OUI database reload ───────────────────────────────────────────────────

    def _reload_oui_db(self):
        """Re-read offenders.json without restarting the app."""
        self._offenders_path = get_offenders_path()
        self._set_status("OUI vendor database reloaded.")

    # ── Topology tab ──────────────────────────────────────────────────────────

    def _build_topology_tab(self) -> QWidget:
        from ui.topology_widget import TopologyWidget
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lbl = QLabel("Network topology — run a Device Fingerprint scan first.")
        lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._topology_widget = TopologyWidget()
        lay.addWidget(lbl)
        lay.addWidget(self._topology_widget, 1)
        return w

    # ── ARP monitor tab ───────────────────────────────────────────────────────

    def _build_arp_monitor_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._arp_status = QLabel("ARP spoof monitor not running.")
        self._arp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        btn_row = QHBoxLayout()
        btn_start = QPushButton("▶  Start ARP Monitor (30s)")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_arp_monitor)
        btn_row.addWidget(btn_start)
        btn_row.addStretch()
        self._arp_table = _table(["Type", "Attacker MAC", "Attacker IP", "Victim IP", "Original MAC", "Verdict"])
        self._arp_table.setColumnWidth(0, 110)
        self._arp_table.setColumnWidth(1, 145)
        self._arp_table.setColumnWidth(2, 120)
        self._arp_table.setColumnWidth(5, 400)
        lay.addWidget(self._arp_status)
        lay.addLayout(btn_row)
        lay.addWidget(self._arp_table, 1)
        return w

    @pyqtSlot()
    def _start_arp_monitor(self):
        from workers.scan_worker import ARPMonitorWorker
        if self._arp_worker and self._arp_worker.isRunning():
            return
        self._arp_table.setRowCount(0)
        gateway_ip = self._net_info.get("gateway") if self._net_info else None
        self._arp_worker = ARPMonitorWorker(gateway_ip=gateway_ip, duration=30)
        self._arp_worker.event_found.connect(self._on_arp_event)
        self._arp_worker.result.connect(lambda r: self._arp_status.setText(r.plain_verdict))
        self._arp_worker.status.connect(self._arp_status.setText)
        self._arp_worker.error.connect(lambda e: self._arp_status.setText(f"⚠ {e}"))
        self._arp_worker.start()
        self._arp_status.setText("ARP monitor started…")

    @pyqtSlot(object)
    def _on_arp_event(self, event):
        row = self._arp_table.rowCount()
        self._arp_table.insertRow(row)
        level = "HIGH" if event.event_type in ("GATEWAY_HIJACK",) else "MEDIUM"
        for col, val in enumerate([
            event.event_type, event.attacker_mac, event.attacker_ip,
            event.victim_ip, event.original_mac, event.verdict
        ]):
            item = QTableWidgetItem(str(val))
            item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                _color_for_level(level)
            ))
            self._arp_table.setItem(row, col, item)

    # ── DHCP monitor tab ──────────────────────────────────────────────────────

    def _build_dhcp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._dhcp_status = QLabel("DHCP rogue server monitor not running.")
        self._dhcp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        btn_row = QHBoxLayout()
        btn_start = QPushButton("▶  Send DHCP Discover")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_dhcp_scan)
        btn_row.addWidget(btn_start)
        btn_row.addStretch()
        self._dhcp_table = _table(["Server IP", "Server MAC", "Offered IP", "Gateway", "DNS", "Lease", "Rogue?", "Verdict"])
        self._dhcp_table.setColumnWidth(7, 400)
        lay.addWidget(self._dhcp_status)
        lay.addLayout(btn_row)
        lay.addWidget(self._dhcp_table, 1)
        return w

    @pyqtSlot()
    def _start_dhcp_scan(self):
        from workers.scan_worker import DHCPDetectorWorker
        if self._dhcp_worker and self._dhcp_worker.isRunning():
            return
        self._dhcp_table.setRowCount(0)
        self._dhcp_worker = DHCPDetectorWorker(duration=10)
        self._dhcp_worker.offer_found.connect(self._on_dhcp_offer)
        self._dhcp_worker.result.connect(lambda r: self._dhcp_status.setText(r.plain_verdict))
        self._dhcp_worker.status.connect(self._dhcp_status.setText)
        self._dhcp_worker.error.connect(lambda e: self._dhcp_status.setText(f"⚠ {e}"))
        self._dhcp_worker.start()
        self._dhcp_status.setText("DHCP discover sent — listening for offers…")

    @pyqtSlot(object)
    def _on_dhcp_offer(self, offer):
        row = self._dhcp_table.rowCount()
        self._dhcp_table.insertRow(row)
        level = "HIGH" if offer.is_rogue else "CLEAN"
        for col, val in enumerate([
            offer.server_ip, offer.server_mac, offer.offered_ip,
            offer.gateway, ", ".join(offer.dns_servers),
            f"{offer.lease_time}s", "YES ⚠" if offer.is_rogue else "No",
            offer.verdict,
        ]):
            item = QTableWidgetItem(str(val))
            item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                _color_for_level(level)
            ))
            self._dhcp_table.setItem(row, col, item)

    # ── Bandwidth tab ─────────────────────────────────────────────────────────

    def _build_bandwidth_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._bw_status = QLabel("Bandwidth monitor not running. Requires admin + Npcap.")
        self._bw_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        btn_row = QHBoxLayout()
        btn_start = QPushButton("▶  Start Bandwidth Monitor")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_bandwidth_monitor)
        btn_stop = QPushButton("■  Stop")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_bandwidth_monitor)
        btn_row.addWidget(btn_start)
        btn_row.addWidget(btn_stop)
        btn_row.addStretch()
        self._bw_table = _table(["MAC / Label", "TX (kbps)", "RX (kbps)", "Total (kbps)", "Total (Mbps)"])
        lay.addWidget(self._bw_status)
        lay.addLayout(btn_row)
        lay.addWidget(self._bw_table, 1)
        return w

    @pyqtSlot()
    def _start_bandwidth_monitor(self):
        from workers.scan_worker import BandwidthWorker
        if self._bw_worker and self._bw_worker.isRunning():
            return
        # Build label map from M1 results if available
        label_map: dict = {}
        if self._m1_result:
            for d in self._m1_result.get("devices", []):
                mac = d.get("mac", "") if isinstance(d, dict) else (getattr(d, "mac", "") or "")
                host = d.get("hostname", "") if isinstance(d, dict) else (getattr(d, "hostname", "") or "")
                vendor = d.get("vendor", "") if isinstance(d, dict) else (getattr(d, "vendor", "") or "")
                if mac:
                    label_map[mac.lower()] = host or vendor or mac
        self._bw_worker = BandwidthWorker(interval_s=5.0, label_map=label_map)
        self._bw_worker.snapshot.connect(self._on_bw_snapshot)
        self._bw_worker.status.connect(self._bw_status.setText)
        self._bw_worker.error.connect(lambda e: self._bw_status.setText(f"⚠ {e}"))
        self._bw_worker.start()

    @pyqtSlot()
    def _stop_bandwidth_monitor(self):
        if self._bw_worker:
            self._bw_worker.stop()
            self._bw_status.setText("Bandwidth monitor stopped.")

    @pyqtSlot(object)
    def _on_bw_snapshot(self, snap):
        self._bw_table.setRowCount(0)
        for entry in snap.entries:
            row = self._bw_table.rowCount()
            self._bw_table.insertRow(row)
            total_kbps = entry.total_bps / 1000
            level = "HIGH" if total_kbps > 5000 else ("MEDIUM" if total_kbps > 500 else "CLEAN")
            for col, val in enumerate([
                entry.label or entry.mac,
                f"{entry.tx_bps/1000:.1f}",
                f"{entry.rx_bps/1000:.1f}",
                f"{total_kbps:.1f}",
                f"{entry.total_mbps:.3f}",
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                    _color_for_level(level)
                ))
                self._bw_table.setItem(row, col, item)
        self._bw_status.setText(
            f"Bandwidth snapshot ({snap.window_s:.0f}s window) — "
            f"{len(snap.entries)} device(s)"
        )

    # ── Scheduler tab ─────────────────────────────────────────────────────────

    def _build_scheduler_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._sched_status = QLabel("Scheduled scanner not running.")
        self._sched_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl_row = QHBoxLayout()
        self._sched_interval = QSpinBox()
        self._sched_interval.setRange(1, 1440)
        self._sched_interval.setValue(15)
        self._sched_interval.setSuffix(" min")
        self._sched_interval.setFixedWidth(90)
        btn_start = QPushButton("▶  Start Scheduler")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_scheduler)
        btn_stop = QPushButton("■  Stop")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_scheduler)
        ctrl_row.addWidget(QLabel("Interval:"))
        ctrl_row.addWidget(self._sched_interval)
        ctrl_row.addWidget(btn_start)
        ctrl_row.addWidget(btn_stop)
        ctrl_row.addStretch()
        self._sched_log = QTextEdit()
        self._sched_log.setReadOnly(True)
        self._sched_log.setStyleSheet(f"background:{BG_CARD};color:{TEXT_PRIMARY};font-size:11px;")
        lay.addWidget(self._sched_status)
        lay.addLayout(ctrl_row)
        lay.addWidget(self._sched_log, 1)
        return w

    @pyqtSlot()
    def _start_scheduler(self):
        from workers.scan_worker import SchedulerWorker
        if self._sched_worker and self._sched_worker.isRunning():
            return
        self._sched_worker = SchedulerWorker(
            interval_minutes=self._sched_interval.value(),
            offenders_path=self._offenders_path,
            notify_desktop=True,
        )
        self._sched_worker.status.connect(self._on_sched_status)
        self._sched_worker.alert.connect(lambda t, m: self._sched_log.append(f"🔔 {t}: {m}"))
        self._sched_worker.error.connect(lambda e: self._sched_log.append(f"⚠ {e}"))
        self._sched_worker.start()

    @pyqtSlot()
    def _stop_scheduler(self):
        if self._sched_worker:
            self._sched_worker.stop()
            self._sched_status.setText("Scheduler stopped.")

    @pyqtSlot(str)
    def _on_sched_status(self, msg: str):
        self._sched_status.setText(msg)
        self._sched_log.append(msg)

    # ── SNMP tab ──────────────────────────────────────────────────────────────

    def _build_snmp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._snmp_status = QLabel("SNMP poller not running.")
        self._snmp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl_row = QHBoxLayout()
        self._snmp_community = QLineEdit("public")
        self._snmp_community.setFixedWidth(120)
        self._snmp_community.setPlaceholderText("community string")
        btn_poll = QPushButton("▶  Poll All Devices")
        btn_poll.setObjectName("btnNetRefresh")
        btn_poll.clicked.connect(self._start_snmp_poll)
        ctrl_row.addWidget(QLabel("Community:"))
        ctrl_row.addWidget(self._snmp_community)
        ctrl_row.addWidget(btn_poll)
        ctrl_row.addStretch()
        self._snmp_table = _table(["Host", "Name", "Description", "Uptime", "Interfaces", "Contact"])
        self._snmp_table.setColumnWidth(0, 120)
        self._snmp_table.setColumnWidth(2, 350)
        lay.addWidget(self._snmp_status)
        lay.addLayout(ctrl_row)
        lay.addWidget(self._snmp_table, 1)
        return w

    @pyqtSlot()
    def _start_snmp_poll(self):
        from workers.scan_worker import SNMPWorker
        if self._snmp_worker and self._snmp_worker.isRunning():
            return
        # Collect IPs from last M1 scan + gateway
        hosts: list = []
        if self._m1_result:
            for d in self._m1_result.get("devices", []):
                ip = getattr(d, "ip", None) if not isinstance(d, dict) else d.get("ip")
                if ip:
                    hosts.append(ip)
        gw = self._net_info.get("gateway") if self._net_info else None
        if gw and gw not in hosts:
            hosts.insert(0, gw)
        if not hosts:
            self._snmp_status.setText("No devices found — run a Device Fingerprint scan first.")
            return
        self._snmp_table.setRowCount(0)
        community = self._snmp_community.text().strip() or "public"
        self._snmp_worker = SNMPWorker(hosts=hosts, community=community)
        self._snmp_worker.host_result.connect(self._on_snmp_result)
        self._snmp_worker.status.connect(self._snmp_status.setText)
        self._snmp_worker.error.connect(lambda e: self._snmp_status.setText(f"⚠ {e}"))
        self._snmp_worker.start()

    @pyqtSlot(object)
    def _on_snmp_result(self, result):
        if not result.reachable:
            return
        row = self._snmp_table.rowCount()
        self._snmp_table.insertRow(row)
        for col, val in enumerate([
            result.host, result.sys_name, result.sys_descr[:80],
            result.sys_uptime, result.if_count, result.sys_contact,
        ]):
            self._snmp_table.setItem(row, col, QTableWidgetItem(str(val)))

    # ── Recon: SYN Stealth Scan tab ───────────────────────────────────────────

    def _build_recon_syn_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        warn = QLabel(
            "⚠  SYN stealth scan requires administrator privileges and Npcap (Windows). "
            "Scans are not logged by the target's application layer. "
            "Use only on networks you own or have authorization to test."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{AMBER};font-size:11px;background:#1a1a00;padding:6px;border-radius:6px;")
        self._syn_status = QLabel("SYN scanner idle.")
        self._syn_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl = QHBoxLayout()
        self._syn_host = QLineEdit()
        self._syn_host.setPlaceholderText("IP or hostname…")
        self._syn_host.setFixedWidth(180)
        self._syn_rate = QSpinBox()
        self._syn_rate.setRange(10, 5000)
        self._syn_rate.setValue(500)
        self._syn_rate.setSuffix(" pps")
        self._syn_rate.setFixedWidth(100)
        from PyQt6.QtWidgets import QComboBox as _CB
        self._syn_ports_combo = _CB()
        self._syn_ports_combo.addItems(["Top 1000 ports", "Common 26 ports", "Full range (slow)"])
        self._syn_ports_combo.setFixedWidth(160)
        btn = QPushButton("⚡  SYN Scan")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_syn_scan)
        btn_stop = QPushButton("■  Stop")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_syn_scan)
        ctrl.addWidget(self._syn_host)
        ctrl.addWidget(QLabel("Rate:"))
        ctrl.addWidget(self._syn_rate)
        ctrl.addWidget(self._syn_ports_combo)
        ctrl.addWidget(btn)
        ctrl.addWidget(btn_stop)
        ctrl.addStretch()
        self._recon_syn_table = _table(["Port", "State", "Protocol", "Service"])
        self._recon_syn_table.setColumnWidth(0, 70)
        self._recon_syn_table.setColumnWidth(1, 90)
        self._recon_syn_table.setColumnWidth(2, 70)
        self._recon_syn_table.setColumnWidth(3, 220)
        lay.addWidget(warn)
        lay.addWidget(self._syn_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_syn_table, 1)
        return w

    @pyqtSlot()
    def _start_syn_scan(self):
        from workers.scan_worker import SYNScanWorker
        host = self._syn_host.text().strip()
        if not host:
            return
        if self._syn_worker and self._syn_worker.isRunning():
            return
        self._recon_syn_table.setRowCount(0)
        mode_text = self._syn_ports_combo.currentText()
        if "Full range" in mode_text:
            ports = list(range(1, 65536))
        elif "Common 26" in mode_text:
            from modules.port_scanner import COMMON_PORTS
            ports = COMMON_PORTS
        else:
            from modules.syn_scanner import TOP_1000_PORTS
            ports = TOP_1000_PORTS
        rate = self._syn_rate.value()
        self._syn_worker = SYNScanWorker(host=host, ports=ports, rate_pps=rate)
        self._syn_worker.result.connect(self._on_syn_result)
        self._syn_worker.status.connect(self._syn_status.setText)
        self._syn_worker.error.connect(lambda e: self._syn_status.setText(f"⚠ {e}"))
        self._syn_worker.start()

    @pyqtSlot()
    def _stop_syn_scan(self):
        if self._syn_worker:
            self._syn_worker.stop()

    @pyqtSlot(object)
    def _on_syn_result(self, result):
        from PyQt6.QtGui import QColor
        self._recon_syn_table.setRowCount(0)
        for p in result.open_ports:
            row = self._recon_syn_table.rowCount()
            self._recon_syn_table.insertRow(row)
            color = RED if p.state == "open" else AMBER
            for col, val in enumerate([str(p.port), p.state, p.proto, p.service]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self._recon_syn_table.setItem(row, col, item)
        self._syn_status.setText(result.plain_verdict if not result.error else f"⚠ {result.error}")

    # ── Recon: UDP Scan tab ───────────────────────────────────────────────────

    def _build_recon_udp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        warn = QLabel(
            "⚠  UDP scan requires administrator privileges and Npcap (Windows). "
            "No response = open|filtered (firewall or open service — UDP is ambiguous)."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{AMBER};font-size:11px;background:#1a1a00;padding:6px;border-radius:6px;")
        self._udp_status = QLabel("UDP scanner idle.")
        self._udp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl = QHBoxLayout()
        self._udp_host = QLineEdit()
        self._udp_host.setPlaceholderText("IP or hostname…")
        self._udp_host.setFixedWidth(180)
        btn = QPushButton("📻  UDP Scan")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_udp_scan)
        ctrl.addWidget(self._udp_host)
        ctrl.addWidget(btn)
        ctrl.addStretch()
        self._recon_udp_table = _table(["Port", "State", "Service"])
        self._recon_udp_table.setColumnWidth(0, 70)
        self._recon_udp_table.setColumnWidth(1, 120)
        self._recon_udp_table.setColumnWidth(2, 220)
        lay.addWidget(warn)
        lay.addWidget(self._udp_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_udp_table, 1)
        return w

    @pyqtSlot()
    def _start_udp_scan(self):
        from workers.scan_worker import UDPScanWorker
        host = self._udp_host.text().strip()
        if not host:
            return
        if self._udp_worker and self._udp_worker.isRunning():
            return
        self._recon_udp_table.setRowCount(0)
        self._udp_worker = UDPScanWorker(host=host)
        self._udp_worker.result.connect(self._on_udp_result)
        self._udp_worker.status.connect(self._udp_status.setText)
        self._udp_worker.error.connect(lambda e: self._udp_status.setText(f"⚠ {e}"))
        self._udp_worker.start()

    @pyqtSlot(object)
    def _on_udp_result(self, result):
        from PyQt6.QtGui import QColor
        self._recon_udp_table.setRowCount(0)
        for p in result.open_ports:
            row = self._recon_udp_table.rowCount()
            self._recon_udp_table.insertRow(row)
            color = AMBER if p.state == "open|filtered" else GREEN
            for col, val in enumerate([str(p.port), p.state, p.service]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self._recon_udp_table.setItem(row, col, item)
        self._udp_status.setText(result.plain_verdict if not result.error else f"⚠ {result.error}")

    # ── Recon: Deep OS Fingerprint tab ────────────────────────────────────────

    def _build_recon_os_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._os_status = QLabel("OS fingerprinter idle. Run Device Fingerprint scan first, or enter IPs manually.")
        self._os_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._os_status.setWordWrap(True)
        ctrl = QHBoxLayout()
        self._os_hosts_input = QLineEdit()
        self._os_hosts_input.setPlaceholderText("Leave blank to use M1 scan results…")
        btn = QPushButton("🖥  Fingerprint")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_os_fingerprint)
        ctrl.addWidget(self._os_hosts_input, 1)
        ctrl.addWidget(btn)
        self._recon_os_table = _table(["IP", "TTL", "OS Family", "Confidence", "TCP Window", "Banner Hint"])
        self._recon_os_table.setColumnWidth(0, 120)
        self._recon_os_table.setColumnWidth(1, 50)
        self._recon_os_table.setColumnWidth(2, 200)
        self._recon_os_table.setColumnWidth(3, 80)
        self._recon_os_table.setColumnWidth(4, 100)
        lay.addWidget(self._os_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_os_table, 1)
        return w

    @pyqtSlot()
    def _start_os_fingerprint(self):
        from workers.scan_worker import OSFingerprintWorker
        manual = self._os_hosts_input.text().strip()
        if manual:
            ips = [x.strip() for x in manual.replace(",", " ").split() if x.strip()]
        else:
            ips = []
            if self._m1_result:
                for d in self._m1_result.get("devices", []):
                    ip = getattr(d, "ip", None) if not isinstance(d, dict) else d.get("ip")
                    if ip:
                        ips.append(ip)
        if not ips:
            self._os_status.setText("No IPs to fingerprint. Run a scan first or enter IPs manually.")
            return
        if self._os_worker and self._os_worker.isRunning():
            return
        self._recon_os_table.setRowCount(0)
        self._os_worker = OSFingerprintWorker(ips=ips)
        self._os_worker.result.connect(self._on_os_result)
        self._os_worker.status.connect(self._os_status.setText)
        self._os_worker.error.connect(lambda e: self._os_status.setText(f"⚠ {e}"))
        self._os_worker.start()

    @pyqtSlot(dict)
    def _on_os_result(self, data: dict):
        for guess in data.get("guesses", []):
            row = self._recon_os_table.rowCount()
            self._recon_os_table.insertRow(row)
            for col, val in enumerate([
                getattr(guess, "ip", ""),
                str(getattr(guess, "ttl", "")),
                getattr(guess, "os_family", ""),
                getattr(guess, "confidence", ""),
                getattr(guess, "tcp_window", ""),
                getattr(guess, "banner_hint", ""),
            ]):
                self._recon_os_table.setItem(row, col, QTableWidgetItem(str(val)))
        self._os_status.setText(f"Fingerprinted {len(data.get('guesses', []))} host(s).")

    # ── Recon: Risk Scorer tab ────────────────────────────────────────────────

    def _build_recon_risk_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._risk_status = QLabel("Risk scorer idle. Run Device Fingerprint scan first.")
        self._risk_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl = QHBoxLayout()
        btn = QPushButton("🎯  Score All Devices")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._run_risk_scorer)
        ctrl.addWidget(btn)
        ctrl.addStretch()
        self._recon_risk_table = _table(["IP", "Device Type", "Score", "Severity", "Primary Finding", "Remediation"])
        self._recon_risk_table.setColumnWidth(0, 120)
        self._recon_risk_table.setColumnWidth(1, 160)
        self._recon_risk_table.setColumnWidth(2, 55)
        self._recon_risk_table.setColumnWidth(3, 80)
        self._recon_risk_table.setColumnWidth(4, 300)
        lay.addWidget(self._risk_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_risk_table, 1)
        return w

    @pyqtSlot()
    def _run_risk_scorer(self):
        from PyQt6.QtGui import QColor
        if not self._m1_result:
            self._risk_status.setText("No scan data — run Device Fingerprint first.")
            return
        try:
            from modules.risk_scorer import score_devices
            assessments = score_devices(self._m1_result.get("devices", []))
            self._recon_risk_table.setRowCount(0)
            for a in assessments:
                row = self._recon_risk_table.rowCount()
                self._recon_risk_table.insertRow(row)
                color = (RED if a.severity in ("CRITICAL", "HIGH") else
                         AMBER if a.severity == "MEDIUM" else GREEN)
                top_finding = a.findings[0].title if a.findings else "—"
                for col, val in enumerate([
                    a.ip, a.device_type or a.vendor,
                    str(a.total_score), a.severity,
                    top_finding, a.top_remediation,
                ]):
                    item = QTableWidgetItem(str(val))
                    item.setForeground(QColor(color if col in (2, 3) else TEXT_PRIMARY))
                    self._recon_risk_table.setItem(row, col, item)
            critical = sum(1 for a in assessments if a.severity in ("CRITICAL", "HIGH"))
            self._risk_status.setText(
                f"Scored {len(assessments)} device(s) — {critical} HIGH/CRITICAL risk."
            )
        except Exception as exc:
            self._risk_status.setText(f"⚠ Risk scoring failed: {exc}")

    # ── Recon: CVE Lookup tab ─────────────────────────────────────────────────

    def _build_recon_cve_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        info = QLabel(
            "Queries the NVD (National Vulnerability Database) API v2 for known CVEs "
            "matching service versions detected by the port scanner. "
            "Set NVD_API_KEY environment variable for higher rate limits."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._cve_status = QLabel("CVE lookup idle. Run the port scanner first (Advanced Tools tab).")
        self._cve_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._cve_status.setWordWrap(True)
        ctrl = QHBoxLayout()
        self._cve_target_input = QLineEdit()
        self._cve_target_input.setPlaceholderText("Optional: manually add service versions, e.g.  OpenSSH 8.9p1, Apache/2.4.54")
        btn = QPushButton("🛡  Lookup CVEs")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_cve_lookup)
        ctrl.addWidget(self._cve_target_input, 1)
        ctrl.addWidget(btn)
        self._recon_cve_table = _table(["CVE ID", "Service", "Score", "Severity", "Published", "Description"])
        self._recon_cve_table.setColumnWidth(0, 130)
        self._recon_cve_table.setColumnWidth(1, 160)
        self._recon_cve_table.setColumnWidth(2, 55)
        self._recon_cve_table.setColumnWidth(3, 80)
        self._recon_cve_table.setColumnWidth(4, 90)
        lay.addWidget(info)
        lay.addWidget(self._cve_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_cve_table, 1)
        return w

    @pyqtSlot()
    def _start_cve_lookup(self):
        from workers.scan_worker import CVELookupWorker
        if self._cve_worker and self._cve_worker.isRunning():
            return

        # Collect service versions from last port scan result
        versions: list = []
        manual = self._cve_target_input.text().strip()
        if manual:
            versions = [v.strip() for v in manual.split(",") if v.strip()]
        else:
            # Pull from port scan results table
            ps_table = self._ps_table
            version_col = 2  # Version column index in port scan table
            for row in range(ps_table.rowCount()):
                item = ps_table.item(row, version_col)
                if item and item.text().strip():
                    versions.append(item.text().strip())

        if not versions:
            self._cve_status.setText("No service versions found. Run a port scan first or enter versions manually.")
            return

        self._recon_cve_table.setRowCount(0)
        self._cve_worker = CVELookupWorker(service_versions=list(set(versions)))
        self._cve_worker.cve_result.connect(self._on_cve_result)
        self._cve_worker.status.connect(self._cve_status.setText)
        self._cve_worker.finished_all.connect(lambda: self._cve_status.setText(
            self._cve_status.text() + "  ✓ Done."
        ))
        self._cve_worker.start()

    @pyqtSlot(str, object)
    def _on_cve_result(self, service_version: str, result):
        from PyQt6.QtGui import QColor
        for cve in result.cves:
            row = self._recon_cve_table.rowCount()
            self._recon_cve_table.insertRow(row)
            sev = (cve.severity or "NONE").upper()
            color = (RED if sev in ("CRITICAL", "HIGH") else
                     AMBER if sev == "MEDIUM" else
                     BLUE if sev == "LOW" else TEXT_SECONDARY)
            for col, val in enumerate([
                cve.cve_id, service_version,
                f"{cve.cvss_score:.1f}", sev,
                cve.published, cve.description,
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor(color if col in (2, 3) else TEXT_PRIMARY))
                self._recon_cve_table.setItem(row, col, item)

    # ── Recon: Internet Exposure tab ──────────────────────────────────────────

    def _build_recon_exposure_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        info = QLabel(
            "Checks whether LAN devices are reachable from the public internet.\n"
            "Stage 1: fetches your public WAN IP and detects carrier-grade NAT (CGNAT).\n"
            "Stage 2: queries your router's UPnP/IGD (LAN-only SSDP) for port-forwarding rules — "
            "any forwarded port means that service is internet-accessible."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._exposure_status = QLabel("Internet exposure check idle.")
        self._exposure_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._exposure_status.setWordWrap(True)
        self._exposure_verdict = QLabel("")
        self._exposure_verdict.setWordWrap(True)
        self._exposure_verdict.setStyleSheet(
            f"color:{AMBER};font-size:12px;font-weight:bold;padding:6px;"
            f"background:#1a1000;border-radius:6px;"
        )
        self._exposure_verdict.hide()
        ctrl = QHBoxLayout()
        btn = QPushButton("🌐  Check Exposure")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_exposure_check)
        ctrl.addWidget(btn)
        ctrl.addStretch()
        self._recon_exposure_table = _table(
            ["Device IP", "External Port", "Internal Port", "Protocol", "Description", "Enabled"]
        )
        self._recon_exposure_table.setColumnWidth(0, 130)
        self._recon_exposure_table.setColumnWidth(1, 110)
        self._recon_exposure_table.setColumnWidth(2, 110)
        self._recon_exposure_table.setColumnWidth(3, 70)
        self._recon_exposure_table.setColumnWidth(4, 200)
        lay.addWidget(info)
        lay.addWidget(self._exposure_verdict)
        lay.addWidget(self._exposure_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_exposure_table, 1)
        return w

    @pyqtSlot()
    def _start_exposure_check(self):
        from workers.scan_worker import InternetExposureWorker
        if self._exposure_worker and self._exposure_worker.isRunning():
            return
        self._recon_exposure_table.setRowCount(0)
        self._exposure_verdict.hide()
        self._exposure_worker = InternetExposureWorker()
        self._exposure_worker.result.connect(self._on_exposure_result)
        self._exposure_worker.status.connect(self._exposure_status.setText)
        self._exposure_worker.error.connect(lambda e: self._exposure_status.setText(f"⚠ {e}"))
        self._exposure_worker.start()

    @pyqtSlot(object)
    def _on_exposure_result(self, result):
        from PyQt6.QtGui import QColor
        risk_color = RED if result.risk == "HIGH" else AMBER if result.risk == "MEDIUM" else GREEN
        self._exposure_verdict.setText(result.plain_verdict)
        self._exposure_verdict.setStyleSheet(
            f"color:{risk_color};font-size:12px;font-weight:bold;padding:6px;"
            f"background:#1a0000;border-radius:6px;" if result.risk == "HIGH" else
            f"color:{risk_color};font-size:12px;font-weight:bold;padding:6px;"
            f"background:#1a1000;border-radius:6px;"
        )
        self._exposure_verdict.show()
        self._recon_exposure_table.setRowCount(0)
        for m in result.upnp_mappings:
            row = self._recon_exposure_table.rowCount()
            self._recon_exposure_table.insertRow(row)
            row_color = RED if m.enabled else TEXT_SECONDARY
            for col, val in enumerate([
                m.internal_ip, str(m.external_port), str(m.internal_port),
                m.protocol, m.description, "Yes" if m.enabled else "No",
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor(row_color))
                self._recon_exposure_table.setItem(row, col, item)
        self._exposure_status.setText(
            f"WAN IP: {result.wan_ip or 'unknown'} | "
            f"CGNAT: {'Yes' if result.cgnat else 'No'} | "
            f"UPnP mappings: {len(result.upnp_mappings)}"
        )

    def _show_about(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QApplication
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        dlg = QDialog(self)
        dlg.setWindowTitle("About NetSentinel")
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet(self.styleSheet())
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        lay.setContentsMargins(28, 24, 28, 20)

        title = QLabel("NetSentinel")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{ACCENT};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        version = QLabel(f"Version {QApplication.applicationVersion()}")
        version.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Designed for use on networks you own or are authorized to administer. Network Security Scanner & Connectivity Monitor")
        desc.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:13px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)

        author = QLabel("Built by <b>Ossian Ericson</b>")
        author.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:13px;")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)

        linkedin = QLabel(
            '<a href="https://www.linkedin.com/in/ossian-ericson/" '
            f'style="color:{ACCENT};">linkedin.com/in/ossian-ericson</a>'
        )
        linkedin.setOpenExternalLinks(True)
        linkedin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        linkedin.setStyleSheet("font-size:12px;")

        btn_close = QPushButton("Close")
        btn_close.setObjectName("btnNetRefresh")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(dlg.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        btn_row.addStretch()

        disclaimer = QLabel(
            "For use on networks you own or have explicit authorization to test."
        )
        disclaimer.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disclaimer.setWordWrap(True)

        for w in (title, version, desc, author, linkedin):
            lay.addWidget(w)
        lay.addSpacing(8)
        lay.addWidget(disclaimer)
        lay.addSpacing(4)
        lay.addLayout(btn_row)

        dlg.exec()

    # ── Scan orchestration ───────────────────────────────────────────────────

    @pyqtSlot()
    def _start_full_scan(self):
        # Reset UI
        self._m1_result = self._m2_result = self._m3_result = None
        self._m4_result = self._m5_result = None
        self._m1_table.setRowCount(0)
        self._m2_table.setRowCount(0)
        self._m3_table.setRowCount(0)
        self._m4_table.setRowCount(0)
        self._m5_outage_table.setRowCount(0)
        self._net_devices_table.setRowCount(0)
        self._graph.reset()
        self._verdict.update("Pre-scan in progress (flushing caches & sweeping subnet)…", "UNKNOWN")
        self._set_scanning(True)
        self._active_count = 0

        # Run pre-scan first (flush + ping sweep), then kick off modules
        from workers.scan_worker import PreScanWorker
        self._prescan_worker = PreScanWorker(flush_caches=True)
        self._prescan_worker.status.connect(self._on_prescan_status)
        self._prescan_worker.done.connect(self._launch_modules)
        self._prescan_worker.start()

    @pyqtSlot(str)
    def _on_prescan_status(self, m: str):
        """Propagate pre-scan progress to the status bar and all module status labels."""
        self._set_status(m)
        for lbl in (self._m1_status, self._m2_status, self._m3_status,
                    self._m4_status, self._m5_status):
            lbl.setText(m)

    @pyqtSlot()
    def _launch_modules(self):
        try:
            self._launch_modules_impl()
        except Exception as exc:
            self._set_status(f"Scan startup failed: {exc}")
            self._set_scanning(False)
            self._verdict.update(f"Scan failed to start: {exc}", "HIGH")

    def _launch_modules_impl(self):
        from workers.scan_worker import (
            Module1Worker, Module2Worker, Module3Worker,
            Module4Worker, Module5Worker,
        )

        gateway_ip   = self._net_info.get("gateway") if self._net_info else None
        gateway_mac  = self._net_info.get("gateway_mac") if self._net_info else None
        # Pre-populate rogue MACs from the previous scan (best-effort; M1 and M3 run concurrently)
        rogue_macs: list = []
        if self._m1_result:
            for _d in self._m1_result.get("devices", []):
                _risk = _d.risk_level if not isinstance(_d, dict) else _d.get("risk_level", "")
                _mac  = _d.mac        if not isinstance(_d, dict) else _d.get("mac", "")
                if _risk == "HIGH" and _mac:
                    rogue_macs.append(_mac)

        self._verdict.update("Scan in progress…", "UNKNOWN")
        self._workers.clear()
        self._active_count = 0
        # Refresh network info now that caches have been flushed (Fix #14)
        self._refresh_network_info()

        # Module 1 — always runs
        w1 = Module1Worker(self._offenders_path)
        w1.result.connect(self._on_m1_result)
        w1.status.connect(lambda m: (self._set_status(m), self._m1_status.setText(m)))
        w1.error.connect(lambda e: self._m1_status.setText(f"Error: {e}"))
        w1.finished.connect(self._on_worker_done)
        self._workers.append(w1)
        self._active_count += 1

        # Module 2 — needs admin + Scapy
        if self._chk_stp.isChecked():
            w2 = Module2Worker(gateway_mac, duration=self._stp_duration.value())
            w2.bpdu_found.connect(self._on_bpdu_found)
            w2.result.connect(self._on_m2_result)
            w2.status.connect(lambda m: (self._set_status(m), self._m2_status.setText(m)))
            w2.error.connect(lambda e: self._m2_status.setText(f"⚠ {e}"))
            w2.finished.connect(self._on_worker_done)
            self._workers.append(w2)
            self._active_count += 1

        # Module 3
        if self._chk_storm.isChecked():
            w3 = Module3Worker(
                duration=self._storm_duration.value(),
                known_rogue_macs=rogue_macs,
            )
            w3.result.connect(self._on_m3_result)
            w3.status.connect(lambda m: (self._set_status(m), self._m3_status.setText(m)))
            w3.error.connect(lambda e: self._m3_status.setText(f"⚠ {e}"))
            w3.finished.connect(self._on_worker_done)
            self._workers.append(w3)
            self._active_count += 1

        # Module 4
        if self._chk_wifi.isChecked():
            w4 = Module4Worker()
            w4.result.connect(self._on_m4_result)
            w4.status.connect(lambda m: (self._set_status(m), self._m4_status.setText(m)))
            w4.error.connect(lambda e: self._m4_status.setText(f"⚠ {e}"))
            w4.finished.connect(self._on_worker_done)
            self._workers.append(w4)
            self._active_count += 1

        # Module 5
        if self._chk_dns.isChecked():
            w5 = Module5Worker(gateway_ip=gateway_ip)
            w5.ping_point.connect(self._on_ping_point)
            w5.dns_point.connect(self._on_dns_point)
            w5.result.connect(self._on_m5_result)
            w5.status.connect(lambda m: (self._set_status(m), self._m5_status.setText(m)))
            w5.error.connect(lambda e: self._m5_status.setText(f"⚠ {e}"))
            w5.finished.connect(self._on_worker_done)
            self._workers.append(w5)
            self._active_count += 1
            self._graph_timer.start()

        for w in self._workers:
            w.start()

    # ── Module result handlers ────────────────────────────────────────────────

    @pyqtSlot(dict)
    def _on_m1_result(self, data: dict):
        self._m1_result = data
        devices = data.get("devices", [])
        self._m1_table.setRowCount(0)
        for d in devices:
            level   = d.risk_level if not isinstance(d, dict) else d.get("risk_level", "UNKNOWN")
            ip      = d.ip       if not isinstance(d, dict) else d.get("ip", "?")
            host    = d.hostname if not isinstance(d, dict) else d.get("hostname", "")
            mac     = d.mac      if not isinstance(d, dict) else d.get("mac", "?")
            vendor  = d.vendor   if not isinstance(d, dict) else d.get("vendor", "Unknown")
            dtype   = d.device_type if not isinstance(d, dict) else d.get("device_type", "")
            # Fall back to connection_type when device_type is blank
            if not dtype:
                dtype = d.connection_type if not isinstance(d, dict) else d.get("connection_type", "Unknown Device")
            verdict = d.verdict  if not isinstance(d, dict) else d.get("verdict", "")
            _add_row(self._m1_table, [ip, host or "—", mac, vendor, level, dtype, verdict], level)

        self._m1_status.setText(
            f"✓  {data.get('total_count', 0)} devices scanned — "
            f"{data.get('high_risk_count', 0)} HIGH RISK"
        )
        # Mirror into Network Info tab
        self._net_devices_table.setRowCount(0)
        for d in data.get("devices", []):
            level   = d.risk_level if not isinstance(d, dict) else d.get("risk_level", "UNKNOWN")
            ip      = d.ip       if not isinstance(d, dict) else d.get("ip", "?")
            host    = d.hostname if not isinstance(d, dict) else d.get("hostname", "")
            mac     = d.mac      if not isinstance(d, dict) else d.get("mac", "?")
            vendor  = d.vendor   if not isinstance(d, dict) else d.get("vendor", "Unknown")
            _add_row(self._net_devices_table, [ip, host or "—", mac, vendor, level], level)

        # ── Baseline diff ────────────────────────────────────────────────────
        try:
            from modules.utils import load_device_baseline, save_device_baseline, diff_devices_against_baseline
            # Convert device objects to plain dicts for the util function
            dev_dicts = []
            for d in data.get("devices", []):
                dev_dicts.append({
                    "mac":      (d.mac      if not isinstance(d, dict) else d.get("mac", "")),
                    "ip":       (d.ip       if not isinstance(d, dict) else d.get("ip", "")),
                    "hostname": (d.hostname if not isinstance(d, dict) else d.get("hostname", "")),
                    "vendor":   (d.vendor   if not isinstance(d, dict) else d.get("vendor", "")),
                })
            baseline = load_device_baseline()
            new_devs = diff_devices_against_baseline(dev_dicts, baseline)
            save_device_baseline(baseline)
            self._bl_table.setRowCount(0)
            if new_devs:
                self._bl_new_lbl.setText(f"⚠  {len(new_devs)} new device(s) detected since last scan!")
                self._bl_new_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                for nd in new_devs:
                    first = baseline.get((nd.get("mac") or "").lower(), {}).get("first_seen", "—")
                    _add_row(self._bl_table,
                             [nd.get("ip","?"), nd.get("hostname","") or "—",
                              nd.get("mac","?"), nd.get("vendor","Unknown"), first],
                             "MEDIUM")
            else:
                self._bl_new_lbl.setText("✓  No new devices since last scan.")
                self._bl_new_lbl.setStyleSheet(f"color:{GREEN}; font-size:11px;")
        except Exception as _exc:
            self._bl_new_lbl.setText(f"Baseline check failed: {_exc}")

        self._update_overall_verdict()
        # Refresh topology widget with new device list
        try:
            gw_ip  = self._net_info.get("gateway") if self._net_info else None
            gw_mac = self._net_info.get("gateway_mac") if self._net_info else None
            self._topology_widget.render(data.get("devices", []), gw_ip, gw_mac)
        except AttributeError:
            pass  # topology widget not yet initialised
        except Exception as _topo_exc:
            self._set_status(f"Topology render error: {_topo_exc}")
        # Re-apply any active NL search now that new data is loaded
        if hasattr(self, "_m1_search") and self._m1_search.text().strip():
            self._filter_m1_by_nl(self._m1_search.text())

    @pyqtSlot(str)
    def _filter_m1_by_nl(self, text: str):
        """Filter Device Fingerprinter rows using the NL query engine."""
        text = text.strip()
        # Clear filter — show all rows
        if not text:
            for row in range(self._m1_table.rowCount()):
                self._m1_table.setRowHidden(row, False)
            if self._m1_result:
                self._m1_status.setText(
                    f"✓  {self._m1_result.get('total_count', 0)} devices scanned — "
                    f"{self._m1_result.get('high_risk_count', 0)} HIGH RISK"
                )
            return
        if not self._m1_result:
            return
        try:
            from modules.nl_query import query as _nl_query
            devices = self._m1_result.get("devices", [])
            result = _nl_query(devices, text)
            if result.error:
                self._m1_status.setText(f"⚠  {result.error}")
                return
            matched_ips = {
                (m.device.ip if not isinstance(m.device, dict) else m.device.get("ip", ""))
                for m in result.matches
            }
            for row in range(self._m1_table.rowCount()):
                ip_item = self._m1_table.item(row, 0)
                ip = ip_item.text() if ip_item else ""
                self._m1_table.setRowHidden(row, ip not in matched_ips)
            self._m1_status.setText(
                f"Filter: {len(matched_ips)} match(es) — {result.explanation}"
            )
        except Exception as exc:
            self._m1_status.setText(f"Filter error: {exc}")

    @pyqtSlot(object)
    def _on_bpdu_found(self, bpdu):
        level = "HIGH" if bpdu.is_rogue else "CLEAN"
        _add_row(
            self._m2_table,
            [
                bpdu.src_mac, bpdu.bpdu_type, bpdu.root_mac,
                str(bpdu.bridge_priority),
                f"{bpdu.hello_time:.1f}", f"{bpdu.max_age:.1f}", f"{bpdu.forward_delay:.1f}",
                "\u26a0 YES" if bpdu.is_rogue else "No",
            ],
            level,
        )
        if bpdu.is_rogue:
            self._m2_status.setText(f"\u26a0 ROGUE ROOT BRIDGE: {bpdu.src_mac}")

    @pyqtSlot(dict)
    def _on_m2_result(self, data: dict):
        self._m2_result = data
        rogue = data.get("rogue_count", 0)
        total = data.get("total_bpdus", 0)
        self._m2_status.setText(
            f"✓  {total} BPDU frame(s) captured — {rogue} rogue Root Bridge claim(s)"
        )
        self._update_overall_verdict()

    @pyqtSlot(object)
    def _on_m3_result(self, storm):
        self._m3_result = storm
        level = storm.storm_level if not isinstance(storm, dict) else storm.get("storm_level", "?")
        bps   = storm.bcast_per_sec if not isinstance(storm, dict) else storm.get("bcast_per_sec", 0)
        mps   = storm.mcast_per_sec if not isinstance(storm, dict) else storm.get("mcast_per_sec", 0)
        ratio = storm.bcast_ratio if not isinstance(storm, dict) else storm.get("bcast_ratio", 0)
        top5  = storm.top_sources if not isinstance(storm, dict) else storm.get("top_sources", [])
        rogues = set(storm.rogue_matches if not isinstance(storm, dict) else storm.get("rogue_matches", []))

        self._update_stat(self._m3_bcast_lbl, f"{bps:.1f}", _color_for_level(level))
        self._update_stat(self._m3_mcast_lbl, f"{mps:.1f}")
        self._update_stat(self._m3_ratio_lbl, f"{ratio:.1%}")
        self._update_stat(self._m3_level_lbl, level, _color_for_level(level))

        self._m3_table.setRowCount(0)
        for mac, count in top5:
            is_rogue = mac in rogues
            _add_row(
                self._m3_table,
                [mac, str(count), "⚠ YES — CONFIRMED SABOTAGE" if is_rogue else "No"],
                "HIGH" if is_rogue else "CLEAN",
            )

        self._m3_status.setText(f"✓  Storm level: {level} ({bps:.1f} bcast/s)")
        self._update_overall_verdict()

    @pyqtSlot(object)
    def _on_m4_result(self, wifi):
        self._m4_result = wifi
        networks = wifi.networks if not isinstance(wifi, dict) else wifi.get("networks", [])
        self._m4_table.setRowCount(0)
        for n in networks:
            ssid  = n.ssid if not isinstance(n, dict) else n.get("ssid", "")
            bssid = n.bssid if not isinstance(n, dict) else n.get("bssid", "")
            ch    = n.channel if not isinstance(n, dict) else n.get("channel", 0)
            band  = n.band if not isinstance(n, dict) else n.get("band", "?")
            sig   = n.signal_dbm if not isinstance(n, dict) else n.get("signal_dbm", 0)
            hidden = n.is_hidden if not isinstance(n, dict) else n.get("is_hidden", False)
            rogue  = n.is_rogue_ssid if not isinstance(n, dict) else n.get("is_rogue_ssid", False)
            conflict = n.co_channel_conflict if not isinstance(n, dict) else n.get("co_channel_conflict", False)
            level = "HIGH" if rogue else ("MEDIUM" if conflict else ("LOW" if hidden else "CLEAN"))
            _add_row(
                self._m4_table,
                [
                    ssid or "[HIDDEN]", bssid, str(ch), band, str(sig),
                    "Yes" if hidden else "No",
                    "⚠ Yes" if rogue else "No",
                    "⚠ Yes" if conflict else "No",
                ],
                level,
            )

        rogue_c = wifi.rogue_count if not isinstance(wifi, dict) else wifi.get("rogue_count", 0)
        hidden_c = wifi.hidden_count if not isinstance(wifi, dict) else wifi.get("hidden_count", 0)
        self._m4_status.setText(
            f"✓  {len(networks)} networks — {rogue_c} suspicious SSIDs, {hidden_c} hidden"
        )
        self._update_overall_verdict()

    @pyqtSlot(object)
    def _on_ping_point(self, pt):
        self._graph.add_ping_point(pt.timestamp, pt.target, pt.rtt_ms)

    @pyqtSlot(object)
    def _on_dns_point(self, pt):
        self._graph.add_ping_point(pt.timestamp, "DNS", pt.rtt_ms)

    @pyqtSlot(object)
    def _on_m5_result(self, corr):
        self._m5_result = corr
        self._graph_timer.stop()
        self._graph.redraw()

        outages  = corr.micro_outages   if not isinstance(corr, dict) else corr.get("micro_outages", [])
        stp_list = corr.stp_signatures  if not isinstance(corr, dict) else corr.get("stp_signatures", [])
        self._m5_outage_table.setRowCount(0)
        for o in outages:
            is_stp = o in stp_list
            level = "HIGH" if is_stp else "MEDIUM"
            _add_row(
                self._m5_outage_table,
                [
                    o.get("target", "?"),
                    f"{o.get('duration', 0):.1f}",
                    str(o.get("consecutive_drops", 0)),
                    "⚠ YES — STP" if is_stp else "No",
                    level,
                ],
                level,
            )

        self._m5_status.setText(
            f"\u2713  {len(outages)} outage(s) \u2014 "
            f"{len(stp_list)} "
            "STP reconvergence signature(s)"
        )
        self._update_overall_verdict()

    def _refresh_graph(self):
        self._graph.redraw()

    @pyqtSlot()
    def _on_worker_done(self):
        self._active_count -= 1
        if self._active_count <= 0:
            self._active_count = 0
            self._set_scanning(False)
            self._set_status("Scan complete.")
            self._graph_timer.stop()
            self._graph.redraw()
            self._workers.clear()

    # ── Overall verdict ───────────────────────────────────────────────────────

    def _update_overall_verdict(self):
        verdicts = []
        level = "CLEAN"

        if self._m1_result:
            v = self._m1_result.get("plain_verdict", "")
            if v:
                verdicts.append(v)
            if self._m1_result.get("high_risk_count", 0) > 0:
                level = "HIGH"

        if self._m2_result:
            v = self._m2_result.get("plain_verdict", "")
            if v:
                verdicts.append(v)
            if self._m2_result.get("rogue_count", 0) > 0:
                level = "HIGH"

        if self._m3_result:
            storm_level = (
                self._m3_result.storm_level
                if not isinstance(self._m3_result, dict)
                else self._m3_result.get("storm_level", "CLEAN")
            )
            v = (
                self._m3_result.plain_verdict
                if not isinstance(self._m3_result, dict)
                else self._m3_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            if storm_level in ("STORM", "WARNING") and level == "CLEAN":
                level = "MEDIUM" if storm_level == "WARNING" else "HIGH"

        if self._m4_result:
            v = (
                self._m4_result.plain_verdict
                if not isinstance(self._m4_result, dict)
                else self._m4_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            rogue_c = (
                self._m4_result.rogue_count
                if not isinstance(self._m4_result, dict)
                else self._m4_result.get("rogue_count", 0)
            )
            if rogue_c and level == "CLEAN":
                level = "MEDIUM"

        if self._m5_result:
            v = (
                self._m5_result.plain_verdict
                if not isinstance(self._m5_result, dict)
                else self._m5_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            stp_sigs = (
                self._m5_result.stp_signatures
                if not isinstance(self._m5_result, dict)
                else self._m5_result.get("stp_signatures", [])
            )
            if stp_sigs:
                level = "HIGH"

        if self._diag_result:
            v = getattr(self._diag_result, "plain_verdict", "") or ""
            if v:
                verdicts.append(f"Diagnostics: {v}")
            # Failed ping to gateway → escalate
            gw_ping = next(
                (p for p in getattr(self._diag_result, "ping_results", []) if p.host == "Gateway"),
                None,
            )
            if gw_ping and gw_ping.status == "FAIL" and level == "CLEAN":
                level = "HIGH"
            # DNS leak
            leak = getattr(self._diag_result, "dns_leak", None)
            if leak and getattr(leak, "leak_detected", False) and level == "CLEAN":
                level = "MEDIUM"

        combined = "\n\n".join(verdicts) if verdicts else "Scan in progress..."
        self._verdict.update(combined, level)

    # ── Export ────────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _export_report(self):
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        default_dir = str(Path.home() / "Desktop")

        path_str, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            str(Path(default_dir) / f"netsentinel_report_{ts}.html"),
            "HTML Report (*.html);;JSON Export (*.json);;CSV Device List (*.csv);;Nmap XML (*.xml);;All Files (*)",
        )
        if not path_str:
            return

        out = Path(path_str)

        # Determine overall level
        level = "CLEAN"
        if self._m1_result and self._m1_result.get("high_risk_count", 0):
            level = "HIGH"
        if self._m2_result and self._m2_result.get("rogue_count", 0):
            level = "HIGH"
        overall = self._verdict._text.text()

        try:
            suffix = out.suffix.lower()
            if suffix == ".json":
                from modules.report_exporter import save_json_report
                save_json_report(
                    out,
                    module1_data=self._m1_result,
                    module2_data=self._m2_result,
                    module3_data=self._m3_result,
                    module4_data=self._m4_result,
                    module5_data=self._m5_result,
                    diagnostics_data=self._diag_result,
                    network_info_data=self._net_info if self._net_info else None,
                    overall_verdict=overall,
                    overall_level=level,
                )
            elif suffix == ".csv":
                from modules.report_exporter import save_csv_report
                save_csv_report(out, self._m1_result)
            elif suffix == ".xml":
                from modules.report_exporter import save_nmap_xml_report
                ps_result = getattr(self, "_last_portscan_result", None)
                save_nmap_xml_report(out, self._m1_result, ps_result)
            else:
                from modules.report_exporter import save_report
                save_report(
                    out,
                    module1_data=self._m1_result,
                    module2_data=self._m2_result,
                    module3_data=self._m3_result,
                    module4_data=self._m4_result,
                    module5_data=self._m5_result,
                    diagnostics_data=self._diag_result,
                    network_info_data=self._net_info if self._net_info else None,
                    overall_verdict=overall,
                    overall_level=level,
                )
                webbrowser.open(out.as_uri())
            self._set_status(f"Report saved: {out.name}")
        except Exception as exc:
            self._set_status(f"Export failed: {exc}")

    # ── Network Info ──────────────────────────────────────────────────────────

    def _refresh_network_info(self):
        from workers.scan_worker import NetworkInfoWorker
        # Guard: don't start a second worker if one is already running
        if hasattr(self, "_net_info_worker") and self._net_info_worker and self._net_info_worker.isRunning():
            return
        self._net_info_worker = NetworkInfoWorker()
        self._net_info_worker.result.connect(self._update_net_info_ui)
        self._net_info_worker.error.connect(lambda e: self._net_info_label.setText(f"Error: {e}"))
        self._net_info_worker.start()
        self._net_info_label.setText("Refreshing network information…")

    # ── Diagnostics ───────────────────────────────────────────────────────────

    @pyqtSlot()
    def _start_diagnostics(self):
        from workers.scan_worker import DiagnosticsWorker
        if self._diag_worker and self._diag_worker.isRunning():
            return
        self._diag_ping_table.setRowCount(0)
        self._diag_dns_table.setRowCount(0)
        self._diag_trace_table.setRowCount(0)
        for lbl in self._diag_http_labels:
            lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding:0 10px;")
            name = lbl.text().split(":")[0].lstrip("● ")
            lbl.setText(f"● {name}: testing…")
        self._update_stat(self._diag_speed_lbl, "…")
        self._update_stat(self._diag_public_lbl, "…")
        self._update_stat(self._diag_dns_lbl, "…")
        self._update_stat(self._diag_gw_lbl, "…")
        self._btn_diag.setEnabled(False)
        self._diag_status_lbl.setText("Running diagnostics…")

        gw = self._net_info.get("gateway") if self._net_info else None
        self._diag_worker = DiagnosticsWorker(gateway_ip=gw)
        self._diag_worker.status.connect(lambda m: self._diag_status_lbl.setText(m))
        self._diag_worker.result.connect(self._on_diag_result)
        self._diag_worker.error.connect(
            lambda e: (
                self._diag_status_lbl.setText(f"Error: {e}"),
                self._btn_diag.setEnabled(True),
            )
        )
        self._diag_worker.finished.connect(lambda: self._btn_diag.setEnabled(True))
        self._diag_worker.start()

    @pyqtSlot(object)
    def _on_diag_result(self, result):
        from ui.styles import GREEN, AMBER, RED, TEXT_SECONDARY, TEXT_PRIMARY, BLUE

        self._diag_result = result

        # Ping table
        self._diag_ping_table.setRowCount(0)
        for p in result.ping_results:
            color = GREEN if p.status == "OK" else (AMBER if p.status == "SLOW" else RED)
            rtt_str = f"{p.rtt_ms:.0f}" if p.rtt_ms >= 0 else "unreachable"
            row = self._diag_ping_table.rowCount()
            self._diag_ping_table.insertRow(row)
            for col, val in enumerate([p.host, p.ip, rtt_str, p.status]):
                item = QTableWidgetItem(str(val))
                item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                        color if col == 3 else TEXT_PRIMARY
                    )
                )
                self._diag_ping_table.setItem(row, col, item)

        # DNS table
        self._diag_dns_table.setRowCount(0)
        for d in result.dns_results:
            color = GREEN if d.status == "OK" else (AMBER if d.status == "SLOW" else RED)
            lat_str = f"{d.latency_ms:.0f} ms" if d.latency_ms >= 0 else "failed"
            row = self._diag_dns_table.rowCount()
            self._diag_dns_table.insertRow(row)
            for col, val in enumerate([d.server, lat_str, d.resolved_ip, d.status]):
                item = QTableWidgetItem(str(val))
                item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                        color if col == 3 else TEXT_PRIMARY
                    )
                )
                self._diag_dns_table.setItem(row, col, item)

        # HTTP labels
        for i, h in enumerate(result.http_results):
            if i < len(self._diag_http_labels):
                lbl = self._diag_http_labels[i]
                color = GREEN if h.status == "OK" else (AMBER if h.status == "PARTIAL" else RED)
                code_str = str(h.status_code) if h.status_code else "—"
                lbl.setText(f"● {h.url}: {h.status} ({code_str})")
                lbl.setStyleSheet(f"color:{color}; font-size:11px; padding:0 10px;")

        # Traceroute
        self._diag_trace_table.setRowCount(0)
        for hop in result.trace_hops:
            rtt_str = f"{hop.rtt_ms:.0f}" if hop.rtt_ms >= 0 else "—"
            row = self._diag_trace_table.rowCount()
            self._diag_trace_table.insertRow(row)
            for col, val in enumerate([str(hop.hop), hop.ip, rtt_str]):
                self._diag_trace_table.setItem(row, col, QTableWidgetItem(val))

        # Summary stats
        gw_ping = next((p for p in result.ping_results if p.host == "Gateway"), None)
        gw_str = (f"{gw_ping.rtt_ms:.0f} ms" if gw_ping and gw_ping.rtt_ms >= 0 else "—")
        gw_col = GREEN if gw_ping and gw_ping.status == "OK" else (AMBER if gw_ping and gw_ping.status == "SLOW" else RED)
        self._update_stat(self._diag_gw_lbl, gw_str, gw_col)

        speed_str = (
            f"{result.download_mbps:.1f} Mbps"
            if result.download_mbps >= 1
            else (f"{result.download_mbps * 1000:.0f} Kbps" if result.download_mbps > 0 else "—")
        )
        self._update_stat(self._diag_speed_lbl, speed_str, GREEN if result.download_mbps > 0 else RED)
        self._update_stat(self._diag_public_lbl, result.public_ip or "—", BLUE if result.public_ip else RED)

        sys_dns = next((d for d in result.dns_results if d.server == "System DNS"), None)
        dns_str = f"{sys_dns.latency_ms:.0f} ms" if sys_dns and sys_dns.latency_ms >= 0 else "—"
        dns_col = GREEN if sys_dns and sys_dns.status == "OK" else (AMBER if sys_dns and sys_dns.status == "SLOW" else RED)
        self._update_stat(self._diag_dns_lbl, dns_str, dns_col)

        self._diag_status_lbl.setText(f"Diagnostics complete.  {result.plain_verdict}")
        self._btn_diag.setEnabled(True)

        # DNS Leak
        from PyQt6.QtGui import QColor
        leak = getattr(result, "dns_leak", None)
        self._diag_leak_table.setRowCount(0)
        if leak:
            color = RED if leak.leak_detected else GREEN
            self._diag_leak_lbl.setText(leak.plain_verdict)
            self._diag_leak_lbl.setStyleSheet(f"color:{color}; font-size:11px; padding-left:10px;")
            for e in leak.resolvers_seen:
                r = self._diag_leak_table.rowCount()
                self._diag_leak_table.insertRow(r)
                for col, val in enumerate([e.server_ip, e.country, e.org]):
                    self._diag_leak_table.setItem(r, col, QTableWidgetItem(val))

        self._update_overall_verdict()

    # ── Recon: Credentialed SSH Scan ─────────────────────────────────────────

    def _build_recon_cred_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QFormLayout, QComboBox
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Connects to a remote host via SSH and collects:\n"
            "installed packages, running services, local users, patch level,\n"
            "listening ports, sudo NOPASSWD entries, and failed login attempts.\n"
            "Requires SSH access (password or private key). "
            "Works on Linux, macOS, and Windows (OpenSSH)."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setContentsMargins(0, 0, 0, 0)
        self._cred_host    = QLineEdit(); self._cred_host.setPlaceholderText("192.168.1.1")
        self._cred_port    = QSpinBox(); self._cred_port.setRange(1, 65535); self._cred_port.setValue(22)
        self._cred_user    = QLineEdit(); self._cred_user.setPlaceholderText("root")
        self._cred_pass    = QLineEdit(); self._cred_pass.setPlaceholderText("(leave blank to use key)")
        self._cred_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._cred_key     = QLineEdit(); self._cred_key.setPlaceholderText("/home/user/.ssh/id_rsa")
        self._cred_os      = QComboBox()
        self._cred_os.addItems(["auto", "linux", "macos", "windows"])
        form.addRow("Host:", self._cred_host)
        form.addRow("SSH Port:", self._cred_port)
        form.addRow("Username:", self._cred_user)
        form.addRow("Password:", self._cred_pass)
        form.addRow("Key file:", self._cred_key)
        form.addRow("OS hint:", self._cred_os)

        ctrl = QHBoxLayout()
        self._btn_cred = QPushButton("🔑  Run Credentialed Scan")
        self._btn_cred.setObjectName("btnNetRefresh")
        self._btn_cred.clicked.connect(self._start_cred_scan)
        self._btn_cred_stop = QPushButton("⏹  Stop")
        self._btn_cred_stop.clicked.connect(lambda: self._cred_worker and self._cred_worker.stop())
        ctrl.addWidget(self._btn_cred)
        ctrl.addWidget(self._btn_cred_stop)
        ctrl.addStretch()

        self._cred_status = QLabel("Credentialed scan idle.")
        self._cred_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._cred_status.setWordWrap(True)

        self._cred_verdict = QLabel("")
        self._cred_verdict.setWordWrap(True)
        self._cred_verdict.setStyleSheet(
            f"color:{GREEN};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:6px;"
        )
        self._cred_verdict.hide()

        self._recon_cred_sw_table   = _table(["Package", "Version", "Source"])
        self._recon_cred_svc_table  = _table(["Service", "Status", "PID"])
        self._recon_cred_user_table = _table(["User", "UID / SID", "Home", "Shell"])

        from PyQt6.QtWidgets import QTabWidget as _TW
        inner_tabs = _TW()
        inner_tabs.addTab(self._recon_cred_sw_table,   "📦 Software")
        inner_tabs.addTab(self._recon_cred_svc_table,  "⚙ Services")
        inner_tabs.addTab(self._recon_cred_user_table, "👤 Users")

        lay.addWidget(info)
        lay.addWidget(form_w)
        lay.addWidget(self._cred_verdict)
        lay.addWidget(self._cred_status)
        lay.addLayout(ctrl)
        lay.addWidget(inner_tabs, 1)
        return w

    @pyqtSlot()
    def _start_cred_scan(self):
        from workers.scan_worker import CredentialedScanWorker
        host = self._cred_host.text().strip()
        if not host:
            self._cred_status.setText("⚠ Enter a host IP or hostname.")
            return
        if self._cred_worker and self._cred_worker.isRunning():
            return
        self._recon_cred_sw_table.setRowCount(0)
        self._recon_cred_svc_table.setRowCount(0)
        self._recon_cred_user_table.setRowCount(0)
        self._cred_verdict.hide()
        self._cred_worker = CredentialedScanWorker(
            host=host,
            ssh_port=self._cred_port.value(),
            username=self._cred_user.text().strip() or "root",
            password=self._cred_pass.text(),
            key_path=self._cred_key.text().strip(),
            os_hint=self._cred_os.currentText(),
        )
        self._cred_worker.result.connect(self._on_cred_result)
        self._cred_worker.status.connect(self._cred_status.setText)
        self._cred_worker.error.connect(lambda e: self._cred_status.setText(f"⚠ {e}"))
        self._cred_worker.start()

    @pyqtSlot(object)
    def _on_cred_result(self, res):
        from PyQt6.QtWidgets import QTableWidgetItem as _TWI
        flags = res.risk_flags
        color = RED if flags else GREEN
        self._cred_verdict.setText(res.plain_verdict + (f"\n⚠ {' | '.join(flags)}" if flags else ""))
        self._cred_verdict.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:6px;"
        )
        self._cred_verdict.show()
        self._cred_status.setText("Credentialed scan complete.")

        for sw in res.software:
            r = self._recon_cred_sw_table.rowCount()
            self._recon_cred_sw_table.insertRow(r)
            for c, v in enumerate([sw.name, sw.version, sw.source]):
                self._recon_cred_sw_table.setItem(r, c, _TWI(v))

        for svc in res.services:
            r = self._recon_cred_svc_table.rowCount()
            self._recon_cred_svc_table.insertRow(r)
            for c, v in enumerate([svc.name, svc.status, str(svc.pid) if svc.pid else ""]):
                self._recon_cred_svc_table.setItem(r, c, _TWI(v))

        for u in res.users:
            r = self._recon_cred_user_table.rowCount()
            self._recon_cred_user_table.insertRow(r)
            for c, v in enumerate([u.username, u.uid, u.home, u.shell]):
                self._recon_cred_user_table.setItem(r, c, _TWI(v))

    # ── Recon: Ultra-fast Combined Discovery ─────────────────────────────────

    def _build_recon_discovery_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Runs all discovery methods in parallel and merges results:\n"
            "• ARP cache (passive, instant)\n"
            "• ARP broadcast sweep (Scapy — requires admin)\n"
            "• ICMP ping sweep (64 parallel threads)\n"
            "• TCP SYN probe to ports 80/443/22/8080 (Scapy)\n"
            "• mDNS query (zero-conf devices: printers, Chromecast, Apple TV)\n"
            "Typically completes a /24 in under 3 seconds."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        ctrl = QHBoxLayout()
        self._disc_cidr = QLineEdit()
        self._disc_cidr.setPlaceholderText("192.168.1.0/24  (blank = auto-detect)")
        self._disc_cidr.setMaximumWidth(260)
        self._disc_passive_chk = QCheckBox("Passive only (no active probes)")
        self._btn_disc = QPushButton("🚀  Start Discovery")
        self._btn_disc.setObjectName("btnNetRefresh")
        self._btn_disc.clicked.connect(self._start_discovery)
        self._btn_disc_stop = QPushButton("⏹  Stop")
        self._btn_disc_stop.clicked.connect(lambda: self._discovery_worker and self._discovery_worker.stop())
        ctrl.addWidget(self._disc_cidr)
        ctrl.addWidget(self._disc_passive_chk)
        ctrl.addWidget(self._btn_disc)
        ctrl.addWidget(self._btn_disc_stop)
        ctrl.addStretch()

        self._disc_status = QLabel("Combined discovery idle.")
        self._disc_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._disc_status.setWordWrap(True)

        self._recon_disc_table = _table(["IP", "MAC", "Hostname", "Methods", "Latency (ms)"])
        self._recon_disc_table.setColumnWidth(0, 130)
        self._recon_disc_table.setColumnWidth(1, 140)
        self._recon_disc_table.setColumnWidth(2, 200)
        self._recon_disc_table.setColumnWidth(3, 180)

        lay.addWidget(info)
        lay.addLayout(ctrl)
        lay.addWidget(self._disc_status)
        lay.addWidget(self._recon_disc_table, 1)
        return w

    @pyqtSlot()
    def _start_discovery(self):
        from workers.scan_worker import CombinedDiscoveryWorker
        if self._discovery_worker and self._discovery_worker.isRunning():
            return
        self._recon_disc_table.setRowCount(0)
        self._disc_status.setText("Starting combined discovery…")
        self._discovery_worker = CombinedDiscoveryWorker(
            cidr=self._disc_cidr.text().strip(),
            passive_only=self._disc_passive_chk.isChecked(),
        )
        self._discovery_worker.result.connect(self._on_discovery_result)
        self._discovery_worker.status.connect(self._disc_status.setText)
        self._discovery_worker.error.connect(lambda e: self._disc_status.setText(f"⚠ {e}"))
        self._discovery_worker.start()

    @pyqtSlot(object)
    def _on_discovery_result(self, res):
        from PyQt6.QtWidgets import QTableWidgetItem as _TWI
        self._disc_status.setText(res.plain_verdict)
        for dev in res.devices:
            r = self._recon_disc_table.rowCount()
            self._recon_disc_table.insertRow(r)
            ms = f"{dev.response_ms:.0f}" if dev.response_ms else ""
            for c, v in enumerate([dev.ip, dev.mac, dev.hostname,
                                    ", ".join(dev.discovery_methods), ms]):
                self._recon_disc_table.setItem(r, c, _TWI(v))

    # ── Recon: SMB / NetBIOS Enumerator ──────────────────────────────────────

    def _build_recon_smb_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QFormLayout, QTabWidget as _TW
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "NetBIOS + SMB enumeration.\n"
            "Tier 1 (no credentials): machine name, workgroup/domain, OS version, "
            "anonymous session check, share list (Windows scanner only).\n"
            "Tier 2 (with credentials): full share list, local users, active sessions, "
            "local groups. Requires impacket or Windows net.exe."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setContentsMargins(0, 0, 0, 0)
        self._smb_host   = QLineEdit(); self._smb_host.setPlaceholderText("192.168.1.1")
        self._smb_user   = QLineEdit(); self._smb_user.setPlaceholderText("(blank = Tier 1 only)")
        self._smb_pass   = QLineEdit(); self._smb_pass.setPlaceholderText("")
        self._smb_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._smb_domain = QLineEdit(); self._smb_domain.setPlaceholderText("WORKGROUP")
        form.addRow("Host:", self._smb_host)
        form.addRow("Username:", self._smb_user)
        form.addRow("Password:", self._smb_pass)
        form.addRow("Domain:", self._smb_domain)

        ctrl = QHBoxLayout()
        self._btn_smb = QPushButton("🗂  Enumerate SMB")
        self._btn_smb.setObjectName("btnNetRefresh")
        self._btn_smb.clicked.connect(self._start_smb_enum)
        self._btn_smb_stop = QPushButton("⏹  Stop")
        self._btn_smb_stop.clicked.connect(lambda: self._smb_worker and self._smb_worker.stop())
        ctrl.addWidget(self._btn_smb)
        ctrl.addWidget(self._btn_smb_stop)
        ctrl.addStretch()

        self._smb_status = QLabel("SMB enumeration idle.")
        self._smb_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._smb_status.setWordWrap(True)

        self._smb_verdict = QLabel("")
        self._smb_verdict.setWordWrap(True)
        self._smb_verdict.setStyleSheet(
            f"color:{AMBER};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:6px;"
        )
        self._smb_verdict.hide()

        self._recon_smb_shares_table = _table(["Share", "Type", "Comment", "Risk"])
        self._recon_smb_users_table  = _table(["Username", "SID / UID", "Full Name", "Last Logon"])

        inner_tabs = _TW()
        inner_tabs.addTab(self._recon_smb_shares_table, "📁 Shares")
        inner_tabs.addTab(self._recon_smb_users_table,  "👤 Users")

        lay.addWidget(info)
        lay.addWidget(form_w)
        lay.addWidget(self._smb_verdict)
        lay.addWidget(self._smb_status)
        lay.addLayout(ctrl)
        lay.addWidget(inner_tabs, 1)
        return w

    @pyqtSlot()
    def _start_smb_enum(self):
        from workers.scan_worker import SMBEnumWorker
        host = self._smb_host.text().strip()
        if not host:
            self._smb_status.setText("⚠ Enter a host IP or hostname.")
            return
        if self._smb_worker and self._smb_worker.isRunning():
            return
        self._recon_smb_shares_table.setRowCount(0)
        self._recon_smb_users_table.setRowCount(0)
        self._smb_verdict.hide()
        self._smb_worker = SMBEnumWorker(
            host=host,
            username=self._smb_user.text().strip(),
            password=self._smb_pass.text(),
            domain=self._smb_domain.text().strip(),
        )
        self._smb_worker.result.connect(self._on_smb_result)
        self._smb_worker.status.connect(self._smb_status.setText)
        self._smb_worker.error.connect(lambda e: self._smb_status.setText(f"⚠ {e}"))
        self._smb_worker.start()

    @pyqtSlot(object)
    def _on_smb_result(self, res):
        from PyQt6.QtWidgets import QTableWidgetItem as _TWI
        flags = res.risk_flags
        color = RED if any("Anonymous" in f or "DC" in f for f in flags) else (AMBER if flags else GREEN)
        self._smb_verdict.setText(res.plain_verdict + (f"\n⚠ {' | '.join(flags)}" if flags else ""))
        self._smb_verdict.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:6px;"
        )
        self._smb_verdict.show()
        self._smb_status.setText("SMB enumeration complete.")

        high_risk = {"DISK"}
        for share in res.shares:
            r = self._recon_smb_shares_table.rowCount()
            self._recon_smb_shares_table.insertRow(r)
            risk = "HIGH" if (share.share_type in high_risk and not share.name.endswith("$")) else "—"
            for c, v in enumerate([share.name, share.share_type, share.comment, risk]):
                item = _TWI(v)
                if risk == "HIGH":
                    from PyQt6.QtGui import QColor
                    item.setForeground(QColor(RED))
                self._recon_smb_shares_table.setItem(r, c, item)

        for u in res.users:
            r = self._recon_smb_users_table.rowCount()
            self._recon_smb_users_table.insertRow(r)
            for c, v in enumerate([u.username, u.uid, u.full_name, u.last_logon]):
                self._recon_smb_users_table.setItem(r, c, _TWI(v))

    # ── Recon: Plugin System ──────────────────────────────────────────────────

    def _build_recon_plugin_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Custom plugins extend NetSentinel with your own checks.\n"
            "Each plugin is a .py file in the plugins/ folder (shown below) with a "
            "PLUGIN_META dict and a run(devices) function that returns a PluginResult.\n"
            "Click Reload to re-scan the folder after adding or editing a plugin."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        ctrl = QHBoxLayout()
        self._btn_plugin_reload = QPushButton("↺  Reload Plugins")
        self._btn_plugin_reload.setObjectName("btnNetRefresh")
        self._btn_plugin_reload.clicked.connect(self._reload_plugins)

        self._btn_plugin_open_dir = QPushButton("📂  Open Plugins Folder")
        self._btn_plugin_open_dir.setObjectName("btnNetRefresh")
        self._btn_plugin_open_dir.clicked.connect(self._open_plugins_dir)

        self._btn_plugin_run = QPushButton("▶  Run Selected")
        self._btn_plugin_run.setObjectName("btnNetRefresh")
        self._btn_plugin_run.clicked.connect(self._run_selected_plugin)

        ctrl.addWidget(self._btn_plugin_reload)
        ctrl.addWidget(self._btn_plugin_open_dir)
        ctrl.addWidget(self._btn_plugin_run)
        ctrl.addStretch()

        self._plugin_dir_lbl = QLabel("")
        self._plugin_dir_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")

        self._plugin_list_table = _table(["Plugin", "Version", "Tags", "Description", "Author"])
        self._plugin_list_table.setColumnWidth(0, 180)
        self._plugin_list_table.setColumnWidth(1, 60)
        self._plugin_list_table.setColumnWidth(2, 120)
        self._plugin_list_table.setColumnWidth(3, 300)

        self._plugin_status = QLabel("Click Reload Plugins to discover .py files in the plugins folder.")
        self._plugin_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._plugin_status.setWordWrap(True)

        self._plugin_result_text = QTextEdit()
        self._plugin_result_text.setReadOnly(True)
        self._plugin_result_text.setMaximumHeight(160)
        self._plugin_result_text.setStyleSheet(
            f"background:{BG_CARD};color:{TEXT_PRIMARY};font-size:11px;"
            "border:1px solid #2a2a4a;border-radius:6px;padding:6px;"
        )
        self._plugin_result_text.setPlaceholderText("Plugin output will appear here…")

        lay.addWidget(info)
        lay.addLayout(ctrl)
        lay.addWidget(self._plugin_dir_lbl)
        lay.addWidget(self._plugin_list_table, 1)
        lay.addWidget(self._plugin_status)
        lay.addWidget(self._plugin_result_text)

        self._plugins: list = []
        self._plugin_worker = None
        self._reload_plugins()
        return w

    @pyqtSlot()
    def _reload_plugins(self):
        from modules.plugin_system import load_plugins, plugins_dir
        self._plugins = load_plugins()
        d = plugins_dir()
        self._plugin_dir_lbl.setText(f"Plugins folder: {d}")
        self._plugin_list_table.setRowCount(0)
        for p in self._plugins:
            r = self._plugin_list_table.rowCount()
            self._plugin_list_table.insertRow(r)
            for c, v in enumerate([p.name, p.version, p.tag_str, p.description, p.author]):
                self._plugin_list_table.setItem(r, c, QTableWidgetItem(v))
        n = len(self._plugins)
        self._plugin_status.setText(
            f"{n} plugin{'s' if n != 1 else ''} loaded. Select one and click Run Selected."
        )

    @pyqtSlot()
    def _open_plugins_dir(self):
        from modules.plugin_system import plugins_dir
        import subprocess, sys
        d = str(plugins_dir())
        if sys.platform == "win32":
            subprocess.Popen(["explorer", d])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    @pyqtSlot()
    def _run_selected_plugin(self):
        from workers.scan_worker import PluginWorker
        row = self._plugin_list_table.currentRow()
        if row < 0 or row >= len(self._plugins):
            self._plugin_status.setText("⚠ Select a plugin from the list first.")
            return
        if self._plugin_worker and self._plugin_worker.isRunning():
            return
        info = self._plugins[row]
        # Use Module 1 scan results as device list if available
        devices = []
        if self._m1_result:
            devices = self._m1_result.get("devices", [])
        self._plugin_status.setText(f"Running '{info.name}'…")
        self._plugin_result_text.clear()
        self._plugin_worker = PluginWorker(info, devices)
        self._plugin_worker.result.connect(self._on_plugin_result)
        self._plugin_worker.status.connect(self._plugin_status.setText)
        self._plugin_worker.error.connect(self._on_plugin_error)
        self._plugin_worker.start()

    @pyqtSlot(object)
    def _on_plugin_result(self, res):
        lines = [f"Plugin: {res.plugin_name}", f"Risk: {res.risk_level}"]
        if res.findings:
            lines.append(f"Findings ({len(res.findings)}):")
            for f in res.findings:
                lines.append(f"  • {f}")
        else:
            lines.append("No findings.")
        self._plugin_result_text.setPlainText("\n".join(lines))
        color = RED if res.risk_level in ("HIGH", "CRITICAL") else (AMBER if res.risk_level == "MEDIUM" else GREEN)
        self._plugin_status.setText(
            f"'{res.plugin_name}' complete — {res.risk_level} "
            f"({len(res.findings)} finding{'s' if len(res.findings) != 1 else ''})."
        )
        self._plugin_status.setStyleSheet(f"color:{color};font-size:11px;")

    @pyqtSlot(str)
    def _on_plugin_error(self, msg: str):
        self._plugin_result_text.setPlainText(f"ERROR:\n{msg}")
        self._plugin_status.setText("Plugin failed — see output above.")
        self._plugin_status.setStyleSheet(f"color:{RED};font-size:11px;")

    # ── Private Endpoint Checker tab ─────────────────────────────────────────

    def _build_recon_pe_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        title = QLabel("🔒  Private Endpoint Checker")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{ACCENT_LITE};")
        lay.addWidget(title)

        desc = QLabel(
            "Verify that named service endpoints resolve to private (RFC-1918) IPs, "
            "are TCP-reachable, and have valid TLS certificates.  "
            "Works for Azure Private Link, AWS PrivateLink, and any internal hostname:port."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(desc)

        # ── Input area ────────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid #2a2a4a; border-radius:10px;"
        )
        input_lay = QVBoxLayout(input_frame)
        input_lay.setContentsMargins(14, 10, 14, 10)
        input_lay.setSpacing(6)

        input_lbl = QLabel("Endpoints — one per line, format:  hostname:port  or  IP:port  (port optional, defaults to 443)")
        input_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        input_lay.addWidget(input_lbl)

        self._pe_input = QTextEdit()
        self._pe_input.setPlaceholderText(
            "myblob.privatelink.blob.core.windows.net:443\n"
            "my-rds.cluster-xxxx.us-east-1.rds.amazonaws.com:5432\n"
            "10.0.1.55:22"
        )
        self._pe_input.setFixedHeight(100)
        self._pe_input.setStyleSheet(
            f"background:#0d0d1e; color:{TEXT_PRIMARY}; border:1px solid #2a2a4a;"
            "border-radius:6px; padding:6px; font-size:12px; font-family:'Courier New';"
        )
        input_lay.addWidget(self._pe_input)

        btn_row = QHBoxLayout()
        self._btn_pe_run = QPushButton("▶  Run Checks")
        self._btn_pe_run.setObjectName("btnDiag")
        self._btn_pe_run.setFixedHeight(34)
        self._btn_pe_run.clicked.connect(self._run_pe_checks)
        self._btn_pe_clear = QPushButton("Clear")
        self._btn_pe_clear.setFixedHeight(34)
        self._btn_pe_clear.clicked.connect(lambda: (
            self._pe_table.setRowCount(0),
            self._pe_status.setText("")
        ))
        self._pe_status = QLabel("")
        self._pe_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        btn_row.addWidget(self._btn_pe_run)
        btn_row.addWidget(self._btn_pe_clear)
        btn_row.addWidget(self._pe_status, 1)
        input_lay.addLayout(btn_row)
        lay.addWidget(input_frame)

        # ── Results table ─────────────────────────────────────────────────────
        self._pe_table = _table([
            "Status", "Endpoint", "Cloud", "Resolved IP(s)",
            "Private?", "TCP", "TLS Days", "Findings"
        ])
        self._pe_table.setColumnWidth(0, 60)
        self._pe_table.setColumnWidth(1, 220)
        self._pe_table.setColumnWidth(2, 70)
        self._pe_table.setColumnWidth(3, 150)
        self._pe_table.setColumnWidth(4, 65)
        self._pe_table.setColumnWidth(5, 55)
        self._pe_table.setColumnWidth(6, 70)
        lay.addWidget(self._pe_table, 1)

        return w

    @pyqtSlot()
    def _run_pe_checks(self):
        from workers.scan_worker import PrivateEndpointWorker
        from modules.private_endpoint_checker import EndpointSpec

        raw = self._pe_input.toPlainText().strip()
        if not raw:
            self._pe_status.setText("⚠ Enter at least one endpoint above.")
            return
        if self._pe_worker and self._pe_worker.isRunning():
            return

        specs: list = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                # Could be host:port OR IPv6 — detect by counting colons
                parts = line.rsplit(":", 1)
                try:
                    port = int(parts[1])
                    host = parts[0].strip("[]")
                except ValueError:
                    host = line
                    port = 443
            else:
                host = line
                port = 443
            specs.append(EndpointSpec(host=host, port=port))

        if not specs:
            self._pe_status.setText("⚠ No valid endpoints parsed.")
            return

        self._pe_table.setRowCount(0)
        self._pe_status.setText(f"Checking {len(specs)} endpoint(s)…")
        self._btn_pe_run.setEnabled(False)

        self._pe_worker = PrivateEndpointWorker(specs)
        self._pe_worker.result.connect(self._on_pe_result)
        self._pe_worker.status.connect(self._pe_status.setText)
        self._pe_worker.error.connect(lambda e: self._pe_status.setText(f"⚠ {e}"))
        self._pe_worker.finished_all.connect(self._on_pe_done)
        self._pe_worker.start()

    @pyqtSlot(object)
    def _on_pe_result(self, res):
        from PyQt6.QtGui import QColor
        row = self._pe_table.rowCount()
        self._pe_table.insertRow(row)

        status_color = GREEN if res.status == "PASS" else (AMBER if res.status == "WARN" else RED)
        ips_str  = ", ".join(res.resolved_ips[:3]) + ("…" if len(res.resolved_ips) > 3 else "")
        priv_str = "✔ Yes" if res.is_private else ("⚠ LEAK" if res.dns_leak else "—")
        tcp_str  = "✔" if res.tcp_open else "✘"
        tls_str  = str(res.cert.days_left) if (res.cert and not res.cert.error and res.cert.days_left >= 0) else "—"
        findings = " | ".join(res.findings) if res.findings else "All checks passed"
        if res.dns_server:
            findings += f"  [resolver: {res.dns_server}]"

        vals = [res.status, res.spec.label, res.cloud or "—", ips_str,
                priv_str, tcp_str, tls_str, findings]
        for col, val in enumerate(vals):
            item = QTableWidgetItem(str(val))
            c = status_color if col == 0 else (
                (GREEN if "✔" in str(val) else (RED if "✘" in str(val) or "LEAK" in str(val) else TEXT_PRIMARY))
            )
            item.setForeground(QColor(c))
            self._pe_table.setItem(row, col, item)

    @pyqtSlot()
    def _on_pe_done(self):
        total = self._pe_table.rowCount()
        fails = sum(
            1 for r in range(total)
            if (self._pe_table.item(r, 0) or QTableWidgetItem()).text() == "FAIL"
        )
        self._pe_status.setText(
            f"✓ Done — {total} endpoint(s), {fails} FAIL, {total - fails} OK."
        )
        self._btn_pe_run.setEnabled(True)
