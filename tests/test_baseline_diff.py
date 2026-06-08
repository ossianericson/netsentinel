"""
Tests for modules/utils.py :: diff_devices_against_baseline()

No network, no disk (save_device_baseline is not called here — we pass
baseline dicts directly to the pure diff function).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.utils import diff_devices_against_baseline


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dev(mac: str, ip: str = "192.168.1.2",
         hostname: str = "host", vendor: str = "ACME") -> dict:
    return {"mac": mac, "ip": ip, "hostname": hostname, "vendor": vendor}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_empty_baseline_all_devices_are_new():
    devices = [_dev("aa:bb:cc:dd:ee:01"), _dev("aa:bb:cc:dd:ee:02")]
    baseline: dict = {}
    new = diff_devices_against_baseline(devices, baseline)
    assert len(new) == 2
    assert len(baseline) == 2


def test_known_device_not_in_new_list():
    devices = [_dev("aa:bb:cc:dd:ee:01")]
    baseline = {
        "aa:bb:cc:dd:ee:01": {
            "ip": "192.168.1.1", "hostname": "old", "vendor": "X",
            "first_seen": "2026-01-01T00:00:00", "last_seen": "2026-01-01T00:00:00",
        }
    }
    new = diff_devices_against_baseline(devices, baseline)
    assert new == []


def test_mixed_new_and_known():
    devices = [
        _dev("aa:bb:cc:dd:ee:01"),  # known
        _dev("aa:bb:cc:dd:ee:02"),  # new
    ]
    baseline = {
        "aa:bb:cc:dd:ee:01": {
            "ip": "192.168.1.1", "hostname": "router", "vendor": "TP-Link",
            "first_seen": "2026-01-01T00:00:00", "last_seen": "2026-01-01T00:00:00",
        }
    }
    new = diff_devices_against_baseline(devices, baseline)
    assert len(new) == 1
    assert new[0]["mac"] == "aa:bb:cc:dd:ee:02"


def test_new_device_added_to_baseline():
    mac = "aa:bb:cc:dd:ee:03"
    devices = [_dev(mac, ip="192.168.1.10", hostname="laptop", vendor="Dell")]
    baseline: dict = {}
    diff_devices_against_baseline(devices, baseline)
    assert mac in baseline
    assert baseline[mac]["ip"] == "192.168.1.10"
    assert baseline[mac]["hostname"] == "laptop"
    assert "first_seen" in baseline[mac]
    assert "last_seen" in baseline[mac]


def test_known_device_last_seen_updated():
    mac = "aa:bb:cc:dd:ee:04"
    old_ts = "2026-01-01T00:00:00"
    baseline = {
        mac: {
            "ip": "192.168.1.5", "hostname": "tv", "vendor": "Samsung",
            "first_seen": old_ts, "last_seen": old_ts,
        }
    }
    devices = [_dev(mac, ip="192.168.1.5")]
    diff_devices_against_baseline(devices, baseline)
    assert baseline[mac]["last_seen"] != old_ts  # updated to now


def test_known_device_ip_updated_when_changed():
    mac = "aa:bb:cc:dd:ee:05"
    baseline = {
        mac: {
            "ip": "192.168.1.5", "hostname": "phone", "vendor": "Apple",
            "first_seen": "2026-01-01T00:00:00", "last_seen": "2026-01-01T00:00:00",
        }
    }
    devices = [_dev(mac, ip="192.168.1.99")]   # IP changed (DHCP reassignment)
    diff_devices_against_baseline(devices, baseline)
    assert baseline[mac]["ip"] == "192.168.1.99"


def test_device_without_mac_is_ignored():
    devices = [{"mac": "", "ip": "192.168.1.1", "hostname": "", "vendor": ""}]
    baseline: dict = {}
    new = diff_devices_against_baseline(devices, baseline)
    assert new == []
    assert baseline == {}


def test_mac_normalised_to_lowercase():
    """MACs with uppercase letters should still match a lowercase baseline key."""
    mac_upper = "AA:BB:CC:DD:EE:FF"
    mac_lower = "aa:bb:cc:dd:ee:ff"
    baseline = {
        mac_lower: {
            "ip": "192.168.1.1", "hostname": "gw", "vendor": "Cisco",
            "first_seen": "2026-01-01T00:00:00", "last_seen": "2026-01-01T00:00:00",
        }
    }
    devices = [_dev(mac_upper)]
    new = diff_devices_against_baseline(devices, baseline)
    # Should be recognised as known (same MAC normalised)
    assert new == []


def test_first_seen_is_set_only_on_creation():
    mac = "aa:bb:cc:dd:ee:06"
    baseline: dict = {}
    devices = [_dev(mac)]
    diff_devices_against_baseline(devices, baseline)
    first_seen_1 = baseline[mac]["first_seen"]

    # Second scan — same device, first_seen must NOT change
    diff_devices_against_baseline(devices, baseline)
    assert baseline[mac]["first_seen"] == first_seen_1


def test_empty_device_list_leaves_baseline_unchanged():
    baseline = {
        "aa:bb:cc:dd:ee:07": {
            "ip": "10.0.0.1", "hostname": "router", "vendor": "Ubiquiti",
            "first_seen": "2026-01-01T00:00:00", "last_seen": "2026-01-01T00:00:00",
        }
    }
    original_first = baseline["aa:bb:cc:dd:ee:07"]["first_seen"]
    new = diff_devices_against_baseline([], baseline)
    assert new == []
    assert baseline["aa:bb:cc:dd:ee:07"]["first_seen"] == original_first
