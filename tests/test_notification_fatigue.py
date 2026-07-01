"""
Notification-fatigue composition test (Sprint 5).

Verifies a guarantee, not new plumbing: once a rule_name is snoozed via
NotificationRouter.set_snooze(), BOTH of the following are suppressed —

  1. The "plain" path: AlertEngine fires a SERVICE_DOWN alert -> its injected
     on_alert callback (NotificationRouter.dispatch) is called -> zero channel
     dispatches occur because dispatch() checks _is_snoozed() before touching
     any channel.
  2. The escalation follow-up path: app.py's _on_result (Sprint 1) builds a
     synthetic AlertFired reusing the SAME rule_name and calls
     notif_router.dispatch(...) directly (bypassing AlertEngine entirely).
     Because both paths funnel through the same dispatch() method and the same
     snooze registry keyed by rule_name, this must be gated identically.

This test constructs a real AlertEngine + real NotificationRouter with a fake
channel (counts deliveries) — no mocks needed since the router already
supports late-binding a toast callback and channel list.
"""
from __future__ import annotations

import time

from modules.alert_engine import AlertEngine, AlertFired, AlertRule
from modules.notification_router import NotificationRouter, ToastChannel


def _make_router_with_counting_toast():
    router = NotificationRouter()
    deliveries = []
    router.set_toast_callback(lambda alert: deliveries.append(alert))
    router.set_channels([ToastChannel(enabled=True, min_severity="INFO")])
    return router, deliveries


class TestNotificationFatigueSnoozeComposition:
    def test_plain_service_down_path_gated_by_snooze(self):
        """AlertEngine.evaluate_service_checks-style flow: engine fires ->
        on_alert (router.dispatch) is invoked -> snoozed rule delivers nothing."""
        router, deliveries = _make_router_with_counting_toast()
        engine = AlertEngine(store=None)
        engine.set_rules([
            AlertRule(name="svc-down-8080", rule_type="SERVICE_DOWN", cooldown_s=0)
        ])
        engine.set_on_alert(router.dispatch)

        # Snooze the rule before the service ever fires
        router.set_snooze("svc-down-8080", until_ts=time.time() + 3600)

        # Directly exercise the same dispatch() call AlertEngine.on_alert would
        # make (evaluate_service_checks constructs an AlertFired the same way;
        # what matters here is that dispatch() is the single choke point).
        alert = AlertFired(
            rule_name="svc-down-8080",
            rule_type="SERVICE_DOWN",
            host="192.168.1.10:8080",
            message="Service unreachable",
            severity="CRITICAL",
            ts=int(time.time()),
        )
        engine._on_alert = router.dispatch  # mirror set_on_alert wiring
        engine._on_alert(alert)

        assert deliveries == [], (
            "Snoozed rule_name still produced a toast delivery on the plain path"
        )

    def test_escalation_followup_path_gated_by_same_snooze_key(self):
        """app.py's escalation follow-up (Sprint 1) calls notif_router.dispatch()
        directly with a synthetic AlertFired reusing the original rule_name —
        prove it is equally suppressed by the same snooze entry."""
        router, deliveries = _make_router_with_counting_toast()
        router.set_snooze("svc-down-8080", until_ts=time.time() + 3600)

        escalation = AlertFired(
            rule_name="svc-down-8080",   # same rule_name as the plain alert
            rule_type="SERVICE_DOWN",
            host="192.168.1.10:8080",
            message="Root cause: DNS resolution failing upstream",
            severity="CRITICAL",
            ts=int(time.time()),
            cta_page="Service Diagnostics",
            cta_filter="192.168.1.10",
        )
        router.dispatch(escalation)

        assert deliveries == [], (
            "Snoozed rule_name still produced a toast delivery on the escalation "
            "follow-up path — snooze gating is not composed correctly"
        )

    def test_unsnoozed_rule_still_delivers_on_both_paths(self):
        """Sanity check: without a snooze, both paths DO deliver — proves the
        suppression above is caused by snooze, not some unrelated silent bug."""
        router, deliveries = _make_router_with_counting_toast()

        plain = AlertFired(
            rule_name="svc-down-9090", rule_type="SERVICE_DOWN",
            host="10.0.0.5:9090", message="down", severity="CRITICAL",
            ts=int(time.time()),
        )
        router.dispatch(plain)

        escalation = AlertFired(
            rule_name="svc-down-9090", rule_type="SERVICE_DOWN",
            host="10.0.0.5:9090", message="root cause found", severity="CRITICAL",
            ts=int(time.time()),
        )
        router.dispatch(escalation)

        assert len(deliveries) == 2

    def test_maintenance_window_also_suppresses_plain_path_independent_of_snooze(self):
        """Composition sanity: a maintenance window suppresses at the AlertEngine
        layer (before dispatch is even called), independent of the notification
        snooze mechanism -- the two suppression layers must not interfere."""
        router, deliveries = _make_router_with_counting_toast()
        engine = AlertEngine(store=None)
        engine.set_rules([
            AlertRule(name="rtt-high", rule_type="RTT_THRESHOLD",
                      threshold_ms=50.0, cooldown_s=0)
        ])
        engine.set_on_alert(router.dispatch)
        engine.set_maintenance_checker(lambda host: "Nightly Quiet Hours")

        fired = engine.evaluate_cycle({
            "ts": int(time.time()),
            "states": {"10.0.0.1": "UP"},
            "rtts": {"10.0.0.1": 150.0},
            "loss": {},
        })

        assert fired == []
        assert deliveries == []
