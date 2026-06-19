"""
tests/test_metric_store_app_traffic.py — App Traffic history persistence (Sprint 6).

Covers record_app_traffic_sample()/prune_app_traffic_samples() in metric_store.py
and the query_app_traffic_* read methods in metric_store_queries_metrics.py.
"""
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


def test_prune_app_traffic_samples_removes_old_rows(store):
    old_ts = int(time.time()) - 40 * 86400
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Web", "HTTPS", 1_000, 10.0, ts=old_ts)
    store.record_app_traffic_sample("aa:bb:cc:dd:ee:01", "laptop", "Web", "HTTPS", 2_000, 10.0)
    store.prune_app_traffic_samples(retain_days=35)
    totals = store.query_app_traffic_category_totals(hours=24.0 * 365)
    assert totals["Web"] == 2_000
