"""
Smoke-import tests for the 12 critical modules that previously had zero coverage.

These tests verify:
  1. The module imports cleanly in a headless / no-display environment
  2. Key public symbols (dataclasses, top-level functions) are present and have
     the expected type — catching PyInstaller hidden-import regressions and
     accidental removal of public API.

No network calls are made.  Any function that touches the network or raw
sockets is tested only for importability and expected signatures.
"""

from __future__ import annotations

import importlib
import inspect
import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _import(name: str):
    """Import a module by dotted name, fail the test if it raises."""
    return importlib.import_module(name)


# ── 1. rogue_device ────────────────────────────────────────────────────────────

class TestRogueDevice:
    def test_import(self):
        m = _import("modules.rogue_device")
        assert m is not None

    def test_public_symbols(self):
        from modules.rogue_device import DeviceInfo, scan
        assert inspect.isclass(DeviceInfo)
        assert callable(scan)

    def test_device_info_fields(self):
        from modules.rogue_device import DeviceInfo
        di = DeviceInfo.__dataclass_fields__
        for field in ("ip", "mac", "vendor", "hostname", "risk_level"):
            assert field in di, f"DeviceInfo missing field: {field}"


# ── 2. stp_detector ────────────────────────────────────────────────────────────

class TestStpDetector:
    def test_import(self):
        _import("modules.stp_detector")

    def test_public_symbols(self):
        from modules.stp_detector import BPDUInfo, STPSniffer, scan
        assert inspect.isclass(BPDUInfo)
        assert inspect.isclass(STPSniffer)
        assert callable(scan)

    def test_bpdu_info_fields(self):
        from modules.stp_detector import BPDUInfo
        for field in ("src_mac", "root_mac", "bridge_mac", "interface", "is_rogue"):
            assert field in BPDUInfo.__dataclass_fields__


# ── 3. storm_analyser ─────────────────────────────────────────────────────────

class TestStormAnalyser:
    def test_import(self):
        _import("modules.storm_analyser")

    def test_public_symbols(self):
        from modules.storm_analyser import StormResult, scan
        assert inspect.isclass(StormResult)
        assert callable(scan)

    def test_storm_result_fields(self):
        from modules.storm_analyser import StormResult
        for field in ("storm_level", "bcast_per_sec", "top_sources", "duration_seconds"):
            assert field in StormResult.__dataclass_fields__


# ── 4. speed_tester ───────────────────────────────────────────────────────────

class TestSpeedTester:
    def test_import(self):
        _import("modules.speed_tester")

    def test_public_symbols(self):
        from modules.speed_tester import (
            SpeedServer, SpeedTestResult, speed_to_fraction,
            fetch_servers, run_test, _find_ookla_cli,
        )
        assert inspect.isclass(SpeedServer)
        assert inspect.isclass(SpeedTestResult)
        assert callable(speed_to_fraction)
        assert callable(fetch_servers)
        assert callable(run_test)
        assert callable(_find_ookla_cli)

    def test_speed_test_result_fields(self):
        from modules.speed_tester import SpeedTestResult
        for field in ("download_mbps", "upload_mbps", "ping_ms",
                      "server_name", "backend"):
            assert field in SpeedTestResult.__dataclass_fields__

    def test_speed_to_fraction_zero(self):
        from modules.speed_tester import speed_to_fraction
        assert speed_to_fraction(0) == 0.0

    def test_speed_to_fraction_max(self):
        from modules.speed_tester import speed_to_fraction
        assert speed_to_fraction(1000) == pytest.approx(1.0, abs=0.01)

    def test_speed_to_fraction_midrange(self):
        from modules.speed_tester import speed_to_fraction
        frac = speed_to_fraction(100)
        assert 0.0 < frac < 1.0

    def test_find_ookla_cli_returns_path_or_none(self):
        from modules.speed_tester import _find_ookla_cli
        from pathlib import Path
        result = _find_ookla_cli()
        assert result is None or isinstance(result, Path)


# ── 5. port_scanner ───────────────────────────────────────────────────────────

class TestPortScanner:
    def test_import(self):
        _import("modules.port_scanner")

    def test_public_symbols(self):
        from modules.port_scanner import (
            PortResult, PortScanResult, scan,
            apply_politeness,
        )
        assert inspect.isclass(PortResult)
        assert inspect.isclass(PortScanResult)
        assert callable(scan)
        assert callable(apply_politeness)

    def test_apply_politeness_reduces_ports(self):
        from modules.port_scanner import apply_politeness
        ports = list(range(1, 200))
        result = apply_politeness(ports, level="polite")
        # polite mode should return a subset or the same list
        assert isinstance(result, list)
        assert len(result) <= len(ports)

    def test_port_result_fields(self):
        from modules.port_scanner import PortResult
        for field in ("port", "open", "name", "banner"):
            assert field in PortResult.__dataclass_fields__


# ── 6. arp_monitor ────────────────────────────────────────────────────────────

class TestArpMonitor:
    def test_import(self):
        _import("modules.arp_monitor")

    def test_public_symbols(self):
        from modules.arp_monitor import SpoofEvent, ARPScanResult, ARPSniffer, scan
        assert inspect.isclass(SpoofEvent)
        assert inspect.isclass(ARPScanResult)
        assert inspect.isclass(ARPSniffer)
        assert callable(scan)

    def test_spoof_event_fields(self):
        from modules.arp_monitor import SpoofEvent
        for field in ("attacker_ip", "attacker_mac", "event_type", "is_rogue"):
            assert field in SpoofEvent.__dataclass_fields__


# ── 7. wifi_scanner ───────────────────────────────────────────────────────────

class TestWifiScanner:
    def test_import(self):
        _import("modules.wifi_scanner")

    def test_public_symbols(self):
        from modules.wifi_scanner import NetworkInfo, WifiScanResult, scan
        assert inspect.isclass(NetworkInfo)
        assert inspect.isclass(WifiScanResult)
        assert callable(scan)

    def test_channel_helper(self):
        from modules.wifi_scanner import _channel_from_freq
        assert _channel_from_freq(2412) == 1
        assert _channel_from_freq(2437) == 6
        assert _channel_from_freq(5180) == 36


# ── 8. os_fingerprint ────────────────────────────────────────────────────────

class TestOsFingerprint:
    def test_import(self):
        _import("modules.os_fingerprint")

    def test_public_symbols(self):
        from modules.os_fingerprint import OSGuess, fingerprint_host, _ttl_to_os
        assert inspect.isclass(OSGuess)
        assert callable(fingerprint_host)
        assert callable(_ttl_to_os)

    def test_ttl_to_os_known_values(self):
        from modules.os_fingerprint import _ttl_to_os
        assert "Windows" in _ttl_to_os(128)
        assert "Linux" in _ttl_to_os(64)

    def test_os_guess_fields(self):
        from modules.os_fingerprint import OSGuess
        for field in ("ip", "os_family", "confidence", "banner_hint"):
            assert field in OSGuess.__dataclass_fields__


# ── 9. syn_scanner ────────────────────────────────────────────────────────────

class TestSynScanner:
    def test_import(self):
        _import("modules.syn_scanner")

    def test_public_symbols(self):
        from modules.syn_scanner import SYNPortResult, SYNScanResult, syn_scan, udp_scan
        assert inspect.isclass(SYNPortResult)
        assert inspect.isclass(SYNScanResult)
        assert callable(syn_scan)
        assert callable(udp_scan)

    def test_syn_port_result_fields(self):
        from modules.syn_scanner import SYNPortResult
        for field in ("port", "state"):
            assert field in SYNPortResult.__dataclass_fields__


# ── 10. threat_intel ─────────────────────────────────────────────────────────

class TestThreatIntel:
    def test_import(self):
        _import("modules.threat_intel")

    def test_public_symbols(self):
        from modules.threat_intel import ThreatEntry, AbuseIpDbResult, _is_public_ip
        assert inspect.isclass(ThreatEntry)
        assert inspect.isclass(AbuseIpDbResult)
        assert callable(_is_public_ip)

    def test_is_public_ip_private(self):
        from modules.threat_intel import _is_public_ip
        assert _is_public_ip("192.168.1.1") is False
        assert _is_public_ip("10.0.0.1") is False
        assert _is_public_ip("172.16.0.1") is False

    def test_is_public_ip_public(self):
        from modules.threat_intel import _is_public_ip
        assert _is_public_ip("8.8.8.8") is True
        assert _is_public_ip("1.1.1.1") is True

    def test_threat_entry_fields(self):
        from modules.threat_intel import ThreatEntry
        for field in ("indicator", "source", "categories", "confidence"):
            assert field in ThreatEntry.__dataclass_fields__


# ── 11. dns_correlator ───────────────────────────────────────────────────────

class TestDnsCorrelator:
    def test_import(self):
        _import("modules.dns_correlator")

    def test_public_symbols(self):
        from modules.dns_correlator import (
            PingPoint, DnsPoint, CorrelatorResult, scan,
        )
        assert inspect.isclass(PingPoint)
        assert inspect.isclass(DnsPoint)
        assert inspect.isclass(CorrelatorResult)
        assert callable(scan)

    def test_correlator_result_fields(self):
        from modules.dns_correlator import CorrelatorResult
        for field in ("ping_series", "dns_series", "micro_outages", "dns_only_failures"):
            assert field in CorrelatorResult.__dataclass_fields__


# ── 12. smb_enumerator ───────────────────────────────────────────────────────

class TestSmbEnumerator:
    def test_import(self):
        _import("modules.smb_enumerator")

    def test_public_symbols(self):
        from modules.smb_enumerator import (
            SMBShare, SMBEnumResult, enumerate_smb,
        )
        assert inspect.isclass(SMBShare)
        assert inspect.isclass(SMBEnumResult)
        assert callable(enumerate_smb)

    def test_smb_share_fields(self):
        from modules.smb_enumerator import SMBShare
        for field in ("name", "share_type", "comment", "permissions"):
            assert field in SMBShare.__dataclass_fields__

    def test_smb_enum_result_fields(self):
        from modules.smb_enumerator import SMBEnumResult
        for field in ("host", "shares", "netbios", "error"):
            assert field in SMBEnumResult.__dataclass_fields__
