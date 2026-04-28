"""
NetSentinel — entry point.

Network Security Scanner & Long-Term Connectivity Monitor.

Usage:
    python app.py

Or double-click the compiled executable.
"""

import sys
import os


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
        "ui.matrix_rain",
        "modules.mac_registry",
        "modules.name_resolver",
        "modules.network_benchmark",
        "modules.iot_baseline",
        "modules.root_cause_correlator",
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
    _check_python_version()
    _check_pyqt()

    # ── Crash hardening ───────────────────────────────────────────────────────
    # Enable C-level fault handler so segfaults / access violations write a
    # traceback to a log file instead of silently closing the app.
    import faulthandler
    _crash_log_path = os.path.join(
        os.path.dirname(getattr(sys, "executable", os.path.abspath(__file__))),
        "netsentinel_crash.log",
    )
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

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QIcon
    from PyQt6.QtCore import Qt

    # Enable high-DPI
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("NetSentinel")
    app.setApplicationVersion("1.3.1")
    app.setOrganizationName("netsentinel")

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

    from modules.metric_store import MetricStore
    from modules.alert_engine import AlertEngine
    from workers.availability_worker import AvailabilityWorker
    from workers.cert_worker import CertWorker
    from workers.service_worker import ServiceWorker as SvcWorker
    from workers.report_scheduler_worker import ReportSchedulerWorker
    from workers.snmp_trap_worker import SnmpTrapWorker
    from workers.syslog_worker import SyslogWorker

    store  = MetricStore()           # uses default portable path
    alerts = AlertEngine(store=store)

    from modules.notification_router import NotificationRouter
    notif_router = NotificationRouter()
    alerts.set_on_alert(notif_router.dispatch)

    from modules.maintenance_window import MaintenanceWindowManager
    maint_manager = MaintenanceWindowManager()
    alerts.set_maintenance_checker(maint_manager.is_suppressed)

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

    from ui.dashboard import Dashboard
    window = Dashboard(store=store, alert_engine=alerts, notif_router=notif_router,
                       maint_manager=maint_manager)
    window.show()

    # First-run onboarding dialog (shown once per install)
    from ui.first_run_dialog import FirstRunDialog, should_show_first_run
    if should_show_first_run():
        dlg = FirstRunDialog(parent=window)
        dlg.exec()

    # Wire notification router → toast callback + notifications page
    notif_router.set_toast_callback(window._show_alert_toast)
    window._notifications_page.set_router(notif_router)
    window._maintenance_page.set_manager(maint_manager)

    # Wire report worker → reports page
    report_worker.report_saved.connect(window._reports_page.on_report_saved)
    report_worker.error.connect(window._reports_page.on_worker_error)
    window._reports_page.set_worker(report_worker)

    # Wire SNMP trap worker → trap page
    snmp_trap_worker.trap_received.connect(window._snmp_trap_page.on_trap_received)
    snmp_trap_worker.status.connect(window._snmp_trap_page.on_status)
    snmp_trap_worker.error.connect(window._snmp_trap_page.on_error)

    # Wire syslog worker → syslog page
    syslog_worker.message_received.connect(window._syslog_page.on_message_received)
    syslog_worker.status.connect(window._syslog_page.on_status)
    syslog_worker.error.connect(window._syslog_page.on_error)

    # Wire worker signal → history + inventory + uptime pages
    avail_worker.cycle_done.connect(window._history_page.on_cycle_done)
    avail_worker.cycle_done.connect(window._inventory_page.on_cycle_done)
    avail_worker.cycle_done.connect(window._uptime_page.on_cycle_done)

    # Wire cert worker → cert page
    cert_worker.check_done.connect(window._cert_page.on_check_done)

    # Wire service worker → service page + alert engine
    svc_worker.check_done.connect(window._service_page.on_check_done)

    def _on_svc_check(results: list) -> None:
        fired = alerts.evaluate_service_checks(results)
        for a in fired:
            window._show_alert_toast(a)
        window._overview_page.on_svc_done(results)

    svc_worker.check_done.connect(_on_svc_check)

    # Wire cert alerts
    def _on_cert_check(results: list) -> None:
        fired = alerts.evaluate_cert_checks(results)
        for a in fired:
            window._show_alert_toast(a)
        window._overview_page.on_cert_done(results)

    cert_worker.check_done.connect(_on_cert_check)

    # Wire availability cycle → alert engine + overview page
    def _on_cycle(result_dict: dict) -> None:
        fired = alerts.evaluate_cycle(result_dict)
        for a in fired:
            window._show_alert_toast(a)
            window._overview_page.on_alert(a)
        window._overview_page.on_cycle_done(result_dict)

    avail_worker.cycle_done.connect(_on_cycle)

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
