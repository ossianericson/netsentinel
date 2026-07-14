"""
Tests for F-80 -- Security Audit on-demand scans never reached an "error" state.

Before this fix, every on-demand scan worker's ``error`` signal only updated a status
label's text (``self._x_status.setText(f"warning {e}")``); none of them called
``_nav_set_scan_state(label, "error", ...)``. That meant the Security Overview Scan
Status card, the flyout dot, and the rail badge all stayed on whatever state they last
had -- typically "Never run" -- even after a scan genuinely failed (RULE-SS1 violation).

Each test here patches the relevant worker class (mirroring the existing
tests/test_cve_lookup_wiring.py pattern), invokes the real ``_start_*`` method, then
calls the callable that was connected to the mocked worker's ``error`` signal and
asserts ``_nav_set_scan_state`` was told about the failure with the exact nav label.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui.nav.labels import NavLabel as L  # noqa: E402
from ui.tabs_helpers import _table  # noqa: E402
from ui.tabs_recon import _ReconTabsMixin  # noqa: E402


def _error_callables(mock_worker) -> list:
    """Every callable connected to the mocked worker's .error signal."""
    return [call.args[0] for call in mock_worker.error.connect.call_args_list]


def _fires_nav_error(mock_worker, nav_mock, label, msg="boom") -> None:
    """Invoke every connected error callback and assert one reached _nav_set_scan_state."""
    for cb in _error_callables(mock_worker):
        cb(msg)
    nav_mock.assert_any_call(label, "error", error=msg)


class _FakeHost(_ReconTabsMixin):
    """Minimal stand-in exposing only the attributes each _start_* method touches."""

    def __init__(self) -> None:
        self._nav_set_scan_state = MagicMock()
        self._record_recent_action = MagicMock()
        self._m1_result = None

        # Port Scan (TCP)
        self._syn_host = MagicMock(text=lambda: "10.0.0.5")
        self._syn_worker = None
        self._recon_syn_table = _table(["Port", "State", "Protocol", "Service", "Version", "Banner", "CVEs"])
        self._syn_status = MagicMock()
        self._syn_ports_combo = MagicMock(currentText=lambda: "Top 1000")
        self._syn_rate = MagicMock(value=lambda: 100)
        self._on_syn_result = MagicMock()

        # Port Scan (UDP)
        self._udp_host = MagicMock(text=lambda: "10.0.0.5")
        self._udp_worker = None
        self._recon_udp_table = _table(["Port", "State", "Service"])
        self._udp_status = MagicMock()
        self._on_udp_result = MagicMock()

        # OS Detection
        self._os_hosts_input = MagicMock(text=lambda: "10.0.0.5")
        self._os_worker = None
        self._recon_os_table = _table(["IP", "TTL", "OS Family", "Confidence", "TCP Window", "Banner Hint"])
        self._os_status = MagicMock()
        self._on_os_result = MagicMock()

        # CVE Lookup
        self._cve_worker = None
        self._cve_target_input = MagicMock(text=lambda: "OpenSSH 8.9p1")
        self._ps_table = _table(["Port", "Service", "Version", "Banner", "Risk"])
        self._recon_cve_table = _table(["CVE ID", "Service", "Score", "Severity", "Published", "Description"])
        self._cve_status = MagicMock()
        self._on_cve_result = MagicMock()

        # Exposed to Internet
        self._exposure_worker = None
        self._recon_exposure_table = _table(["Port", "Protocol", "Risk"])
        self._exposure_verdict = MagicMock()
        self._exposure_status = MagicMock()
        self._on_exposure_result = MagicMock()

        # Login Test
        self._cred_host = MagicMock(text=lambda: "10.0.0.5")
        self._cred_worker = None
        self._recon_cred_sw_table = _table(["Package", "Version", "Source"])
        self._recon_cred_svc_table = _table(["Service", "Status", "PID"])
        self._recon_cred_user_table = _table(["User", "UID / SID", "Home", "Shell"])
        self._recon_cred_sessions_table = _table(["Active Session (logged-in user)"])
        self._recon_cred_info_table = _table(["Field", "Value"])
        self._cred_verdict = MagicMock()
        self._cred_status = MagicMock()
        self._cred_port = MagicMock(value=lambda: 22)
        self._cred_user = MagicMock(text=lambda: "root")
        self._cred_pass = MagicMock(text=lambda: "")
        self._cred_key = MagicMock(text=lambda: "")
        self._cred_os = MagicMock(currentText=lambda: "auto")
        self._on_cred_result = MagicMock()

        # Full Device Discovery
        self._discovery_worker = None
        self._recon_disc_table = _table(["IP", "Method", "Detail"])
        self._disc_status = MagicMock()
        self._disc_cidr = MagicMock(text=lambda: "")
        self._disc_passive_chk = MagicMock(isChecked=lambda: False)
        self._on_discovery_result = MagicMock()


class TestOnDemandScanErrorsReachScanRegistry:
    def test_syn_scan_error_sets_registry_error(self):
        host = _FakeHost()
        with patch("workers.scan_worker.SYNScanWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_syn_scan()
        _fires_nav_error(mock_cls.return_value, host._nav_set_scan_state, L.PORT_SCAN_TCP)

    def test_udp_scan_error_sets_registry_error(self):
        host = _FakeHost()
        with patch("workers.scan_worker.UDPScanWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_udp_scan()
        _fires_nav_error(mock_cls.return_value, host._nav_set_scan_state, L.PORT_SCAN_UDP)

    def test_os_fingerprint_error_sets_registry_error(self):
        host = _FakeHost()
        with patch("workers.scan_worker.OSFingerprintWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_os_fingerprint()
        _fires_nav_error(mock_cls.return_value, host._nav_set_scan_state, L.OS_DETECTION)

    def test_cve_lookup_error_sets_registry_error(self):
        host = _FakeHost()
        with patch("workers.scan_worker.CVELookupWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_cve_lookup()
        _fires_nav_error(mock_cls.return_value, host._nav_set_scan_state, L.CVE_LOOKUP)

    def test_exposure_check_error_sets_registry_error(self):
        host = _FakeHost()
        with patch("workers.scan_worker.InternetExposureWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_exposure_check()
        _fires_nav_error(mock_cls.return_value, host._nav_set_scan_state, L.EXPOSED_TO_INTERNET)

    def test_login_test_error_sets_registry_error(self):
        host = _FakeHost()
        with patch("workers.scan_worker.CredentialedScanWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_cred_scan()
        _fires_nav_error(mock_cls.return_value, host._nav_set_scan_state, L.LOGIN_TEST)

    def test_full_device_discovery_error_sets_registry_error(self):
        host = _FakeHost()
        with patch("workers.scan_worker.CombinedDiscoveryWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_discovery()
        _fires_nav_error(mock_cls.return_value, host._nav_set_scan_state, L.FULL_DEVICE_DISCOVERY)


class TestCVELookupWorkerErrorSignal:
    """CVELookupWorker previously had no `error` signal at all -- failures were only
    buried in a `status` text message, so nothing downstream could distinguish a
    failure from a normal progress update."""

    def test_worker_emits_error_signal_on_exception(self, qt_app):
        from workers.scan_worker import CVELookupWorker

        worker = CVELookupWorker(service_versions=["Nginx 1.20"])
        received = []
        worker.error.connect(received.append)

        with patch("modules.cve_lookup.lookup_many", side_effect=RuntimeError("network down")):
            worker.run()

        assert len(received) == 1
        assert "network down" in received[0]


class TestThreatIntelScanErrorSignal:
    def test_refresh_error_emits_scan_error(self, qt_app):
        from ui.pages.threat_intel_page import ThreatIntelPage

        page = ThreatIntelPage.__new__(ThreatIntelPage)
        received = []
        page.scan_error = MagicMock()
        page.scan_error.emit = received.append
        page._refresh_btn = MagicMock()
        page._cache_btn = MagicMock()
        page._status_lbl = MagicMock()

        page._on_refresh_error("feed unreachable")

        assert received == ["feed unreachable"]
