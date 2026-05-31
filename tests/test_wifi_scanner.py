"""Tests for modules/wifi_scanner.py — 802.11 WiFi scanner."""
import re
import pytest
from modules.wifi_scanner import (
    NetworkInfo, ConnectedClient, WifiScanResult,
    _channel_from_freq, _band_from_channel, ROGUE_SSID_PATTERNS,
)


def test_import():
    import modules.wifi_scanner as m
    assert hasattr(m, "scan")
    assert hasattr(m, "NetworkInfo")
    assert hasattr(m, "WifiScanResult")
    assert hasattr(m, "ROGUE_SSID_PATTERNS")


def test_network_info_fields():
    n = NetworkInfo(
        ssid="MyNetwork",
        bssid="aa:bb:cc:dd:ee:ff",
        channel=6,
        signal_dbm=-65,
        band="2.4 GHz",
        is_hidden=False,
        is_rogue_ssid=False,
    )
    assert n.ssid == "MyNetwork"
    assert n.channel == 6
    assert n.signal_dbm == -65
    assert n.is_rogue_ssid is False


def test_connected_client_fields():
    c = ConnectedClient(mac="11:22:33:44:55:66", ip="192.168.1.50")
    assert c.mac == "11:22:33:44:55:66"
    assert c.ip == "192.168.1.50"


def test_wifi_scan_result_defaults():
    r = WifiScanResult()
    assert r.networks == []
    assert r.connected_clients == []
    assert r.error == ""


def test_rogue_ssid_patterns_not_empty():
    assert len(ROGUE_SSID_PATTERNS) > 0


def test_channel_from_freq_2ghz():
    assert _channel_from_freq(2412) == 1
    assert _channel_from_freq(2437) == 6
    assert _channel_from_freq(2462) == 11


def test_channel_from_freq_5ghz():
    ch36 = _channel_from_freq(5180)
    assert ch36 == 36


def test_channel_from_freq_unknown():
    result = _channel_from_freq(0)
    assert isinstance(result, int)


def test_band_from_channel_2ghz():
    assert "2.4" in _band_from_channel(1)
    assert "2.4" in _band_from_channel(11)


def test_band_from_channel_5ghz():
    assert "5" in _band_from_channel(36)
    assert "5" in _band_from_channel(149)


def test_rogue_ssid_pattern_match():
    patterns = [re.compile(p, re.IGNORECASE) for p in ROGUE_SSID_PATTERNS]
    assert any(p.search("GoogleSetup_ABC") for p in patterns)
