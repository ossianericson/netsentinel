"""
NetSentinel — entry point.

Network Security Scanner & Long-Term Connectivity Monitor.

Usage:
    python app.py

Or double-click the compiled executable.
"""

import sys
import os

# ── Suppress CMD flashes in windowed exe ─────────────────────────────────────
# On Windows, scapy calls subprocess.Popen (for `route print`, `arp -a`, etc.)
# at import time WITHOUT CREATE_NO_WINDOW, causing brief CMD flashes.
# Patch Popen before any network library loads so all child processes are
# spawned hidden.  This only activates in a frozen (PyInstaller) windowed build
# where there is no console to attach to anyway.
if sys.platform == "win32" and getattr(sys, "frozen", False):
    import subprocess as _subprocess
    _OrigPopen = _subprocess.Popen
    _CNW = _subprocess.CREATE_NO_WINDOW

    class _SilentPopen(_OrigPopen):  # type: ignore[misc]
        def __init__(self, *args, **kwargs):
            # Only suppress the console window when the caller hasn't explicitly
            # set creationflags (e.g. Ookla CLI or other tools that manage their
            # own flags must not be overridden).
            if "creationflags" not in kwargs:
                kwargs["creationflags"] = _CNW
                si = kwargs.get("startupinfo") or _subprocess.STARTUPINFO()
                si.dwFlags |= _subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0  # SW_HIDE
                kwargs["startupinfo"] = si
            super().__init__(*args, **kwargs)

    _subprocess.Popen = _SilentPopen  # type: ignore[misc]


def _smoke_test() -> None:
    """
    Headless import check used by CI and the post-build exe verification step.

    Run with:  python app.py --smoke   (source)
               NetSentinel.exe --smoke (bundled)

    Exits 0 on success, 1 on the first import failure.
    No display or QApplication is needed.
    """
    _failed: list[str] = []
    _checks = [
        "PyQt6.QtWidgets",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtNetwork",
        "matplotlib.backends.backend_qtagg",
        "scapy.layers.all",
        "ui.styles",
        "ui.dashboard",
        "ui.live_graph",
        "modules.rogue_device",
        "modules.stp_detector",
        "modules.storm_analyser",
        "modules.port_scanner",
        "modules.dns_correlator",
        "modules.network_diagnostics",
        "modules.report_exporter",
        "modules.network_logger",
        "modules.wifi_scanner",
        "modules.arp_monitor",
        "modules.dhcp_detector",
        "modules.os_fingerprint",
        "modules.bandwidth_monitor",
        "modules.tls_checker",
        "modules.snmp_poller",
        "modules.scheduler",
        "ui.topology_widget",
        "modules.device_classifier",
        "modules.risk_scorer",
        "modules.syn_scanner",
        "modules.cve_lookup",
        "modules.credentialed_scan",
        "modules.combined_discovery",
        "modules.smb_enumerator",
        "modules.plugin_system",
        "modules.private_endpoint_checker",
        "modules.cloud_metadata",
        "modules.log_chart",
        "modules.mac_registry",
        "modules.name_resolver",
        "modules.network_benchmark",
        "modules.iot_baseline",
        "modules.root_cause_correlator",
        "modules.speed_tester",
        "modules.alert_engine",
        "modules.notification_router",
        "modules.utils",
        "modules.maintenance_window",
        "modules.snmp_trap_receiver",
        "modules.syslog_receiver",
        "modules.trend_analyser",
        "modules.rest_api",
        "modules.ha_detector",
        "modules.internet_exposure",
        "modules.dns_zone_scanner",
        "modules.dhcp_lease_scanner",
        "modules.colours",
        "ui.command_palette",
        "ui.empty_state",
        "ui.expanding_table",
        "modules.threat_intel",
        "modules.cert_monitor",
        "modules.availability_monitor",
        "workers.scan_worker",
        "workers.speed_test_worker",
        "workers.availability_worker",
        "workers.cert_worker",
        "workers.threat_intel_worker",
        "ui.pages.diagnosis_page",
        "workers.diagnosis_worker",
        "modules.metric_store",
        "modules.lab_scenarios",
        "modules.diagnostic_card",
        "workers.service_worker",
        "workers.report_scheduler_worker",
        "workers.snmp_trap_worker",
        "workers.syslog_worker",
        "workers.rest_api_worker",
        "ui.first_run_dialog",
        "ui.pages.home_page",
        "ui.pages.overview_page",
        "ui.pages.history_page",
        "ui.pages.inventory_page",
        "ui.pages.uptime_page",
        "ui.pages.cert_page",
        "ui.pages.service_page",
        "ui.pages.reports_page",
        "ui.pages.snmp_trap_page",
        "ui.pages.syslog_page",
        "ui.pages.threat_intel_page",
        "ui.pages.geo_map_page",
        "ui.pages.network_doc_page",
        "ui.pages.notifications_page",
        "ui.pages.maintenance_page",
        "ui.pages.lab_mode_page",
        "ui.pages.mqtt_page",
        "ui.pages.speed_test_page",
        "ui.pages.connections_page",
        "ui.pages.cve_page",
        "ui.pages.dns_zone_page",
        "ui.pages.dhcp_lease_page",
        "ui.pages.ookla_cli_banner",
        "ui.pages.live_bandwidth_page",
        "ui.pages.wifi_heatmap_page",
        "ui.pages.home_automation_page",
        "ui.pages.trigger_builder_page",
        "ui.pages.ip_calculator_page",
        "ui.pages.baseline_page",
        "ui.pages.automation_page",
        "ui.pages.settings_page",
        "ui.pages.timeline_page",
        "modules.digest_builder",
        "ui.pages.trend_page",
        "ui.skeleton",
        "modules.colours",
        "modules.deco_client",
        "modules.wifi_heatmap",
        "ui.pages.hardware_integration_page",
        "ui.pages.wifi_monitor_page",
        "workers.wifi_monitor_worker",
    ]
    for _mod in _checks:
        try:
            __import__(_mod)
        except Exception as _exc:  # noqa: BLE001
            _failed.append(f"  FAIL  {_mod}: {_exc}")

    if _failed:
        print("smoke-test FAILED:\n" + "\n".join(_failed), file=sys.stderr)
        sys.exit(1)

    print("smoke-test OK")
    sys.exit(0)


def _headless() -> None:
    """
    Headless / CLI mode.  No display or QApplication required.

    Usage:
        python app.py --headless [--output report.html] [--cidr 192.168.1.0/24]

    Runs Module 1 (device fingerprint) + optional CIDR scan, then writes an
    HTML report.  Exit code 0 = success, 1 = error.
    """
    import argparse
    parser = argparse.ArgumentParser(
        prog="NetSentinel",
        description="Headless device scan — no GUI required.",
    )
    parser.add_argument("--output", default="netsentinel_report.html",
                        help="Output HTML report path (default: netsentinel_report.html)")
    parser.add_argument("--cidr", default=None,
                        help="CIDR range to scan (e.g. 192.168.1.0/24). Defaults to local /24.")
    args, _ = parser.parse_known_args()

    print("NetSentinel — headless scan")
    print(f"Output: {args.output}")

    try:
        from modules.utils import (
            get_offenders_path, flush_network_caches, get_local_ip,
            ping_sweep_subnet, ping_sweep_cidr,
        )
        from modules.rogue_device import scan as m1_scan
        from modules.report_exporter import generate_html

        print("[1/4] Flushing caches…")
        flush_network_caches()

        if args.cidr:
            print(f"[2/4] CIDR sweep: {args.cidr}…")
            ping_sweep_cidr(args.cidr, progress_cb=print)
        else:
            print("[2/4] Subnet sweep…")
            local_ip = get_local_ip()
            ping_sweep_subnet(local_ip, progress_cb=print)

        print("[3/4] Fingerprinting devices…")
        path = get_offenders_path()
        data = m1_scan(path)
        devices = data.get("devices", [])
        print(f"      {len(devices)} device(s) found, "
              f"{data.get('high_risk_count', 0)} HIGH RISK")

        print("[4/4] Writing report…")
        html = generate_html(module1_data=data)
        output_path = os.path.abspath(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Report saved: {output_path}")
        sys.exit(0)

    except Exception as exc:
        import traceback
        print(f"ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


def _fatal(title: str, message: str) -> None:
    """Show an error in a way that is visible even when --windowed hides the console."""
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        _app = QApplication.instance() or QApplication(sys.argv)
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.exec()
    except Exception:
        # Last resort: write to a log file next to the exe
        import traceback
        import tempfile
        log_path = os.path.join(os.path.dirname(sys.executable), "netsentinel_error.log")
        try:
            from modules.utils import get_app_data_dir
            log_path = os.path.join(get_app_data_dir(), "netsentinel_error.log")
        except Exception:
            pass
        try:
            with open(log_path, "w") as f:
                f.write(f"{title}\n{message}\n\n")
                traceback.print_exc(file=f)
        except OSError:
            pass
    sys.exit(1)


def _check_python_version():
    if sys.version_info < (3, 9):
        _fatal(
            "Python version error",
            f"Python 3.9 or later is required.\nYou are running Python {sys.version}",
        )


def _check_pyqt():
    try:
        import PyQt6  # noqa: F401
    except ImportError:
        _fatal(
            "Missing dependency",
            "PyQt6 is not installed.\nRun:  pip install -r requirements.txt",
        )


def main():
    # Guard sys.stderr/stdout being None in windowed PyInstaller builds
    if sys.stderr is None:
        try:
            from modules.utils import get_app_data_dir as _get_app_dir
            sys.stderr = open(str(_get_app_dir() / "netsentinel_stderr.log"), "a")  # noqa: SIM115
        except Exception:
            import io as _io
            sys.stderr = _io.StringIO()
    if sys.stdout is None:
        import io as _io
        sys.stdout = _io.StringIO()

    _check_python_version()
    _check_pyqt()

    # ── Crash hardening ───────────────────────────────────────────────────────
    # Enable C-level fault handler so segfaults / access violations write a
    # traceback to a log file instead of silently closing the app.
    import faulthandler
    # Write crash log to per-user AppData to avoid PermissionError in Program Files
    try:
        from modules.utils import get_app_data_dir as _get_app_dir
        _crash_log_path = str(_get_app_dir() / "netsentinel_crash.log")
    except Exception:
        import tempfile
        _crash_log_path = os.path.join(tempfile.gettempdir(), "netsentinel_crash.log")
    try:
        _crash_log_fd = open(_crash_log_path, "a")  # noqa: SIM115
        faulthandler.enable(file=_crash_log_fd)
    except Exception:
        faulthandler.enable()  # fallback: write to stderr

    # Catch unhandled Python exceptions and show them instead of silent exit.
    def _excepthook(exc_type, exc_value, exc_tb):
        import traceback as _tb
        _fatal("Unhandled Error", "".join(_tb.format_exception(exc_type, exc_value, exc_tb)))

    sys.excepthook = _excepthook
    # ─────────────────────────────────────────────────────────────────────────

    from PyQt6.QtWidgets import QApplication, QSplashScreen
    from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
    from PyQt6.QtCore import Qt, QSettings, qInstallMessageHandler, QRect

    # Suppress noisy Qt warnings that come from matplotlib's QtAgg backend
    # measuring fonts with pixel-size QFont objects (pointSize() returns -1).
    def _qt_message_handler(msg_type, context, message):
        if "Point size <= 0" in message:
            return  # matplotlib font-metrics noise — safe to ignore
        # In windowed/frozen builds sys.stderr is None — guard before writing
        import sys as _sys
        if _sys.stderr is not None:
            _sys.stderr.write(message + "\n")
    qInstallMessageHandler(_qt_message_handler)

    # Enable high-DPI
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    # Tell Windows to use NetSentinel's icon in the taskbar instead of Python's.
    # Must be called before QApplication is created.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "netsentinel.netsentinel.1"
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("NetSentinel")
    app.setApplicationVersion("1.9.63")

    _start_minimised = "--minimised" in sys.argv

    # ── Splash screen ─────────────────────────────────────────────────────────
    # PERF-1: splash screen with progress messages.
    # 800×500 canvas with the 480×280 design centred inside it — covers the
    # area around the content card so small amounts of background bleed are hidden.
    from ui.styles import (  # noqa: E402
        SPLASH_BG, SPLASH_TITLE_FG, SPLASH_SUBTITLE_FG,
        SPLASH_VERSION_FG, SPLASH_MSG_FG,
    )
    _SPLASH_W, _SPLASH_H = 480, 280          # logical size of the centred card
    _CANVAS_W, _CANVAS_H = 800, 500         # outer canvas (covers extra area)
    _SOX = (_CANVAS_W - _SPLASH_W) // 2     # card x-offset on the canvas
    _SOY = (_CANVAS_H - _SPLASH_H) // 2     # card y-offset on the canvas

    _splash_base = QPixmap(_CANVAS_W, _CANVAS_H)
    _splash_base.fill(QColor(SPLASH_BG))
    _spp = QPainter(_splash_base)
    _spp.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    # Title
    _spp.setPen(QColor(SPLASH_TITLE_FG))
    _spp.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
    _spp.drawText(QRect(_SOX, _SOY + 60, _SPLASH_W, 55), Qt.AlignmentFlag.AlignCenter, "NetSentinel")
    # Subtitle
    _spp.setPen(QColor(SPLASH_SUBTITLE_FG))
    _spp.setFont(QFont("Segoe UI", 11))
    _spp.drawText(QRect(_SOX, _SOY + 120, _SPLASH_W, 30), Qt.AlignmentFlag.AlignCenter,
                  "Network Security Scanner")
    # Version
    _spp.setPen(QColor(SPLASH_VERSION_FG))
    _spp.setFont(QFont("Segoe UI", 9))
    _spp.drawText(QRect(_SOX, _SOY + 250, _SPLASH_W, 22), Qt.AlignmentFlag.AlignCenter, "v1.9.63")
    _spp.end()

    _splash = QSplashScreen(_splash_base, Qt.WindowType.WindowStaysOnTopHint)
    if not _start_minimised:
        _splash.show()
        app.processEvents()

    def _splash_msg(msg: str, process_events: bool = True) -> None:
        """Overlay a progress message on the splash without redrawing the base."""
        _px = _splash_base.copy()
        _p = QPainter(_px)
        _p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        # Clear previous message area (positioned relative to the centred card)
        _p.fillRect(QRect(_SOX, _SOY + 175, _SPLASH_W, 28), QColor(SPLASH_BG))
        _p.setPen(QColor(SPLASH_MSG_FG))
        _p.setFont(QFont("Segoe UI", 9))
        _p.drawText(QRect(_SOX, _SOY + 177, _SPLASH_W, 24), Qt.AlignmentFlag.AlignCenter, msg)
        _p.end()
        _splash.setPixmap(_px)
        if process_events:
            app.processEvents()
    # ─────────────────────────────────────────────────────────────────────────
    app.setOrganizationName("netsentinel")

    # Apply QMenu rules at application level so top-level (parentless) menus
    # are styled — widget-level stylesheets do not reach separate top-level windows.
    from ui.styles import BG_CARD, TEXT_PRIMARY, BORDER, BG_HOVER, WHITE
    from ui.styles import TOOLTIP_BG, TOOLTIP_BORDER
    app.setStyleSheet(
        f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
        f" border:1px solid {BORDER}; padding:4px; font-size:12px; }}"
        f"QMenu::item {{ padding:4px 16px; color:{TEXT_PRIMARY}; background:{BG_CARD}; }}"
        f"QMenu::item:selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        # QToolTip is a top-level window — must be set at app level to take effect
        f"QToolTip {{ background:{TOOLTIP_BG}; color:{WHITE};"
        f" border:1px solid {TOOLTIP_BORDER}; border-radius:3px; padding:4px 8px;"
        f" font-size:11px; }}"
    )

    # ── Single instance guard ─────────────────────────────────────────────────
    # If another instance is running, signal it to restore its window and exit.
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    _INSTANCE_KEY = "NetSentinel_SingleInstance_v1"
    _probe = QLocalSocket()
    _probe.connectToServer(_INSTANCE_KEY)
    if _probe.waitForConnected(500):
        # Another instance is alive — tell it to come to the front and exit.
        _probe.write(b"SHOW")
        _probe.flush()
        _probe.waitForBytesWritten(500)
        _probe.disconnectFromServer()
        _probe = None
        sys.exit(0)
    # No running instance found; clean up the probe and take ownership of the key.
    _probe.abort()
    del _probe
    _instance_server = QLocalServer()
    # Remove any stale socket left by a prior crash (no-op on Windows).
    # Only called after the probe confirmed no live server is behind the name.
    QLocalServer.removeServer(_INSTANCE_KEY)
    if not _instance_server.listen(_INSTANCE_KEY):
        # Fallback: if listen fails, run without instance guard rather than crashing.
        _instance_server = None
    # ─────────────────────────────────────────────────────────────────────────

    # App icon (bundled as icon.ico / icon.png if present)
    from pathlib import Path
    import sys as _sys
    if getattr(_sys, "frozen", False):
        base = Path(_sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent

    for ico in (
        "NetSentinel.ico",
        "assets/icons/NetSentinel.ico",
        "icon.ico",
        "icon.png",
    ):
        ico_path = base / ico
        if ico_path.exists():
            app.setWindowIcon(QIcon(str(ico_path)))
            break

    _splash_msg("Initialising database…")
    from modules.metric_store import MetricStore
    from modules.alert_engine import AlertEngine
    from workers.availability_worker import AvailabilityWorker
    from workers.cert_worker import CertWorker
    from workers.service_worker import ServiceWorker as SvcWorker
    from workers.report_scheduler_worker import ReportSchedulerWorker
    from workers.snmp_trap_worker import SnmpTrapWorker
    from workers.syslog_worker import SyslogWorker
    from workers.rest_api_worker import RestApiWorker

    store  = MetricStore()           # uses default portable path
    alerts = AlertEngine(store=store)
    alerts.set_warmup_period(10)     # suppress boot-time alert noise for 10 s

    # Restore user-configured rule enabled states from QSettings.
    # All rules default to disabled (opt-in); missing key → treat as disabled.
    from modules.alert_engine import rule_settings_key as _rk
    _rule_qs = QSettings("NetSentinel", "NetSentinel")
    _rules = alerts.get_rules()
    for _r in _rules:
        _r.enabled = _rule_qs.value(_rk(_r.name), False, type=bool)
    alerts.set_rules(_rules)

    from modules.notification_router import NotificationRouter
    notif_router = NotificationRouter()
    alerts.set_on_alert(notif_router.dispatch)

    from modules.maintenance_window import MaintenanceWindowManager
    maint_manager = MaintenanceWindowManager()
    alerts.set_maintenance_checker(maint_manager.is_suppressed)

    _splash_msg("Starting background workers…")
    avail_worker = AvailabilityWorker(store=store, interval_s=60)
    avail_worker.start()

    cert_worker = CertWorker(store=store, interval_s=3600)
    cert_worker.start()

    svc_worker = SvcWorker(store=store, interval_s=60)
    svc_worker.start()

    report_worker = ReportSchedulerWorker(store=store)
    report_worker.start()

    snmp_trap_worker = SnmpTrapWorker()
    snmp_trap_worker.start()

    syslog_worker = SyslogWorker()
    syslog_worker.start()

    # REST API worker — only starts when user has enabled it in Settings
    _qs = QSettings("NetSentinel", "NetSentinel")
    rest_api_worker: RestApiWorker | None = None
    if _qs.value("rest_api/enabled", False, type=bool):
        _port     = int(_qs.value("rest_api/port", 8765))
        _external = _qs.value("rest_api/external", False, type=bool)
        _host     = "0.0.0.0" if _external else "127.0.0.1"
        rest_api_worker = RestApiWorker(store=store)
        rest_api_worker.set_bind(_host, _port)
        rest_api_worker.error.connect(
            lambda msg: print(f"[REST API] ERROR: {msg}", flush=True)
        )
        from modules.rest_api import get_or_create_api_key as _ensure_key
        _ensure_key()  # generate and persist key on first enable
        rest_api_worker.start()

    _splash_msg("Loading interface…")
    from ui.dashboard import Dashboard
    window = Dashboard(store=store, alert_engine=alerts, notif_router=notif_router,
                       maint_manager=maint_manager)

    # Wire notification router → toast callback + notifications page
    notif_router.set_toast_callback(window._show_alert_toast)
    window._notifications_page.set_router(notif_router)
    window._notifications_page.set_alert_engine(alerts)
    window._maintenance_page.set_manager(maint_manager)

    # Wire report worker → reports page
    report_worker.report_saved.connect(window._reports_page.on_report_saved)
    report_worker.error.connect(window._reports_page.on_worker_error)
    window._reports_page.set_worker(report_worker)

    # Wire SNMP trap worker → trap page + log hub
    snmp_trap_worker.trap_received.connect(window._snmp_trap_page.on_trap_received)
    snmp_trap_worker.trap_received.connect(window._log_hub_page.on_snmp_trap)
    snmp_trap_worker.status.connect(window._snmp_trap_page.on_status)
    snmp_trap_worker.error.connect(window._snmp_trap_page.on_error)

    # Wire syslog worker → syslog page + log hub
    syslog_worker.message_received.connect(window._syslog_page.on_message_received)
    syslog_worker.message_received.connect(window._log_hub_page.on_syslog_message)
    syslog_worker.status.connect(window._syslog_page.on_status)
    syslog_worker.error.connect(window._syslog_page.on_error)

    # Wire worker signal → history + inventory + uptime + home pages
    avail_worker.cycle_done.connect(window._history_page.on_cycle_done)
    avail_worker.cycle_done.connect(window._inventory_page.on_cycle_done)
    avail_worker.cycle_done.connect(window._uptime_page.on_cycle_done)
    avail_worker.cycle_done.connect(window._home_page.on_cycle_done)

    # Wire cert worker → cert page; load persisted targets
    cert_worker.check_done.connect(window._cert_page.on_check_done)
    _cert_targets = window._cert_page._load_targets()
    if _cert_targets:
        from modules.cert_monitor import CertTarget as _CertTarget
        cert_worker.set_targets([_CertTarget(host=t["host"], ports=t.get("ports", [443])) for t in _cert_targets])
    window._cert_page.certs_changed.connect(cert_worker.set_targets)

    # Wire service worker → service page + alert engine; load persisted targets
    svc_worker.check_done.connect(window._service_page.on_check_done)
    _svc_targets = window._service_page._load_targets()
    if _svc_targets:
        from modules.service_monitor import ServiceTarget as _SvcTarget
        svc_worker.set_targets([_SvcTarget(t["host"], t["port"], t.get("label", "")) for t in _svc_targets])
    window._service_page.services_changed.connect(svc_worker.set_targets)

    def _on_svc_check(results: list) -> None:
        fired = alerts.evaluate_service_checks(results)
        for a in fired:
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
        window._overview_page.on_svc_done(results)  # delegates to ServiceStatusTile.update_services

    svc_worker.check_done.connect(_on_svc_check)

    # Wire cert alerts
    def _on_cert_check(results: list) -> None:
        fired = alerts.evaluate_cert_checks(results)
        for a in fired:
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
        window._overview_page.on_cert_done(results)

    cert_worker.check_done.connect(_on_cert_check)

    # Wire availability cycle → alert engine + overview page
    def _on_cycle(result_dict: dict) -> None:
        fired = alerts.evaluate_cycle(result_dict)
        for a in fired:
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            window._overview_page.on_alert(a)
        window._overview_page.on_cycle_done(result_dict)  # delegates to DeviceCountTile + RttSummaryTile

    avail_worker.cycle_done.connect(_on_cycle)

    # Wire threat intel page → geo map threat overlay
    window._threat_intel_page.entries_updated.connect(
        window._geo_map_page.set_threat_entries
    )

    # Wire empty-state CTAs → full scan
    window._network_doc_page.scan_requested.connect(window._start_full_scan)
    window._history_page.scan_requested.connect(window._start_full_scan)
    window._uptime_page.scan_requested.connect(window._start_full_scan)
    window._inventory_page.scan_requested.connect(window._start_full_scan)

    # ── Show window / close splash ────────────────────────────────────────────
    if not _start_minimised:
        _splash_msg("Ready.", process_events=False)
        if not window.isVisible():
            # Non-maximized path: window was not shown during _restore_settings().
            window.show()
        # _splash.close() fires the Qt event loop which delivers the first WM_PAINT
        # to the main window and hides the splash in the same DWM compositing frame.
        _splash.close()
        # Fix restore geometry: showMaximized() in _restore_settings() used Qt's
        # default HWND position; apply the saved normal geometry via SetWindowPlacement
        # so showNormal() restores to the correct location.
        _png = getattr(window, '_pending_normal_geo', None)
        if _png and sys.platform == "win32":
            _nx, _ny, _nw, _nh = _png
            from PyQt6.QtCore import QTimer as _QTimer
            def _fix_geo(_nx=_nx, _ny=_ny, _nw=_nw, _nh=_nh):
                try:
                    import ctypes as _ct
                    class _P(_ct.Structure):
                        _fields_ = [("x", _ct.c_long), ("y", _ct.c_long)]
                    class _R(_ct.Structure):
                        _fields_ = [("l", _ct.c_long), ("t", _ct.c_long),
                                    ("r", _ct.c_long), ("b", _ct.c_long)]
                    class _WP(_ct.Structure):
                        _fields_ = [("length", _ct.c_uint), ("flags", _ct.c_uint),
                                    ("showCmd", _ct.c_uint), ("ptMin", _P),
                                    ("ptMax", _P), ("rcNormal", _R)]
                    wp = _WP()
                    wp.length = _ct.sizeof(_WP)
                    _hwnd = int(window.winId())
                    _ct.windll.user32.GetWindowPlacement(_hwnd, _ct.byref(wp))
                    wp.rcNormal.l = _nx; wp.rcNormal.t = _ny
                    wp.rcNormal.r = _nx + _nw; wp.rcNormal.b = _ny + _nh
                    _ct.windll.user32.SetWindowPlacement(_hwnd, _ct.byref(wp))
                except Exception:
                    pass
            _QTimer.singleShot(0, _fix_geo)
    else:
        _splash.close()

    # Windows logoff/shutdown — save state before the session ends.
    # commitDataRequest fires before WM_ENDSESSION; no unsafe MSG casting needed.
    def _on_commit_data(manager) -> None:
        window._save_window_state()
        manager.release()
    app.commitDataRequest.connect(_on_commit_data)

    # Second-instance → raise this window to the front
    def _on_second_instance() -> None:
        conn = _instance_server.nextPendingConnection()
        if conn:
            conn.waitForReadyRead(200)
        window.show()
        window.setWindowState(
            (window.windowState() & ~Qt.WindowState.WindowMinimized)
            | Qt.WindowState.WindowActive
        )
        window.raise_()
        window.activateWindow()

    if _instance_server is not None:
        _instance_server.newConnection.connect(_on_second_instance)

    # First-run welcome overlay is shown by Dashboard._show_welcome_overlay()
    # via a 600 ms deferred timer after the window is fully painted.

    ret = app.exec()
    avail_worker.stop()
    avail_worker.wait(5000)
    cert_worker.stop()
    cert_worker.wait(5000)
    svc_worker.stop()
    svc_worker.wait(5000)
    report_worker.stop()
    report_worker.wait(5000)
    snmp_trap_worker.stop()
    snmp_trap_worker.wait(5000)
    syslog_worker.stop()
    syslog_worker.wait(5000)
    if rest_api_worker is not None:
        rest_api_worker.stop()
        rest_api_worker.wait(3000)
    if _instance_server is not None:
        _instance_server.close()
    store.close()
    sys.exit(ret)


if __name__ == "__main__":
    # MUST be first: lets PyInstaller-frozen subprocesses started by
    # multiprocessing.Process re-enter the correct target function instead
    # of re-launching the GUI.
    import multiprocessing
    multiprocessing.freeze_support()

    if "--smoke" in sys.argv:
        _smoke_test()
    if "--headless" in sys.argv:
        _headless()
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        import traceback
        _fatal("Unexpected error", traceback.format_exc())


