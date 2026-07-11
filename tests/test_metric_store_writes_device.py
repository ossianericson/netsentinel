"""
Tests for modules/metric_store_writes_device.py (_DeviceWritesMixin).

These methods are exercised indirectly by test_metric_store.py, test_device_tracker.py,
test_topology_snapshot.py, and test_rest_api.py — this file covers the mixin's
public surface directly to satisfy RULE-T1 (every module needs a test file).
"""
import pytest

from modules.metric_store import MetricStore


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


class TestIpObservation:
    def test_record_and_read_back(self, store):
        store.record_ip_observation("aa:bb:cc:00:01:01", "10.0.0.1")
        rows = [tuple(r) for r in store.get_ip_history_stats("aa:bb:cc:00:01:01")]
        assert rows == [("10.0.0.1", 1)]

    def test_repeat_observation_increments_seen_count(self, store):
        store.record_ip_observation("aa:bb:cc:00:01:02", "10.0.0.2")
        store.record_ip_observation("aa:bb:cc:00:01:02", "10.0.0.2")
        rows = [tuple(r) for r in store.get_ip_history_stats("aa:bb:cc:00:01:02")]
        assert rows == [("10.0.0.2", 2)]

    def test_empty_mac_or_ip_is_noop(self, store):
        store.record_ip_observation("", "10.0.0.3")
        store.record_ip_observation("aa:bb:cc:00:01:03", "")
        assert store.get_ip_history_stats("aa:bb:cc:00:01:03") == []

    def test_get_total_seen_count_sums_across_ips(self, store):
        mac = "aa:bb:cc:00:01:04"
        store.record_ip_observation(mac, "10.0.0.4")
        store.record_ip_observation(mac, "10.0.0.4")
        store.record_ip_observation(mac, "10.0.0.5")
        assert store.get_total_seen_count(mac) == 3

    def test_get_total_seen_count_unknown_mac_is_zero(self, store):
        assert store.get_total_seen_count("aa:bb:cc:ff:ff:ff") == 0


class TestDeviceStability:
    def test_update_with_role(self, store):
        mac = "aa:bb:cc:00:02:01"
        store.upsert_known_device(mac, ip="10.0.1.1")
        store.update_device_stability(mac, scan_count=5, ip_stability=0.9, inferred_role="gateway")
        kd = store.get_known_devices()[mac]
        assert kd.scan_count == 5
        assert abs(kd.ip_stability - 0.9) < 1e-9
        assert kd.inferred_role == "gateway"

    def test_update_without_role_preserves_existing(self, store):
        mac = "aa:bb:cc:00:02:02"
        store.upsert_known_device(mac, ip="10.0.1.2")
        store.update_device_stability(mac, scan_count=5, ip_stability=0.9, inferred_role="server")
        store.update_device_stability(mac, scan_count=6, ip_stability=0.95, inferred_role=None)
        kd = store.get_known_devices()[mac]
        assert kd.scan_count == 6
        assert kd.inferred_role == "server"


class TestDeviceAnnotations:
    def test_save_and_get(self, store):
        store.save_device_annotations("aa:bb:cc:00:03:01", user_label="Office PC", room="Office")
        ann = store.get_device_annotations("aa:bb:cc:00:03:01")
        assert ann["user_label"] == "Office PC"

    def test_get_missing_returns_empty_dict(self, store):
        assert store.get_device_annotations("aa:bb:cc:ff:ff:fe") == {}

    def test_get_all_returns_every_mac(self, store):
        store.save_device_annotations("aa:bb:cc:00:03:02", user_label="A")
        store.save_device_annotations("aa:bb:cc:00:03:03", user_label="B")
        all_ann = store.get_all_device_annotations()
        assert all_ann["aa:bb:cc:00:03:02"]["user_label"] == "A"
        assert all_ann["aa:bb:cc:00:03:03"]["user_label"] == "B"

    def test_partial_update_preserves_other_fields(self, store):
        mac = "aa:bb:cc:00:03:04"
        store.save_device_annotations(
            mac,
            user_label="Office PC",
            location="Server Room",
            owner="IT Dept",
            asset_tag="AT-042",
            notes="Original note",
        )
        store.save_device_annotations(mac, notes="Only updating the note")
        ann = store.get_device_annotations(mac)
        assert ann["notes"] == "Only updating the note"
        assert ann["user_label"] == "Office PC"
        assert ann["location"] == "Server Room"
        assert ann["owner"] == "IT Dept"
        assert ann["asset_tag"] == "AT-042"


class TestDeviceChangeEvents:
    def test_record_and_get(self, store):
        store.record_device_change_event("aa:bb:cc:00:04:01", "ip_changed", "10.0.0.1", "10.0.0.2", "scan")
        evs = store.get_device_change_events("aa:bb:cc:00:04:01")
        assert len(evs) == 1
        assert evs[0]["event_type"] == "ip_changed"

    def test_empty_mac_is_noop(self, store):
        store.record_device_change_event("", "ip_changed", "1", "2", "scan")
        assert store.get_all_device_change_events() == []

    def test_get_all_across_macs(self, store):
        store.record_device_change_event("aa:bb:cc:00:04:02", "hostname_changed", "old", "new", "scan")
        store.record_device_change_event("aa:bb:cc:00:04:03", "hostname_changed", "old2", "new2", "scan")
        all_evs = store.get_all_device_change_events()
        macs = {e["mac"] for e in all_evs}
        assert {"aa:bb:cc:00:04:02", "aa:bb:cc:00:04:03"} <= macs


class TestTopologySnapshots:
    def test_save_and_get_last(self, store):
        store.save_topology_snapshot(1000, '{"a": 1}')
        row = store.get_last_topology_snapshot()
        assert row == (1000, '{"a": 1}')

    def test_get_last_returns_none_when_empty(self, store):
        assert store.get_last_topology_snapshot() is None

    def test_prune_keeps_only_latest_n(self, store):
        for ts in range(15):
            store.save_topology_snapshot(ts, "{}", keep=10)
        rows = store._execute_read("SELECT COUNT(*) FROM topology_snapshots")
        assert rows[0][0] <= 10


class TestKnownDeviceWrites:
    def test_upsert_and_authorize(self, store):
        mac = "aa:bb:cc:00:05:01"
        store.upsert_known_device(mac, ip="10.0.2.1", vendor="Cisco")
        store.set_device_authorized(mac, False)
        kd = store.get_known_devices()[mac]
        assert kd.is_authorized is False

    def test_record_device_state(self, store):
        store.record_device_state("10.0.2.2", "aa:bb:cc:00:05:02", "host", "UP", rtt_ms=5.0)

    def test_record_device_event_rejects_invalid_type(self, store):
        with pytest.raises(ValueError):
            store.record_device_event("10.0.2.3", "NOT_A_TYPE")


class TestClassificationOverrides:
    def test_set_and_clear(self, store):
        mac = "aa:bb:cc:00:06:01"
        store.set_classification_override(mac, "Router")
        assert store.get_classification_override(mac) == "Router"
        store.clear_classification_override(mac)
        assert store.get_classification_override(mac) is None
