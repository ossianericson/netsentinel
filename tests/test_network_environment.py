"""
Behavioural tests for modules/network_environment.py

Covers:
  - detect_environment() branch precedence: vpn > corporate (domain or wide 10.x) >
    large_subnet > home
  - home is the silent case: empty reasons, no title
  - a VPN-named adapter that is disconnected / has no IPv4 must NOT trigger "vpn"
  - detect_environment() calls the real utils_net helpers when given no arguments

All fixtures are fake (net_info, adapters) dicts/lists — no real machine state is touched.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.network_environment import (
    detect_environment,
    NetworkEnvironment,
    partition_by_scope,
    network_fingerprint,
)


def _net_info(local_ips=None, gateway="192.168.1.1", dns_servers=None, domain=""):
    return {
        "local_ips": local_ips or [],
        "gateway": gateway,
        "dns_servers": dns_servers or [],
        "domain": domain,
    }


def _adapter(name, connected=True, ipv4="192.168.1.50"):
    return {
        "name": name,
        "type": "Ethernet",
        "mac": "aa:bb:cc:dd:ee:ff",
        "ipv4": ipv4,
        "speed_mbps": 1000,
        "signal_pct": -1,
        "connected": connected,
    }


class TestVpnDetection:
    def test_active_vpn_adapter_yields_vpn_kind(self):
        net_info = _net_info(
            local_ips=[{"ip": "10.10.5.23", "mask": "255.255.0.0", "adapter": "GlobalProtect"}],
            gateway="10.10.0.1",
        )
        adapters = [_adapter("GlobalProtect", connected=True, ipv4="10.10.5.23")]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.kind == "vpn"
        assert env.vpn_adapter == "GlobalProtect"
        assert env.confidence == "high"
        assert env.reasons
        assert "GlobalProtect" in env.title

    def test_disconnected_vpn_named_adapter_is_ignored(self):
        # A VPN client installed but not currently connected must not flag "vpn" —
        # only adapters that are connected and hold an IPv4 count as evidence.
        net_info = _net_info(
            local_ips=[{"ip": "192.168.1.50", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
        )
        adapters = [
            _adapter("TAP-Windows Adapter V9", connected=False, ipv4=""),
            _adapter("Wi-Fi", connected=True, ipv4="192.168.1.50"),
        ]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.kind == "home"

    def test_vpn_takes_precedence_over_domain(self):
        net_info = _net_info(
            local_ips=[{"ip": "10.10.5.23", "mask": "255.255.0.0", "adapter": "AnyConnect"}],
            domain="CONTOSO.LOCAL",
        )
        adapters = [_adapter("Cisco AnyConnect", connected=True, ipv4="10.10.5.23")]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.kind == "vpn"


class TestCorporateDetection:
    def test_domain_membership_yields_corporate_kind(self):
        net_info = _net_info(
            local_ips=[{"ip": "192.168.1.50", "mask": "255.255.255.0", "adapter": "Ethernet"}],
            domain="CONTOSO.LOCAL",
        )
        adapters = [_adapter("Ethernet", connected=True, ipv4="192.168.1.50")]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.kind == "corporate"
        assert env.domain == "CONTOSO.LOCAL"
        assert env.confidence == "high"
        assert env.reasons

    def test_wide_10_slash_8_yields_corporate_kind(self):
        net_info = _net_info(
            local_ips=[{"ip": "10.20.3.44", "mask": "255.255.0.0", "adapter": "Ethernet"}],
            domain="",
        )
        adapters = [_adapter("Ethernet", connected=True, ipv4="10.20.3.44")]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.kind == "corporate"
        assert env.prefix_len == 16


class TestLargeSubnetDetection:
    def test_wide_non_10x_subnet_yields_large_subnet_kind(self):
        net_info = _net_info(
            local_ips=[{"ip": "172.16.5.10", "mask": "255.255.240.0", "adapter": "Ethernet"}],
            domain="",
        )
        adapters = [_adapter("Ethernet", connected=True, ipv4="172.16.5.10")]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.kind == "large_subnet"
        assert env.prefix_len == 20
        assert env.subnet_hosts == 4094


class TestHomeDetection:
    def test_plain_home_network_is_silent(self):
        net_info = _net_info(
            local_ips=[{"ip": "192.168.1.42", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
            domain="",
        )
        adapters = [_adapter("Wi-Fi", connected=True, ipv4="192.168.1.42")]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.kind == "home"
        assert env.reasons == []
        assert env.title == ""

    def test_returns_network_environment_instance(self):
        net_info = _net_info(
            local_ips=[{"ip": "192.168.1.42", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
        )
        adapters = [_adapter("Wi-Fi", connected=True, ipv4="192.168.1.42")]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert isinstance(env, NetworkEnvironment)


class TestScopeCidr:
    """L5: NetworkEnvironment.scope_cidr is the REAL local subnet (whatever width it
    actually is) — never forced to /24. A flat corporate L2 keeps its full /16 so
    every device on it still gets scanned; only genuinely foreign-subnet ARP noise
    (a different network entirely) is ever excluded by callers using this value."""

    def test_home_scope_cidr_is_local_24(self):
        net_info = _net_info(
            local_ips=[{"ip": "192.168.1.42", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
        )
        adapters = [_adapter("Wi-Fi", connected=True, ipv4="192.168.1.42")]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.scope_cidr == "192.168.1.0/24"

    def test_corporate_scope_cidr_is_the_full_wide_subnet(self):
        net_info = _net_info(
            local_ips=[{"ip": "10.20.3.44", "mask": "255.255.0.0", "adapter": "Ethernet"}],
            domain="",
        )
        adapters = [_adapter("Ethernet", connected=True, ipv4="10.20.3.44")]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.kind == "corporate"
        assert env.scope_cidr == "10.20.0.0/16"

    def test_vpn_scope_cidr_matches_vpn_adapter_subnet(self):
        net_info = _net_info(
            local_ips=[{"ip": "10.10.5.23", "mask": "255.255.0.0", "adapter": "GlobalProtect"}],
            gateway="10.10.0.1",
        )
        adapters = [_adapter("GlobalProtect", connected=True, ipv4="10.10.5.23")]

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.scope_cidr == "10.10.0.0/16"

    def test_no_local_ips_yields_empty_scope_cidr(self):
        net_info = _net_info(local_ips=[])
        adapters = []

        env = detect_environment(net_info=net_info, adapters=adapters)

        assert env.scope_cidr == ""


class TestPartitionByScope:
    """L5: rogue_device.scan() must never silently over-scan into a subnet it
    wasn't asked to touch, and never silently drop what it excludes — pairs are
    always partitioned into (in_scope, out_of_scope), never discarded."""

    def test_splits_in_scope_and_out_of_scope_pairs(self):
        pairs = [
            ("192.168.1.10", "aa:aa:aa:aa:aa:01"),
            ("192.168.1.11", "aa:aa:aa:aa:aa:02"),
            ("10.8.0.5", "aa:aa:aa:aa:aa:03"),   # different subnet entirely
        ]

        in_scope, out_of_scope = partition_by_scope(pairs, "192.168.1.0/24")

        assert in_scope == pairs[:2]
        assert out_of_scope == [pairs[2]]

    def test_blank_scope_cidr_fails_open_everything_in_scope(self):
        pairs = [("192.168.1.10", "aa:aa:aa:aa:aa:01"), ("10.8.0.5", "aa:aa:aa:aa:aa:02")]

        in_scope, out_of_scope = partition_by_scope(pairs, "")

        assert in_scope == pairs
        assert out_of_scope == []

    def test_malformed_scope_cidr_fails_open_everything_in_scope(self):
        pairs = [("192.168.1.10", "aa:aa:aa:aa:aa:01")]

        in_scope, out_of_scope = partition_by_scope(pairs, "not-a-cidr")

        assert in_scope == pairs
        assert out_of_scope == []

    def test_malformed_ip_in_pairs_is_treated_as_out_of_scope(self):
        pairs = [("not-an-ip", "aa:aa:aa:aa:aa:01")]

        in_scope, out_of_scope = partition_by_scope(pairs, "192.168.1.0/24")

        assert in_scope == []
        assert out_of_scope == pairs

    def test_empty_pairs_returns_empty_lists(self):
        in_scope, out_of_scope = partition_by_scope([], "192.168.1.0/24")

        assert in_scope == []
        assert out_of_scope == []


class TestNetworkFingerprint:
    """L6: fingerprint keyed by gateway MAC + subnet — deliberately DIFFERENT from
    NetworkEnvironment.fingerprint() (kind:vpn_adapter:domain), since two distinct
    physical "home" networks must be asked about authorization separately even
    though they'd share the same environment-kind fingerprint."""

    def test_fingerprint_combines_gateway_mac_and_subnet(self):
        net_info = _net_info(
            local_ips=[{"ip": "192.168.1.42", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
            gateway="192.168.1.1",
        )
        arp_snapshot = {"192.168.1.1": "aa:bb:cc:dd:ee:ff"}

        fp = network_fingerprint(net_info=net_info, arp_snapshot=arp_snapshot)

        assert fp == "aa:bb:cc:dd:ee:ff@192.168.1.0/24"

    def test_falls_back_to_gateway_ip_when_mac_unknown(self):
        net_info = _net_info(
            local_ips=[{"ip": "192.168.1.42", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
            gateway="192.168.1.1",
        )

        fp = network_fingerprint(net_info=net_info, arp_snapshot={})

        assert fp == "192.168.1.1@192.168.1.0/24"

    def test_falls_back_to_unknown_when_gateway_missing(self):
        net_info = _net_info(
            local_ips=[{"ip": "192.168.1.42", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
            gateway=None,
        )

        fp = network_fingerprint(net_info=net_info, arp_snapshot={})

        assert fp == "unknown@192.168.1.0/24"

    def test_two_different_physical_networks_of_the_same_kind_get_different_fingerprints(self):
        home_a = _net_info(
            local_ips=[{"ip": "192.168.1.42", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
            gateway="192.168.1.1",
        )
        home_b = _net_info(
            local_ips=[{"ip": "192.168.50.7", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
            gateway="192.168.50.1",
        )
        arp_a = {"192.168.1.1": "aa:aa:aa:aa:aa:aa"}
        arp_b = {"192.168.50.1": "bb:bb:bb:bb:bb:bb"}

        fp_a = network_fingerprint(net_info=home_a, arp_snapshot=arp_a)
        fp_b = network_fingerprint(net_info=home_b, arp_snapshot=arp_b)

        assert fp_a != fp_b

    def test_calls_real_helpers_when_no_arguments_given(self, monkeypatch):
        called = {"net_info": False, "arp": False}

        def fake_net_info():
            called["net_info"] = True
            return _net_info(
                local_ips=[{"ip": "192.168.1.42", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
                gateway="192.168.1.1",
            )

        def fake_arp():
            called["arp"] = True
            return {"192.168.1.1": "aa:bb:cc:dd:ee:ff"}

        monkeypatch.setattr("modules.network_environment.get_network_info", fake_net_info)
        monkeypatch.setattr("modules.network_environment.get_arp_snapshot", fake_arp)

        fp = network_fingerprint()

        assert called["net_info"] is True
        assert called["arp"] is True
        assert fp == "aa:bb:cc:dd:ee:ff@192.168.1.0/24"


class TestInjectableDefaults:
    def test_calls_real_helpers_when_no_arguments_given(self, monkeypatch):
        called = {"net_info": False, "adapters": False}

        def fake_net_info():
            called["net_info"] = True
            return _net_info(
                local_ips=[{"ip": "192.168.1.42", "mask": "255.255.255.0", "adapter": "Wi-Fi"}],
            )

        def fake_adapters():
            called["adapters"] = True
            return [_adapter("Wi-Fi", connected=True, ipv4="192.168.1.42")]

        monkeypatch.setattr("modules.network_environment.get_network_info", fake_net_info)
        monkeypatch.setattr("modules.network_environment.get_interface_details", fake_adapters)

        env = detect_environment()

        assert called["net_info"] is True
        assert called["adapters"] is True
        assert env.kind == "home"
