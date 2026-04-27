"""
Tests for modules/mac_registry.py

Verifies OUI lookup returns correct fields, handles MAC format variants,
and returns empty dict for unknown OUIs.

No network, no file I/O, no GUI required.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.mac_registry import lookup, vendor_from_mac, model_from_mac, all_ouis


# ── lookup() ──────────────────────────────────────────────────────────────────

class TestLookup:
    def test_known_google_oui_colon_format(self):
        # f4:f5:d8 → Google Home / Nest Audio
        result = lookup("f4:f5:d8:aa:bb:cc")
        assert result["vendor"] == "Google"
        assert "Nest" in result["model"] or "Home" in result["model"]
        assert result["device_type"] == "Smart Speaker"

    def test_known_playstation5_oui(self):
        result = lookup("0c:fe:45:11:22:33")
        assert result["vendor"] == "Sony Interactive Entertainment"
        assert "PlayStation 5" in result["model"]
        assert result["device_type"] == "Games Console"

    def test_known_nintendo_switch_oui(self):
        result = lookup("40:d2:8a:aa:bb:cc")
        assert result["vendor"] == "Nintendo"
        assert "Switch" in result["model"]
        assert result["device_type"] == "Games Console"

    def test_known_samsung_tv_oui(self):
        result = lookup("8c:77:12:aa:bb:cc")
        assert result["vendor"] == "Samsung"
        assert result["device_type"] == "Smart TV"

    def test_known_lg_tv_oui(self):
        result = lookup("64:99:5d:aa:bb:cc")
        assert result["vendor"] == "LG"
        assert result["device_type"] == "Smart TV"

    def test_known_xbox_oui(self):
        result = lookup("98:5f:d3:aa:bb:cc")
        assert result["vendor"] == "Microsoft"
        assert "Xbox" in result["model"]
        assert result["device_type"] == "Games Console"

    def test_known_roku_oui(self):
        result = lookup("cc:6d:a0:aa:bb:cc")
        assert result["vendor"] == "Roku"
        assert result["device_type"] == "Streaming Stick"

    def test_unknown_oui_returns_empty_dict(self):
        result = lookup("00:00:00:aa:bb:cc")
        assert result == {}

    def test_result_is_independent_copy(self):
        # Mutating the returned dict must not affect the registry
        r1 = lookup("f4:f5:d8:aa:bb:cc")
        r1["vendor"] = "TAMPERED"
        r2 = lookup("f4:f5:d8:aa:bb:cc")
        assert r2["vendor"] == "Google"


class TestMacFormats:
    """lookup() must accept all common MAC formats."""

    def test_uppercase_colon(self):
        assert lookup("F4:F5:D8:AA:BB:CC")["vendor"] == "Google"

    def test_dash_separated(self):
        assert lookup("F4-F5-D8-AA-BB-CC")["vendor"] == "Google"

    def test_condensed_no_separator(self):
        # 12 hex chars, no separator
        assert lookup("f4f5d8aabbcc")["vendor"] == "Google"

    def test_mixed_case(self):
        assert lookup("f4:F5:d8:Aa:Bb:Cc")["vendor"] == "Google"


class TestShortcuts:
    def test_vendor_from_mac_known(self):
        assert vendor_from_mac("f4:f5:d8:00:00:00") == "Google"

    def test_vendor_from_mac_unknown(self):
        assert vendor_from_mac("00:00:00:00:00:00") == ""

    def test_model_from_mac_known(self):
        model = model_from_mac("f4:f5:d8:00:00:00")
        assert "Nest" in model or "Home" in model

    def test_model_from_mac_unknown(self):
        assert model_from_mac("00:00:00:00:00:00") == ""


class TestAllOuis:
    def test_returns_dict(self):
        registry = all_ouis()
        assert isinstance(registry, dict)
        assert len(registry) > 100

    def test_all_entries_have_required_keys(self):
        required = {"vendor", "model", "device_type", "product_line"}
        registry = all_ouis()
        for oui, info in registry.items():
            missing = required - set(info.keys())
            assert not missing, f"OUI {oui} missing keys: {missing}"

    def test_all_oui_keys_are_lowercase_8_chars(self):
        registry = all_ouis()
        for oui in registry:
            assert len(oui) == 8, f"OUI key wrong length: {oui!r}"
            assert oui == oui.lower(), f"OUI key not lowercase: {oui!r}"
            assert oui.count(":") == 2, f"OUI key wrong format: {oui!r}"

    def test_consoles_present(self):
        registry = all_ouis()
        console_entries = [v for v in registry.values() if v["device_type"] == "Games Console"]
        assert len(console_entries) >= 10, "Expected at least 10 Games Console entries"

    def test_smart_tvs_present(self):
        registry = all_ouis()
        tv_entries = [v for v in registry.values() if v["device_type"] == "Smart TV"]
        assert len(tv_entries) >= 10, "Expected at least 10 Smart TV entries"
