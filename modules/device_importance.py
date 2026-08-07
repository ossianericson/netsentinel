"""
device_importance — does this device matter?

The second gate of the Signal Quality Program, and the replacement for a binary
check that was measurably wrong. `MetricStore.is_device_alert_in_scope()` admits
a device to all ten device-scoped alert rules when
`inferred_role in ("gateway", "infrastructure")`. On the reference network that
single boolean admitted **53.4 % of every candidate alert** — and it was wrong
for 8 of its 13 role assignments:

  * a PS4, a Chromecast, a Lexmark printer, three unidentifiable privacy MACs
    and the SSDP multicast group `239.255.255.250` all held `infrastructure`;
  * the real mesh AP — OUI-registered as
    `Google Nest / Nest Wifi / Google Wifi Router` — held **no role at all**,
    because the classifier had labelled it a "Video Doorbell".

So the fix cannot be "raise the promotion threshold". The two things the old
rule treated as evidence are both unreliable:

  * **`device_type`** is a heuristic guess. It called an iPad a "Domain
    Controller" and a mesh router a doorbell. It is a hint, never a warrant.
  * **"always on and never changed IP"** describes every printer, streaming
    stick, games console and sleeping IoT bulb on a home network. It is a
    statement about uptime, not about function.

This module therefore ranks devices by *corroborated* evidence — OUI-registered
vendor identity, an explicit role that survived the same corroboration, and
explicit user intent — into four tiers, so an alert rule can require a floor
(`AlertRule.min_tier`) instead of consulting one overloaded boolean.

Two invariants are load-bearing:

  1. **Inference can never outrun identity.** An `ANONYMOUS` or `NOT_A_DEVICE`
     identity is not promotable to INFRASTRUCTURE or CRITICAL, no matter what a
     stored `inferred_role` says. This is what stops a stale role written by the
     old logic from surviving into the new gate.
  2. **Explicit user intent is not inference and is not subject to (1).**
     `alert_opt_in` is the user saying "alert me about this device"; honouring
     the identity gate there would silently revoke an opt-in they already made
     — a regression, not a fix. `is_pinned` is different: pinning is a *display*
     preference for the device map, so it only lifts a device the app can
     actually name. `NOT_A_DEVICE` is capped at TRANSIENT regardless of either,
     because no user intent makes a multicast group a host.

Pure Python — no PyQt, no DB access (ARCH RULE 1). Tiers are recomputed from
the current row on every call and never read from a stored column, because the
stored values this module replaces are known to be wrong.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from functools import total_ordering
from typing import Any, Mapping, Optional, Union

from modules.device_identity import (
    Identity,
    IdentityClass,
    classify_identity,
    is_promotable_to_infrastructure,
)

__all__ = [
    "Tier",
    "Importance",
    "classify_importance",
    "classify_known_device",
    "tier_from_name",
    "vendor_suggests_infrastructure",
    "device_type_suggests_edge_infrastructure",
]


# ── Tier ─────────────────────────────────────────────────────────────────────

# Ordering, lowest first. Kept separate from the Enum body so `rank` is a plain
# index lookup rather than relying on definition order.
_TIER_ORDER = ("transient", "personal", "infrastructure", "critical")


@total_ordering
class Tier(Enum):
    """How much the app is allowed to care about a device.

    Values are stable lowercase strings, not `auto()` integers: they are written
    to `AlertRule.min_tier`, compared across restarts, and will be persisted to
    `known_device.importance_tier` by the Phase 6 migration.
    """

    TRANSIENT = "transient"            # a guest phone, a one-off scan hit
    PERSONAL = "personal"              # someone's identified, long-lived device
    INFRASTRUCTURE = "infrastructure"  # NAS, server, switch, user-pinned
    CRITICAL = "critical"              # gateway, modem, mesh AP

    @property
    def rank(self) -> int:
        return _TIER_ORDER.index(self.value)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Tier):
            return NotImplemented
        return self.rank < other.rank


def tier_from_name(name: Optional[str]) -> Optional[Tier]:
    """Parse a tier name leniently. Returns None for anything unrecognised.

    Callers treat None as "unspecified" and fall back to their own default,
    so a typo in a persisted `min_tier` degrades to the default floor rather
    than raising out of the alert hot path.
    """
    if not name:
        return None
    try:
        return Tier(name.strip().lower())
    except ValueError:
        return None


@dataclass(frozen=True)
class Importance:
    """The verdict for one device, with the evidence that produced it."""

    tier: Tier
    reason: str
    source: str  # "override" | "user" | "inferred"


# ── Evidence vocabulary ──────────────────────────────────────────────────────

# Vendor strings come from the OUI registry — a hardware manufacturer's
# registered assignment — which is why they are trusted here while `device_type`
# is not. Every token below names a networking *product class*, not a brand that
# also sells consumer electronics: "Google" alone must never match (the
# reference network has a Google streaming stick), but
# "Google Nest / Nest Wifi / Google Wifi Router" must.
#
# Word-boundary anchored deliberately. A bare substring test for "deco" or
# "eero" inside an arbitrary vendor string is exactly the kind of loose match
# that produced the defect this module exists to fix.
_INFRA_VENDOR_RE = re.compile(
    r"\b(?:"
    r"access\s*point|wireless\s+ap|wi-?fi\s+router|wireless\s+router|"
    r"nest\s+wifi|google\s+wifi|deco|eero|orbi|unifi|ubiquiti|mikrotik|"
    r"aruba|ruckus|meraki|edgerouter|draytek|zyxel|fritz!?box|openwrt|"
    r"sonicwall|fortinet|watchguard|netgate|cambium|engenius|"
    r"range\s+extenders?|extenders?|repeaters?|routers?|firewalls?|modems?"
    r")\b",
    re.IGNORECASE,
)

# device_type values that describe the network edge itself. Used only to split
# CRITICAL from INFRASTRUCTURE once some *other* signal has already justified
# promotion — never as the promotion evidence on its own.
_EDGE_INFRA_TYPES = frozenset({
    "router", "gateway", "modem", "access point", "wireless ap",
    "mesh network node", "mesh node", "firewall",
})

# Roles that survived corroborated inference in device_stability.infer_role().
_INFRA_ROLES = frozenset({"infrastructure", "server"})

# PERSONAL is "an identified device that has been around" — deliberately loose
# on stability, because phones and laptops legitimately roam across DHCP leases
# (the reference network's iPhone sits at 0.71) and are still someone's device.
_PERSONAL_MIN_SCANS = 10
_PERSONAL_MIN_STABILITY = 0.5

_PLACEHOLDERS = frozenset({
    "", "-", "?", "n/a", "na", "none", "null",
    "unknown", "unknown device", "unknown vendor",
})


def _meaningful(value: Optional[str]) -> bool:
    """True when `value` is a real handle rather than a scanner placeholder."""
    if not value:
        return False
    return value.strip().lower() not in _PLACEHOLDERS


def _type_matches(device_type: Optional[str], types: frozenset) -> bool:
    """Word-boundary aware membership test — stops 'ap' matching 'laptop'."""
    padded = f" {(device_type or '').strip().lower()} "
    return any(f" {t} " in padded for t in types)


def vendor_suggests_infrastructure(vendor: Optional[str]) -> bool:
    """True when an OUI-registered vendor string names a networking product.

    This is the corroborating signal that rescues the mesh AP the `device_type`
    classifier mislabelled, and the reason role inference no longer needs to
    guess from uptime.
    """
    if not _meaningful(vendor):
        return False
    return _INFRA_VENDOR_RE.search(vendor or "") is not None


def device_type_suggests_edge_infrastructure(device_type: Optional[str]) -> bool:
    """True when the classifier's guess names the network edge (router/AP/modem)."""
    return _type_matches(device_type, _EDGE_INFRA_TYPES)


# ── Classification ───────────────────────────────────────────────────────────

def _resolve_identity(
    mac: Optional[str],
    hostname: Optional[str],
    vendor: Optional[str],
    ip: Optional[str],
    mac_randomized: bool,
) -> Identity:
    """Identity for this row, reinforced by the stored `mac_randomized` column.

    `classify_identity()` derives randomisation from the MAC's U/L bit, which is
    the better source when the MAC is intact. The stored column (populated by
    DeviceTracker from Phase 1 onward) is what remains when it is not — a row
    whose MAC is missing or garbled but which is known to carry no OUI has no
    handle at all, and must not be treated as nameable.
    """
    identity = classify_identity(mac, hostname, vendor, ip)
    if identity.identity_class is IdentityClass.NOT_A_DEVICE:
        return identity
    if (
        mac_randomized
        and not _meaningful(hostname)
        and not _meaningful(vendor)
        and identity.identity_class is not IdentityClass.ANONYMOUS
    ):
        return Identity(
            IdentityClass.ANONYMOUS,
            "known-randomised MAC with no hostname or vendor",
            True,
        )
    return identity


def classify_importance(
    *,
    mac: Optional[str] = None,
    ip: Optional[str] = None,
    hostname: Optional[str] = None,
    vendor: Optional[str] = None,
    device_type: Optional[str] = None,
    inferred_role: Optional[str] = None,
    scan_count: int = 0,
    ip_stability: float = 0.0,
    custom_name: Optional[str] = None,
    is_pinned: bool = False,
    mac_randomized: bool = False,
    alert_opt_in: bool = False,
    override: Optional[Union[Tier, str]] = None,
) -> Importance:
    """Rank one device.

    Every argument maps to an existing `known_device` column, so no schema
    change is needed to tier the whole inventory. Malformed MACs and IPs are
    classified, not rejected — this runs on the alert evaluation path, where a
    raise would be worse than a conservative answer. Numeric arguments are
    trusted; use `classify_known_device()` to coerce a raw row.
    """
    identity = _resolve_identity(mac, hostname, vendor, ip, bool(mac_randomized))

    # ── 1. Not an endpoint — nothing below can apply ─────────────────────────
    if identity.identity_class is IdentityClass.NOT_A_DEVICE:
        return Importance(Tier.TRANSIENT, identity.reason, "inferred")

    # ── 2. Explicit override ─────────────────────────────────────────────────
    forced: Optional[Tier] = None
    if isinstance(override, Tier):
        forced = override
    elif isinstance(override, str):
        forced = tier_from_name(override)
    if forced is not None:
        return Importance(forced, "explicit user override", "override")

    inferred = _infer_tier(
        identity=identity,
        vendor=vendor,
        device_type=device_type,
        inferred_role=inferred_role,
        scan_count=scan_count,
        ip_stability=ip_stability,
        custom_name=custom_name,
        is_pinned=is_pinned,
    )

    # ── 3. Explicit alert opt-in — user intent, so it is a FLOOR, not a value.
    # It never demotes a gateway, and it is deliberately not subject to the
    # identity gate: the user already asked for these alerts.
    if alert_opt_in and inferred.tier < Tier.INFRASTRUCTURE:
        return Importance(
            Tier.INFRASTRUCTURE, "user opted this device in to alerts", "user"
        )
    return inferred


def _infer_tier(
    *,
    identity: Identity,
    vendor: Optional[str],
    device_type: Optional[str],
    inferred_role: Optional[str],
    scan_count: int,
    ip_stability: float,
    custom_name: Optional[str],
    is_pinned: bool,
) -> Importance:
    """The inference half — everything the identity gate constrains."""
    promotable = is_promotable_to_infrastructure(identity)

    # ── CRITICAL / INFRASTRUCTURE — only for a device we can name ────────────
    if promotable:
        if (inferred_role or "").lower() == "gateway":
            return Importance(Tier.CRITICAL, "inferred role: gateway", "inferred")
        if vendor_suggests_infrastructure(vendor):
            return Importance(
                Tier.CRITICAL,
                f"vendor identifies networking hardware: {vendor}",
                "inferred",
            )
        if device_type_suggests_edge_infrastructure(device_type) and (
            (inferred_role or "").lower() in _INFRA_ROLES
        ):
            return Importance(
                Tier.CRITICAL, f"network edge device: {device_type}", "inferred"
            )
        if (inferred_role or "").lower() in _INFRA_ROLES:
            return Importance(
                Tier.INFRASTRUCTURE, f"inferred role: {inferred_role}", "inferred"
            )
        if is_pinned:
            return Importance(Tier.INFRASTRUCTURE, "pinned by the user", "user")

    # ── PERSONAL — identified, and either named or long-lived ────────────────
    if identity.identity_class is IdentityClass.IDENTIFIED:
        if _meaningful(custom_name):
            return Importance(Tier.PERSONAL, "named by the user", "user")
        if scan_count >= _PERSONAL_MIN_SCANS and ip_stability >= _PERSONAL_MIN_STABILITY:
            return Importance(
                Tier.PERSONAL,
                f"identified and long-lived ({scan_count} scans, "
                f"{ip_stability:.0%} IP stability)",
                "inferred",
            )

    return Importance(Tier.TRANSIENT, identity.reason, "inferred")


def classify_known_device(row: Union[Mapping[str, Any], Any]) -> Importance:
    """Convenience wrapper for a `known_device` row (KnownDevice or dict).

    Duck-typed on purpose: `modules/` must not import the MetricStore schema
    just to read seven attributes off a record it was handed.
    """
    def get(name: str, default: Any = None) -> Any:
        if isinstance(row, Mapping):
            return row.get(name, default)
        return getattr(row, name, default)

    return classify_importance(
        mac=get("mac"),
        ip=get("ip"),
        hostname=get("hostname"),
        vendor=get("vendor"),
        device_type=get("device_type"),
        inferred_role=get("inferred_role"),
        scan_count=int(get("scan_count", 0) or 0),
        ip_stability=float(get("ip_stability", 0.0) or 0.0),
        custom_name=get("custom_name"),
        is_pinned=bool(get("is_pinned", False)),
        mac_randomized=bool(get("mac_randomized", False)),
        alert_opt_in=bool(get("alert_opt_in", False)),
    )
