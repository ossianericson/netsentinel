"""
Tests for modules/metric_store.py — SQLite backend.
All tests use an in-memory database so no files are created on disk.
"""
import time
import threading
import pytest

from modules.metric_store import (
    MetricStore,
    RttPoint,
    DeviceStatePoint,
    DeviceEvent,
    KnownDevice,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    """Fresh on-disk MetricStore for each test (tmp_path is unique per test)."""
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def mem_store():
    """In-memory store for tests that explicitly need it."""
    s = MetricStore(db_path=":memory:")
    yield s
    s.close()


# ── Construction & schema ─────────────────────────────────────────────────────

class TestConstruction:
    def test_opens_in_memory(self, mem_store):
        counts = mem_store.get_row_counts()
        assert set(counts.keys()) == {"rtt_sample", "device_state", "device_event", "known_device", "cert_check", "service_check", "speed_test", "ha_detected"}

    def test_row_counts_start_at_zero(self, store):
        for v in store.get_row_counts().values():
            assert v == 0

    def test_sqlalchemy_missing_raises(self):
        """Passing backend_url without sqlalchemy installed raises ImportError."""
        import sys
        # Temporarily hide sqlalchemy if present
        sa = sys.modules.pop("sqlalchemy", None)
        try:
            with pytest.raises(ImportError, match="SQLAlchemy"):
                MetricStore(backend_url="postgresql://fake/fake")
        finally:
            if sa is not None:
                sys.modules["sqlalchemy"] = sa


# ── record_rtt / query_rtt_history ───────────────────────────────────────────

class TestRttSamples:
    def test_record_and_retrieve(self, store):
        now = int(time.time())
        store.record_rtt("8.8.8.8", 14.2, 0.0, 1.1, ts=now)
        pts = store.query_rtt_history("8.8.8.8", hours=1)
        assert len(pts) == 1
        p = pts[0]
        assert isinstance(p, RttPoint)
        assert p.host == "8.8.8.8"
        assert p.rtt_ms == pytest.approx(14.2)
        assert p.loss_pct == pytest.approx(0.0)
        assert p.jitter_ms == pytest.approx(1.1)
        assert p.ts == now

    def test_multiple_hosts_isolated(self, store):
        now = int(time.time())
        store.record_rtt("1.1.1.1", 10.0, ts=now)
        store.record_rtt("8.8.8.8", 20.0, ts=now)
        assert len(store.query_rtt_history("1.1.1.1", hours=1)) == 1
        assert len(store.query_rtt_history("8.8.8.8", hours=1)) == 1

    def test_oldest_first_ordering(self, store):
        base = int(time.time()) - 7200
        for i in range(5):
            store.record_rtt("host.test", float(i * 10), ts=base + i * 60)
        pts = store.query_rtt_history("host.test", hours=3)
        assert len(pts) == 5
        assert pts[0].rtt_ms == pytest.approx(0.0)
        assert pts[-1].rtt_ms == pytest.approx(40.0)

    def test_window_filters_old_records(self, store):
        old_ts  = int(time.time()) - 48 * 3600
        new_ts  = int(time.time()) - 30 * 60
        store.record_rtt("host.test", 5.0,  ts=old_ts)
        store.record_rtt("host.test", 15.0, ts=new_ts)
        pts = store.query_rtt_history("host.test", hours=1)
        assert len(pts) == 1
        assert pts[0].rtt_ms == pytest.approx(15.0)

    def test_unreachable_recorded_as_minus_one(self, store):
        store.record_rtt("dead.host", -1.0, loss_pct=100.0)
        pts = store.query_rtt_history("dead.host", hours=1)
        assert pts[0].rtt_ms == pytest.approx(-1.0)
        assert pts[0].loss_pct == pytest.approx(100.0)

    def test_query_all_rtt_hosts(self, store):
        now = int(time.time())
        for h in ("a.test", "b.test", "c.test"):
            store.record_rtt(h, 1.0, ts=now)
        hosts = store.query_all_rtt_hosts(hours=1)
        assert set(hosts) == {"a.test", "b.test", "c.test"}

    def test_query_all_rtt_hosts_empty_outside_window(self, store):
        old_ts = int(time.time()) - 48 * 3600
        store.record_rtt("old.host", 1.0, ts=old_ts)
        assert store.query_all_rtt_hosts(hours=1) == []

    def test_default_jitter_is_minus_one(self, store):
        store.record_rtt("host.test", 10.0)
        pts = store.query_rtt_history("host.test", hours=1)
        assert pts[0].jitter_ms == pytest.approx(-1.0)


# ── record_device_state / query_device_state_history ─────────────────────────

class TestDeviceState:
    def test_record_and_retrieve(self, store):
        now = int(time.time())
        store.record_device_state("192.168.1.1", "aa:bb:cc", "router", "UP", 5.0, ts=now)
        pts = store.query_device_state_history("192.168.1.1", hours=1)
        assert len(pts) == 1
        p = pts[0]
        assert isinstance(p, DeviceStatePoint)
        assert p.ip == "192.168.1.1"
        assert p.mac == "aa:bb:cc"
        assert p.state == "UP"
        assert p.rtt_ms == pytest.approx(5.0)

    def test_state_uppercased(self, store):
        store.record_device_state("10.0.0.1", None, None, "down")
        pts = store.query_device_state_history("10.0.0.1", hours=1)
        assert pts[0].state == "DOWN"

    def test_multiple_states_oldest_first(self, store):
        base = int(time.time()) - 3600
        states = ["UP", "DEGRADED", "DOWN", "UP"]
        for i, st in enumerate(states):
            store.record_device_state("10.0.0.2", None, None, st, ts=base + i * 300)
        pts = store.query_device_state_history("10.0.0.2", hours=2)
        assert [p.state for p in pts] == states

    def test_window_filters_old_records(self, store):
        old_ts = int(time.time()) - 48 * 3600
        new_ts = int(time.time()) - 5 * 60
        store.record_device_state("10.0.0.3", None, None, "DOWN", ts=old_ts)
        store.record_device_state("10.0.0.3", None, None, "UP",   ts=new_ts)
        pts = store.query_device_state_history("10.0.0.3", hours=1)
        assert len(pts) == 1
        assert pts[0].state == "UP"

    def test_none_rtt_allowed(self, store):
        store.record_device_state("10.0.0.4", None, None, "DOWN", rtt_ms=None)
        pts = store.query_device_state_history("10.0.0.4", hours=1)
        assert pts[0].rtt_ms is None


# ── query_uptime_pct ──────────────────────────────────────────────────────────

class TestUptimePct:
    def test_all_up_returns_100(self, store):
        base = int(time.time()) - 3600
        for i in range(10):
            store.record_device_state("10.0.0.5", None, None, "UP", ts=base + i * 300)
        assert store.query_uptime_pct("10.0.0.5", hours=2) == pytest.approx(100.0)

    def test_all_down_returns_0(self, store):
        base = int(time.time()) - 3600
        for i in range(4):
            store.record_device_state("10.0.0.6", None, None, "DOWN", ts=base + i * 300)
        assert store.query_uptime_pct("10.0.0.6", hours=2) == pytest.approx(0.0)

    def test_half_up(self, store):
        base = int(time.time()) - 3600
        for i in range(4):
            st = "UP" if i % 2 == 0 else "DOWN"
            store.record_device_state("10.0.0.7", None, None, st, ts=base + i * 300)
        pct = store.query_uptime_pct("10.0.0.7", hours=2)
        assert pct == pytest.approx(50.0)

    def test_no_records_returns_100(self, store):
        assert store.query_uptime_pct("unknown.host", hours=24) == pytest.approx(100.0)

    def test_degraded_not_counted_as_up(self, store):
        base = int(time.time()) - 600
        store.record_device_state("10.0.0.8", None, None, "UP",       ts=base)
        store.record_device_state("10.0.0.8", None, None, "DEGRADED", ts=base + 60)
        store.record_device_state("10.0.0.8", None, None, "DOWN",     ts=base + 120)
        pct = store.query_uptime_pct("10.0.0.8", hours=1)
        assert pct == pytest.approx(100.0 / 3, abs=0.1)


# ── record_device_event / query_device_events ─────────────────────────────────

class TestDeviceEvents:
    def test_record_and_retrieve(self, store):
        now = int(time.time())
        store.record_device_event("192.168.1.50", "JOINED", mac="de:ad:be:ef:00:01",
                                   detail="new device", ts=now)
        events = store.query_device_events(hours=1)
        assert len(events) == 1
        e = events[0]
        assert isinstance(e, DeviceEvent)
        assert e.ip == "192.168.1.50"
        assert e.event_type == "JOINED"
        assert e.mac == "de:ad:be:ef:00:01"
        assert e.detail == "new device"

    def test_invalid_event_type_raises(self, store):
        with pytest.raises(ValueError, match="event_type"):
            store.record_device_event("1.2.3.4", "HACKED")

    def test_event_type_uppercased_on_valid(self, store):
        store.record_device_event("1.2.3.4", "joined")
        events = store.query_device_events(hours=1)
        assert events[0].event_type == "JOINED"

    def test_filter_by_ip(self, store):
        now = int(time.time())
        store.record_device_event("10.0.0.1", "JOINED", ts=now)
        store.record_device_event("10.0.0.2", "JOINED", ts=now)
        events = store.query_device_events(hours=1, ip="10.0.0.1")
        assert len(events) == 1
        assert events[0].ip == "10.0.0.1"

    def test_filter_by_event_type(self, store):
        now = int(time.time())
        store.record_device_event("10.0.0.1", "JOINED",    ts=now)
        store.record_device_event("10.0.0.1", "DOWN",      ts=now)
        store.record_device_event("10.0.0.1", "RECOVERED", ts=now)
        events = store.query_device_events(hours=1, event_types=["DOWN", "RECOVERED"])
        assert len(events) == 2
        types = {e.event_type for e in events}
        assert types == {"DOWN", "RECOVERED"}

    def test_results_newest_first(self, store):
        base = int(time.time()) - 600
        store.record_device_event("10.0.0.1", "JOINED", ts=base)
        store.record_device_event("10.0.0.1", "DOWN",   ts=base + 300)
        events = store.query_device_events(hours=1)
        assert events[0].event_type == "DOWN"
        assert events[1].event_type == "JOINED"

    def test_all_valid_event_types_accepted(self, store):
        valid = ["JOINED", "LEFT", "UP", "DOWN", "DEGRADED", "RECOVERED"]
        for et in valid:
            store.record_device_event("10.0.0.9", et)
        events = store.query_device_events(hours=1)
        assert len(events) == len(valid)


# ── upsert_known_device / get_known_devices ───────────────────────────────────

class TestKnownDevices:
    def test_insert_and_retrieve(self, store):
        now = int(time.time())
        store.upsert_known_device("aa:bb:cc:dd:ee:ff", ip="10.0.0.1",
                                   hostname="myrouter", vendor="ASUS",
                                   device_type="Router", ts=now)
        devices = store.get_known_devices()
        assert "aa:bb:cc:dd:ee:ff" in devices
        d = devices["aa:bb:cc:dd:ee:ff"]
        assert isinstance(d, KnownDevice)
        assert d.ip == "10.0.0.1"
        assert d.hostname == "myrouter"
        assert d.vendor == "ASUS"
        assert d.is_authorized is True

    def test_upsert_updates_ip_and_last_seen(self, store):
        now = int(time.time())
        store.upsert_known_device("11:22:33:44:55:66", ip="10.0.0.2", ts=now - 3600)
        store.upsert_known_device("11:22:33:44:55:66", ip="10.0.0.99", ts=now)
        d = store.get_known_devices()["11:22:33:44:55:66"]
        assert d.ip == "10.0.0.99"
        assert d.last_seen == now
        assert d.first_seen == now - 3600

    def test_upsert_preserves_existing_hostname_when_none(self, store):
        store.upsert_known_device("aa:00:00:00:00:01", hostname="original")
        store.upsert_known_device("aa:00:00:00:00:01", hostname=None)
        d = store.get_known_devices()["aa:00:00:00:00:01"]
        assert d.hostname == "original"

    def test_set_device_authorized_false(self, store):
        store.upsert_known_device("bb:00:00:00:00:01")
        store.set_device_authorized("bb:00:00:00:00:01", False)
        d = store.get_known_devices()["bb:00:00:00:00:01"]
        assert d.is_authorized is False

    def test_set_device_authorized_true(self, store):
        store.upsert_known_device("bb:00:00:00:00:02", is_authorized=False)
        store.set_device_authorized("bb:00:00:00:00:02", True)
        d = store.get_known_devices()["bb:00:00:00:00:02"]
        assert d.is_authorized is True

    def test_empty_inventory(self, store):
        assert store.get_known_devices() == {}


# ── prune_old_data ────────────────────────────────────────────────────────────

class TestPrune:
    def test_prune_removes_old_rtt(self, store):
        old_ts = int(time.time()) - 32 * 86400
        store.record_rtt("8.8.8.8", 1.0, ts=old_ts)
        store.prune_old_data(retain_days=30)
        assert store.query_rtt_history("8.8.8.8", hours=24 * 365) == []

    def test_prune_keeps_recent_rtt(self, store):
        new_ts = int(time.time()) - 1 * 86400
        store.record_rtt("8.8.8.8", 1.0, ts=new_ts)
        store.prune_old_data(retain_days=30)
        assert len(store.query_rtt_history("8.8.8.8", hours=24 * 365)) == 1

    def test_prune_removes_old_device_state(self, store):
        old_ts = int(time.time()) - 35 * 86400
        store.record_device_state("1.2.3.4", None, None, "UP", ts=old_ts)
        store.prune_old_data(retain_days=30)
        assert store.query_device_state_history("1.2.3.4", hours=24 * 365) == []

    def test_prune_removes_old_events(self, store):
        old_ts = int(time.time()) - 35 * 86400
        store.record_device_event("1.2.3.4", "JOINED", ts=old_ts)
        store.prune_old_data(retain_days=30)
        assert store.query_device_events(hours=24 * 365) == []

    def test_known_devices_never_pruned(self, store):
        old_ts = int(time.time()) - 400 * 86400
        store.upsert_known_device("cc:00:00:00:00:01", ts=old_ts)
        store.prune_old_data(retain_days=30)
        # known_device is an inventory — never time-pruned
        assert "cc:00:00:00:00:01" in store.get_known_devices()


# ── Thread safety ─────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_writes_do_not_corrupt(self, store):
        errors = []

        def _write(host, n):
            try:
                for i in range(n):
                    store.record_rtt(host, float(i))
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=_write, args=(f"host{j}.test", 20))
            for j in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        counts = store.get_row_counts()
        assert counts["rtt_sample"] == 100   # 5 threads × 20 writes


# ── get_db_size_bytes ─────────────────────────────────────────────────────────

class TestDbSize:
    def test_in_memory_returns_zero(self, mem_store):
        # :memory: has no file — should return 0 gracefully
        size = mem_store.get_db_size_bytes()
        assert size == 0

    def test_file_db_returns_nonzero_after_write(self, store):
        store.record_rtt("8.8.8.8", 1.0)
        assert store.get_db_size_bytes() > 0
