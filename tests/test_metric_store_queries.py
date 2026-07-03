"""Tests for modules/metric_store_queries.py — MetricStoreQueryMixin via MetricStore."""
import datetime
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


def test_query_previous_grade_none_initially(store):
    assert store.query_previous_grade() is None


def test_query_previous_grade_none_with_single_grade(store):
    """Only one grade recorded — there is no 'previous' row yet."""
    store.record_grade("A", 95.0, "Excellent")
    assert store.query_previous_grade() is None


def test_query_previous_grade_returns_second_most_recent(store):
    store.record_grade("C", 60.0, "Degraded")
    store.record_grade("A", 95.0, "Excellent")
    prev = store.query_previous_grade()
    assert prev is not None
    assert prev["grade"] == "C"
    assert prev["score"] == 60.0
    # and query_last_grade still returns the newest
    assert store.query_last_grade()["grade"] == "A"


def test_list_snapshots_empty(store):
    assert store.list_snapshots() == []


def test_record_grade_retains_history_for_regression_detection(store):
    """record_grade() must append, not replace — GRADE_REGRESSION needs the
    prior grade to still be queryable after a new one is recorded (V6 Sprint 1)."""
    store.record_grade("A", 95.0, "Excellent")
    first = store.query_last_grade()
    store.record_grade("C", 70.0, "Degraded")
    second = store.query_last_grade()
    assert first["grade"] == "A"
    assert second["grade"] == "C"
    rows = store._execute_read("SELECT COUNT(*) AS n FROM grade_result", ())
    assert rows[0]["n"] == 2


def test_query_ip_churn_flags_devices_with_multiple_ips(store):
    mac = "aa:bb:cc:00:00:01"
    store.record_ip_observation(mac, "10.0.0.1")
    store.record_ip_observation(mac, "10.0.0.2")
    store.record_ip_observation(mac, "10.0.0.3")
    stable_mac = "aa:bb:cc:00:00:02"
    store.record_ip_observation(stable_mac, "10.0.0.9")
    churn = store.query_ip_churn(hours=24.0, min_ips=3)
    assert churn.get(mac) == 3
    assert stable_mac not in churn


def test_query_ip_churn_empty_when_below_threshold(store):
    mac = "aa:bb:cc:00:00:03"
    store.record_ip_observation(mac, "10.0.0.1")
    store.record_ip_observation(mac, "10.0.0.2")
    assert store.query_ip_churn(hours=24.0, min_ips=3) == {}


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


def test_prune_old_data_returns_total_rows_deleted(store):
    """Stability Sprint 1 (G2): prune_old_data() must return the total row
    count deleted so callers can decide whether a VACUUM is worthwhile."""
    old_ts = int(time.time()) - 40 * 86400
    for i in range(3):
        store.record_rtt(f"host{i}", 10.0, ts=old_ts)
    deleted = store.prune_old_data(retain_days=30)
    assert isinstance(deleted, int)
    assert deleted >= 3


def test_prune_old_data_prunes_app_traffic_samples(store):
    """Stability Sprint 1 (G1): app_traffic_sample grew unbounded because
    prune_app_traffic_samples() had zero runtime callers. prune_old_data()
    must now invoke it."""
    old_ts = int(time.time()) - 40 * 86400
    store.record_app_traffic_sample(
        mac="aa:bb:cc:dd:ee:ff", label="Test Device", category="web",
        app="chrome", bytes_total=1000, window_s=10.0, ts=old_ts,
    )
    rows = store._execute_read("SELECT COUNT(*) AS n FROM app_traffic_sample", ())
    assert rows[0]["n"] == 1
    store.prune_old_data(retain_days=30)
    rows = store._execute_read("SELECT COUNT(*) AS n FROM app_traffic_sample", ())
    assert rows[0]["n"] == 0


def test_prune_old_data_prunes_alert_fired(store):
    """Stability Sprint 1 (G9): alert_fired had no retention at all."""
    old_ts = int(time.time()) - 400 * 86400
    store.record_alert_fired("RULE_X", "192.168.1.1", "WARNING", "test alert", ts=old_ts)
    rows = store._execute_read("SELECT COUNT(*) AS n FROM alert_fired", ())
    assert rows[0]["n"] == 1
    store.prune_old_data(retain_days=30)
    rows = store._execute_read("SELECT COUNT(*) AS n FROM alert_fired", ())
    assert rows[0]["n"] == 0


def test_prune_old_data_keeps_recent_alert_fired(store):
    store.record_alert_fired("RULE_X", "192.168.1.1", "WARNING", "recent alert")
    store.prune_old_data(retain_days=30)
    rows = store._execute_read("SELECT COUNT(*) AS n FROM alert_fired", ())
    assert rows[0]["n"] == 1


def test_prune_old_data_prunes_device_events_audit_table(store):
    """Stability Sprint 1 (G9): device_events (plural, audit trail) stores a
    TEXT datetime — must use a SQL-native datetime cutoff, not an epoch int."""
    old_dt = (datetime.datetime.utcnow() - datetime.timedelta(days=400)).strftime("%Y-%m-%d %H:%M:%S")
    store._execute_write(
        "INSERT INTO device_events (mac, event_type, old_value, new_value, source, ts) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("aa:bb:cc:dd:ee:ff", "RENAMED", "old", "new", "test", old_dt),
    )
    rows = store._execute_read("SELECT COUNT(*) AS n FROM device_events", ())
    assert rows[0]["n"] == 1
    store.prune_old_data(retain_days=30)
    rows = store._execute_read("SELECT COUNT(*) AS n FROM device_events", ())
    assert rows[0]["n"] == 0


def test_prune_old_data_keeps_recent_device_events(store):
    store.record_device_change_event("aa:bb:cc:dd:ee:ff", "RENAMED", "old", "new", "test")
    store.prune_old_data(retain_days=30)
    rows = store._execute_read("SELECT COUNT(*) AS n FROM device_events", ())
    assert rows[0]["n"] == 1


def test_vacuum_if_needed_runs_above_threshold(store):
    """Stability Sprint 1 (G2): the old PRAGMA VACUUM call was invalid SQL and
    silently swallowed — vacuum_if_needed() must issue a real VACUUM when
    enough rows were deleted to make it worthwhile."""
    ran = store.vacuum_if_needed(rows_deleted=1000, threshold=500)
    assert ran is True


def test_vacuum_if_needed_skips_below_threshold(store):
    ran = store.vacuum_if_needed(rows_deleted=1, threshold=500)
    assert ran is False


def test_get_row_counts(store):
    store.record_rtt("8.8.8.8", 10.0)
    counts = store.get_row_counts()
    assert "rtt_sample" in counts
    assert counts["rtt_sample"] >= 1
