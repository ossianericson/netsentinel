"""
Device-type classifier.

Takes the data already available after a Module 1 scan — vendor string,
hostname, open ports, OS guess — and returns a concise human-readable
device-type label such as "IP Camera", "NAS", "Smart TV", or
"Domain Controller".

No network calls are made here; this is purely a classification step
over data that has already been collected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from modules.device_classifier_rules import _RULES


# ── Classification result type ────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    """
    Rich return type from classify_with_evidence().

    device_type   : Human-readable label e.g. "Smart TV", "Games Console".
    vendor        : Vendor string passed in (may be empty).
    confidence    : 0.0–1.0 estimate of classification quality.
    evidence      : Which discriminators fired e.g. ["vendor", "hostname:bravia"].
    mac_randomized: True when the U/L bit indicates a locally administered MAC.
    """
    device_type: str
    vendor: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    mac_randomized: bool = False


def is_randomized_mac(mac: str) -> bool:
    """
    Return True when the MAC's U/L bit (second-least-significant bit of the
    first octet) is set, indicating a locally administered / OS-randomised
    address rather than a genuine burnt-in OUI.

    Accepts any common MAC format: XX:XX:XX:XX:XX:XX, XX-XX-XX-XX-XX-XX,
    XXXXXXXXXXXX, or mixed case.
    """
    normalized = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(normalized) < 2:
        return False
    try:
        return bool(int(normalized[:2], 16) & 0x02)
    except ValueError:
        return False


# ── Public API ────────────────────────────────────────────────────────────────

_MESH_HOSTNAME_RE = re.compile(
    r"eero|deco|orbi|velop|halo|nova|nest.?wifi|google.?wifi|\bmesh\b",
    re.IGNORECASE,
)


def classify(
    vendor: str = "",
    hostname: str = "",
    open_ports: Optional[set[int]] = None,
    os_family: str = "",
    is_gateway: bool = False,
) -> str:
    """
    Return a human-readable device-type label.

    Parameters
    ----------
    vendor      Vendor / manufacturer string (from OUI or banner).
    hostname    Reverse-DNS hostname or NetBIOS name.
    open_ports  Set of open TCP port numbers.
    os_family   OS guess string, e.g. "Windows", "Linux/macOS".
    is_gateway  When True the device is known to be the network gateway —
                bypass OUI/hostname heuristics and return the router label
                directly.  Hostname is still checked for mesh-node patterns
                so a Deco/Eero gateway gets "Mesh Network Node" rather than
                the generic "Router / Gateway".

    Returns
    -------
    A label such as "IP Camera", "NAS Server", "Windows PC", or
    "Unknown Device" if no rule matches.
    """
    if open_ports is None:
        open_ports = set()

    # Gateway devices are definitively routers.  Bypass the OUI/hostname
    # classifier (which can be misled by chip-maker OUIs like Liteon) and
    # return the correct label immediately.
    if is_gateway:
        if _MESH_HOSTNAME_RE.search(hostname):
            return "Mesh Network Node"
        return "Router / Gateway"

    v = vendor.lower()
    h = hostname.lower()
    o = os_family.lower()

    for rule in _RULES:
        # Vendor match. vendor_re is corroboration, not a hard gate, when the
        # rule also carries hostname_re/os_re: those are strong enough
        # discriminators to stand on their own. iOS/Android randomise the
        # MAC by default, so vendor lookup returns "" on exactly the device
        # classes whose hostname rules exist -- a hostname that literally
        # reads "iPhone" must still classify correctly. any_ports-only rules
        # stay vendor-gated: ports alone are too broad a signal (80/443 open
        # says nothing about being a router without the vendor).
        if "vendor_re" in rule and not re.search(rule["vendor_re"], v):
            if not ("hostname_re" in rule or "os_re" in rule):
                continue

        # Hostname match
        if "hostname_re" in rule and not re.search(rule["hostname_re"], h):
            continue

        # OS match
        if "os_re" in rule and not re.search(rule["os_re"], o):
            continue

        # All-of ports
        if "ports" in rule and not rule["ports"].issubset(open_ports):
            continue

        # Any-of ports (primary)
        if "any_ports" in rule and not rule["any_ports"].intersection(open_ports):
            continue

        # Any-of ports (secondary — used in multi-any_ports rules like mail server)
        if "any_ports_b" in rule and not rule["any_ports_b"].intersection(open_ports):
            continue

        return rule["label"]

    return "Unknown Device"


def classify_with_evidence(
    vendor: str = "",
    hostname: str = "",
    open_ports: Optional[set[int]] = None,
    os_family: str = "",
    mac: str = "",
    is_gateway: bool = False,
    best_rule: bool = False,
) -> ClassificationResult:
    """
    Like classify() but returns a ClassificationResult with a confidence
    score and a list of which discriminators fired.

    Parameters
    ----------
    vendor      Vendor / manufacturer string (from OUI or banner).
    hostname    Reverse-DNS hostname or NetBIOS name.
    open_ports  Set of open TCP port numbers.
    os_family   OS guess string, e.g. "Windows", "Linux/macOS".
    mac         Raw MAC address; used to detect locally administered MACs.
    is_gateway  When True the device is known to be the network gateway —
                returns confidence=1.0 with evidence ["is_gateway"].
    best_rule   When True, return the HIGHEST-SCORING matching rule instead of
                the first one listed in _RULES. Off by default so the shipped
                path is unchanged; see the note below.

    Returns
    -------
    ClassificationResult — never None; falls back to device_type="Unknown Device".

    Note — why `best_rule` exists
    ----------------------------
    _RULES is a hand-ordered list and this function historically returned on the
    FIRST rule that matched, so precedence was *position in the list* rather than
    strength of evidence. Measured: a device matching the `{445, 548}` ports rule
    (0.20) and a vendor rule (0.40) returned the ports answer at 0.20, with the
    vendor evidence discarded entirely — a capability outranking an identity
    purely because the Servers block is written above the vendor block. With
    `best_rule=True` every matching rule is scored and the best one wins; an
    exact score tie still resolves to the earlier-listed rule, preserving the
    hand-ordered precedence where it was actually deliberate.
    """
    if open_ports is None:
        open_ports = set()

    mac_rand = is_randomized_mac(mac) if mac else False

    if is_gateway:
        label = (
            "Mesh Network Node" if _MESH_HOSTNAME_RE.search(hostname)
            else "Router / Gateway"
        )
        return ClassificationResult(
            device_type=label,
            vendor=vendor,
            confidence=1.0,
            evidence=["is_gateway"],
            mac_randomized=mac_rand,
        )
    v = vendor.lower()
    h = hostname.lower()
    o = os_family.lower()

    best: Optional[ClassificationResult] = None

    for rule in _RULES:
        # Precompute which discriminators match for this rule
        v_match = bool(v and "vendor_re" in rule and re.search(rule["vendor_re"], v))
        h_match = bool(h and "hostname_re" in rule and re.search(rule["hostname_re"], h))
        o_match = bool(o and "os_re" in rule and re.search(rule["os_re"], o))
        p_match = bool("ports" in rule and rule["ports"].issubset(open_ports))
        ap_match = bool("any_ports" in rule and rule["any_ports"].intersection(open_ports))

        # Mirror the gating logic from classify() exactly
        if "vendor_re" in rule and not v_match:
            if not ("hostname_re" in rule or "os_re" in rule):
                continue
        if "hostname_re" in rule and not h_match:
            continue
        if "os_re" in rule and not o_match:
            continue
        if "ports" in rule and not p_match:
            continue
        if "any_ports" in rule and not ap_match:
            continue
        if "any_ports_b" in rule and not rule["any_ports_b"].intersection(open_ports):
            continue

        # Rule matched — build evidence list and compute confidence
        evidence: list[str] = []
        confidence = 0.0

        if v_match:
            # Vendor match is worth less when the MAC may be randomised
            boost = 0.20 if mac_rand else 0.40
            label = "vendor(randomized-mac-penalty)" if mac_rand else "vendor"
            evidence.append(label)
            confidence += boost
        if h_match:
            evidence.append(f"hostname:{hostname[:40]}")
            confidence += 0.30
        if o_match:
            evidence.append(f"os:{os_family}")
            confidence += 0.15
        if p_match:
            evidence.append(f"ports:{sorted(rule['ports'])}")
            confidence += 0.20
        if ap_match:
            matched_p = rule["any_ports"].intersection(open_ports)
            evidence.append(f"any-ports:{sorted(matched_p)}")
            confidence += 0.15
        if mac_rand:
            evidence.append("randomized-mac")

        matched = ClassificationResult(
            device_type=rule["label"],
            vendor=vendor,
            confidence=min(1.0, confidence),
            evidence=evidence,
            mac_randomized=mac_rand,
        )
        if not best_rule:
            return matched
        # `>` not `>=`: an exact tie keeps the earlier-listed rule, so the
        # hand-ordered precedence still decides where it was deliberate.
        if best is None or matched.confidence > best.confidence:
            best = matched

    if best is not None:
        return best

    fallback_evidence: list[str] = ["no-rule-matched"]
    if mac_rand:
        fallback_evidence.append("randomized-mac")
    return ClassificationResult(
        device_type="Unknown Device",
        vendor=vendor,
        confidence=0.0,
        evidence=fallback_evidence,
        mac_randomized=mac_rand,
    )


def classify_from_observation(obs: object) -> ClassificationResult:
    """
    Return a ClassificationResult derived directly from a PassiveObservation.

    The observation's device_hint is already a resolved label (produced by the
    SSDP/mDNS classification tables), so we wrap it without further heuristics.
    Confidence is mapped from the string flag: "high" → 0.85, "low" → 0.40.
    """
    hint = getattr(obs, "device_hint", "") or ""
    confidence_str = getattr(obs, "confidence", "low")
    protocol = getattr(obs, "protocol", "")
    service_type = getattr(obs, "service_type", "")

    if not hint:
        return ClassificationResult(
            device_type="Unknown Device",
            confidence=0.0,
            evidence=[f"passive-{protocol}:no-hint"],
        )

    confidence = 0.85 if confidence_str == "high" else 0.40
    evidence = [f"passive-{protocol}:{service_type}"]
    return ClassificationResult(
        device_type=hint,
        confidence=confidence,
        evidence=evidence,
    )


def get_all_device_types() -> list:
    """Return sorted list of all valid device type labels for the UI dropdown."""
    types: set = {rule["label"] for rule in _RULES}
    types.update(["Router / Gateway", "Mesh Network Node", "Unknown Device"])
    return sorted(types)


def classify_registry_first(
    mac: str = "",
    vendor: str = "",
    hostname: str = "",
    open_ports: Optional[set[int]] = None,
    os_family: str = "",
    is_gateway: bool = False,
) -> str:
    """
    Unified registry-first classification entry point.

    Consults modules.mac_registry.lookup(mac) first — its OUI database is
    product-specific and more accurate when the MAC is present — and falls
    back to the heuristic classify() otherwise. Codifies the precedence
    modules.name_resolver.resolve() already applies for vendor/model lookups.
    """
    if mac:
        from modules.mac_registry import lookup as _mac_lookup
        device_type = _mac_lookup(mac).get("device_type", "")
        if device_type:
            return device_type
    return classify(
        vendor=vendor, hostname=hostname, open_ports=open_ports,
        os_family=os_family, is_gateway=is_gateway,
    )


def classify_device(device, is_gateway: bool = False) -> str:
    """
    Convenience wrapper that accepts a DeviceInfo dataclass instance or a
    plain dict (as returned by Module 1) and calls classify().
    """
    if isinstance(device, dict):
        vendor    = device.get("vendor", "")
        hostname  = device.get("hostname", "")
        os_family = device.get("os_family", "")
        ports     = set(device.get("open_ports", []))
    else:
        vendor    = getattr(device, "vendor",    "")
        hostname  = getattr(device, "hostname",  "")
        os_family = getattr(device, "os_family", "")
        ports     = set(getattr(device, "open_ports", []) or [])

    return classify(vendor=vendor, hostname=hostname,
                    open_ports=ports, os_family=os_family,
                    is_gateway=is_gateway)
