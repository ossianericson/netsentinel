"""Tests for modules/metric_store_queries.py — MetricStoreQueryMixin via MetricStore."""
import pytest
import time

from modules.metric_store import MetricStore


@pytest.fixture
def store():
    s = MetricStore(db_path=":memory:")
    yield s
    s.close()


def test_query_rtt_returns_empty_initially(store):
    assert store.query_rtt_history("8.8.8.8") == []


def test_query_rtt_after_record(store):
    store.record_rtt("8.8.8.8", 14.2, 0.0)
    rows = store.query_rtt_history("8.8.8.8")
    assert len(rows) == 1
    assert rows[0].rtt_ms == 14.2


def test_query_all_rtt_hosts(store):
    store.record_rtt("host1", 10.0)
    store.record_rtt("host2", 20.0)
    hosts = store.query_all_rtt_hosts()
    assert "host1" in hosts
    assert "host2" in hosts


def test_query_uptime_pct_no_data_returns_none(store):
    assert store.query_uptime_pct("192.168.1.1") is None


def test_query_uptime_pct_all_up(store):
    for _ in range(5):
        store.record_device_state("192.168.1.1", None, None, "UP")
    assert store.query_uptime_pct("192.168.1.1") == 100.0


def test_query_uptime_pct_mixed(store):
    store.record_device_state("192.168.1.2", None, None, "UP")
    store.record_device_state("192.168.1.2", None, None, "DOWN")
    pct = store.query_uptime_pct("192.168.1.2")
    assert 40.0 <= pct <= 60.0


def test_query_device_events_empty(store):
    assert store.query_device_events() == []


def test_query_device_events_filtered(store):
    store.record_device_event("192.168.1.1", "JOINED")
    store.record_device_event("192.168.1.1", "LEFT")
    joined = store.query_device_events(event_types=["JOINED"])
    assert len(joined) == 1
    assert joined[0].event_type == "JOINED"


def test_get_known_devices_empty(store):
    assert store.get_known_devices() == {}


def test_get_known_devices_after_upsert(store):
    store.upsert_known_device("aa:bb:cc:dd:ee:ff", ip="192.168.1.5", hostname="router")
    devices = store.get_known_devices()
    assert "aa:bb:cc:dd:ee:ff" in devices
    assert devices["aa:bb:cc:dd:ee:ff"].ip == "192.168.1.5"


def test_query_cert_status_empty(store):
    assert store.query_cert_status() == []


def test_query_service_status_empty(store):
    assert store.query_service_status() == []


def test_query_service_after_record(store):
    store.record_service_check("192.168.1.1", 80, up=True, rtt_ms=5.0)
    results = store.query_service_status()
    assert len(results) == 1
    assert results[0].up is True


def test_query_last_grade_none_initially(store):
    assert store.query_last_grade() is None


def test_query_last_grade_after_record(store):
    store.record_grade("A", 95.0, "Excellent network health")
    g = store.query_last_grade()
    assert g is not None
    assert g["grade"] == "A"
    assert g["score"] == 95.0


def test_list_snapshots_empty(store):
    assert store.list_snapshots() == []


def test_list_snapshots_after_store(store):
    store.store_snapshot(int(time.time()), "test", '{"key": "val"}')
    snaps = store.list_snapshots()
    assert len(snaps) == 1
    assert snaps[0]["label"] == "test"


def test_prune_old_data(store):
    # Record with an old timestamp
    old_ts = int(time.time()) - 40 * 86400
    store.record_rtt("old-host", 10.0, ts=old_ts)
    assert len(store.query_rtt_history("old-host", hours=24 * 45)) == 1
    store.prune_old_data(retain_days=30)
    assert store.query_rtt_history("old-host", hours=24 * 45) == []


def test_get_row_counts(store):
    store.record_rtt("8.8.8.8", 10.0)
    counts = store.get_row_counts()
    assert "rtt_sample" in counts
    assert counts["rtt_sample"] >= 1
