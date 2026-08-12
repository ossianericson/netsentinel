"""
AlertEngine — threshold-based alerting engine (T1#1).

Evaluates configurable rules against metrics produced by the monitoring
pipeline (availability cycles, device tracker results). When a rule fires it
produces an AlertFired object. Cooldown prevents duplicate alerts.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected as constructor parameter.
  • Alert delivery (toast/email/webhook) is the caller's responsibility.

Supported rule types — see RULE_TYPES in modules/alert_types.py for the
canonical list; V6 Sprint 1 added JITTER_HIGH/MESH_DEGRADED/
MODEM_SIGNAL_DROP/GRADE_REGRESSION/IP_CHURN, V6 Sprint 2 added
RTT_ANOMALY/IOT_BEHAVIOR/TREND_FORECAST (per-host baseline anomaly,
iot_baseline.py monitor alerts, and trend_analyser.py ETA forecasts).

Each rule has:
  name           str    — unique human label
  rule_type      str    — one of the above
  host           str    — IP/hostname to watch; None = all hosts
  threshold_ms   float  — for RTT_THRESHOLD
  threshold_pct  float  — for LOSS_THRESHOLD
  threshold_days int    — for CERT_EXPIRY
  flap_count     int    — for FLAP: minimum transitions in window to be "flapping"
  flap_window_s  int    — for FLAP: rolling time window (seconds)
  cooldown_s     int    — minimum seconds between repeated firings of the same rule
  enabled        bool

Flap suppression:
  When a host is detected as flapping, HOST_DOWN alerts for that host are
  suppressed during that cycle to avoid alert storms.

Parent/child dependency suppression (T3#12):
  When a parent device is DOWN, HOST_DOWN alerts for its registered children
  are suppressed so operators don't receive N child alerts for every upstream
  outage.  Register relationships via set_dependency_map().  Suppression lifts
  automatically when the parent recovers.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional

from modules.alert_types import (  # noqa: F401 — re-exported
    AlertFired, AlertRule, RULE_TYPES, DEFAULT_ACK_HOLD_SECONDS,
)
from modules.metric_store import MetricStore
from modules.alert_suppressor import (
    EscalationPolicy, _default_rules, rule_settings_key,
    _MaintenanceSuppressionMixin, _DeviceScopeMixin,
)
from modules.evidence import EvidenceGate
from modules.alert_engine_checks import _AlertChecksMixin
from modules.alert_engine_checks2 import _AlertChecksMixin2
from modules.alert_engine_checks3 import _AlertChecksMixin3
from modules.alert_engine_checks4 import _AlertChecksMixin4
from modules.alert_engine_checks5 import _AlertChecksMixin5
from modules.alert_engine_cycle import _AlertCycleMixin
from modules.alert_engine_routing import cta_for_rule, append_action

# Re-exported for backwards-compat callers (e.g. from modules.alert_engine import rule_settings_key)
__all__ = [
    "AlertRule", "AlertFired", "AlertEngine",
    "EscalationPolicy", "rule_settings_key", "RULE_TYPES",
    "DEFAULT_ACK_HOLD_SECONDS",
]


# ── CTA routing + action-step text — see modules/alert_engine_routing.py ─────
# (RULE-AH1 split: this was a self-contained lookup-table block with no
# evaluate_* logic, so it moved out cleanly when alert_engine.py hit the budget.)

_cta_for_rule = cta_for_rule


# ── Engine ────────────────────────────────────────────────────────────────────

class AlertEngine(_AlertChecksMixin, _AlertChecksMixin2, _AlertChecksMixin3, _AlertChecksMixin4, _AlertChecksMixin5, _AlertCycleMixin, _MaintenanceSuppressionMixin, _DeviceScopeMixin):
    """
    Stateless rule evaluator. Call the appropriate evaluate_* method after
    each monitoring cycle or scan result.

    Parameters
    ----------
    store : MetricStore
        Injected MetricStore singleton — used only to look up recent history
        when needed (e.g. consecutive-failure counts). May be None; alerts
        still fire but history-based suppression is skipped.
    rules : list[AlertRule]
        Initial rule list. Add/replace via set_rules().
    on_alert : callable | None
        Called synchronously with each AlertFired. Keep it fast.
    """

    def __init__(
        self,
        store: Optional[MetricStore] = None,
        rules: Optional[List[AlertRule]] = None,
        on_alert: Optional[Callable[[AlertFired], None]] = None,
    ):
        self._store    = store
        self._rules    = list(rules or _default_rules())
        self._on_alert = on_alert
        # rule_name::host → last_fired_ts
        self._last_fired: Dict[str, int] = {}
        # rule_name::host → ts the user acknowledged it. Cooldown alone only
        # spaces out repeats (300 s for most rules), so a condition that stays
        # true re-alerts forever and acknowledging does nothing to stop it —
        # ack marks a past DB row, it never reached the engine. A hold mutes
        # the key for _ack_hold_s; a resolution clears it so a genuinely new
        # occurrence after recovery still alerts.
        self._ack_hold: Dict[str, int] = {}
        self._ack_hold_s: int = DEFAULT_ACK_HOLD_SECONDS
        # host → [(ts, state), ...] — rolling history for flap detection
        self._state_history: Dict[str, List] = {}
        # hosts currently classified as flapping
        self._flapping_hosts: set = set()
        # parent_ip → [child_ip, ...] — for dependency-based suppression
        self._dependency_map: Dict[str, List[str]] = {}
        # optional callable(host) → window_label|None — for maintenance suppression
        self._maintenance_checker: Optional[Callable[[str], Optional[str]]] = None
        # optional callable(host) → bool — per-device alert opt-in scope (None = allow all)
        self._scope_checker: Optional[Callable[[str], bool]] = None
        # optional callable(label, host, rule_name, severity, msg) — logs drops (record_suppression)
        self._suppression_recorder: Optional[Callable[[str, str, str, str, str], None]] = None
        # escalation policies
        self._escalation_policies: List[EscalationPolicy] = []
        # boot-time warmup — suppress all alerts until this timestamp
        self._suppress_until: float = 0.0
        # ── S4-1: resolution tracking ──────────────────────────────────────────
        # host → ts_when_went_down (for HOST_DOWN resolution, downtime calc)
        self._host_down_since: Dict[str, int] = {}
        # service_key → ts_when_went_down (for SERVICE_DOWN resolution)
        self._service_down_since: Dict[str, int] = {}
        # service_key → consecutive failed-check count since last success
        # (grace period before the first SERVICE_DOWN alert fires)
        self._service_fail_streak: Dict[str, int] = {}
        # ── S4-3: consolidation ────────────────────────────────────────────────
        # minimum simultaneous HOST_DOWN alerts to consolidate into one
        self._consolidation_threshold: int = 5
        # ── V6 Sprint 1: resolution tracking for new rule types ────────────────
        self._jitter_high_since: Dict[str, int] = {}
        self._mesh_degraded_since: Dict[str, int] = {}
        self._modem_degraded_since: Dict[str, int] = {}
        self._ip_churn_since: Dict[str, int] = {}
        # ── V6 Sprint 2: resolution tracking for the dormant-engine rules ──────
        self._rtt_anomaly_since: Dict[str, int] = {}
        # ── Signal Quality Phase 3: edge-triggering + duplicate-outage dedup ───
        # Both None/False = the legacy level-triggered path, unchanged. Selected
        # by experimental/signal_quality_v2 in app.py (RULE-EXP1).
        self._availability_gate: Optional[EvidenceGate] = None
        self._suppress_duplicate_outage: bool = False
        # ── Signal Quality Phase 4: INFRA_UNREACHABLE (alert_engine_checks5) ───
        # Built on first use so an engine that never polls hardware carries no
        # gate state. device_key → ts_when_it_stopped_answering.
        self._infra_gate: Optional[EvidenceGate] = None
        self._infra_unreachable_since: Dict[str, int] = {}
        # ── Signal Quality Phase 4: DNS_LATENCY (alert_engine_checks5) ─────────
        # The baseline lives here, not in the caller: there is no logged DNS
        # history anywhere in the app to prefer over it, so unlike
        # MODEM_SIGNAL_DROP there is nothing for a caller to resolve.
        self._dns_gate: Optional[EvidenceGate] = None
        self._dns_series = None            # alert_baseline.RollingSeries, lazily built
        self._dns_latency_since: Dict[str, int] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def set_rules(self, rules: List[AlertRule]) -> None:
        self._rules = list(rules)

    def get_rules(self) -> List[AlertRule]:
        return list(self._rules)

    def set_on_alert(self, cb: Callable[[AlertFired], None]) -> None:
        self._on_alert = cb

    def get_flapping_hosts(self) -> set:
        """Return the set of host identifiers currently classified as flapping."""
        return set(self._flapping_hosts)

    def set_dependency_map(self, parent_ip: str, child_ips: list) -> None:
        """
        Register a parent → children relationship.
        When the parent host is DOWN, HOST_DOWN alerts for all listed children
        are suppressed.  Calling again for the same parent replaces the list.
        """
        self._dependency_map[parent_ip] = list(child_ips)

    def get_dependency_map(self) -> Dict[str, List[str]]:
        """Return a shallow copy of the current dependency map."""
        return {k: list(v) for k, v in self._dependency_map.items()}

    def clear_dependency_map(self) -> None:
        """Remove all registered parent/child dependencies."""
        self._dependency_map.clear()

    # set_maintenance_checker / set_suppression_recorder — see _MaintenanceSuppressionMixin

    def set_warmup_period(self, seconds: float) -> None:
        """Suppress all alert firings for *seconds* after this call.

        Call once at startup to avoid spurious notifications fired before the
        first real monitoring cycle completes.
        """
        self._suppress_until = time.time() + seconds

    def set_escalation_policies(self, policies: List[EscalationPolicy]) -> None:
        """Replace the current escalation policy list."""
        self._escalation_policies = list(policies)

    def get_escalation_policies(self) -> List[EscalationPolicy]:
        """Return a copy of the current escalation policies."""
        return list(getattr(self, "_escalation_policies", []))

    def set_consolidation_threshold(self, n: int) -> None:
        """Set how many simultaneous HOST_DOWN alerts trigger consolidation (default 5)."""
        self._consolidation_threshold = max(2, int(n))

    # set_availability_edge_trigger / set_duplicate_outage_suppression —
    # see _AlertCycleMixin in modules/alert_engine_cycle.py (RULE-AH1 split).

    def check_escalations(self, store: MetricStore) -> List[dict]:
        """
        Return fired alerts that are unacknowledged and past their escalation threshold.

        store: MetricStore instance — used to query unacked alerts.

        Returns a list of dicts with keys:
          alert_row — the alert_fired row dict from MetricStore
          policy    — the matching EscalationPolicy
        """
        policies = getattr(self, "_escalation_policies", [])
        if not policies or store is None:
            return []

        due = []
        for policy in policies:
            if not policy.enabled:
                continue
            wait_s = policy.wait_minutes * 60
            unacked = store.get_unacked_alerts(older_than_s=wait_s)
            for row in unacked:
                if row.get("rule_name") == policy.rule_name and not row.get("escalated"):
                    due.append({"alert_row": row, "policy": policy})
        return due

    # ── S4-4: action steps appended to every alert message — see
    #    modules/alert_engine_routing.py for ACTION_STEPS (RULE-AH1 split) ───

    _append_action = staticmethod(append_action)

    # evaluate_cycle() — see _AlertCycleMixin in modules/alert_engine_cycle.py
    # (RULE-AH1 split). The whole availability-cycle pass moved there together:
    # per-rule evaluation, HOST_DOWN consolidation, and recovery resolution.

    def evaluate_tracker_result(self, tracker_result) -> List[AlertFired]:
        """
        Evaluate NEW_DEVICE / DEVICE_GONE rules against a TrackerResult object.
        Accepts any object with .new_devices and .gone_devices attributes.
        """
        fired: List[AlertFired] = []
        now = int(time.time())

        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.rule_type == "NEW_DEVICE":
                for dev in getattr(tracker_result, "new_devices", []):
                    # RULE-ID1: the MAC is the exact key and is always present on
                    # a TrackedDevice (_normalise() returns None without one).
                    # `host` is the cooldown AND ack-hold key, so keying by the
                    # address made one device's ack mute a co-tenant on a shared
                    # lease -- 7 of 20 addresses on the reference network.
                    host = dev.mac or dev.ip
                    label = dev.hostname or dev.vendor or "Unknown device"
                    alert = self._fire_if_cooled(
                        rule, host, now,
                        message=self._append_action(
                            f"New device joined your network: {label} [{dev.mac}]"
                            f"{' at ' + dev.ip if dev.ip else ''} — was this expected?",
                            "NEW_DEVICE",
                        ),
                        severity="WARNING",
                        value=None,
                    )
                    if alert:
                        fired.append(alert)
                        if self._on_alert:
                            self._on_alert(alert)

            elif rule.rule_type == "DEVICE_GONE":
                for dev in getattr(tracker_result, "gone_devices", []):
                    host = dev.mac or dev.ip          # RULE-ID1 — see NEW_DEVICE above
                    label = dev.hostname or dev.vendor or "Unknown device"
                    alert = self._fire_if_cooled(
                        rule, host, now,
                        message=self._append_action(
                            f"{label} [{dev.mac}] has left your network"
                            f"{' (was at ' + dev.ip + ')' if dev.ip else ''}.",
                            "DEVICE_GONE",
                        ),
                        severity="WARNING",
                        value=None,
                    )
                    if alert:
                        fired.append(alert)
                        if self._on_alert:
                            self._on_alert(alert)

        return fired

    # ── Internal helpers ──────────────────────────────────────────────────────

    # _eval_rule_for_host / _availability_admits / _host_down_rule_covers —
    # see _AlertCycleMixin in modules/alert_engine_cycle.py (RULE-AH1 split).

    def _fire_if_cooled(
        self,
        rule: AlertRule,
        host: str,
        now: int,
        message: str,
        severity: str,
        value: Optional[float],
        scope_host: Optional[str] = None,
    ) -> Optional[AlertFired]:
        """Return an AlertFired only if cooldown has expired and host is not under maintenance.

        `host` doubles as the cooldown dedup key for some rule types (e.g. a
        composite f"{host}::{alert_type}" for IOT_BEHAVIOR) and is not always a
        real device identifier. `scope_host`, when given, is used for the
        per-device scope check instead — defaults to `host` when omitted.
        """
        # Boot warmup — suppress all firings during the initial quiet period
        if time.time() < self._suppress_until:
            return None
        # Maintenance suppression — drop when the host is in a window, but log it
        if self._maintenance_suppresses(host, rule.name, severity, message):
            return None
        # Per-device scope — drop device-health alerts for hosts below the floor
        if self._out_of_scope(
            scope_host if scope_host is not None else host,
            rule.rule_type,
            rule.min_tier,
        ):
            return None
        key = f"{rule.name}::{host}"
        # Acknowledgement hold — the user has said "I know about this one".
        if self._ack_hold_s > 0:
            acked = self._ack_hold.get(key)
            if acked is not None:
                if now - acked < self._ack_hold_s:
                    return None
                del self._ack_hold[key]  # expired — a mute, not a permanent block
        last = self._last_fired.get(key)
        if last is not None and now - last < rule.cooldown_s:
            return None
        self._last_fired[key] = now
        cta_page, cta_filter = _cta_for_rule(rule.rule_type, host)
        return AlertFired(
            rule_name=rule.name,
            rule_type=rule.rule_type,
            host=host,
            message=message,
            severity=severity,
            ts=now,
            value=value,
            cta_page=cta_page,
            cta_filter=cta_filter,
        )

    # ── Acknowledgement holds ─────────────────────────────────────────────────

    def set_ack_hold_seconds(self, seconds: int) -> None:
        """How long an ack mutes the same (rule, host). 0 disables the hold."""
        try:
            self._ack_hold_s = max(0, int(seconds))
        except (TypeError, ValueError):
            self._ack_hold_s = DEFAULT_ACK_HOLD_SECONDS

    def note_acknowledged(
        self, rule_name: str, host: str, ts: Optional[int] = None
    ) -> None:
        """Record that the user acknowledged this (rule, host)."""
        if not rule_name:
            return
        self._ack_hold[f"{rule_name}::{host or ''}"] = int(
            ts if ts is not None else time.time()
        )

    def clear_ack_hold(self, rule_name: str, host: str) -> None:
        """Drop the hold — the condition resolved, so the next one is new."""
        self._ack_hold.pop(f"{rule_name}::{host or ''}", None)

    def load_last_fired(self, rows) -> None:
        """Seed cooldown state from persisted `alert_fired` history.

        `_last_fired` is in-memory, so before this every restart reset every
        cooldown: a condition that was still true at launch re-alerted
        immediately, and a user who restarts often never stopped hearing about
        it. The same defect `load_ack_holds()` fixes for acknowledgements.

        `rows` is `{dedup_key: last_ts}` from
        `MetricStore.get_last_fired_by_rule_host()` — derived from the alert
        history itself rather than a second persistence path, so dedup state
        cannot drift from what the user sees in Alert History. Resolutions are
        excluded there: a resolution is not a firing, and seeding one would mute
        the next genuine alert for a whole cooldown after every recovery.
        """
        for key, ts in (rows or {}).items():
            if not key or not isinstance(key, str):
                continue
            try:
                ts_i = int(ts)
            except (TypeError, ValueError):
                continue
            if ts_i > self._last_fired.get(key, 0):
                self._last_fired[key] = ts_i

    def load_ack_holds(self, acked_rows) -> None:
        """Seed holds from persisted `alert_fired` rows.

        _ack_hold (like _last_fired) is in-memory, so every restart would
        otherwise unmute the whole backlog and re-alert it within one cooldown.
        Reads acked_ts straight off the existing rows — no schema change. Rows
        that are unacked or malformed are skipped, and the newest ack wins per
        key so an older row can't shadow a more recent acknowledgement.
        """
        for row in acked_rows or []:
            if not isinstance(row, dict):
                continue
            rule_name = row.get("rule_name") or ""
            acked_ts  = row.get("acked_ts")
            if not rule_name or acked_ts in (None, ""):
                continue
            try:
                ts = int(acked_ts)
            except (TypeError, ValueError):
                continue
            key = f"{rule_name}::{row.get('host') or ''}"
            if ts > self._ack_hold.get(key, 0):
                self._ack_hold[key] = ts

    def _fire_resolution(
        self,
        rule: AlertRule,
        host: str,
        now: int,
        message: str,
        *,
        downtime_s: Optional[int] = None,
        cta_page: Optional[str] = None,
        cta_filter: Optional[str] = None,
        scope_host: Optional[str] = None,
    ) -> Optional[AlertFired]:
        """Return a resolution AlertFired unless boot warmup, a maintenance
        window, or device-scope opt-in suppresses it.

        Deliberately does NOT apply the per-rule cooldown _fire_if_cooled
        does — a resolution fires at most once per down-state (the caller
        pops its own `_since`-style tracking dict before calling this) and
        must never be swallowed by the cooldown of the alert it closes. The
        acknowledgement hold is skipped for the same reason, and is *cleared*
        here: the condition is over, so the next occurrence is genuinely new
        and must be allowed to alert.
        """
        self.clear_ack_hold(rule.name, host)
        if time.time() < self._suppress_until:
            return None
        if self._maintenance_suppresses(host, rule.name, "HEALTHY", message):
            return None
        if self._out_of_scope(
            scope_host if scope_host is not None else host,
            rule.rule_type,
            rule.min_tier,
        ):
            return None
        return AlertFired(
            rule_name=rule.name,
            rule_type=rule.rule_type,
            host=host,
            message=message,
            severity="HEALTHY",
            ts=now,
            is_resolution=True,
            downtime_s=downtime_s,
            cta_page=cta_page,
            cta_filter=cta_filter,
        )

    # _update_state_history / _rebuild_flapping_hosts / _is_dependency_suppressed
    # / _count_transitions — see _AlertCycleMixin in
    # modules/alert_engine_cycle.py (RULE-AH1 split). They are reached through
    # AlertEngine by inheritance, so `AlertEngine._count_transitions(...)`
    # still resolves.


