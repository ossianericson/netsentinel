"""
evidence.py — the corroboration predicate for the Signal Quality Program.

Phase 3. Every claim the app makes about a device answers the same question in
a slightly different accent: *has this been seen enough times, consecutively,
to be worth saying — and is this the first time we would say it about this
episode?*  Phase 0 measured what happens when nothing asks it: `HOST_DOWN`
fired 1,637 times against 164 resolutions on the reference network, a 10:1
ratio, because `state == "DOWN"` was evaluated fresh on every cycle with only a
120 s cooldown between repeats. One overnight outage produced roughly 240
alerts describing one fact.

The fix is not a longer cooldown — a cooldown spaces repeats out, it does not
stop them, and lengthening it delays the *first* alert too. The fix is to make
the trigger an **edge**: fire on the observation that confirms an episode, then
stay silent until the condition clears and a genuinely new episode begins.

Two things live here rather than in a private streak dict inside AlertEngine:

  * **Reuse.** Phase 4 wires four more signals (modem unreachable, mesh node
    degraded, DNS latency, gateway loss) that each need exactly this predicate.
    `alert_engine_checks.py` already grew one hand-rolled copy —
    `_SERVICE_DOWN_MIN_CONSECUTIVE_FAILS` with its own `_service_fail_streak`
    dict — and a second, third and fourth copy is how the shapes drift apart.
  * **Testability.** The edge is the load-bearing part of Phase 3's noise
    reduction, and it is far easier to pin here, against a pattern string, than
    through a full `evaluate_cycle()` round trip.

What this module deliberately does NOT do
-----------------------------------------
The program plan sketched `EvidenceGate.admit()` as checking identity,
corroboration, baseline deviation, **tier** and actionability. Tier is not
checked here: `_DeviceScopeMixin._out_of_scope()` already applies it to every
rule type from a single place, including the ~15 rule types that never reach
this gate, and a second copy would be a second thing to keep in step. Identity
and baseline arrive as caller-supplied predicates for the same reason — the
gate composes verdicts, it does not go and fetch them.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 1).
  • No MetricStore access; callers pass what they already know.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


# How many consecutive symptomatic observations the availability path requires
# before it will speak. 1 = pure edge-triggering: alert on the first observation
# of an episode, then stay silent until it clears.
#
# Deliberately 1 and not 3. The monitor layer carries its own confirmation
# (device_baseline.DOWN_CONFIRMATION_CYCLES) before it will even classify a host
# as DOWN, so the two stack: raising this to 3 would put the first gateway alert
# 4 cycles / 4 minutes after the outage began, past acceptance criterion 5's
# 3-minute budget. Confirmation belongs in one layer, and the monitor is the one
# that can still see the raw ping. Pinned by
# tests/test_alert_engine_edge_trigger.py::
# test_confirmation_delay_stays_inside_the_three_minute_budget.
DEFAULT_MIN_CONSECUTIVE = 1

# Confidence bonus applied when the caller confirms the observation also
# deviates from the device's own learned baseline. Ordering aid, not a
# probability — see Evidence.confidence.
#
# Repetition alone is therefore capped at 1.0 - this value: a claim corroborated
# only by "we saw it N times" can never outrank one that is *also* abnormal for
# the device in question. Without the headroom the bonus is unreachable at
# min_consecutive=1 (the shipped default), which is the whole availability path.
_BASELINE_CONFIDENCE_BONUS = 0.25


@dataclass(frozen=True)
class Evidence:
    """What is known about the episode a candidate claim belongs to.

    observations — symptomatic observations in the current episode
    consecutive  — consecutive symptomatic observations right now
    window_s     — seconds spanned by the current streak (0 for a single one)
    confidence   — 0.0..1.0 **ordering aid, not a probability**. It ranks two
                   claims against each other; it does not estimate how likely
                   either is to be true. RULE-A3's severity vocabulary is
                   unaffected and stays the thing shown to users.
    basis        — one plain-English line naming the corroboration, suitable
                   for an alert detail field or a log line.
    """
    observations: int
    consecutive:  int
    window_s:     int
    confidence:   float
    basis:        str


_EMPTY = Evidence(
    observations=0, consecutive=0, window_s=0, confidence=0.0,
    basis="no observations recorded",
)


@dataclass
class _Episode:
    """Mutable per-key state. Exists only while a key is symptomatic."""
    observations: int
    consecutive:  int
    first_ts:     int
    last_ts:      int


class EvidenceGate:
    """Edge-triggered admission for a repeating symptomatic condition.

    Usage is two calls per key per cycle::

        gate.observe(host, state == "DOWN", now)   # every host, every cycle
        ok, ev = gate.admit(host)                  # only where a rule asks

    `observe()` must be driven from the **observation**, never from whether an
    alert was ultimately emitted. A firing suppressed downstream (scope,
    maintenance window, cooldown, acknowledgement hold) must not re-arm the
    edge, or re-opening scope mid-outage would manufacture a fresh "went
    offline" claim for an outage that started hours earlier.

    `admit()` is a pure read of the current streak: it returns True exactly
    while `consecutive == min_consecutive`, so two rules asking about the same
    host in the same cycle get the same answer and neither consumes a token.
    """

    def __init__(
        self,
        min_consecutive: int = DEFAULT_MIN_CONSECUTIVE,
        require_baseline_deviation: bool = False,
    ) -> None:
        if int(min_consecutive) < 1:
            raise ValueError(
                f"min_consecutive must be >= 1, got {min_consecutive!r} — "
                f"0 would admit a condition that was never observed"
            )
        self._min_consecutive = int(min_consecutive)
        self._require_baseline_deviation = bool(require_baseline_deviation)
        self._episodes: Dict[str, _Episode] = {}

    # ── Observation ───────────────────────────────────────────────────────────

    def observe(self, key: str, symptomatic: bool, ts: int) -> Evidence:
        """Record one observation of `key`. Returns the resulting Evidence.

        A non-symptomatic observation ends the episode and releases the key's
        state — the gate sees every host on every cycle for the life of the
        process, so healthy keys must not accumulate.
        """
        if not symptomatic:
            self._episodes.pop(key, None)
            return _EMPTY

        episode = self._episodes.get(key)
        if episode is None:
            episode = _Episode(
                observations=0, consecutive=0, first_ts=int(ts), last_ts=int(ts)
            )
            self._episodes[key] = episode
        episode.observations += 1
        episode.consecutive  += 1
        episode.last_ts       = int(ts)
        return self._evidence(episode, baseline_deviates=None)

    def reset(self, key: str) -> None:
        """Re-arm `key` without a healthy observation.

        For callers that resolve an episode out of band — the engine fires a
        HOST_DOWN resolution from its own `_host_down_since` bookkeeping, and a
        subsequent outage must be allowed to alert even if the intervening
        healthy cycle was never fed through observe().
        """
        self._episodes.pop(key, None)

    forget = reset   # same operation; named for the "drop this host" intent

    def tracked_keys(self) -> int:
        """How many keys currently hold episode state. Leak check for tests."""
        return len(self._episodes)

    # ── Admission ─────────────────────────────────────────────────────────────

    def admit(
        self,
        key: str,
        *,
        identity_stable: bool = True,
        baseline_deviates: Optional[bool] = None,
    ) -> Tuple[bool, Evidence]:
        """Should a claim about `key` be made right now?

        identity_stable   — False for a host the app cannot honestly name
                            (device_identity: NOT_A_DEVICE / ANONYMOUS). Never
                            admitted, whatever the corroboration.
        baseline_deviates — True/False when the caller knows whether this
                            departs from the device's own normal; **None when
                            unknown**, which never suppresses. Over-suppression
                            is the failure mode the program plan calls out, and
                            "no baseline learned yet" is the common case on a
                            fresh install.
        """
        episode = self._episodes.get(key)
        if episode is None:
            return False, _EMPTY

        evidence = self._evidence(episode, baseline_deviates, identity_stable)

        if not identity_stable:
            return False, evidence
        if (
            self._require_baseline_deviation
            and baseline_deviates is False
        ):
            return False, evidence
        # The edge: exactly the observation that confirms the episode. Strict
        # equality, not >=, is what makes this fire once instead of forever.
        return episode.consecutive == self._min_consecutive, evidence

    # ── Internal ──────────────────────────────────────────────────────────────

    def _evidence(
        self,
        episode: _Episode,
        baseline_deviates: Optional[bool],
        identity_stable: bool = True,
    ) -> Evidence:
        window_s = max(0, episode.last_ts - episode.first_ts)
        if not identity_stable:
            confidence = 0.0
        else:
            corroboration = min(1.0, episode.consecutive / self._min_consecutive)
            confidence = corroboration * (1.0 - _BASELINE_CONFIDENCE_BONUS)
            if baseline_deviates is True:
                confidence = min(1.0, confidence + _BASELINE_CONFIDENCE_BONUS)
        plural = "s" if episode.consecutive != 1 else ""
        basis = (
            f"{episode.consecutive} consecutive observation{plural} "
            f"over {window_s}s"
        )
        if baseline_deviates is True:
            basis += ", outside this device's learned normal"
        elif baseline_deviates is False:
            basis += ", within this device's learned normal"
        return Evidence(
            observations=episode.observations,
            consecutive=episode.consecutive,
            window_s=window_s,
            confidence=round(confidence, 3),
            basis=basis,
        )
