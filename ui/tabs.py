"""
tabs.py — TabBuilderMixin: page factory and sidebar assembly for Dashboard.

Sprint 6 (S13-1): extracted from ui/dashboard.py.
Sprint 8: split into sub-mixins (_ScanTabsMixin, _NetworkTabsMixin, _DiagTabsMixin)
          in ui/tabs_scan.py, ui/tabs_network.py, ui/tabs_diag.py.

Utility functions are defined in ui/tabs_helpers.py; re-exported here for
backward compatibility with callers that do `from ui.tabs import _table`.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from modules.scan_persistence import record_app_traffic_samples
from ui.nav.labels import NavLabel as L
from ui.nav.rail import _RailButton, _FlyoutPanel, _CanvasClickFilter, _make_nav_icon
from ui.widgets.alert_drawer import AlertDrawer

# ─── Re-export utility functions from tabs_helpers for backward compat ────────
# dashboard.py uses: `from ui.tabs import _table, _make_card, _page_header …`
from ui.tabs_helpers import (  # noqa: F401 — intentional re-export
    _make_scroll_area,
    _table,
    _add_row,
    _add_skeleton_rows,
    _empty_state_widget,
    _error_state_widget,
    _make_card,
    _page_header,
)

from ui.tabs_scan import _ScanTabsMixin
from ui.tabs_network import _NetworkTabsMixin
from ui.tabs_diag import _DiagTabsMixin
from ui.tabs_analysis import _AnalysisTabsMixin
from ui.tabs_analysis_isp import _AnalysisIspMixin
from ui.tabs_recon import _ReconTabsMixin
from ui.tabs_monitors import _MonitorTabsMixin
from ui.tabs_help import _HelpTabsMixin
from ui import styles as _s


class TabBuilderMixin(_ScanTabsMixin, _NetworkTabsMixin, _DiagTabsMixin,
                      _AnalysisTabsMixin, _AnalysisIspMixin, _ReconTabsMixin,
                      _MonitorTabsMixin, _HelpTabsMixin):
    """Mixin providing all tab/page content builders for Dashboard.

    Extracted from ui/dashboard.py (Sprint 6, S13-1).
    Sprint 8: decomposed into sub-mixins for scan (M1–M5), network info,
    and diagnostics/logger/tools.
    P7: Topology/ARP/DHCP/Bandwidth/Scheduler/SNMP tab builders extracted to
    ui/tabs_monitors.py; Help tab + About dialog extracted to ui/tabs_help.py.
    This class retains only _build_tabs() (the page factory + sidebar
    assembly method).
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
        self._inventory_page.show_on_map.connect(self._show_ip_on_geo_map)
        self.global_time_range_changed.connect(self._service_page.set_global_hours)
        self._service_page.diagnose_service.connect(self._on_service_page_diagnose)

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

        def _mk_baseline_page():
            from ui.pages.baseline_page import BaselinePage
            self._baseline_page = BaselinePage(store=self._store, parent=None)
            self._baseline_page.drift_detected.connect(self._on_config_drift_detected)
            return self._baseline_page
        self._lazy_or_build("_baseline_page", L.CONFIG_SNAPSHOTS, _mk_baseline_page)

        from ui.pages.trend_page import TrendPage
        self._trend_page = TrendPage(store=self._store, parent=None)
        self._trend_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.maintenance_page import MaintenancePage
        self._maintenance_page = MaintenancePage(parent=None)

        from ui.pages.snmp_trap_page import SnmpTrapPage
        self._snmp_trap_page = SnmpTrapPage(store=self._store)

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

        def _mk_troubleshoot_page():
            from ui.pages.troubleshoot_page import TroubleshootPage
            self._troubleshoot_page = TroubleshootPage(parent=None)
            self._troubleshoot_page.navigate_to.connect(self._nav_rail_go_to)
            self._troubleshoot_page.diagnose_symptom.connect(self._on_diagnose_symptom)
            return self._troubleshoot_page
        self._lazy_or_build("_troubleshoot_page", L.TROUBLESHOOT, _mk_troubleshoot_page)

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

        def _mk_connections_page():
            from ui.pages.connections_page import ConnectionsPage
            self._connections_page = ConnectionsPage(parent=None)
            self._connections_page.show_on_map.connect(self._show_ip_on_geo_map)
            self._connections_page.focus_host_in_inventory.connect(
                lambda ip: (self._nav_rail_go_to(L.INVENTORY_CHANGES),
                            self._inventory_page.select_device(ip))
            )
            self._connections_page.lookup_threat_intel.connect(
                lambda ip: (self._threat_intel_page.check_ip(ip),
                            self._nav_rail_go_to(L.THREAT_INTEL))
            )
            self._connections_page.set_popover(self._device_popover)
            return self._connections_page
        self._lazy_or_build("_connections_page", L.ACTIVE_CONNECTIONS, _mk_connections_page)
        self._inventory_page.show_connections_for.connect(
            lambda ip: (self._ensure_page("_connections_page").focus_on_ip(ip),
                        self._nav_rail_go_to(L.ACTIVE_CONNECTIONS))
        )

        from ui.pages.live_bandwidth_page import LiveBandwidthPage
        self._live_bandwidth_page = LiveBandwidthPage(parent=None)

        def _mk_app_traffic_page():
            from ui.pages.app_traffic_page import AppTrafficPage
            self._app_traffic_page = AppTrafficPage(store=self._store, parent=None)
            self._app_traffic_page.traffic_sample_ready.connect(self._on_app_traffic_sample)
            self._app_traffic_page.top_host_changed.connect(self._home_page.on_bandwidth_update)
            if self._app_traffic_pending_label_map is not None:
                self._app_traffic_page.set_label_map(self._app_traffic_pending_label_map)
                self._app_traffic_pending_label_map = None
            return self._app_traffic_page
        self._lazy_or_build("_app_traffic_page", L.APP_TRAFFIC, _mk_app_traffic_page)

        def _mk_dhcp_lease_page():
            from ui.pages.dhcp_lease_page import DhcpLeasePage
            self._dhcp_lease_page = DhcpLeasePage(parent=None)
            self._dhcp_lease_page.navigate_to.connect(self._nav_rail_go_to)
            self._dhcp_lease_page.select_device.connect(self._inventory_page.select_device)
            return self._dhcp_lease_page
        self._lazy_or_build("_dhcp_lease_page", L.DHCP_LEASES, _mk_dhcp_lease_page)

        def _mk_dns_zone_page():
            from ui.pages.dns_zone_page import DnsZonePage
            self._dns_zone_page = DnsZonePage(parent=None)
            self._dns_zone_page.scan_complete.connect(self._on_dns_zone_complete)
            return self._dns_zone_page
        self._lazy_or_build("_dns_zone_page", L.DNS_ZONE_MAP, _mk_dns_zone_page)

        from ui.pages.threat_intel_page import ThreatIntelPage
        self._threat_intel_page = ThreatIntelPage(parent=None)
        self._threat_intel_page.show_on_map.connect(self._show_ip_on_geo_map)
        self._threat_intel_page.show_in_connections.connect(
            lambda ip: (self._ensure_page("_connections_page").focus_on_ip(ip),
                        self._nav_rail_go_to(L.ACTIVE_CONNECTIONS))
        )

        from ui.pages.security_overview_page import SecurityOverviewPage
        self._security_overview_page = SecurityOverviewPage(store=self._store, parent=None)
        self._security_overview_page.navigate_to.connect(self._nav_rail_go_to)
        self._security_overview_page.scan_requested.connect(self._start_full_scan)

        from ui.pages.cve_page import CvePage
        self._cve_page = CvePage(self._store, parent=None)
        self._cve_page.navigate_to_inventory.connect(
            lambda ip: (self._nav_rail_go_to(L.INVENTORY_CHANGES), self._inventory_page.select_device(ip))
        )
        self._cve_page.navigate_to.connect(self._nav_rail_go_to)
        self._cve_page.lookup_threat_intel_for.connect(
            lambda ip: (self._threat_intel_page.focus_on_host(ip),
                        self._nav_rail_go_to(L.THREAT_INTEL))
        )
        self._inventory_page.check_cves_for.connect(
            lambda ip: (self._cve_page.focus_on_host(ip),
                        self._nav_rail_go_to(L.CVE_TRACKER))
        )
        self._inventory_page.navigate_to.connect(self._nav_rail_go_to)

        # ── DEVICE-1: device quick-profile popover ────────────────────────────
        from ui.widgets.device_popover import DevicePopover
        self._device_popover = DevicePopover(parent=self)
        self._device_popover.set_store(self._store)
        self._device_popover.navigate_to_inventory.connect(self._on_popover_open_inventory)
        self._device_popover.navigate_to_threat_intel.connect(self._on_popover_open_threat_intel)

        # Inject popover into pages that need it (connections_page's own
        # set_popover call lives in its lazy factory above — it isn't
        # constructed yet at this point when lazy).
        for _p in (self._threat_intel_page, self._cve_page, self._log_hub_page):
            if hasattr(_p, "set_popover"):
                _p.set_popover(self._device_popover)

        from ui.pages.automation_page import AutomationPage
        self._automation_page = AutomationPage(parent=None)

        from ui.pages.network_doc_page import NetworkDocPage
        self._network_doc_page = NetworkDocPage(parent=None)

        from ui.pages.mqtt_page import MqttPage
        self._mqtt_page = MqttPage(parent=None)

        def _mk_ip_calc_page():
            from ui.pages.ip_calculator_page import IpCalculatorPage
            self._ip_calc_page = IpCalculatorPage(parent=None)
            return self._ip_calc_page
        self._lazy_or_build("_ip_calc_page", L.IP_CALCULATOR, _mk_ip_calc_page)

        def _mk_wifi_heatmap_page():
            from ui.pages.wifi_heatmap_page import WifiHeatmapPage
            self._wifi_heatmap_page = WifiHeatmapPage(parent=None)
            return self._wifi_heatmap_page
        self._lazy_or_build("_wifi_heatmap_page", L.WIFI_HEATMAP, _mk_wifi_heatmap_page)

        from ui.pages.geo_map_page import GeoMapPage
        self._geo_map_page = GeoMapPage(store=self._store, parent=None)
        self._geo_map_page.navigate_requested.connect(self._nav_rail_go_to)
        self._wan_ip_ready.connect(self._geo_map_page.set_home_ip)
        self._wan_ip_nav_req.connect(self._on_wan_ip_nav)

        from ui.pages.trigger_builder_page import TriggerBuilderPage
        self._trigger_page = TriggerBuilderPage(store=self._store, parent=None)

        from ui.pages.lab_mode_page import LabModePage
        self._lab_mode_page = LabModePage(store=self._store, parent=None)

        def _mk_protocol_viz_page():
            from ui.pages.protocol_viz_page import ProtocolVizPage
            self._protocol_viz_page = ProtocolVizPage(parent=None)
            self._protocol_viz_page.navigate_to.connect(self._nav_rail_go_to)
            # Replay context buffered by _feed_protocol_viz_context() while this
            # page was still a placeholder (scan handlers feed it on every scan,
            # independent of nav — see ui/nav/lazy_page.py).
            if self._protocol_viz_pending_context is not None:
                self._protocol_viz_page.set_context(**self._protocol_viz_pending_context)
                self._protocol_viz_pending_context = None
            return self._protocol_viz_page
        self._lazy_or_build("_protocol_viz_page", L.PROTOCOL_VISUALIZER, _mk_protocol_viz_page)

        def _mk_discover_page():
            from ui.pages.discover_page import FeatureGuidePage
            self._discover_page = FeatureGuidePage(parent=None)
            self._discover_page.navigate_to.connect(self._nav_rail_go_to)
            return self._discover_page
        self._lazy_or_build("_discover_page", L.FEATURE_GUIDE, _mk_discover_page)

        from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage
        self._service_diagnostics_page = ServiceDiagnosticsPage(parent=None)
        self._service_diagnostics_page.scan_complete.connect(self._on_service_diag_complete)

        from ui.pages.hardware_integration_page import HardwareIntegrationPage
        self._hardware_integration_page = HardwareIntegrationPage(parent=None)
        self._hardware_integration_page.plugin_result.connect(self._on_hardware_plugin_result)
        self._hardware_integration_page.plugin_page_added.connect(self._on_plugin_page_added)
        self._hardware_integration_page.plugin_page_removed.connect(self._on_plugin_page_removed)
        self._hardware_integration_page.plugin_renamed.connect(self._on_plugin_page_renamed)
        self._hardware_integration_page.navigate_to.connect(self._nav_rail_go_to)
        self._hardware_integration_page.geo_map_ip.connect(self._show_ip_on_geo_map)
        self._hardware_integration_page.port_scan_ip.connect(
            lambda ip: (self._syn_host.setText(ip), self._nav_rail_go_to(L.PORT_SCAN_TCP))
        )
        self._hardware_integration_page.check_abuse_ip.connect(
            lambda ip: (self._threat_intel_page.check_ip(ip), self._nav_rail_go_to(L.THREAT_INTEL))
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
            _pg.navigate_to.connect(self._nav_rail_go_to)
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

        # Populate Network Logger DB bar and set initial Monitor badge once the event loop starts.
        from PyQt6.QtCore import QTimer as _QT
        _QT.singleShot(0, lambda: self._log_hub_page.update_plugin_sources(
            [pg._label for pg in self._plugin_pages.values()]
        ))
        _QT.singleShot(0, self._update_monitor_badge)
        _QT.singleShot(0, self._push_monitor_pills)

        def _mk_rest_api_page():
            from ui.pages.rest_api_page import RestApiPage
            self._rest_api_page = RestApiPage(store=self._store, parent=None)
            return self._rest_api_page
        self._lazy_or_build("_rest_api_page", L.REST_API, _mk_rest_api_page)

        self._mtr_tab_widget      = self._build_mtr_tab()
        self._adv_tab_widget      = self._build_advanced_tools_tab()
        self._port_scanner_tab_widget = self._build_port_scanner_tab()
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

        def _mk_wifi_monitor_page():
            from ui.pages.wifi_monitor_page import WiFiMonitorPage
            self._wifi_monitor_page = WiFiMonitorPage(parent=None)
            return self._wifi_monitor_page
        self._lazy_or_build("_wifi_monitor_page", L.MONITOR_802_11, _mk_wifi_monitor_page)

        from ui.pages.monitor_overview_page import MonitorOverviewPage
        self._monitor_overview_page = MonitorOverviewPage(parent=None)
        self._monitor_overview_page.navigate_to.connect(self._nav_rail_go_to)
        self._monitor_overview_page.start_all_requested.connect(
            lambda: (self._start_arp_monitor(), self._start_dhcp_scan(), self._toggle_logger())
        )
        if self._store is not None:
            self._monitor_overview_page.set_store(self._store)

        def _mk_help_tab_widget():
            self._help_tab_widget = self._build_help_tab()
            return self._help_tab_widget
        self._lazy_or_build("_help_tab_widget", L.HELP_REFERENCE, _mk_help_tab_widget)

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
        _s.themed_ss(self._logging_container, "QTabWidget::pane {{ border:1px solid {BORDER}; background:{BG_DARK}; }}"
            "QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            "  padding:6px 18px; border:1px solid {BORDER}; border-bottom:none; margin-right:2px; }}"
            "QTabBar::tab:selected {{ background:{ACCENT}; color:{BG_DARK}; font-weight:bold; }}"
            "QTabBar::tab:hover {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
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
            self._home_page.start_arp_requested.connect(self._start_arp_monitor)
            self._home_page.start_logger_requested.connect(self._toggle_logger)
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
        self._diagnosis_page.service_diag_requested.connect(self._on_service_page_diagnose)

        # Populate home page suggestions on first build (deferred so _home_page exists)
        from PyQt6.QtCore import QTimer as _QTr
        _QTr.singleShot(0, self._refresh_home_suggestions)

        # ── Worker refs ───────────────────────────────────────────────────────
        self._arp_worker:        Optional[object] = None
        self._dhcp_worker:       Optional[object] = None
        self._bw_worker:         Optional[object] = None
        self._sched_worker:      Optional[object] = None
        self._snmp_worker:       Optional[object] = None
        self._snmp_if_worker:    Optional[object] = None
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
        self._nav_delegate = self._NavAdminDelegate(self._nav_admin_rows, self._nav)
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
        self._nav_add_page("⬡", "Dashboard",            self._overview_page)
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
        self._nav_add_page("⊕", "Geolocation Map",    self._geo_map_page)
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
        _s.themed_ss(self._nav_flat_panel, "QWidget {{ background:{SIDEBAR_BG}; }}")
        _fp_lay = QVBoxLayout(self._nav_flat_panel)
        _fp_lay.setContentsMargins(0, 0, 0, 0)
        _fp_lay.setSpacing(0)

        self._mode_seg_btns: dict = {}   # kept for compat — buttons no longer rendered

        # Search / filter (flat panel only — hidden by default)
        self._nav_search = QLineEdit()
        self._nav_search.setObjectName("navSearch")
        self._nav_search.setPlaceholderText("  Filter…")
        self._nav_search.setToolTip(_s.safe_tooltip("Filter sidebar pages  (Ctrl+F)"))
        self._nav_search.setFixedHeight(28)
        _s.themed_ss(self._nav_search, "QLineEdit#navSearch {{"
            " background:{SIDEBAR_HOVER}; color:{SIDEBAR_ITEM_FG};"
            " border:none; border-bottom:1px solid {NAV_DIVIDER};"
            " padding:0 8px; font-size:11px; }}"
            "QLineEdit#navSearch:focus {{ color:{WHITE}; }}")
        self._nav_search.textChanged.connect(self._on_nav_search_changed)
        self._nav_search.setVisible(False)

        # Collapse ◀ / ▶ toggle (flat panel footer)
        self._sidebar_toggle_btn = QPushButton("◀")
        self._sidebar_toggle_btn.setFixedHeight(24)
        _s.themed_ss(self._sidebar_toggle_btn, "QPushButton {{ background:{SIDEBAR_SECTION_BG}; color:{SIDEBAR_SECTION_FG};"
            " border:none; border-top:1px solid {NAV_DIVIDER}; font-size:11px; }}"
            "QPushButton:hover {{ color:{WHITE}; background:{SIDEBAR_HOVER}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        self._sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)

        _fp_lay.addWidget(self._nav_search)
        _fp_lay.addWidget(self._nav, 1)
        _fp_lay.addWidget(self._sidebar_toggle_btn)

        # Panel 1 — activity rail + flyout (Standard/Pro mode)
        self._nav_rail_panel = QWidget()
        _s.themed_ss(self._nav_rail_panel, "QWidget {{ background:{SIDEBAR_BG}; }}")
        _rp_lay = QHBoxLayout(self._nav_rail_panel)
        _rp_lay.setContentsMargins(0, 0, 0, 0)
        _rp_lay.setSpacing(0)

        # 48px icon rail
        self._nav_rail = QWidget()
        self._nav_rail.setFixedWidth(56)
        _s.themed_ss(self._nav_rail, "background: {SIDEBAR_BG}; border-right: 1px solid {NAV_DIVIDER};")
        self._nav_rail_lay = QVBoxLayout(self._nav_rail)
        self._nav_rail_lay.setContentsMargins(0, 0, 0, 0)
        self._nav_rail_lay.setSpacing(0)

        # Persistent search button — always visible at top of rail, opens Ctrl+K palette
        _rail_search_btn = QPushButton()
        _rail_search_btn.setFixedSize(56, 32)
        _rail_search_btn.setToolTip(_s.safe_tooltip("Search all pages  (Ctrl+K)"))
        _rail_search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _rail_search_btn.setIcon(_make_nav_icon("search", 18, _s.TEXT_MUTED))
        _rail_search_btn.setIconSize(QSize(18, 18))
        _rail_search_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; outline: none; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.07); }}"
            f"QPushButton:focus, QPushButton:focus-visible {{"
            f" outline: none; border: none; }}"
        )
        _rail_search_btn.clicked.connect(self._open_command_palette)
        # "Ctrl+K" chip — always-visible shortcut hint below the search icon
        _ctrlk_chip = QLabel("Ctrl+K")
        _ctrlk_chip.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        _ctrlk_chip.setFixedWidth(56)
        _s.themed_ss(_ctrlk_chip, "font-size:8px; color:{TEXT_MUTED}; background:transparent;"
            " border:none; border-bottom:1px solid {NAV_DIVIDER}; padding-bottom:4px;")
        _ctrlk_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        _ctrlk_chip.mousePressEvent = lambda _e: self._open_command_palette()
        self._nav_rail_lay.addWidget(_rail_search_btn)
        self._nav_rail_lay.addWidget(_ctrlk_chip)
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
        _s.themed_ss(div, "background: {NAV_DIVIDER}; max-width: 1px;")
        h.addWidget(div)
        # Content wrapper
        content_wrapper = QWidget()
        content_wrapper.setObjectName("contentArea")
        cw_lay = QVBoxLayout(content_wrapper)
        cw_lay.setContentsMargins(12, 10, 12, 8)
        cw_lay.setSpacing(0)
        self._content_area_layout = cw_lay

        # Breadcrumb row — label + "?" help button
        bc_row = QHBoxLayout()
        bc_row.setContentsMargins(0, 0, 0, 0)
        bc_row.setSpacing(4)
        self._back_btn = QPushButton("‹ Back")
        self._back_btn.setFixedHeight(20)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._back_btn, "QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            " border:none; padding:0 4px; }}"
            "QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._back_btn.setVisible(False)
        self._back_btn.clicked.connect(self._nav_go_back)
        bc_row.addWidget(self._back_btn)

        self._breadcrumb_lbl = QLabel("Getting Started  ›  Home")
        self._breadcrumb_lbl.setFixedHeight(20)
        _s.themed_ss(self._breadcrumb_lbl, "color: {TEXT_SECONDARY}; font-size: 11px; padding: 0 2px;"
            " background: transparent; border: none;")
        bc_row.addWidget(self._breadcrumb_lbl, 1)

        cw_lay.addLayout(bc_row)

        self._tip_bar = QPushButton("ⓘ  Tips  ▾")
        self._tip_bar.setCheckable(True)
        self._tip_bar.setFixedHeight(22)
        self._tip_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._tip_bar, "QPushButton {{ text-align:left; padding:0 10px; font-size:10px;"
            " color:{ACCENT}; background:transparent; border:none;"
            " border-bottom:1px solid {BORDER}; }}"
            "QPushButton:hover {{ color:{WHITE}; }}"
            "QPushButton:checked {{ color:{WHITE}; font-weight:bold;"
            " border-bottom:1px solid {ACCENT}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._tip_bar.toggled.connect(self._toggle_help_panel)
        cw_lay.addWidget(self._tip_bar)

        # Collapsible help strip — shown below breadcrumb, hidden by default
        self._help_panel = QFrame()
        self._help_panel.setObjectName("pageHelpPanel")
        _s.themed_ss(self._help_panel, "QFrame#pageHelpPanel {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:6px; }}")
        self._help_panel.setVisible(False)
        hp_lay = QVBoxLayout(self._help_panel)
        hp_lay.setContentsMargins(12, 8, 12, 8)
        hp_lay.setSpacing(4)
        self._help_what_lbl = QLabel()
        self._help_what_lbl.setWordWrap(True)
        _s.themed_ss(self._help_what_lbl, "font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;")
        hp_lay.addWidget(self._help_what_lbl)
        self._help_hidden_lbl = QLabel()
        self._help_hidden_lbl.setWordWrap(True)
        _s.themed_ss(self._help_hidden_lbl, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;")
        hp_lay.addWidget(self._help_hidden_lbl)

        _kbd_shortcuts = [
            ("Ctrl+K",         "Command palette — find any page or feature"),
            ("Ctrl+F",         "Focus sidebar search"),
            ("Ctrl+Q",         "Quit"),
            ("Escape",         "Close section panel"),
            ("Right-click",    "Context menu on any table row"),
            ("Ctrl+Shift+H",   "Quick Check Window"),
        ]
        self._help_shortcuts_lbl = QLabel(
            "<b>Keyboard shortcuts:</b>  " +
            "   ·   ".join(f"<code>{k}</code> {d}" for k, d in _kbd_shortcuts)
        )
        self._help_shortcuts_lbl.setWordWrap(True)
        _s.themed_ss(self._help_shortcuts_lbl, "font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
            " border-top:1px solid {BORDER}; padding-top:4px; margin-top:2px;")
        self._help_shortcuts_lbl.setTextFormat(Qt.TextFormat.RichText)
        hp_lay.addWidget(self._help_shortcuts_lbl)

        cw_lay.addWidget(self._help_panel)

        # HEALTH-2: offline/no-LAN amber banner (hidden until 3 consecutive ping failures)
        self._lan_banner = QFrame()
        _s.themed_ss(self._lan_banner, "QFrame {{ background:{AMBER_BG}; border:1px solid {AMBER};"
            " border-radius:4px; }}")
        self._lan_banner.setFixedHeight(32)
        self._lan_banner.setVisible(False)
        _lbb = QHBoxLayout(self._lan_banner)
        _lbb.setContentsMargins(10, 0, 10, 0)
        _lbb.setSpacing(8)
        _lan_icon = QLabel("⚠")
        _s.themed_ss(_lan_icon, "font-size:13px; color:{AMBER}; border:none; background:transparent;")
        _lan_lbl = QLabel("No internet connection detected — operating in offline mode.")
        _s.themed_ss(_lan_lbl, "font-size:11px; color:{INLINE_WARN_FG}; border:none; background:transparent;")
        _lan_dismiss = QPushButton("Dismiss")
        _lan_dismiss.setFixedHeight(22)
        _s.themed_ss(_lan_dismiss, "QPushButton {{ font-size:10px; color:{INLINE_WARN_FG}; background:transparent;"
            " border:1px solid {AMBER}; border-radius:3px; padding:0 8px; }}"
            "QPushButton:hover {{ background:{INLINE_WARN_BG}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
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
        # Shared alert drawer — slides in at window right edge from any page
        self._shared_alert_drawer = AlertDrawer(self)
        self._shared_alert_drawer.set_store(self._store)
        self._shared_alert_drawer.navigate_to.connect(self._nav_rail_go_to)
        self._shared_alert_drawer.view_in_log_hub.connect(self._on_view_alert_in_log_hub)
        self._shared_alert_drawer.acknowledged.connect(self._on_shared_drawer_acked)
        h.addWidget(self._shared_alert_drawer)
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

    def _on_dns_zone_complete(self, verdict: str) -> None:
        """Feed DNS Zone scan completion into the scan registry."""
        import time as _time
        self._nav_set_scan_state(L.DNS_ZONE_MAP, "fresh", ts=_time.time(), verdict=verdict)

    def _on_service_diag_complete(self) -> None:
        """Feed Service Diagnostics completion into the scan registry."""
        import time as _time
        result = getattr(self._service_diagnostics_page, "_last_result", None)
        verdict = ""
        if result is not None:
            svc = getattr(result, "service_name", "")
            layer = getattr(result, "failure_layer", "none")
            verdict = f"{svc}: {layer}" if layer != "none" else f"{svc}: OK"
        self._nav_set_scan_state(L.SERVICE_DIAGNOSTICS, "fresh", ts=_time.time(), verdict=verdict or "Diagnostics complete")

    def _on_service_page_diagnose(self, service_id: str) -> None:
        """Navigate to Service Diagnostics, pre-selecting service_id if provided."""
        if service_id:
            self._service_diagnostics_page.set_service(service_id)
        self._nav_rail_go_to(L.SERVICE_DIAGNOSTICS)

    def _on_diagnose_symptom(self, symptom_key: str) -> None:
        """Pre-select a symptom on DiagnosisPage and navigate to it."""
        self._diagnosis_page.preset_symptom(symptom_key)
        self._nav_rail_go_to(L.WHATS_WRONG)

    def _on_app_traffic_sample(self, samples: list) -> None:
        """Persist App Traffic per-flow samples to MetricStore in one batched
        transaction (S6-1, RULE-DW1, Phase B1 — was one commit per sample).

        AppTrafficPage never writes to the store directly (ARCH RULE 1) — it
        emits traffic_sample_ready and this dashboard-layer handler performs
        the actual write.
        """
        if not self._store:
            return
        rows = []
        for s in samples:
            try:
                rows.append({
                    "mac": s["mac"], "label": s["label"], "category": s["category"],
                    "app": s["app"], "bytes_total": s["bytes_total"],
                    "window_s": s["window_s"], "cdn": s.get("cdn"),
                })
            except Exception:
                pass  # non-fatal — a single malformed sample shouldn't drop the rest
        if rows:
            record_app_traffic_samples(self._store, rows)
