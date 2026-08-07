"""
Phase 6's three engine-side defaults changes.

1. `AlertRule.min_consecutive` — generalises `_SERVICE_DOWN_MIN_CONSECUTIVE_FAILS`,
   a hardcoded 3 that HOST_DOWN never got and that no rule could tune.
2. Restart-safe dedup — `_last_fired` is in-memory, so every restart reset every
   cooldown and a still-true condition re-alerted on launch.
3. RTT_ANOMALY's absolute floor — measured and deliberately deferred out of
   Phase 4 because it is a defaults decision. See the numbers in the module.
"""
from __future__ import annotations

import time

import pytest

from modules.alert_engine import AlertEngine
from modules.alert_types import AlertRule


# ── 1. AlertRule.min_consecutive ─────────────────────────────────────────────

class TestMinConsecutive:
    def test_defaults_to_one(self):
        """1 = pure edge-triggering, the shipped availability behaviour. A
        higher default would silently delay every rule's first alert."""
        assert AlertRule(name="r", rule_type="HOST_DOWN").min_consecutive == 1

    def test_rejects_less_than_one(self):
        """0 would admit a condition that was never observed."""
        with pytest.raises(ValueError):
            AlertRule(name="r", rule_type="HOST_DOWN", min_consecutive=0)

    def test_service_down_default_rule_keeps_its_grace_period(self):
        """The hardcoded 3 becomes a field value, not a behaviour change: a
        target that was never reachable must still not fire on check one."""
        from modules.alert_suppressor import _default_rules
        rule = next(r for r in _default_rules() if r.rule_type == "SERVICE_DOWN")
        assert rule.min_consecutive == 3

    def test_service_down_honours_the_rule_not_the_module_constant(self):
        rule = AlertRule(name="svc", rule_type="SERVICE_DOWN", cooldown_s=0,
                         enabled=True, min_consecutive=1)
        engine = AlertEngine(store=None, rules=[rule])
        results = [{"host": "10.0.0.1", "port": 443, "up": False, "label": "api"}]
        fired = engine.evaluate_service_checks(results)
        assert fired, "min_consecutive=1 must alert on the first failed check"

    def test_service_down_still_waits_when_the_rule_asks_it_to(self):
        rule = AlertRule(name="svc", rule_type="SERVICE_DOWN", cooldown_s=0,
                         enabled=True, min_consecutive=3)
        engine = AlertEngine(store=None, rules=[rule])
        results = [{"host": "10.0.0.1", "port": 443, "up": False, "label": "api"}]
        assert engine.evaluate_service_checks(results) == []
        assert engine.evaluate_service_checks(results) == []
        assert engine.evaluate_service_checks(results), "third failure should fire"

    def test_host_down_stays_at_one_so_criterion_5_still_holds(self):
        """Raising HOST_DOWN's confirmation would push the first gateway alert
        past acceptance criterion 5's three-minute budget — the monitor layer
        already carries its own DOWN confirmation."""
        from modules.alert_suppressor import _default_rules
        rule = next(r for r in _default_rules() if r.rule_type == "HOST_DOWN")
        assert rule.min_consecutive == 1


# ── 2. Restart-safe dedup ────────────────────────────────────────────────────

class TestLastFiredPersistence:
    def test_load_last_fired_suppresses_a_repeat_within_cooldown(self):
        now = int(time.time())
        rule = AlertRule(name="Host Down", rule_type="HOST_DOWN",
                         cooldown_s=600, enabled=True)
        engine = AlertEngine(store=None, rules=[rule])
        engine.load_last_fired({"Host Down::10.0.0.1": now - 60})

        fired = engine.evaluate_cycle(
            {"states": {"10.0.0.1": "DOWN"}, "rtts": {"10.0.0.1": -1.0}}
        )
        assert fired == [], (
            "a restart must not re-announce an outage it already reported "
            "60 seconds ago"
        )

    def test_an_expired_entry_does_not_suppress(self):
        now = int(time.time())
        rule = AlertRule(name="Host Down", rule_type="HOST_DOWN",
                         cooldown_s=60, enabled=True)
        engine = AlertEngine(store=None, rules=[rule])
        engine.load_last_fired({"Host Down::10.0.0.1": now - 600})
        assert engine.evaluate_cycle(
            {"states": {"10.0.0.1": "DOWN"}, "rtts": {"10.0.0.1": -1.0}}
        )

    def test_ignores_malformed_rows(self):
        engine = AlertEngine(store=None, rules=[])
        engine.load_last_fired({"": 1, "ok::h": "not-an-int", None: 5})
        engine.load_last_fired(None)  # must not raise

    def test_newest_wins_per_key(self):
        engine = AlertEngine(store=None, rules=[])
        engine.load_last_fired({"a::h": 100})
        engine.load_last_fired({"a::h": 50})
        assert engine._last_fired["a::h"] == 100, (
            "an older row must not shadow a more recent firing"
        )


# ── 3. RTT_ANOMALY absolute floor ────────────────────────────────────────────

class _Metric:
    def __init__(self, mean, sigma, days=30.0):
        self.mean, self._sigma, self.days_covered = mean, sigma, days
        self.is_valid = True

    def anomaly_threshold(self, sigma):
        return self.mean + sigma * self._sigma


class _Baseline:
    def __init__(self, metric):
        self.rtt_ms = metric


class _Learner:
    def __init__(self, metric):
        self._b = _Baseline(metric)

    def get_host_baseline(self, host):
        return self._b


def _engine():
    rule = AlertRule(name="RTT Anomaly", rule_type="RTT_ANOMALY", sigma=2.0,
                     cooldown_s=0, enabled=True)
    return AlertEngine(store=None, rules=[rule])


class TestRttAnomalyFloor:
    def test_the_floor_is_the_apps_existing_definition_of_slow(self):
        """Not an invented number: availability_monitor's degraded threshold."""
        from modules.alert_engine_checks2 import _RTT_ANOMALY_FLOOR_MS
        from modules.availability_monitor import DEFAULT_DEGRADED_THRESHOLD
        assert _RTT_ANOMALY_FLOOR_MS == DEFAULT_DEGRADED_THRESHOLD

    def test_a_stable_host_does_not_alert_on_a_few_milliseconds(self):
        """The defect the floor exists to fix. Fixing the maturity gate took the
        reference database from 0 to 21 of 26 hosts mature, and a very stable
        host learns a very tight mean+2sigma — 2.0 ms on the gateway, so a 3 ms
        reply read as 'responding slower than its usual pattern'."""
        learner = _Learner(_Metric(mean=1.0, sigma=0.5))   # threshold = 2.0 ms
        assert _engine().evaluate_rtt_anomaly_checks({"192.168.68.1": 3.0}, learner) == []

    def test_the_old_shipped_example_no_longer_fires(self):
        """mean 20 / sigma 5 / observed 45 ms was pinned by
        test_alert_engine_v6_sprint2.py. It is below the floor, so it stops
        firing — a deliberate semantics change, not a fixup."""
        learner = _Learner(_Metric(mean=20.0, sigma=5.0))  # threshold = 30 ms
        assert _engine().evaluate_rtt_anomaly_checks({"10.0.0.1": 45.0}, learner) == []

    def test_a_genuinely_slow_host_still_alerts(self):
        learner = _Learner(_Metric(mean=20.0, sigma=5.0))
        assert _engine().evaluate_rtt_anomaly_checks({"10.0.0.1": 400.0}, learner)

    def test_the_floor_is_a_floor_never_a_ceiling(self):
        """A host that normally answers in 600 ms keeps its higher learned
        threshold — the floor must not become a mute button in either
        direction."""
        learner = _Learner(_Metric(mean=600.0, sigma=50.0))  # threshold = 700 ms
        engine = _engine()
        assert engine.evaluate_rtt_anomaly_checks({"10.0.0.2": 400.0}, learner) == [], (
            "400 ms is above the 150 ms floor but normal for THIS host"
        )
        assert engine.evaluate_rtt_anomaly_checks({"10.0.0.2": 900.0}, learner)

    def test_an_immature_baseline_is_still_gated(self):
        learner = _Learner(_Metric(mean=20.0, sigma=5.0, days=2.0))
        assert _engine().evaluate_rtt_anomaly_checks({"10.0.0.1": 999.0}, learner) == []

    def test_resolution_fires_once_the_host_returns_to_normal(self):
        learner = _Learner(_Metric(mean=200.0, sigma=20.0))  # threshold = 240 ms
        engine = _engine()
        assert engine.evaluate_rtt_anomaly_checks({"10.0.0.3": 500.0}, learner)
        resolved = engine.evaluate_rtt_anomaly_checks({"10.0.0.3": 210.0}, learner)
        assert resolved and resolved[0].is_resolution
