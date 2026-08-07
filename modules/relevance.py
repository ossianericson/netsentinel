"""
relevance.py — one ranking function for every surface that makes a claim.

Phase 5 of the Signal Quality Program. Phases 1-4 decided *whether* the app is
allowed to say something: identity, importance tier, per-device baseline, and
corroborating evidence. What remained was that each surface then ordered the
survivors by its own rule — almost always "newest first" — so a gateway outage
from ten minutes ago sat below a guest phone joining ten seconds ago on the
Timeline, the Home card, the Event Feed and the Monitor tiles alike.

`score(claim)` is the shared answer. It is **ordering only**:

  * It does not introduce a severity vocabulary. RULE-A3's
    `Info/Warning/High/Critical` and the internal `RISK_COLORS` scale both stay
    exactly as they are, and a Claim carries its producer's severity string
    through untouched. Scoring reads that string; nothing writes one.
  * The number is not a probability, a confidence, or a percentage, and must
    never be shown to a user. It exists to sort a list.

**Over-suppression is the failure mode to watch** — the program plan says so
explicitly, and it is the reason for the neutral-default rule that runs through
this module: *absence of information never ranks a claim down.* An unknown tier
outranks a known-transient one; an absent confidence outranks a low one; an
unrecognised severity still scores above zero. A fresh install knows none of
these things about anything, and a ranking layer that reads "I don't know" as
"unimportant" would bury every claim on day one.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 1).
  • No MetricStore access; callers pass the tier map they already read
    (MetricStore.get_importance_tiers() is one query for the whole inventory).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional

__all__ = [
    "Claim",
    "score",
    "rank",
    "claim_from_alert_row",
    "claim_from_device_event",
]


# ── Weights ──────────────────────────────────────────────────────────────────
#
# Both severity vocabularies in use are accepted, because relevance sits between
# them: the alert engine writes INFO/WARNING/CRITICAL/HEALTHY, while RULE-A3's
# user-facing set is Info/Warning/High/Critical, and `alert_audit` additionally
# requires MEDIUM to exist in the router's ordering. Mapping both here is what
# lets this module rank across surfaces without anyone inventing a third set.
_SEVERITY_WEIGHT = {
    "CRITICAL": 1.00,
    "HIGH":     0.80,
    "WARNING":  0.60,
    "MEDIUM":   0.50,
    "INFO":     0.30,
    # A resolution is real news and belongs on the Timeline, but "the gateway
    # came back" must never outrank "the gateway is down".
    "HEALTHY":  0.15,
}

# An unrecognised severity ranks as INFO rather than 0. A zero would silently
# drop the claim to the bottom of every surface, which is indistinguishable
# from suppressing it — and the producer of an unknown string is a bug to find,
# not a claim to hide.
_SEVERITY_UNKNOWN = 0.30

_TIER_WEIGHT = {
    "critical":       1.00,
    "infrastructure": 0.85,
    "personal":       0.60,
    "transient":      0.35,
}

# Deliberately above "transient" and below "personal": a device the importance
# model has no row for is unranked, not unimportant. Ranking it beneath a device
# explicitly known to be transient would mean a fresh install — where nothing is
# tiered yet — sorts its whole inventory below its own noise.
_TIER_UNKNOWN = 0.60

# Confidence scales within a band rather than from zero: a claim the evidence
# gate rated 0.1 is weak, not absent, and still outranks nothing at all.
_CONFIDENCE_FLOOR = 0.60
_CONFIDENCE_UNKNOWN = 1.00   # no gate on this path — neutral, never a penalty

# Recency half-life. 24 h keeps "today" clearly above "last week" while leaving
# a 7-day Timeline usefully ordered rather than collapsing to a single bucket.
_RECENCY_HALF_LIFE_S = 86_400.0
# Weight of the slow tail below. Not a flat floor: an exponential alone
# underflows to 0 within a few weeks, so every old claim would score identically
# and the surface would lose all ordering among its own history — a Timeline
# showing a year of events would render its tail in arbitrary order. The tail is
# hyperbolic instead, so recency stays *strictly* decreasing forever while the
# exponential does the real work inside the first few days.
_RECENCY_TAIL = 0.05
_RECENCY_TAIL_SCALE_S = 365.0 * 86_400.0

_ACTIONABLE_BONUS = 1.15      # multiplicative; the clamp keeps it in range
_ACKNOWLEDGED_FACTOR = 0.40   # the user has said "I know" — below unacked, not gone

# Dismissal history. Each dismissal of a rule_type costs a little, down to a
# floor: a class the user always dismisses sinks but stays rankable. The floor
# is above the gap between adjacent severities on purpose — see
# tests/test_relevance.py::test_dismissal_cannot_reorder_a_critical_below_an_info.
_DISMISSAL_STEP = 0.03
_DISMISSAL_FLOOR = 0.70


# ── Claim ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Claim:
    """One thing the app is about to say, normalised across source tables.

    Built by the adapters below from an `alert_fired` row or a `device_event`,
    so a surface mixing both (Timeline, Home, the Monitor tiles) can order them
    against each other instead of interleaving two separate sorts.

    severity — the producer's own string, in either vocabulary. Carried through
               untouched; relevance reads it and never rewrites it.
    tier     — device_importance.Tier value, or None when unknown (neutral).
    confidence — evidence.Evidence.confidence, or None when the producing path
               has no evidence gate (neutral, never a penalty).
    """

    ts: int
    severity: str
    rule_type: str = ""
    host: str = ""
    tier: Optional[str] = None
    confidence: Optional[float] = None
    actionable: bool = False
    acknowledged: bool = False


# ── Scoring ──────────────────────────────────────────────────────────────────

def _recency(ts: int, now: float) -> float:
    # A future timestamp is clock skew between the producer and the renderer,
    # not a more relevant claim — clamp rather than reward it.
    age = max(0.0, float(now) - float(ts))
    decay = 0.5 ** (age / _RECENCY_HALF_LIFE_S)
    tail = 1.0 / (1.0 + age / _RECENCY_TAIL_SCALE_S)
    return _RECENCY_TAIL * tail + (1.0 - _RECENCY_TAIL) * decay


def _dismissal_factor(rule_type: str, dismissals: Optional[Mapping[str, int]]) -> float:
    if not dismissals or not rule_type:
        return 1.0
    try:
        n = int(dismissals.get(rule_type, 0) or 0)
    except (TypeError, ValueError):
        return 1.0
    if n <= 0:
        return 1.0
    return max(_DISMISSAL_FLOOR, 1.0 - _DISMISSAL_STEP * n)


def score(
    claim: Claim,
    *,
    now: Optional[float] = None,
    dismissals: Optional[Mapping[str, int]] = None,
) -> float:
    """Rank one claim against others. Returns 0.0..1.0. **Ordering only.**

    Never a severity, never a probability, never shown to a user. `dismissals`
    is {rule_type: times the user dismissed one} — it de-ranks a class the user
    keeps waving away without ever silencing it.
    """
    now = time.time() if now is None else now

    sev = _SEVERITY_WEIGHT.get(str(claim.severity or "").strip().upper(),
                               _SEVERITY_UNKNOWN)
    tier = _TIER_WEIGHT.get(str(claim.tier or "").strip().lower(), _TIER_UNKNOWN)

    if claim.confidence is None:
        conf = _CONFIDENCE_UNKNOWN
    else:
        try:
            raw = min(1.0, max(0.0, float(claim.confidence)))
        except (TypeError, ValueError):
            raw = 1.0
        conf = _CONFIDENCE_FLOOR + (1.0 - _CONFIDENCE_FLOOR) * raw

    value = sev * tier * conf * _recency(claim.ts, now)
    if claim.actionable:
        value *= _ACTIONABLE_BONUS
    if claim.acknowledged:
        value *= _ACKNOWLEDGED_FACTOR
    value *= _dismissal_factor(claim.rule_type, dismissals)

    return round(min(1.0, max(0.0, value)), 6)


def rank(
    claims: Iterable[Claim],
    *,
    now: Optional[float] = None,
    dismissals: Optional[Mapping[str, int]] = None,
) -> List[Claim]:
    """Return `claims` most-relevant first. Stable, and never mutates the input.

    Stability matters: two equally-scored claims must keep the producer's own
    order, so a surface that already sorted by timestamp does not shuffle on
    every refresh.
    """
    now = time.time() if now is None else now
    return sorted(
        list(claims),
        key=lambda c: score(c, now=now, dismissals=dismissals),
        reverse=True,
    )


# ── Adapters ─────────────────────────────────────────────────────────────────

def _get(row: Any, name: str, default: Any = None) -> Any:
    """Read `name` off a Mapping or an object. Duck-typed on purpose: callers
    hand us sqlite row dicts, dataclasses and Qt-side stubs alike."""
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _coerce_ts(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _tier_for(tiers: Optional[Mapping[str, str]], *keys: Any) -> Optional[str]:
    """First known tier among `keys`. None — not 'transient' — when unknown."""
    if not tiers:
        return None
    for key in keys:
        if key:
            found = tiers.get(str(key))
            if found:
                return str(found)
    return None


def claim_from_alert_row(
    row: Any, tiers: Optional[Mapping[str, str]] = None
) -> Claim:
    """Build a Claim from an `alert_fired` row (get_recent_alerts() shape).

    Tolerates a pre-v22 row: `confidence` is simply absent there, which maps to
    None and is neutral. Actionability comes from the CTA routing table — "does
    the app know where to send the user to fix this" is exactly the question,
    and the table already answers it per rule type.
    """
    from modules.alert_engine_routing import RULE_CTA

    rule_type = str(_get(row, "rule_type", "") or "")
    confidence = _get(row, "confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = None

    return Claim(
        ts=_coerce_ts(_get(row, "ts")),
        severity=str(_get(row, "severity", "") or ""),
        rule_type=rule_type,
        host=str(_get(row, "host", "") or ""),
        tier=_tier_for(tiers, _get(row, "host")),
        confidence=confidence,
        actionable=bool(RULE_CTA.get(rule_type)),
        acknowledged=_get(row, "acked_ts") is not None,
    )


# device_event has no severity column, so one is derived. Every value below is
# already in the app's vocabulary — this maps event types onto RULE-A3's set
# rather than inventing a parallel scale for the event stream.
_EVENT_SEVERITY = {
    "DOWN":      "CRITICAL",
    "LEFT":      "WARNING",
    "DEGRADED":  "WARNING",
    "JOINED":    "WARNING",   # an unexpected device joining is worth a look
    "UP":        "HEALTHY",
    "RECOVERED": "HEALTHY",
}


def claim_from_device_event(
    event: Any, tiers: Optional[Mapping[str, str]] = None
) -> Claim:
    """Build a Claim from a `device_event` row (DeviceEvent or dict).

    Keyed by IP when there is one and MAC otherwise — `record_device_event()`
    already falls back that way when a device has no address, so the tier
    lookup has to try both or a MAC-keyed event would always read as untiered.
    """
    ip = _get(event, "ip", "") or ""
    mac = _get(event, "mac", "") or ""
    kind = str(_get(event, "event_type", "") or "").upper()
    return Claim(
        ts=_coerce_ts(_get(event, "ts")),
        severity=_EVENT_SEVERITY.get(kind, "INFO"),
        rule_type=f"DEVICE_EVENT_{kind}" if kind else "DEVICE_EVENT",
        host=str(ip or mac),
        tier=_tier_for(tiers, ip, mac),
        confidence=None,          # the event stream has no evidence gate
        actionable=bool(ip or mac),
        acknowledged=False,       # device_event carries no ack concept
    )
