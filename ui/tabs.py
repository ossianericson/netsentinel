"""
tabs.py — TabBuilderMixin: all tab content builders for the Dashboard.

Extracted from ui/dashboard.py (Sprint 6, S13-1).
Methods here build the QWidget content for each scan-result tab.
They are called once during Dashboard._build_ui() via _build_tabs().
"""
from __future__ import annotations

import webbrowser
from typing import Optional

from PyQt6.QtCore import Qt, QSettings, QSize, QTimer, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.live_graph import LiveGraphWidget
from ui.npcap_banner import NpcapMissingBanner
from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, AMBER_BG, BG_CARD, BG_DARK, BG_HOVER, BORDER,
    CARD_RADIUS, CHART_PURPLE, GREEN, NAV_DIVIDER,
    RED, RISK_COLORS,
    SIDEBAR_BG, SIDEBAR_HOVER, SIDEBAR_ITEM_FG, SIDEBAR_SECTION_BG, SIDEBAR_SECTION_FG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, WHITE,
)
from ui.nav.rail import _RailButton, _FlyoutPanel, _CanvasClickFilter, _make_nav_icon

# ─── Module-level tab helpers (also imported by dashboard.py) ─────────────────

from PyQt6.QtWidgets import QScrollArea, QTableWidget


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
    t.horizontalHeader().setDefaultSectionSize(120)
    t.setShowGrid(True)
    t.verticalHeader().setDefaultSectionSize(24)  # compact row height
    return t


def _add_row(table: QTableWidget, values: list, level: str = "CLEAN"):
    from PyQt6.QtGui import QColor
    from ui.styles import RISK_COLORS as _RC, TEXT_SECONDARY as _TS
    row = table.rowCount()
    table.insertRow(row)
    color = _RC.get(level.upper(), _TS)
    for col, val in enumerate(values):
        item = QTableWidgetItem(str(val))
        if level in ("HIGH", "STORM", "MEDIUM", "WARNING"):
            item.setForeground(QColor(color))
        table.setItem(row, col, item)


def _add_skeleton_rows(table: QTableWidget, count: int = 8) -> None:
    """Insert placeholder rows while a scan worker is running."""
    from PyQt6.QtGui import QColor
    from ui.styles import TEXT_MUTED as _TM
    col_count = table.columnCount()
    for _ in range(count):
        row = table.rowCount()
        table.insertRow(row)
        for col in range(col_count):
            item = QTableWidgetItem("—")
            item.setForeground(QColor(_TM))
            table.setItem(row, col, item)


def _empty_state_widget(icon: str, headline: str, body: str,
                        cta_label: "str | None", cta_action: "callable | None") -> "QWidget":
    """Reusable empty-state panel: icon + headline + body text + optional CTA button."""
    from PyQt6.QtWidgets import QWidget as _W, QVBoxLayout as _VL, QHBoxLayout as _HL, QLabel as _L, QPushButton as _B
    from PyQt6.QtCore import Qt as _Qt
    from ui.styles import ACCENT as _AC, BG_HOVER as _BH, TEXT_PRIMARY as _TP, TEXT_SECONDARY as _TS
    w = _W()
    vl = _VL(w)
    vl.setContentsMargins(32, 32, 32, 32)
    vl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    ic = _L(icon)
    ic.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    ic.setStyleSheet(f"font-size:30px; background:transparent; border:none;")
    hd = _L(headline)
    hd.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    hd.setStyleSheet(f"font-size:13px; font-weight:bold; color:{_TP}; background:transparent; border:none;")
    bd = _L(body)
    bd.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    bd.setWordWrap(True)
    bd.setStyleSheet(f"font-size:11px; color:{_TS}; background:transparent; border:none;")
    vl.addWidget(ic)
    vl.addWidget(hd)
    vl.addSpacing(4)
    vl.addWidget(bd)
    if cta_label and cta_action:
        vl.addSpacing(10)
        btn = _B(cta_label)
        btn.setFixedHeight(28)
        btn.setCursor(_Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background:{_AC}; color:#fff; border:none;"
            f" border-radius:4px; font-size:11px; font-weight:600; padding:0 16px; }}"
            f"QPushButton:hover {{ background:#1a6fc4; }}"
            f"QPushButton:pressed {{ color:{_TP}; }}"
        )
        btn.clicked.connect(cta_action)
        hl = _HL()
        hl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(btn)
        vl.addLayout(hl)
    return w


def _error_state_widget(message: str, retry_fn: "callable") -> "QWidget":
    """Reusable error-state panel: warning icon + message + Retry button."""
    from PyQt6.QtWidgets import QWidget as _W, QVBoxLayout as _VL, QHBoxLayout as _HL, QLabel as _L, QPushButton as _B
    from PyQt6.QtCore import Qt as _Qt
    from ui.styles import AMBER as _AM, BG_HOVER as _BH, TEXT_PRIMARY as _TP, TEXT_SECONDARY as _TS
    w = _W()
    vl = _VL(w)
    vl.setContentsMargins(32, 32, 32, 32)
    vl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    ic = _L("⚠")
    ic.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    ic.setStyleSheet(f"font-size:28px; color:{_AM}; background:transparent; border:none;")
    hd = _L(message)
    hd.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    hd.setWordWrap(True)
    hd.setStyleSheet(f"font-size:12px; color:{_TP}; background:transparent; border:none;")
    vl.addWidget(ic)
    vl.addSpacing(6)
    vl.addWidget(hd)
    if retry_fn:
        vl.addSpacing(10)
        btn = _B("Retry")
        btn.setFixedHeight(28)
        btn.setCursor(_Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{_AM}; border:1px solid {_AM};"
            f" border-radius:4px; font-size:11px; padding:0 16px; }}"
            f"QPushButton:hover {{ background:{_AM}22; }}"
            f"QPushButton:pressed {{ background:{_BH}; color:{_AM}; }}"
        )
        btn.clicked.connect(retry_fn)
        hl = _HL()
        hl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(btn)
        vl.addLayout(hl)
    return w


def _make_card(title: str) -> tuple:
    """
    Build a standard enterprise card frame.
    Returns (card_QFrame, body_QVBoxLayout) — add content widgets to body_layout.
    Card: white BG, 0px border-radius, navy header bar (32px) with uppercase title.
    """
    from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
    from ui.styles import TEXT_PRIMARY as _TP
    card = QFrame()
    card.setObjectName("card")
    card_lay = QVBoxLayout(card)
    card_lay.setContentsMargins(0, 0, 0, 0)
    card_lay.setSpacing(0)

    hdr = QFrame()
    hdr.setObjectName("cardHeader")
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 0, 10, 0)
    hdr_lay.setSpacing(0)
    t = QLabel(title.upper())
    t.setStyleSheet(
        f"color:{_TP}; font-weight:bold; font-size:11px;"
        "letter-spacing:0.5px; background:transparent; border:none;"
    )
    hdr_lay.addWidget(t)
    hdr_lay.addStretch()
    card_lay.addWidget(hdr)

    body_lay = QVBoxLayout()
    body_lay.setContentsMargins(0, 0, 0, 0)
    body_lay.setSpacing(0)
    card_lay.addLayout(body_lay, 1)

    return card, body_lay


def _page_header(title: str, subtitle: str = "") -> QFrame:
    """
    Returns a QFrame header container with 16/20/12px breathing room and a
    1px bottom divider.  title 18px bold TEXT_PRIMARY, subtitle 11px TEXT_SECONDARY.
    """
    from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
    from ui.styles import BORDER as _BR, TEXT_PRIMARY as _TP, TEXT_SECONDARY as _TS
    container = QFrame()
    container.setObjectName("pageHeader")
    container.setStyleSheet(
        f"QFrame#pageHeader {{ background: transparent; border: none;"
        f" border-bottom: 1px solid {_BR}; }}"
    )
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(20, 16, 20, 12)
    vbox.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(
        f"color:{_TP}; font-size:18px; font-weight:bold;"
        "padding:0; background:transparent; border:none;"
    )
    vbox.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setStyleSheet(
            f"color:{_TS}; font-size:11px;"
            "padding:0; background:transparent; border:none;"
        )
        vbox.addWidget(s)
    return container


class TabBuilderMixin:
    """Mixin providing all tab/page content builders for Dashboard.

    Extracted from ui/dashboard.py (Sprint 6, S13-1).
    Methods call helpers (_make_card, _table, _page_header, etc.) that are
    defined as module-level functions in dashboard.py and are in scope because
    Dashboard inherits from this mixin alongside QMainWindow.
    """

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

        from ui.pages.history_page import HistoryPage
        self._history_page = HistoryPage(store=self._store)
        self.global_time_range_changed.connect(self._history_page.set_global_hours)

        from ui.pages.inventory_page import InventoryPage
        self._inventory_page = InventoryPage(store=self._store)
        self._inventory_page.device_selected.connect(
            self._on_inventory_device_selected,
            Qt.ConnectionType.QueuedConnection,
        )

        from ui.pages.cert_page import CertPage
        self._cert_page = CertPage(store=self._store)
        self.global_time_range_changed.connect(self._cert_page.set_global_hours)

        from ui.pages.uptime_page import UptimePage
        self._uptime_page = UptimePage(store=self._store)

        from ui.pages.service_page import ServicePage
        self._service_page = ServicePage(store=self._store)
        self.global_time_range_changed.connect(self._service_page.set_global_hours)

        from ui.pages.reports_page import ReportsPage
        self._reports_page = ReportsPage(store=self._store)

        from ui.pages.timeline_page import TimelinePage
        self._timeline_page = TimelinePage(store=self._store)
        self._timeline_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.notifications_page import NotificationsPage
        self._notifications_page = NotificationsPage(router=None, parent=None)
        self._notifications_page.navigate_to.connect(self._nav_rail_go_to)
        self._notifications_page.view_in_log_hub.connect(self._on_view_alert_in_log_hub)
        self._notifications_page.automation_rule_requested.connect(self._on_automation_rule_requested)
        self._notifications_page.select_inventory_device.connect(self._inventory_page.select_device)
        self._notifications_page.alert_acknowledged.connect(self._push_monitor_pills)
        self._notifications_page.set_store(self._store)
        self.global_time_range_changed.connect(self._notifications_page.set_global_hours)

        from ui.pages.baseline_page import BaselinePage
        self._baseline_page = BaselinePage(store=self._store, parent=None)
        self._baseline_page.drift_detected.connect(self._on_config_drift_detected)

        from ui.pages.trend_page import TrendPage
        self._trend_page = TrendPage(store=self._store, parent=None)
        self._trend_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.maintenance_page import MaintenancePage
        self._maintenance_page = MaintenancePage(parent=None)

        from ui.pages.snmp_trap_page import SnmpTrapPage
        self._snmp_trap_page = SnmpTrapPage(store=self._store)
        self._snmp_trap_page.navigate_to_settings.connect(
            lambda: self._nav_go_to("Settings")
        )

        from ui.pages.syslog_page import SyslogPage
        self._syslog_page = SyslogPage(parent=None)

        from ui.pages.log_hub_page import LogHubPage
        self._log_hub_page = LogHubPage(store=self._store, parent=None)
        self._log_hub_page.animate_requested.connect(self._on_animate_log_entry)
        self._log_hub_page.live_challenge_detected.connect(self._on_live_challenge)
        self._log_hub_page.logging_active_changed.connect(self._update_monitor_badge)
        self._log_hub_page.navigate_to.connect(self._nav_rail_go_to)
        self._last_modem_log_ts: float = 0.0
        self._last_mesh_log_ts:  float = 0.0

        from ui.pages.overview_page import OverviewPage
        self._overview_page = OverviewPage(store=self._store, parent=None)
        # Wire trend results to overview tile (OVERVIEW-4; trend_page created earlier)
        self._trend_page.report_ready.connect(self._overview_page.on_trend_result)

        from ui.pages.diagnosis_page import DiagnosisPage
        self._diagnosis_page = DiagnosisPage(store=self._store, parent=None)

        from ui.pages.settings_page import SettingsPage
        self._settings_page = SettingsPage(parent=None)
        self._settings_page.reload_oui_requested.connect(self._reload_oui_db)
        self._settings_page.reset_dismissed_requested.connect(self._reset_dismissed_notices)
        self._settings_page.export_all_requested.connect(self._on_export_all)
        self._settings_page.run_setup_requested.connect(self._on_run_first_time_setup)
        self._settings_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.speed_test_page import SpeedTestPage
        self._speed_test_page = SpeedTestPage(store=self._store, parent=None)
        self._speed_test_page.modem_pause_requested.connect(self._on_modem_disconnect)
        self.global_time_range_changed.connect(self._speed_test_page.set_global_hours)

        from ui.pages.home_automation_page import HomeAutomationPage
        self._ha_page = HomeAutomationPage(store=self._store, parent=None)
        self._ha_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.connections_page import ConnectionsPage
        self._connections_page = ConnectionsPage(parent=None)

        from ui.pages.live_bandwidth_page import LiveBandwidthPage
        self._live_bandwidth_page = LiveBandwidthPage(parent=None)

        from ui.pages.dhcp_lease_page import DhcpLeasePage
        self._dhcp_lease_page = DhcpLeasePage(parent=None)
        self._dhcp_lease_page.navigate_to.connect(self._nav_rail_go_to)
        self._dhcp_lease_page.select_device.connect(self._inventory_page.select_device)

        from ui.pages.dns_zone_page import DnsZonePage
        self._dns_zone_page = DnsZonePage(parent=None)

        from ui.pages.threat_intel_page import ThreatIntelPage
        self._threat_intel_page = ThreatIntelPage(parent=None)
        self._threat_intel_page.show_on_map.connect(self._show_ip_on_geo_map)

        from ui.pages.security_overview_page import SecurityOverviewPage
        self._security_overview_page = SecurityOverviewPage(parent=None)
        self._security_overview_page.navigate_to.connect(self._nav_rail_go_to)
        self._security_overview_page.scan_requested.connect(self._start_full_scan)
        self._security_overview_page.security_scan_requested.connect(self._run_security_scans)

        from ui.pages.cve_page import CvePage
        self._cve_page = CvePage(self._store, parent=None)
        self._cve_page.navigate_to_inventory.connect(
            lambda ip: (self._nav_rail_go_to("Inventory Changes"), self._inventory_page.select_device(ip))
        )

        # ── DEVICE-1: device quick-profile popover ────────────────────────────
        from ui.widgets.device_popover import DevicePopover
        self._device_popover = DevicePopover(parent=self)
        self._device_popover.set_store(self._store)
        self._device_popover.navigate_to_inventory.connect(self._on_popover_open_inventory)
        self._device_popover.navigate_to_threat_intel.connect(self._on_popover_open_threat_intel)

        # Inject popover into pages that need it
        for _p in (self._connections_page, self._threat_intel_page,
                   self._cve_page, self._log_hub_page):
            if hasattr(_p, "set_popover"):
                _p.set_popover(self._device_popover)

        from ui.pages.automation_page import AutomationPage
        self._automation_page = AutomationPage(parent=None)

        from ui.pages.network_doc_page import NetworkDocPage
        self._network_doc_page = NetworkDocPage(parent=None)

        from ui.pages.mqtt_page import MqttPage
        self._mqtt_page = MqttPage(parent=None)

        from ui.pages.ip_calculator_page import IpCalculatorPage
        self._ip_calc_page = IpCalculatorPage(parent=None)

        from ui.pages.wifi_heatmap_page import WifiHeatmapPage
        self._wifi_heatmap_page = WifiHeatmapPage(parent=None)

        from ui.pages.geo_map_page import GeoMapPage
        self._geo_map_page = GeoMapPage(store=self._store, parent=None)
        self._geo_map_page.navigate_requested.connect(self._nav_rail_go_to)

        from ui.pages.trigger_builder_page import TriggerBuilderPage
        self._trigger_page = TriggerBuilderPage(store=self._store, parent=None)

        from ui.pages.lab_mode_page import LabModePage
        self._lab_mode_page = LabModePage(store=self._store, parent=None)

        from ui.pages.protocol_viz_page import ProtocolVizPage
        self._protocol_viz_page = ProtocolVizPage(parent=None)
        self._protocol_viz_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.discover_page import FeatureGuidePage
        self._discover_page = FeatureGuidePage(parent=None)
        self._discover_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.hardware_integration_page import HardwareIntegrationPage
        self._hardware_integration_page = HardwareIntegrationPage(parent=None)
        self._hardware_integration_page.plugin_result.connect(self._on_hardware_plugin_result)
        self._hardware_integration_page.plugin_page_added.connect(self._on_plugin_page_added)
        self._hardware_integration_page.plugin_page_removed.connect(self._on_plugin_page_removed)
        self._hardware_integration_page.plugin_renamed.connect(self._on_plugin_page_renamed)
        self._hardware_integration_page.navigate_to.connect(self._nav_rail_go_to)
        self._hardware_integration_page.geo_map_ip.connect(self._show_ip_on_geo_map)
        self._hardware_integration_page.port_scan_ip.connect(
            lambda ip: (self._syn_host.setText(ip), self._nav_rail_go_to("Port Scan (TCP)"))
        )
        self._hardware_integration_page.check_abuse_ip.connect(
            lambda ip: (self._threat_intel_page.check_ip(ip), self._nav_rail_go_to("Threat Intelligence"))
        )

        # Pre-populate enrichment from cached QSettings so the first scan has
        # hostname / band / node data without waiting for the first poll cycle.
        # Key by instance_id (stable) not path (may change between launches).
        from ui.pages.hardware_integration_page import (
            _load_instances as _hw_instances,
            _load_last_result as _hw_last,
        )
        from modules.deco_client import _norm_mac as _hw_nm
        for _hw_inst in _hw_instances():
            # Try by instance_id (new format), fall back to path (old format)
            _hw_cached = _hw_last(_hw_inst["id"]) or _hw_last(_hw_inst["path"])
            if _hw_cached and _hw_cached.get("info", {}).get("type") != "modem":
                _hw_clients = _hw_cached.get("clients", [])
                self._plugin_enrichments[_hw_inst["id"]] = {
                    _hw_nm(c.get("mac", "")): c
                    for c in _hw_clients
                    if c.get("mac")
                }
                # Also pre-populate _plugin_nodes so the topology renders as
                # mesh (not flat) on the first scan before the first poll cycle.
                _hw_nodes = _hw_cached.get("status", {}).get("extra", {}).get("nodes", [])
                _hw_type  = _hw_cached.get("info", {}).get("type", "other")
                _hw_name  = (_hw_cached.get("info", {}).get("name", "")
                             or _hw_inst.get("name", "")
                             or _hw_inst.get("path", "plugin"))
                if not _hw_nodes and _hw_clients and _hw_type in ("router", "mesh", "ap"):
                    _hw_nodes = [{"name": _hw_name, "role": "primary",
                                  "ip": _hw_cached.get("info", {}).get("ip", ""), "mac": ""}]
                self._plugin_nodes[_hw_inst["id"]] = _hw_nodes

        # Create one PluginDevicePage per registered instance.
        # Pages are registered in the nav by _build_pro_nav() further below.
        from ui.pages.plugin_device_page import PluginDevicePage
        from ui.pages.hardware_integration_page import _validate_script as _hw_validate
        from pathlib import Path as _HwPath
        self._plugin_pages: dict[str, PluginDevicePage] = {}
        for _hw_inst in _hw_instances():
            _hw_p = _hw_inst["path"]
            if _hw_p in self._plugin_pages:
                continue  # deduplicate — same path, multiple instances
            _ok, _msg, _meta = _hw_validate(_hw_p)
            _hw_type   = _meta.get("type", "other") if _ok else "other"
            # Prefer instance name (may have been customised) over meta name
            _hw_label  = _hw_inst.get("name") or (_meta.get("name") if _ok else None) or _HwPath(_hw_p).stem
            _hw_ip     = _hw_inst.get("ip") or (_meta.get("ip", "") if _ok else "")
            _cred_lbl  = _meta.get("credential_label", "Password") if _ok else "Password"
            _pg = PluginDevicePage(_hw_p, _hw_label, _hw_type, hw_ip=_hw_ip,
                                   credential_label=_cred_lbl, parent=None)
            _pg.test_requested.connect(self._on_plugin_page_test)
            if not _ok or not _HwPath(_hw_p).is_file():
                _pg.mark_unavailable()
            else:
                # Seed with cached result so page shows data on first open
                _hw_cached2 = _hw_last(_hw_inst["id"]) or _hw_last(_hw_p)
                if _hw_cached2:
                    _pg.update(_hw_cached2)
                    if _hw_type == "modem":
                        import time as _t2
                        from modules.network_infrastructure import hw_state as _hws
                        _s2 = _hw_cached2.get("status", {})
                        _x2 = _s2.get("extra", {})
                        _hws.update_modem({
                            "ts":               int(_t2.time()),
                            "wan_ip":           _s2.get("wan_ip"),
                            "wan_status":       _s2.get("wan_status"),
                            "firmware_version": _x2.get("firmware"),
                            "network_type":     _x2.get("network_type"),
                            "signal_bars":      _x2.get("signal_bars"),
                            "mcc":              _x2.get("mcc"),
                            "mnc":              _x2.get("mnc"),
                            "cell_id":          _x2.get("cell_id"),
                            "enb_id":           _x2.get("enb_id"),
                            "nr5g_rsrp_dbm":    _x2.get("nr5g_rsrp_dbm"),
                            "nr5g_sinr_db":     _x2.get("nr5g_sinr_db"),
                            "nr5g_rsrq_db":     _x2.get("nr5g_rsrq_db"),
                            "nr5g_band":        _x2.get("nr5g_band"),
                            "nr5g_pci":         _x2.get("nr5g_pci"),
                            "nr5g_arfcn":       _x2.get("nr5g_arfcn"),
                            "lte_rsrp_dbm":     _x2.get("lte_rsrp_dbm"),
                            "lte_snr_db":       _x2.get("lte_snr_db"),
                            "lte_rsrq_db":      _x2.get("lte_rsrq_db"),
                            "lte_band":         _x2.get("lte_band"),
                            "lte_pci":          _x2.get("lte_pci"),
                            "lte_earfcn":       _x2.get("lte_earfcn"),
                            "endc_info":        _x2.get("endc_info"),
                        }, source=_hw_p, hw_name=_hw_label)
            self._plugin_pages[_hw_p] = _pg  # keyed by path for signal compat

        # Populate Log Hub DB bar and set initial Monitor badge once the event loop starts.
        from PyQt6.QtCore import QTimer as _QT
        _QT.singleShot(0, lambda: self._log_hub_page.update_plugin_sources(
            [pg._label for pg in self._plugin_pages.values()]
        ))
        _QT.singleShot(0, self._update_monitor_badge)
        _QT.singleShot(0, self._push_monitor_pills)

        from ui.pages.rest_api_page import RestApiPage
        self._rest_api_page = RestApiPage(store=self._store, parent=None)

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

        from ui.pages.wifi_monitor_page import WiFiMonitorPage
        self._wifi_monitor_page = WiFiMonitorPage(parent=None)

        from ui.pages.monitor_overview_page import MonitorOverviewPage
        self._monitor_overview_page = MonitorOverviewPage(parent=None)
        self._monitor_overview_page.navigate_to.connect(self._nav_rail_go_to)
        if self._store is not None:
            self._monitor_overview_page.set_store(self._store)

        self._help_tab_widget            = self._build_help_tab()

        # ── Store tab refs for mode nav builders ──────────────────────────────
        self._m1_tab = m1
        self._m2_tab = m2
        self._m3_tab = m3
        self._m4_tab = m4
        self._m5_tab = m5
        self._net_tab = net
        self._dia_tab = dia
        self._log_tab = log

        # Unified logging container — "Log Sources" (config) first, "Activity Log" (viewer) second.
        # Created here before the nav runs so each widget has exactly one parent (the container)
        # and is never registered separately in the stack.
        from PyQt6.QtWidgets import QTabWidget as _LogTW
        self._logging_container = _LogTW()
        self._logging_container.setStyleSheet(
            f"QTabWidget::pane {{ border:1px solid {BORDER}; background:{BG_DARK}; }}"
            f"QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f"  padding:6px 18px; border:1px solid {BORDER}; border-bottom:none; margin-right:2px; }}"
            f"QTabBar::tab:selected {{ background:{ACCENT}; color:{BG_DARK}; font-weight:bold; }}"
            f"QTabBar::tab:hover {{ background:{BG_HOVER}; }}"
        )
        self._logging_container.addTab(self._log_tab,       "Log Sources")
        self._logging_container.addTab(self._log_hub_page,  "Activity Log")

        # HomePage (pre-instantiated here; registered in stack below)
        from ui.pages.home_page import HomePage
        self._home_page = HomePage(store=self._store, parent=None)
        # Wire HomePage hero buttons and incoming speed results (guard prevents
        # double-connection if _build_tabs() is ever called more than once)
        self._pending_live_scenario = None
        if not self._home_page._signals_connected:
            self._home_page._btn_scan.clicked.connect(self._start_full_scan)
            self._home_page._btn_rescan_compact.clicked.connect(self._start_full_scan)
            self._home_page._btn_isp.clicked.connect(self._open_isp_from_home)
            self._home_page._btn_diagnose.clicked.connect(self._open_diagnosis)
            self._speed_test_page.test_completed.connect(self._home_page.on_speed_result)
            self._speed_test_page.test_completed.connect(self._on_speed_test_modem_forward)
            self._home_page.navigate_to.connect(self._on_overview_navigate)
            self._home_page.start_monitoring_requested.connect(self._toggle_logger)
            self._home_page.investigate_live_requested.connect(self._on_investigate_live)
            self._home_page.alert_view_requested.connect(self._on_alert_view_requested)
            self._home_page.rescan_requested.connect(self._start_full_scan)
            self._home_page.add_plugin_requested.connect(
                lambda p: self._hardware_integration_page._import_bundled(p)
            )
            self._home_page._signals_connected = True
        self._overview_page.navigate_to.connect(self._on_overview_navigate)
        self._overview_page.scan_requested.connect(self._start_full_scan)
        self._overview_page.report_requested.connect(self._run_full_report)
        self._overview_page.export_requested.connect(self._export_report)
        self._overview_page.security_scan_requested.connect(self._run_security_scans)
        self._overview_page.modem_tile_clicked.connect(self._on_modem_tile_clicked)
        self._active_modem_plugin_label: str = ""
        self._diagnosis_page.navigate_to.connect(self._on_overview_navigate)
        self._diagnosis_page.diagnosis_saved.connect(self._home_page.refresh_diag_summary)

        # Populate home page suggestions on first build (deferred so _home_page exists)
        from PyQt6.QtCore import QTimer as _QTr
        _QTr.singleShot(0, self._refresh_home_suggestions)

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
        self._nav.setObjectName("sideNav")
        self._nav_delegate = self._NavAdminDelegate(self._nav_admin_rows, RED, self._nav)
        self._nav.setItemDelegate(self._nav_delegate)
        # Right-click → pin/unpin to Favourites
        self._nav.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._nav.customContextMenuRequested.connect(self._nav_context_menu)
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._stack.setMinimumSize(0, 0)
        # Pre-register HomePage so _nav_ref() can find it via indexOf()
        self._stack.addWidget(self._home_page)
        self._stack.addWidget(self._diagnosis_page)
        self._stack.addWidget(self._lab_mode_page)
        self._stack.addWidget(self._protocol_viz_page)
        self._stack.addWidget(self._discover_page)
        self._stack.addWidget(self._hardware_integration_page)
        self._stack.addWidget(self._rest_api_page)
        self._nav_row_to_page:   dict = {}
        self._nav_separators:    set  = set()
        # Extended nav data model
        self._nav_item_icons:    dict = {}
        self._nav_item_labels:   dict = {}
        self._nav_header_rows:   set  = set()
        self._nav_section_groups: dict = {}
        self._nav_current_section:  int  = -1
        self._nav_current_subgroup: int  = -1
        self._nav_collapsed:     bool = False

        # ── PINNED — top 7 most-used pages; always visible, no subgroups ──────────
        self._nav_add_section("Pinned", icon="📌")
        self._nav_add_page("⬡", "Overview",             self._overview_page)
        self._nav_add_page("◎", "DNS & Outages",        m5)
        self._nav_add_page("▲", "Live Bandwidth",       self._live_bandwidth_page)
        self._nav_add_page("⚡", "Speed Test",           self._speed_test_page)
        self._nav_add_page("⊞", "Devices on Network",   m1)
        self._nav_add_page("⏷", "Availability History", self._history_page)
        self._nav_add_page("⇄", "Active Connections",   self._connections_page)

        # ── STANDARD — full organised structure ───────────────────────────────────
        self._nav_add_section("Standard", icon="◼", collapsed_by_default=False)

        # Discover — expanded by default so the user immediately sees what's there
        self._nav_add_subgroup("Discover", icon="🖥", collapsed_by_default=False)
        self._nav_add_page ("〇", "WiFi Networks",        m4)
        self._nav_add_page ("ℹ",  "Network Info",         net)
        self._nav_add_page ("≡", "DHCP Lease Inventory", self._dhcp_lease_page)
        self._nav_add_page ("⊹", "DNS Zone Map",         self._dns_zone_page)
        self._nav_current_subgroup = -1

        # Threat Detection — collapsed; expand when you need security analysis
        self._nav_add_subgroup("Threat Detection", icon="🛡")
        self._nav_add_page("⚠", "Broadcast Storm",      m3)
        self._nav_add_page("⇌", "Rogue Bridge (STP)",   m2)
        self._nav_add_page("◈", "IoT Behaviour",        self._iot_baseline_tab_widget)
        self._nav_current_subgroup = -1

        # Health & History — collapsed; historical data on demand
        self._nav_add_subgroup("Health & History", icon="◉")
        self._nav_add_page ("∆", "Inventory Changes",    self._inventory_page)
        self._nav_add_page ("✓", "Uptime & SLA",         self._uptime_page)
        self._nav_add_page ("◉", "Service Heartbeat",    self._service_page)
        self._nav_add_page ("▦", "Network Grade",        self._benchmark_tab_widget)
        self._nav_current_subgroup = -1

        # Diagnostics — collapsed; deeper investigation tools
        self._nav_add_subgroup("Diagnostics", icon="💊")
        self._nav_add_page("≣", "Network Logger",        self._logging_container)
        self._nav_add_page("↗", "Trend Forecasts",      self._trend_page)
        self._nav_add_page("⬡", "IPv6 Devices",         self._ipv6_tab_widget)
        self._nav_current_subgroup = -1

        # Reports & Alerts — collapsed; admin/config
        self._nav_add_subgroup("Reports & Alerts", icon="🔔")
        self._nav_add_page("◟", "Notifications",        self._notifications_page)
        self._nav_add_page("⊟", "Auto Reports",         self._reports_page)
        self._nav_add_page("⊡", "Network Timeline",     self._timeline_page)
        self._nav_add_page("⊛", "Config Snapshots",     self._baseline_page)
        self._nav_add_page("⚙", "Maintenance Windows",  self._maintenance_page)
        self._nav_add_page("△", "Custom Triggers",      self._trigger_page)
        self._nav_current_subgroup = -1

        # Tools — collapsed; utilities
        self._nav_add_subgroup("Tools", icon="⚡")
        self._nav_add_page ("⌂", "Home Automation",     self._ha_page)
        _tools_heatmap_row = self._nav_add_page("◈", "WiFi Heatmap",       self._wifi_heatmap_page)
        _tools_geomap_row  = self._nav_add_page("⊕", "Geolocation Map",    self._geo_map_page)
        self._nav_current_subgroup = -1

        # ── ADVANCED (collapsed by default) ────────────────────────────────────
        self._nav_adv_sep = self._nav.count()
        self._nav_add_section("Advanced", icon="⚙", collapsed_by_default=True)

        self._nav_add_subgroup("Deep Analysis", icon="🔬")
        _mtr_row  = self._nav_add_page("⦳", "Hop-by-Hop Trace",  self._mtr_tab_widget)
        _arp_row  = self._nav_add_page("⊙", "ARP Spoof Watch",    self._arp_tab_widget)
        _snmp_row = self._nav_add_page("⊳", "SNMP Device Info",   self._snmp_tab_widget)
        _snmp_trap_row = self._nav_add_page("⊲", "SNMP Trap Receiver", self._snmp_trap_page)
        _syslog_row    = self._nav_add_page("≡", "Syslog Viewer",       self._syslog_page)
        self._nav_current_subgroup = -1

        _adv_tools_row = self._nav_add_page("⚙", "Tools & Wake-on-LAN", self._adv_tab_widget)
        _adv_map_row   = self._nav_add_page("⬡", "Network Map",          self._topology_tab_widget)
        _adv_bw_row    = self._nav_add_page("▲", "Bandwidth Usage",       self._bw_tab_widget)
        _adv_sched_row = self._nav_add_page("⏱", "Scheduled Scans",       self._sched_tab_widget)
        _adv_auto_row  = self._nav_add_page("→", "Automation Hooks",      self._automation_page)
        _adv_doc_row   = self._nav_add_page("▣", "Network Doc",            self._network_doc_page)
        _adv_mqtt_row  = self._nav_add_page("◉", "MQTT / Home Assistant",  self._mqtt_page)

        # compat refs
        self._nav_adv_rows      = [_mtr_row, _adv_tools_row, _adv_map_row,
                                    _arp_row, _adv_bw_row, _adv_sched_row,
                                    _snmp_row, _snmp_trap_row, _syslog_row,
                                    _adv_auto_row, _adv_doc_row, _adv_mqtt_row,
                                    _tools_heatmap_row]
        self._adv_tab_index_adv = _adv_tools_row
        self._adv_tab_index_mtr = _mtr_row
        self._nav_separators.add(self._nav_adv_sep)

        # ── SECURITY AUDIT (collapsed by default) ──────────────────────────────
        self._nav_recon_sep = self._nav.count()
        self._nav_add_section("Security Audit", icon="🔐", collapsed_by_default=True)
        self._nav_recon_rows = [
            self._nav_add_page("⊙", "Security Overview",      self._security_overview_page),
            self._nav_add_page("🧠", "Threat Intelligence",    self._threat_intel_page),
            self._nav_add_page("✚", "TLS & exposure",         self._cert_page),
            self._nav_add_page("🔎", "Port Scan (TCP)",        self._recon_syn_tab_widget),
            self._nav_add_page("🔎", "Port Scan (UDP)",        self._recon_udp_tab_widget),
            self._nav_add_page("💻", "OS Detection",           self._recon_os_tab_widget),
            self._nav_add_page("⚠",  "Device Risk Score",     self._recon_risk_tab_widget),
            self._nav_add_page("🛡", "Known CVEs",             self._recon_cve_tab_widget),
            self._nav_add_page("📋", "CVE Tracker",              self._cve_page),
            self._nav_add_page("🌍", "Exposed to Internet",    self._recon_exposure_tab_widget),
            self._nav_add_page("🔑", "Login Test (SSH/SMB)",   self._recon_cred_tab_widget),
            self._nav_add_page("🔭", "Full Device Discovery",  self._recon_discovery_tab_widget),
            self._nav_add_page("🗂", "Windows Shares (SMB)",   self._recon_smb_tab_widget),
            self._nav_add_page("🔌", "Recon Plugins",          self._recon_plugin_tab_widget),
            self._nav_add_page("🔒", "Private Endpoint Check", self._recon_pe_tab_widget),
            self._nav_add_page("☁",  "Cloud Metadata Probe",  self._recon_cloud_tab_widget),
        ]
        self._nav_separators.add(self._nav_recon_sep)
        self._recon_tab_start_index = -1  # kept for compat

        # ── EDUCATION (collapsed by default) ───────────────────────────────────
        self._nav_edu_sep = self._nav.count()
        self._nav_add_section("Education", icon="◎", collapsed_by_default=True)
        self._nav_add_page("⬡", "Lab Mode",             self._lab_mode_page)
        self._nav_add_page("◈", "Protocol Visualizer",  self._protocol_viz_page)
        self._nav_add_page("◉", "Feature Guide",        self._discover_page)
        self._nav_add_page("?", "Help & Reference",     self._help_tab_widget)
        self._nav_separators.add(self._nav_edu_sep)

        # ── EXTEND (collapsed by default) ───────────────────────────────────
        self._nav_extend_sep = self._nav.count()
        self._nav_add_section("Extend", icon="⬡", collapsed_by_default=True)
        self._nav_add_page("⊕", "Hardware", self._hardware_integration_page)
        self._nav_separators.add(self._nav_extend_sep)

        # Apply initial collapse for ALL groups that start collapsed (both level-0
        # sections and level-1 sub-groups).  Process level-0 first so parent
        # hide state is established before children are evaluated.
        for _hrow, _grp in self._nav_section_groups.items():
            if _grp["collapsed"] and _grp["level"] == 0:
                self._nav_apply_section_visibility(_hrow, True)
        for _hrow, _grp in self._nav_section_groups.items():
            if _grp["collapsed"] and _grp["level"] == 1:
                self._nav_apply_section_visibility(_hrow, True)

        # ── Wire signals ──────────────────────────────────────────────────────
        self._nav.currentRowChanged.connect(self._on_nav_row_changed)
        self._nav.itemClicked.connect(self._on_nav_item_clicked)
        # Select the Overview row (first real page in the Pinned section)
        self._nav.setCurrentRow(1)

        # ── Build sidebar panels ───────────────────────────────────────────────
        # Panel 0 — flat QListWidget sidebar (Home mode)
        self._nav_flat_panel = QWidget()
        self._nav_flat_panel.setFixedWidth(220)
        self._nav_flat_panel.setStyleSheet(f"QWidget {{ background:{SIDEBAR_BG}; }}")
        _fp_lay = QVBoxLayout(self._nav_flat_panel)
        _fp_lay.setContentsMargins(0, 0, 0, 0)
        _fp_lay.setSpacing(0)

        self._mode_seg_btns: dict = {}   # kept for compat — buttons no longer rendered

        # Search / filter (flat panel only — hidden by default)
        self._nav_search = QLineEdit()
        self._nav_search.setObjectName("navSearch")
        self._nav_search.setPlaceholderText("  Filter…")
        self._nav_search.setToolTip("Filter sidebar pages  (Ctrl+F)")
        self._nav_search.setFixedHeight(28)
        self._nav_search.setStyleSheet(
            f"QLineEdit#navSearch {{"
            f" background:{SIDEBAR_HOVER}; color:{SIDEBAR_ITEM_FG};"
            f" border:none; border-bottom:1px solid {NAV_DIVIDER};"
            f" padding:0 8px; font-size:11px; }}"
            f"QLineEdit#navSearch:focus {{ color:{WHITE}; }}"
        )
        self._nav_search.textChanged.connect(self._on_nav_search_changed)
        self._nav_search.setVisible(False)

        # Collapse ◀ / ▶ toggle (flat panel footer)
        self._sidebar_toggle_btn = QPushButton("◀")
        self._sidebar_toggle_btn.setFixedHeight(24)
        self._sidebar_toggle_btn.setStyleSheet(
            f"QPushButton {{ background:{SIDEBAR_SECTION_BG}; color:{SIDEBAR_SECTION_FG};"
            f" border:none; border-top:1px solid {NAV_DIVIDER}; font-size:11px; }}"
            f"QPushButton:hover {{ color:{WHITE}; background:{SIDEBAR_HOVER}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)

        _fp_lay.addWidget(self._nav_search)
        _fp_lay.addWidget(self._nav, 1)
        _fp_lay.addWidget(self._sidebar_toggle_btn)

        # Panel 1 — activity rail + flyout (Standard/Pro mode)
        self._nav_rail_panel = QWidget()
        self._nav_rail_panel.setStyleSheet(f"QWidget {{ background:{SIDEBAR_BG}; }}")
        _rp_lay = QHBoxLayout(self._nav_rail_panel)
        _rp_lay.setContentsMargins(0, 0, 0, 0)
        _rp_lay.setSpacing(0)

        # 48px icon rail
        self._nav_rail = QWidget()
        self._nav_rail.setFixedWidth(56)
        self._nav_rail.setStyleSheet(
            f"background: {SIDEBAR_BG}; border-right: 1px solid {NAV_DIVIDER};"
        )
        self._nav_rail_lay = QVBoxLayout(self._nav_rail)
        self._nav_rail_lay.setContentsMargins(0, 0, 0, 0)
        self._nav_rail_lay.setSpacing(0)

        # Mode pill at top of rail (cycling dot)
        self._rail_mode_btn = QPushButton("●")
        self._rail_mode_btn.setFixedSize(48, 32)
        self._rail_mode_btn.setToolTip("Click to cycle: Standard → Pro → Home")
        self._rail_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rail_mode_btn.clicked.connect(self._cycle_mode)
        self._rail_mode_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {ACCENT}; font-size: 10px; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.07); }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._rail_mode_btn.setVisible(False)  # mode switcher removed

        # Persistent search button — always visible at top of rail, opens Ctrl+K palette
        _rail_search_btn = QPushButton()
        _rail_search_btn.setFixedSize(56, 36)
        _rail_search_btn.setToolTip("Search all pages  (Ctrl+K)")
        _rail_search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _rail_search_btn.setIcon(_make_nav_icon("search", 18, "#6B7A8D"))
        _rail_search_btn.setIconSize(QSize(18, 18))
        _rail_search_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; outline: none;"
            f" border-bottom: 1px solid {NAV_DIVIDER}; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.07); }}"
            f"QPushButton:focus, QPushButton:focus-visible {{"
            f" outline: none; border: none; border-bottom: 1px solid {NAV_DIVIDER}; }}"
        )
        _rail_search_btn.clicked.connect(self._open_command_palette)
        self._nav_rail_lay.addWidget(_rail_search_btn)
        self._nav_rail_lay.addStretch()

        # Settings button pinned at bottom of rail
        self._rail_settings_btn = _RailButton("settings", "Settings")
        self._rail_settings_btn.clicked.connect(self._open_settings_dialog)
        self._nav_rail_lay.addWidget(self._rail_settings_btn)

        # Flyout panel (zero-width when closed)
        self._nav_flyout = _FlyoutPanel(self._nav_rail_panel)

        _rp_lay.addWidget(self._nav_rail)
        _rp_lay.addWidget(self._nav_flyout)

        # Sidebar container — show/hide panels so the layout respects their widths
        self._nav_sidebar_container = QWidget()
        _sc_lay = QHBoxLayout(self._nav_sidebar_container)
        _sc_lay.setContentsMargins(0, 0, 0, 0)
        _sc_lay.setSpacing(0)
        _sc_lay.addWidget(self._nav_flat_panel)
        _sc_lay.addWidget(self._nav_rail_panel)
        self._nav_rail_panel.setVisible(True)    # always visible — no mode switcher

        # Canvas click filter — closes flyout when user clicks content area
        self._canvas_filter = _CanvasClickFilter(self)
        self._canvas_filter.close_requested.connect(self._on_canvas_click)

        # ── Assemble sidebar + content area ───────────────────────────────────
        container = QWidget()
        container.setObjectName("contentArea")
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._nav_sidebar_container)
        # 1px divider between sidebar stack and content
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet(f"background: {NAV_DIVIDER}; max-width: 1px;")
        h.addWidget(div)
        # Content wrapper
        content_wrapper = QWidget()
        content_wrapper.setObjectName("contentArea")
        cw_lay = QVBoxLayout(content_wrapper)
        cw_lay.setContentsMargins(12, 10, 12, 8)
        cw_lay.setSpacing(0)

        # Breadcrumb row — label + "?" help button
        bc_row = QHBoxLayout()
        bc_row.setContentsMargins(0, 0, 0, 0)
        bc_row.setSpacing(4)
        self._back_btn = QPushButton("‹ Back")
        self._back_btn.setFixedHeight(20)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0 4px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._back_btn.setVisible(False)
        self._back_btn.clicked.connect(self._nav_go_back)
        bc_row.addWidget(self._back_btn)

        self._breadcrumb_lbl = QLabel("Getting Started  ›  Home")
        self._breadcrumb_lbl.setFixedHeight(20)
        self._breadcrumb_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 0 2px;"
            f" background: transparent; border: none;"
        )
        bc_row.addWidget(self._breadcrumb_lbl, 1)

        cw_lay.addLayout(bc_row)

        self._tip_bar = QPushButton("ⓘ  Tips  ▾")
        self._tip_bar.setCheckable(True)
        self._tip_bar.setFixedHeight(22)
        self._tip_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tip_bar.setStyleSheet(
            f"QPushButton {{ text-align:left; padding:0 10px; font-size:10px;"
            f" color:{ACCENT}; background:transparent; border:none;"
            f" border-bottom:1px solid {BORDER}; }}"
            f"QPushButton:hover {{ color:{WHITE}; }}"
            f"QPushButton:checked {{ color:{WHITE}; font-weight:bold;"
            f" border-bottom:1px solid {ACCENT}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._tip_bar.toggled.connect(self._toggle_help_panel)
        cw_lay.addWidget(self._tip_bar)

        # Collapsible help strip — shown below breadcrumb, hidden by default
        self._help_panel = QFrame()
        self._help_panel.setObjectName("pageHelpPanel")
        self._help_panel.setStyleSheet(
            f"QFrame#pageHelpPanel {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:6px; }}"
        )
        self._help_panel.setVisible(False)
        hp_lay = QVBoxLayout(self._help_panel)
        hp_lay.setContentsMargins(12, 8, 12, 8)
        hp_lay.setSpacing(4)
        self._help_what_lbl = QLabel()
        self._help_what_lbl.setWordWrap(True)
        self._help_what_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        hp_lay.addWidget(self._help_what_lbl)
        self._help_hidden_lbl = QLabel()
        self._help_hidden_lbl.setWordWrap(True)
        self._help_hidden_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        hp_lay.addWidget(self._help_hidden_lbl)

        _kbd_shortcuts = [
            ("Ctrl+K",         "Command palette — find any page or feature"),
            ("Ctrl+R",         "Run full network scan"),
            ("Ctrl+E",         "Export last scan results"),
            ("Ctrl+Q",         "Quit"),
            ("F5",             "Refresh current page"),
            ("Escape",         "Close section panel"),
            ("Right-click",    "Context menu on any table row"),
            ("Ctrl+Shift+M",   "Visual Diagnostic Overlay"),
        ]
        self._help_shortcuts_lbl = QLabel(
            "<b>Keyboard shortcuts:</b>  " +
            "   ·   ".join(f"<code>{k}</code> {d}" for k, d in _kbd_shortcuts)
        )
        self._help_shortcuts_lbl.setWordWrap(True)
        self._help_shortcuts_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
            f" border-top:1px solid {BORDER}; padding-top:4px; margin-top:2px;"
        )
        self._help_shortcuts_lbl.setTextFormat(Qt.TextFormat.RichText)
        hp_lay.addWidget(self._help_shortcuts_lbl)

        cw_lay.addWidget(self._help_panel)

        # HEALTH-2: offline/no-LAN amber banner (hidden until 3 consecutive ping failures)
        self._lan_banner = QFrame()
        self._lan_banner.setStyleSheet(
            f"QFrame {{ background:{AMBER_BG}; border:1px solid {AMBER};"
            f" border-radius:4px; }}"
        )
        self._lan_banner.setFixedHeight(32)
        self._lan_banner.setVisible(False)
        _lbb = QHBoxLayout(self._lan_banner)
        _lbb.setContentsMargins(10, 0, 10, 0)
        _lbb.setSpacing(8)
        _lan_icon = QLabel("⚠")
        _lan_icon.setStyleSheet(f"font-size:13px; color:{AMBER}; border:none; background:transparent;")
        _lan_lbl = QLabel("No internet connection detected — operating in offline mode.")
        _lan_lbl.setStyleSheet(f"font-size:11px; color:#92400E; border:none; background:transparent;")
        _lan_dismiss = QPushButton("Dismiss")
        _lan_dismiss.setFixedHeight(22)
        _lan_dismiss.setStyleSheet(
            f"QPushButton {{ font-size:10px; color:#92400E; background:transparent;"
            f" border:1px solid #F59E0B; border-radius:3px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:#FEF3C7; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        _lan_dismiss.clicked.connect(lambda: (
            self._lan_banner.setVisible(False),
            setattr(self, "_lan_fail_count", 0),
        ))
        _lbb.addWidget(_lan_icon)
        _lbb.addWidget(_lan_lbl, 1)
        _lbb.addWidget(_lan_dismiss)
        cw_lay.addWidget(self._lan_banner)

        cw_lay.setSpacing(6)
        cw_lay.addWidget(self._stack)
        h.addWidget(content_wrapper, 1)
        content_wrapper.installEventFilter(self._canvas_filter)

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

        # Alert badge refresh — poll every 30 s for unacked alerts on Security Audit section
        self._alert_badge_timer = QTimer(self)
        self._alert_badge_timer.setInterval(30_000)
        self._alert_badge_timer.timeout.connect(self._refresh_alert_badge)
        self._alert_badge_timer.start()
        # Attach empty-state overlays to key scan tables
        from ui.empty_state import EmptyStateOverlay
        EmptyStateOverlay(self._m1_table, "⊞", "No devices found",
                          "Click  Scan  to discover devices on the network")
        EmptyStateOverlay(self._m2_table, "⇌", "No STP anomalies detected",
                          "Run a scan to check for rogue bridges")
        EmptyStateOverlay(self._m3_table, "⚠", "No storms detected",
                          "Run a scan to check for broadcast storms")

        # Keep self._tabs pointing at something for any legacy code that checks it
        self._tabs = container
        return container


    def _build_m1_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # ── KPI summary tiles ─────────────────────────────────────────────────
        lay.addWidget(self._build_kpi_bar())

        self._m1_status = QLabel("Not yet scanned.")
        self._m1_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")

        self._m1_group_btn = QPushButton("▼▼  Collapse All")
        self._m1_group_btn.setFixedHeight(22)
        self._m1_group_btn.setStyleSheet(
            f"QPushButton{{background:{BG_DARK};color:{TEXT_MUTED};border:1px solid {BORDER};"
            f"border-radius:3px;padding:0 8px;font-size:10px;}}"
            f"QPushButton:hover{{background:{BG_HOVER};color:{TEXT_PRIMARY};}}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._m1_group_btn.setVisible(False)
        self._m1_group_btn.clicked.connect(self._m1_toggle_all_groups)

        _node_grp_on = QSettings("NetSentinel", "NetSentinel").value(
            "devices/group_by_node", False, type=bool
        )
        self._m1_group_by_node: bool = _node_grp_on

        # Segmented view control — always enabled, no plugin gate
        self._m1_seg_active_ss = (
            f"QPushButton{{background:{ACCENT_DARK};color:#fff;border:none;"
            f"border-radius:3px;padding:0 10px;font-size:10px;}}"
            f"QPushButton:hover{{background:{ACCENT};}}"
        )
        self._m1_seg_inactive_ss = (
            f"QPushButton{{background:transparent;color:{TEXT_MUTED};border:none;"
            f"border-radius:3px;padding:0 10px;font-size:10px;}}"
            f"QPushButton:hover{{background:{BG_HOVER};color:{TEXT_PRIMARY};}}"
        )
        _seg_frame = QFrame()
        _seg_frame.setFixedHeight(24)
        _seg_frame.setStyleSheet(
            f"QFrame{{background:{BG_DARK};border:1px solid {BORDER};border-radius:4px;}}"
        )
        _seg_lay = QHBoxLayout(_seg_frame)
        _seg_lay.setContentsMargins(1, 1, 1, 1)
        _seg_lay.setSpacing(0)

        self._m1_seg_list = QPushButton("≡  List")
        self._m1_seg_list.setFixedHeight(22)
        self._m1_seg_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self._m1_seg_list.setToolTip("Flat device list")
        self._m1_seg_list.setStyleSheet(
            self._m1_seg_inactive_ss if _node_grp_on else self._m1_seg_active_ss
        )
        self._m1_seg_node = QPushButton("⊞  By Node")
        self._m1_seg_node.setFixedHeight(22)
        self._m1_seg_node.setCursor(Qt.CursorShape.PointingHandCursor)
        self._m1_seg_node.setToolTip("Group devices by mesh node / AP")
        self._m1_seg_node.setStyleSheet(
            self._m1_seg_active_ss if _node_grp_on else self._m1_seg_inactive_ss
        )
        _seg_lay.addWidget(self._m1_seg_list)
        _seg_lay.addWidget(self._m1_seg_node)

        self._m1_seg_list.clicked.connect(lambda: self._on_node_group_toggled(False))
        self._m1_seg_node.clicked.connect(lambda: self._on_node_group_toggled(True))

        _status_row = QHBoxLayout()
        _status_row.setContentsMargins(0, 0, 0, 0)
        _status_row.addWidget(self._m1_status, 1)
        _status_row.addWidget(_seg_frame)
        _status_row.addSpacing(4)
        _status_row.addWidget(self._m1_group_btn)

        # Integration discovery banner — hidden until scan finds a device matching
        # a bundled plugin's default gateway IP
        from PyQt6.QtWidgets import QLabel as _QL, QPushButton as _QPB
        self._m1_int_banner = QFrame()
        self._m1_int_banner.setVisible(False)
        _ib_lay = QHBoxLayout(self._m1_int_banner)
        _ib_lay.setContentsMargins(10, 5, 10, 5)
        _ib_lay.setSpacing(8)
        self._m1_int_banner.setStyleSheet(
            f"QFrame {{ background:{ACCENT}18; border:1px solid {ACCENT}55;"
            " border-radius:4px; }}"
        )
        self._m1_int_lbl = QLabel()
        self._m1_int_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:11px; background:transparent; border:none;"
        )
        _ib_lay.addWidget(self._m1_int_lbl, 1)
        _int_cfg_btn = QPushButton("Configure  →")
        _int_cfg_btn.setFixedHeight(22)
        _int_cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _int_cfg_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            " border-radius:3px; font-size:10px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:#005A9E; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        _int_cfg_btn.clicked.connect(
            lambda: self._nav_rail_go_to("Hardware")
        )
        _ib_lay.addWidget(_int_cfg_btn)

        self._m1_node_hint = QLabel()   # hidden stub — hint lives in By Node group header
        self._m1_node_hint.setVisible(False)

        self._m1_table = _table([
            "IP Address", "Hostname", "MAC Address", "Vendor", "Risk", "Device Type",
            "Node", "Band", "Verdict",
        ])
        self._m1_table.setColumnWidth(0, 120)
        self._m1_table.setColumnWidth(1, 160)
        self._m1_table.setColumnWidth(2, 145)
        self._m1_table.setColumnWidth(3, 180)
        self._m1_table.setColumnWidth(4, 70)
        self._m1_table.setColumnWidth(5, 130)
        self._m1_table.setColumnWidth(6, 155)
        self._m1_table.setColumnWidth(7, 55)
        # Node (6) and Band (7) are hidden until a Deco scan populates them
        self._m1_table.setColumnHidden(6, True)
        self._m1_table.setColumnHidden(7, True)
        self._m1_table.setStyleSheet(
            f"QTableWidget::item:hover {{ background-color: {BG_HOVER}; }}"
        )

        # Column sorting (click header to sort ascending/descending)
        self._m1_table.setSortingEnabled(True)
        self._m1_table.horizontalHeader().setSortIndicatorShown(True)
        self._m1_table.horizontalHeader().sortIndicatorChanged.connect(
            self._m1_sort_changed
        )

        # Right-click context menu
        self._m1_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m1_table.customContextMenuRequested.connect(self._m1_context_menu)

        # Double-click → pre-fill Port Scan (TCP) and navigate there
        self._m1_table.doubleClicked.connect(self._m1_row_double_clicked)

        # Empty-state placeholder shown when table has no rows
        self._m1_empty = QLabel("Run a scan to discover devices on this network.")
        self._m1_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._m1_empty.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:13px; padding:40px;"
            "background:transparent; border:none;"
        )

        # ── Card wrapping table + empty state ─────────────────────────────────
        m1_card, m1_body = _make_card("Discovered Devices")

        # Search bar + filter chips (FILTER-1)
        _frow_w = QWidget()
        _frow_w.setStyleSheet("background:transparent;")
        _frow = QHBoxLayout(_frow_w)
        _frow.setContentsMargins(8, 5, 8, 4)
        _frow.setSpacing(6)

        self._m1_search = QLineEdit()
        self._m1_search.setPlaceholderText("Search IP, hostname, MAC, vendor…")
        self._m1_search.setFixedHeight(26)
        self._m1_search.setClearButtonEnabled(True)
        self._m1_search.setStyleSheet(
            f"QLineEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 6px; font-size:11px; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._m1_search.textChanged.connect(self._m1_apply_filter)
        _frow.addWidget(self._m1_search, 1)

        self._m1_chip_active_ss = (
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" border-radius:3px; padding:0 8px; font-size:10px; }}"
        )
        self._m1_chip_inactive_ss = (
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 8px; font-size:10px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; border-color:{TEXT_MUTED}; }}"
        )
        self._m1_chip = "all"
        self._m1_chip_btns: dict = {}
        for _ckey, _clabel in (
            ("all", "All"), ("online", "Online"),
            ("offline", "Offline"), ("unknown", "Unknown vendor"),
        ):
            _cbtn = QPushButton(_clabel)
            _cbtn.setFixedHeight(22)
            _cbtn.setCursor(Qt.CursorShape.PointingHandCursor)
            _cbtn.setStyleSheet(
                self._m1_chip_active_ss if _ckey == "all" else self._m1_chip_inactive_ss
            )
            _cbtn.clicked.connect(lambda _=False, k=_ckey: self._m1_set_chip(k))
            self._m1_chip_btns[_ckey] = _cbtn
            _frow.addWidget(_cbtn)

        from ui.widgets.density_toggle import DensityToggle
        _frow.addSpacing(4)
        _frow.addWidget(DensityToggle("m1_devices", self._m1_table))

        m1_body.addWidget(_frow_w)

        # Stack: table on top, empty label behind — we toggle visibility
        from PyQt6.QtWidgets import QStackedWidget as _SW
        self._m1_stack = _SW()
        self._m1_stack.addWidget(self._m1_empty)   # index 0 — empty state
        self._m1_stack.addWidget(self._m1_table)   # index 1 — live data
        self._m1_stack.setCurrentIndex(0)
        m1_body.addWidget(self._m1_stack)

        lay.addLayout(_status_row)
        lay.addWidget(self._m1_int_banner)
        lay.addWidget(m1_card, 1)

        from ui.widgets.explainer_panel import ExplainerPanel
        self._m1_explainer = ExplainerPanel("rogue_device")
        self._m1_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m1_explainer)
        return w

    @pyqtSlot('QModelIndex')
    def _m1_row_double_clicked(self, index) -> None:
        """Double-click a device row → pre-fill SYN scanner IP and navigate."""
        ip_item = self._m1_table.item(index.row(), 0)
        if ip_item:
            ip = ip_item.text().strip()
            if ip and hasattr(self, "_syn_host"):
                self._syn_host.setText(ip)
                self._nav_rail_go_to("Port Scan (TCP)")

    def _m1_set_chip(self, key: str) -> None:
        self._m1_chip = key
        for k, btn in self._m1_chip_btns.items():
            btn.setStyleSheet(
                self._m1_chip_active_ss if k == key else self._m1_chip_inactive_ss
            )
        self._m1_apply_filter()

    def _m1_apply_filter(self) -> None:
        text = self._m1_search.text().lower().strip()
        chip = self._m1_chip
        for row in range(self._m1_table.rowCount()):
            text_match = not text or any(
                text in (self._m1_table.item(row, col) or QTableWidgetItem()).text().lower()
                for col in (0, 1, 2, 3)
            )
            risk_item = self._m1_table.item(row, 4)
            risk = (risk_item.text() if risk_item else "").upper()
            vendor_item = self._m1_table.item(row, 3)
            vendor = (vendor_item.text() if vendor_item else "").lower().strip()
            if chip == "all":
                chip_match = True
            elif chip == "online":
                chip_match = risk != "UNKNOWN"
            elif chip == "offline":
                chip_match = risk == "UNKNOWN"
            else:
                chip_match = vendor in ("unknown", "—", "")
            self._m1_table.setRowHidden(row, not (text_match and chip_match))

    def _m1_sort_changed(self, col: int, order) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("home/m1_sort_col", col)
        qs.setValue("home/m1_sort_order", int(order))

    def _m1_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m1_table.rowAtIndex(pos) if hasattr(self._m1_table, 'rowAtIndex') \
              else self._m1_table.rowAt(pos.y())
        if row < 0:
            return
        first = self._m1_table.item(row, 0)
        if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
            return
        ip  = (first or QTableWidgetItem()).text()
        mac = (self._m1_table.item(row, 2) or QTableWidgetItem()).text()
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_scan     = menu.addAction(f"🔍  Port Scan  {ip}")
        act_geo      = menu.addAction(f"🗺  Show on Geo Map →")
        act_abuseipdb = menu.addAction(f"🛡  Check IP (AbuseIPDB) →")
        act_wol      = menu.addAction(f"⚡  Wake-on-LAN  →  {mac}")
        # Show CVE Tracker link only when this IP has tracked CVE entries
        _has_cves = False
        try:
            if self._store:
                _has_cves = any(c.get("host") == ip for c in self._store.list_cve_lifecycles())
        except Exception:
            pass
        act_cve = menu.addAction(f"🔎  View in CVE Tracker →") if _has_cves else None
        menu.addSeparator()
        act_fix      = menu.addAction("🔧  How to Fix")
        menu.addSeparator()
        act_copy_ip  = menu.addAction("📋  Copy IP")
        act_copy_mac = menu.addAction("📋  Copy MAC")
        act_copy_row = menu.addAction("📋  Copy full row")
        chosen = menu.exec(self._m1_table.viewport().mapToGlobal(pos))
        if chosen == act_scan:
            self._run_port_scan(ip)
        elif chosen == act_geo:
            self._show_ip_on_geo_map(ip)
        elif chosen == act_abuseipdb:
            self._threat_intel_page.check_ip(ip)
            self._nav_rail_go_to("Threat Intelligence")
        elif act_cve and chosen == act_cve:
            self._nav_rail_go_to("CVE Tracker")
        elif chosen == act_wol:
            self._send_wol(mac)
        elif chosen == act_fix:
            # find remediation from stored result
            rem = ""
            if self._m1_result:
                for d in self._m1_result.get("devices", []):
                    d_ip = d.get("ip", "") if isinstance(d, dict) else getattr(d, "ip", "")
                    if d_ip == ip:
                        rem = d.get("remediation", "") if isinstance(d, dict) else getattr(d, "remediation", "")
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

    def _net_devices_context_menu(self, pos) -> None:
        """Context menu for the Network Info tab's device table."""
        from PyQt6.QtWidgets import QMenu
        row = self._net_devices_table.rowAt(pos.y())
        if row < 0:
            return
        ip  = (self._net_devices_table.item(row, 0) or QTableWidgetItem()).text()
        mac = (self._net_devices_table.item(row, 2) or QTableWidgetItem()).text()
        if not ip:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_scan  = menu.addAction(f"🔍  Port Scan  {ip}")
        act_geo   = menu.addAction(f"🗺  Show on Geo Map →")
        act_abuse = menu.addAction(f"🛡  Check IP (AbuseIPDB) →")
        menu.addSeparator()
        act_copy_ip  = menu.addAction("📋  Copy IP")
        act_copy_mac = menu.addAction("📋  Copy MAC")
        chosen = menu.exec(self._net_devices_table.viewport().mapToGlobal(pos))
        if chosen == act_scan:
            self._run_port_scan(ip)
        elif chosen == act_geo:
            self._show_ip_on_geo_map(ip)
        elif chosen == act_abuse:
            self._threat_intel_page.check_ip(ip)
            self._nav_rail_go_to("Threat Intelligence")
        elif chosen == act_copy_ip:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(ip)
        elif chosen == act_copy_mac:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(mac)

    # ── Module 2 ──────────────────────────────────────────────────────────────

    def _build_m2_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addWidget(NpcapMissingBanner(parent=empty))
        evl.addStretch()
        em_desc = QLabel(
            "STP/BPDU frame capture identifies unauthorised Spanning Tree root bridges\n"
            "that cause intermittent network drops and DNS failures."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Start STP Capture")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(200)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "Rogue Bridge Detection",
            "STP/BPDU frame capture — identifies unauthorised Spanning Tree root bridges"
        ))
        self._m2_status = QLabel("Not yet scanned.")
        self._m2_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m2_status)
        card, card_body = _make_card("STP Frames Detected")
        self._m2_table = _table([
            "Source MAC", "BPDU Type", "Root MAC", "Bridge Priority",
            "Hello (s)", "MaxAge (s)", "FwdDelay (s)", "Rogue?"
        ])
        self._m2_table.setColumnWidth(0, 150)
        self._m2_table.setColumnWidth(1, 80)
        self._m2_table.setColumnWidth(2, 150)
        self._m2_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m2_table.customContextMenuRequested.connect(self._m2_context_menu)
        card_body.addWidget(self._m2_table)
        lay.addWidget(card, 1)
        from ui.widgets.explainer_panel import ExplainerPanel
        self._m2_explainer = ExplainerPanel("stp_rogue")
        self._m2_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m2_explainer)

        self._m2_stack = QStackedWidget()
        self._m2_stack.addWidget(empty)
        self._m2_stack.addWidget(content)
        return self._m2_stack

    def _m2_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m2_table.rowAt(pos.y())
        if row < 0:
            return
        src_mac = (self._m2_table.item(row, 0) or QTableWidgetItem()).text()
        is_rogue = (self._m2_table.item(row, 7) or QTableWidgetItem()).text().strip().upper() in ("YES", "TRUE", "ROGUE")
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
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
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addWidget(NpcapMissingBanner(parent=empty))
        evl.addStretch()
        em_desc = QLabel(
            "Live packet capture measures broadcast and multicast rates\n"
            "and identifies the device causing a broadcast storm."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Start Broadcast Capture")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(220)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "Broadcast Storm Analysis",
            "Live packet capture — measures broadcast/multicast rates and storm level"
        ))
        self._m3_status = QLabel("Not yet scanned.")
        self._m3_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m3_status)
        stats = QHBoxLayout()
        self._m3_bcast_lbl = self._stat_label("Broadcast/s", "—")
        self._m3_mcast_lbl = self._stat_label("Multicast/s", "—")
        self._m3_ratio_lbl = self._stat_label("Bcast ratio", "—")
        self._m3_level_lbl = self._stat_label("Storm level", "—")
        for w2 in (self._m3_bcast_lbl, self._m3_mcast_lbl,
                   self._m3_ratio_lbl, self._m3_level_lbl):
            stats.addWidget(w2)
        stats.addStretch()
        lay.addLayout(stats)
        card, card_body = _make_card("Broadcast Sources")
        self._m3_table = _table(["Source MAC", "Broadcast Packets", "Rogue Match?"])
        self._m3_table.setColumnWidth(0, 160)
        self._m3_table.setColumnWidth(1, 160)
        self._m3_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m3_table.customContextMenuRequested.connect(self._m3_context_menu)
        card_body.addWidget(self._m3_table)
        lay.addWidget(card, 1)
        from ui.widgets.explainer_panel import ExplainerPanel
        self._m3_explainer = ExplainerPanel("broadcast_storm")
        self._m3_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m3_explainer)

        self._m3_stack = QStackedWidget()
        self._m3_stack.addWidget(empty)
        self._m3_stack.addWidget(content)
        return self._m3_stack

    def _m3_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m3_table.rowAt(pos.y())
        if row < 0:
            return
        src_mac = (self._m3_table.item(row, 0) or QTableWidgetItem()).text()
        bcast   = (self._m3_table.item(row, 1) or QTableWidgetItem()).text()
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
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
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addStretch()
        em_desc = QLabel(
            "No WiFi scan has been run yet.\n"
            "NetSentinel will enumerate nearby networks, detect rogue SSIDs,\n"
            "and flag co-channel interference."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Scan for WiFi Networks")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(220)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "WiFi Networks",
            "Wireless scan — SSID enumeration, rogue AP detection, co-channel interference"
        ))
        self._m4_status = QLabel("Not yet scanned.")
        self._m4_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m4_status)

        # Deco band-usage KPI chips — hidden until mesh data arrives
        self._m4_deco_bar = self._build_m4_deco_bar()
        self._m4_deco_bar.setVisible(False)
        lay.addWidget(self._m4_deco_bar)

        card, card_body = _make_card("Detected Networks")
        self._m4_table = _table([
            "SSID", "BSSID", "Nodes", "Channel", "Band", "Signal (dBm)",
            "Rogue SSID?", "Co-Channel?", "Connected?",
        ])
        self._m4_table.setColumnWidth(0, 180)
        self._m4_table.setColumnWidth(1, 150)
        self._m4_table.setColumnWidth(2, 55)   # Nodes
        self._m4_table.setColumnWidth(5, 105)  # Signal range
        self._m4_table.setColumnWidth(8, 95)   # Connected
        card_body.addWidget(self._m4_table)
        lay.addWidget(card, 1)

        self._m4_stack = QStackedWidget()
        self._m4_stack.addWidget(empty)
        self._m4_stack.addWidget(content)
        return self._m4_stack

    def _build_m4_deco_bar(self) -> QWidget:
        """KPI chips showing Deco band usage — revealed when mesh data is present."""
        bar = QWidget()
        bar.setFixedHeight(62)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 2, 0, 4)
        row.setSpacing(8)

        def _chip(dot_color: str, label: str):
            tile = QFrame()
            tile.setObjectName("card")
            tile.setStyleSheet(
                f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
                f"border-left:3px solid {dot_color};border-radius:0px;}}"
            )
            vl = QVBoxLayout(tile)
            vl.setContentsMargins(8, 4, 8, 4)
            vl.setSpacing(1)
            hdr = QHBoxLayout()
            hdr.setSpacing(4)
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{dot_color};font-size:9px;background:transparent;border:none;")
            lbl = QLabel(label.upper())
            lbl.setStyleSheet(
                f"color:{TEXT_MUTED};font-size:9px;font-weight:bold;"
                "letter-spacing:0.5px;background:transparent;border:none;"
            )
            hdr.addWidget(dot); hdr.addWidget(lbl); hdr.addStretch()
            vl.addLayout(hdr)
            val = QLabel("—")
            val.setStyleSheet(f"color:{TEXT_MUTED};font-size:18px;font-weight:bold;"
                              "background:transparent;border:none;")
            vl.addWidget(val)
            return tile, val

        header = QLabel("Deco band usage")
        header.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;padding:0;background:transparent;")
        row.addWidget(header)

        t1, self._m4_chip_24   = _chip(GREEN,        "2.4 GHz clients")
        t2, self._m4_chip_5    = _chip(ACCENT,        "5 GHz clients")
        t3, self._m4_chip_6    = _chip(CHART_PURPLE,  "6 GHz clients")
        t4, self._m4_chip_wired = _chip(TEXT_SECONDARY, "Wired clients")
        for t in (t1, t2, t3, t4):
            row.addWidget(t, 1)
        row.addStretch()
        return bar

    def _update_m4_deco_chips(self) -> None:
        """Refresh Deco band-usage chips from current mesh enrichment data."""
        if not getattr(self, "_mesh_enrichment", None):
            return
        counts: dict = {"2.4G": 0, "5G": 0, "6G": 0, "Wired": 0}
        for mc in self._mesh_enrichment.values():
            band = getattr(mc, "band", "")
            if band in counts:
                counts[band] += 1
        self._m4_chip_24.setText(str(counts["2.4G"]))
        self._m4_chip_5.setText(str(counts["5G"]))
        self._m4_chip_6.setText(str(counts["6G"]))
        self._m4_chip_wired.setText(str(counts["Wired"]))
        self._m4_deco_bar.setVisible(True)

    # ── Module 5 ──────────────────────────────────────────────────────────────

    def _build_m5_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addStretch()
        em_desc = QLabel(
            "Continuous RTT and DNS monitoring hasn't started yet.\n"
            "Run a scan to begin measuring latency and detecting outages."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Start Monitoring")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(180)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "DNS & Outage Monitor",
            "Continuous RTT/DNS monitoring — latency graph, outage detection, STP correlation"
        ))
        self._m5_status = QLabel("Not yet scanned.")
        self._m5_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m5_status)
        self._graph = LiveGraphWidget()
        self._graph.setMinimumHeight(80)
        lay.addWidget(self._graph, 2)
        card, card_body = _make_card("Detected Outages")
        self._m5_outage_table = _table([
            "Target", "Duration (s)", "Consecutive Drops", "STP Signature?", "Severity"
        ])
        card_body.addWidget(self._m5_outage_table)
        lay.addWidget(card, 1)
        from ui.widgets.explainer_panel import ExplainerPanel
        self._m5_explainer = ExplainerPanel("dns_stability")
        self._m5_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m5_explainer)

        self._m5_stack = QStackedWidget()
        self._m5_stack.addWidget(empty)
        self._m5_stack.addWidget(content)
        return self._m5_stack

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
        hdr_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
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
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
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
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        rl = QVBoxLayout(router_frame)
        rl.setContentsMargins(18, 14, 18, 14)
        rl.setSpacing(6)
        rl_title = QLabel("🔗  Router / Modem Admin Panel")
        rl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        rl_title.setStyleSheet(f"color:{TEXT_PRIMARY};")
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
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        os_l = QVBoxLayout(os_frame)
        os_l.setContentsMargins(18, 12, 18, 12)
        os_l.setSpacing(6)
        os_title = QLabel("⚙️  Network Settings Shortcuts")
        os_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        os_title.setStyleSheet(f"color:{TEXT_PRIMARY};")
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
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        dhcp_l = QVBoxLayout(dhcp_frame)
        dhcp_l.setContentsMargins(18, 12, 18, 12)
        dhcp_l.setSpacing(4)
        dhcp_title = QLabel("🕐  DHCP Lease  &  Adapter Details")
        dhcp_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        dhcp_title.setStyleSheet(f"color:{TEXT_PRIMARY};")
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
        self._net_devices_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._net_devices_table.customContextMenuRequested.connect(self._net_devices_context_menu)
        lay.addWidget(self._net_devices_table, 1)
        return w

    def _update_net_info_ui(self, info: dict):
        """Populate the Network Info tab from a get_network_info() dict."""
        self._net_info = info
        self._protocol_viz_page.set_context(
            net_info=self._net_info,
            devices=self._m1_result.get("devices", []) if self._m1_result else [],
            diag_result=self._diag_result,
            m2_result=self._m2_result,
        )
        self._diagnosis_page.set_network_info(
            info.get("gateway"),
            info.get("gateway_mac"),
        )

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

        # Show a basic header status once the network is confirmed reachable
        if not self._verdict_badge.isVisible():
            if info.get("gateway") and info.get("local_ips"):
                self._verdict_badge.setText("● Network healthy")
                self._verdict_badge.setStyleSheet(
                    f"color:{GREEN}; font-size:11px; font-weight:600;"
                    " background:transparent; border:none; padding:0 12px;"
                )
                self._verdict_badge.setVisible(True)

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

