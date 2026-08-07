"""
Tests for modules/device_identity.py — what the app is allowed to say a thing *is*.

Written test-first (RULE-TDD1). The module answers two questions the rest of the
Signal Quality Program depends on:

  1. Is this a device at all? A multicast address is not. The live database held
     `01:00:5e:7f:ff:fa` / `239.255.255.250` (SSDP) as a known_device row promoted
     to inferred_role=infrastructure, which opted "it" into every device-scoped
     alert rule.

  2. Can we name it? 8 of 30 devices on the reference network carry a randomised
     MAC with no hostname and no vendor. They are stable, not churning — they are
     unidentifiable, and three had been promoted to infrastructure.

The consequence both share: an unidentifiable or non-existent thing must never be
promotable to infrastructure, because that role is the alert-eligibility gate.
"""
from __future__ import annotations

import pytest

from modules.device_identity import (
    IdentityClass,
    classify_identity,
    is_promotable_to_infrastructure,
)


# ── NOT_A_DEVICE: addresses that are not endpoints ───────────────────────────

@pytest.mark.parametrize("mac", [
    "01:00:5e:7f:ff:fa",   # IPv4 multicast (SSDP) — the live-database case
    "01:00:5e:00:00:fb",   # mDNS
    "33:33:00:00:00:01",   # IPv6 multicast
    "ff:ff:ff:ff:ff:ff",   # broadcast
    "01-00-5e-7f-ff-fa",   # dash-separated form
    "01005E7FFFFA",        # bare form
])
def test_group_bit_macs_are_not_devices(mac):
    """The least-significant bit of the first octet is the I/G (group) bit. Any
    MAC with it set is a multicast/broadcast destination, never a host."""
    assert classify_identity(mac).identity_class is IdentityClass.NOT_A_DEVICE


@pytest.mark.parametrize("ip", [
    "224.0.0.1",         # all-hosts multicast
    "239.255.255.250",   # SSDP — the live-database case
    "255.255.255.255",   # limited broadcast
    "ff02::1",           # IPv6 all-nodes multicast
])
def test_multicast_and_broadcast_ips_are_not_devices(ip):
    assert classify_identity("aa:bb:cc:dd:ee:ff", ip=ip).identity_class is (
        IdentityClass.NOT_A_DEVICE
    )


@pytest.mark.parametrize("mac", ["00:00:00:00:00:00", "", "   ", "?", None])
def test_empty_and_zero_macs_are_not_devices(mac):
    assert classify_identity(mac).identity_class is IdentityClass.NOT_A_DEVICE


def test_not_a_device_wins_over_randomised_bit():
    """33:33:.. has BOTH the group bit (0x01) and the local bit (0x02) set.
    Ordering matters: it must classify as NOT_A_DEVICE, not ANONYMOUS."""
    ident = classify_identity("33:33:00:00:00:01")
    assert ident.identity_class is IdentityClass.NOT_A_DEVICE


def test_not_a_device_carries_a_reason():
    assert classify_identity("01:00:5e:7f:ff:fa").reason


# ── ANONYMOUS: real devices we cannot name ───────────────────────────────────

def test_randomised_mac_with_no_name_or_vendor_is_anonymous():
    ident = classify_identity("02:a8:f1:3b:93:40")
    assert ident.identity_class is IdentityClass.ANONYMOUS
    assert ident.is_randomized is True


@pytest.mark.parametrize("vendor", [None, "", "   ", "Unknown", "unknown", "Unknown Vendor"])
def test_placeholder_vendors_do_not_count_as_identification(vendor):
    """The live database stores 'Unknown' for every privacy-MAC device; treating
    that string as a real vendor would defeat the whole check."""
    ident = classify_identity("02:a8:f1:3b:93:40", vendor=vendor)
    assert ident.identity_class is IdentityClass.ANONYMOUS


@pytest.mark.parametrize("hostname", [None, "", "   ", "?"])
def test_placeholder_hostnames_do_not_count_as_identification(hostname):
    ident = classify_identity("02:a8:f1:3b:93:40", hostname=hostname)
    assert ident.identity_class is IdentityClass.ANONYMOUS


# ── IDENTIFIED: enough to name the thing ─────────────────────────────────────

def test_randomised_mac_with_a_hostname_is_identified():
    """'Ossians-iPhone-2022' is a randomised MAC that is perfectly identifiable —
    iOS randomises per-SSID and then keeps that MAC. Privacy MAC alone is not
    grounds to call a device anonymous."""
    ident = classify_identity("92:ac:4a:bf:8d:10", hostname="Ossians-iPhone-2022")
    assert ident.identity_class is IdentityClass.IDENTIFIED
    assert ident.is_randomized is True


def test_randomised_mac_with_a_real_vendor_is_identified():
    ident = classify_identity("92:35:ca:16:8f:38", vendor="Apple, Inc.")
    assert ident.identity_class is IdentityClass.IDENTIFIED


def test_ordinary_mac_is_identified_even_with_no_metadata():
    """A globally-administered MAC is an OUI-backed identity by itself."""
    ident = classify_identity("f4:f5:d8:aa:bb:cc")
    assert ident.identity_class is IdentityClass.IDENTIFIED
    assert ident.is_randomized is False


def test_ordinary_private_ip_does_not_affect_classification():
    ident = classify_identity("f4:f5:d8:aa:bb:cc", ip="192.168.1.20")
    assert ident.identity_class is IdentityClass.IDENTIFIED


# ── Infrastructure promotion gate ────────────────────────────────────────────

def test_anonymous_devices_are_never_promotable_to_infrastructure():
    """Three anonymous MACs held inferred_role=infrastructure in the live
    database, which is the alert-eligibility gate."""
    ident = classify_identity("02:a8:f1:3b:93:40")
    assert is_promotable_to_infrastructure(ident) is False


def test_non_devices_are_never_promotable_to_infrastructure():
    ident = classify_identity("01:00:5e:7f:ff:fa", ip="239.255.255.250")
    assert is_promotable_to_infrastructure(ident) is False


def test_identified_devices_are_promotable():
    ident = classify_identity("3c:64:cf:e0:27:02", vendor="TP-Link", hostname="deco")
    assert is_promotable_to_infrastructure(ident) is True


# ── Contract details the callers rely on ─────────────────────────────────────

def test_is_randomized_matches_the_existing_classifier_helper():
    """device_identity must not re-derive the U/L bit test — there were already
    two copies in the tree. Consolidating means agreeing exactly."""
    from modules.device_classifier import is_randomized_mac
    for mac in ("02:00:00:00:00:01", "f4:f5:d8:aa:bb:cc", "92:ac:4a:bf:8d:10"):
        assert classify_identity(mac).is_randomized == is_randomized_mac(mac)


def test_classify_identity_is_total_over_junk_input():
    """Called from the scan hot path — must never raise, whatever a scanner emits."""
    for mac in ("zz:zz:zz:zz:zz:zz", "1", "::::", "aa:bb"):
        assert classify_identity(mac).identity_class in tuple(IdentityClass)


def test_identity_class_values_are_stable_strings():
    """Persisted to known_device.importance_source and compared across restarts."""
    assert IdentityClass.IDENTIFIED.value == "identified"
    assert IdentityClass.ANONYMOUS.value == "anonymous"
    assert IdentityClass.NOT_A_DEVICE.value == "not_a_device"
