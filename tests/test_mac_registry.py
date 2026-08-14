"""
Tests for modules/mac_registry.py

Verifies OUI lookup returns correct fields, handles MAC format variants,
and returns empty dict for unknown OUIs.

Also enforces the two integrity invariants the curated table needs but did not
have (see TestIeeeAgreement / TestNoDuplicateOuis below): its vendor claims must
not contradict IEEE, and no OUI may be defined twice.

No network, no file I/O, no GUI required — the IEEE cross-check reads scapy's
bundled offline `manuf` database, the same source mac_lookup.py already uses.
"""

import ast
import re
import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.mac_registry import lookup, vendor_from_mac, model_from_mac, all_ouis

_REGISTRY_SRC = Path(__file__).parent.parent / "modules" / "mac_registry.py"


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


# ── Registry integrity ────────────────────────────────────────────────────────
#
# The curated table is consulted BEFORE the IEEE database by
# classify_registry_first() and rogue_device.scan(), and its device_type is
# sticky — _apply_resolution() only reclassifies when device_type is empty or
# "Unknown Device". So a wrong vendor here is not a cosmetic label error: it
# decides the device type too, and no later evidence can dislodge it.
#
# Live case that motivated these tests: d8:3a:dd is Raspberry Pi Trading Ltd,
# but the table claimed Microsoft / Xbox Series X / S, so a Raspberry Pi named
# "pinas" rendered as vendor Microsoft, type Games Console.

# Imported, not reimplemented: the runtime safety net in mac_registry.py
# applies the same predicate, and a second copy of this arithmetic would drift
# from it the first time an alias is added on one side only.
from modules.mac_registry import vendors_agree as _vendors_agree  # noqa: E402


def _ieee_vendor(oui: str) -> str:
    """IEEE vendor for an OUI via scapy's bundled offline manuf DB.

    Returns "" when IEEE has no record — scapy echoes the query back for an
    unknown OUI, and an absent assignment is not a contradiction.
    """
    from scapy.all import conf

    query = f"{oui}:00:00:00"
    try:
        result = conf.manufdb._get_manuf(query)
    except Exception:
        return ""
    if not result or result == query or result == oui:
        return ""
    return result


class TestIeeeAgreement:
    """The curated table refines IEEE; it must never contradict it."""

    def test_no_entry_contradicts_ieee(self):
        pytest.importorskip("scapy", reason="scapy provides the offline IEEE manuf DB")

        conflicts = []
        for oui, info in sorted(all_ouis().items()):
            ieee = _ieee_vendor(oui)
            if not ieee:
                continue  # IEEE has no assignment on record — nothing to contradict
            if not _vendors_agree(info["vendor"], ieee):
                conflicts.append(
                    f"  {oui}  table says {info['vendor']!r} "
                    f"({info['model']!r} -> {info['device_type']!r})  "
                    f"but IEEE says {ieee!r}"
                )

        assert not conflicts, (
            f"{len(conflicts)} curated OUI entries contradict the IEEE assignment.\n"
            "The table is consulted BEFORE IEEE and its device_type is sticky, so a wrong\n"
            "vendor here also produces a wrong device type that nothing downstream can fix.\n"
            "Correct the row, or delete it and let the scapy fallback answer:\n"
            + "\n".join(conflicts)
        )


class TestNoDuplicateOuis:
    """No OUI may be defined in two dicts — the later update() wins silently."""

    def test_no_oui_appears_in_two_dicts(self):
        # Source-level, not runtime: _OUI_REGISTRY.update() collapses duplicates
        # before any test can observe them, so a runtime check is blind to this.
        tree = ast.parse(_REGISTRY_SRC.read_text(encoding="utf-8"))
        seen = {}
        collisions = []

        for node in tree.body:
            if not (isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                    and isinstance(node.value, ast.Dict)):
                continue
            dict_name = node.target.id
            for key in node.value.keys:
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                oui = key.value
                if not re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){2}", oui):
                    continue
                if oui in seen:
                    prev_dict, prev_line = seen[oui]
                    collisions.append(
                        f"  {oui}  defined in {prev_dict} (line {prev_line}) "
                        f"and again in {dict_name} (line {key.lineno})"
                    )
                else:
                    seen[oui] = (dict_name, key.lineno)

        assert not collisions, (
            f"{len(collisions)} OUIs are defined twice. Whichever dict is passed to\n"
            "_OUI_REGISTRY.update() last silently wins, so one of the two entries is\n"
            "dead code that reads as authoritative. Delete the wrong one:\n"
            + "\n".join(collisions)
        )


# ---------------------------------------------------------------------------
# An OUI identifies an organisation, not a product
# ---------------------------------------------------------------------------
#
# A registry device_type is claimed at 0.90, which outranks every other source
# (the vendor+hostname heuristic tops out at 0.70), so it decides the label
# outright. That is only defensible when the OUI really does carry one product
# class. Where a vendor reuses an OUI across a range, the entry must claim what
# it can support -- vendor and product line -- and leave device_type to whatever
# real evidence the scan found.
#
# f0:72:ea was entered as "Google Nest Doorbell" -> Video Doorbell. The
# reference network's device on that OUI is a Nest Wifi router, owner-confirmed,
# and it rendered in the Devices page as a Video Doorbell at 90% confidence.

_MULTI_PRODUCT_OUIS = [
    # (oui, why)
    ("f0:72:ea", "Google reuses this across the Nest range; a Nest Wifi router "
                 "on this OUI rendered as a Video Doorbell"),
]


@pytest.mark.parametrize("oui,why", _MULTI_PRODUCT_OUIS)
def test_multi_product_oui_claims_no_device_type(oui, why):
    from modules.mac_registry import lookup

    entry = lookup(f"{oui}:00:00:00")
    assert entry, f"{oui} vanished from the registry"
    assert not entry.get("device_type"), (
        f"{oui} claims device_type={entry.get('device_type')!r} at registry "
        f"confidence, which outranks every other source. {why}."
    )


def test_a_device_type_free_entry_still_identifies_the_vendor():
    """Dropping device_type must not throw away the rest of the entry."""
    from modules.mac_registry import lookup

    entry = lookup("f0:72:ea:51:d3:b8")
    assert entry.get("vendor") == "Google"
    assert entry.get("product_line") == "Google Nest"


def test_nest_wifi_row_is_not_a_video_doorbell():
    """The reference-network regression, end to end through the classifier."""
    from modules.device_classifier import classify_registry_first

    result = classify_registry_first(
        mac="f0:72:ea:51:d3:b8", vendor="Google", hostname=""
    )
    assert result != "Video Doorbell"
