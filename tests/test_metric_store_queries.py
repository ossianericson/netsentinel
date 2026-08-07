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


def test_get_max_device_scan_count_empty_returns_zero(store):
    assert store.get_max_device_scan_count() == 0


def test_get_max_device_scan_count_returns_highest(store):
    """B4 (F8 usage signal): the suggestion engine's 'you've scanned N times but
    never visited X' nudge needs a cheap proxy for how many scan cycles this
    install has been through — the highest known_device.scan_count is that proxy."""
    store.upsert_known_device("aa:bb:cc:dd:ee:01", ip="192.168.1.5", hostname="router")
    store.upsert_known_device("aa:bb:cc:dd:ee:02", ip="192.168.1.6", hostname="phone")
    store.update_device_stability("aa:bb:cc:dd:ee:01", scan_count=3, ip_stability=1.0)
    store.update_device_stability("aa:bb:cc:dd:ee:02", scan_count=12, ip_stability=1.0)
    assert store.get_max_device_scan_count() == 12


def test_set_device_alert_opt_in(store):
    store.upsert_known_device("aa:bb:cc:dd:ee:ff", ip="192.168.1.5", hostname="router")
    assert store.get_known_devices()["aa:bb:cc:dd:ee:ff"].alert_opt_in is False
    store.set_device_alert_opt_in("aa:bb:cc:dd:ee:ff", True)
    assert store.get_known_devices()["aa:bb:cc:dd:ee:ff"].alert_opt_in is True
    store.set_device_alert_opt_in("aa:bb:cc:dd:ee:ff", False)
    assert store.get_known_devices()["aa:bb:cc:dd:ee:ff"].alert_opt_in is False


def test_is_device_alert_in_scope_unknown_device_false(store):
    assert store.is_device_alert_in_scope("192.168.1.99") is False


def test_is_device_alert_in_scope_opted_in_by_ip(store):
    store.upsert_known_device("aa:bb:cc:dd:ee:ff", ip="192.168.1.5", hostname="phone")
    store.set_device_alert_opt_in("aa:bb:cc:dd:ee:ff", True)
    assert store.is_device_alert_in_scope("192.168.1.5") is True


def test_is_device_alert_in_scope_opted_in_by_mac(store):
    """IP_CHURN passes a MAC, not an IP — must resolve either identifier."""
    store.upsert_known_device("aa:bb:cc:dd:ee:ff", ip="192.168.1.5", hostname="phone")
    store.set_device_alert_opt_in("aa:bb:cc:dd:ee:ff", True)
    assert store.is_device_alert_in_scope("aa:bb:cc:dd:ee:ff") is True


def test_is_device_alert_in_scope_infra_role_true_without_opt_in(store):
    store.upsert_known_device("aa:bb:cc:dd:ee:ff", ip="192.168.1.1", hostname="gateway")
    store._execute_write(
        "UPDATE known_device SET inferred_role=? WHERE mac=?",
        ("gateway", "aa:bb:cc:dd:ee:ff"),
    )
    assert store.is_device_alert_in_scope("192.168.1.1") is True


def test_is_device_alert_in_scope_checks_every_mac_at_an_ip(store):
    """REGRESSION: the query matched `ip = ? OR mac = ?` but only ever read
    rows[0], so with several MACs at one address the answer depended on row
    order. Found live: after the Phase 2 role migration the reference network's
    mesh AP (192.168.68.64) shares its IP with two stale privacy MACs, and the
    gate reported it out of scope purely because one of those sorted first."""
    store.upsert_known_device(mac="3a:41:94:e8:e2:5f", ip="192.168.68.64")
    store.upsert_known_device(mac="f0:72:ea:51:d3:b8", ip="192.168.68.64")
    store.upsert_known_device(mac="2a:06:0f:d0:53:59", ip="192.168.68.64")
    store.update_device_stability(
        mac="f0:72:ea:51:d3:b8", scan_count=6, ip_stability=0.67,
        inferred_role="infrastructure",
    )

    assert store.is_device_alert_in_scope("192.168.68.64") is True


def test_is_device_alert_in_scope_honours_an_opt_in_on_any_mac_at_an_ip(store):
    store.upsert_known_device(mac="3a:41:94:e8:e2:5f", ip="192.168.68.64")
    store.upsert_known_device(mac="2a:06:0f:d0:53:59", ip="192.168.68.64")
    store.set_device_alert_opt_in("2a:06:0f:d0:53:59", True)

    assert store.is_device_alert_in_scope("192.168.68.64") is True


def test_clear_inferred_role_removes_a_stale_role(store):
    """update_device_stability() deliberately never clears a role, so the
    Phase 2 migration needs an explicit path to undo the 9 wrong promotions
    the deleted always-on catch-all wrote."""
    store.upsert_known_device(mac="5c:93:a2:5c:47:19", ip="192.168.68.69")
    store.update_device_stability(
        mac="5c:93:a2:5c:47:19", scan_count=588, ip_stability=0.99,
        inferred_role="infrastructure",
    )
    assert store.is_device_alert_in_scope("192.168.68.69") is True

    store.clear_inferred_role("5c:93:a2:5c:47:19")

    assert store.is_device_alert_in_scope("192.168.68.69") is False


def test_clear_inferred_role_is_safe_for_an_unknown_mac(store):
    store.clear_inferred_role("00:00:00:00:00:01")  # must not raise


def test_delete_known_device_removes_the_inventory_row(store):
    """Program acceptance criterion 3 — a NOT_A_DEVICE entry must be *absent*
    from known_device, not merely stripped of its role. Phase 1 stopped new
    multicast rows being written and Phase 2 cleared the role, but the SSDP
    group was still physically in the reference inventory with 654 scans."""
    store.upsert_known_device(mac="01:00:5e:7f:ff:fa", ip="239.255.255.250")
    assert "01:00:5e:7f:ff:fa" in store.get_known_devices()

    store.delete_known_device("01:00:5e:7f:ff:fa")

    assert "01:00:5e:7f:ff:fa" not in store.get_known_devices()


def test_delete_known_device_leaves_event_history_intact(store):
    """The record/claim split is load-bearing: known_device is an inventory
    *claim*, while device_event/device_ip_history are append-only *records*.
    Retracting the claim must not destroy the forensics."""
    mac = "01:00:5e:7f:ff:fa"
    store.upsert_known_device(mac=mac, ip="239.255.255.250")
    store.record_ip_observation(mac, "239.255.255.250")
    store.record_device_event("239.255.255.250", "JOINED", mac=mac)

    store.delete_known_device(mac)

    assert store.get_total_seen_count(mac) == 1
    assert len(store.query_device_events(ip="239.255.255.250")) == 1


def test_delete_known_device_is_safe_for_an_unknown_mac(store):
    store.delete_known_device("00:00:00:00:00:01")  # must not raise


def test_delete_known_device_normalises_mac_case(store):
    """upsert stores whatever case it is given; every other write method in
    this family lowercases, so the delete must match on the same terms."""
    store.upsert_known_device(mac="01:00:5e:7f:ff:fa", ip="239.255.255.250")

    store.delete_known_device("01:00:5E:7F:FF:FA")

    assert "01:00:5e:7f:ff:fa" not in store.get_known_devices()


def test_importance_tier_recomputes_and_ignores_a_stale_role(store):
    """The tier is derived on every call, never read from a stored column —
    the stored values this replaces are known to be wrong."""
    store.upsert_known_device(
        mac="5c:93:a2:5c:47:19", ip="192.168.68.69", hostname="PS4-C8208A",
        vendor="Liteon Technology Corporation", device_type="Games Console",
    )
    store.update_device_stability(
        mac="5c:93:a2:5c:47:19", scan_count=588, ip_stability=0.99,
        inferred_role="printer",
    )
    assert store.get_device_importance_tier("192.168.68.69") == "personal"


def test_importance_tier_for_the_gateway_is_critical(store):
    store.upsert_known_device(
        mac="3c:64:cf:e0:27:02", ip="192.168.68.1",
        vendor="TP-Link (Deco mesh / RE series extenders)",
    )
    store.update_device_stability(
        mac="3c:64:cf:e0:27:02", scan_count=662, ip_stability=1.0,
        inferred_role="gateway",
    )
    assert store.get_device_importance_tier("192.168.68.1") == "critical"
    assert store.get_device_importance_tier("3c:64:cf:e0:27:02") == "critical"


def test_importance_tier_for_an_unknown_device_is_transient(store):
    assert store.get_device_importance_tier("192.168.1.222") == "transient"


def test_importance_tier_takes_the_highest_of_several_macs_at_one_ip(store):
    """The reference network has three MACs at 192.168.68.64 — the mesh AP and
    two stale privacy MACs. Alerts are keyed by IP, so taking whichever row the
    database returned first would let row order decide whether the AP is
    alertable."""
    store.upsert_known_device(mac="3a:41:94:e8:e2:5f", ip="192.168.68.64")
    store.upsert_known_device(
        mac="f0:72:ea:51:d3:b8", ip="192.168.68.64",
        vendor="Google Nest / Nest Wifi / Google Wifi Router",
        device_type="Video Doorbell",
    )
    store.upsert_known_device(mac="2a:06:0f:d0:53:59", ip="192.168.68.64")

    assert store.get_device_importance_tier("192.168.68.64") == "critical"
    assert store.get_device_importance_tier("3a:41:94:e8:e2:5f") == "transient"


def test_is_device_alert_in_scope_not_opted_in_false(store):
    store.upsert_known_device("aa:bb:cc:dd:ee:ff", ip="192.168.1.5", hostname="phone")
    assert store.is_device_alert_in_scope("192.168.1.5") is False


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


def test_record_alert_fired_rule_type_defaults_empty(store):
    store.record_alert_fired("Host Down", "192.168.1.1", "WARNING", "host is down")
    rows = store.get_unacked_alerts()
    assert rows[0]["rule_type"] == ""


def test_record_alert_fired_stores_rule_type(store):
    store.record_alert_fired(
        "New Open Port", "192.168.1.1", "HIGH", "port 22 opened",
        rule_type="NEW_OPEN_PORT",
    )
    rows = store.get_unacked_alerts()
    assert rows[0]["rule_type"] == "NEW_OPEN_PORT"


def test_get_unacked_alerts_filters_by_rule_types(store):
    store.record_alert_fired("Host Down", "192.168.1.1", "WARNING", "down", rule_type="HOST_DOWN")
    store.record_alert_fired("New CVE", "192.168.1.1", "HIGH", "cve found", rule_type="NEW_CVE")
    rows = store.get_unacked_alerts(rule_types=["NEW_CVE"])
    assert len(rows) == 1
    assert rows[0]["rule_type"] == "NEW_CVE"


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


def test_prune_old_data_keeps_speed_test_forever(store):
    """Stability Sprint 2 (G4): speed_test is low-volume (per-run) — long-term
    speed trends require it to survive the 30-day operational prune window."""
    old_ts = int(time.time()) - 400 * 86400
    store.record_speed_test(100.0, 20.0, 10.0, ts=old_ts)
    store.prune_old_data(retain_days=30)
    rows = store._execute_read("SELECT COUNT(*) AS n FROM speed_test", ())
    assert rows[0]["n"] == 1


def test_prune_old_data_keeps_grade_result_forever(store):
    """Stability Sprint 2 (G4): grade_result's own DDL comment says
    'append-only' — pruning it at 30 days contradicted that contract."""
    old_ts = int(time.time()) - 400 * 86400
    store._execute_write(
        "INSERT INTO grade_result(ts, grade, score, verdict) VALUES(?, ?, ?, ?)",
        (old_ts, "B", 80.0, "old grade"),
    )
    store.prune_old_data(retain_days=30)
    rows = store._execute_read("SELECT COUNT(*) AS n FROM grade_result", ())
    assert rows[0]["n"] == 1


def test_prune_old_data_rolls_up_rtt_samples_before_deleting(store):
    """Stability Sprint 2 (G4): prune_old_data() must populate daily_rollup
    from the rtt_sample rows it is about to delete, so long-term trend charts
    survive the 30-day raw-row prune window."""
    old_ts = int(time.time()) - 40 * 86400
    store.record_rtt("host1", 10.0, ts=old_ts)
    store.record_rtt("host1", 20.0, ts=old_ts + 60)
    store.prune_old_data(retain_days=30)
    rows = store._execute_read("SELECT COUNT(*) AS n FROM rtt_sample", ())
    assert rows[0]["n"] == 0
    rollup_rows = store.query_daily_rollup("rtt_ms", host="host1")
    assert len(rollup_rows) == 1
    assert rollup_rows[0].n == 2
    assert rollup_rows[0].avg == 15.0


def test_query_rtt_weekly_avg_none_when_no_data(store):
    """Stability Sprint 2 (G11): trend_page._update_rtt_headline() ran a
    per-host 14-day raw scan on the main thread on every showEvent — replaced
    with a single SQL aggregate."""
    assert store.query_rtt_weekly_avg() is None


def test_query_rtt_weekly_avg_this_week_only(store):
    now = int(time.time())
    store.record_rtt("host1", 10.0, ts=now - 3600)
    store.record_rtt("host1", 20.0, ts=now - 7200)
    result = store.query_rtt_weekly_avg()
    assert result is not None
    assert result["this_avg"] == 15.0
    assert result["this_n"] == 2
    assert result["last_avg"] is None


def test_query_rtt_weekly_avg_splits_this_and_last_week(store):
    now = int(time.time())
    store.record_rtt("host1", 10.0, ts=now - 3600)                 # this week
    store.record_rtt("host1", 30.0, ts=now - 10 * 86400)           # last week
    result = store.query_rtt_weekly_avg()
    assert result["this_avg"] == 10.0
    assert result["last_avg"] == 30.0


def test_query_rtt_weekly_avg_excludes_unreachable_sentinel(store):
    """rtt_ms == -1.0 means unreachable — must not pollute the average."""
    now = int(time.time())
    store.record_rtt("host1", 10.0, ts=now - 3600)
    store.record_rtt("host1", -1.0, ts=now - 3600)
    result = store.query_rtt_weekly_avg()
    assert result["this_avg"] == 10.0
    assert result["this_n"] == 1


def test_query_rtt_weekly_avg_ignores_samples_older_than_14_days(store):
    old_ts = int(time.time()) - 20 * 86400
    store.record_rtt("host1", 999.0, ts=old_ts)
    assert store.query_rtt_weekly_avg() is None


def test_get_row_counts(store):
    store.record_rtt("8.8.8.8", 10.0)
    counts = store.get_row_counts()
    assert "rtt_sample" in counts
    assert counts["rtt_sample"] >= 1
