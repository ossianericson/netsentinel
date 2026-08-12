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


# ── RULE-ID1: an address is a lease, not an identity ──────────────────────────

class TestTrackerResultKeysByMacNotIp:
    """`host = dev.ip or dev.mac` preferred the ambiguous key over the exact one.

    `host` is not just a display string: `_fire_if_cooled()` builds
    `f"{rule.name}::{host}"` and uses it as BOTH the cooldown dedup key and the
    acknowledgement-hold key. On the 7-of-20 reference-network addresses claimed
    by more than one MAC, that means one device's ack mutes a different device.

    The pre-existing `TestTrackerResult` cases above are structurally blind to
    this (RULE-DBG5's shape): they build `FakeDev(mac=...)` with the default
    empty `ip`, so the `or` falls through to the MAC and passes either way.
    Every device here carries BOTH fields, which is what production produces —
    `device_tracker._normalise()` returns None without a MAC, so a TrackedDevice
    always has one.
    """

    def _dev(self, mac: str, ip: str):
        from dataclasses import dataclass

        @dataclass
        class FakeDev:
            mac: str
            ip: str = ""
            hostname: str = ""
            vendor: str = ""
            device_type: str = ""

        return FakeDev(mac=mac, ip=ip)

    def _result(self, new=(), gone=()):
        from dataclasses import dataclass, field
        from typing import List

        @dataclass
        class FakeResult:
            new_devices: List = field(default_factory=list)
            gone_devices: List = field(default_factory=list)

        return FakeResult(new_devices=list(new), gone_devices=list(gone))

    SHARED_IP = "192.168.68.64"
    MAC_A = "dc:a6:32:2c:41:c7"
    MAC_B = "f0:72:ea:51:d3:b8"

    def test_new_device_alert_is_keyed_by_mac(self):
        eng = _engine_with(AlertRule("New", "NEW_DEVICE", cooldown_s=0))
        tr = self._result(new=[self._dev(self.MAC_A, self.SHARED_IP)])
        fired = eng.evaluate_tracker_result(tr)
        assert len(fired) == 1
        assert fired[0].host == self.MAC_A

    def test_gone_device_alert_is_keyed_by_mac(self):
        eng = _engine_with(AlertRule("Gone", "DEVICE_GONE", cooldown_s=0))
        tr = self._result(gone=[self._dev(self.MAC_A, self.SHARED_IP)])
        fired = eng.evaluate_tracker_result(tr)
        assert len(fired) == 1
        assert fired[0].host == self.MAC_A

    def test_two_devices_sharing_an_address_do_not_share_a_cooldown(self):
        # A long cooldown: with an IP key the second device is swallowed as a
        # duplicate of the first, because both resolve to the same dedup key.
        eng = _engine_with(AlertRule("Gone", "DEVICE_GONE", cooldown_s=3600))
        tr = self._result(gone=[
            self._dev(self.MAC_A, self.SHARED_IP),
            self._dev(self.MAC_B, self.SHARED_IP),
        ])
        fired = eng.evaluate_tracker_result(tr)
        assert len(fired) == 2, "a co-tenant on the same address was deduped away"
        assert {a.host for a in fired} == {self.MAC_A, self.MAC_B}

    def test_acking_one_device_does_not_mute_its_address_co_tenant(self):
        eng = _engine_with(AlertRule("Gone", "DEVICE_GONE", cooldown_s=0))
        eng.set_ack_hold_seconds(86400)

        first = eng.evaluate_tracker_result(
            self._result(gone=[self._dev(self.MAC_A, self.SHARED_IP)])
        )
        assert len(first) == 1
        eng.note_acknowledged(first[0].rule_name, first[0].host)

        # A DIFFERENT device that happens to hold the same address must still alert.
        second = eng.evaluate_tracker_result(
            self._result(gone=[self._dev(self.MAC_B, self.SHARED_IP)])
        )
        assert len(second) == 1, "ack on one MAC muted a different MAC on the same IP"
        assert second[0].host == self.MAC_B

    def test_address_is_still_used_when_the_device_has_no_mac(self):
        # The fallback must stay intact: an IP is better than nothing.
        eng = _engine_with(AlertRule("Gone", "DEVICE_GONE", cooldown_s=0))
        tr = self._result(gone=[self._dev("", self.SHARED_IP)])
        fired = eng.evaluate_tracker_result(tr)
        assert len(fired) == 1
        assert fired[0].host == self.SHARED_IP


# ── set_rules / get_rules ─────────────────────────────────────────────────────

class TestMaintenanceSuppressionRecording:
    """Sprint 5: MaintenanceWindowManager.record_suppression() was dead plumbing
    (never called). AlertEngine must now call an injected suppression recorder
    whenever an alert is dropped because a maintenance window covers the host."""

    def test_suppression_recorder_called_when_alert_suppressed(self):
        eng = _engine_with(AlertRule("High RTT", "RTT_THRESHOLD", threshold_ms=100.0, cooldown_s=0))
        eng.set_maintenance_checker(lambda host: "Nightly Quiet Hours")
        calls = []
        eng.set_suppression_recorder(
            lambda window_label, host, rule_name, severity, message: calls.append(
                (window_label, host, rule_name, severity, message)
            )
        )
        fired = eng.evaluate_cycle(_cycle({"8.8.8.8": "DEGRADED"}, {"8.8.8.8": 250.0}))
        assert fired == []
        assert len(calls) == 1
        window_label, host, rule_name, severity, message = calls[0]
        assert window_label == "Nightly Quiet Hours"
        assert host == "8.8.8.8"
        assert rule_name == "High RTT"

    def test_suppression_recorder_not_called_when_not_suppressed(self):
        eng = _engine_with(AlertRule("High RTT", "RTT_THRESHOLD", threshold_ms=100.0, cooldown_s=0))
        eng.set_maintenance_checker(lambda host: None)  # no window covers this host
        calls = []
        eng.set_suppression_recorder(lambda *a: calls.append(a))
        fired = eng.evaluate_cycle(_cycle({"8.8.8.8": "DEGRADED"}, {"8.8.8.8": 250.0}))
        assert len(fired) == 1
        assert calls == []

    def test_no_recorder_set_does_not_raise(self):
        """Default (no recorder injected) must behave exactly as before."""
        eng = _engine_with(AlertRule("High RTT", "RTT_THRESHOLD", threshold_ms=100.0, cooldown_s=0))
        eng.set_maintenance_checker(lambda host: "Some Window")
        fired = eng.evaluate_cycle(_cycle({"8.8.8.8": "DEGRADED"}, {"8.8.8.8": 250.0}))
        assert fired == []


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
