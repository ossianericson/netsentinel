"""
alert_engine_checks.py — _AlertChecksMixin: cert, service, and baseline check
evaluation.

Extracted from alert_engine.py (Sprint 2 file-budget split) to keep that file
within its 800-line budget.  AlertEngine inherits this mixin.

Provides:
  evaluate_cert_checks()      — CERT_EXPIRY / CERT_EXPIRED rule evaluation
  evaluate_service_checks()   — SERVICE_DOWN rule evaluation
  evaluate_baseline_metrics() — BASELINE_DROP rule evaluation (Sprint 3)
"""
from __future__ import annotations

import time
from typing import List

from modules.alert_types import AlertFired


class _AlertChecksMixin:
    """Mixin for AlertEngine providing cert, service, and baseline check evaluation methods."""

    def evaluate_service_checks(self, service_results) -> List:
        """
        Evaluate SERVICE_DOWN rules against a list of service check results.
        Accepts objects or dicts with: host, port, up, label, error.
        """
        fired: List[AlertFired] = []
        now = int(time.time())

        def _get(obj, attr):
            return obj.get(attr) if isinstance(obj, dict) else getattr(obj, attr, None)

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "SERVICE_DOWN":
                continue
            for result in service_results:
                host  = _get(result, "host") or ""
                port  = _get(result, "port") or 0
                up    = _get(result, "up")
                label = _get(result, "label") or f"{host}:{port}"
                key   = f"{host}:{port}"

                if rule.host and rule.host not in (host, key, label):
                    continue

                if up:
                    # ── S4-1: service came back — fire resolution if it was down ──
                    if key in self._service_down_since:
                        down_ts = self._service_down_since.pop(key)
                        downtime = now - down_ts
                        mins, secs = divmod(downtime, 60)
                        if mins >= 60:
                            duration = f"{mins // 60}h {mins % 60}m"
                        elif mins > 0:
                            duration = f"{mins}m {secs}s"
                        else:
                            duration = f"{secs}s"
                        resolution = AlertFired(
                            rule_name=rule.name,
                            rule_type="SERVICE_DOWN",
                            host=key,
                            message=(
                                f"{label} is back — was unreachable for {duration}."
                            ),
                            severity="HEALTHY",
                            ts=now,
                            is_resolution=True,
                            downtime_s=downtime,
                            cta_page="Service Heartbeat",
                            cta_filter=key,
                        )
                        fired.append(resolution)
                        if self._on_alert:
                            self._on_alert(resolution)
                    continue

                alert = self._fire_if_cooled(
                    rule, key, now,
                    message=(
                        f"{label} is not responding on {host} (port {port}) — "
                        f"the service may be offline or blocked by a firewall.  "
                        f"→ Restart the service  → Check firewall rules for port {port}"
                    ),
                    severity="CRITICAL",
                    value=None,
                )
                if alert:
                    self._service_down_since.setdefault(key, now)
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

        return fired

    def evaluate_cert_checks(self, cert_results) -> List:
        """
        Evaluate CERT_EXPIRY / CERT_EXPIRED rules against a list of cert
        check objects.  Accepts any objects (or dicts) with the attributes:
          host, port, days_remaining, is_expired, error.
        """
        fired: List[AlertFired] = []
        now = int(time.time())

        def _get(obj, attr):
            return obj.get(attr) if isinstance(obj, dict) else getattr(obj, attr, None)

        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.rule_type not in ("CERT_EXPIRY", "CERT_EXPIRED"):
                continue
            for result in cert_results:
                host        = _get(result, "host") or ""
                port        = _get(result, "port") or 443
                is_expired  = _get(result, "is_expired") or False
                days        = _get(result, "days_remaining")
                error       = _get(result, "error")
                target_key  = f"{host}:{port}"

                if rule.host and rule.host not in (host, target_key):
                    continue
                if error:   # unreachable — skip cert rule evaluation
                    continue

                if rule.rule_type == "CERT_EXPIRED" and is_expired:
                    alert = self._fire_if_cooled(
                        rule, target_key, now,
                        message=self._append_action(
                            f"Security certificate expired on {host}:{port} — "
                            f"connections may show security warnings. Renew it now.",
                            "CERT_EXPIRED",
                        ),
                        severity="CRITICAL",
                        value=float(days) if days is not None else None,
                    )
                    if alert:
                        fired.append(alert)
                        if self._on_alert:
                            self._on_alert(alert)

                elif rule.rule_type == "CERT_EXPIRY":
                    if days is not None and not is_expired and days < rule.threshold_days:
                        alert = self._fire_if_cooled(
                            rule, target_key, now,
                            message=self._append_action(
                                f"Security certificate on {host}:{port} expires in "
                                f"{days} day{'s' if days != 1 else ''} — "
                                f"renew before it expires to avoid connection warnings.",
                                "CERT_EXPIRY",
                            ),
                            severity="WARNING",
                            value=float(days),
                        )
                        if alert:
                            fired.append(alert)
                            if self._on_alert:
                                self._on_alert(alert)

        return fired

    def evaluate_baseline_metrics(
        self, current_mbps: float, prior_downloads: List[float]
    ) -> List[AlertFired]:
        """
        Evaluate BASELINE_DROP rules — delegates the actual math/copy to
        speed_drop_detector.evaluate_speed_drop() (reuse, not reimplement;
        this is the same detector the manual Speed Test page uses).
        """
        from modules.speed_drop_detector import evaluate_speed_drop

        fired: List[AlertFired] = []
        now = int(time.time())

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "BASELINE_DROP":
                continue
            verdict = evaluate_speed_drop(
                current_mbps,
                prior_downloads,
                min_samples=rule.min_samples,
                warn_pct=rule.warn_pct,
                high_pct=rule.high_pct,
            )
            if not verdict.is_drop:
                continue
            severity = "CRITICAL" if verdict.severity == "High" else "WARNING"
            alert = self._fire_if_cooled(
                rule, "speedtest", now,
                message=self._append_action(verdict.headline, "BASELINE_DROP"),
                severity=severity,
                value=verdict.drop_pct,
            )
            if alert:
                fired.append(alert)
                if self._on_alert:
                    self._on_alert(alert)

        return fired
