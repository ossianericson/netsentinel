"""
Tests for per-device alert scoping in the AlertEngine.

Background: historically every broadcast rule (rule.host is None) was evaluated
against every device seen in the last scan, so device-health alerts (HOST_DOWN,
RTT_THRESHOLD, FLAP, ...) fired for guest phones, IoT bulbs, and other transient
devices nobody asked to monitor. This adds an opt-in scope filter: device-scoped
rules only fire for a host the injected scope checker approves (infrastructure
roles + user opt-in). Genuine security-event rules (NEW_DEVICE, ARP_SPOOF, ...)
are never gated.

Covers:
  • DEVICE_SCOPED_RULE_TYPES and SECURITY_RELEVANT_RULE_TYPES are subsets of the
    canonical RULE_TYPES set (drift guard).
  • The two sets are disjoint (a rule type is either device-scoped or a broadcast
    security event, never both).
  • A device-scoped rule (HOST_DOWN) does NOT fire for an out-of-scope host.
  • The same rule DOES fire for an in-scope host.
  • With no scope checker set (default), all hosts are allowed (back-compat).
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock


def _make_engine():
    from modules.alert_engine import AlertEngine
    store = MagicMock()
    store.get_known_devices.return_value = {}
    return AlertEngine(store=store)


def _enable_host_down(engine):
    rules = engine.get_rules()
    for r in rules:
        r.enabled = r.rule_type == "HOST_DOWN"
    engine.set_rules(rules)


def _down_cycle(host: str):
    return {
        "devices": [{"ip": host, "mac": "aa:bb:cc:dd:ee:01", "risk_level": "LOW"}],
        "rtts": {host: -1.0},
        "states": {host: "DOWN"},
        "ts": int(time.time()),
    }


# ── Constant integrity ────────────────────────────────────────────────────────

class TestRuleTypeConstants:
    def test_device_scoped_subset_of_rule_types(self):
        from modules.alert_types import DEVICE_SCOPED_RULE_TYPES, RULE_TYPES
        assert DEVICE_SCOPED_RULE_TYPES <= RULE_TYPES, (
            f"Unknown rule types in DEVICE_SCOPED_RULE_TYPES: "
            f"{DEVICE_SCOPED_RULE_TYPES - RULE_TYPES}"
        )

    def test_security_relevant_subset_of_rule_types(self):
        from modules.alert_types import SECURITY_RELEVANT_RULE_TYPES, RULE_TYPES
        assert SECURITY_RELEVANT_RULE_TYPES <= RULE_TYPES, (
            f"Unknown rule types in SECURITY_RELEVANT_RULE_TYPES: "
            f"{SECURITY_RELEVANT_RULE_TYPES - RULE_TYPES}"
        )

    def test_sets_are_disjoint(self):
        from modules.alert_types import (
            DEVICE_SCOPED_RULE_TYPES, SECURITY_RELEVANT_RULE_TYPES,
        )
        overlap = DEVICE_SCOPED_RULE_TYPES & SECURITY_RELEVANT_RULE_TYPES
        assert not overlap, f"Rule types in both sets: {overlap}"

    def test_host_down_is_device_scoped(self):
        from modules.alert_types import DEVICE_SCOPED_RULE_TYPES
        assert "HOST_DOWN" in DEVICE_SCOPED_RULE_TYPES


# ── Scope filtering behaviour ─────────────────────────────────────────────────

class TestDeviceScopeFilter:
    def test_out_of_scope_host_does_not_fire(self):
        engine = _make_engine()
        _enable_host_down(engine)
        engine.set_alert_scope_checker(lambda host: False)  # nothing in scope
        fired = engine.evaluate_cycle(_down_cycle("192.168.1.50"))
        assert not any(a.rule_type == "HOST_DOWN" for a in fired), (
            "HOST_DOWN must not fire for an out-of-scope device"
        )

    def test_in_scope_host_fires(self):
        engine = _make_engine()
        _enable_host_down(engine)
        engine.set_alert_scope_checker(lambda host: host == "192.168.1.1")
        fired = engine.evaluate_cycle(_down_cycle("192.168.1.1"))
        assert any(a.rule_type == "HOST_DOWN" for a in fired), (
            "HOST_DOWN must fire for an in-scope device"
        )

    def test_no_checker_allows_all(self):
        engine = _make_engine()
        _enable_host_down(engine)
        # No set_alert_scope_checker call — default must be all-allowed (back-compat)
        fired = engine.evaluate_cycle(_down_cycle("10.0.0.9"))
        assert any(a.rule_type == "HOST_DOWN" for a in fired), (
            "With no scope checker, all hosts must be allowed"
        )

    def test_none_checker_disables_filter(self):
        engine = _make_engine()
        _enable_host_down(engine)
        engine.set_alert_scope_checker(lambda host: False)
        engine.set_alert_scope_checker(None)  # explicitly disable
        fired = engine.evaluate_cycle(_down_cycle("10.0.0.9"))
        assert any(a.rule_type == "HOST_DOWN" for a in fired)


# ── Composite dedup-key identity mismatch (IOT_BEHAVIOR / TREND_FORECAST) ─────
#
# IOT_BEHAVIOR and TREND_FORECAST are device-scoped, but _fire_if_cooled's
# cooldown dedup key for these two rule types is a composite string
# (f"{host}::{alert_type}" / f"{result.host}::{result.metric}"), not the plain
# host. If the scope check used that composite string, it would never match a
# known_device row and would silently suppress these alerts for every device,
# even an in-scope one. _fire_if_cooled must accept a scope_host override used
# only for the scope check.

class TestCompositeKeyScopeResolution:
    def test_iot_behavior_fires_for_in_scope_host_despite_composite_key(self):
        from modules.alert_engine import AlertEngine
        from unittest.mock import MagicMock

        store = MagicMock()
        store.get_known_devices.return_value = {}
        engine = AlertEngine(store=store)
        rules = engine.get_rules()
        for r in rules:
            r.enabled = r.rule_type == "IOT_BEHAVIOR"
        engine.set_rules(rules)
        engine.set_alert_scope_checker(lambda host: host == "192.168.1.1")

        signal = MagicMock()
        signal.ip = "192.168.1.1"
        signal.mac = "aa:bb:cc:dd:ee:01"
        signal.severity = "HIGH"
        signal.device_label = "Test Device"
        signal.alert_type = "NEW_DEST"
        signal.detail = "connected to a new destination"

        fired = engine.evaluate_iot_behavior_checks([signal])
        assert any(a.rule_type == "IOT_BEHAVIOR" for a in fired), (
            "IOT_BEHAVIOR must fire for an in-scope host — the composite dedup "
            "key must not be used for the scope check"
        )

    def test_trend_forecast_fires_for_in_scope_host_despite_composite_key(self):
        from modules.alert_engine import AlertEngine
        from unittest.mock import MagicMock

        store = MagicMock()
        store.get_known_devices.return_value = {}
        engine = AlertEngine(store=store)
        rules = engine.get_rules()
        for r in rules:
            r.enabled = r.rule_type == "TREND_FORECAST"
        engine.set_rules(rules)
        engine.set_alert_scope_checker(lambda host: host == "192.168.1.1")

        result = MagicMock()
        result.host = "192.168.1.1"
        result.metric = "rtt_ms"
        result.severity = "WARNING"
        result.eta_hours = 2.0
        result.current_value = 150.0
        result.threshold = 200.0
        result.summary = "RTT trending toward threshold"

        trend_report = MagicMock()
        trend_report.results = [result]

        fired = engine.evaluate_trend_checks(trend_report)
        assert any(a.rule_type == "TREND_FORECAST" for a in fired), (
            "TREND_FORECAST must fire for an in-scope host — the composite dedup "
            "key must not be used for the scope check"
        )
