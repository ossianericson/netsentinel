"""Tests for modules/report_sanitizer.py (TDD — written before implementation)."""

from modules.report_sanitizer import (
    mask_ip,
    vendor_only,
    sanitize_text,
    strip_hostname,
)


def test_mask_ip_private_returns_stable_alias():
    ip_map: dict = {}
    first = mask_ip("192.168.1.50", ip_map)
    again = mask_ip("192.168.1.50", ip_map)
    assert first == again
    assert first.startswith("192.168.1.")


def test_mask_ip_distinct_ips_get_distinct_aliases():
    ip_map: dict = {}
    a = mask_ip("192.168.1.10", ip_map)
    b = mask_ip("10.0.0.5", ip_map)
    assert a != b


def test_mask_ip_public_ip_returns_none():
    ip_map: dict = {}
    assert mask_ip("8.8.8.8", ip_map) is None


def test_mask_ip_invalid_string_returns_none():
    ip_map: dict = {}
    assert mask_ip("not-an-ip", ip_map) is None


def test_vendor_only_uses_known_vendor():
    assert vendor_only(vendor="TP-Link") == "TP-Link device"


def test_vendor_only_falls_back_to_unknown():
    assert vendor_only(vendor=None, mac="") == "Unknown device"


def test_sanitize_text_replaces_known_ip_with_alias():
    ip_map = {"192.168.1.50": "192.168.1.2"}
    text = "The device at 192.168.1.50 is failing."
    out = sanitize_text(text, ip_map)
    assert "192.168.1.50" not in out
    assert "192.168.1.2" in out


def test_sanitize_text_strips_mac_addresses():
    text = "Offending device MAC aa:bb:cc:dd:ee:ff detected."
    out = sanitize_text(text, {})
    assert "aa:bb:cc:dd:ee:ff" not in out.lower()


def test_sanitize_text_omits_unmapped_public_ip():
    text = "Public IP 8.8.8.8 was contacted."
    out = sanitize_text(text, {})
    assert "8.8.8.8" not in out


def test_strip_hostname_always_empty():
    assert strip_hostname("my-laptop.local") == ""
