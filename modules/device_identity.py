"""
device_identity — what NetSentinel is allowed to say a thing *is*.

The first gate of the Signal Quality Program. Everything downstream (importance
tiering, alert eligibility, inventory display) depends on two questions this
module answers, and both were previously unasked:

  1. **Is this a device at all?** A multicast destination address is not an
     endpoint. The reference database carried `01:00:5e:7f:ff:fa` /
     `239.255.255.250` — the SSDP multicast group — as a `known_device` row that
     had been promoted to `inferred_role=infrastructure`, which is the gate
     `is_device_alert_in_scope()` uses. A non-existent host was therefore opted
     in to all ten device-scoped alert rules.

  2. **Can we name it?** 8 of 30 devices on that network carry a randomised
     (locally-administered) MAC. They are *stable* — 483-606 scans, 0.71-0.88 IP
     stability — so the problem is not MAC rotation, it is that five of them have
     no hostname and no vendor. Three had likewise been promoted to
     infrastructure.

A randomised MAC is **not** by itself grounds to call a device anonymous: iOS and
Android randomise per-SSID and then keep that address, so `Ossians-iPhone-2022`
is both randomised and perfectly identifiable. Anonymity requires a randomised
MAC *and* the absence of any other handle.

Pure Python — no PyQt, no DB access (ARCH RULE 1). The U/L bit test is imported
from `device_classifier` rather than re-derived; there were already two copies of
that arithmetic in the tree and a third would be one more thing to drift.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from modules.device_classifier import is_randomized_mac

__all__ = [
    "IdentityClass",
    "Identity",
    "classify_identity",
    "is_promotable_to_infrastructure",
]

# Strings that scanners and enrichment write to mean "I don't know". Treating any
# of these as a real name defeats the whole check — the reference database stores
# the literal "Unknown" as the vendor for every privacy-MAC device.
_PLACEHOLDER_VALUES = frozenset({
    "", "-", "?", "n/a", "na", "none", "null",
    "unknown", "unknown device", "unknown vendor",
})

# Limited broadcast. The stdlib exposes is_multicast but has no is_broadcast for
# a bare address, so this one is checked explicitly.
_IPV4_BROADCAST = ipaddress.IPv4Address("255.255.255.255")

_MAC_HEX_LEN = 12


class IdentityClass(Enum):
    """How confidently the app can speak about a thing.

    Values are stable lowercase strings because they are persisted to
    `known_device.importance_source` and compared across restarts.
    """

    IDENTIFIED = "identified"      # has a usable handle: OUI, hostname or vendor
    ANONYMOUS = "anonymous"        # a real device we cannot name
    NOT_A_DEVICE = "not_a_device"  # multicast/broadcast/malformed — not an endpoint


@dataclass(frozen=True)
class Identity:
    """The verdict for one observed address."""

    identity_class: IdentityClass
    reason: str
    is_randomized: bool = False

    @property
    def is_real_device(self) -> bool:
        return self.identity_class is not IdentityClass.NOT_A_DEVICE

    @property
    def is_nameable(self) -> bool:
        return self.identity_class is IdentityClass.IDENTIFIED


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalise_mac(mac: Optional[str]) -> str:
    """Lowercase hex digits only. Returns '' for anything unusable."""
    if not mac:
        return ""
    stripped = mac.replace(":", "").replace("-", "").replace(".", "").strip().lower()
    return stripped if stripped else ""


def _first_octet(mac_hex: str) -> Optional[int]:
    """The first octet as an int, or None when the MAC is not parseable."""
    if len(mac_hex) < 2:
        return None
    try:
        return int(mac_hex[:2], 16)
    except ValueError:
        return None


def _is_meaningful(value: Optional[str]) -> bool:
    """True when `value` is a real handle rather than a placeholder."""
    if not value:
        return False
    return value.strip().lower() not in _PLACEHOLDER_VALUES


def _non_host_ip_reason(ip: Optional[str]) -> Optional[str]:
    """Why `ip` cannot belong to a single host, or None when it can."""
    if not ip or not ip.strip():
        return None
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None  # not parseable as an IP — judge on the MAC alone
    if addr.is_multicast:
        return f"{ip} is a multicast group address, not a host"
    if addr == _IPV4_BROADCAST:
        return f"{ip} is the limited broadcast address, not a host"
    return None


# ── Public API ───────────────────────────────────────────────────────────────

def classify_identity(
    mac: Optional[str],
    hostname: Optional[str] = None,
    vendor: Optional[str] = None,
    ip: Optional[str] = None,
) -> Identity:
    """Classify one observed address. Never raises — called from the scan hot path.

    Checks run in a deliberate order: "is it an endpoint at all" precedes "can we
    name it", because some addresses set both bits. `33:33:00:00:00:01` (IPv6
    multicast) has the group bit *and* the locally-administered bit set, and must
    resolve as NOT_A_DEVICE rather than as an anonymous device.
    """
    mac_hex = _normalise_mac(mac)
    randomized = is_randomized_mac(mac or "")

    # ── 1. Not an endpoint ───────────────────────────────────────────────────
    if not mac_hex:
        return Identity(IdentityClass.NOT_A_DEVICE, "no MAC address", randomized)

    octet = _first_octet(mac_hex)
    if octet is None or len(mac_hex) != _MAC_HEX_LEN:
        return Identity(
            IdentityClass.NOT_A_DEVICE, f"malformed MAC address {mac!r}", randomized
        )

    if set(mac_hex) == {"0"}:
        return Identity(IdentityClass.NOT_A_DEVICE, "all-zero MAC address", randomized)

    if octet & 0x01:
        # I/G bit: the frame is destined for a group, so no single host owns it.
        return Identity(
            IdentityClass.NOT_A_DEVICE,
            f"{mac} is a multicast/broadcast MAC, not a host",
            randomized,
        )

    ip_reason = _non_host_ip_reason(ip)
    if ip_reason is not None:
        return Identity(IdentityClass.NOT_A_DEVICE, ip_reason, randomized)

    # ── 2. A real device — can we name it? ───────────────────────────────────
    named = _is_meaningful(hostname)
    vendored = _is_meaningful(vendor)

    if randomized and not named and not vendored:
        # A privacy MAC carries no OUI, so with no hostname and no vendor there
        # is nothing left to identify it by.
        return Identity(
            IdentityClass.ANONYMOUS,
            "randomised MAC with no hostname or vendor",
            True,
        )

    if randomized:
        handle = "hostname" if named else "vendor"
        return Identity(
            IdentityClass.IDENTIFIED, f"randomised MAC identified by {handle}", True
        )

    return Identity(
        IdentityClass.IDENTIFIED, "globally-administered MAC (OUI-backed)", False
    )


def is_promotable_to_infrastructure(identity: Identity) -> bool:
    """True when this identity may be inferred as gateway/infrastructure.

    Infrastructure role is the alert-eligibility gate in
    `MetricStore.is_device_alert_in_scope()`, so promoting something the app
    cannot even name opts an unnameable thing into every device-scoped rule.
    Only an IDENTIFIED device is eligible; role inference still has to justify
    the promotion on its own evidence beyond this check.
    """
    return identity.identity_class is IdentityClass.IDENTIFIED
