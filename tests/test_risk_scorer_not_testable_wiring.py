"""
L3 (Sprint 5a) -- _run_risk_scorer() must thread the not_testable host sets
populated by the SYN-scan and OS-detection result handlers into score_devices(),
mirroring the existing credential_hosts convention (F-46).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui.tabs_helpers import _table  # noqa: E402
from ui.tabs_recon import _ReconTabsMixin  # noqa: E402


class _FakeHost(_ReconTabsMixin):
    """Minimal stand-in exposing only what _run_risk_scorer touches."""

    def __init__(self) -> None:
        self._m1_result = {"devices": [{"ip": "10.0.0.5"}, {"ip": "10.0.0.6"}]}
        self._cred_access_hosts = None
        self._port_scan_not_testable_hosts = {"10.0.0.5"}
        self._os_detect_not_testable_hosts = {"10.0.0.6"}
        self._risk_status = MagicMock()
        # RULE-SS1: _run_risk_scorer now records its scan state on the nav registry
        self._nav_set_scan_state = MagicMock()
        self._recon_risk_table = _table(
            ["IP", "Device Type", "Score", "Severity", "Primary Finding", "Remediation"]
        )


def test_run_risk_scorer_threads_not_testable_hosts_into_score_devices(monkeypatch):
    captured: dict = {}

    def _fake_score_devices(devices, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("modules.risk_scorer.score_devices", _fake_score_devices)
    host = _FakeHost()
    host._run_risk_scorer()

    assert captured.get("port_scan_not_testable_hosts") == {"10.0.0.5"}
    assert captured.get("os_detect_not_testable_hosts") == {"10.0.0.6"}


def test_run_risk_scorer_defaults_to_empty_sets_when_not_populated(monkeypatch):
    """Hosts never wired (e.g. a host with no attribute set at all) must not crash."""
    captured: dict = {}

    def _fake_score_devices(devices, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("modules.risk_scorer.score_devices", _fake_score_devices)

    class _BareHost(_ReconTabsMixin):
        def __init__(self):
            self._m1_result = {"devices": []}
            self._cred_access_hosts = None
            self._risk_status = MagicMock()
            # RULE-SS1: _run_risk_scorer now records its scan state
            self._nav_set_scan_state = MagicMock()
            self._recon_risk_table = _table(
                ["IP", "Device Type", "Score", "Severity", "Primary Finding", "Remediation"]
            )

    host = _BareHost()
    host._run_risk_scorer()

    assert captured.get("port_scan_not_testable_hosts") in (None, set())
    assert captured.get("os_detect_not_testable_hosts") in (None, set())
