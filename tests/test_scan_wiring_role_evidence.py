"""
Behavioural test for the Signal Quality Phase 2 evidence wiring (RULE-T7).

`ui/scan_wiring.py::_m1_track_devices` is the only place that knows both the
detected network (`_net_info`) and the mesh system's reported nodes
(`_mesh_units`), and role inference is downstream of it. If that hand-off is
missed, nothing fails loudly: inference silently falls back to the .1/.254
guess, the real mesh AP keeps no role, and the only symptom is a quieter
alert gate than intended.

That is not hypothetical. The evidence call originally sat inside the same
`try` as `process_scan()`, so a DeviceTracker without `set_evidence()` skipped
device persistence *entirely* — caught by three existing tests, and the reason
the call now has its own guard. These tests pin both halves: the evidence must
arrive, and a failure to build it must not take device tracking down with it.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

try:
    from ui.scan_wiring import ScanResultMixin
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.device_tracker import TrackerResult


class _RecordingTracker:
    def __init__(self, store):
        self._store = store
        self.evidence = None
        self.scans = 0

    def set_evidence(self, evidence):
        self.evidence = evidence

    def process_scan(self, devices, known=None):
        self.scans += 1
        return TrackerResult()


class _Unit:
    def __init__(self, mac):
        self.mac = mac


class _Stub(ScanResultMixin):
    pass


def _make_stub(tracker_cls, monkeypatch, *, net_info=None, mesh_units=None):
    monkeypatch.setattr("modules.device_tracker.DeviceTracker", tracker_cls)
    stub = _Stub()
    stub._store = MagicMock()
    stub._alert_engine = None
    stub._set_status = MagicMock()
    if net_info is not None:
        stub._net_info = net_info
    if mesh_units is not None:
        stub._mesh_units = mesh_units
    return stub


def test_gateway_and_mesh_nodes_reach_the_tracker(monkeypatch):
    stub = _make_stub(
        _RecordingTracker, monkeypatch,
        net_info={"gateway": "192.168.68.1", "gateway_mac": "3c:64:cf:e0:27:02"},
        mesh_units=[_Unit("F4:F5:D8:AA:BB:CC")],
    )

    stub._m1_track_devices({"devices": []})

    evidence = stub._device_tracker.evidence
    assert evidence is not None, "role evidence never reached the DeviceTracker"
    assert evidence.gateway_ip == "192.168.68.1"
    assert evidence.mesh_node_macs == frozenset({"f4:f5:d8:aa:bb:cc"})


def test_unresolved_gateway_does_not_break_the_scan(monkeypatch):
    """RULE-NET1: net_info["gateway"] is None until a route/ARP lookup
    succeeds — a normal state on VPN, not corruption."""
    stub = _make_stub(
        _RecordingTracker, monkeypatch, net_info={"gateway": None},
    )

    stub._m1_track_devices({"devices": []})

    assert stub._device_tracker.evidence.gateway_ip is None
    assert stub._device_tracker.scans == 1


def test_evidence_is_refreshed_on_every_scan(monkeypatch):
    """The tracker is cached on the Dashboard for the app's lifetime, but
    net_info is re-read — a gateway learned after the first scan must land."""
    stub = _make_stub(_RecordingTracker, monkeypatch, net_info={"gateway": None})
    stub._m1_track_devices({"devices": []})
    assert stub._device_tracker.evidence.gateway_ip is None

    stub._net_info = {"gateway": "10.0.0.1"}
    stub._m1_track_devices({"devices": []})

    assert stub._device_tracker.evidence.gateway_ip == "10.0.0.1"
    assert stub._device_tracker.scans == 2


def test_a_tracker_without_set_evidence_still_persists_the_scan(monkeypatch):
    """Evidence only ever improves inference. Failing to deliver it must
    degrade role accuracy for one scan, never skip the scan."""

    class _LegacyTracker:
        def __init__(self, store):
            self.scans = 0

        def process_scan(self, devices, known=None):
            self.scans += 1
            return TrackerResult()

    stub = _make_stub(_LegacyTracker, monkeypatch, net_info={"gateway": "10.0.0.1"})

    stub._m1_track_devices({"devices": []})

    assert stub._device_tracker.scans == 1


def test_a_malformed_mesh_unit_does_not_break_the_scan(monkeypatch):
    """_mesh_units comes from a third-party router plugin."""
    stub = _make_stub(
        _RecordingTracker, monkeypatch,
        net_info={"gateway": "10.0.0.1"}, mesh_units=[object(), None],
    )

    stub._m1_track_devices({"devices": []})

    assert stub._device_tracker.scans == 1
    assert stub._device_tracker.evidence.gateway_ip == "10.0.0.1"
