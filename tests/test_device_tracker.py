"""
Tests for modules/device_tracker.py
"""
import time
import pytest

from modules.metric_store import MetricStore
from modules.device_tracker import DeviceTracker, _normalise


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def tracker(store):
    return DeviceTracker(store=store, gone_threshold_s=3600)


def _dev(mac="aa:bb:cc:11:22:33", ip="192.168.1.10", host="mypc", vendor="Apple"):
    return {"mac": mac, "ip": ip, "hostname": host, "vendor": vendor, "device_type": "Laptop"}


# ── _normalise ────────────────────────────────────────────────────────────────

class TestNormalise:
    def test_dict_device(self):
        td = _normalise(_dev())
        assert td.mac == "aa:bb:cc:11:22:33"
        assert td.ip == "192.168.1.10"

    def test_object_device(self):
        class Obj:
            mac = "AA:BB:CC:11:22:33"
            ip = "10.0.0.1"
            hostname = "router"
            vendor = "Cisco"
            device_type = "Router"
            connection_type = ""
        td = _normalise(Obj())
        assert td.mac == "aa:bb:cc:11:22:33"

    def test_mac_normalised_to_lower(self):
        td = _normalise({"mac": "AA:BB:CC:DD:EE:FF", "ip": ""})
        assert td.mac == "aa:bb:cc:dd:ee:ff"

    def test_missing_mac_returns_none(self):
        assert _normalise({"ip": "1.2.3.4"}) is None

    def test_broadcast_mac_returns_none(self):
        assert _normalise({"mac": "ff:ff:ff:ff:ff:ff"}) is None

    def test_zero_mac_returns_none(self):
        assert _normalise({"mac": "00:00:00:00:00:00"}) is None

    def test_question_mark_mac_returns_none(self):
        assert _normalise({"mac": "?"}) is None

    def test_fallback_to_connection_type(self):
        td = _normalise({"mac": "aa:bb:cc:00:00:01", "device_type": "", "connection_type": "Ethernet"})
        assert td.device_type == "Ethernet"


# ── First scan — JOINED events ────────────────────────────────────────────────

class TestFirstScan:
    def test_new_device_in_result(self, tracker):
        result = tracker.process_scan([_dev()])
        assert len(result.new_devices) == 1
        assert result.new_devices[0].mac == "aa:bb:cc:11:22:33"

    def test_multiple_new_devices(self, tracker):
        devices = [
            _dev("aa:bb:cc:00:00:01", "10.0.0.1"),
            _dev("aa:bb:cc:00:00:02", "10.0.0.2"),
            _dev("aa:bb:cc:00:00:03", "10.0.0.3"),
        ]
        result = tracker.process_scan(devices)
        assert len(result.new_devices) == 3

    def test_joined_event_written_to_store(self, tracker, store):
        tracker.process_scan([_dev()])
        events = store.query_device_events(hours=1, event_types=["JOINED"])
        assert len(events) == 1
        assert events[0].event_type == "JOINED"

    def test_no_gone_devices_on_first_scan(self, tracker):
        result = tracker.process_scan([_dev()])
        assert result.gone_devices == []

    def test_total_known_updated(self, tracker, store):
        tracker.process_scan([_dev("aa:bb:cc:00:00:01"), _dev("aa:bb:cc:00:00:02")])
        result = tracker.process_scan([_dev("aa:bb:cc:00:00:01"), _dev("aa:bb:cc:00:00:02")])
        assert result.total_known == 2


# ── Second scan — same devices, no new events ─────────────────────────────────

class TestRepeatScan:
    def test_no_new_devices_on_second_scan(self, tracker):
        tracker.process_scan([_dev()])
        result = tracker.process_scan([_dev()])
        assert result.new_devices == []

    def test_joined_event_not_duplicated(self, tracker, store):
        tracker.process_scan([_dev()])
        tracker.process_scan([_dev()])
        events = store.query_device_events(hours=1, event_types=["JOINED"])
        assert len(events) == 1

    def test_known_device_upserted_with_new_ip(self, tracker, store):
        tracker.process_scan([_dev(mac="aa:bb:cc:11:22:33", ip="192.168.1.10")])
        tracker.process_scan([_dev(mac="aa:bb:cc:11:22:33", ip="192.168.1.99")])
        kd = store.get_known_devices().get("aa:bb:cc:11:22:33")
        assert kd.ip == "192.168.1.99"


# ── New device added on second scan ──────────────────────────────────────────

class TestNewDeviceAdded:
    def test_new_device_detected(self, tracker):
        tracker.process_scan([_dev("aa:bb:cc:00:00:01")])
        result = tracker.process_scan([
            _dev("aa:bb:cc:00:00:01"),
            _dev("aa:bb:cc:00:00:02"),
        ])
        assert len(result.new_devices) == 1
        assert result.new_devices[0].mac == "aa:bb:cc:00:00:02"


# ── Gone device detection ─────────────────────────────────────────────────────

class TestGoneDetection:
    def test_gone_device_detected(self, tmp_path):
        store = MetricStore(db_path=tmp_path / "gone.db")
        tracker = DeviceTracker(store=store, gone_threshold_s=1)

        tracker.process_scan([_dev("aa:bb:cc:00:00:01"), _dev("aa:bb:cc:00:00:02")])

        # Manually backdate last_seen for device 2 to simulate time passing
        store._execute_write(
            "UPDATE known_device SET last_seen = ? WHERE mac = ?",
            (int(time.time()) - 10, "aa:bb:cc:00:00:02"),
        )

        result = tracker.process_scan([_dev("aa:bb:cc:00:00:01")])
        store.close()

        assert len(result.gone_devices) == 1
        assert result.gone_devices[0].mac == "aa:bb:cc:00:00:02"

    def test_left_event_written_to_store(self, tmp_path):
        store = MetricStore(db_path=tmp_path / "left.db")
        tracker = DeviceTracker(store=store, gone_threshold_s=1)
        tracker.process_scan([_dev("aa:bb:cc:00:00:01"), _dev("aa:bb:cc:00:00:02")])
        store._execute_write(
            "UPDATE known_device SET last_seen = ? WHERE mac = ?",
            (int(time.time()) - 10, "aa:bb:cc:00:00:02"),
        )
        tracker.process_scan([_dev("aa:bb:cc:00:00:01")])
        events = store.query_device_events(hours=1, event_types=["LEFT"])
        store.close()
        assert len(events) == 1

    def test_left_not_duplicated_within_threshold(self, tmp_path):
        store = MetricStore(db_path=tmp_path / "nodup.db")
        tracker = DeviceTracker(store=store, gone_threshold_s=1)
        tracker.process_scan([_dev("aa:bb:cc:00:00:01"), _dev("aa:bb:cc:00:00:02")])
        store._execute_write(
            "UPDATE known_device SET last_seen = ? WHERE mac = ?",
            (int(time.time()) - 10, "aa:bb:cc:00:00:02"),
        )
        # Two consecutive scans without device 2 — LEFT event emitted only once
        tracker.process_scan([_dev("aa:bb:cc:00:00:01")])
        tracker.process_scan([_dev("aa:bb:cc:00:00:01")])
        events = store.query_device_events(hours=1, event_types=["LEFT"])
        store.close()
        assert len(events) == 1

    def test_gone_threshold_zero_disables_left_events(self, tmp_path):
        store = MetricStore(db_path=tmp_path / "noleft.db")
        tracker = DeviceTracker(store=store, gone_threshold_s=0)
        tracker.process_scan([_dev("aa:bb:cc:00:00:01"), _dev("aa:bb:cc:00:00:02")])
        result = tracker.process_scan([_dev("aa:bb:cc:00:00:01")])
        store.close()
        assert result.gone_devices == []


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_scan_returns_empty_result(self, tracker):
        result = tracker.process_scan([])
        assert result.new_devices == []
        assert result.gone_devices == []

    def test_device_without_mac_ignored(self, tracker):
        result = tracker.process_scan([{"ip": "192.168.1.1"}])
        assert result.new_devices == []

    def test_mixed_valid_invalid_devices(self, tracker):
        devices = [
            {"ip": "192.168.1.1"},                        # no mac — ignored
            _dev("aa:bb:cc:00:00:01"),                    # valid
            {"mac": "ff:ff:ff:ff:ff:ff", "ip": "x"},    # broadcast — ignored
        ]
        result = tracker.process_scan(devices)
        assert len(result.new_devices) == 1

    def test_scan_ts_is_recent(self, tracker):
        before = int(time.time())
        result = tracker.process_scan([_dev()])
        assert result.scan_ts >= before


# ── Annotations ───────────────────────────────────────────────────────────────

from modules.device_tracker import (
    get_all_annotations, get_annotations, record_ip_observation,
    get_ip_history, save_annotations,
)


class TestAnnotations:
    def test_save_and_get(self, store):
        save_annotations("aa:bb:cc:11:22:33", store, user_label="Living Room TV")
        ann = get_annotations("aa:bb:cc:11:22:33", store)
        assert ann["user_label"] == "Living Room TV"

    def test_get_missing_returns_empty_dict(self, store):
        assert get_annotations("ff:ff:ff:ff:ff:ff", store) == {}

    def test_all_fields_persisted(self, store):
        save_annotations(
            "aa:bb:cc:00:00:01", store,
            user_label="Router",
            location="Rack 1",
            owner="IT",
            notes="Replaced 2024",
            asset_tag="INV-001",
        )
        ann = get_annotations("aa:bb:cc:00:00:01", store)
        assert ann["location"] == "Rack 1"
        assert ann["owner"] == "IT"
        assert ann["notes"] == "Replaced 2024"
        assert ann["asset_tag"] == "INV-001"

    def test_upsert_overwrites_existing(self, store):
        save_annotations("aa:bb:cc:00:00:02", store, user_label="Old Label")
        save_annotations("aa:bb:cc:00:00:02", store, user_label="New Label")
        ann = get_annotations("aa:bb:cc:00:00:02", store)
        assert ann["user_label"] == "New Label"

    def test_mac_normalised_to_lower(self, store):
        save_annotations("AA:BB:CC:00:00:03", store, user_label="Test")
        ann = get_annotations("aa:bb:cc:00:00:03", store)
        assert ann["user_label"] == "Test"

    def test_get_all_annotations_returns_all(self, store):
        save_annotations("aa:bb:cc:00:00:04", store, user_label="A")
        save_annotations("aa:bb:cc:00:00:05", store, user_label="B")
        all_ann = get_all_annotations(store)
        assert all_ann.get("aa:bb:cc:00:00:04", {}).get("user_label") == "A"
        assert all_ann.get("aa:bb:cc:00:00:05", {}).get("user_label") == "B"

    def test_get_all_annotations_empty_store(self, store):
        assert get_all_annotations(store) == {}


# ── IP History ────────────────────────────────────────────────────────────────

class TestIpHistory:
    def test_record_and_retrieve(self, store):
        record_ip_observation("aa:bb:cc:11:22:33", "192.168.1.10", store)
        hist = get_ip_history("aa:bb:cc:11:22:33", store)
        assert len(hist) == 1
        assert hist[0]["ip"] == "192.168.1.10"
        assert hist[0]["seen_count"] == 1

    def test_upsert_increments_count(self, store):
        record_ip_observation("aa:bb:cc:00:00:06", "10.0.0.1", store)
        record_ip_observation("aa:bb:cc:00:00:06", "10.0.0.1", store)
        record_ip_observation("aa:bb:cc:00:00:06", "10.0.0.1", store)
        hist = get_ip_history("aa:bb:cc:00:00:06", store)
        assert len(hist) == 1
        assert hist[0]["seen_count"] == 3

    def test_multiple_ips_tracked(self, store):
        record_ip_observation("aa:bb:cc:00:00:07", "10.0.0.5", store)
        record_ip_observation("aa:bb:cc:00:00:07", "10.0.0.9", store)
        hist = get_ip_history("aa:bb:cc:00:00:07", store)
        ips = {h["ip"] for h in hist}
        assert ips == {"10.0.0.5", "10.0.0.9"}

    def test_empty_mac_ignored(self, store):
        record_ip_observation("", "10.0.0.1", store)
        assert get_ip_history("", store) == []

    def test_empty_ip_ignored(self, store):
        record_ip_observation("aa:bb:cc:00:00:08", "", store)
        assert get_ip_history("aa:bb:cc:00:00:08", store) == []

    def test_mac_normalised_to_lower(self, store):
        record_ip_observation("AA:BB:CC:00:00:09", "10.0.0.2", store)
        hist = get_ip_history("aa:bb:cc:00:00:09", store)
        assert len(hist) == 1

    def test_history_sorted_by_last_seen_desc(self, store):
        record_ip_observation("aa:bb:cc:00:00:0a", "10.0.0.1", store)
        record_ip_observation("aa:bb:cc:00:00:0a", "10.0.0.2", store)
        # Manually set first IP's last_seen to be older
        store._execute_write(
            "UPDATE device_ip_history SET last_seen = '2020-01-01 00:00:00' WHERE ip = ?",
            ("10.0.0.1",),
        )
        hist = get_ip_history("aa:bb:cc:00:00:0a", store)
        assert hist[0]["ip"] == "10.0.0.2"
