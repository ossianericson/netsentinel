"""
NetSentinel — entry point.

Network Security Scanner & Long-Term Connectivity Monitor.

Usage:
    python app.py

Or double-click the compiled executable.
"""

import sys
import os
import time

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
        "modules.scan_status_md",
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
        "modules.speed_drop_detector",
        "modules.speed_tester",
        "modules.speed_tester_servers",
        "modules.firewall_rules",
        "modules.alert_engine",
        "modules.service_escalation",
        "modules.proactive_digest",
        "modules.digest_bullets",
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
        "workers.proactive_probe_worker",
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
        "modules.passive_observer",
        "workers.passive_observer_worker",
        "modules.lldp_scanner",
        "workers.lldp_worker",
        "modules.health_score",
        "workers.health_worker",
        "ui.widgets.health_status_card",
        "modules.scheduled_speed_test",
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
        log_path = os.path.join(os.path.dirname(sys.executable), "netsentinel_error.log")
        try:
            from modules.utils import get_app_data_dir
            log_path = os.path.join(get_app_data_dir(), "netsentinel_error.log")
        except Exception:
            pass  # fall back to exe-dir path if AppData is unavailable
        try:
            with open(log_path, "w") as f:
                f.write(f"{title}\n{message}\n\n")
                traceback.print_exc(file=f)
        except OSError:
            pass  # non-fatal — error already shown in the dialog
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


# ── Post-Dashboard wiring helpers ────────────────────────────────────────────

def _wire_logging(window, passive_observer_worker, snmp_trap_worker, syslog_worker):
    passive_observer_worker.observation_ready.connect(window._on_passive_observation)
    snmp_trap_worker.trap_received.connect(window._snmp_trap_page.on_trap_received)
    snmp_trap_worker.trap_received.connect(window._log_hub_page.on_snmp_trap)
    snmp_trap_worker.status.connect(window._snmp_trap_page.on_status)
    snmp_trap_worker.error.connect(window._snmp_trap_page.on_error)
    syslog_worker.message_received.connect(window._syslog_page.on_message_received)
    syslog_worker.message_received.connect(window._log_hub_page.on_syslog_message)
    syslog_worker.status.connect(window._syslog_page.on_status)
    syslog_worker.error.connect(window._syslog_page.on_error)
    window._log_hub_page.start_logger_requested.connect(window._log_hub_page.show_network_log)


def _wire_notifications(window, alerts, notif_router, maint_manager, report_worker):
    notif_router.set_toast_callback(window._show_alert_toast)
    window._notifications_page.set_router(notif_router)
    window._notifications_page.set_alert_engine(alerts)
    if hasattr(window, "_shared_alert_drawer"):
        window._shared_alert_drawer.set_router(notif_router)
    window._maintenance_page.set_manager(maint_manager)
    report_worker.report_saved.connect(window._reports_page.on_report_saved)
    report_worker.error.connect(window._reports_page.on_worker_error)
    window._reports_page.set_worker(report_worker)

    # Load persisted alert dependency trees and push them into the live engine
    from ui.pages.notif_dep_card import _load_deps as _load_alert_deps
    for _dep in _load_alert_deps():
        _parent   = _dep.get("parent", "")
        _children = _dep.get("children", [])
        if _parent and _children:
            alerts.set_dependency_map(_parent, _children)

    # Keep the live engine in sync when the user adds/removes dependencies in the UI
    window._notifications_page.notify_dep_changed.connect(
        lambda parent, children: alerts.set_dependency_map(parent, children)
    )


def _wire_monitoring(window, avail_worker, cert_worker, svc_worker, alerts, notif_router, store):
    avail_worker.cycle_done.connect(window._history_page.on_cycle_done)
    avail_worker.cycle_done.connect(window._inventory_page.on_cycle_done)
    avail_worker.cycle_done.connect(window._uptime_page.on_cycle_done)
    avail_worker.cycle_done.connect(window._home_page.on_cycle_done)

    cert_worker.check_done.connect(window._cert_page.on_check_done)
    _cert_targets = window._cert_page._load_targets()
    if _cert_targets:
        from modules.cert_monitor import CertTarget as _CertTarget
        cert_worker.set_targets([
            _CertTarget(host=t["host"], ports=t.get("ports", [443]), label=t.get("label", ""))
            for t in _cert_targets
        ])
    window._cert_page.certs_changed.connect(cert_worker.set_targets)

    svc_worker.check_done.connect(window._service_page.on_check_done)
    _svc_targets = window._service_page._load_targets()
    if _svc_targets:
        from modules.service_monitor import ServiceTarget as _SvcTarget
        svc_worker.set_targets([_SvcTarget(t["host"], t["port"], t.get("label", "")) for t in _svc_targets])
    window._service_page.services_changed.connect(svc_worker.set_targets)
    window._service_page.check_now_requested.connect(svc_worker.check_now)

    # ── Sprint 1: SERVICE_DOWN escalation ──────────────────────────────────────
    # The plain "unreachable" toast above fires immediately. When escalation is
    # enabled, run DiagnosticEngine classification in the background (via the
    # existing ServiceDiagnosticsWorker, RULE 4 — never block the main thread)
    # and dispatch a richer follow-up on the SAME rule_type=SERVICE_DOWN a few
    # seconds later, explaining *why* (filtered / local / real outage).
    import time as _time
    from PyQt6.QtCore import QSettings
    from modules.alert_types import AlertFired
    from modules.service_escalation import (
        ServiceEscalationTracker, layer_to_message, parse_service_key,
        to_alert_severity,
    )
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker

    _escalation_tracker = ServiceEscalationTracker()
    _escalation_workers: list = []  # keep QThread refs alive until they finish

    def _persist_alert(a) -> None:
        # Sprint 4: persist every fired alert so modules.digest_bullets has
        # overnight history to summarize — nothing wrote to alert_fired before
        # this sprint, so get_recent_alerts()-backed digest bullets would
        # otherwise always report "nothing happened" in the live app.
        try:
            store.record_alert_fired(a.rule_name, a.host, a.severity, a.message, ts=a.ts)
        except Exception:
            pass  # non-fatal — persistence failure must not block notification delivery

    def _escalation_enabled() -> bool:
        return QSettings("NetSentinel", "NetSentinel").value(
            "notif/service_escalation_enabled", True, type=bool
        )

    def _run_service_escalation(alert) -> None:
        host, port = parse_service_key(alert.host)
        if not host or not _escalation_tracker.should_escalate(host, port):
            return
        _escalation_tracker.mark_escalated(host, port)

        worker = ServiceDiagnosticsWorker(custom_host=host)

        def _cleanup() -> None:
            if worker in _escalation_workers:
                _escalation_workers.remove(worker)
            worker.deleteLater()

        def _on_result(result, _rule_name=alert.rule_name, _key=alert.host) -> None:
            ui_severity, message = layer_to_message(result.failure_layer, host, port)
            escalation = AlertFired(
                rule_name=_rule_name,
                rule_type="SERVICE_DOWN",
                host=_key,
                message=message,
                severity=to_alert_severity(ui_severity),
                ts=int(_time.time()),
                cta_page="Service Diagnostics",
                cta_filter=host,
            )
            notif_router.dispatch(escalation)  # dispatch() already invokes the toast callback
            window._home_page.on_alert(escalation)
            _persist_alert(escalation)
            _cleanup()

        def _on_error(_msg: str) -> None:
            _cleanup()  # non-fatal — the plain SERVICE_DOWN toast already fired

        worker.result_ready.connect(_on_result)
        worker.error.connect(_on_error)
        _escalation_workers.append(worker)
        worker.start()

    def _on_svc_check(results: list) -> None:
        fired = alerts.evaluate_service_checks(results)
        for a in fired:
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            _persist_alert(a)
            if a.rule_type == "SERVICE_DOWN" and not a.is_resolution and _escalation_enabled():
                _run_service_escalation(a)
        window._overview_page.on_svc_done(results)

    svc_worker.check_done.connect(_on_svc_check)

    def _on_cert_check(results: list) -> None:
        fired = alerts.evaluate_cert_checks(results)
        for a in fired:
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            _persist_alert(a)
        window._overview_page.on_cert_done(results)

    cert_worker.check_done.connect(_on_cert_check)

    # V6 Sprint 2 — RTT_ANOMALY: per-host mean+2sigma baseline, refreshed hourly
    # (7-day history queries per host are too costly to redo every cycle).
    from modules.alert_baseline import BaselineLearner
    from PyQt6.QtCore import QTimer as _QTimer

    _baseline_learner = BaselineLearner()

    def _refresh_baselines() -> None:
        try:
            _baseline_learner.refresh(store)
        except Exception:
            pass  # non-fatal — anomaly checks just skip hosts with no baseline yet

    _refresh_baselines()
    _baseline_timer = _QTimer(window)
    _baseline_timer.setInterval(3600_000)
    _baseline_timer.timeout.connect(_refresh_baselines)
    _baseline_timer.start()

    def _on_cycle(result_dict: dict) -> None:
        fired = alerts.evaluate_cycle(result_dict)

        # V6 Sprint 1 — JITTER_HIGH: sustained jitter over the last 10 min per host.
        jitter_by_host: dict = {}
        for host in result_dict.get("states", {}):
            try:
                pts = store.query_rtt_history(host, hours=10.0 / 60.0)
            except Exception:
                pts = []
            vals = [p.jitter_ms for p in pts if p.jitter_ms is not None and p.jitter_ms >= 0]
            if vals:
                jitter_by_host[host] = vals
        fired += alerts.evaluate_jitter_checks(jitter_by_host)

        # V6 Sprint 2 — RTT_ANOMALY: per-host baseline, gated on Baseline.is_mature.
        rtts_by_host = {h: r for h, r in result_dict.get("rtts", {}).items() if r >= 0}
        fired += alerts.evaluate_rtt_anomaly_checks(rtts_by_host, _baseline_learner)

        for a in fired:
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            window._overview_page.on_alert(a)
            _persist_alert(a)
        window._overview_page.on_cycle_done(result_dict)

    avail_worker.cycle_done.connect(_on_cycle)


def _wire_speedtest_scheduling(window, worker, alerts, store):
    """
    Sprint 3 — scheduled speed test.  ``worker`` is a ProactiveProbeWorker
    running modules.scheduled_speed_test.run_scheduled_speed_test().  Each
    completed probe is evaluated against the BASELINE_DROP rule; a fired
    alert flows through the same window._show_alert_toast() +
    window._home_page.on_alert() path every other evaluate_* caller uses
    (see the pre-existing double-toast note in _wire_monitoring — left
    alone here for the same reason: not this sprint's concern).

    Sprint 4: also persists via store.record_alert_fired() so
    modules.digest_bullets._speed_trend_bullet() has overnight BASELINE_DROP
    history to summarize in the Morning Briefing.
    """
    def _on_probe_done(result) -> None:
        fired = alerts.evaluate_baseline_metrics(
            result.download_mbps, result.prior_downloads,
            current_sinr=result.current_sinr, prior_sinr=result.prior_sinr,
        )
        for a in fired:
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            try:
                store.record_alert_fired(a.rule_name, a.host, a.severity, a.message, ts=a.ts)
            except Exception:
                pass  # non-fatal — persistence failure must not block notification delivery

    def _on_probe_error(_msg: str) -> None:
        pass  # non-fatal — the worker retries automatically on its next interval

    worker.probe_done.connect(_on_probe_done)
    worker.error.connect(_on_probe_error)

    def _on_auto_speedtest_changed(enabled: bool, interval_hours: int) -> None:
        worker.set_interval(interval_hours * 3600)
        if enabled and not worker.isRunning():
            worker.start()
        elif not enabled and worker.isRunning():
            worker.stop()
            worker.wait(3000)

    window._speed_test_page.auto_speedtest_changed.connect(_on_auto_speedtest_changed)


def _wire_port_sweep(window, worker, alerts, store, cert_worker):
    """V6 Sprint 3.1/3.3/3.5 — nightly port-scan sweep of known devices,
    diffed against the prior sweep for NEW_OPEN_PORT alerts.  Also drives
    3.3 auto-TLS enrolment (hosts with 443/8443 open feed the Cert page)
    and 3.5 scan-registry freshness (reuses the "Port Scan (TCP)" label
    already shown on the Security Overview Scan Status card)."""
    def _on_probe_done(report) -> None:
        for a in alerts.evaluate_port_sweep_checks(report):
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            try:
                store.record_alert_fired(a.rule_name, a.host, a.severity, a.message, ts=a.ts)
            except Exception:
                pass  # non-fatal — persistence failure must not block notification delivery
        try:
            from modules.cert_auto_enroll import auto_enroll_from_sweep
            window._cert_page.merge_auto_targets(
                auto_enroll_from_sweep(report.all_devices, cert_worker.get_targets())
            )
        except Exception:
            pass  # non-fatal — auto-enrolment failure must not block the sweep's own alerts
        window._nav_set_scan_state(
            "Port Scan (TCP)", "fresh", ts=time.time(),
            verdict=f"{len(report.new_ports)} new open port(s) across {len(report.all_devices)} device(s)",
        )

    def _on_probe_error(msg: str) -> None:
        window._nav_set_scan_state("Port Scan (TCP)", "error", error=msg)

    worker.probe_done.connect(_on_probe_done)
    worker.error.connect(_on_probe_error)


def _wire_cve_recheck(window, worker, alerts, store):
    """V6 Sprint 3.2/3.5 — scheduled CVE re-check for already-fingerprinted
    services, diffed against cve_lifecycle for NEW_CVE alerts."""
    def _on_probe_done(report) -> None:
        for a in alerts.evaluate_cve_recheck_checks(report):
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            try:
                store.record_alert_fired(a.rule_name, a.host, a.severity, a.message, ts=a.ts)
            except Exception:
                pass  # non-fatal — persistence failure must not block notification delivery
        window._nav_set_scan_state(
            "CVE Lookup", "fresh", ts=time.time(),
            verdict=f"{len(report.new_cves)} new CVE(s) found",
        )

    def _on_probe_error(msg: str) -> None:
        window._nav_set_scan_state("CVE Lookup", "error", error=msg)

    worker.probe_done.connect(_on_probe_done)
    worker.error.connect(_on_probe_error)


def _wire_exposure_watch(window, worker, alerts, store):
    """V6 Sprint 3.4/3.5 — weekly internet-exposure check, diffed against the
    prior week's snapshot for NEW_EXPOSURE alerts."""
    def _on_probe_done(report) -> None:
        for a in alerts.evaluate_exposure_checks(report):
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            try:
                store.record_alert_fired(a.rule_name, a.host, a.severity, a.message, ts=a.ts)
            except Exception:
                pass  # non-fatal — persistence failure must not block notification delivery
        window._nav_set_scan_state(
            "Exposed to Internet", "fresh", ts=time.time(),
            verdict=f"{len(report.new_exposed)} newly exposed port(s)",
        )

    def _on_probe_error(msg: str) -> None:
        window._nav_set_scan_state("Exposed to Internet", "error", error=msg)

    worker.probe_done.connect(_on_probe_done)
    worker.error.connect(_on_probe_error)


def _wire_arp_watch(window, worker, alerts, store):
    """V6 Sprint 4.1 — background ARP spoof watch. ``worker`` is a
    ProactiveProbeWorker running modules.arp_watch.run_arp_watch_cycle() on a
    fixed interval, independent of whether the ARP Spoof Watch page is open."""
    from ui.styles import GREEN, RED

    def _on_probe_done(report) -> None:
        for a in alerts.evaluate_arp_watch_checks(report):
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            try:
                store.record_alert_fired(a.rule_name, a.host, a.severity, a.message, ts=a.ts)
            except Exception:
                pass  # non-fatal — persistence failure must not block notification delivery
        window._set_flyout_dot("ARP Spoof Watch", RED if report.events else GREEN)

    def _on_probe_error(msg: str) -> None:
        window._set_flyout_dot("ARP Spoof Watch", "")

    worker.probe_done.connect(_on_probe_done)
    worker.error.connect(_on_probe_error)


def _wire_dhcp_watch(window, worker, alerts, store):
    """V6 Sprint 4.2 — background rogue DHCP watch. ``worker`` is a
    ProactiveProbeWorker running modules.dhcp_watch.run_dhcp_watch_cycle() on
    a fixed interval, independent of whether the DHCP Rogue Monitor page is
    open."""
    from ui.styles import GREEN, RED

    def _on_probe_done(report) -> None:
        for a in alerts.evaluate_dhcp_watch_checks(report):
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            try:
                store.record_alert_fired(a.rule_name, a.host, a.severity, a.message, ts=a.ts)
            except Exception:
                pass  # non-fatal — persistence failure must not block notification delivery
        window._set_flyout_dot("DHCP Rogue Monitor", RED if report.rogue_offers else GREEN)

    def _on_probe_error(msg: str) -> None:
        window._set_flyout_dot("DHCP Rogue Monitor", "")

    worker.probe_done.connect(_on_probe_done)
    worker.error.connect(_on_probe_error)


def _wire_trend_forecast(window, worker, alerts, store):
    """V6 Sprint 2 — TREND_FORECAST.  ``worker`` is a ProactiveProbeWorker
    running modules.trend_analyser.run_full_trend_report() hourly.  Each
    completed report is evaluated against the TREND_FORECAST rule; fired
    early-warning alerts flow through the same toast/home-page/persist path
    every other evaluate_* caller uses."""
    def _on_probe_done(report) -> None:
        for a in alerts.evaluate_trend_checks(report):
            window._show_alert_toast(a)
            window._home_page.on_alert(a)
            try:
                store.record_alert_fired(a.rule_name, a.host, a.severity, a.message, ts=a.ts)
            except Exception:
                pass  # non-fatal — persistence failure must not block notification delivery

    def _on_probe_error(_msg: str) -> None:
        pass  # non-fatal — the worker retries automatically on its next interval

    worker.probe_done.connect(_on_probe_done)
    worker.error.connect(_on_probe_error)


def _wire_cross_page(window):
    window._threat_intel_page.entries_updated.connect(window._geo_map_page.set_threat_entries)
    # ThreatIntelPage loads its local cache synchronously in __init__, which runs
    # (and fires entries_updated) before this connection exists — seed the map
    # once with whatever it already loaded so startup data isn't silently dropped.
    if window._threat_intel_page._threat_entries:
        window._geo_map_page.set_threat_entries(window._threat_intel_page._threat_entries)
    window._hardware_integration_page.plugin_page_added.connect(window._home_page.on_hardware_added)
    window._home_page._freshness_strip.navigate_to.connect(window._nav_rail_go_to)

    def _on_cert_scan_complete() -> None:
        if getattr(window, "_pending_security_tools", []):
            window._advance_security_audit()
        window._nav_set_scan_state("TLS & Exposure", "fresh")

    def _on_threat_intel_scan_complete() -> None:
        if getattr(window, "_pending_security_tools", []):
            window._advance_security_audit()
        window._nav_set_scan_state("Threat Intel", "fresh")

    window._cert_page.scan_complete.connect(_on_cert_scan_complete)
    window._threat_intel_page.scan_complete.connect(_on_threat_intel_scan_complete)
    window._service_diagnostics_page.scan_started.connect(
        lambda: window._nav_set_scan_state("Service Diagnostics", "running")
    )
    window._service_diagnostics_page.scan_complete.connect(
        lambda: window._nav_set_scan_state("Service Diagnostics", "fresh")
    )


def _wire_scan_ctas(window):
    window._network_doc_page.scan_requested.connect(window._start_full_scan)
    window._history_page.scan_requested.connect(window._start_full_scan)
    window._uptime_page.scan_requested.connect(window._start_full_scan)
    window._inventory_page.scan_requested.connect(window._start_full_scan)
    window._ha_page.scan_requested.connect(window._start_full_scan)
    window._cert_page.scan_requested.connect(window._start_full_scan)
    window._service_page.scan_requested.connect(window._start_full_scan)
    window._speed_test_page.scan_requested.connect(window._start_full_scan)
    window._lab_mode_page.scan_requested.connect(window._start_full_scan)
    window._speed_test_page.speed_drop_detected.connect(window._on_speed_drop_detected)

    def _on_explore_protocol(proto_key: str) -> None:
        window._nav_rail_go_to("Protocol Visualizer")
        window._protocol_viz_page.select_protocol(proto_key)

    window._lab_mode_page.explore_protocol.connect(_on_explore_protocol)
    window._trigger_page.scan_requested.connect(window._start_full_scan)
    window._diagnosis_page.scan_requested.connect(window._start_full_scan)
    window._cve_page.scan_requested.connect(window._start_full_scan)
    window._geo_map_page.scan_requested.connect(window._start_full_scan)
    window._timeline_page.scan_requested.connect(window._start_full_scan)
    window._trend_page.scan_requested.connect(window._start_full_scan)


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

    # Suppress non-fatal matplotlib "Tight layout not applied" UserWarning that
    # fires when a chart widget is too small to fit axis decorations. This is a
    # rendering heuristic failure, not a data problem — the chart still draws.
    import warnings as _warnings
    _warnings.filterwarnings(
        "ignore", "Tight layout not applied", UserWarning, "matplotlib"
    )

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

    # Catch unhandled Python exceptions (including PyQt6 slot exceptions) and
    # write them to the crash log so they are never silently swallowed when
    # the user runs the app without a console (shortcut / frozen exe).
    def _excepthook(exc_type, exc_value, exc_tb):
        import traceback as _tb
        msg = "".join(_tb.format_exception(exc_type, exc_value, exc_tb))
        # Always write to the crash log first so we have a record even if the
        # dialog itself raises another exception.
        try:
            from modules.utils import get_app_data_dir as _gad
            _elog = _gad() / "netsentinel_exceptions.log"
            import datetime as _dt
            with open(str(_elog), "a", encoding="utf-8") as _f:
                _f.write(f"\n--- {_dt.datetime.now().isoformat()} ---\n{msg}")
        except Exception:
            pass  # non-fatal — log write failure must not mask the original error
        _fatal("Unhandled Error", msg)

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
        pass  # non-Windows or ctypes unavailable — AppUserModelID is cosmetic only

    # Required for QtWebEngineWidgets (Interactive Network Map).  Must be set
    # before QApplication is created — Qt rejects lazy WebEngine imports otherwise.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("NetSentinel")
    app.setApplicationVersion("2.1.22")

    _start_minimised = "--minimised" in sys.argv
    _startup_logger  = "--startup-logger" in sys.argv
    if _startup_logger:
        _start_minimised = True

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
    _spp.drawText(QRect(_SOX, _SOY + 250, _SPLASH_W, 22), Qt.AlignmentFlag.AlignCenter, "v2.1.22")
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

    # Apply QMenu/QToolTip rules at application level so top-level (parentless)
    # menus are styled — widget-level stylesheets do not reach separate windows.
    from ui.styles import get_app_qss
    app.setStyleSheet(get_app_qss())

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
    from workers.passive_observer_worker import PassiveObserverWorker
    from workers.health_worker import HealthWorker

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

    # V6 Sprint 5.4 — global alert-fatigue guardrail. Scales every rule's
    # noise-relevant thresholds by the user's chosen sensitivity; default
    # "balanced" leaves the shipped defaults unchanged.
    from modules.alert_sensitivity import apply_sensitivity, DEFAULT_SENSITIVITY
    _sensitivity = _rule_qs.value("alerts/sensitivity", DEFAULT_SENSITIVITY, type=str)
    apply_sensitivity(_rules, _sensitivity)

    alerts.set_rules(_rules)

    from modules.notification_router import NotificationRouter
    notif_router = NotificationRouter()
    alerts.set_on_alert(notif_router.dispatch)

    from modules.maintenance_window import MaintenanceWindowManager
    maint_manager = MaintenanceWindowManager()
    alerts.set_maintenance_checker(maint_manager.is_suppressed)

    # Sprint 5 — wire the previously-dead record_suppression() plumbing so
    # suppressed alerts actually appear in the maintenance suppression log.
    # AlertEngine only knows the window's label (from is_suppressed), not its
    # id, so we look the matching window up by label to pass a real window_id.
    def _record_alert_suppression(window_label, host, rule_name, severity, message):
        window_id = ""
        for _w in maint_manager.get_windows():
            if _w.label == window_label:
                window_id = _w.id
                break
        maint_manager.record_suppression(
            window_id, window_label, host, rule_name, severity, message
        )

    alerts.set_suppression_recorder(_record_alert_suppression)

    # Pre-warm tplinkrouterc6u on the main STA thread before any plugin workers
    # start.  tplinkrouterc6u.common.encryption uses Windows COM-based crypto;
    # importing it from a background QThread raises RPC_E_WRONG_THREAD (0x8001010d).
    # Importing here puts the module in sys.modules so the lazy import in
    # deco_client._ensure_client() becomes a no-op when called from the worker.
    try:
        import tplinkrouterc6u  # noqa: F401
    except ImportError:
        pass  # optional dep — not installed; Deco hardware plugin will surface the error gracefully

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

    passive_observer_worker = PassiveObserverWorker()
    passive_observer_worker.start()

    health_worker = HealthWorker(store=store)
    health_worker.start()

    # V6 Sprint 2 — TREND_FORECAST: hourly OLS ETA-to-threshold sweep. Pure DB
    # analysis (no new network probing), so it runs always-on like health_worker;
    # the TREND_FORECAST alert rule itself stays opt-in/disabled by default.
    from workers.proactive_probe_worker import ProactiveProbeWorker as _ProactiveProbeWorker
    from modules.trend_analyser import run_full_trend_report as _run_full_trend_report

    trend_worker = _ProactiveProbeWorker(
        probe=lambda: _run_full_trend_report(store),
        interval_s=3600,
    )
    trend_worker.start()

    # Sprint 3 — scheduled background speed tests. Opt-in, default off: bandwidth
    # consent is explicit and separate from notification consent (BASELINE_DROP
    # rule, enabled independently under Notifications).
    from workers.proactive_probe_worker import ProactiveProbeWorker
    from modules.scheduled_speed_test import run_scheduled_speed_test

    _speedtest_qs = QSettings("NetSentinel", "NetSentinel")
    _speedtest_interval_h = int(_speedtest_qs.value("speedtest/scheduled_interval_hours", 6))
    scheduled_speedtest_worker = ProactiveProbeWorker(
        probe=lambda: run_scheduled_speed_test(store),
        interval_s=_speedtest_interval_h * 3600,
    )
    # Sprint 5 — respect maintenance windows / quiet hours for the "speedtest"
    # host key (same convention used by evaluate_baseline_metrics' cooldown key).
    scheduled_speedtest_worker.set_maintenance_checker(
        lambda: maint_manager.is_suppressed("speedtest") is not None
    )

    # V6 Sprint 3 — scheduled security posture scans. Opt-in, default off
    # (BACKLOG-V6 guardrail: no new background network activity without an
    # explicit toggle) — enabled/started from the Security Overview
    # "Scheduled Posture Scans" card via posture_scheduling_changed below.
    from modules.port_sweep import run_nightly_port_sweep
    from modules.cve_recheck import run_cve_recheck
    from modules.exposure_watch import run_weekly_exposure_check
    from modules.arp_watch import run_arp_watch_cycle
    from modules.dhcp_watch import run_dhcp_watch_cycle

    _posture_qs = QSettings("NetSentinel", "NetSentinel")
    port_sweep_worker = ProactiveProbeWorker(
        probe=lambda: run_nightly_port_sweep(store),
        interval_s=24 * 3600,
    )
    port_sweep_worker.set_maintenance_checker(
        lambda: maint_manager.is_suppressed("port_sweep") is not None
    )
    cve_recheck_worker = ProactiveProbeWorker(
        probe=lambda: run_cve_recheck(store),
        interval_s=12 * 3600,
    )
    cve_recheck_worker.set_maintenance_checker(
        lambda: maint_manager.is_suppressed("cve_recheck") is not None
    )
    exposure_watch_worker = ProactiveProbeWorker(
        probe=lambda: run_weekly_exposure_check(store),
        interval_s=7 * 24 * 3600,
    )
    exposure_watch_worker.set_maintenance_checker(
        lambda: maint_manager.is_suppressed("exposure_check") is not None
    )

    # V6 Sprint 4.1/4.2 — passive always-on guards. Gateway IP is looked up
    # fresh each cycle (cheap — a handful of syscalls) rather than cached,
    # since the background worker outlives any one scan and the gateway can
    # change (e.g. laptop moves networks).
    def _run_arp_watch_cycle() -> object:
        from modules.utils_net import get_network_info
        gateway_ip = get_network_info().get("gateway")
        return run_arp_watch_cycle(gateway_ip=gateway_ip, duration=20)

    arp_watch_worker = ProactiveProbeWorker(
        probe=_run_arp_watch_cycle,
        interval_s=15 * 60,
    )
    arp_watch_worker.set_maintenance_checker(
        lambda: maint_manager.is_suppressed("arp_watch") is not None
    )
    dhcp_watch_worker = ProactiveProbeWorker(
        probe=lambda: run_dhcp_watch_cycle(duration=8),
        interval_s=30 * 60,
    )
    dhcp_watch_worker.set_maintenance_checker(
        lambda: maint_manager.is_suppressed("dhcp_watch") is not None
    )

    _posture_workers = {
        "port_sweep": port_sweep_worker,
        "cve_recheck": cve_recheck_worker,
        "exposure_check": exposure_watch_worker,
        "arp_watch": arp_watch_worker,
        "dhcp_watch": dhcp_watch_worker,
    }

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

    _wire_logging(window, passive_observer_worker, snmp_trap_worker, syslog_worker)
    _wire_notifications(window, alerts, notif_router, maint_manager, report_worker)
    _wire_monitoring(window, avail_worker, cert_worker, svc_worker, alerts, notif_router, store)
    _wire_cross_page(window)
    _wire_scan_ctas(window)
    _wire_speedtest_scheduling(window, scheduled_speedtest_worker, alerts, store)
    if _speedtest_qs.value("speedtest/scheduled_enabled", False, type=bool):
        scheduled_speedtest_worker.start()
    _wire_trend_forecast(window, trend_worker, alerts, store)

    # V6 Sprint 3.1/3.3/3.5, 3.2/3.5, 3.4/3.5 — scheduled posture scans.
    # Each starts only if its Security Overview toggle was already on at
    # launch; the toggle's posture_scheduling_changed signal starts/stops
    # the matching worker for the rest of the session.
    _wire_port_sweep(window, port_sweep_worker, alerts, store, cert_worker)
    _wire_cve_recheck(window, cve_recheck_worker, alerts, store)
    _wire_exposure_watch(window, exposure_watch_worker, alerts, store)
    _wire_arp_watch(window, arp_watch_worker, alerts, store)
    _wire_dhcp_watch(window, dhcp_watch_worker, alerts, store)

    def _on_posture_scheduling_changed(key: str, enabled: bool) -> None:
        posture_worker = _posture_workers.get(key)
        if posture_worker is None:
            return
        if enabled and not posture_worker.isRunning():
            posture_worker.start()
        elif not enabled and posture_worker.isRunning():
            posture_worker.stop()
            posture_worker.wait(3000)

    window._security_overview_page.posture_scheduling_changed.connect(_on_posture_scheduling_changed)
    for _key, _posture_worker in _posture_workers.items():
        if _posture_qs.value(f"posture/{_key}_enabled", False, type=bool):
            _posture_worker.start()

    # S2-5: wire ambient health worker → home page card + system tray
    health_worker.result_ready.connect(window._home_page.on_health_update)
    if window._tray_manager.is_available():
        health_worker.result_ready.connect(
            lambda snap: window._tray_manager.set_health(snap.state, snap.headline)
        )

    # S4-5: all-quiet opt-in notification — show once per day when no alerts fired
    try:
        from PyQt6.QtCore import QSettings as _QSettings
        from modules.quiet_notifier import check_and_maybe_notify as _check_quiet
        _qs4 = _QSettings("NetSentinel", "NetSentinel")
        _quiet = _check_quiet(store, _qs4.value, _qs4.setValue)
        if _quiet and window._tray_manager.is_available():
            window._tray_manager.show_notification(
                _quiet.headline, _quiet.sub_text, severity="INFO"
            )
    except Exception:
        pass  # non-fatal — quiet notifier is cosmetic

    # S8-1: morning briefing — opt-in daily 3-bullet summary, default off
    try:
        from PyQt6.QtCore import QSettings as _QSettings5, QTimer as _BriefingTimer
        from modules.morning_briefing import check_and_build_briefing as _check_briefing

        def _do_morning_briefing_check() -> None:
            try:
                _qs5 = _QSettings5("NetSentinel", "NetSentinel")
                _briefing = _check_briefing(store, _qs5.value, _qs5.setValue)
                if _briefing and window._tray_manager.is_available():
                    window._tray_manager.show_notification(
                        _briefing.headline, "\n".join(_briefing.bullets),
                        severity="INFO",
                        on_click=lambda: window._nav_rail_go_to("Home"),
                    )
            except Exception:
                pass  # non-fatal — morning briefing is cosmetic

        _do_morning_briefing_check()
        # Recurring check — the gating hour may not have arrived yet at startup.
        _briefing_timer = _BriefingTimer(window)
        _briefing_timer.timeout.connect(_do_morning_briefing_check)
        _briefing_timer.start(15 * 60 * 1000)  # check every 15 minutes
    except Exception:
        pass  # non-fatal — morning briefing is cosmetic

    # S8-3: "Email me this report →" on the weekly report card
    def _on_email_weekly_report() -> None:
        from ui.widgets.toast import ToastManager
        try:
            from modules.notification_router import EmailChannel
            from modules.notification_channels import send_plain_email
            from modules.digest_builder import build_digest_html
            channel = next(
                (c for c in notif_router.get_channels()
                 if isinstance(c, EmailChannel) and c.enabled and c.smtp_host),
                None,
            )
            if channel is None:
                ToastManager.show(
                    "No email channel configured — set one up in Notifications.",
                    "warning",
                )
                return
            ok = send_plain_email(
                channel, "NetSentinel Weekly Report", build_digest_html(store)
            )
            ToastManager.show(
                "Weekly report emailed." if ok else "Could not send the email — check SMTP settings.",
                "success" if ok else "error",
            )
        except Exception:
            ToastManager.show("Could not send the weekly report email.", "error")

    window._home_page.email_weekly_report_requested.connect(_on_email_weekly_report)

    # Pre-populate Devices table and Network Map from the last MetricStore scan so
    # the app is never blank on startup — a live scan replaces this data normally.
    _splash_msg("Restoring last scan…")
    try:
        window._restore_cached_scan()
    except Exception:
        pass  # non-fatal — startup cache restore is best-effort

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
                    pass  # geometry fixup is best-effort; window still visible
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

    # H10: check logging milestones at startup (deferred so DB is warmed up)
    from PyQt6.QtCore import QTimer as _MilestoneTimer
    _MilestoneTimer.singleShot(
        2000, lambda: window._home_page._check_logger_milestones()
    )

    # Startup task: auto-start Network Logger when launched by Windows startup task
    if _startup_logger:
        window._start_logger_if_needed()

    # ── Tracemalloc profiling (activated by NETSENTINEL_TRACEMALLOC=1 env var) ──
    # Set by tools/monkey_test.py --tracemalloc to identify retained object types
    # during long chaos runs.  Logs the top-20 allocation sites every 60 s to the
    # standard Python logger so the output appears in netsentinel_debug.log.
    if os.environ.get("NETSENTINEL_TRACEMALLOC") == "1":
        import tracemalloc as _tm
        import logging as _logging
        import threading as _threading
        _tm.start(25)  # keep 25 frames of traceback per allocation
        _tm_log = _logging.getLogger("netsentinel.tracemalloc")
        _tm_baseline: list = []

        def _tm_snapshot_loop() -> None:
            import time as _time
            _time.sleep(60)   # let the app warm up before first snapshot
            while True:
                _time.sleep(60)
                try:
                    snap = _tm.take_snapshot()
                    stats = snap.statistics("lineno")
                    _tm_log.info("=== tracemalloc top-20 (by current size) ===")
                    for s in stats[:20]:
                        _tm_log.info("  %s", s)
                    if _tm_baseline:
                        diff = snap.compare_to(_tm_baseline[-1], "lineno")
                        _tm_log.info("=== tracemalloc diff vs previous snapshot ===")
                        for d in diff[:20]:
                            _tm_log.info("  %s", d)
                    _tm_baseline[:] = [snap]  # keep only the last snapshot for diff
                except Exception as _e:
                    _tm_log.warning("tracemalloc snapshot failed: %s", _e)

        _tm_thread = _threading.Thread(target=_tm_snapshot_loop, daemon=True,
                                       name="tracemalloc-sampler")
        _tm_thread.start()
        import logging as _llog
        _llog.getLogger("netsentinel.tracemalloc").setLevel(_llog.DEBUG)
    # ─────────────────────────────────────────────────────────────────────────

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
    health_worker.stop()
    health_worker.wait(3000)
    if scheduled_speedtest_worker.isRunning():
        scheduled_speedtest_worker.stop()
        scheduled_speedtest_worker.wait(5000)
    if rest_api_worker is not None:
        rest_api_worker.stop()
        rest_api_worker.wait(3000)
    window._hardware_integration_page.closedown()
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
    except Exception:  # noqa: BLE001
        import traceback
        _fatal("Unexpected error", traceback.format_exc())


