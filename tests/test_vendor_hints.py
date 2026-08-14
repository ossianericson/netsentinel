"""Tests for modules/vendor_hints.py — vendor derived from a hostname.

No network, no file I/O, no GUI required.
"""
import pytest

from modules.vendor_hints import vendor_from_hostname


# ── vendor_from_hostname ──────────────────────────────────────────────────────
#
# A privacy MAC carries no OUI and never will, so vendor lookup returns nothing
# for it no matter how many OUIs the registry gains. But the hostname is often a
# perfectly good handle -- device_identity.py already argues this for identity
# ("Ossians-iPhone-2022 is both randomised and perfectly identifiable"); only
# device_type was ever derived from it, never vendor.
#
# Live case: 6a:94:29:ec:8f:4d / "Chromecast-Audio-Vardagsrum" rendered with
# vendor "Unknown" beside an identical Chromecast that happened to have a real
# OUI and so showed "Google".

class TestVendorFromHostname:
    """Derive a vendor from an unambiguous product name in the hostname."""

    @pytest.mark.parametrize("hostname,expected", [
        ("Chromecast-Audio-Vardagsrum", "Google"),
        ("chromecast1234",              "Google"),
        ("Google-Home-Mini",            "Google"),
        ("Nest-Hub-Kitchen",            "Google"),
        ("Echo-Dot-Bedroom",            "Amazon"),
        ("amazon-fire-tv",              "Amazon"),
        ("Ossians-iPhone-2022",         "Apple"),
        ("Johns-MacBook-Pro",           "Apple"),
        ("raspberrypi",                 "Raspberry Pi"),
        ("rpi4-kitchen",                "Raspberry Pi"),
        ("Galaxy-S23",                  "Samsung"),
        ("PlayStation-5",               "Sony"),
        ("XBOX-LIVINGROOM",             "Microsoft"),
        ("Sonos-Beam",                  "Sonos"),
        ("roku-ultra",                  "Roku"),
        ("Deco-XE75-Hall",              "TP-Link"),
    ])
    def test_known_product_names(self, hostname, expected):
        assert vendor_from_hostname(hostname) == expected

    @pytest.mark.parametrize("hostname", [
        "LibreELEC",      # runs on Pi, Odroid and x86 alike
        "dietpi",
        "armbian",
        "openwrt",
        "ubuntu-server",
    ])
    def test_os_names_do_not_imply_a_vendor(self, hostname):
        # An OS name says what the device runs, not who made it. Guessing a
        # vendor from one is exactly the over-claim this whole change removes.
        assert vendor_from_hostname(hostname) == ""

    @pytest.mark.parametrize("hostname", [
        "", "   ", "greenest-server", "echolocation-pc", "shielded-host",
        "192.168.1.50", "desktop-4f9a2b",
    ])
    def test_no_match_returns_empty(self, hostname):
        # "greenest"/"echolocation"/"shielded" contain nest/echo/shield as
        # substrings -- word boundaries must keep them from matching.
        assert vendor_from_hostname(hostname) == ""

    def test_agrees_with_the_registry_on_a_device_that_has_both(self):
        # A hostname-derived vendor must not contradict the OUI-derived one
        # where both are available, or the two paths would disagree in the UI.
        from modules.mac_registry import lookup
        assert vendor_from_hostname("raspberrypi") == lookup("d8:3a:dd:00:00:00")["vendor"]
