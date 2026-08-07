"""
Regression tests for the Signal Quality Phase 2 wiring in device_tracker.py.

Role inference is only as good as what reaches it. Two things previously did
not:

  1. **The device's own identity.** `update_stability_for_device()` was called
     with the MAC, IP, device_type and custom_name only — no hostname, no
     vendor. Under Phase 2's identity gate that would read every privacy MAC as
     anonymous and strip the role from a perfectly identifiable
     `Ossians-iPhone-2022`.

  2. **What the network says.** The real gateway address and the mesh system's
     own node list live on the Dashboard, and nothing carried them down to the
     inference that most needs them — which is why the reference network's
     actual mesh AP held no role while a PS4 held "infrastructure".

Written before the fix (RULE-T3), driven end-to-end through process_scan()
against a real MetricStore rather than a mock, because the defect is in the
call chain, not in either end of it.
"""
from __future__ import annotations

import pytest

from modules.device_stability import RoleEvidence
from modules.device_tracker import DeviceTracker
from modules.metric_store import MetricStore


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "tracker_importance.db")
    yield s
    s.close()


def _dev(mac, ip, host="", vendor="", device_type=""):
    return {
        "mac": mac, "ip": ip, "hostname": host,
        "vendor": vendor, "device_type": device_type,
    }


def _role(store, mac):
    return store.get_known_devices()[mac].inferred_role


# ── Identity reaches the inference ───────────────────────────────────────────

def test_hostname_keeps_a_privacy_mac_promotable(store):
    """iOS/Android randomise per-SSID and keep the address. Dropping the
    hostname on the way to inference would make this device anonymous."""
    tracker = DeviceTracker(store=store)
    tracker.process_scan([
        _dev("92:ac:4a:bf:8d:10", "192.168.1.1", host="Ossians-iPhone-2022"),
    ])
    assert _role(store, "92:ac:4a:bf:8d:10") == "gateway"


def test_unidentifiable_privacy_mac_is_not_promoted(store):
    """ACCEPTANCE CRITERION 1 — three such devices held infrastructure."""
    tracker = DeviceTracker(store=store)
    tracker.process_scan([_dev("6a:34:64:72:f8:f0", "192.168.1.1")])
    assert _role(store, "6a:34:64:72:f8:f0") is None


def test_vendor_reaches_the_inference(store):
    """The reference network's real mesh AP, classified "Video Doorbell"."""
    tracker = DeviceTracker(store=store)
    tracker.process_scan([
        _dev("f0:72:ea:51:d3:b8", "192.168.68.64",
             vendor="Google Nest / Nest Wifi / Google Wifi Router",
             device_type="Video Doorbell"),
    ])
    assert _role(store, "f0:72:ea:51:d3:b8") == "infrastructure"


# ── Network evidence reaches the inference ───────────────────────────────────

def test_gateway_evidence_is_applied(store):
    tracker = DeviceTracker(
        store=store, evidence=RoleEvidence(gateway_ip="192.168.68.99"),
    )
    tracker.process_scan([_dev("3c:64:cf:e0:27:02", "192.168.68.99", vendor="TP-Link")])
    assert _role(store, "3c:64:cf:e0:27:02") == "gateway"


def test_gateway_evidence_denies_the_octet_guess(store):
    """Knowing the real gateway is also knowing what is not the gateway."""
    tracker = DeviceTracker(
        store=store, evidence=RoleEvidence(gateway_ip="192.168.68.99"),
    )
    tracker.process_scan([_dev("f4:f5:d8:aa:bb:cc", "192.168.68.1", vendor="Sonos")])
    assert _role(store, "f4:f5:d8:aa:bb:cc") is None


def test_mesh_node_list_is_applied(store):
    tracker = DeviceTracker(
        store=store,
        evidence=RoleEvidence(mesh_node_macs=frozenset({"F4:F5:D8:AA:BB:CC"})),
    )
    tracker.process_scan([_dev("f4:f5:d8:aa:bb:cc", "192.168.68.30", vendor="Sonos")])
    assert _role(store, "f4:f5:d8:aa:bb:cc") == "infrastructure"


def test_evidence_can_be_replaced_between_scans(store):
    """net_info is re-read per scan; a tracker cached on the Dashboard must not
    pin the gateway address it saw the first time."""
    tracker = DeviceTracker(store=store)
    tracker.process_scan([_dev("f4:f5:d8:aa:bb:cc", "192.168.68.30", vendor="Sonos")])
    assert _role(store, "f4:f5:d8:aa:bb:cc") is None

    tracker.set_evidence(RoleEvidence(gateway_ip="192.168.68.30"))
    tracker.process_scan([_dev("f4:f5:d8:aa:bb:cc", "192.168.68.30", vendor="Sonos")])
    assert _role(store, "f4:f5:d8:aa:bb:cc") == "gateway"


def test_default_tracker_still_works_without_evidence(store):
    """Back-compat: every existing DeviceTracker(store) call site keeps working."""
    tracker = DeviceTracker(store=store)
    tracker.process_scan([_dev("f4:f5:d8:aa:bb:cc", "192.168.1.1", vendor="Sonos")])
    assert _role(store, "f4:f5:d8:aa:bb:cc") == "gateway"
