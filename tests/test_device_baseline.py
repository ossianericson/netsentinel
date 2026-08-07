"""
Tests for modules/device_baseline.py — per-device normal.

Written test-first per RULE-TDD1. Phase 0 defect 4: a fixed global threshold
applied to devices whose normal is different. `192.168.68.54` (a Chromecast)
averages 194.3 ms against availability_monitor's `degraded_threshold = 150.0`,
so it sits permanently on the boundary and emitted **306 state events** in 25
days — the single loudest device on the reference network. The top five churn
sources were a Chromecast, a laptop, a printer, a PS5 and a streaming stick:
every one a device that legitimately sleeps or varies.

Acceptance criterion 2 is the target: those 306 events drop to <= 10 *without*
losing a genuine outage.
"""
from __future__ import annotations

import time

import pytest

from modules.device_baseline import (
    DOWN_CONFIRMATION_CYCLES,
    MIN_BASELINE_SAMPLES,
    DeviceBaselines,
    derive_degraded_threshold,
    derive_hour_of_week_downtime,
    hour_of_week,
)


DEFAULT = 150.0


class _Point:
    """Duck-types metric_store's DeviceStatePoint / RttPoint."""
    def __init__(self, ts, state="UP", rtt_ms=10.0):
        self.ts = ts
        self.state = state
        self.rtt_ms = rtt_ms


class _FakeStore:
    """Minimal MetricStore stand-in — only the one read the module needs."""
    def __init__(self, points_by_host=None):
        self._points = points_by_host or {}
        self.calls = 0

    def query_device_state_history(self, ip, hours=24.0):
        self.calls += 1
        since = time.time() - hours * 3600
        return [p for p in self._points.get(ip, []) if p.ts >= since]


# ── Pure threshold maths ─────────────────────────────────────────────────────

class TestDeriveDegradedThreshold:
    def test_too_few_samples_keeps_the_global_default(self):
        assert derive_degraded_threshold([190.0] * 5, DEFAULT) == DEFAULT

    def test_the_chromecast_case_lifts_the_threshold_clear_of_the_mean(self):
        """194 ms mean against a 150 ms threshold is the whole defect."""
        rtts = [194.3 + (i % 7) * 4.0 for i in range(200)]
        threshold = derive_degraded_threshold(rtts, DEFAULT)
        mean = sum(rtts) / len(rtts)
        assert threshold > mean, (
            "a threshold at or below the device's own mean is what produced "
            "306 state events from one Chromecast"
        )
        assert threshold > DEFAULT

    def test_a_fast_device_never_gets_a_looser_threshold(self):
        """The global default is a floor, never a ceiling. Learning must only
        make the app quieter about odd devices, never louder about normal ones
        — and never hide a real regression on a fast host."""
        rtts = [4.0 + (i % 3) for i in range(200)]
        assert derive_degraded_threshold(rtts, DEFAULT) == DEFAULT

    def test_zero_variance_still_leaves_headroom(self):
        """mean + 2*0 == mean, which lands the threshold exactly on the boundary
        and reproduces the defect with different arithmetic."""
        rtts = [900.0] * 200
        threshold = derive_degraded_threshold(rtts, DEFAULT)
        assert threshold > 900.0

    def test_unreachable_samples_are_excluded(self):
        """rtt < 0 means 'no reply', not 'a very fast reply'. Averaging -1 in
        would drag the learned mean down and tighten the threshold."""
        clean = [200.0] * 200
        dirty = clean + [-1.0] * 50
        assert derive_degraded_threshold(dirty, DEFAULT) == pytest.approx(
            derive_degraded_threshold(clean, DEFAULT)
        )

    def test_empty_input_is_the_default(self):
        assert derive_degraded_threshold([], DEFAULT) == DEFAULT


# ── Hour-of-week duty cycle ──────────────────────────────────────────────────

class TestHourOfWeek:
    def test_bucket_is_in_range(self):
        assert 0 <= hour_of_week(int(time.time())) < 168

    def test_same_hour_next_week_is_the_same_bucket(self):
        ts = 1_780_000_000
        assert hour_of_week(ts) == hour_of_week(ts + 7 * 86400)

    def test_an_hour_later_is_the_next_bucket(self):
        ts = 1_780_000_000
        assert hour_of_week(ts + 3600) == (hour_of_week(ts) + 1) % 168


class TestDeriveHourOfWeekDowntime:
    def test_empty_history_yields_no_buckets(self):
        assert derive_hour_of_week_downtime([]) == {}

    def test_a_bucket_that_is_always_down_reads_as_one(self):
        base = 1_780_000_000
        pts = [_Point(base + w * 7 * 86400, state="DOWN") for w in range(5)]
        buckets = derive_hour_of_week_downtime(pts)
        assert buckets[hour_of_week(base)] == pytest.approx(1.0)

    def test_a_bucket_that_is_never_down_reads_as_zero(self):
        base = 1_780_000_000
        pts = [_Point(base + w * 7 * 86400, state="UP") for w in range(5)]
        assert derive_hour_of_week_downtime(pts)[hour_of_week(base)] == 0.0

    def test_thin_buckets_are_dropped_not_reported_as_certain(self):
        """One observation in a bucket is not a duty cycle. Reporting 1.0 from
        a single sample would silently suppress a real first-ever outage."""
        pts = [_Point(1_780_000_000, state="DOWN")]
        assert derive_hour_of_week_downtime(pts) == {}

    def test_degraded_counts_as_reachable(self):
        base = 1_780_000_000
        pts = [_Point(base + w * 7 * 86400, state="DEGRADED") for w in range(5)]
        assert derive_hour_of_week_downtime(pts)[hour_of_week(base)] == 0.0


# ── The cached facade ────────────────────────────────────────────────────────

class TestDeviceBaselines:
    def test_unknown_host_gets_the_default_threshold(self):
        bl = DeviceBaselines(_FakeStore(), default_degraded_ms=DEFAULT)
        assert bl.degraded_threshold("10.0.0.1") == DEFAULT

    def test_learned_threshold_is_used_once_there_is_enough_history(self):
        now = int(time.time())
        pts = [
            _Point(now - i * 60, state="UP", rtt_ms=194.0 + (i % 5))
            for i in range(MIN_BASELINE_SAMPLES * 3)
        ]
        bl = DeviceBaselines(
            _FakeStore({"10.0.0.54": pts}), default_degraded_ms=DEFAULT
        )
        assert bl.degraded_threshold("10.0.0.54") > DEFAULT

    def test_the_store_is_not_queried_once_per_call(self):
        """This sits on the 60 s availability cycle for every target; a query
        per host per cycle would put real I/O on the monitor thread."""
        store = _FakeStore()
        bl = DeviceBaselines(store, default_degraded_ms=DEFAULT)
        for _ in range(20):
            bl.degraded_threshold("10.0.0.1")
        assert store.calls == 1

    def test_invalidate_forces_a_refresh(self):
        store = _FakeStore()
        bl = DeviceBaselines(store, default_degraded_ms=DEFAULT)
        bl.degraded_threshold("10.0.0.1")
        bl.invalidate()
        bl.degraded_threshold("10.0.0.1")
        assert store.calls == 2

    def test_a_store_error_falls_back_to_the_default(self):
        """A baseline is an optimisation. It must never take the monitor down."""
        class _Broken:
            def query_device_state_history(self, ip, hours=24.0):
                raise RuntimeError("database is locked")

        bl = DeviceBaselines(_Broken(), default_degraded_ms=DEFAULT)
        assert bl.degraded_threshold("10.0.0.1") == DEFAULT

    def test_no_store_is_tolerated(self):
        bl = DeviceBaselines(None, default_degraded_ms=DEFAULT)
        assert bl.degraded_threshold("10.0.0.1") == DEFAULT
        assert bl.is_expected_down("10.0.0.1") is None

    def test_is_expected_down_is_none_without_evidence(self):
        """Unknown must never read as 'expected' — that would suppress the
        first outage of every device on a fresh install."""
        bl = DeviceBaselines(_FakeStore(), default_degraded_ms=DEFAULT)
        assert bl.is_expected_down("10.0.0.1") is None

    def test_is_expected_down_true_for_a_habitually_absent_hour(self):
        base = int(time.time()) - 21 * 86400
        pts = []
        for w in range(4):                       # same hour-of-week, 4 weeks
            for m in range(6):
                pts.append(_Point(base + w * 7 * 86400 + m * 60, state="DOWN"))
        bl = DeviceBaselines(
            _FakeStore({"10.0.0.54": pts}), default_degraded_ms=DEFAULT,
            window_days=28,
        )
        assert bl.is_expected_down("10.0.0.54", base) is True

    def test_is_expected_down_false_for_an_hour_it_is_normally_up(self):
        base = int(time.time()) - 21 * 86400
        pts = []
        for w in range(4):
            for m in range(6):
                pts.append(_Point(base + w * 7 * 86400 + m * 60, state="UP"))
        bl = DeviceBaselines(
            _FakeStore({"10.0.0.54": pts}), default_degraded_ms=DEFAULT,
            window_days=28,
        )
        assert bl.is_expected_down("10.0.0.54", base) is False


# ── Confirmation constant ────────────────────────────────────────────────────

def test_down_confirmation_is_at_least_two_cycles():
    """One missed ping is not an outage — that is the churn source. But it must
    stay small: it is latency added ahead of every real outage alert."""
    assert 2 <= DOWN_CONFIRMATION_CYCLES <= 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
