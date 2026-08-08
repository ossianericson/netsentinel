"""
Regression tests for ui/scan_wiring.py::_m1_seed_classification_claims()
(Device Identity Program Phase 3).

Without this seeding step, the claim tracker starts every scan empty, so the
first passive/DHCP claim to arrive later in the scan would arbitrate against
no history and win outright regardless of strength -- silently overwriting a
confident scan-time classification, the exact churn defect the program
measures.
"""
from __future__ import annotations

from modules.device_classification import ClaimTracker


class _Stub:
    """Bare object carrying only what _m1_seed_classification_claims() reads."""

    def __init__(self, tracker):
        self._classification_claims = tracker


def _import_method():
    from ui.scan_wiring import ScanResultMixin
    return ScanResultMixin._m1_seed_classification_claims


def test_seeds_a_claim_matching_the_devices_current_classification():
    tracker = ClaimTracker()
    stub = _Stub(tracker)
    seed = _import_method()

    seed(stub, [
        {"mac": "aa:bb:cc:00:00:01", "vendor": "Lexmark", "hostname": "",
         "open_ports": [9100], "os_family": "", "is_gateway": False},
    ])

    assert tracker.claim_count("aa:bb:cc:00:00:01") == 1
    result = tracker.add("aa:bb:cc:00:00:01", None)
    assert result.device_type == "Print Server"


def test_reset_between_scans_does_not_accumulate_stale_claims():
    tracker = ClaimTracker()
    stub = _Stub(tracker)
    seed = _import_method()

    devices = [{"mac": "aa:bb:cc:00:00:02", "vendor": "Lexmark", "hostname": "",
                "open_ports": [9100], "os_family": "", "is_gateway": False}]
    seed(stub, devices)
    seed(stub, devices)  # simulates a second scan of the same network

    assert tracker.claim_count("aa:bb:cc:00:00:02") == 1


def test_devices_with_no_mac_are_skipped():
    tracker = ClaimTracker()
    stub = _Stub(tracker)
    seed = _import_method()

    seed(stub, [{"mac": "", "vendor": "Lexmark"}])
    assert tracker.add("", None) is None


def test_object_shaped_devices_are_supported():
    """Real scan results carry DeviceInfo objects, not dicts."""
    class _Dev:
        mac = "aa:bb:cc:00:00:03"
        vendor = "Lexmark"
        hostname = ""
        open_ports = [9100]
        os_family = ""
        is_gateway = False

    tracker = ClaimTracker()
    stub = _Stub(tracker)
    seed = _import_method()

    seed(stub, [_Dev()])
    assert tracker.claim_count("aa:bb:cc:00:00:03") == 1


def test_missing_tracker_attribute_is_a_silent_noop():
    class _NoTracker:
        pass

    seed = _import_method()
    seed(_NoTracker(), [{"mac": "aa:bb:cc:00:00:04"}])  # must not raise
