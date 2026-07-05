"""
alert_engine_checks2.py — _AlertChecksMixin2: RTT_ANOMALY / IOT_BEHAVIOR /
TREND_FORECAST rule evaluation (V6 Sprint 2 — "wire the dormant baseline
engines").

New file rather than growing alert_engine_checks.py further — keeps both
files under the RULE-AH1 600-line budget (see tests/test_module_loc.py).

Provides:
  evaluate_rtt_anomaly_checks() — RTT_ANOMALY: per-host mean+2sigma baseline
                                   from modules.alert_baseline.BaselineLearner
  evaluate_iot_behavior_checks() — IOT_BEHAVIOR: wraps modules.iot_baseline
                                    IoTAlert objects as AlertFired
  evaluate_trend_checks()        — TREND_FORECAST: early-warning ETA-to-
                                    threshold forecasts from modules.trend_analyser
"""
from __future__ import annotations

import time
from typing import Dict, List

from modules.alert_types import AlertFired

# IOT_BEHAVIOR — modules.iot_baseline.IoTAlert.severity -> AlertFired.severity
_IOT_SEVERITY_MAP = {
    "CRITICAL": "CRITICAL",
    "HIGH":     "CRITICAL",
    "MEDIUM":   "WARNING",
}


class _AlertChecksMixin2:
    """Mixin for AlertEngine providing RTT_ANOMALY/IOT_BEHAVIOR/TREND_FORECAST checks."""

    def evaluate_rtt_anomaly_checks(
        self, host_rtts: Dict[str, float], learner,
    ) -> List[AlertFired]:
        """RTT_ANOMALY — a host's current RTT exceeds its own learned
        mean+sigma*stddev baseline (modules.alert_baseline.BaselineLearner).

        Gated on Baseline.is_mature (>=30 samples over >=7 days, per
        BaselineMetric.is_valid/days_covered) so the learning period does not
        produce false positives.  `learner` must expose get_host_baseline(host).
        """
        fired: List[AlertFired] = []
        now = int(time.time())
        since = self._rtt_anomaly_since

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "RTT_ANOMALY":
                continue
            for host, rtt in host_rtts.items():
                if rule.host and rule.host != host:
                    continue
                baseline = learner.get_host_baseline(host) if learner else None
                metric = baseline.rtt_ms if baseline else None
                if metric is None or not metric.is_valid or metric.days_covered < 7:
                    continue

                threshold = metric.anomaly_threshold(rule.sigma)
                if rtt > threshold:
                    alert = self._fire_if_cooled(
                        rule, host, now,
                        message=self._append_action(
                            f"{host} is responding slower than its usual pattern "
                            f"({rtt:.0f} ms vs a typical {metric.mean:.0f} ms) — "
                            f"this device may be having a problem specific to it.",
                            "RTT_THRESHOLD",
                        ),
                        severity="WARNING",
                        value=rtt,
                    )
                    if alert:
                        since.setdefault(host, now)
                        fired.append(alert)
                        if self._on_alert:
                            self._on_alert(alert)
                elif host in since:
                    since.pop(host)
                    resolution = AlertFired(
                        rule_name=rule.name,
                        rule_type="RTT_ANOMALY",
                        host=host,
                        message=f"{host}'s response time is back to its usual pattern.",
                        severity="HEALTHY",
                        ts=now,
                        is_resolution=True,
                        cta_page="DNS & Stability",
                        cta_filter=host,
                    )
                    fired.append(resolution)
                    if self._on_alert:
                        self._on_alert(resolution)

        return fired

    def evaluate_iot_behavior_checks(self, iot_alerts: list) -> List[AlertFired]:
        """IOT_BEHAVIOR — wraps modules.iot_baseline.IoTMonitor alerts
        (NEW_DEST / NEW_PORT / METADATA_PROBE / SYN_SCAN / RATE_SPIKE) as
        real AlertEngine alerts instead of page-only findings.

        No resolution alert — these are point-in-time behavioural signals
        (same pattern as NEW_DEVICE / DEVICE_GONE), not an up/down state.
        """
        fired: List[AlertFired] = []
        now = int(time.time())

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "IOT_BEHAVIOR":
                continue
            for signal in iot_alerts:
                host = getattr(signal, "ip", None) or getattr(signal, "mac", "")
                if rule.host and rule.host not in (host, getattr(signal, "mac", "")):
                    continue
                severity = _IOT_SEVERITY_MAP.get(getattr(signal, "severity", ""), "WARNING")
                label = getattr(signal, "device_label", host)
                kind = getattr(signal, "alert_type", "").replace("_", " ").title()
                detail = getattr(signal, "detail", "")

                alert = self._fire_if_cooled(
                    rule, f"{host}::{getattr(signal, 'alert_type', '')}", now,
                    message=self._append_action(
                        f"{label}: {kind} — {detail}",
                        "IOT_BEHAVIOR",
                    ),
                    severity=severity,
                    value=None,
                    scope_host=host,
                )
                if alert:
                    alert.host = host
                    alert.cta_filter = host
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

        return fired

    def evaluate_trend_checks(self, trend_report) -> List[AlertFired]:
        """TREND_FORECAST — fires an early-warning alert when a metric is
        projected (via modules.trend_analyser OLS regression) to cross its
        threshold soon, instead of waiting for a user to open Trend Forecasts.

        Only fires for results that have NOT already crossed the threshold
        (current_value < threshold) with a projected eta_hours — an
        already-crossed value is RTT_THRESHOLD/LOSS_THRESHOLD's job, and
        firing both would be a duplicate alert for the same condition.
        """
        fired: List[AlertFired] = []
        now = int(time.time())

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "TREND_FORECAST":
                continue
            for result in getattr(trend_report, "results", []):
                if result.severity not in ("CRITICAL", "WARNING"):
                    continue
                if result.eta_hours is None or result.current_value >= result.threshold:
                    continue
                if rule.host and rule.host != result.host:
                    continue

                key = f"{result.host}::{result.metric}"
                alert = self._fire_if_cooled(
                    rule, key, now,
                    message=self._append_action(result.summary, "TREND_FORECAST"),
                    severity=result.severity,
                    value=result.current_value,
                    scope_host=result.host,
                )
                if alert:
                    alert.host = result.host
                    alert.cta_filter = result.host
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

        return fired
