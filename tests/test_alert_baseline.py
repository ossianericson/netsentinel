"""Tests for modules/alert_baseline.py (S4-2 baseline learning window)."""
import time
import pytest
from unittest.mock import MagicMock


def _make_store(rtt_hosts=None, rtt_points=None, speed_points=None):
    store = MagicMock()
    store.query_all_rtt_hosts.return_value = rtt_hosts or []
    store.query_rtt_history.return_value = rtt_points or []
    store.query_speed_test_history.return_value = speed_points or []
    return store


# ── Import ────────────────────────────────────────────────────────────────────

def test_import():
    from modules.alert_baseline import BaselineLearner, BaselineMetric, Baseline
    assert BaselineLearner
    assert BaselineMetric
    assert Baseline


# ── BaselineMetric ────────────────────────────────────────────────────────────

def test_baseline_metric_valid():
    from modules.alert_baseline import BaselineMetric
    m = BaselineMetric(mean=50.0, stddev=10.0, sample_count=100, days_covered=8.0)
    assert m.is_valid
    assert m.anomaly_threshold(2.0) == pytest.approx(70.0)
    assert m.low_threshold(2.0) == pytest.approx(30.0)


def test_baseline_metric_invalid_few_samples():
    from modules.alert_baseline import BaselineMetric
    m = BaselineMetric(mean=50.0, stddev=5.0, sample_count=5, days_covered=8.0)
    assert not m.is_valid


def test_baseline_metric_low_threshold_floor():
    from modules.alert_baseline import BaselineMetric
    m = BaselineMetric(mean=5.0, stddev=10.0, sample_count=100, days_covered=8.0)
    assert m.low_threshold(2.0) == 0.0   # never negative


# ── Baseline.is_mature ────────────────────────────────────────────────────────

def test_baseline_not_mature_no_metrics():
    from modules.alert_baseline import Baseline
    b = Baseline(host="8.8.8.8")
    assert not b.is_mature


def test_baseline_mature_with_valid_rtt():
    from modules.alert_baseline import Baseline, BaselineMetric
    m = BaselineMetric(mean=30.0, stddev=5.0, sample_count=100, days_covered=8.0)
    b = Baseline(host="8.8.8.8", rtt_ms=m)
    assert b.is_mature


def test_baseline_not_mature_too_few_days():
    from modules.alert_baseline import Baseline, BaselineMetric
    m = BaselineMetric(mean=30.0, stddev=5.0, sample_count=100, days_covered=3.0)
    b = Baseline(host="8.8.8.8", rtt_ms=m)
    assert not b.is_mature


# ── BaselineLearner with no data ──────────────────────────────────────────────

def test_learner_empty_store():
    from modules.alert_baseline import BaselineLearner
    store = _make_store()
    learner = BaselineLearner()
    learner.refresh(store)
    assert learner.get_network_baseline() is not None
    assert not learner.is_mature()


# ── BaselineLearner with RTT data ─────────────────────────────────────────────

def _make_rtt_point(ts, rtt_ms, loss_pct=0.0):
    p = MagicMock()
    p.ts = ts
    p.rtt_ms = rtt_ms
    p.loss_pct = loss_pct
    return p


def test_learner_computes_rtt_baseline():
    from modules.alert_baseline import BaselineLearner
    now = int(time.time())
    # Simulate 8 days of data (> 7-day threshold)
    start = now - 8 * 86400
    # 200 RTT samples with stable ~30ms RTT
    points = [_make_rtt_point(start + i * 3456, 30.0 + (i % 5)) for i in range(50)]
    store = _make_store(rtt_hosts=["8.8.8.8"], rtt_points=points)
    learner = BaselineLearner()
    learner.refresh(store)
    bl = learner.get_host_baseline("8.8.8.8")
    assert bl is not None
    assert bl.rtt_ms is not None
    assert bl.rtt_ms.mean == pytest.approx(32.0, abs=1.0)


def test_learner_is_mature_after_7_days():
    from modules.alert_baseline import BaselineLearner
    now = int(time.time())
    start = now - 8 * 86400
    points = [_make_rtt_point(start + i * 3600, 25.0) for i in range(60)]
    store = _make_store(rtt_hosts=["192.168.1.1"], rtt_points=points)
    learner = BaselineLearner()
    learner.refresh(store)
    assert learner.is_mature()


# ── BaselineLearner speed baseline ────────────────────────────────────────────

def _make_speed_point(ts, dl, ul):
    p = MagicMock()
    p.ts = ts
    p.download_mbps = dl
    p.upload_mbps = ul
    return p


def test_learner_speed_baseline():
    from modules.alert_baseline import BaselineLearner
    now = int(time.time())
    start = now - 8 * 86400
    speed_pts = [_make_speed_point(start + i * 86400, 95.0 + i, 20.0) for i in range(8)]
    store = _make_store(speed_points=speed_pts)
    learner = BaselineLearner()
    learner.refresh(store)
    nb = learner.get_network_baseline()
    assert nb is not None
    assert nb.download_mbps is not None
    assert nb.download_mbps.mean == pytest.approx(98.5, abs=1.0)


# ── Anomaly threshold derivation ──────────────────────────────────────────────

def test_anomaly_threshold_above_mean():
    from modules.alert_baseline import BaselineMetric
    m = BaselineMetric(mean=30.0, stddev=5.0, sample_count=100, days_covered=8.0)
    # 2-sigma threshold should be mean + 2*stddev = 40
    assert m.anomaly_threshold(2.0) == pytest.approx(40.0)


def test_low_threshold_for_speed():
    from modules.alert_baseline import BaselineMetric
    # 95 Mbps ± 10 Mbps stddev → low threshold at 75 Mbps
    m = BaselineMetric(mean=95.0, stddev=10.0, sample_count=50, days_covered=8.0)
    assert m.low_threshold(2.0) == pytest.approx(75.0)
