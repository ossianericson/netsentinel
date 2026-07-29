"""Tests for modules/port_sweep.py (V6 Sprint 3.1 — nightly port-scan sweep)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from modules.config_baseline import build_snapshot_from_scan
from modules.port_scanner import PortResult, PortScanResult


def _known_device(ip: str, mac: str = "aa:bb:cc:dd:ee:ff", hostname: str = "") -> dict:
    return {
        "mac": mac, "ip": ip, "hostname": hostname, "vendor": "", "device_type": "",
        "first_seen": 0, "last_seen": 0, "is_authorized": True, "category": "",
        "custom_name": "", "room": "",
    }


def _scan_result(host: str, ports: list) -> PortScanResult:
    return PortScanResult(
        host=host, ip=host,
        open_ports=[PortResult(port=p, name=f"port{p}", open=True) for p in ports],
        scanned=len(ports),
    )


def test_import():
    from modules.port_sweep import run_nightly_port_sweep, PortSweepReport
    assert run_nightly_port_sweep is not None
    assert PortSweepReport is not None


def test_first_run_stores_snapshot_with_no_diff():
    """With no prior posture_port_sweep snapshot, the first run reports zero new ports."""
    from modules.port_sweep import run_nightly_port_sweep

    store = MagicMock()
    store.query_known_devices_summary.return_value = [_known_device("192.168.1.40")]
    store.list_snapshots.return_value = []  # no prior snapshot
    store.store_snapshot.return_value = 1

    with patch("modules.port_sweep.port_scanner.scan", return_value=_scan_result("192.168.1.40", [22, 80])):
        report = run_nightly_port_sweep(store)

    assert report.new_ports == []
    assert len(report.all_devices) == 1
    assert report.all_devices[0].open_ports == [22, 80]


def test_second_run_detects_newly_opened_port():
    """A port that wasn't open on the prior sweep but is now must be flagged."""
    from modules.port_sweep import run_nightly_port_sweep

    store = MagicMock()
    store.query_known_devices_summary.return_value = [_known_device("192.168.1.40")]

    prior_snap = build_snapshot_from_scan(
        [{"ip": "192.168.1.40", "open_ports": [22, 80]}],
        label="posture_port_sweep",
    )
    prior_snap.id = 1
    prior_snap.ts = 1000
    prior_row = {"id": 1, "ts": 1000, "label": "posture_port_sweep", "data_json": prior_snap.to_json()}

    store.list_snapshots.return_value = [prior_row]
    store.store_snapshot.return_value = 2

    with patch("modules.port_sweep.port_scanner.scan", return_value=_scan_result("192.168.1.40", [22, 80, 23])):
        report = run_nightly_port_sweep(store)

    assert report.new_ports == [("192.168.1.40", 23)]


def test_ignores_snapshots_with_a_different_label():
    """User-triggered config baseline snapshots must not be mistaken for the sweep's own history."""
    from modules.port_sweep import run_nightly_port_sweep

    store = MagicMock()
    store.query_known_devices_summary.return_value = [_known_device("192.168.1.40")]

    unrelated_snap = build_snapshot_from_scan(
        [{"ip": "192.168.1.40", "open_ports": [22]}], label="user_baseline",
    )
    unrelated_row = {"id": 5, "ts": 500, "label": "user_baseline", "data_json": unrelated_snap.to_json()}
    store.list_snapshots.return_value = [unrelated_row]
    store.store_snapshot.return_value = 6

    with patch("modules.port_sweep.port_scanner.scan", return_value=_scan_result("192.168.1.40", [22, 80])):
        report = run_nightly_port_sweep(store)

    # No same-label prior snapshot found -> treated as first run, no diff.
    assert report.new_ports == []


def test_skips_devices_with_no_ip():
    from modules.port_sweep import run_nightly_port_sweep

    store = MagicMock()
    store.query_known_devices_summary.return_value = [_known_device(""), _known_device("192.168.1.40")]
    store.list_snapshots.return_value = []
    store.store_snapshot.return_value = 1

    with patch("modules.port_sweep.port_scanner.scan", return_value=_scan_result("192.168.1.40", [22])) as mock_scan:
        run_nightly_port_sweep(store)

    mock_scan.assert_called_once_with("192.168.1.40")


# ── S2 #1: an unreachable device is not_testable, not "zero open ports" ───────

def test_unreachable_device_is_marked_not_testable():
    from modules.port_sweep import run_nightly_port_sweep

    store = MagicMock()
    store.query_known_devices_summary.return_value = [_known_device("192.168.1.41")]
    store.list_snapshots.return_value = []
    store.store_snapshot.return_value = 1

    with patch("modules.port_sweep.port_scanner.scan", return_value=_scan_result("192.168.1.41", [])), \
         patch("modules.port_sweep.icmp_ping", return_value=-1.0):
        report = run_nightly_port_sweep(store)

    assert report.all_devices[0].not_testable is True


def test_reachable_device_with_zero_ports_is_not_flagged_not_testable():
    """A genuinely reachable device with nothing open must not be confused
    with a device that simply never answered."""
    from modules.port_sweep import run_nightly_port_sweep

    store = MagicMock()
    store.query_known_devices_summary.return_value = [_known_device("192.168.1.41")]
    store.list_snapshots.return_value = []
    store.store_snapshot.return_value = 1

    with patch("modules.port_sweep.port_scanner.scan", return_value=_scan_result("192.168.1.41", [])), \
         patch("modules.port_sweep.icmp_ping", return_value=12.5):
        report = run_nightly_port_sweep(store)

    assert report.all_devices[0].not_testable is False


def test_a_sweep_that_missed_a_device_does_not_flood_new_ports_next_time():
    """The exact live-DB shape: a device asleep on sweep 2 (not_testable, no
    diff against sweep 1) must not make sweep 3 read its whole open-port set
    as newly opened."""
    from modules.port_sweep import run_nightly_port_sweep

    store = MagicMock()
    store.query_known_devices_summary.return_value = [_known_device("192.168.1.41")]

    # Sweep 1: device answers with 2 open ports.
    with patch("modules.port_sweep.port_scanner.scan", return_value=_scan_result("192.168.1.41", [22, 80])), \
         patch("modules.port_sweep.icmp_ping", return_value=5.0):
        store.list_snapshots.return_value = []
        store.store_snapshot.side_effect = None
        store.store_snapshot.return_value = 1
        report1 = run_nightly_port_sweep(store)
    snap1_row = {
        "id": 1, "ts": 1000, "label": "posture_port_sweep",
        "data_json": report1.snapshot.to_json(),
    }

    # Sweep 2: device is asleep -- zero ports, no ping reply.
    with patch("modules.port_sweep.port_scanner.scan", return_value=_scan_result("192.168.1.41", [])), \
         patch("modules.port_sweep.icmp_ping", return_value=-1.0):
        store.list_snapshots.return_value = [snap1_row]
        store.store_snapshot.return_value = 2
        report2 = run_nightly_port_sweep(store)
    assert report2.new_ports == [], "an unreachable sweep must never report closed-then-reopened ports"
    snap2_row = {
        "id": 2, "ts": 2000, "label": "posture_port_sweep",
        "data_json": report2.snapshot.to_json(),
    }

    # Sweep 3: device answers again with the SAME 2 ports as sweep 1.
    with patch("modules.port_sweep.port_scanner.scan", return_value=_scan_result("192.168.1.41", [22, 80])), \
         patch("modules.port_sweep.icmp_ping", return_value=5.0):
        store.list_snapshots.return_value = [snap2_row]
        store.store_snapshot.return_value = 3
        report3 = run_nightly_port_sweep(store)

    assert report3.new_ports == [], (
        "diffing against a not_testable prior sweep must not read ports the "
        "device had all along as newly opened"
    )


# ── S2 #3: device-type-expected ports are suppressed ──────────────────────────

def test_expected_port_for_device_type_is_not_reported_as_new():
    from modules.port_sweep import run_nightly_port_sweep

    store = MagicMock()
    store.query_known_devices_summary.return_value = [
        {**_known_device("192.168.1.52"), "device_type": "Streaming Stick"}
    ]

    prior_snap = build_snapshot_from_scan(
        [{"ip": "192.168.1.52", "open_ports": [], "device_type": "Streaming Stick"}],
        label="posture_port_sweep",
    )
    prior_snap.id = 1
    prior_snap.ts = 1000
    prior_row = {"id": 1, "ts": 1000, "label": "posture_port_sweep", "data_json": prior_snap.to_json()}
    store.list_snapshots.return_value = [prior_row]
    store.store_snapshot.return_value = 2

    with patch("modules.port_sweep.port_scanner.scan", return_value=_scan_result("192.168.1.52", [49152])), \
         patch("modules.port_sweep.icmp_ping", return_value=5.0):
        report = run_nightly_port_sweep(store)

    assert report.new_ports == [], "UPnP SSDP on a streaming stick is expected, not a security event"
