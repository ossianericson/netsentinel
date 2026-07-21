"""
Environment detection — classify the network NetSentinel is currently running on so the
app can say, in plain English, why results look different before a scan starts.

Pure Python, no PyQt imports. See .apm/instructions/ Part 1.A for the design rationale.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from modules.utils_net import get_arp_snapshot, get_interface_details, get_network_info

_VPN_KEYWORDS = (
    "tap", "tun", "wireguard", "nordlynx", "anyconnect", "globalprotect",
    "fortinet", "forticlient", "pulse", "zscaler", "openvpn", "tailscale",
    "zerotier", "utun", "ppp",
)


@dataclass
class NetworkEnvironment:
    kind: str = "home"            # "home" | "vpn" | "corporate" | "large_subnet"
    confidence: str = "high"      # "high" | "medium"
    title: str = ""                # "" on home — nothing is shown
    reasons: list = field(default_factory=list)   # plain-English evidence, one line each
    effects: list = field(default_factory=list)   # what the user should expect to be degraded
    vpn_adapter: str = ""
    domain: str = ""
    prefix_len: int = 24
    subnet_hosts: int = 254
    scope_cidr: str = ""          # L5: the REAL local subnet, whatever width it is —
                                   # never forced to /24. "" when it can't be determined.

    def fingerprint(self) -> str:
        return f"{self.kind}:{self.vpn_adapter}:{self.domain}"


def _mask_to_prefix(mask: str) -> int | None:
    if not mask:
        return None
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except (ValueError, ipaddress.NetmaskValueError):
        return None


def _widest_subnet(local_ips: list) -> tuple:
    """Return (ip, prefix_len) for the entry with the smallest (widest) prefix."""
    best_ip, best_prefix = "", 24
    for entry in local_ips:
        prefix = _mask_to_prefix(entry.get("mask", ""))
        if prefix is None:
            continue
        if best_ip == "" or prefix < best_prefix:
            best_ip, best_prefix = entry.get("ip", ""), prefix
    return best_ip, best_prefix


def _find_vpn_adapter(adapters: list) -> str:
    for adapter in adapters:
        if not adapter.get("connected") or not adapter.get("ipv4"):
            continue
        name = adapter.get("name", "")
        lname = name.lower()
        if any(kw in lname for kw in _VPN_KEYWORDS):
            return name
    return ""


def _subnet_hosts_for(prefix_len: int) -> int:
    if prefix_len >= 31:
        return 0
    return (2 ** (32 - prefix_len)) - 2


def _sweep_coverage_note(prefix_len: int) -> str:
    """L5: honesty note for when the pre-scan ping sweep only covers a /24 (fast,
    unchanged since before this sprint) inside a real subnet that is wider than
    that. Devices already in this PC's ARP/DHCP history are unaffected — this is
    about addresses the sweep never actively pings, not about scope exclusion."""
    return (
        f"NetSentinel actively pings the 254 addresses closest to yours by default "
        f"(your network is a /{prefix_len}) — devices already known to this PC are "
        "still found; others may not appear until reached directly."
    )


def _scope_cidr_for(ip: str, prefix_len: int) -> str:
    """The real local subnet CIDR containing *ip* — deliberately NOT capped to /24.
    A flat corporate L2 keeps its full width so every device on it is still in
    scope; only a genuinely different subnet is ever excluded by a caller that
    partitions ARP entries against this value (L5)."""
    if not ip:
        return ""
    try:
        return str(ipaddress.ip_network(f"{ip}/{prefix_len}", strict=False))
    except ValueError:
        return ""


def partition_by_scope(pairs: list, scope_cidr: str) -> tuple:
    """
    Split a list of (ip, mac) pairs into (in_scope, out_of_scope) by whether ip
    falls inside scope_cidr (L5). A blank or unparseable scope_cidr FAILS OPEN —
    every pair comes back in_scope — matching the "no scope given" meaning used
    by every caller (rogue_device.scan()'s scope_cidr=None default). An
    unparseable ip within the pairs is treated as out_of_scope: scope membership
    must be positively confirmed, never assumed.
    """
    if not scope_cidr:
        return list(pairs), []
    try:
        network = ipaddress.ip_network(scope_cidr, strict=False)
    except ValueError:
        return list(pairs), []

    in_scope: list = []
    out_of_scope: list = []
    for ip, mac in pairs:
        try:
            is_in = ipaddress.ip_address(ip) in network
        except ValueError:
            is_in = False
        (in_scope if is_in else out_of_scope).append((ip, mac))
    return in_scope, out_of_scope


def network_fingerprint(net_info: dict = None, arp_snapshot: dict = None) -> str:
    """
    Identify the physical network for the L6 authorization gate — keyed by
    gateway MAC + subnet, deliberately separate from NetworkEnvironment.fingerprint()
    (kind:vpn_adapter:domain). Two different physical "home" networks must be
    asked about authorization separately even though they'd share the same
    environment-kind fingerprint.

    Falls back to the gateway IP when its MAC isn't in the ARP snapshot yet, and
    to the literal "unknown" when there is no gateway at all — still usable as a
    (weaker) fingerprint rather than raising.
    """
    if net_info is None:
        net_info = get_network_info()
    if arp_snapshot is None:
        arp_snapshot = get_arp_snapshot()

    local_ips = net_info.get("local_ips") or []
    wide_ip, prefix_len = _widest_subnet(local_ips)
    subnet_cidr = _scope_cidr_for(wide_ip, prefix_len)

    gateway_ip = net_info.get("gateway") or ""
    gateway_mac = (arp_snapshot or {}).get(gateway_ip, "") if gateway_ip else ""
    identity = gateway_mac or gateway_ip or "unknown"
    return f"{identity}@{subnet_cidr}"


def detect_environment(net_info: dict = None, adapters: list = None) -> NetworkEnvironment:
    """
    Classify the current network. Both parameters are injectable so tests never touch the
    real machine; production callers pass nothing and this function calls the existing
    utils_net helpers itself.
    """
    if net_info is None:
        net_info = get_network_info()
    if adapters is None:
        adapters = get_interface_details()

    domain = (net_info.get("domain") or "").strip()
    local_ips = net_info.get("local_ips") or []
    wide_ip, prefix_len = _widest_subnet(local_ips)
    subnet_hosts = _subnet_hosts_for(prefix_len)
    is_wide = prefix_len < 24
    is_10x = wide_ip.startswith("10.")
    scope_cidr = _scope_cidr_for(wide_ip, prefix_len)

    vpn_adapter = _find_vpn_adapter(adapters)

    if vpn_adapter:
        reasons = [f"Active VPN adapter detected: {vpn_adapter}"]
        if domain:
            reasons.append(f"Windows domain membership detected: {domain}")
        effects = [
            "Device names may be missing — VPNs usually block the reverse-DNS and "
            + "NetBIOS lookups NetSentinel uses.",
            "Some security scans need to reach devices directly and may report "
            + "nothing through the tunnel.",
        ]
        if is_wide:
            effects.append(
                f"This network is large (up to ~{subnet_hosts} addresses), so a full "
                "scan can take minutes, not seconds."
            )
            effects.append(_sweep_coverage_note(prefix_len))
        return NetworkEnvironment(
            kind="vpn", confidence="high", title=f"VPN detected: {vpn_adapter}",
            reasons=reasons, effects=effects, vpn_adapter=vpn_adapter, domain=domain,
            prefix_len=prefix_len, subnet_hosts=subnet_hosts, scope_cidr=scope_cidr,
        )

    corporate_signal = bool(domain) or (is_10x and is_wide)
    if corporate_signal:
        reasons = []
        if domain:
            reasons.append(f"Windows domain membership detected: {domain}")
        if is_10x and is_wide:
            reasons.append(f"Wide private subnet detected: /{prefix_len} (10.0.0.0/8)")
        effects = [
            "Device names may be missing — corporate DNS/NetBIOS lookups are often "
            "restricted for non-domain tools.",
            f"This network is large (up to ~{subnet_hosts} addresses), so a full scan "
            "can take minutes, not seconds.",
        ]
        if is_wide:
            effects.append(_sweep_coverage_note(prefix_len))
        title = f"Corporate network detected ({domain})" if domain else \
            "Corporate-style large network detected"
        return NetworkEnvironment(
            kind="corporate", confidence="high" if domain else "medium", title=title,
            reasons=reasons, effects=effects, vpn_adapter="", domain=domain,
            prefix_len=prefix_len, subnet_hosts=subnet_hosts, scope_cidr=scope_cidr,
        )

    if is_wide:
        reasons = [f"Subnet is wider than a typical home /24: /{prefix_len}"]
        effects = [
            f"This network is large (up to ~{subnet_hosts} addresses), so a full scan "
            "can take minutes, not seconds.",
            "The Network Map may group devices by subnet rather than showing every "
            "device individually.",
            _sweep_coverage_note(prefix_len),
        ]
        return NetworkEnvironment(
            kind="large_subnet", confidence="medium",
            title=f"Large network detected (/{prefix_len})",
            reasons=reasons, effects=effects, vpn_adapter="", domain=domain,
            prefix_len=prefix_len, subnet_hosts=subnet_hosts, scope_cidr=scope_cidr,
        )

    return NetworkEnvironment(
        kind="home", confidence="high", title="", reasons=[], effects=[],
        vpn_adapter="", domain=domain, prefix_len=prefix_len, subnet_hosts=subnet_hosts,
        scope_cidr=scope_cidr,
    )
