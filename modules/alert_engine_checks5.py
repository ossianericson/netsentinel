"""
alert_engine_checks5.py — _AlertChecksMixin5: INFRA_UNREACHABLE and DNS_LATENCY
rule evaluation (Signal Quality Phase 4).

New file rather than growing alert_engine_checks4.py — keeps every
alert_engine_checks*.py file under the RULE-AH1 780-line budget (see
tests/test_module_loc.py).

Provides:
  evaluate_infra_unreachable_checks() — INFRA_UNREACHABLE: a registered piece
      of infrastructure (modem, router, AP, switch) stopped answering its
      poll.
  evaluate_dns_latency_checks()       — DNS_LATENCY: name resolution is slow
      relative to what this network's resolver normally does.

Fed from `workers.plugin_polling_worker.PluginPollingWorker`'s `error`/`result`
signals via `ui/pages/hardware_integration_page.py`. Until Phase 4 that signal
reached only the plugin card's health counter and the circuit breaker, so the
modem could be unplugged and the app would grey out a card without ever saying
anything — one of the "signals the user calls real produce nothing" cases the
program was opened to fix.

Unlike checks3/checks4's event-shaped rules, this one describes a *state*, so
it fires a resolution when the device answers again — the same shape as
HOST_DOWN and MESH_DEGRADED.

Corroboration comes from `modules.evidence.EvidenceGate`, not a private streak
dict: the gate is the shared edge-trigger predicate, and re-deriving "N
consecutive, then once per episode" here is exactly how the shapes drift apart
(see the module docstring in evidence.py). The plugin card's own `consecutive`
counter is deliberately NOT reused as the streak — it carries an AUTH carve-out
for a different purpose (keeping the card in a "Re-enter Password" state), and
the gate must be driven from the observation itself.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 1).
  • No MetricStore access.
"""
from __future__ import annotations

import math
import time
from typing import List, Optional, Sequence

from modules.alert_baseline import RollingSeries, _mean_stddev
from modules.alert_types import AlertFired
from modules.evidence import EvidenceGate

# Consecutive failed polls before an outage is worth reporting.
#
# 2, not 1: a single failed poll is routinely a transient timeout on a busy
# link, and the gate is edge-triggered so a longer streak would not reduce
# repeats — it only trades responsiveness for confidence in the *first* claim.
# 2, not 3: the modem plugin polls every 30 s (PluginPollingWorker._INTERVALS),
# so 2 puts the first alert 60 s into an outage, and router/AP at 60 s puts it
# at 120 s — both inside acceptance criterion 5's 3-minute budget, which 3
# would breach for router/AP at 180 s.
_INFRA_MIN_CONSECUTIVE = 2

# ── DNS_LATENCY ───────────────────────────────────────────────────────────────
#
# A network-wide metric, so it is keyed by a literal string rather than a device
# — the same class as MESH_DEGRADED ("mesh") and GRADE_REGRESSION
# ("network-grade"), and the reason DNS_LATENCY is in neither
# DEVICE_SCOPED_RULE_TYPES nor SECURITY_RELEVANT_RULE_TYPES.
_DNS_KEY = "dns"

# Two consecutive slow lookups, for the same reason as _INFRA_MIN_CONSECUTIVE:
# one slow resolution is routine, and the gate is edge-triggered so a longer
# streak buys confidence in the first claim rather than fewer repeats. At the
# logger's default 60 s cycle this puts the first alert 120 s in, inside
# acceptance criterion 5's 3-minute budget.
_DNS_MIN_CONSECUTIVE = 2

# Samples of learned history before the rule will speak. 20 at the 60 s cycle is
# a ~20-minute warm-up, matching modem_sinr_dropped()'s default.
_DNS_MIN_SAMPLES = 20

_DNS_SIGMA = 2.0

# Below this, "anomalous" is not the same as "slow". On a resolver that answers
# in 2 ms +/- 0.4 ms, mean + 2*sigma is 2.8 ms, and without a floor every third
# lookup clears it. 200 ms is not invented here: it is already the app's
# DNS-is-slow number in ui/pages/log_source_panel.py's live-challenge trigger.
_DNS_ABSOLUTE_FLOOR_MS = 200.0

# 240 samples = 4 hours at the logger's default 60 s cycle.
_DNS_SERIES_MAXLEN = 240


def _as_latency(value) -> Optional[float]:
    """Coerce a reported DNS latency to a usable float, or None.

    None covers every input the rule must not treat as an observation: a failed
    probe (network_logger reports -1.0), a missing field, and the non-numeric /
    non-finite values that reach here from untyped sources.
    """
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    v = float(value)
    if not math.isfinite(v) or v < 0:
        return None
    return v


def _dns_threshold(prior: List[float]) -> Optional[float]:
    """mean + 2*sigma, floored — or None while the baseline is still cold."""
    if len(prior) < _DNS_MIN_SAMPLES:
        return None
    mean, std = _mean_stddev(prior)
    return max(_DNS_ABSOLUTE_FLOOR_MS, mean + _DNS_SIGMA * std)


class _AlertChecksMixin5:
    """Mixin for AlertEngine providing the INFRA_UNREACHABLE / DNS_LATENCY checks."""

    def evaluate_infra_unreachable_checks(
        self,
        device_key: str,
        unreachable: bool,
        label: str = "",
        reason: str = "",
        ts: Optional[int] = None,
    ) -> List[AlertFired]:
        """INFRA_UNREACHABLE — a polled infrastructure device stopped answering.

        Call once per poll outcome, for both outcomes: `unreachable=True` on a
        failed poll and `False` on a successful one. The healthy call is what
        ends the episode and releases the gate's state, so it is not optional.

        device_key — stable per-instance id (the plugin instance id/path)
        label      — human name for the message ("ZTE MC889")
        reason     — classified error text, carried into the message
        """
        fired: List[AlertFired] = []
        now = int(ts if ts is not None else time.time())
        name = label or device_key

        if self._infra_gate is None:
            self._infra_gate = EvidenceGate(min_consecutive=_INFRA_MIN_CONSECUTIVE)
        self._infra_gate.observe(device_key, unreachable, now)

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "INFRA_UNREACHABLE":
                continue
            if rule.host and rule.host != device_key:
                continue

            if unreachable:
                admitted, evidence = self._infra_gate.admit(device_key)
                if not admitted:
                    continue
                detail = f" ({reason})" if reason else ""
                alert = self._fire_if_cooled(
                    rule, device_key, now,
                    message=self._append_action(
                        f"{name} is not responding{detail} — "
                        f"{evidence.basis}.  Anything behind it is offline too.",
                        "INFRA_UNREACHABLE",
                    ),
                    severity="CRITICAL",
                    value=None,
                )
                if alert:
                    self._infra_unreachable_since.setdefault(device_key, now)
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)
            elif device_key in self._infra_unreachable_since:
                down_since = self._infra_unreachable_since.pop(device_key)
                resolution = self._fire_resolution(
                    rule, device_key, now,
                    message=(
                        f"{name} is responding again — it was unreachable for "
                        f"{max(0, now - down_since)}s."
                    ),
                    cta_page="Hardware",
                    cta_filter=None,
                )
                if resolution:
                    fired.append(resolution)
                    if self._on_alert:
                        self._on_alert(resolution)

        return fired

    def evaluate_dns_latency_checks(
        self,
        dns_ms,
        *,
        outage_hosts: Sequence[str] = (),
        ts: Optional[int] = None,
    ) -> List[AlertFired]:
        """DNS_LATENCY — name resolution is slow for *this* network.

        Call once per measured lookup, for every outcome. There is no logged
        DNS history to learn from anywhere in the app — no `dns_sample` table,
        and `device_baseline` reads `device_state`, which holds no DNS rows —
        so the baseline is the in-memory `RollingSeries` this method owns.
        Unlike MODEM_SIGNAL_DROP there is no DB copy to prefer, so there is
        nothing for a caller to resolve and the series does not belong outside.

        dns_ms       — measured latency in ms; -1.0 (or any negative/unusable
                       value) means the probe failed, which is an outage and
                       not this rule's claim to make.
        outage_hosts — hosts whose being down makes slow DNS a *symptom*
                       rather than a finding; typically the gateway and the
                       internet reachability probes. Caller-supplied, because
                       `_host_down_since` holds every LAN device since C3
                       routed the LAN availability worker into the engine, and
                       one dead printer must not mute DNS alerting.
        """
        fired: List[AlertFired] = []
        now = int(ts if ts is not None else time.time())

        if self._dns_series is None:
            self._dns_series = RollingSeries(maxlen=_DNS_SERIES_MAXLEN)
        if self._dns_gate is None:
            self._dns_gate = EvidenceGate(min_consecutive=_DNS_MIN_CONSECUTIVE)

        value = _as_latency(dns_ms)
        if value is None:
            # A resolver that returned nothing is neither slow nor healthy.
            # Feeding it through as healthy would silently end an open episode
            # and let the next slow sample re-alert about the same one.
            return fired

        threshold = _dns_threshold(self._dns_series.values())
        slow = threshold is not None and value > threshold

        # Learn only from samples that were NOT classified as slow. Letting the
        # anomaly into its own baseline desensitises the rule and then falsely
        # resolves it: measured on 20 samples at ~20 ms followed by a steady
        # 600 ms, mean + 2*sigma crosses 600 by the sixth cycle, so the engine
        # would alert and then announce "back to normal" mid-outage. Pinned by
        # tests/test_alert_engine_dns_latency.py::
        # test_a_sustained_episode_never_normalises_itself.
        if not slow:
            self._dns_series.append(value)

        if any(h in self._host_down_since for h in outage_hosts):
            # reset() rather than observe(), deliberately, and against
            # EvidenceGate's usual "drive it from the observation" contract:
            # suppression here means "do not make this claim now", not "this
            # episode is spent". If DNS is still slow once the outage lifts,
            # that is a genuine independent finding that has never been
            # reported, and the edge has to be able to fire for it.
            self._dns_gate.reset(_DNS_KEY)
            return fired

        self._dns_gate.observe(_DNS_KEY, slow, now)

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "DNS_LATENCY":
                continue
            if rule.host and rule.host != _DNS_KEY:
                continue

            if slow:
                admitted, evidence = self._dns_gate.admit(_DNS_KEY)
                if not admitted:
                    continue
                alert = self._fire_if_cooled(
                    rule, _DNS_KEY, now,
                    message=self._append_action(
                        f"DNS lookups are taking {value:.0f} ms — normally under "
                        f"{threshold:.0f} ms on this network ({evidence.basis}).  "
                        f"Websites will feel slow to load even though your "
                        f"connection speed is fine.",
                        "DNS_LATENCY",
                    ),
                    severity="WARNING",
                    value=value,
                )
                if alert:
                    self._dns_latency_since.setdefault(_DNS_KEY, now)
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)
            elif _DNS_KEY in self._dns_latency_since:
                slow_since = self._dns_latency_since.pop(_DNS_KEY)
                resolution = self._fire_resolution(
                    rule, _DNS_KEY, now,
                    message=(
                        f"DNS lookups are back to normal ({value:.0f} ms) — they "
                        f"were slow for {max(0, now - slow_since)}s."
                    ),
                    cta_page="DNS & Stability",
                    cta_filter=None,
                )
                if resolution:
                    fired.append(resolution)
                    if self._on_alert:
                        self._on_alert(resolution)

        return fired
