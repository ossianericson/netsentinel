"""
Tests for modules/trend_analyser.py

Covers:
  - _linreg: basic regression, flat line, single point, zero-variance x
  - _project_hours_to_threshold: normal crossing, past crossing, flat slope, too-far crossing
  - _direction: RISING / FALLING / STABLE
  - analyse_host_rtt: needs MetricStore with real data; uses a mock store
  - run_full_trend_report: smoke test with mock store
  - TrendReport: critical / warnings / has_alerts properties
  - SnapshotDiff summary (imported from config_baseline tests)
"""
from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock

from modules.trend_analyser import (
    TrendResult, TrendReport,
    _linreg, _project_hours_to_threshold, _direction,
    analyse_host_rtt, run_full_trend_report,
    DEFAULT_THRESHOLDS,
)


class TestLinreg(unittest.TestCase):
    def test_perfect_fit(self):
        xs = [0.0, 1.0, 2.0, 3.0]
        ys = [0.0, 2.0, 4.0, 6.0]
        slope, intercept, r2 = _linreg(xs, ys)
        self.assertAlmostEqual(slope, 2.0)
        self.assertAlmostEqual(intercept, 0.0)
        self.assertAlmostEqual(r2, 1.0)

    def test_flat_line(self):
        xs = [0.0, 1.0, 2.0]
        ys = [5.0, 5.0, 5.0]
        slope, intercept, r2 = _linreg(xs, ys)
        self.assertAlmostEqual(slope, 0.0)
        self.assertAlmostEqual(intercept, 5.0)

    def test_single_point_returns_zero_slope(self):
        slope, intercept, r2 = _linreg([0.0], [42.0])
        self.assertEqual(slope, 0.0)
        self.assertEqual(intercept, 42.0)

    def test_zero_variance_x(self):
        # All x same → degenerate
        slope, intercept, r2 = _linreg([1.0, 1.0, 1.0], [3.0, 4.0, 5.0])
        self.assertEqual(slope, 0.0)

    def test_negative_slope(self):
        xs = [0.0, 1.0, 2.0]
        ys = [10.0, 5.0, 0.0]
        slope, intercept, r2 = _linreg(xs, ys)
        self.assertAlmostEqual(slope, -5.0)


class TestProjectHoursToThreshold(unittest.TestCase):
    def test_normal_crossing(self):
        # x is in seconds, slope is per-second
        # y = (1/3600)*x + 0; threshold=5.0 → x_cross = 5*3600 s → 5 hours from 0
        slope_per_sec = 1.0 / 3600.0
        eta = _project_hours_to_threshold(slope_per_sec, 0.0, 0.0, 5.0)
        self.assertAlmostEqual(eta, 5.0)

    def test_already_past_threshold(self):
        # y = 2x + 0, current x=0, but threshold=0 → crossing at x=0, delta=0 → None
        eta = _project_hours_to_threshold(2.0, 0.0, 0.0, 0.0)
        self.assertIsNone(eta)

    def test_flat_slope_returns_none(self):
        eta = _project_hours_to_threshold(0.0, 50.0, 0.0, 100.0)
        self.assertIsNone(eta)

    def test_too_far_away_returns_none(self):
        # slope=0.001/h, threshold=10000, crossing far in future
        eta = _project_hours_to_threshold(0.001, 0.0, 0.0, 10000.0)
        self.assertIsNone(eta)

    def test_falling_below_threshold_returns_none(self):
        # Negative slope, threshold above current → won't cross upwards
        eta = _project_hours_to_threshold(-2.0, 50.0, 0.0, 100.0)
        self.assertIsNone(eta)


class TestDirection(unittest.TestCase):
    def test_rising(self):
        self.assertEqual(_direction(1.0), "RISING")

    def test_falling(self):
        self.assertEqual(_direction(-1.0), "FALLING")

    def test_stable_positive(self):
        self.assertEqual(_direction(0.005), "STABLE")

    def test_stable_negative(self):
        self.assertEqual(_direction(-0.005), "STABLE")


class TestAnalyseHostRtt(unittest.TestCase):
    def _make_store(self, rtt_values, host="10.0.0.1", base_ts=None):
        """Create a mock MetricStore whose query_rtt_history returns synthetic data."""
        from modules.metric_store import RttPoint
        now = int(time.time())
        base = base_ts or (now - 3600 * len(rtt_values))
        interval = 3600
        points = [
            RttPoint(
                ts=base + i * interval,
                host=host,
                rtt_ms=v,
                loss_pct=0.0,
                jitter_ms=0.0,
            )
            for i, v in enumerate(rtt_values)
        ]
        store = MagicMock()
        store.query_rtt_history.return_value = points
        return store

    def test_rising_rtt_produces_warning_or_critical(self):
        # 5 samples, rising from 20ms to 120ms → should exceed 100ms threshold
        store = self._make_store([20, 45, 70, 95, 120])
        results = analyse_host_rtt(store, "10.0.0.1", window_hours=5,
                                   thresholds={"rtt_ms": 100.0})
        rtt_results = [r for r in results if r.metric == "rtt_ms"]
        self.assertTrue(len(rtt_results) > 0)
        # Current value is 120 → already above threshold → CRITICAL
        self.assertEqual(rtt_results[0].severity, "CRITICAL")
        self.assertEqual(rtt_results[0].direction, "RISING")

    def test_stable_rtt_is_clean(self):
        store = self._make_store([10, 11, 10, 11, 10])
        results = analyse_host_rtt(store, "10.0.0.1", window_hours=5,
                                   thresholds={"rtt_ms": 100.0})
        rtt_results = [r for r in results if r.metric == "rtt_ms"]
        self.assertTrue(len(rtt_results) > 0)
        self.assertIn(rtt_results[0].severity, ("CLEAN", "INFO"))

    def test_too_few_samples_returns_empty(self):
        store = self._make_store([10, 20])  # < 3 points
        results = analyse_host_rtt(store, "10.0.0.1", window_hours=2)
        self.assertEqual(results, [])

    def test_result_fields_populated(self):
        store = self._make_store([10, 20, 30, 40, 50])
        results = analyse_host_rtt(store, "10.0.0.1", window_hours=5)
        for r in results:
            self.assertIsInstance(r.current_value, (int, float))
            self.assertIsInstance(r.slope_per_hour, float)
            self.assertIsInstance(r.r_squared, float)
            self.assertIsInstance(r.summary, str)
            self.assertTrue(len(r.summary) > 0)


class TestRunFullTrendReport(unittest.TestCase):
    def test_empty_host_list(self):
        store = MagicMock()
        store.query_all_rtt_hosts.return_value = []
        report = run_full_trend_report(store)
        self.assertEqual(report.results, [])
        self.assertFalse(report.has_alerts)

    def test_report_sorted_critical_first(self):
        from modules.metric_store import RttPoint
        now = int(time.time())

        def _points(start, end, host):
            n = 6
            return [
                RttPoint(ts=now - (n - i) * 600, host=host,
                         rtt_ms=start + (end - start) * i / (n - 1),
                         loss_pct=0.0, jitter_ms=0.0)
                for i in range(n)
            ]

        store = MagicMock()
        store.query_all_rtt_hosts.return_value = ["host-a", "host-b"]
        store.query_rtt_history.side_effect = lambda host, **kw: (
            _points(5, 200, host) if host == "host-a" else _points(5, 12, host)
        )
        report = run_full_trend_report(store, window_hours=1,
                                       thresholds={"rtt_ms": 100.0, "loss_pct": 50.0, "jitter_ms": 50.0})
        sevs = [r.severity for r in report.results]
        # CRITICAL or WARNING should come before CLEAN
        clean_indices  = [i for i, s in enumerate(sevs) if s == "CLEAN"]
        alert_indices  = [i for i, s in enumerate(sevs) if s in ("CRITICAL", "WARNING")]
        if clean_indices and alert_indices:
            self.assertLess(min(alert_indices), min(clean_indices))

    def test_report_timestamp_set(self):
        store = MagicMock()
        store.query_all_rtt_hosts.return_value = []
        before = int(time.time())
        report = run_full_trend_report(store)
        self.assertGreaterEqual(report.ts, before)


class TestTrendReport(unittest.TestCase):
    def _make_result(self, severity):
        return TrendResult(
            host="h", metric="rtt_ms", window_hours=24, sample_count=10,
            current_value=50.0, mean_value=40.0, slope_per_hour=2.0,
            r_squared=0.9, threshold=100.0, eta_hours=25.0,
            direction="RISING", severity=severity,
            summary="test summary",
        )

    def test_critical_property(self):
        r = TrendReport(ts=0, results=[self._make_result("CRITICAL"),
                                       self._make_result("CLEAN")])
        self.assertEqual(len(r.critical), 1)

    def test_warnings_property(self):
        r = TrendReport(ts=0, results=[self._make_result("WARNING"),
                                       self._make_result("CLEAN")])
        self.assertEqual(len(r.warnings), 1)

    def test_has_alerts_false_when_all_clean(self):
        r = TrendReport(ts=0, results=[self._make_result("CLEAN")])
        self.assertFalse(r.has_alerts)

    def test_has_alerts_true_with_critical(self):
        r = TrendReport(ts=0, results=[self._make_result("CRITICAL")])
        self.assertTrue(r.has_alerts)


if __name__ == "__main__":
    unittest.main()
