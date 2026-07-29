"""
Tests for modules/config_baseline.py and MetricStore config_snapshot CRUD.

Covers:
  - build_snapshot_from_scan: basic construction, port normalisation
  - store_snapshot / load_snapshot / list_snapshots / delete_snapshot
  - diff_snapshots: added/removed devices, port changes, field changes, SNMP changes
  - SnapshotDiff.has_drift and summary()
  - ConfigSnapshot JSON round-trip
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest

from modules.metric_store import MetricStore
from modules.config_baseline import (
    ConfigSnapshot,
    DeviceEntry,
    build_snapshot_from_scan,
    delete_snapshot,
    diff_snapshots,
    list_snapshots,
    load_snapshot,
    store_snapshot,
)


def _make_store():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    store = MetricStore(db_path=tmp.name)
    return store, tmp.name


class TestBuildSnapshot(unittest.TestCase):
    def test_basic(self):
        devices = [
            {"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "router",
             "open_ports": [80, 443], "vendor": "Cisco", "device_type": "Router"},
            {"ip": "192.168.1.2", "mac": "11:22:33:44:55:66", "hostname": "workstation",
             "open_ports": [22], "vendor": "Dell", "device_type": "PC"},
        ]
        snap = build_snapshot_from_scan(devices, label="test")
        assert len(snap.devices) == 2
        assert snap.label == "test"
        assert snap.id == 0  # not stored yet
        assert snap.devices[0].ip == "192.168.1.1"
        assert 80 in snap.devices[0].open_ports

    def test_ports_key_alias(self):
        """Should accept 'ports' as alias for 'open_ports'."""
        devices = [{"ip": "10.0.0.1", "ports": [22, 80]}]
        snap = build_snapshot_from_scan(devices)
        assert snap.devices[0].open_ports == [22, 80]

    def test_dict_ports(self):
        """port_scanner may return {port: {state: ...}} dicts."""
        devices = [{"ip": "10.0.0.1", "open_ports": {"22": {"state": "open"}, "80": {"state": "open"}}}]
        snap = build_snapshot_from_scan(devices)
        assert set(snap.devices[0].open_ports) == {22, 80}

    def test_empty_devices(self):
        snap = build_snapshot_from_scan([])
        assert snap.devices == []


class TestMetricStoreCrud(unittest.TestCase):
    def setUp(self):
        self.store, self.db_path = _make_store()

    def tearDown(self):
        self.store.close()
        os.unlink(self.db_path)

    def test_store_and_load(self):
        snap = build_snapshot_from_scan(
            [{"ip": "10.0.0.1", "open_ports": [80]}], label="first"
        )
        stored = store_snapshot(self.store, snap)
        assert stored.id > 0

        loaded = load_snapshot(self.store, stored.id)
        assert loaded is not None
        assert loaded.label == "first"
        assert loaded.devices[0].ip == "10.0.0.1"

    def test_load_nonexistent_returns_none(self):
        assert load_snapshot(self.store, 99999) is None

    def test_list_snapshots(self):
        for i in range(3):
            snap = build_snapshot_from_scan([], label=f"snap{i}")
            store_snapshot(self.store, snap)
        snaps = list_snapshots(self.store)
        assert len(snaps) == 3

    def test_list_limit(self):
        for i in range(5):
            store_snapshot(self.store, build_snapshot_from_scan([], label=f"s{i}"))
        snaps = list_snapshots(self.store, limit=2)
        assert len(snaps) == 2

    def test_delete_snapshot(self):
        snap = store_snapshot(self.store, build_snapshot_from_scan([], label="del"))
        delete_snapshot(self.store, snap.id)
        assert load_snapshot(self.store, snap.id) is None

    def test_json_roundtrip(self):
        devices = [{"ip": "1.2.3.4", "mac": "aa:bb:cc:dd:ee:01", "open_ports": [443]}]
        snap = build_snapshot_from_scan(devices, snmp_results={"1.2.3.4": {"sysDescr": "Linux"}})
        stored = store_snapshot(self.store, snap)
        loaded = load_snapshot(self.store, stored.id)
        assert loaded.snmp_data["1.2.3.4"]["sysDescr"] == "Linux"
        assert loaded.devices[0].mac == "aa:bb:cc:dd:ee:01"


class TestDiffSnapshots(unittest.TestCase):
    def _snap(self, devices, snmp=None, ts=None):
        return ConfigSnapshot(
            id=0, ts=ts or int(time.time()), label="",
            devices=[DeviceEntry(**d) for d in devices],
            snmp_data=snmp or {},
        )

    def test_no_diff(self):
        d = [{"ip": "10.0.0.1", "mac": "aa", "open_ports": [80]}]
        old = self._snap(d)
        new = self._snap(d)
        diff = diff_snapshots(old, new)
        assert not diff.has_drift

    def test_added_device(self):
        old = self._snap([{"ip": "10.0.0.1", "mac": "", "open_ports": []}])
        new = self._snap([
            {"ip": "10.0.0.1", "mac": "", "open_ports": []},
            {"ip": "10.0.0.2", "mac": "", "open_ports": []},
        ])
        diff = diff_snapshots(old, new)
        assert "10.0.0.2" in diff.added_devices
        assert diff.has_drift

    def test_removed_device(self):
        old = self._snap([
            {"ip": "10.0.0.1", "mac": "", "open_ports": []},
            {"ip": "10.0.0.2", "mac": "", "open_ports": []},
        ])
        new = self._snap([{"ip": "10.0.0.1", "mac": "", "open_ports": []}])
        diff = diff_snapshots(old, new)
        assert "10.0.0.2" in diff.removed_devices

    def test_port_opened(self):
        old = self._snap([{"ip": "10.0.0.1", "mac": "", "open_ports": [80]}])
        new = self._snap([{"ip": "10.0.0.1", "mac": "", "open_ports": [80, 443]}])
        diff = diff_snapshots(old, new)
        assert 443 in diff.changed_ports["10.0.0.1"]["added"]
        assert diff.changed_ports["10.0.0.1"]["removed"] == []

    def test_port_closed(self):
        old = self._snap([{"ip": "10.0.0.1", "mac": "", "open_ports": [22, 80]}])
        new = self._snap([{"ip": "10.0.0.1", "mac": "", "open_ports": [80]}])
        diff = diff_snapshots(old, new)
        assert 22 in diff.changed_ports["10.0.0.1"]["removed"]

    def test_field_change_hostname(self):
        old = self._snap([{"ip": "10.0.0.1", "mac": "aa", "hostname": "host-a", "open_ports": []}])
        new = self._snap([{"ip": "10.0.0.1", "mac": "aa", "hostname": "host-b", "open_ports": []}])
        diff = diff_snapshots(old, new)
        assert "hostname" in diff.changed_fields["10.0.0.1"]

    def test_snmp_change(self):
        old = self._snap([], snmp={"10.0.0.1": {"sysDescr": "Linux 5.4"}})
        new = self._snap([], snmp={"10.0.0.1": {"sysDescr": "Linux 6.1"}})
        diff = diff_snapshots(old, new)
        assert "sysDescr" in diff.changed_snmp["10.0.0.1"]
        assert diff.changed_snmp["10.0.0.1"]["sysDescr"]["old"] == "Linux 5.4"
        assert diff.changed_snmp["10.0.0.1"]["sysDescr"]["new"] == "Linux 6.1"

    def test_summary_no_drift(self):
        d = [{"ip": "10.0.0.1", "mac": "", "open_ports": []}]
        diff = diff_snapshots(self._snap(d), self._snap(d))
        assert diff.summary() == "No drift detected"

    def test_summary_multiple_changes(self):
        old = self._snap([{"ip": "10.0.0.1", "mac": "", "open_ports": [80]}])
        new = self._snap([
            {"ip": "10.0.0.1", "mac": "", "open_ports": [80, 443]},
            {"ip": "10.0.0.2", "mac": "", "open_ports": []},
        ])
        diff = diff_snapshots(old, new)
        summary = diff.summary()
        assert "added" in summary
        assert "port" in summary

    # ── S2 #2: a reused DHCP lease must not misattribute port changes ────────

    def test_reused_lease_is_not_read_as_a_port_change_on_the_old_device(self):
        """The exact live-DB shape: 192.168.68.55 changes hands from one
        physical device (MAC A, closed) to a different one (MAC B, port
        8443 open) between sweeps. Diffing by IP alone reads this as
        '192.168.68.55 gained port 8443' -- it is a different device."""
        old = self._snap([{"ip": "192.168.68.55", "mac": "aa:11:11:11:11:11", "open_ports": []}])
        new = self._snap([{"ip": "192.168.68.55", "mac": "bb:22:22:22:22:22", "open_ports": [8443]}])
        diff = diff_snapshots(old, new)
        assert "192.168.68.55" not in diff.changed_ports

    def test_same_device_diffs_correctly_even_after_its_ip_changes(self):
        """The MAC-first match must still catch a genuine port change for a
        device that also happens to have moved to a new IP via DHCP."""
        old = self._snap([{"ip": "192.168.68.55", "mac": "aa:11:11:11:11:11", "open_ports": []}])
        new = self._snap([{"ip": "192.168.68.60", "mac": "aa:11:11:11:11:11", "open_ports": [8443]}])
        diff = diff_snapshots(old, new)
        assert diff.changed_ports.get("192.168.68.60", {}).get("added") == [8443]

    def test_not_testable_entry_is_excluded_from_the_diff(self):
        old = self._snap([{"ip": "10.0.0.1", "mac": "aa", "open_ports": [22, 80]}])
        new = self._snap([{"ip": "10.0.0.1", "mac": "aa", "open_ports": [], "not_testable": True}])
        diff = diff_snapshots(old, new)
        assert "10.0.0.1" not in diff.changed_ports


class TestSnapshotJsonRoundtrip(unittest.TestCase):
    def test_to_json_from_row(self):
        snap = ConfigSnapshot(
            id=42, ts=1000000, label="test",
            devices=[DeviceEntry(ip="1.2.3.4", mac="aa", hostname="h", open_ports=[22])],
            snmp_data={"1.2.3.4": {"x": 1}},
        )
        row = {"id": 42, "ts": 1000000, "label": "test", "data_json": snap.to_json()}
        restored = ConfigSnapshot.from_row(row)
        assert restored.id == 42
        assert restored.devices[0].ip == "1.2.3.4"
        assert restored.devices[0].open_ports == [22]
        assert restored.snmp_data["1.2.3.4"]["x"] == 1


if __name__ == "__main__":
    unittest.main()
