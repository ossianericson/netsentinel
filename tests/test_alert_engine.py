"""
Tests for modules/alert_engine.py
"""
import time
import pytest

from modules.alert_engine import (
    AlertEngine, AlertFired, AlertRule, RULE_TYPES, _default_rules,
)


# ── AlertRule validation ──────────────────────────────────────────────────────

class TestAlertRule:
    def test_valid_rule_types_accepted(self):
        for rt in RULE_TYPES:
            r = AlertRule(name="x", rule_type=rt)
            assert r.rule_type == rt

    def test_rule_type_uppercased(self):
        r = AlertRule(name="x", rule_type="rtt_threshold")
        assert r.rule_type == "RTT_THRESHOLD"

    def test_invalid_rule_type_raises(self):
        with pytest.raises(ValueError, match="Unknown rule_type"):
            AlertRule(name="x", rule_type="INVALID")

    def test_defaults(self):
        r = AlertRule(name="x", rule_type="HOST_DOWN")
        assert r.host is None
        assert r.enabled is True
        assert r.cooldown_s == 300


# ── Default rules ─────────────────────────────────────────────────────────────

class TestDefaultRules:
    def test_returns_non_empty_list(self):
        rules = _default_rules()
        assert len(rules) > 0

    def test_all_rules_valid(self):
        for r in _default_rules():
            assert r.rule_type in RULE_TYPES

    def test_all_default_rules_disabled(self):
        """All built-in rules must default to disabled — users must opt in."""
        for r in _default_rules():
            assert r.enabled is False, (
                f"Rule {r.name!r} must default to enabled=False "
                f"(opt-in only — RULE: no alert fires without explicit user consent)"
            )


# ── evaluate_cycle — RTT_THRESHOLD ───────────────────────────────────────────

def _engine_with(*rules):
    return AlertEngine(store=None, rules=list(rules))


def _cycle(states, rtts, ts=None):
    return {"ts": ts or int(time.time()), "states": states, "rtts": rtts}


class TestRttThreshold:
    def test_fires_when_rtt_exceeds_threshold(self):
        eng = _engine_with(AlertRule("High RTT", "RTT_THRESHOLD", threshold_ms=100.0, cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"8.8.8.8": "DEGRADED"}, {"8.8.8.8": 250.0}))
        assert len(fired) == 1
        assert fired[0].rule_type == "RTT_THRESHOLD"
        assert fired[0].value == pytest.approx(250.0)

    def test_no_fire_when_rtt_at_threshold(self):
        eng = _engine_with(AlertRule("High RTT", "RTT_THRESHOLD", threshold_ms=200.0, cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"8.8.8.8": "UP"}, {"8.8.8.8": 200.0}))
        assert fired == []

    def test_no_fire_when_rtt_below_threshold(self):
        eng = _engine_with(AlertRule("High RTT", "RTT_THRESHOLD", threshold_ms=200.0, cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"8.8.8.8": "UP"}, {"8.8.8.8": 10.0}))
        assert fired == []

    def test_no_fire_when_host_unreachable(self):
        # rtt=-1 means down — RTT_THRESHOLD should not double-fire; HOST_DOWN handles it
        eng = _engine_with(AlertRule("High RTT", "RTT_THRESHOLD", threshold_ms=100.0, cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"8.8.8.8": "DOWN"}, {"8.8.8.8": -1.0}))
        assert fired == []


# ── evaluate_cycle — HOST_DOWN ────────────────────────────────────────────────

class TestHostDown:
    def test_fires_on_down_state(self):
        eng = _engine_with(AlertRule("Down", "HOST_DOWN", cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"10.0.0.1": "DOWN"}, {"10.0.0.1": -1.0}))
        assert len(fired) == 1
        assert fired[0].severity == "CRITICAL"

    def test_no_fire_when_up(self):
        eng = _engine_with(AlertRule("Down", "HOST_DOWN", cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"10.0.0.1": "UP"}, {"10.0.0.1": 10.0}))
        assert fired == []

    def test_host_filter(self):
        eng = _engine_with(AlertRule("Down", "HOST_DOWN", host="10.0.0.1", cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle(
            {"10.0.0.1": "DOWN", "10.0.0.2": "DOWN"},
            {"10.0.0.1": -1.0,  "10.0.0.2": -1.0},
        ))
        # Only the specific host should fire
        assert len(fired) == 1
        assert fired[0].host == "10.0.0.1"


# ── evaluate_cycle — HOST_DEGRADED ───────────────────────────────────────────

class TestHostDegraded:
    def test_fires_on_degraded_state(self):
        eng = _engine_with(AlertRule("Degrad", "HOST_DEGRADED", cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"h": "DEGRADED"}, {"h": 999.0}))
        assert len(fired) == 1
        assert fired[0].severity == "WARNING"

    def test_no_fire_when_up(self):
        eng = _engine_with(AlertRule("Degrad", "HOST_DEGRADED", cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"h": "UP"}, {"h": 10.0}))
        assert fired == []


# ── evaluate_cycle — LOSS_THRESHOLD ──────────────────────────────────────────

class TestLossThreshold:
    def test_fires_when_host_unreachable(self):
        eng = _engine_with(AlertRule("Loss", "LOSS_THRESHOLD", cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"h": "DOWN"}, {"h": -1.0}))
        assert len(fired) == 1
        assert fired[0].value == pytest.approx(100.0)

    def test_no_fire_when_reachable(self):
        eng = _engine_with(AlertRule("Loss", "LOSS_THRESHOLD", cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"h": "UP"}, {"h": 20.0}))
        assert fired == []


# ── Cooldown ──────────────────────────────────────────────────────────────────

class TestCooldown:
    def test_second_fire_suppressed_within_cooldown(self):
        eng = _engine_with(AlertRule("Down", "HOST_DOWN", cooldown_s=300))
        now = int(time.time())
        c = _cycle({"h": "DOWN"}, {"h": -1.0}, ts=now)
        eng.evaluate_cycle(c)
        # Second evaluation 10 s later — still within cooldown
        c2 = _cycle({"h": "DOWN"}, {"h": -1.0}, ts=now + 10)
        fired = eng.evaluate_cycle(c2)
        assert fired == []

    def test_fires_again_after_cooldown(self):
        eng = _engine_with(AlertRule("Down", "HOST_DOWN", cooldown_s=60))
        now = int(time.time())
        eng.evaluate_cycle(_cycle({"h": "DOWN"}, {"h": -1.0}, ts=now))
        fired = eng.evaluate_cycle(_cycle({"h": "DOWN"}, {"h": -1.0}, ts=now + 61))
        assert len(fired) == 1

    def test_cooldown_zero_fires_every_time(self):
        eng = _engine_with(AlertRule("Down", "HOST_DOWN", cooldown_s=0))
        now = int(time.time())
        eng.evaluate_cycle(_cycle({"h": "DOWN"}, {"h": -1.0}, ts=now))
        fired = eng.evaluate_cycle(_cycle({"h": "DOWN"}, {"h": -1.0}, ts=now + 1))
        assert len(fired) == 1


# ── Disabled rule ─────────────────────────────────────────────────────────────

class TestDisabledRule:
    def test_disabled_rule_never_fires(self):
        eng = _engine_with(AlertRule("Down", "HOST_DOWN", enabled=False, cooldown_s=0))
        fired = eng.evaluate_cycle(_cycle({"h": "DOWN"}, {"h": -1.0}))
        assert fired == []


# ── on_alert callback ─────────────────────────────────────────────────────────

class TestOnAlertCallback:
    def test_callback_called_on_fire(self):
        received = []
        eng = _engine_with(AlertRule("Down", "HOST_DOWN", cooldown_s=0))
        eng.set_on_alert(received.append)
        eng.evaluate_cycle(_cycle({"h": "DOWN"}, {"h": -1.0}))
        assert len(received) == 1
        assert isinstance(received[0], AlertFired)

    def test_callback_not_called_when_no_fire(self):
        received = []
        eng = _engine_with(AlertRule("Down", "HOST_DOWN", cooldown_s=0))
        eng.set_on_alert(received.append)
        eng.evaluate_cycle(_cycle({"h": "UP"}, {"h": 10.0}))
        assert received == []


# ── evaluate_tracker_result ───────────────────────────────────────────────────

class TestTrackerResult:
    def _make_tracker_result(self, new=(), gone=()):
        from dataclasses import dataclass, field
        from typing import List

        @dataclass
        class FakeDev:
            mac: str; ip: str = ""; hostname: str = ""; vendor: str = ""; device_type: str = ""

        @dataclass
        class FakeResult:
            new_devices: List = field(default_factory=list)
            gone_devices: List = field(default_factory=list)

        return FakeResult(
            new_devices=[FakeDev(mac=m) for m in new],
            gone_devices=[FakeDev(mac=m) for m in gone],
        )

    def test_new_device_fires(self):
        eng = _engine_with(AlertRule("New", "NEW_DEVICE", cooldown_s=0))
        tr = self._make_tracker_result(new=["aa:bb:cc:00:00:01"])
        fired = eng.evaluate_tracker_result(tr)
        assert len(fired) == 1
        assert fired[0].rule_type == "NEW_DEVICE"

    def test_gone_device_fires(self):
        eng = _engine_with(AlertRule("Gone", "DEVICE_GONE", cooldown_s=0))
        tr = self._make_tracker_result(gone=["aa:bb:cc:00:00:01"])
        fired = eng.evaluate_tracker_result(tr)
        assert len(fired) == 1
        assert fired[0].rule_type == "DEVICE_GONE"

    def test_no_fire_when_empty(self):
        eng = _engine_with(
            AlertRule("New", "NEW_DEVICE", cooldown_s=0),
            AlertRule("Gone", "DEVICE_GONE", cooldown_s=0),
        )
        fired = eng.evaluate_tracker_result(self._make_tracker_result())
        assert fired == []

    def test_multiple_new_devices(self):
        eng = _engine_with(AlertRule("New", "NEW_DEVICE", cooldown_s=0))
        tr = self._make_tracker_result(new=["aa:bb:cc:00:00:01", "aa:bb:cc:00:00:02"])
        fired = eng.evaluate_tracker_result(tr)
        assert len(fired) == 2


# ── set_rules / get_rules ─────────────────────────────────────────────────────

class TestSetGetRules:
    def test_set_rules_replaces_existing(self):
        eng = AlertEngine()
        new_rules = [AlertRule("r", "HOST_DOWN")]
        eng.set_rules(new_rules)
        assert len(eng.get_rules()) == 1

    def test_get_rules_returns_copy(self):
        eng = AlertEngine()
        rules = eng.get_rules()
        rules.clear()
        assert len(eng.get_rules()) > 0   # original unchanged


# ── AlertFired fields ─────────────────────────────────────────────────────────

class TestAlertFiredFields:
    def test_all_fields_set(self):
        eng = _engine_with(AlertRule("High RTT", "RTT_THRESHOLD", threshold_ms=50.0, cooldown_s=0))
        now = int(time.time())
        fired = eng.evaluate_cycle(_cycle({"h": "DEGRADED"}, {"h": 999.0}, ts=now))
        assert len(fired) == 1
        a = fired[0]
        assert a.rule_name  == "High RTT"
        assert a.rule_type  == "RTT_THRESHOLD"
        assert a.host       == "h"
        assert a.ts         == now
        assert isinstance(a.message, str) and len(a.message) > 0
