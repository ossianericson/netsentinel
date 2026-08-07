"""
alert_engine_cycle.py — _AlertCycleMixin: availability-cycle rule evaluation.

Extracted from alert_engine.py (RULE-AH1: 780-line budget, that file was at
762) so the Signal Quality Phase 4 signals have somewhere to land. Pure move:
every method below is byte-for-byte the one that lived in alert_engine.py at
55db5f2, and AlertEngine inherits this mixin so every existing call site —
including `AlertEngine._count_transitions(...)` and `eng._eval_rule_for_host(...)`
in the test suite — resolves unchanged.

The seam is the *cycle*: everything here is driven by one
AvailabilityMonitor.run_cycle() result and nothing else calls into it.
`_eval_rule_for_host()` and `_count_transitions()` have no callers outside this
set, and the two Phase 3 setters travel with the machinery they configure —
the `_MaintenanceSuppressionMixin` precedent, where the setter lives beside its
predicate while `__init__` keeps the field initialisation.

Provides:
  evaluate_cycle()                — the whole per-cycle pass: state history,
                                    flap rebuild, edge-gate feed, per-rule
                                    evaluation, HOST_DOWN consolidation, and
                                    resolution of recovered hosts
  set_availability_edge_trigger() — Phase 3 edge-triggered HOST_DOWN
  set_duplicate_outage_suppression() — Phase 3 one-outage-one-name

Stays in alert_engine.py: _fire_if_cooled / _fire_resolution / _append_action
(shared by every evaluate_* family, not just this one), the acknowledgement
holds, and evaluate_tracker_result().

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 1).
"""
from __future__ import annotations

import json
import time
from typing import Dict, List, Optional

from modules.alert_types import AlertFired, AlertRule
from modules.evidence import EvidenceGate
from modules.alert_engine_routing import RULE_CTA


class _AlertCycleMixin:
    """Mixin for AlertEngine providing availability-cycle rule evaluation."""

    # ── Signal Quality Phase 3 ────────────────────────────────────────────────

    def set_availability_edge_trigger(self, min_consecutive: Optional[int]) -> None:
        """Fire HOST_DOWN once per outage episode instead of once per cycle.

        `min_consecutive` = how many consecutive DOWN observations confirm an
        episode; the alert fires on that observation and then stays silent until
        the host recovers. `None` restores the legacy level-triggered path,
        which re-fires every `cooldown_s` for as long as the host stays down —
        measured at 1,637 firings against 164 resolutions on the reference
        network, ~240 alerts for one overnight outage.

        Note this does **not** change what is recorded; `device_state` still
        gets a row per cycle. It changes only how often the app *claims*.
        """
        self._availability_gate = (
            None if min_consecutive is None
            else EvidenceGate(min_consecutive=int(min_consecutive))
        )

    def set_duplicate_outage_suppression(self, enabled: bool) -> None:
        """Stop reporting one unreachable host under two rule names.

        `HOST_DOWN` (state == "DOWN") and `LOSS_THRESHOLD` (rtt < 0) fire from
        the same cycle for the same fact — 1,637 + 806 firings describing one
        condition on the reference network. When enabled, LOSS_THRESHOLD yields
        to HOST_DOWN, but only where an enabled HOST_DOWN rule actually covers
        that host: a user running LOSS_THRESHOLD alone must lose nothing.
        """
        self._suppress_duplicate_outage = bool(enabled)

    # ── The cycle pass ────────────────────────────────────────────────────────

    def evaluate_cycle(self, cycle_result: dict) -> List[AlertFired]:
        """
        Evaluate rules against a CycleResult-style dict:
          {"ts": int, "states": {host: state}, "rtts": {host: rtt_ms}}

        Returns fired alerts (also calls on_alert for each).
        """
        fired: List[AlertFired] = []
        states: Dict[str, str]   = cycle_result.get("states", {})
        rtts:   Dict[str, float] = cycle_result.get("rtts",   {})
        now = cycle_result.get("ts") or int(time.time())

        # Record state history and rebuild flapping set before evaluating rules
        self._update_state_history(states, now)
        self._rebuild_flapping_hosts(now)

        # ── Phase 3: feed the edge gate from the OBSERVATION, before any rule
        # runs. Driving it from whether an alert was emitted instead would let
        # a downstream suppression (scope, maintenance, cooldown, ack hold)
        # re-arm the edge, so re-opening scope mid-outage would manufacture a
        # fresh "has gone offline" claim for an outage that started hours ago.
        if self._availability_gate is not None:
            for _host, _state in states.items():
                self._availability_gate.observe(_host, _state == "DOWN", now)

        # ── S4-1: resolution — hosts that were down but are now UP ───────────
        down_alerts: List[AlertFired] = []

        for rule in self._rules:
            if not rule.enabled:
                continue
            hosts_to_check = (
                [rule.host] if rule.host and rule.host in states
                else list(states.keys()) if rule.host is None
                else []
            )
            for host in hosts_to_check:
                alert = self._eval_rule_for_host(rule, host, states, rtts, now)
                if alert:
                    if alert.rule_type == "HOST_DOWN":
                        down_alerts.append(alert)
                        # Track when this host went down for downtime calc
                        self._host_down_since.setdefault(host, now)
                    else:
                        fired.append(alert)
                        if self._on_alert:
                            self._on_alert(alert)

        # ── S4-3: consolidation — group simultaneous HOST_DOWN alerts ─────────
        if len(down_alerts) >= self._consolidation_threshold:
            hosts_str = ", ".join(a.host for a in down_alerts[:8])
            extra = len(down_alerts) - 8
            suffix = f" (+{extra} more)" if extra > 0 else ""
            consolidated = AlertFired(
                rule_name=down_alerts[0].rule_name,
                rule_type="HOST_DOWN",
                host="(network)",
                message=(
                    f"{len(down_alerts)} devices lost connectivity simultaneously — "
                    f"your internet connection may be down.  "
                    f"Affected: {hosts_str}{suffix}.  "
                    f"→ Check your router and modem  → Check your ISP status page"
                ),
                severity="CRITICAL",
                ts=now,
                cta_page="DNS & Stability",
                cta_filter=None,
            )
            fired.append(consolidated)
            if self._on_alert:
                self._on_alert(consolidated)
        else:
            for alert in down_alerts:
                fired.append(alert)
                if self._on_alert:
                    self._on_alert(alert)

        # ── S4-1: resolution — check hosts that recovered ─────────────────────
        recovered = [
            h for h in list(self._host_down_since)
            if states.get(h) == "UP"
        ]
        for host in recovered:
            down_ts = self._host_down_since.pop(host)
            # This site sits outside the rule loop above, so the rule must be
            # looked up explicitly — it may have been disabled while the host
            # was down, in which case there is no rule left to attribute the
            # resolution to.
            rule = next(
                (r for r in self._rules if r.rule_type == "HOST_DOWN" and r.enabled), None
            )
            if rule is None:
                continue
            downtime = now - down_ts
            mins, secs = divmod(downtime, 60)
            if mins >= 60:
                duration = f"{mins // 60}h {mins % 60}m"
            elif mins > 0:
                duration = f"{mins}m {secs}s"
            else:
                duration = f"{secs}s"
            resolution = self._fire_resolution(
                rule, host, now,
                message=f"{host} is back online — was unreachable for {duration}.",
                downtime_s=downtime,
                cta_page=RULE_CTA["HOST_DOWN"],
                cta_filter=host,
            )
            if resolution:
                fired.append(resolution)
                if self._on_alert:
                    self._on_alert(resolution)

        # Track hosts newly going down (not consolidated)
        for alert in down_alerts:
            if len(down_alerts) < self._consolidation_threshold:
                self._host_down_since.setdefault(alert.host, now)

        return fired

    # ── Per-rule evaluation ───────────────────────────────────────────────────

    def _eval_rule_for_host(
        self,
        rule: AlertRule,
        host: str,
        states: Dict[str, str],
        rtts:   Dict[str, float],
        now: int,
    ) -> Optional[AlertFired]:
        rt = rule.rule_type
        rtt = rtts.get(host, -1.0)
        state = states.get(host, "")

        if rt == "RTT_THRESHOLD":
            if rtt >= 0 and rtt > rule.threshold_ms:
                return self._fire_if_cooled(
                    rule, host, now,
                    message=self._append_action(
                        f"{host} is responding slowly ({rtt:.0f} ms, normally under "
                        f"{rule.threshold_ms:.0f} ms) — this may affect video calls "
                        f"and real-time applications.",
                        rt,
                    ),
                    severity="WARNING",
                    value=rtt,
                )
        elif rt == "LOSS_THRESHOLD":
            # Loss is expressed as loss_pct in metric_store but only rtt=-1
            # signals a dropped packet at cycle level; detailed loss comes from
            # store history. For cycle-level we treat rtt < 0 as 100% loss.
            if rtt < 0:
                # Phase 3: one outage, one name. `state == "DOWN"` and
                # `rtt < 0` are the same observation at cycle level, so when
                # HOST_DOWN is already speaking about this host, saying it
                # again under a second rule name is duplication, not coverage.
                if (
                    self._suppress_duplicate_outage
                    and state == "DOWN"
                    and self._host_down_rule_covers(host)
                ):
                    return None
                return self._fire_if_cooled(
                    rule, host, now,
                    message=self._append_action(
                        f"{host} is not responding — packets are being lost. "
                        f"Check cables and power to this device.",
                        rt,
                    ),
                    severity="CRITICAL",
                    value=100.0,
                )
        elif rt == "HOST_DOWN":
            if state == "DOWN" and host not in self._flapping_hosts:
                if not self._is_dependency_suppressed(host, states):
                    admits, evidence = self._availability_evidence(host)
                    if not admits:
                        return None
                    alert = self._fire_if_cooled(
                        rule, host, now,
                        message=self._append_action(
                            f"{host} has gone offline and is not responding to pings.",
                            rt,
                        ),
                        severity="CRITICAL",
                        value=None,
                    )
                    # Schema v22: carry the corroboration through to
                    # alert_fired, so history records WHY the claim was made and
                    # relevance.py can rank it. None when no gate is installed
                    # (the legacy level-triggered path), which relevance treats
                    # as neutral rather than as low confidence.
                    if alert is not None and evidence is not None:
                        alert.confidence = evidence.confidence
                        alert.evidence_json = json.dumps({
                            "observations": evidence.observations,
                            "consecutive":  evidence.consecutive,
                            "window_s":     evidence.window_s,
                            "basis":        evidence.basis,
                        })
                    return alert
        elif rt == "HOST_DEGRADED":
            if state == "DEGRADED":
                return self._fire_if_cooled(
                    rule, host, now,
                    message=self._append_action(
                        f"{host} is responding slowly ({rtt:.0f} ms) — "
                        f"network performance may be degraded.",
                        rt,
                    ),
                    severity="WARNING",
                    value=rtt,
                )
        elif rt == "FLAP":
            history = self._state_history.get(host, [])
            transitions = self._count_transitions(history, rule.flap_window_s, now)
            if transitions >= rule.flap_count:
                mins = rule.flap_window_s // 60
                return self._fire_if_cooled(
                    rule, host, now,
                    message=self._append_action(
                        f"{host} keeps going online and offline "
                        f"({transitions} time{'s' if transitions != 1 else ''} "
                        f"in {mins} minute{'s' if mins != 1 else ''}) — "
                        f"check the connection or cable.",
                        rt,
                    ),
                    severity="WARNING",
                    value=float(transitions),
                )
        return None

    def _availability_evidence(self, host: str):
        """Phase 3 edge check, returning `(admits, Evidence | None)`.

        Evidence is None whenever no gate is installed — the legacy
        level-triggered path is bit-for-bit unchanged and has nothing to say
        about corroboration, which is different from saying it is unconvincing.
        """
        gate = self._availability_gate
        if gate is None:
            return True, None
        return gate.admit(host)

    def _availability_admits(self, host: str) -> bool:
        """Boolean form of _availability_evidence(), kept for existing callers."""
        gate = self._availability_gate
        if gate is None:
            return True
        return gate.admit(host)[0]

    def _host_down_rule_covers(self, host: str) -> bool:
        """True when an enabled HOST_DOWN rule would evaluate `host`.

        Mirrors the `hosts_to_check` selection in evaluate_cycle(): a rule with
        `host=None` covers every host, one with an explicit host covers only it.
        """
        return any(
            r.enabled
            and r.rule_type == "HOST_DOWN"
            and (r.host is None or r.host == host)
            for r in self._rules
        )

    # ── State history / flap detection / dependency suppression ───────────────

    def _update_state_history(self, states: Dict[str, str], now: int) -> None:
        """Append current states to per-host history and trim to 24h."""
        cutoff = now - 86400
        for host, state in states.items():
            if host not in self._state_history:
                self._state_history[host] = []
            self._state_history[host].append((now, state))
        # Trim old entries across all hosts
        for host in list(self._state_history):
            self._state_history[host] = [
                (ts, s) for ts, s in self._state_history[host] if ts >= cutoff
            ]
            if not self._state_history[host]:
                del self._state_history[host]

    def _rebuild_flapping_hosts(self, now: int) -> None:
        """Recompute the set of hosts currently considered to be flapping."""
        flapping: set = set()
        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "FLAP":
                continue
            hosts = (
                list(self._state_history.keys())
                if rule.host is None
                else [rule.host]
            )
            for host in hosts:
                history = self._state_history.get(host, [])
                transitions = self._count_transitions(history, rule.flap_window_s, now)
                if transitions >= rule.flap_count:
                    flapping.add(host)
        self._flapping_hosts = flapping

    def _is_dependency_suppressed(self, host: str, states: Dict[str, str]) -> bool:
        """
        Return True if *host* is a registered child of a parent that is
        currently in the DOWN state, meaning the alert should be suppressed.
        """
        for parent_ip, children in self._dependency_map.items():
            if host in children and states.get(parent_ip) == "DOWN":
                return True
        return False

    @staticmethod
    def _count_transitions(history: list, window_s: int, now: int) -> int:
        """Count state changes within the last window_s seconds."""
        cutoff = now - window_s
        windowed = [(ts, s) for ts, s in history if ts >= cutoff]
        if len(windowed) < 2:
            return 0
        return sum(
            1 for i in range(1, len(windowed))
            if windowed[i][1] != windowed[i - 1][1]
        )
