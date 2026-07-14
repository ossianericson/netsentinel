"""
Tests for F-02 -- "Run Selected" Security Scan panel no-ops for TLS & Exposure
and CVE Lookup, 2 of the 4 default-checked _SecurityScanPanel._TOOLS.

Dashboard._advance_security_audit()/_on_tls_check_done() are defined directly on
the Dashboard class (not a standalone mixin), and RULE-TP4-DASH forbids
constructing a real Dashboard in a pytest-collected test. Instead we call the
unbound methods with a minimal duck-typed fake `self` -- this exercises the
real dispatch/advance logic without any Qt widget construction.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui.dashboard import Dashboard  # noqa: E402
from ui.nav.labels import NavLabel as L  # noqa: E402


class _FakeSelf:
    """Minimal stand-in exposing only what _advance_security_audit/_on_tls_check_done touch."""

    def __init__(self) -> None:
        self._pending_security_tools: list = []
        self._net_info = None
        self._syn_host = MagicMock()
        self._start_syn_scan = MagicMock()
        self._start_exposure_check = MagicMock()
        self._threat_intel_page = MagicMock()
        self._run_risk_scorer = MagicMock()
        self._start_cve_lookup = MagicMock()
        self._cert_worker = MagicMock()
        self._awaiting_tls_check = False
        self._nav_set_scan_state = MagicMock()
        self._set_status = MagicMock()

    # Bind the real Dashboard methods under test.
    _advance_security_audit = Dashboard._advance_security_audit
    _on_tls_check_done = Dashboard._on_tls_check_done


class TestCveLookupDispatch:
    def test_cve_lookup_is_dispatched(self):
        """Before the fix, CVE Lookup fell into the 'unrecognised label -- skip
        silently' branch and _start_cve_lookup() was never called."""
        fake = _FakeSelf()
        fake._pending_security_tools = [L.CVE_LOOKUP]
        fake._advance_security_audit()
        fake._start_cve_lookup.assert_called_once()


class TestTlsExposureDispatch:
    def test_tls_exposure_triggers_run_now(self):
        """Before the fix, TLS & Exposure fell into the 'unrecognised label --
        skip silently' branch and CertWorker.run_now() was never called."""
        fake = _FakeSelf()
        fake._pending_security_tools = [L.TLS_EXPOSURE]
        fake._advance_security_audit()
        fake._cert_worker.run_now.assert_called_once()
        fake._nav_set_scan_state.assert_any_call(L.TLS_EXPOSURE, "running")
        assert fake._awaiting_tls_check is True

    def test_missing_cert_worker_skips_and_advances(self):
        fake = _FakeSelf()
        fake._cert_worker = None
        fake._pending_security_tools = [L.TLS_EXPOSURE]
        fake._advance_security_audit()
        fake._set_status.assert_called_once()

    def test_check_done_advances_queue_when_awaited(self):
        """Full sequence: dispatch TLS -> CertWorker finishes -> queue advances."""
        fake = _FakeSelf()
        fake._pending_security_tools = [L.TLS_EXPOSURE]
        fake._advance_security_audit()  # dispatches TLS, sets _awaiting_tls_check
        assert fake._awaiting_tls_check is True

        fake._on_tls_check_done([{"host": "example.com", "is_expired": False, "days_remaining": 90}])

        assert fake._awaiting_tls_check is False
        fresh_calls = [
            c for c in fake._nav_set_scan_state.call_args_list
            if c.args[:2] == (L.TLS_EXPOSURE, "fresh")
        ]
        assert len(fresh_calls) == 1
        assert fresh_calls[0].kwargs["verdict"] == "1 cert(s) OK"
        # Queue was empty after popping TLS, so advancing again reports completion.
        fake._set_status.assert_called_with("Security audit complete — see Security Overview for findings.")

    def test_check_done_does_not_advance_when_not_awaited(self):
        """A routine hourly check (not part of an audit run) must not touch the queue."""
        fake = _FakeSelf()
        fake._on_tls_check_done([])
        fake._set_status.assert_not_called()
