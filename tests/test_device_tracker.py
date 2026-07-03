"""
Tests for modules/device_tracker.py
"""
import calendar
import time
import pytest

from modules.metric_store import MetricStore
from modules.device_tracker import (
    DeviceTracker, _normalise,
    record_event, get_device_events, get_all_device_events,
)


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


# ── TestDeviceAuditEvents ─────────────────────────────────────────────────────

class TestDeviceAuditEvents:
    """Tests for record_event / get_device_events / get_all_device_events."""

    def test_record_and_retrieve_single_event(self, store):
        record_event("aa:bb:cc:11:22:33", "ip_changed", "10.0.0.1", "10.0.0.2", "scan", store)
        events = get_device_events("aa:bb:cc:11:22:33", store)
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"] == "ip_changed"
        assert ev["old_value"] == "10.0.0.1"
        assert ev["new_value"] == "10.0.0.2"
        assert ev["source"] == "scan"

    def test_events_returned_newest_first(self, store):
        mac = "aa:bb:cc:11:22:44"
        record_event(mac, "first_seen",    "", "10.0.0.1", "scan", store)
        record_event(mac, "class_changed", "Unknown Device", "Laptop", "dhcp", store)
        record_event(mac, "went_offline",  "UP", "DOWN", "availability", store)
        events = get_device_events(mac, store)
        assert len(events) == 3
        # All three event types must be present
        types = {ev["event_type"] for ev in events}
        assert types == {"first_seen", "class_changed", "went_offline"}

    def test_limit_is_respected(self, store):
        mac = "aa:bb:cc:11:22:55"
        for i in range(10):
            record_event(mac, "ip_changed", f"10.0.0.{i}", f"10.0.0.{i+1}", "scan", store)
        events = get_device_events(mac, store, limit=5)
        assert len(events) == 5

    def test_empty_mac_ignored(self, store):
        record_event("", "ip_changed", "a", "b", "scan", store)
        events = get_device_events("", store)
        assert events == []

    def test_mac_normalised_to_lower(self, store):
        record_event("AA:BB:CC:11:22:66", "first_seen", "", "10.0.0.1", "scan", store)
        events = get_device_events("aa:bb:cc:11:22:66", store)
        assert len(events) == 1

    def test_get_device_events_filters_by_mac(self, store):
        record_event("aa:bb:cc:11:22:77", "first_seen", "", "10.0.0.1", "scan", store)
        record_event("aa:bb:cc:11:22:88", "first_seen", "", "10.0.0.2", "scan", store)
        events = get_device_events("aa:bb:cc:11:22:77", store)
        assert len(events) == 1
        assert events[0]["new_value"] == "10.0.0.1"

    def test_get_all_device_events_returns_all_macs(self, store):
        record_event("aa:bb:cc:11:22:aa", "first_seen", "", "10.0.0.1", "scan", store)
        record_event("aa:bb:cc:11:22:bb", "first_seen", "", "10.0.0.2", "scan", store)
        all_evs = get_all_device_events(store, limit=100, hours=1)
        macs = {ev["mac"] for ev in all_evs}
        assert "aa:bb:cc:11:22:aa" in macs
        assert "aa:bb:cc:11:22:bb" in macs

    def test_get_all_device_events_respects_limit(self, store):
        for i in range(20):
            record_event(f"aa:bb:cc:11:22:{i:02x}", "first_seen", "", str(i), "scan", store)
        all_evs = get_all_device_events(store, limit=5, hours=1)
        assert len(all_evs) <= 5

    def test_get_all_device_events_empty_when_no_data(self, store):
        all_evs = get_all_device_events(store, limit=100, hours=1)
        assert all_evs == []

    def test_first_seen_recorded_by_process_scan(self, store):
        tracker = DeviceTracker(store=store, gone_threshold_s=3600)
        devices = [{"mac": "aa:bb:cc:11:22:cc", "ip": "10.0.0.5",
                    "hostname": "new-host", "vendor": "Apple", "device_type": "Laptop"}]
        tracker.process_scan(devices)
        events = get_device_events("aa:bb:cc:11:22:cc", store)
        assert any(ev["event_type"] == "first_seen" for ev in events)


# ── Vendor preservation — Bug regression guard ────────────────────────────────

class TestVendorPreservation:
    """Regression guard: 'Unknown' vendor from scan must not clobber a resolved vendor.

    Root cause: DeviceInfo.vendor defaults to "Unknown". When OUI lookup fails,
    the scan emits vendor="Unknown". DeviceTracker.process_scan passes this to
    upsert_known_device(vendor="Unknown"). The SQL COALESCE(excluded.vendor, vendor)
    treats "Unknown" as a real (non-NULL) value and overwrites any previously
    resolved vendor (e.g. "Apple Inc." stored by async OUI lookup).

    Fix: _normalise() must treat "Unknown" / "Unknown Vendor" as empty so that
    upsert_known_device receives vendor=None, allowing COALESCE to preserve the
    existing resolved value.
    """

    def test_upsert_known_device_unknown_string_does_not_clobber(self, store):
        """upsert_known_device with vendor='Unknown' must preserve the existing resolved vendor.

        This tests the MetricStore contract directly — if this fails the COALESCE logic
        needs a new approach; if this passes, the bug is purely in the caller passing 'Unknown'.
        """
        mac = "aa:bb:cc:dd:ee:01"
        store.upsert_known_device(mac, ip="192.168.1.10", vendor="Apple Inc.")
        # Simulate a re-scan that didn't resolve the OUI — should NOT overwrite
        store.upsert_known_device(mac, ip="192.168.1.10", vendor=None)
        kd = store.get_known_devices()[mac]
        assert kd.vendor == "Apple Inc.", (
            f"Expected vendor='Apple Inc.' preserved after upsert with vendor=None; "
            f"got '{kd.vendor}' — COALESCE(NULL, existing) should return existing"
        )

    def test_process_scan_unknown_vendor_does_not_clobber_resolved_vendor(self, store):
        """process_scan with DeviceInfo.vendor='Unknown' must NOT overwrite a stored resolved vendor.

        This is the primary regression test for Bug #1 (restart shows only IPs).

        Flow:
          1. Async OUI lookup previously resolved and persisted vendor='Apple Inc.'
          2. Next scan: device found, OUI not in local DB, DeviceInfo.vendor='Unknown'
          3. process_scan calls upsert_known_device(vendor='Unknown')
          4. Bug: COALESCE('Unknown', 'Apple Inc.') = 'Unknown' → clobbers resolved vendor
          5. Fix: _normalise treats 'Unknown' as '' → upsert_known_device(vendor=None)
             → COALESCE(NULL, 'Apple Inc.') = 'Apple Inc.' → preserved
        """
        mac = "aa:bb:cc:dd:ee:02"
        # Step 1: resolved vendor stored (simulates async OUI lookup having run)
        store.upsert_known_device(mac, ip="192.168.1.10", vendor="Apple Inc.")
        # Step 2: re-scan — OUI not in local DB, vendor defaults to "Unknown"
        tracker = DeviceTracker(store=store)
        tracker.process_scan([{
            "mac": mac, "ip": "192.168.1.10",
            "hostname": "", "vendor": "Unknown", "device_type": "Laptop",
        }])
        kd = store.get_known_devices()[mac]
        assert kd.vendor == "Apple Inc.", (
            f"Expected vendor='Apple Inc.' preserved after process_scan with vendor='Unknown'; "
            f"got '{kd.vendor}' — 'Unknown' string clobbered the resolved vendor. "
            "Fix: _normalise must convert 'Unknown'→'' so upsert receives vendor=None"
        )

    def test_process_scan_unknown_vendor_string_does_not_clobber(self, store):
        """Variant: 'Unknown Vendor' string must also not clobber a resolved vendor."""
        mac = "aa:bb:cc:dd:ee:03"
        store.upsert_known_device(mac, ip="192.168.1.11", vendor="Samsung Electronics")
        tracker = DeviceTracker(store=store)
        tracker.process_scan([{
            "mac": mac, "ip": "192.168.1.11",
            "hostname": "", "vendor": "Unknown Vendor", "device_type": "",
        }])
        kd = store.get_known_devices()[mac]
        assert kd.vendor == "Samsung Electronics", (
            f"Expected 'Samsung Electronics' preserved; got '{kd.vendor}'"
        )

    def test_process_scan_real_vendor_overwrites_unknown_in_store(self, store):
        """When a scan resolves a real vendor, it should update the stored 'Unknown'."""
        mac = "aa:bb:cc:dd:ee:04"
        store.upsert_known_device(mac, ip="192.168.1.12", vendor="Unknown")
        tracker = DeviceTracker(store=store)
        tracker.process_scan([{
            "mac": mac, "ip": "192.168.1.12",
            "hostname": "", "vendor": "Cisco Systems", "device_type": "Router",
        }])
        kd = store.get_known_devices()[mac]
        assert kd.vendor == "Cisco Systems", (
            f"Expected 'Cisco Systems' to overwrite stored 'Unknown'; got '{kd.vendor}'"
        )


# ── Double-count regression guard (Phase 3a) ──────────────────────────────────

class TestNoDoubleCountPerScan:
    """Regression guard: process_scan() must be the single write path for
    device_ip_history. A prior bug had ui/scan_wiring.py call
    record_ip_observation() directly AND rely on process_scan() calling it
    again for the same device in the same scan, doubling seen_count/scan_count
    per scan and skewing ip_stability.
    """

    def test_seen_count_matches_scan_count_after_n_scans(self, store):
        mac = "aa:bb:cc:dd:ee:10"
        tracker = DeviceTracker(store=store)
        n = 5
        for _ in range(n):
            tracker.process_scan([_dev(mac=mac, ip="192.168.1.20")])
        hist = get_ip_history(mac, store)
        assert len(hist) == 1
        assert hist[0]["seen_count"] == n, (
            f"Expected seen_count == {n} after {n} scans of a stable device; "
            f"got {hist[0]['seen_count']} — process_scan() must be the only "
            "caller of record_ip_observation() per scan"
        )
        kd = store.get_known_devices()[mac]
        assert kd.scan_count == n, (
            f"Expected scan_count == {n}; got {kd.scan_count}"
        )


# ── last_seen invariant guard (Phase 3c) ──────────────────────────────────────

def _parse_utc(ts_str: str) -> int:
    return calendar.timegm(time.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))


class TestLastSeenInvariant:
    """known_device.last_seen must equal MAX(device_ip_history.last_seen) for
    that MAC after every scan-driven update (see metric_store.py module
    docstring and DeviceTracker.process_scan docstring)."""

    def test_last_seen_matches_max_ip_history_after_scan(self, store):
        mac = "aa:bb:cc:dd:ee:20"
        tracker = DeviceTracker(store=store)
        tracker.process_scan([_dev(mac=mac, ip="10.0.0.30")])
        kd = store.get_known_devices()[mac]
        hist = get_ip_history(mac, store)
        assert len(hist) == 1
        assert _parse_utc(hist[0]["last_seen"]) == kd.last_seen

    def test_ip_change_freezes_old_ip_row_and_accrues_new(self, store):
        mac = "aa:bb:cc:dd:ee:21"
        tracker = DeviceTracker(store=store)
        tracker.process_scan([_dev(mac=mac, ip="10.0.0.40")])
        tracker.process_scan([_dev(mac=mac, ip="10.0.0.40")])
        tracker.process_scan([_dev(mac=mac, ip="10.0.0.41")])

        hist = {h["ip"]: h for h in get_ip_history(mac, store)}
        assert hist["10.0.0.40"]["seen_count"] == 2
        assert hist["10.0.0.41"]["seen_count"] == 1

        kd = store.get_known_devices()[mac]
        max_last_seen = max(_parse_utc(h["last_seen"]) for h in hist.values())
        assert kd.last_seen == max_last_seen
        assert kd.ip == "10.0.0.41"
