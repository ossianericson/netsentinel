"""Tests for S4-1 (resolution tier), S4-3 (consolidation), S4-4 (action steps)."""
import time

from modules.alert_engine import AlertEngine, AlertRule, AlertFired


def _engine(**kwargs):
    """Create a minimal AlertEngine with one rule of the given type."""
    rule_type = kwargs.pop("rule_type", "HOST_DOWN")
    rules = [AlertRule(name="Test", rule_type=rule_type, cooldown_s=0, enabled=True, **kwargs)]
    return AlertEngine(rules=rules)


# ── S4-1: resolution tier ─────────────────────────────────────────────────────

def test_healthy_alert_fires_on_recovery():
    """A HEALTHY resolution alert should fire when a DOWN host becomes UP."""
    eng = _engine(rule_type="HOST_DOWN")
    now = int(time.time())

    # First cycle: host goes DOWN
    eng.evaluate_cycle({"ts": now, "states": {"192.168.1.1": "DOWN"}, "rtts": {}})
    # host should be tracked as down
    assert "192.168.1.1" in eng._host_down_since

    # Second cycle: host comes UP
    fired = eng.evaluate_cycle({"ts": now + 120, "states": {"192.168.1.1": "UP"}, "rtts": {}})

    healthy = [a for a in fired if a.severity == "HEALTHY"]
    assert len(healthy) == 1, f"Expected 1 HEALTHY alert, got: {fired}"
    assert healthy[0].is_resolution is True
    assert healthy[0].downtime_s == 120


def test_healthy_alert_includes_duration():
    """Resolution message should mention how long the host was down."""
    eng = _engine(rule_type="HOST_DOWN")
    now = int(time.time())
    eng.evaluate_cycle({"ts": now, "states": {"host1": "DOWN"}, "rtts": {}})
    fired = eng.evaluate_cycle({"ts": now + 300, "states": {"host1": "UP"}, "rtts": {}})
    healthy = [a for a in fired if a.severity == "HEALTHY"]
    assert healthy
    assert "5m" in healthy[0].message or "300" in healthy[0].message


def test_no_healthy_if_host_never_was_down():
    """If the host was never tracked as down, no resolution alert should fire."""
    eng = _engine(rule_type="HOST_DOWN")
    now = int(time.time())
    fired = eng.evaluate_cycle({"ts": now, "states": {"192.168.1.1": "UP"}, "rtts": {}})
    healthy = [a for a in fired if a.severity == "HEALTHY"]
    assert healthy == []


def test_service_resolution_on_recovery():
    """SERVICE_DOWN resolution fires when a service comes back up."""
    eng = _engine(rule_type="SERVICE_DOWN")

    service_result_down = [{"host": "192.168.1.1", "port": 80, "up": False, "label": "HTTP"}]
    service_result_up   = [{"host": "192.168.1.1", "port": 80, "up": True,  "label": "HTTP"}]

    eng.evaluate_service_checks(service_result_down)
    assert "192.168.1.1:80" in eng._service_down_since

    fired = eng.evaluate_service_checks(service_result_up)
    healthy = [a for a in fired if a.severity == "HEALTHY"]
    assert len(healthy) == 1
    assert healthy[0].is_resolution is True


def test_service_no_resolution_if_never_down():
    """If a service was never flagged as down, no resolution fires."""
    eng = _engine(rule_type="SERVICE_DOWN")
    result_up = [{"host": "192.168.1.1", "port": 80, "up": True, "label": "HTTP"}]
    fired = eng.evaluate_service_checks(result_up)
    assert not any(a.severity == "HEALTHY" for a in fired)


# ── S4-3: alert consolidation ─────────────────────────────────────────────────

def test_consolidation_fires_for_5_simultaneous_down():
    """5 simultaneous HOST_DOWN alerts should consolidate into one."""
    eng = AlertEngine(rules=[
        AlertRule(name="Host Down", rule_type="HOST_DOWN", cooldown_s=0, enabled=True)
    ])
    eng.set_consolidation_threshold(5)
    now = int(time.time())
    states = {f"192.168.1.{i}": "DOWN" for i in range(1, 6)}
    fired = eng.evaluate_cycle({"ts": now, "states": states, "rtts": {}})

    # Should be one consolidated alert, not 5 individual ones
    critical = [a for a in fired if a.severity == "CRITICAL" and not a.is_resolution]
    assert len(critical) == 1
    assert "simultaneously" in critical[0].message
    assert critical[0].host == "(network)"


def test_no_consolidation_below_threshold():
    """4 simultaneous HOST_DOWN alerts (below threshold of 5) should fire individually."""
    eng = AlertEngine(rules=[
        AlertRule(name="Host Down", rule_type="HOST_DOWN", cooldown_s=0, enabled=True)
    ])
    eng.set_consolidation_threshold(5)
    now = int(time.time())
    states = {f"192.168.1.{i}": "DOWN" for i in range(1, 5)}
    fired = eng.evaluate_cycle({"ts": now, "states": states, "rtts": {}})

    critical = [a for a in fired if a.severity == "CRITICAL" and not a.is_resolution]
    assert len(critical) == 4
    assert all(a.host != "(network)" for a in critical)


def test_consolidation_threshold_configurable():
    """set_consolidation_threshold changes the consolidation point."""
    eng = AlertEngine(rules=[
        AlertRule(name="Host Down", rule_type="HOST_DOWN", cooldown_s=0, enabled=True)
    ])
    eng.set_consolidation_threshold(3)
    now = int(time.time())
    states = {"a": "DOWN", "b": "DOWN", "c": "DOWN"}
    fired = eng.evaluate_cycle({"ts": now, "states": states, "rtts": {}})

    critical = [a for a in fired if a.severity == "CRITICAL" and not a.is_resolution]
    assert len(critical) == 1
    assert "simultaneously" in critical[0].message


# ── S4-4: plain-English action steps ─────────────────────────────────────────

def test_rtt_alert_has_action_step():
    """RTT alerts should include → action step text."""
    eng = AlertEngine(rules=[
        AlertRule(name="High RTT", rule_type="RTT_THRESHOLD",
                  threshold_ms=100.0, cooldown_s=0, enabled=True)
    ])
    now = int(time.time())
    fired = eng.evaluate_cycle({"ts": now, "states": {"8.8.8.8": "UP"}, "rtts": {"8.8.8.8": 200.0}})
    assert fired
    assert "→" in fired[0].message


def test_host_down_alert_has_action_step():
    """HOST_DOWN alerts should include → action step text."""
    eng = _engine(rule_type="HOST_DOWN")
    now = int(time.time())
    fired = eng.evaluate_cycle({"ts": now, "states": {"host1": "DOWN"}, "rtts": {}})
    down_alerts = [a for a in fired if a.rule_type == "HOST_DOWN" and not a.is_resolution]
    assert down_alerts
    assert "→" in down_alerts[0].message


def test_service_down_alert_has_action_step():
    """SERVICE_DOWN alerts should include action steps."""
    eng = _engine(rule_type="SERVICE_DOWN")
    result_down = [{"host": "192.168.1.1", "port": 443, "up": False, "label": "HTTPS"}]
    # 3 consecutive failed checks are required before the first CRITICAL fires
    # (grace period — see test_alert_engine_checks.py).
    eng.evaluate_service_checks(result_down)
    eng.evaluate_service_checks(result_down)
    fired = eng.evaluate_service_checks(result_down)
    critical = [a for a in fired if a.severity == "CRITICAL"]
    assert critical
    assert "→" in critical[0].message


def test_cert_expiry_alert_has_action_step():
    """CERT_EXPIRY alerts should include → action step text."""
    eng = AlertEngine(rules=[
        AlertRule(name="Cert Expiring", rule_type="CERT_EXPIRY",
                  threshold_days=30, cooldown_s=0, enabled=True)
    ])
    result = [{"host": "example.com", "port": 443,
               "is_expired": False, "days_remaining": 10, "error": None}]
    fired = eng.evaluate_cert_checks(result)
    assert fired
    assert "→" in fired[0].message


# ── AlertFired dataclass fields ───────────────────────────────────────────────

def test_alert_fired_has_resolution_fields():
    """AlertFired should have is_resolution and downtime_s fields."""
    a = AlertFired(
        rule_name="Test", rule_type="HOST_DOWN", host="x",
        message="back", severity="HEALTHY", ts=0,
        is_resolution=True, downtime_s=120,
    )
    assert a.is_resolution is True
    assert a.downtime_s == 120


def test_alert_fired_defaults_not_resolution():
    """Normal AlertFired should default to is_resolution=False."""
    a = AlertFired(
        rule_name="Test", rule_type="HOST_DOWN", host="x",
        message="down", severity="CRITICAL", ts=0,
    )
    assert a.is_resolution is False
    assert a.downtime_s is None


# ── Phase 4 — severity vocabulary and resolution routing ─────────────────────
#
# Two defects fixed here:
#   1. "HEALTHY" was absent from _SEVERITY_ORDER -> scored 0 (same as INFO) ->
#      a resolution was silently dropped by every channel with a min_severity
#      above INFO, even though the user had opted into the very rule that
#      fired the original alert.
#   2. 7 resolution call sites constructed AlertFired directly, bypassing
#      _fire_if_cooled's warmup / maintenance-window / device-scope checks --
#      a resolution for a host under maintenance, or out of the per-device
#      opt-in scope, still reached the router.

from unittest.mock import MagicMock  # noqa: E402


def _alert(severity="WARNING", rule_type="RTT_THRESHOLD", host="10.0.0.1", is_resolution=False):
    return AlertFired(
        rule_name="Test Rule", rule_type=rule_type, host=host,
        message="test message", severity=severity, ts=int(time.time()),
        is_resolution=is_resolution,
    )


class TestSeverityVocabulary:
    def test_healthy_ranked_with_warning(self):
        from modules.notification_router import _SEVERITY_ORDER
        assert _SEVERITY_ORDER["HEALTHY"] == _SEVERITY_ORDER["WARNING"]

    def test_high_ranked_with_critical(self):
        from modules.notification_router import _SEVERITY_ORDER
        assert _SEVERITY_ORDER["HIGH"] == _SEVERITY_ORDER["CRITICAL"]

    def test_medium_ranked_with_warning(self):
        from modules.notification_router import _SEVERITY_ORDER
        assert _SEVERITY_ORDER["MEDIUM"] == _SEVERITY_ORDER["WARNING"]

    def test_user_selectable_severity_levels_unchanged(self):
        from modules.notification_router import SEVERITY_LEVELS
        assert SEVERITY_LEVELS == ["INFO", "WARNING", "CRITICAL"]


class TestResolutionRouting:
    def test_healthy_resolution_reaches_a_warning_toast_channel(self):
        from modules.notification_router import NotificationRouter, ToastChannel

        r = NotificationRouter()
        cb = MagicMock()
        r.set_toast_callback(cb)
        r.set_channels([ToastChannel(enabled=True, min_severity="WARNING")])
        r.dispatch(_alert(severity="HEALTHY", is_resolution=True))
        cb.assert_called_once()

    def test_healthy_resolution_still_bypasses_a_critical_floor_channel(self):
        """Resolutions skip the severity floor entirely -- same reasoning
        dispatch_escalation() already uses for escalations."""
        from modules.notification_router import NotificationRouter, ToastChannel

        r = NotificationRouter()
        cb = MagicMock()
        r.set_toast_callback(cb)
        r.set_channels([ToastChannel(enabled=True, min_severity="CRITICAL")])
        r.dispatch(_alert(severity="HEALTHY", is_resolution=True))
        cb.assert_called_once()

    def test_non_resolution_healthy_still_gated_by_rule_types(self):
        from modules.notification_router import _matches_channel
        alert = _alert(severity="HEALTHY", rule_type="HOST_DOWN", is_resolution=True)
        assert _matches_channel(alert, "CRITICAL", ["CERT_EXPIRY"]) is False
        assert _matches_channel(alert, "CRITICAL", ["HOST_DOWN"]) is True

    def test_non_resolution_alert_still_respects_the_severity_floor(self):
        from modules.notification_router import _matches_channel
        alert = _alert(severity="INFO", is_resolution=False)
        assert _matches_channel(alert, "WARNING", []) is False


class TestFireResolution:
    def _rule(self, **kw):
        return AlertRule(name="Host Down", rule_type="HOST_DOWN", enabled=True, **kw)

    def test_returns_alert_fired_with_healthy_severity(self):
        eng = AlertEngine(store=None, rules=[])
        rule = self._rule()
        result = eng._fire_resolution(rule, "10.0.0.1", int(time.time()), "back online")
        assert result is not None
        assert result.severity == "HEALTHY"
        assert result.is_resolution is True
        assert result.rule_name == "Host Down"

    def test_suppressed_during_boot_warmup(self):
        eng = AlertEngine(store=None, rules=[])
        eng.set_warmup_period(60)
        rule = self._rule()
        result = eng._fire_resolution(rule, "10.0.0.1", int(time.time()), "back online")
        assert result is None

    def test_suppressed_during_maintenance_window(self):
        eng = AlertEngine(store=None, rules=[])
        eng.set_maintenance_checker(lambda host: "Weekend Window")
        rule = self._rule()
        result = eng._fire_resolution(rule, "10.0.0.1", int(time.time()), "back online")
        assert result is None

    def test_suppressed_when_out_of_device_scope(self):
        eng = AlertEngine(store=None, rules=[])
        eng.set_alert_scope_checker(lambda host: False)
        rule = self._rule()
        result = eng._fire_resolution(rule, "10.0.0.1", int(time.time()), "back online")
        assert result is None

    def test_not_gated_by_the_rules_cooldown(self):
        """A resolution must fire even immediately after the alert it closes
        -- unlike _fire_if_cooled, _fire_resolution must not consult
        self._last_fired at all."""
        eng = AlertEngine(store=None, rules=[])
        rule = self._rule(cooldown_s=999999)
        now = int(time.time())
        eng._last_fired[f"{rule.name}::10.0.0.1"] = now  # simulate "just fired"
        result = eng._fire_resolution(rule, "10.0.0.1", now, "back online")
        assert result is not None

    def test_carries_downtime_and_cta_through_verbatim(self):
        eng = AlertEngine(store=None, rules=[])
        rule = self._rule()
        result = eng._fire_resolution(
            rule, "10.0.0.1", int(time.time()), "back online",
            downtime_s=120, cta_page="Inventory", cta_filter="10.0.0.1",
        )
        assert result.downtime_s == 120
        assert result.cta_page == "Inventory"
        assert result.cta_filter == "10.0.0.1"


class TestResolutionSitesRespectMaintenanceWindow:
    """End-to-end guard: the 7 resolution call sites previously constructed
    AlertFired directly, with zero gating -- a resolution for a host under
    maintenance reached the router regardless. Covers the HOST_DOWN site in
    alert_engine.py (outside the rule loop -- the trickiest of the 7) plus
    the SERVICE_DOWN site in alert_engine_checks.py."""

    def test_host_down_resolution_respects_maintenance_window(self):
        eng = AlertEngine(store=None, rules=None)
        for rule in eng.get_rules():
            rule.enabled = rule.rule_type == "HOST_DOWN"
        eng.set_warmup_period(0)

        down_result = eng.evaluate_cycle({"ts": 1000, "states": {"10.0.0.1": "DOWN"}, "rtts": {}})
        assert any(a.rule_type == "HOST_DOWN" and not a.is_resolution for a in down_result)

        eng.set_maintenance_checker(lambda host: "Weekend Window")
        up_result = eng.evaluate_cycle({"ts": 2000, "states": {"10.0.0.1": "UP"}, "rtts": {}})
        assert not any(a.is_resolution for a in up_result)

    def test_host_down_resolution_fires_normally_without_maintenance(self):
        eng = AlertEngine(store=None, rules=None)
        for rule in eng.get_rules():
            rule.enabled = rule.rule_type == "HOST_DOWN"
        eng.set_warmup_period(0)

        eng.evaluate_cycle({"ts": 1000, "states": {"10.0.0.1": "DOWN"}, "rtts": {}})
        up_result = eng.evaluate_cycle({"ts": 2000, "states": {"10.0.0.1": "UP"}, "rtts": {}})
        resolutions = [a for a in up_result if a.is_resolution]
        assert len(resolutions) == 1
        assert resolutions[0].host == "10.0.0.1"
        assert resolutions[0].rule_name == "Host Down"

    def test_host_down_resolution_skipped_when_rule_disabled_mid_downtime(self):
        """The HOST_DOWN resolution site is outside the rule loop -- it must
        look the rule up and skip cleanly if disabled while the host was
        down, rather than firing with a synthetic rule name."""
        eng = AlertEngine(store=None, rules=None)
        for rule in eng.get_rules():
            rule.enabled = rule.rule_type == "HOST_DOWN"
        eng.set_warmup_period(0)

        eng.evaluate_cycle({"ts": 1000, "states": {"10.0.0.1": "DOWN"}, "rtts": {}})
        for rule in eng.get_rules():
            if rule.rule_type == "HOST_DOWN":
                rule.enabled = False
        up_result = eng.evaluate_cycle({"ts": 2000, "states": {"10.0.0.1": "UP"}, "rtts": {}})
        assert not any(a.is_resolution for a in up_result)

    def test_service_down_resolution_respects_maintenance_window(self):
        eng = AlertEngine(store=None, rules=[
            AlertRule(name="Service Down", rule_type="SERVICE_DOWN", cooldown_s=0, enabled=True)
        ])
        down = [{"host": "192.168.1.1", "port": 80, "up": False, "label": "HTTP"}]
        up = [{"host": "192.168.1.1", "port": 80, "up": True, "label": "HTTP"}]
        eng.evaluate_service_checks(down)
        eng.set_maintenance_checker(lambda host: "Weekend Window")
        fired = eng.evaluate_service_checks(up)
        assert not any(a.is_resolution for a in fired)
