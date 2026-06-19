"""Tests for modules/bandwidth_monitor.py — per-device bandwidth monitor."""
from modules.bandwidth_monitor import (
    SCAPY_AVAILABLE, BandwidthEntry, BandwidthSnapshot, BandwidthMonitor,
)


def test_import():
    import modules.bandwidth_monitor as m
    assert hasattr(m, "SCAPY_AVAILABLE")
    assert hasattr(m, "BandwidthMonitor")
    assert hasattr(m, "BandwidthSniffer")


def test_scapy_flag_is_bool():
    assert isinstance(SCAPY_AVAILABLE, bool)


def test_bandwidth_entry_defaults():
    entry = BandwidthEntry(mac="aa:bb:cc:dd:ee:ff")
    assert entry.mac == "aa:bb:cc:dd:ee:ff"
    assert entry.rx_bytes == 0
    assert entry.tx_bytes == 0
    assert entry.rx_bps == 0.0


def test_bandwidth_snapshot_fields():
    entry = BandwidthEntry(mac="aa:bb:cc:dd:ee:ff")
    import time
    snap = BandwidthSnapshot(entries={"aa:bb:cc:dd:ee:ff": entry}, window_s=5.0, timestamp=time.time())
    assert snap.window_s == 5.0
    assert "aa:bb:cc:dd:ee:ff" in snap.entries


def test_monitor_instantiates():
    mon = BandwidthMonitor()
    assert mon is not None
    assert mon.interval_s == 5.0


def test_monitor_stop_sets_event():
    mon = BandwidthMonitor()
    assert not mon.stop_event.is_set()
    mon.stop()
    assert mon.stop_event.is_set()


def test_monitor_run_no_scapy_calls_error(monkeypatch):
    monkeypatch.setattr("modules.bandwidth_monitor.SCAPY_AVAILABLE", False)
    errors = []
    mon = BandwidthMonitor(on_error=errors.append)
    mon.run()
    assert len(errors) == 1
    assert "Scapy" in errors[0]
