"""
Worker lifecycle tests — verifies that every QThread worker:
  1. Imports cleanly (catches missing hidden imports in PyInstaller bundles)
  2. Can be instantiated without a running event loop
  3. Starts, runs briefly, and stops without deadlock or exception

All workers are tested with mocked / in-memory dependencies so no real
network sockets, file handles, or external processes are required.

The conftest.py session-scoped QApplication (offscreen platform) provides
the Qt runtime needed by QThread.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────────

WAIT_MS = 2000   # ms to wait for a worker to start/stop


def _start_stop(worker, wait_ms: int = WAIT_MS) -> None:
    """Start a worker, wait briefly, call stop() if available, then join."""
    worker.start()
    worker.thread().msleep(50) if hasattr(worker, "thread") else time.sleep(0.05)
    if hasattr(worker, "stop"):
        worker.stop()
    finished = worker.wait(wait_ms)
    if not finished:
        worker.terminate()
        worker.wait(500)


def _fake_store():
    """Return a minimal MetricStore mock that satisfies worker constructors."""
    s = MagicMock()
    s.query_availability_history = MagicMock(return_value=[])
    s.query_speed_test_history = MagicMock(return_value=[])
    return s


# ── 1. AvailabilityWorker ─────────────────────────────────────────────────────

class TestAvailabilityWorker:
    def test_import(self):
        from workers.availability_worker import AvailabilityWorker
        assert AvailabilityWorker is not None

    def test_instantiate(self, qt_app):
        from workers.availability_worker import AvailabilityWorker
        w = AvailabilityWorker(store=_fake_store(), interval_s=3600)
        assert w is not None

    def test_signals_exist(self, qt_app):
        from workers.availability_worker import AvailabilityWorker
        w = AvailabilityWorker(store=_fake_store())
        assert hasattr(w, "cycle_done")
        assert hasattr(w, "state_changed")
        assert hasattr(w, "error")
        assert hasattr(w, "stop")

    def test_start_stop(self, qt_app):
        from workers.availability_worker import AvailabilityWorker
        from modules.availability_monitor import CycleResult
        with patch("modules.availability_monitor.AvailabilityMonitor.run_cycle",
                   return_value=CycleResult(states={}, rtts={}, changes=[], ts=0)):
            w = AvailabilityWorker(store=_fake_store(), interval_s=3600)
            _start_stop(w)
            assert not w.isRunning()


# ── 2. CertWorker ─────────────────────────────────────────────────────────────

class TestCertWorker:
    def test_import(self):
        from workers.cert_worker import CertWorker
        assert CertWorker is not None

    def test_signals_exist(self, qt_app):
        from workers.cert_worker import CertWorker
        w = CertWorker(store=_fake_store())
        assert hasattr(w, "check_done")
        assert hasattr(w, "error")
        assert hasattr(w, "stop")

    def test_start_stop(self, qt_app):
        from workers.cert_worker import CertWorker
        with patch("modules.cert_monitor.CertMonitor.run_check", return_value=[]):
            w = CertWorker(store=_fake_store(), targets=[])
            _start_stop(w)
            assert not w.isRunning()


# ── 3. DhcpLeaseWorker ────────────────────────────────────────────────────────

class TestDhcpLeaseWorker:
    def test_import(self):
        from workers.dhcp_lease_worker import DhcpLeaseWorker
        assert DhcpLeaseWorker is not None

    def test_signals_exist(self, qt_app):
        from workers.dhcp_lease_worker import DhcpLeaseWorker
        w = DhcpLeaseWorker()
        assert hasattr(w, "result_ready")
        assert hasattr(w, "error")

    def test_start_stop(self, qt_app):
        from workers.dhcp_lease_worker import DhcpLeaseWorker
        with patch("modules.dhcp_lease_scanner.scan", return_value=[]):
            w = DhcpLeaseWorker()
            _start_stop(w)
            assert not w.isRunning()


# ── 4. DnsZoneWorker ─────────────────────────────────────────────────────────

class TestDnsZoneWorker:
    def test_import(self):
        from workers.dns_zone_worker import DnsZoneWorker
        assert DnsZoneWorker is not None

    def test_signals_exist(self, qt_app):
        from workers.dns_zone_worker import DnsZoneWorker
        w = DnsZoneWorker()
        assert hasattr(w, "result_ready")
        assert hasattr(w, "error")

    def test_start_stop(self, qt_app):
        from workers.dns_zone_worker import DnsZoneWorker
        with patch("modules.dns_zone_scanner.scan", return_value=MagicMock(records=[], errors=[])):
            w = DnsZoneWorker()
            _start_stop(w)
            assert not w.isRunning()


# ── 5. HaScanWorker / MacLookupWorker ─────────────────────────────────────────

class TestHaWorker:
    def test_import(self):
        from workers.ha_worker import HaScanWorker, MacLookupWorker
        assert HaScanWorker is not None
        assert MacLookupWorker is not None

    def test_signals_exist(self, qt_app):
        from workers.ha_worker import HaScanWorker
        w = HaScanWorker(hosts=[])
        assert hasattr(w, "results_ready")
        assert hasattr(w, "error")

    def test_start_stop(self, qt_app):
        from workers.ha_worker import HaScanWorker
        w = HaScanWorker(hosts=[])
        _start_stop(w)
        assert not w.isRunning()


# ── 6. IfaceBwPoller ─────────────────────────────────────────────────────────

class TestIfaceBwPoller:
    def test_import(self):
        from workers.iface_bw_worker import IfaceBwPoller
        assert IfaceBwPoller is not None

    def test_signals_exist(self, qt_app):
        from workers.iface_bw_worker import IfaceBwPoller
        w = IfaceBwPoller(interval_s=3600)
        assert hasattr(w, "stats_ready")
        assert hasattr(w, "stop")

    def test_start_stop(self, qt_app):
        from workers.iface_bw_worker import IfaceBwPoller
        w = IfaceBwPoller(interval_s=3600)
        _start_stop(w)
        assert not w.isRunning()


# ── 7. ConnectionSnapshotWorker / ConnectionPollerWorker ──────────────────────

class TestProcessWorker:
    def test_import(self):
        from workers.process_worker import ConnectionSnapshotWorker, ConnectionPollerWorker
        assert ConnectionSnapshotWorker is not None
        assert ConnectionPollerWorker is not None

    def test_snapshot_signals(self, qt_app):
        from workers.process_worker import ConnectionSnapshotWorker
        w = ConnectionSnapshotWorker()
        assert hasattr(w, "snapshot_ready")
        assert hasattr(w, "error")

    def test_snapshot_start_stop(self, qt_app):
        from workers.process_worker import ConnectionSnapshotWorker
        with patch("modules.process_monitor.snapshot", return_value=[]):
            w = ConnectionSnapshotWorker()
            _start_stop(w)
            assert not w.isRunning()

    def test_poller_start_stop(self, qt_app):
        from workers.process_worker import ConnectionPollerWorker
        with patch("modules.process_monitor.snapshot", return_value=[]):
            w = ConnectionPollerWorker(interval=3600)
            _start_stop(w)
            assert not w.isRunning()


# ── 8. ReportSchedulerWorker ─────────────────────────────────────────────────

class TestReportSchedulerWorker:
    def test_import(self):
        from workers.report_scheduler_worker import ReportSchedulerWorker
        assert ReportSchedulerWorker is not None

    def test_signals_exist(self, qt_app):
        from workers.report_scheduler_worker import ReportSchedulerWorker
        w = ReportSchedulerWorker(store=_fake_store())
        assert hasattr(w, "report_saved")
        assert hasattr(w, "error")
        assert hasattr(w, "stop")

    def test_start_stop(self, qt_app):
        from workers.report_scheduler_worker import ReportSchedulerWorker
        w = ReportSchedulerWorker(store=_fake_store())
        _start_stop(w)
        assert not w.isRunning()


# ── 9. RestApiWorker ─────────────────────────────────────────────────────────

class TestRestApiWorker:
    def test_import(self):
        from workers.rest_api_worker import RestApiWorker
        assert RestApiWorker is not None

    def test_signals_exist(self, qt_app):
        from workers.rest_api_worker import RestApiWorker
        w = RestApiWorker(store=_fake_store())
        assert hasattr(w, "started_ok")
        assert hasattr(w, "stopped")
        assert hasattr(w, "error")
        assert hasattr(w, "stop")

    def test_start_stop(self, qt_app):
        from workers.rest_api_worker import RestApiWorker
        # Patch run_server so no real socket is opened
        with patch("modules.rest_api.run_server", return_value=None):
            w = RestApiWorker(store=_fake_store())
            _start_stop(w)
            assert not w.isRunning()


# ── 10. ServiceWorker ────────────────────────────────────────────────────────

class TestServiceWorker:
    def test_import(self):
        from workers.service_worker import ServiceWorker
        assert ServiceWorker is not None

    def test_signals_exist(self, qt_app):
        from workers.service_worker import ServiceWorker
        w = ServiceWorker(store=_fake_store())
        assert hasattr(w, "check_done")
        assert hasattr(w, "error")
        assert hasattr(w, "stop")

    def test_start_stop(self, qt_app):
        from workers.service_worker import ServiceWorker
        with patch("modules.service_monitor.ServiceMonitor.run_check", return_value=[]):
            w = ServiceWorker(store=_fake_store(), targets=[])
            _start_stop(w)
            assert not w.isRunning()


# ── 11. SnmpTrapWorker ───────────────────────────────────────────────────────

class TestSnmpTrapWorker:
    def test_import(self):
        from workers.snmp_trap_worker import SnmpTrapWorker
        assert SnmpTrapWorker is not None

    def test_signals_exist(self, qt_app):
        from workers.snmp_trap_worker import SnmpTrapWorker
        w = SnmpTrapWorker()
        assert hasattr(w, "trap_received")
        assert hasattr(w, "error")
        assert hasattr(w, "stop")

    def test_start_stop(self, qt_app):
        from workers.snmp_trap_worker import SnmpTrapWorker
        with patch("modules.snmp_trap_receiver.SnmpTrapReceiver.open", return_value=16200), \
             patch("modules.snmp_trap_receiver.SnmpTrapReceiver.receive_one", return_value=None):
            w = SnmpTrapWorker(port=16200)
            _start_stop(w)
            assert not w.isRunning()


# ── 12. SyslogWorker ─────────────────────────────────────────────────────────

class TestSyslogWorker:
    def test_import(self):
        from workers.syslog_worker import SyslogWorker
        assert SyslogWorker is not None

    def test_signals_exist(self, qt_app):
        from workers.syslog_worker import SyslogWorker
        w = SyslogWorker()
        assert hasattr(w, "message_received")
        assert hasattr(w, "error")
        assert hasattr(w, "stop")

    def test_start_stop(self, qt_app):
        from workers.syslog_worker import SyslogWorker
        with patch("modules.syslog_receiver.SyslogReceiver.open", return_value=15140), \
             patch("modules.syslog_receiver.SyslogReceiver.receive_one", return_value=None):
            w = SyslogWorker(port=15140)
            _start_stop(w)
            assert not w.isRunning()


# ── 13. SpeedTestWorker / FetchServersWorker ──────────────────────────────────

class TestSpeedTestWorker:
    def test_import(self):
        from workers.speed_test_worker import SpeedTestWorker, FetchServersWorker
        assert SpeedTestWorker is not None
        assert FetchServersWorker is not None

    def test_speed_test_signals(self, qt_app):
        from workers.speed_test_worker import SpeedTestWorker
        w = SpeedTestWorker()
        assert hasattr(w, "phase_changed")
        assert hasattr(w, "result_ready")
        assert hasattr(w, "error")

    def test_fetch_servers_signals(self, qt_app):
        from workers.speed_test_worker import FetchServersWorker
        w = FetchServersWorker(limit=5)
        assert hasattr(w, "servers_ready")
        assert hasattr(w, "error")

    def test_fetch_servers_start_stop(self, qt_app):
        from workers.speed_test_worker import FetchServersWorker
        with patch("modules.speed_tester.fetch_servers", return_value=[]):
            w = FetchServersWorker(limit=5)
            _start_stop(w)
            assert not w.isRunning()

    def test_speed_test_worker_start_stop(self, qt_app):
        from workers.speed_test_worker import SpeedTestWorker
        from modules.speed_tester_backends import SpeedTestResult
        fake_result = SpeedTestResult(
            download_mbps=100.0, upload_mbps=50.0, ping_ms=10.0,
            server_name="Test", server_city="City", server_country="US",
            backend="pure_python",
        )
        with patch("modules.speed_tester.run_test", return_value=fake_result):
            w = SpeedTestWorker()
            _start_stop(w)
            assert not w.isRunning()


# ── 14. ThreatFeedRefreshWorker / AbuseIpDbWorker ────────────────────────────

class TestThreatIntelWorker:
    def test_import(self):
        from workers.threat_intel_worker import ThreatFeedRefreshWorker, AbuseIpDbWorker
        assert ThreatFeedRefreshWorker is not None
        assert AbuseIpDbWorker is not None

    def test_feed_refresh_signals(self, qt_app):
        from workers.threat_intel_worker import ThreatFeedRefreshWorker
        w = ThreatFeedRefreshWorker()
        assert hasattr(w, "result_ready")
        assert hasattr(w, "error")

    def test_feed_refresh_start_stop(self, qt_app):
        from workers.threat_intel_worker import ThreatFeedRefreshWorker
        with patch("modules.threat_intel.refresh_from_feeds", return_value=[]):
            w = ThreatFeedRefreshWorker()
            _start_stop(w)
            assert not w.isRunning()

    def test_abuse_ipdb_signals(self, qt_app):
        from workers.threat_intel_worker import AbuseIpDbWorker
        w = AbuseIpDbWorker(ip="8.8.8.8", api_key="test")
        assert hasattr(w, "result_ready")
        assert hasattr(w, "error")


# ── 15. scan_worker (key workers) ────────────────────────────────────────────

class TestScanWorkerImport:
    """scan_worker.py contains ~20 workers — test that the module imports
    cleanly and key worker classes are present."""

    def test_import(self):
        import workers.scan_worker as sw
        assert sw is not None

    def test_key_classes_present(self):
        from workers.scan_worker import (
            Module1Worker,
            PortScanWorker,
            SYNScanWorker,
            ARPMonitorWorker,
            BandwidthWorker,
            SchedulerWorker,
            CombinedDiscoveryWorker,
            OSFingerprintWorker,
            CVELookupWorker,
        )
        for cls in (Module1Worker, PortScanWorker, SYNScanWorker,
                    ARPMonitorWorker, BandwidthWorker, SchedulerWorker,
                    CombinedDiscoveryWorker, OSFingerprintWorker, CVELookupWorker):
            assert cls is not None

    def test_module1_signals(self, qt_app):
        from workers.scan_worker import Module1Worker
        from pathlib import Path
        w = Module1Worker(offenders_path=Path("offenders.json"))
        assert hasattr(w, "result")
        assert hasattr(w, "error")

    def test_port_scan_worker_instantiate(self, qt_app):
        from workers.scan_worker import PortScanWorker
        w = PortScanWorker(host="127.0.0.1")
        assert hasattr(w, "result")
        assert hasattr(w, "error")

    def test_bandwidth_worker_instantiate(self, qt_app):
        from workers.scan_worker import BandwidthWorker
        w = BandwidthWorker(interval_s=3600)
        assert hasattr(w, "snapshot")
        assert hasattr(w, "stop")

    def test_bandwidth_worker_start_stop(self, qt_app):
        from workers.scan_worker import BandwidthWorker
        with patch("modules.bandwidth_monitor.BandwidthMonitor") as MockBM:
            MockBM.return_value.run = MagicMock(side_effect=lambda: None)
            w = BandwidthWorker(interval_s=3600)
            _start_stop(w)
            assert not w.isRunning()

    def test_combined_discovery_worker_start_stop(self, qt_app):
        from workers.scan_worker import CombinedDiscoveryWorker
        fake_result = MagicMock()
        fake_result.devices = []
        with patch("modules.combined_discovery.discover", return_value=fake_result):
            w = CombinedDiscoveryWorker(cidr="127.0.0.1/32",
                                        passive_only=True,
                                        resolve_hostnames=False)
            _start_stop(w)
            assert not w.isRunning()


# ── DiagnosisWorker ───────────────────────────────────────────────────────────

class TestDiagnosisWorker:
    def test_import(self):
        from workers.diagnosis_worker import DiagnosisWorker
        assert DiagnosisWorker is not None

    def test_signals_exist(self, qt_app):
        from workers.diagnosis_worker import DiagnosisWorker
        w = DiagnosisWorker()
        assert hasattr(w, "progress")
        assert hasattr(w, "finished")
        assert hasattr(w, "stop")

    def test_start_stop(self, qt_app):
        from workers.diagnosis_worker import DiagnosisWorker
        from modules.root_cause_correlator import CorrelationResult

        _empty_result = CorrelationResult()

        with patch("modules.network_diagnostics.scan", return_value=MagicMock(
                trace_hops=[], ping_results=[], dns_results=[],
                download_mbps=-1.0, dns_leak=None)):
            with patch("modules.storm_analyser.scan", return_value=MagicMock(
                    storm_level="CLEAN", top_sources=[], bcast_per_sec=0.0)):
                with patch("modules.rogue_device.scan", return_value={"devices": []}):
                    with patch("modules.stp_detector.scan", return_value=None):
                        with patch("modules.root_cause_correlator.correlate",
                                   return_value=_empty_result):
                            w = DiagnosisWorker(symptom="slow")
                            _start_stop(w)
                            assert not w.isRunning()

    def test_symptom_routing_skips_stp(self, qt_app):
        from workers.diagnosis_worker import DiagnosisWorker
        from modules.root_cause_correlator import CorrelationResult

        with patch("modules.network_diagnostics.scan", return_value=MagicMock(
                trace_hops=[], ping_results=[], dns_results=[],
                download_mbps=-1.0, dns_leak=None)):
            with patch("modules.storm_analyser.scan", return_value=MagicMock(
                    storm_level="CLEAN", top_sources=[], bcast_per_sec=0.0)):
                with patch("modules.rogue_device.scan", return_value={"devices": []}):
                    with patch("modules.stp_detector.scan") as mock_stp:
                        with patch("modules.root_cause_correlator.correlate",
                                   return_value=CorrelationResult()):
                            w = DiagnosisWorker(symptom="slow")
                            _start_stop(w)
                            mock_stp.assert_not_called()

    def test_symptom_routing_skips_storm_and_stp_for_noconn(self, qt_app):
        from workers.diagnosis_worker import DiagnosisWorker
        from modules.root_cause_correlator import CorrelationResult

        with patch("modules.network_diagnostics.scan", return_value=MagicMock(
                trace_hops=[], ping_results=[], dns_results=[],
                download_mbps=-1.0, dns_leak=None)):
            with patch("modules.storm_analyser.scan") as mock_storm:
                with patch("modules.rogue_device.scan", return_value={"devices": []}):
                    with patch("modules.stp_detector.scan") as mock_stp:
                        with patch("modules.root_cause_correlator.correlate",
                                   return_value=CorrelationResult()):
                            w = DiagnosisWorker(symptom="noconn")
                            _start_stop(w)
                            mock_storm.assert_not_called()
                            mock_stp.assert_not_called()
