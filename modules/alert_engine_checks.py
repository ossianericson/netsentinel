"""
alert_engine_checks.py — _AlertChecksMixin: cert, service, and baseline check
evaluation.

Extracted from alert_engine.py (Sprint 2 file-budget split) to keep that file
within its 800-line budget.  AlertEngine inherits this mixin.

Provides:
  evaluate_cert_checks()      — CERT_EXPIRY / CERT_EXPIRED rule evaluation
  evaluate_service_checks()   — SERVICE_DOWN rule evaluation
  evaluate_baseline_metrics() — BASELINE_DROP rule evaluation (Sprint 3)
  evaluate_jitter_checks()    — JITTER_HIGH rule evaluation (V6 Sprint 1)
  evaluate_mesh_checks()      — MESH_DEGRADED rule evaluation (V6 Sprint 1)
  evaluate_modem_checks()     — MODEM_SIGNAL_DROP rule evaluation (V6 Sprint 1)
  evaluate_grade_check()      — GRADE_REGRESSION rule evaluation (V6 Sprint 1)
  evaluate_ip_churn_checks()  — IP_CHURN rule evaluation (V6 Sprint 1)
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from modules.alert_types import AlertFired

# GRADE_REGRESSION — worse rank = lower number
_GRADE_RANK = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}

# MESH_DEGRADED — dBm below this is considered a weak signal
_MESH_WEAK_RSSI = -75.0

# SERVICE_DOWN — consecutive failed checks required before the first CRITICAL
# alert fires. Without this, a target that was never reachable (e.g. added by
# mistake, or an automated fuzz/monkey-test click landing in the add-service
# field) fires CRITICAL on its very first check and re-fires every cooldown
# forever — indistinguishable from a real outage and a source of alert
# fatigue that erodes trust in the app.
_SERVICE_DOWN_MIN_CONSECUTIVE_FAILS = 3


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
                    self._service_fail_streak.pop(key, None)
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

                # Track downtime start on the first observed failure (used for
                # the resolution message's duration), independent of whether
                # the grace period below has elapsed yet.
                self._service_down_since.setdefault(key, now)
                streak = self._service_fail_streak.get(key, 0) + 1
                self._service_fail_streak[key] = streak
                if streak < _SERVICE_DOWN_MIN_CONSECUTIVE_FAILS:
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
        self,
        current_mbps: float,
        prior_downloads: List[float],
        current_sinr: Optional[float] = None,
        prior_sinr: Optional[List[float]] = None,
    ) -> List[AlertFired]:
        """
        Evaluate BASELINE_DROP rules — delegates the actual math/copy to
        speed_drop_detector.evaluate_speed_drop() (reuse, not reimplement;
        this is the same detector the manual Speed Test page uses).

        V6 Sprint 5.2 — when the modem's SINR has also dropped below its own
        learned baseline (reuses modules.alert_baseline.modem_sinr_dropped,
        the same detector MODEM_SIGNAL_DROP uses), the message is reframed as
        a radio-link problem rather than an ISP problem, since blaming the
        ISP for a drop actually caused by weak cellular signal sends the user
        down the wrong troubleshooting path.
        """
        from modules.speed_drop_detector import evaluate_speed_drop
        from modules.alert_baseline import modem_sinr_dropped

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
            headline = verdict.headline
            if modem_sinr_dropped(current_sinr, prior_sinr or [], min_samples=rule.min_samples):
                headline = (
                    "Likely your radio signal, not your ISP: " + headline +
                    " Your modem's signal quality (SINR) has also dropped below its usual level."
                )
            alert = self._fire_if_cooled(
                rule, "speedtest", now,
                message=self._append_action(headline, "BASELINE_DROP"),
                severity=severity,
                value=verdict.drop_pct,
            )
            if alert:
                fired.append(alert)
                if self._on_alert:
                    self._on_alert(alert)

        return fired

    # ── V6 Sprint 1 — alert on data already collected ─────────────────────────

    def evaluate_jitter_checks(self, jitter_by_host: Dict[str, List[float]]) -> List[AlertFired]:
        """JITTER_HIGH — average jitter over the last ~10 min exceeds
        rule.threshold_ms.  Needs >= 3 samples to avoid firing on one spike."""
        fired: List[AlertFired] = []
        now = int(time.time())
        since = self._jitter_high_since

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "JITTER_HIGH":
                continue
            for host, samples in jitter_by_host.items():
                if rule.host and rule.host != host:
                    continue
                if len(samples) < 3:
                    continue
                avg_jitter = sum(samples) / len(samples)
                if avg_jitter > rule.threshold_ms:
                    alert = self._fire_if_cooled(
                        rule, host, now,
                        message=self._append_action(
                            f"{host} has unstable jitter ({avg_jitter:.0f} ms average, normally under "
                            f"{rule.threshold_ms:.0f} ms) — this can cause choppy calls and stutter.",
                            "JITTER_HIGH",
                        ),
                        severity="WARNING",
                        value=avg_jitter,
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
                        rule_type="JITTER_HIGH",
                        host=host,
                        message=f"{host}'s jitter is back to normal ({avg_jitter:.0f} ms).",
                        severity="HEALTHY",
                        ts=now,
                        is_resolution=True,
                        cta_page="Network Logger",
                        cta_filter=host,
                    )
                    fired.append(resolution)
                    if self._on_alert:
                        self._on_alert(resolution)

        return fired

    def evaluate_mesh_checks(
        self,
        unit_count: int,
        online_count: int,
        worst_unit: Optional[str] = None,
        worst_rssi: Optional[float] = None,
    ) -> List[AlertFired]:
        """MESH_DEGRADED — a mesh node dropped offline, or the weakest node's
        RSSI is below _MESH_WEAK_RSSI."""
        fired: List[AlertFired] = []
        now = int(time.time())
        key = "mesh"

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "MESH_DEGRADED":
                continue
            degraded = online_count < unit_count or (worst_rssi is not None and worst_rssi < _MESH_WEAK_RSSI)
            was_degraded = key in self._mesh_degraded_since

            if degraded:
                if online_count < unit_count:
                    detail = f"{unit_count - online_count} of {unit_count} mesh node(s) offline"
                else:
                    detail = f"weakest node ({worst_unit or 'unknown'}) has a poor signal ({worst_rssi:.0f} dBm)"
                alert = self._fire_if_cooled(
                    rule, key, now,
                    message=self._append_action(
                        f"Your mesh network is degraded — {detail}.",
                        "MESH_DEGRADED",
                    ),
                    severity="WARNING",
                    value=worst_rssi,
                )
                if alert:
                    self._mesh_degraded_since.setdefault(key, now)
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)
            elif was_degraded:
                self._mesh_degraded_since.pop(key, None)
                resolution = AlertFired(
                    rule_name=rule.name,
                    rule_type="MESH_DEGRADED",
                    host=key,
                    message="Your mesh network is back to full health.",
                    severity="HEALTHY",
                    ts=now,
                    is_resolution=True,
                    cta_page="Hardware",
                    cta_filter=None,
                )
                fired.append(resolution)
                if self._on_alert:
                    self._on_alert(resolution)

        return fired

    def evaluate_modem_checks(
        self,
        network_type: Optional[str],
        current_sinr: Optional[float],
        prior_sinr: List[float],
        prior_network_type: Optional[str],
    ) -> List[AlertFired]:
        """MODEM_SIGNAL_DROP — fires on a 5G->LTE band downgrade, or when
        current SINR drops more than 2 std-devs below the learned baseline
        (reuses modules.alert_baseline.modem_sinr_dropped)."""
        from modules.alert_baseline import modem_sinr_dropped

        fired: List[AlertFired] = []
        now = int(time.time())
        key = "modem"

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "MODEM_SIGNAL_DROP":
                continue

            downgraded = bool(
                prior_network_type and "5G" in prior_network_type
                and network_type and "5G" not in network_type
            )
            dropped = modem_sinr_dropped(current_sinr, prior_sinr, min_samples=rule.min_samples)
            degraded = downgraded or dropped

            if degraded:
                if downgraded:
                    message = (
                        f"Your modem downgraded from 5G to {network_type} — "
                        f"speeds and latency may suffer."
                    )
                else:
                    message = (
                        f"Your modem's signal quality dropped well below its usual level "
                        f"(SINR {current_sinr:.1f} dB) — check antenna placement or position."
                    )
                alert = self._fire_if_cooled(
                    rule, key, now,
                    message=self._append_action(message, "MODEM_SIGNAL_DROP"),
                    severity="WARNING",
                    value=current_sinr,
                )
                if alert:
                    self._modem_degraded_since.setdefault(key, now)
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)
            elif key in self._modem_degraded_since:
                self._modem_degraded_since.pop(key, None)
                resolution = AlertFired(
                    rule_name=rule.name,
                    rule_type="MODEM_SIGNAL_DROP",
                    host=key,
                    message="Your modem's signal is back to normal.",
                    severity="HEALTHY",
                    ts=now,
                    is_resolution=True,
                    cta_page="Hardware",
                    cta_filter=None,
                )
                fired.append(resolution)
                if self._on_alert:
                    self._on_alert(resolution)

        return fired

    def evaluate_grade_check(
        self,
        grade: str,
        score: float,
        verdict: str,
        prior_grade: Optional[str],
    ) -> List[AlertFired]:
        """GRADE_REGRESSION — the network health grade declined vs. the
        previous run (e.g. A -> C).  Severity scales with how many ranks it fell."""
        fired: List[AlertFired] = []
        now = int(time.time())
        key = "network-grade"

        if prior_grade is None:
            return fired

        new_rank = _GRADE_RANK.get(grade.upper())
        old_rank = _GRADE_RANK.get(prior_grade.upper())
        if new_rank is None or old_rank is None or new_rank >= old_rank:
            return fired

        drop = old_rank - new_rank

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "GRADE_REGRESSION":
                continue
            alert = self._fire_if_cooled(
                rule, key, now,
                message=self._append_action(
                    f"Your network health grade dropped from {prior_grade} to {grade} "
                    f"({verdict}).",
                    "GRADE_REGRESSION",
                ),
                severity="CRITICAL" if drop >= 2 else "WARNING",
                value=score,
            )
            if alert:
                fired.append(alert)
                if self._on_alert:
                    self._on_alert(alert)

        return fired

    def evaluate_ip_churn_checks(self, churn_counts: Dict[str, int]) -> List[AlertFired]:
        """IP_CHURN — a device has used 3+ distinct IPs within 24 h, usually
        because it has no DHCP reservation.  `churn_counts` is
        {mac: distinct_ip_count}, pre-filtered by the caller's query."""
        fired: List[AlertFired] = []
        now = int(time.time())
        since = self._ip_churn_since

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "IP_CHURN":
                continue

            for mac, count in churn_counts.items():
                if rule.host and rule.host != mac:
                    continue
                alert = self._fire_if_cooled(
                    rule, mac, now,
                    message=self._append_action(
                        f"Device {mac} has used {count} different IP addresses in the last "
                        f"24 hours — it may be missing a DHCP reservation.",
                        "IP_CHURN",
                    ),
                    severity="WARNING",
                    value=float(count),
                )
                if alert:
                    since.setdefault(mac, now)
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

            recovered = [mac for mac in list(since) if mac not in churn_counts]
            for mac in recovered:
                since.pop(mac)
                resolution = AlertFired(
                    rule_name=rule.name,
                    rule_type="IP_CHURN",
                    host=mac,
                    message=f"Device {mac}'s IP address is stable again.",
                    severity="HEALTHY",
                    ts=now,
                    is_resolution=True,
                    cta_page="Devices",
                    cta_filter=mac,
                )
                fired.append(resolution)
                if self._on_alert:
                    self._on_alert(resolution)

        return fired
