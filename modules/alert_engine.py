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

from modules.alert_types import AlertFired, AlertRule, RULE_TYPES  # noqa: F401 — re-exported
from modules.metric_store import MetricStore
from modules.alert_suppressor import (
    EscalationPolicy, _default_rules, rule_settings_key, _MaintenanceSuppressionMixin,
)
from modules.alert_engine_checks import _AlertChecksMixin
from modules.alert_engine_checks2 import _AlertChecksMixin2
from modules.speed_drop_detector import RESTART_CHECKLIST

# Re-exported for backwards-compat callers (e.g. from modules.alert_engine import rule_settings_key)
__all__ = [
    "AlertRule", "AlertFired", "AlertEngine",
    "EscalationPolicy", "rule_settings_key", "RULE_TYPES",
]


# ── CTA routing — maps rule_type → (nav_label, filter_string) ────────────────

_RULE_CTA: Dict[str, str] = {
    "RTT_THRESHOLD":  "DNS & Stability",
    "LOSS_THRESHOLD": "DNS & Stability",
    "HOST_DOWN":      "Inventory",
    "HOST_DEGRADED":  "Inventory",
    "NEW_DEVICE":     "Devices",
    "DEVICE_GONE":    "Inventory",
    "CERT_EXPIRY":    "TLS & Cert Monitor",
    "CERT_EXPIRED":   "TLS & Cert Monitor",
    "FLAP":           "Trend Forecasts",
    "SERVICE_DOWN":   "Service Heartbeat",
    "BASELINE_DROP":  "Speed Test",
    "JITTER_HIGH":        "Network Logger",
    "MESH_DEGRADED":      "Hardware",
    "MODEM_SIGNAL_DROP":  "Hardware",
    "GRADE_REGRESSION":   "Network Grade",
    "IP_CHURN":           "Devices",
    "RTT_ANOMALY":        "DNS & Stability",
    "IOT_BEHAVIOR":       "IoT Behaviour",
    "TREND_FORECAST":     "Trend Forecasts",
}


def _cta_for_rule(rule_type: str, host: str) -> tuple[Optional[str], Optional[str]]:
    """Return (cta_page, cta_filter) for an alert so the UI can deep-link to the right page."""
    page = _RULE_CTA.get(rule_type)
    if not page:
        return None, None
    return page, host


# ── Engine ────────────────────────────────────────────────────────────────────

class AlertEngine(_AlertChecksMixin, _AlertChecksMixin2, _MaintenanceSuppressionMixin):
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
        # host → [(ts, state), ...] — rolling history for flap detection
        self._state_history: Dict[str, List] = {}
        # hosts currently classified as flapping
        self._flapping_hosts: set = set()
        # parent_ip → [child_ip, ...] — for dependency-based suppression
        self._dependency_map: Dict[str, List[str]] = {}
        # optional callable(host) → window_label|None — for maintenance suppression
        self._maintenance_checker: Optional[Callable[[str], Optional[str]]] = None
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

    # ── S4-4: action steps appended to every alert message ───────────────────

    _ACTION_STEPS: Dict[str, str] = {
        "RTT_THRESHOLD":  "→ Run a speed test  → Check if other devices are also slow",
        "LOSS_THRESHOLD": "→ Restart your router  → Check all cable connections",
        "HOST_DOWN":      "→ Check the device is powered on  → Check network cable or Wi-Fi",
        "HOST_DEGRADED":  "→ Check for congestion  → Run a speed test to confirm",
        "NEW_DEVICE":     "→ Open Devices to identify it  → Block in your router if unexpected",
        "DEVICE_GONE":    "→ Check if the device was intentionally disconnected",
        "CERT_EXPIRY":    "→ Renew the certificate  → Check auto-renewal is enabled",
        "CERT_EXPIRED":   "→ Renew the certificate now  → Visitors will see security warnings",
        "FLAP":           "→ Check the cable or Wi-Fi signal  → Look for interference",
        "SERVICE_DOWN":   "→ Restart the service  → Check firewall rules for this port",
        "BASELINE_DROP":  "  ".join(f"→ {step}" for step in RESTART_CHECKLIST),
    }

    @staticmethod
    def _append_action(message: str, rule_type: str) -> str:
        step = AlertEngine._ACTION_STEPS.get(rule_type, "")
        if step and step not in message:
            return f"{message}  {step}"
        return message

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
            downtime = now - down_ts
            mins, secs = divmod(downtime, 60)
            if mins >= 60:
                duration = f"{mins // 60}h {mins % 60}m"
            elif mins > 0:
                duration = f"{mins}m {secs}s"
            else:
                duration = f"{secs}s"
            resolution = AlertFired(
                rule_name="Host Down",
                rule_type="HOST_DOWN",
                host=host,
                message=(
                    f"{host} is back online — was unreachable for {duration}."
                ),
                severity="HEALTHY",
                ts=now,
                is_resolution=True,
                downtime_s=downtime,
                cta_page="Inventory",
                cta_filter=host,
            )
            fired.append(resolution)
            if self._on_alert:
                self._on_alert(resolution)

        # Track hosts newly going down (not consolidated)
        for alert in down_alerts:
            if len(down_alerts) < self._consolidation_threshold:
                self._host_down_since.setdefault(alert.host, now)

        return fired

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
                    host = dev.ip or dev.mac
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
                    host = dev.ip or dev.mac
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
                    return self._fire_if_cooled(
                        rule, host, now,
                        message=self._append_action(
                            f"{host} has gone offline and is not responding to pings.",
                            rt,
                        ),
                        severity="CRITICAL",
                        value=None,
                    )
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

    def _fire_if_cooled(
        self,
        rule: AlertRule,
        host: str,
        now: int,
        message: str,
        severity: str,
        value: Optional[float],
    ) -> Optional[AlertFired]:
        """Return an AlertFired only if cooldown has expired and host is not under maintenance."""
        # Boot warmup — suppress all firings during the initial quiet period
        if time.time() < self._suppress_until:
            return None
        # Maintenance suppression — drop when the host is in a window, but log it
        if self._maintenance_suppresses(host, rule.name, severity, message):
            return None
        key = f"{rule.name}::{host}"
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


