"""
tests/test_dhcp_fingerprint.py — Unit tests for modules/dhcp_fingerprint.py
"""
from modules.dhcp_fingerprint import (
    DhcpFingerprint,
    clear_cache,
    fingerprint_from_options,
    fingerprint_vci,
    get_fingerprint,
    get_option12_hostname,
    update_cache,
)


# ── fingerprint_vci ───────────────────────────────────────────────────────────

class TestFingerprintVci:
    def test_windows_msft(self):
        fp = fingerprint_vci("MSFT 5.0")
        assert fp.device_hint == "Windows PC"
        assert fp.confidence == "high"
        assert "Windows" in fp.os_hint
        assert "MSFT" in fp.evidence

    def test_android_with_version(self):
        fp = fingerprint_vci("android-dhcp-12")
        assert fp.device_hint == "Android Device"
        assert fp.confidence == "high"
        assert "12" in fp.os_hint

    def test_android_without_version(self):
        fp = fingerprint_vci("android")
        assert fp.device_hint == "Android Device"
        assert fp.confidence == "low"

    def test_esphome(self):
        fp = fingerprint_vci("ESPHome v2023.1")
        assert fp.device_hint == "IoT Device"
        assert fp.os_hint == "ESPHome"
        assert fp.confidence == "high"

    def test_tasmota(self):
        fp = fingerprint_vci("Tasmota 13.0")
        assert fp.device_hint == "IoT Device"
        assert fp.confidence == "high"

    def test_openwrt(self):
        fp = fingerprint_vci("OpenWrt r12345")
        assert fp.device_hint == "Router / Gateway"
        assert fp.confidence == "high"

    def test_raspbian(self):
        fp = fingerprint_vci("Raspbian GNU/Linux")
        assert fp.device_hint == "Single Board Computer"
        assert fp.confidence == "high"

    def test_iphone(self):
        fp = fingerprint_vci("iPhone")
        assert fp.device_hint == "iPhone / iPad"
        assert fp.confidence == "high"

    def test_pxe_client(self):
        fp = fingerprint_vci("PXEClient:Arch:00007")
        assert fp.device_hint == "PXE Boot Client"
        assert fp.confidence == "high"

    def test_udhcpc_embedded(self):
        fp = fingerprint_vci("udhcpc-1.31.1")
        assert fp.device_hint == "IoT Device"
        assert "Embedded" in fp.os_hint

    def test_unknown_vci_returns_empty_fingerprint(self):
        fp = fingerprint_vci("ZYXEL-CUSTOM-12345")
        assert fp.device_hint == ""
        assert fp.confidence == ""
        assert fp.evidence  # evidence still records the VCI string

    def test_empty_string_returns_empty_fingerprint(self):
        fp = fingerprint_vci("")
        assert fp.device_hint == ""
        assert fp.confidence == ""
        assert fp.evidence == ""

    def test_case_insensitive_cisco(self):
        fp = fingerprint_vci("cisco-7940")
        assert fp.device_hint == "Network Switch/Router"
        assert fp.confidence == "high"


# ── fingerprint_from_options ──────────────────────────────────────────────────

class TestFingerprintFromOptions:
    def test_string_keys(self):
        opts = {"vendor_class_id": "MSFT 5.0", "hostname": "DESKTOP-ABC"}
        fp = fingerprint_from_options(opts)
        assert fp.device_hint == "Windows PC"
        assert fp.hostname == "DESKTOP-ABC"

    def test_bytes_values(self):
        opts = {"vendor_class_id": b"android-dhcp-13", "hostname": b"my-phone"}
        fp = fingerprint_from_options(opts)
        assert fp.device_hint == "Android Device"
        assert "13" in fp.os_hint
        assert fp.hostname == "my-phone"

    def test_integer_keys(self):
        opts = {60: b"MSFT 5.0", 12: b"LAPTOP"}
        fp = fingerprint_from_options(opts)
        assert fp.device_hint == "Windows PC"
        assert fp.hostname == "LAPTOP"

    def test_hostname_only(self):
        fp = fingerprint_from_options({"hostname": "living-room-pi"})
        assert fp.hostname == "living-room-pi"
        assert fp.device_hint == ""  # no VCI → no device hint

    def test_empty_options(self):
        fp = fingerprint_from_options({})
        assert fp.device_hint == ""
        assert fp.hostname == ""

    def test_vci_only(self):
        fp = fingerprint_from_options({"vendor_class_id": "Tasmota"})
        assert fp.device_hint == "IoT Device"
        assert fp.hostname == ""


# ── cache functions ───────────────────────────────────────────────────────────

class TestCache:
    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    def test_update_and_retrieve(self):
        fp = DhcpFingerprint(device_hint="Windows PC", confidence="high",
                              hostname="PC1", evidence="VCI: MSFT 5.0")
        update_cache({"aa:bb:cc:dd:ee:ff": fp})
        result = get_fingerprint("aa:bb:cc:dd:ee:ff")
        assert result is not None
        assert result.device_hint == "Windows PC"

    def test_mac_normalisation(self):
        fp = DhcpFingerprint(device_hint="IoT Device", confidence="high",
                              hostname="sensor", evidence="VCI: ESPHome")
        update_cache({"AA-BB-CC-DD-EE-FF": fp})
        # Retrieve with colon-separated lowercase
        result = get_fingerprint("aa:bb:cc:dd:ee:ff")
        assert result is not None
        assert result.device_hint == "IoT Device"

    def test_high_conf_not_overwritten_by_low_conf(self):
        high = DhcpFingerprint(device_hint="Windows PC",  confidence="high",
                                evidence="VCI: MSFT 5.0")
        low  = DhcpFingerprint(device_hint="Linux Host",  confidence="low",
                                evidence="VCI: linux-")
        update_cache({"11:22:33:44:55:66": high})
        update_cache({"11:22:33:44:55:66": low})
        result = get_fingerprint("11:22:33:44:55:66")
        assert result is not None
        assert result.device_hint == "Windows PC"

    def test_low_conf_overwritten_by_high_conf(self):
        low  = DhcpFingerprint(device_hint="Linux Host",  confidence="low")
        high = DhcpFingerprint(device_hint="Windows PC",  confidence="high")
        update_cache({"aa:aa:aa:aa:aa:aa": low})
        update_cache({"aa:aa:aa:aa:aa:aa": high})
        result = get_fingerprint("aa:aa:aa:aa:aa:aa")
        assert result is not None
        assert result.device_hint == "Windows PC"

    def test_get_option12_hostname(self):
        fp = DhcpFingerprint(hostname="my-laptop", confidence="high")
        update_cache({"de:ad:be:ef:00:01": fp})
        assert get_option12_hostname("de:ad:be:ef:00:01") == "my-laptop"

    def test_get_option12_hostname_missing(self):
        assert get_option12_hostname("ff:ff:ff:ff:ff:ff") == ""

    def test_get_fingerprint_missing(self):
        assert get_fingerprint("00:11:22:33:44:55") is None

    def test_update_cache_empty_dict(self):
        update_cache({})  # must not raise

    def test_clear_cache(self):
        fp = DhcpFingerprint(device_hint="Windows PC", confidence="high")
        update_cache({"ab:cd:ef:01:23:45": fp})
        clear_cache()
        assert get_fingerprint("ab:cd:ef:01:23:45") is None
