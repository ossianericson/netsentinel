"""
tests/test_metric_store_app_traffic.py — App Traffic history persistence (Sprint 6).

Covers record_app_traffic_sample()/prune_app_traffic_samples() in metric_store.py
and the query_app_traffic_* read methods in metric_store_queries_metrics.py.
"""
import statistics
import time

import pytest

from modules.metric_store import MetricStore


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def test_record_and_query_category_totals(store):
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Streaming", "HTTPS", 50_000, 10.0, cdn="Netflix")
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:02", "phone", "Web", "HTTPS", 10_000, 10.0)
    totals = store.query_app_traffic_category_totals(hours=24.0)
    assert totals["Streaming"] == 50_000
    assert totals["Web"] == 10_000


def test_category_totals_excludes_old_samples(store):
    old_ts = int(time.time()) - 48 * 3600
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Streaming", "HTTPS", 50_000, 10.0, ts=old_ts)
    totals = store.query_app_traffic_category_totals(hours=24.0)
    assert totals == {}


def test_device_breakdown_for_category(store):
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Streaming", "HTTPS", 50_000, 10.0)
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:02", "tv", "Streaming", "HTTPS", 80_000, 10.0)
    rows = store.query_app_traffic_device_breakdown("Streaming", hours=24.0)
    assert rows[0]["label"] == "tv"
    assert rows[0]["bytes_total"] == 80_000
    assert rows[1]["label"] == "laptop"


def test_cdn_breakdown_for_category(store):
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Streaming", "HTTPS", 60_000, 10.0, cdn="Netflix")
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:02", "tv", "Streaming", "HTTPS", 40_000, 10.0, cdn="YouTube")
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:03", "tablet", "Streaming", "HTTPS", 5_000, 10.0)  # no CDN match
    rows = store.query_app_traffic_cdn_breakdown("Streaming", hours=24.0)
    by_name = {r["cdn"]: r["bytes_total"] for r in rows}
    assert by_name["Netflix"] == 60_000
    assert by_name["YouTube"] == 40_000
    assert by_name["Other"] == 5_000


def test_weekly_totals_split_group_by_rewrite(store):
    """Stability Sprint 2 (G11): the SQL GROUP BY rewrite must give the same
    split as the old Python loop, without materializing every row."""
    now = int(time.time())
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Web", "HTTPS", 3_000, 10.0, ts=now - 3600)
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Web", "HTTPS", 4_000, 10.0, ts=now - 8 * 86400)
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Web", "HTTPS", 9_000, 10.0, ts=now - 20 * 86400)
    totals = store.query_app_traffic_weekly_totals()
    assert totals["this_week"] == 3_000
    assert totals["last_week"] == 4_000


def test_weekly_totals_split(store):
    now = int(time.time())
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Web", "HTTPS", 1_000, 10.0, ts=now - 3600)
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Web", "HTTPS", 2_000, 10.0, ts=now - 10 * 86400)
    totals = store.query_app_traffic_weekly_totals()
    assert totals["this_week"] == 1_000
    assert totals["last_week"] == 2_000


def test_category_totals_range_splits_this_and_last_week(store):
    now = int(time.time())
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Gaming", "Steam", 1_000, 10.0, ts=now - 3600)
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Gaming", "Steam", 2_000, 10.0, ts=now - 10 * 86400)
    this_week = store.query_app_traffic_category_totals_range(0, 168)
    last_week = store.query_app_traffic_category_totals_range(168, 336)
    assert this_week["Gaming"] == 1_000
    assert last_week["Gaming"] == 2_000


def test_active_device_count(store):
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Gaming", "Steam", 1_000, 10.0)
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:02", "pc", "Gaming", "Steam", 1_000, 10.0)
    assert store.query_app_traffic_active_device_count(seconds=60.0) == 2
    assert store.query_app_traffic_active_device_count(category="Web", seconds=60.0) == 0


def test_hourly_distribution_groups_by_hour(store):
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Gaming", "Steam", 1_000, 10.0)
    dist = store.query_app_traffic_hourly_distribution(hours=24.0)
    assert sum(dist.values()) == 1_000


def test_hourly_distribution_buckets_correct_local_hour(store):
    """Stability Sprint 2 (G11): the SQL GROUP BY rewrite must bucket by the
    same local hour-of-day that the old Python time.localtime() loop did."""
    now = int(time.time())
    local_hour = time.localtime(now).tm_hour
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Gaming", "Steam", 500, 10.0, ts=now)
    dist = store.query_app_traffic_hourly_distribution(hours=1.0)
    assert dist == {local_hour: 500}


def test_hourly_distribution_filters_by_category(store):
    now = int(time.time())
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Gaming", "Steam", 500, 10.0, ts=now)
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:02", "pc", "Web", "HTTPS", 700, 10.0, ts=now)
    dist = store.query_app_traffic_hourly_distribution(category="Gaming", hours=1.0)
    assert sum(dist.values()) == 500


def test_hourly_distribution_excludes_samples_outside_window(store):
    old_ts = int(time.time()) - 48 * 3600
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Gaming", "Steam", 500, 10.0, ts=old_ts)
    dist = store.query_app_traffic_hourly_distribution(hours=24.0)
    assert dist == {}


def test_prune_app_traffic_samples_removes_old_rows(store):
    old_ts = int(time.time()) - 40 * 86400
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Web", "HTTPS", 1_000, 10.0, ts=old_ts)
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Web", "HTTPS", 2_000, 10.0)
    store.prune_app_traffic_samples(retain_days=35)
    totals = store.query_app_traffic_category_totals(hours=24.0 * 365)
    assert totals["Web"] == 2_000


# ── Scaling guards (G11) ───────────────────────────────────────────────────
# Confirms the GROUP BY rewrite doesn't scale with row count the way the old
# per-row Python loop did. See .claude/rules/tests.instructions.md.


def _seed_rows(store, n):
    now = int(time.time())
    conn = store._conn
    conn.executemany(
        "INSERT INTO app_traffic_sample (ts, mac, label, category, app, cdn, bytes_total, window_s) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (now - (i % 3600), "aa:bb:cc:dd:ee:01", "laptop", "Web", "HTTPS", None, 100, 10.0)
            for i in range(n)
        ],
    )
    conn.commit()


def _median_time(fn, repeats=5):
    times = [None] * repeats
    for i in range(repeats):
        t0 = time.perf_counter()
        fn()
        times[i] = time.perf_counter() - t0
    return statistics.median(times)


@pytest.mark.benchmark
def test_hourly_distribution_scaling(tmp_path):
    small_store = MetricStore(db_path=tmp_path / "small.db")
    large_store = MetricStore(db_path=tmp_path / "large.db")
    _seed_rows(small_store, 200)
    _seed_rows(large_store, 2000)
    t_small = _median_time(lambda: small_store.query_app_traffic_hourly_distribution(hours=24.0 * 365))
    t_large = _median_time(lambda: large_store.query_app_traffic_hourly_distribution(hours=24.0 * 365))
    small_store.close()
    large_store.close()
    if t_small < 1e-7:
        pytest.skip("below measurement threshold")
    ratio = t_large / t_small
    assert ratio < 15, (
        f"Scaling ratio {ratio:.1f}x for 10x input suggests O(n^2) regression "
        f"(t_small={t_small:.6f}s, t_large={t_large:.6f}s)"
    )


@pytest.mark.benchmark
def test_weekly_totals_scaling(tmp_path):
    small_store = MetricStore(db_path=tmp_path / "small2.db")
    large_store = MetricStore(db_path=tmp_path / "large2.db")
    _seed_rows(small_store, 200)
    _seed_rows(large_store, 2000)
    t_small = _median_time(lambda: small_store.query_app_traffic_weekly_totals())
    t_large = _median_time(lambda: large_store.query_app_traffic_weekly_totals())
    small_store.close()
    large_store.close()
    if t_small < 1e-7:
        pytest.skip("below measurement threshold")
    ratio = t_large / t_small
    assert ratio < 15, (
        f"Scaling ratio {ratio:.1f}x for 10x input suggests O(n^2) regression "
        f"(t_small={t_small:.6f}s, t_large={t_large:.6f}s)"
    )
