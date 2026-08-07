"""
Tests for modules/device_importance.py — does this device matter?

Written test-first (RULE-TDD1). Phase 2 of the Signal Quality Program replaces
the binary alert-eligibility check (`inferred_role in ("gateway",
"infrastructure")`) with a four-level tier, because the binary check admitted
53.4% of all candidate alerts on the reference network and was wrong for 8 of
its 13 role assignments.

Every "reference network" case below is a real row from the measured database
documented in docs/spikes/signal-quality-baseline.md — including the vendor
strings verbatim, because the whole point of Phase 2 is that the app must stop
trusting `device_type` (which called a Google Nest Wifi router a "Video
Doorbell" and an iPad a "Domain Controller") and start requiring corroboration.
"""
from __future__ import annotations

import pytest

from modules.device_importance import (
    Importance,
    Tier,
    classify_importance,
    tier_from_name,
    vendor_suggests_infrastructure,
)


# ── Tier ordering ────────────────────────────────────────────────────────────

def test_tiers_are_ordered_critical_highest():
    assert Tier.CRITICAL > Tier.INFRASTRUCTURE > Tier.PERSONAL > Tier.TRANSIENT


def test_tier_comparison_is_usable_as_a_min_tier_floor():
    assert Tier.CRITICAL >= Tier.INFRASTRUCTURE
    assert not (Tier.PERSONAL >= Tier.INFRASTRUCTURE)
    assert Tier.PERSONAL >= Tier.PERSONAL


def test_tier_values_are_stable_lowercase_strings():
    # Persisted and compared across restarts — must not become auto() ints.
    assert Tier.CRITICAL.value == "critical"
    assert Tier.INFRASTRUCTURE.value == "infrastructure"
    assert Tier.PERSONAL.value == "personal"
    assert Tier.TRANSIENT.value == "transient"


@pytest.mark.parametrize("name", ["critical", "CRITICAL", " Critical ", "personal"])
def test_tier_from_name_round_trips(name):
    assert tier_from_name(name) is Tier[name.strip().upper()]


@pytest.mark.parametrize("name", ["", None, "important", "gateway"])
def test_tier_from_name_returns_none_for_unknown(name):
    assert tier_from_name(name) is None


# ── Identity gate: the constraint the whole program rests on ─────────────────

def test_multicast_group_is_never_more_than_transient():
    """01:00:5e:7f:ff:fa / 239.255.255.250 held inferred_role=infrastructure in
    the live database. It is not a host; no stored role and no user opt-in may
    lift it above TRANSIENT."""
    imp = classify_importance(
        mac="01:00:5e:7f:ff:fa",
        ip="239.255.255.250",
        inferred_role="infrastructure",
        scan_count=654,
        ip_stability=1.0,
        alert_opt_in=True,
        is_pinned=True,
        custom_name="definitely a router",
    )
    assert imp.tier is Tier.TRANSIENT


def test_anonymous_device_cannot_be_inferred_above_transient():
    """A randomised MAC with no hostname and no vendor is unidentifiable. Three
    such devices carried inferred_role=infrastructure on the reference network;
    a stale role must not survive the identity gate."""
    imp = classify_importance(
        mac="6a:34:64:72:f8:f0",
        ip="192.168.68.56",
        vendor="Unknown",
        device_type="Unknown Device",
        inferred_role="infrastructure",
        scan_count=592,
        ip_stability=0.78,
    )
    assert imp.tier is Tier.TRANSIENT


def test_anonymous_device_cannot_reach_infrastructure_by_pinning():
    """Pinning is a display preference, not a claim about function."""
    imp = classify_importance(
        mac="02:a8:f1:3b:93:40",
        vendor="Unknown",
        inferred_role="infrastructure",
        is_pinned=True,
        scan_count=568,
        ip_stability=0.79,
    )
    assert imp.tier < Tier.INFRASTRUCTURE


def test_stored_mac_randomized_flag_forces_anonymous_when_no_handle():
    """known_device.mac_randomized is populated from Phase 1 onward. When the
    MAC string itself is unusable, the stored column is the only evidence left
    that this address carries no OUI."""
    imp = classify_importance(
        mac="",
        ip="192.168.68.99",
        mac_randomized=True,
        inferred_role="infrastructure",
        scan_count=500,
        ip_stability=0.95,
    )
    assert imp.tier is Tier.TRANSIENT


# ── CRITICAL: gateway, modem, mesh AP ────────────────────────────────────────

def test_gateway_role_is_critical():
    """The TP-Link Deco at 192.168.68.1 — the one correct role assignment on
    the reference network."""
    imp = classify_importance(
        mac="3c:64:cf:e0:27:02",
        ip="192.168.68.1",
        vendor="TP-Link (Deco mesh / RE series extenders)",
        device_type="Mesh Network Node",
        inferred_role="gateway",
        scan_count=662,
        ip_stability=1.0,
    )
    assert imp.tier is Tier.CRITICAL


def test_google_nest_wifi_router_is_critical_despite_wrong_device_type():
    """ACCEPTANCE CRITERION 2. The real mesh AP was classified "Video Doorbell"
    and carried no role at all. Its OUI-registered vendor string is the
    corroborating evidence device_type failed to provide."""
    imp = classify_importance(
        mac="f0:72:ea:51:d3:b8",
        ip="192.168.68.64",
        vendor="Google Nest / Nest Wifi / Google Wifi Router",
        device_type="Video Doorbell",
        inferred_role=None,
        scan_count=6,
        ip_stability=0.67,
    )
    assert imp.tier is Tier.CRITICAL


def test_infrastructure_role_with_edge_device_type_is_critical():
    imp = classify_importance(
        mac="aa:bb:cc:dd:ee:01",
        ip="192.168.1.2",
        vendor="Ubiquiti Networks",
        device_type="Access Point",
        inferred_role="infrastructure",
    )
    assert imp.tier is Tier.CRITICAL


# ── INFRASTRUCTURE: NAS, server, switch, user-pinned ─────────────────────────

def test_server_role_is_infrastructure_not_critical():
    imp = classify_importance(
        mac="aa:bb:cc:dd:ee:02",
        ip="192.168.1.10",
        vendor="Synology",
        device_type="NAS",
        inferred_role="server",
        scan_count=400,
        ip_stability=0.99,
    )
    assert imp.tier is Tier.INFRASTRUCTURE


def test_pinned_identified_device_is_infrastructure():
    imp = classify_importance(
        mac="aa:bb:cc:dd:ee:03",
        ip="192.168.1.11",
        hostname="workbench",
        vendor="Intel Corporate",
        is_pinned=True,
    )
    assert imp.tier is Tier.INFRASTRUCTURE
    assert imp.source == "user"


def test_alert_opt_in_floors_the_tier_at_infrastructure():
    """The user explicitly asked for alerts on this device. Enabling the tier
    gate must not silently revoke an opt-in they already made."""
    imp = classify_importance(
        mac="5c:93:a2:5c:47:19",
        ip="192.168.68.69",
        hostname="PS4-C8208A",
        vendor="Liteon Technology Corporation",
        device_type="Games Console",
        alert_opt_in=True,
        scan_count=588,
        ip_stability=0.99,
    )
    assert imp.tier is Tier.INFRASTRUCTURE
    assert imp.source == "user"


def test_alert_opt_in_survives_the_identity_gate():
    """The identity gate constrains *inference*. An opt-in is the user speaking,
    and gating it would silently revoke an opt-in they already made on an
    unnameable device — a regression, not a fix."""
    imp = classify_importance(
        mac="6a:34:64:72:f8:f0",
        ip="192.168.68.56",
        vendor="Unknown",
        alert_opt_in=True,
    )
    assert imp.tier is Tier.INFRASTRUCTURE


def test_alert_opt_in_never_demotes_a_gateway():
    """It is a floor, not a fixed value."""
    imp = classify_importance(
        mac="3c:64:cf:e0:27:02",
        ip="192.168.68.1",
        vendor="TP-Link (Deco mesh / RE series extenders)",
        inferred_role="gateway",
        alert_opt_in=True,
    )
    assert imp.tier is Tier.CRITICAL


def test_alert_opt_in_cannot_lift_a_multicast_group():
    imp = classify_importance(
        mac="01:00:5e:7f:ff:fa", ip="239.255.255.250", alert_opt_in=True,
    )
    assert imp.tier is Tier.TRANSIENT


def test_explicit_override_wins_over_inference():
    imp = classify_importance(
        mac="aa:bb:cc:dd:ee:04",
        ip="192.168.1.12",
        hostname="printer",
        vendor="Brother",
        inferred_role="printer",
        override=Tier.CRITICAL,
    )
    assert imp.tier is Tier.CRITICAL
    assert imp.source == "override"


def test_explicit_override_accepts_a_tier_name_string():
    imp = classify_importance(
        mac="aa:bb:cc:dd:ee:05", ip="192.168.1.13", vendor="Brother",
        override="transient",
    )
    assert imp.tier is Tier.TRANSIENT


# ── PERSONAL: identified and long-lived, or user-named ───────────────────────

def test_ps4_is_no_higher_than_personal():
    """ACCEPTANCE CRITERION 2 — carried inferred_role=infrastructure."""
    imp = classify_importance(
        mac="5c:93:a2:5c:47:19",
        ip="192.168.68.69",
        hostname="PS4-C8208A",
        vendor="Liteon Technology Corporation",
        device_type="Games Console",
        scan_count=588,
        ip_stability=0.99,
    )
    assert imp.tier is Tier.PERSONAL


def test_chromecast_is_no_higher_than_personal():
    """ACCEPTANCE CRITERION 2. Also the top state-churn source in the baseline
    (306 events from one device) — exactly what must stop reaching the gate."""
    imp = classify_importance(
        mac="54:60:09:ee:10:2a",
        ip="192.168.68.54",
        vendor="Google Chromecast / Google Home / Cast Audio",
        device_type="Streaming Stick",
        scan_count=654,
        ip_stability=0.71,
    )
    assert imp.tier is Tier.PERSONAL


def test_lexmark_printer_is_no_higher_than_personal():
    """ACCEPTANCE CRITERION 2 — carried inferred_role=infrastructure."""
    imp = classify_importance(
        mac="00:21:b7:a3:09:1a",
        ip="192.168.68.57",
        hostname="ET0021B7A3091A",
        vendor="Lexmark International, Inc.",
        device_type="Unknown Device",
        inferred_role="printer",
        scan_count=662,
        ip_stability=0.87,
    )
    assert imp.tier is Tier.PERSONAL


def test_user_named_device_is_personal_even_when_rarely_seen():
    imp = classify_importance(
        mac="aa:bb:cc:dd:ee:06",
        ip="192.168.1.20",
        vendor="Apple, Inc.",
        custom_name="Dad's iPad",
        scan_count=1,
        ip_stability=0.1,
    )
    assert imp.tier is Tier.PERSONAL


def test_identified_but_unstable_newcomer_is_transient():
    imp = classify_importance(
        mac="1c:ce:51:98:dd:1c",
        vendor="AzureWave Technology Inc.",
        scan_count=1,
        ip_stability=1.0,
    )
    assert imp.tier is Tier.TRANSIENT


def test_identified_but_low_stability_long_lived_is_still_personal():
    """Devices that legitimately roam (phones) are still someone's device."""
    imp = classify_importance(
        mac="92:ac:4a:bf:8d:10",
        ip="192.168.68.50",
        hostname="Ossians-iPhone-2022",
        scan_count=606,
        ip_stability=0.71,
    )
    assert imp.tier is Tier.PERSONAL


# ── Result shape ─────────────────────────────────────────────────────────────

def test_result_carries_a_reason_and_source():
    imp = classify_importance(mac="aa:bb:cc:dd:ee:07", ip="192.168.1.30")
    assert isinstance(imp, Importance)
    assert imp.reason
    assert imp.source in ("override", "user", "inferred")


def test_classify_never_raises_on_garbage_input():
    for bad in (None, "", "not-a-mac", "zz:zz:zz:zz:zz:zz"):
        imp = classify_importance(mac=bad, ip="also-not-an-ip", scan_count=-1)
        assert isinstance(imp.tier, Tier)


# ── Vendor evidence ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("vendor", [
    "Google Nest / Nest Wifi / Google Wifi Router",
    "TP-Link (Deco mesh / RE series extenders)",
    "Ubiquiti Networks",
    "NETGEAR Orbi",
    "eero inc.",
    "MikroTik",
])
def test_vendor_hints_recognised(vendor):
    assert vendor_suggests_infrastructure(vendor) is True


@pytest.mark.parametrize("vendor", [
    # Placeholders
    "", None, "Unknown", "Unknown Vendor", "n/a",
    # Verbatim from the reference network's known_device rows
    "Google",
    "Google Chromecast / Google Home / Cast Audio",
    "Liteon Technology Corporation",
    "Lexmark International, Inc.",
    "Sony Interactive Entertainment",
    "Amazon Technologies Inc.",
    "Apple, Inc.",
    "Raspberry Pi",
    "AzureWave Technology Inc.",
    "Intel Corporate",
    "Microsoft",
    "Samsung",
    "Sonos",
    "Arcadyan Corporation",
    # Common home-network vendors that must not be swept up. Several are
    # networking *brands* that also sell endpoints, which is precisely why the
    # pattern matches product classes and not manufacturer names.
    "TP-Link Technologies Co.,Ltd.",
    "NETGEAR",
    "ASUSTek COMPUTER INC.",
    "Cisco Systems, Inc",
    "Huawei Technologies Co.,Ltd",
    "Xiaomi Communications Co Ltd",
    "Espressif Inc.",
    "Nintendo Co.,Ltd.",
    "Roku, Inc.",
    "Sonoff / ITEAD",
    "LG Electronics",
    "Philips Lighting BV",
    "Bose Corporation",
    "Dell Inc.",
    "Hewlett Packard",
    "Brother Industries, LTD.",
    "Canon Inc.",
    "Ring LLC",
    "Ecobee Inc.",
    "Tesla Motors",
])
def test_vendor_hints_do_not_fire_on_consumer_devices(vendor):
    """A loose pattern here re-creates the exact defect Phase 2 exists to fix:
    anything this matches is promoted straight past the alert gate.

    Note the deliberate asymmetry — "NETGEAR" does not match but "NETGEAR Orbi"
    does, and "TP-Link Technologies Co.,Ltd." does not match while
    "TP-Link (Deco mesh / RE series extenders)" does. The evidence is the
    product class in the OUI registration, never the brand."""
    assert vendor_suggests_infrastructure(vendor) is False
