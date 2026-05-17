# -*- mode: python ; coding: utf-8 -*-
"""
NetSentinel — PyInstaller build specification.

This is the SINGLE SOURCE OF TRUTH for the packaged executable.
Edit this file when adding new modules or dependencies.
build.bat and .github/workflows/release.yml both reference it so
changes propagate to all platforms automatically.

Build (production, windowed):
    pyinstaller NetSentinel.spec

Debug build (keeps a console window so print/traceback output is visible):
    set NETSENTINEL_DEBUG=1 && pyinstaller NetSentinel.spec   (Windows)
    NETSENTINEL_DEBUG=1 pyinstaller NetSentinel.spec           (macOS/Linux)
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all

# ── Build mode ────────────────────────────────────────────────────────────────
# Set NETSENTINEL_DEBUG=1 to get a console window for troubleshooting.
_debug_build = os.environ.get("NETSENTINEL_DEBUG", "0") == "1"

# ── Data files ────────────────────────────────────────────────────────────────
datas = [
    ("offenders.json", "."),
    ("assets/icons", "assets/icons"),
    ("ui/assets", "ui/assets"),
]

# ── Collect whole packages (data + binaries + submodule tree) ─────────────────
# PyInstaller cannot auto-discover dynamically-loaded backends and lazy-loaded
# protocol layers, so we collect every file for these packages.
binaries: list = []
hiddenimports: list = [
    # PyQt6 Qt modules that are loaded at runtime via dynamic dispatch
    "PyQt6.sip",
    "PyQt6.QtCore",
    "PyQt6.QtWidgets",
    "PyQt6.QtGui",
    "PyQt6.QtNetwork",
    "PyQt6.QtPrintSupport",
    "PyQt6.QtSvg",
    "PyQt6.QtOpenGL",
    "PyQt6.QtOpenGLWidgets",
    # Matplotlib backend used by ui/live_graph.py
    "matplotlib.backends.backend_qtagg",
    # Scapy loads all protocol layers lazily; collect them explicitly
    "scapy.layers.all",
    "scapy.arch.windows",
    # speedtest-cli
    "speedtest",
    # psutil (process/network stats)
    "psutil",
    "psutil._pswindows",
    # keyring platform backends
    "keyring",
    "keyring.backends.Windows",
    "keyring.backends.fail",
    # Flask and dependencies (REST API)
    "flask",
    "flask.json",
    "werkzeug",
    "werkzeug.serving",
    "werkzeug.routing",
    "jinja2",
    "click",
    "itsdangerous",
    # ── modules/ — every backend module listed explicitly ─────────────────────
    "modules.alert_engine",
    "modules.arp_monitor",
    "modules.availability_monitor",
    "modules.bandwidth_monitor",
    "modules.cert_monitor",
    "modules.cloud_metadata",
    "modules.colours",
    "modules.combined_discovery",
    "modules.config_baseline",
    "modules.credentialed_scan",
    "modules.cve_lookup",
    "modules.deco_client",
    "modules.device_classifier",
    "modules.device_tracker",
    "modules.dhcp_detector",
    "modules.dhcp_lease_scanner",
    "modules.dns_correlator",
    "modules.dns_zone_scanner",
    "modules.ha_detector",
    "modules.internet_exposure",
    "modules.iot_baseline",
    "modules.log_chart",
    "modules.mac_lookup",
    "modules.mac_registry",
    "modules.maintenance_window",
    "modules.metric_store",
    "modules.name_resolver",
    "modules.network_benchmark",
    "modules.network_diagnostics",
    "modules.network_logger",
    "modules.nl_query",
    "modules.notification_router",
    "modules.os_fingerprint",
    "modules.plugin_system",
    "modules.port_scanner",
    "modules.private_endpoint_checker",
    "modules.process_monitor",
    "modules.report_exporter",
    "modules.report_scheduler",
    "modules.rest_api",
    "modules.risk_scorer",
    "modules.rogue_device",
    "modules.diagnostic_card",
    "modules.lab_scenarios",
    "modules.root_cause_correlator",
    "modules.scheduler",
    "modules.service_monitor",
    "modules.smb_enumerator",
    "modules.snmp_poller",
    "modules.snmp_trap_receiver",
    "modules.speed_tester",
    "modules.storm_analyser",
    "modules.stp_detector",
    "modules.syn_scanner",
    "modules.syslog_receiver",
    "modules.threat_intel",
    "modules.tls_checker",
    "modules.trend_analyser",
    "modules.utils",
    "modules.wifi_heatmap",
    "modules.wifi_scanner",
    # ── ui/ — shell and all page modules ──────────────────────────────────────
    "ui.dashboard",
    "ui.command_palette",
    "ui.empty_state",
    "ui.expanding_table",
    "ui.first_run_dialog",
    "ui.live_graph",
    "ui.npcap_banner",
    "ui.skeleton",
    "ui.styles",
    "ui.system_tray",
    "ui.topology_widget",
    "ui.pages.automation_page",
    "ui.pages.baseline_page",
    "ui.pages.cert_page",
    "ui.pages.connections_page",
    "ui.pages.cve_page",
    "ui.pages.dhcp_lease_page",
    "ui.pages.discover_page",
    "ui.pages.dns_zone_page",
    "ui.pages.geo_map_page",
    "ui.pages.history_page",
    "ui.pages.home_automation_page",
    "ui.pages.home_page",
    "ui.pages.inventory_page",
    "ui.pages.ip_calculator_page",
    "ui.pages.lab_mode_page",
    "ui.pages.live_bandwidth_page",
    "ui.pages.log_hub_page",
    "ui.pages.maintenance_page",
    "ui.pages.mesh_router_page",
    "ui.pages.modem_page",
    "ui.pages.mqtt_page",
    "ui.pages.network_doc_page",
    "ui.pages.notifications_page",
    "ui.pages.ookla_cli_banner",
    "ui.pages.overview_page",
    "ui.pages.protocol_viz_page",
    "ui.pages.reports_page",
    "ui.pages.service_page",
    "ui.pages.settings_page",
    "ui.pages.snmp_trap_page",
    "ui.pages.speed_test_page",
    "ui.pages.syslog_page",
    "ui.pages.threat_intel_page",
    "ui.pages.trend_page",
    "ui.pages.trigger_builder_page",
    "ui.pages.uptime_page",
    "ui.pages.wifi_heatmap_page",
    "ui.widgets.explainer_panel",
    "ui.widgets.protocol_canvas",
    "modules.protocol_animator",
    # ── workers/ — all QThread workers ────────────────────────────────────────
    "workers.availability_worker",
    "workers.cert_worker",
    "workers.dhcp_lease_worker",
    "workers.diagnosis_worker",
    "workers.dns_zone_worker",
    "workers.ha_worker",
    "workers.iface_bw_worker",
    "workers.mesh_worker",
    "workers.process_worker",
    "workers.report_scheduler_worker",
    "workers.rest_api_worker",
    "workers.scan_worker",
    "workers.service_worker",
    "workers.snmp_trap_worker",
    "workers.speed_test_worker",
    "workers.syslog_worker",
    "workers.threat_intel_worker",
    "workers.zte_worker",
]

for _pkg in ("scapy", "PyQt6", "matplotlib", "flask", "keyring"):
    _d, _b, _h = collect_all(_pkg)
    datas         += _d
    binaries      += _b
    hiddenimports += _h

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NetSentinel",
    debug=_debug_build,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=_debug_build,              # False in production, True for debug
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icons/NetSentinel.ico" if sys.platform == "win32" else None,
)

# macOS: wrap the binary in a .app bundle (only relevant on macOS)
if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821 — PyInstaller injects this name at build time
        exe,
        name="NetSentinel.app",
        icon="assets/icons/NetSentinel.ico",
        bundle_identifier="com.netsentinel.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
