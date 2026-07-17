"""
protocol_animator — builds ProtocolSceneData for the interactive protocol visualizer.

Five builder functions, one per protocol.  Each reads from data that the dashboard
already holds in memory (net_info, scan results, MetricStore) — no new network calls.

ARP and DNS are populated from last-scan data.
TCP and DHCP are conceptual illustrations using your network's real addresses.
STP uses last STP scan BPDUs when available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from modules.protocol_frames import (
    FrameLayer,
    ethernet_layer,
    find_mac_for_ip,
    ipv4_layer,
    tcp_layer,
    udp_layer,
)


# ── Data contracts ─────────────────────────────────────────────────────────────

@dataclass
class AnimNode:
    id:    str    # unique key referenced by AnimStep.from_node / to_node
    label: str    # display name, may contain \n for two lines
    role:  str    # "client" | "gateway" | "dns" | "server" | "broadcast" | "switch" | "root"
    x:     float  # 0.0–1.0 relative horizontal position in the canvas
    y:     float  # 0.0–1.0 relative vertical position


@dataclass
class AnimStep:
    from_node:    str
    to_node:      str
    packet_label: str   # short name drawn on the moving dot, e.g. "ARP Request"
    frame_detail: str   # one-liner shown under the packet label
    explanation:  str   # 2–3 sentences in the description panel below the canvas
    is_broadcast: bool = False   # dashed arrow
    is_reply:     bool = False   # green dot instead of blue
    layers: List[FrameLayer] = field(default_factory=list)   # Frame Anatomy inspector (Phase A2)


@dataclass
class ProtocolSceneData:
    protocol:         str
    title:            str
    subtitle:         str            # data provenance shown in grey below the title
    nodes:            List[AnimNode]
    steps:            List[AnimStep]
    missing_data_msg: str = ""       # non-empty → show placeholder, skip canvas


# ── Helpers ────────────────────────────────────────────────────────────────────

def _short_ip(ip: str) -> str:
    return ip or "?.?.?.?"


def _short_mac(mac: str) -> str:
    return (mac or "??:??:??:??:??:??").upper()


def _local_ip(net_info: dict) -> str:
    ips = net_info.get("local_ips", [])
    if ips and isinstance(ips[0], dict):
        return ips[0].get("ip", "")
    return ips[0] if ips else ""


def _hostname() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "This device"


# ── ARP Resolution ─────────────────────────────────────────────────────────────

def build_arp_scene(net_info: dict, devices: list) -> ProtocolSceneData:
    gw_ip  = net_info.get("gateway", "")
    gw_mac = net_info.get("gateway_mac", "")
    my_ip  = _local_ip(net_info)
    my_name = _hostname()

    if not gw_ip or not my_ip:
        return ProtocolSceneData(
            protocol="ARP", title="ARP Resolution", subtitle="",
            nodes=[], steps=[],
            missing_data_msg="Run a network scan first to populate gateway and local IP.",
        )

    nodes = [
        AnimNode("client",    f"{my_name}\n{_short_ip(my_ip)}",         "client",    0.1, 0.5),
        AnimNode("broadcast", "Network broadcast\nff:ff:ff:ff:ff:ff:ff", "broadcast", 0.5, 0.5),
        AnimNode("gateway",   f"Gateway / Router\n{_short_ip(gw_ip)}",  "gateway",   0.9, 0.5),
    ]

    my_mac = find_mac_for_ip(devices, my_ip)

    steps = [
        AnimStep(
            from_node="client", to_node="broadcast",
            packet_label="ARP Request",
            frame_detail=f"Who has {gw_ip}? Tell {my_ip}",
            explanation=(
                f"Your device ({my_ip}) needs to send a packet to the gateway but doesn't know its "
                f"MAC address yet. It broadcasts an ARP Request to every device on the subnet — "
                f"\"Who has {gw_ip}? Tell me your hardware address.\""
            ),
            is_broadcast=True,
            layers=[
                ethernet_layer(my_mac, "FF:FF:FF:FF:FF:FF", "0x0806", "ARP"),
                FrameLayer("ARP", [
                    ("Opcode", "1 (Request)"),
                    ("Sender MAC", _short_mac(my_mac)),
                    ("Sender IP", _short_ip(my_ip)),
                    ("Target MAC", "00:00:00:00:00:00"),
                    ("Target IP", _short_ip(gw_ip)),
                ]),
            ],
        ),
        AnimStep(
            from_node="gateway", to_node="client",
            packet_label="ARP Reply",
            frame_detail=f"{gw_ip} is at {_short_mac(gw_mac)}",
            explanation=(
                f"The gateway ({gw_ip}) recognises its own IP and replies directly (unicast) to your "
                f"device with its MAC address: {_short_mac(gw_mac)}. "
                f"Your device caches this mapping in its ARP table so future packets go directly."
            ),
            is_reply=True,
            layers=[
                ethernet_layer(gw_mac, my_mac, "0x0806", "ARP"),
                FrameLayer("ARP", [
                    ("Opcode", "2 (Reply)"),
                    ("Sender MAC", _short_mac(gw_mac)),
                    ("Sender IP", _short_ip(gw_ip)),
                    ("Target MAC", _short_mac(my_mac)),
                    ("Target IP", _short_ip(my_ip)),
                ]),
            ],
        ),
    ]

    subtitle = "Using your last scan data"
    return ProtocolSceneData("ARP", "ARP Resolution", subtitle, nodes, steps)


# ── DNS Lookup ─────────────────────────────────────────────────────────────────

def build_dns_scene(net_info: dict, diag_result: Any) -> ProtocolSceneData:
    my_ip  = _local_ip(net_info)
    my_name = _hostname()

    dns_servers = net_info.get("dns_servers", [])
    resolver_ip = dns_servers[0] if dns_servers else ""

    latency_ms = None
    if diag_result and hasattr(diag_result, "dns_results") and diag_result.dns_results:
        for dr in diag_result.dns_results:
            if dr.status == "OK" and dr.latency_ms > 0:
                latency_ms = dr.latency_ms
                if dr.server and dr.server != "System DNS":
                    resolver_ip = resolver_ip or dr.server
                break

    resolver_label = f"DNS Resolver\n{_short_ip(resolver_ip)}" if resolver_ip else "DNS Resolver\n(system configured)"
    latency_str = f" ({latency_ms:.0f} ms)" if latency_ms else ""

    nodes = [
        AnimNode("client",   f"{my_name}\n{_short_ip(my_ip)}",  "client",  0.1, 0.5),
        AnimNode("resolver", resolver_label,                      "dns",     0.5, 0.5),
        AnimNode("upstream", "Authoritative DNS\n(Internet)",    "server",  0.9, 0.5),
    ]

    _CLIENT_PORT = 51820
    _upstream_ip = "198.41.0.4"   # a.root-servers.net — RFC-representative root server

    steps = [
        AnimStep(
            from_node="client", to_node="resolver",
            packet_label="DNS Query",
            frame_detail="A example.com?",
            explanation=(
                f"Your device asks its configured DNS resolver ({resolver_ip or 'system DNS'}) "
                f"to translate a domain name into an IP address. "
                f"This uses UDP port 53 and takes only one round-trip if the resolver has a cached answer."
            ),
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(my_ip, resolver_ip, proto="17 (UDP)"),
                udp_layer(_CLIENT_PORT, 53),
                FrameLayer("DNS", [
                    ("Transaction ID", "0x1a2b"),
                    ("Flags", "Standard query"),
                    ("Questions", "A example.com"),
                ]),
            ],
        ),
        AnimStep(
            from_node="resolver", to_node="upstream",
            packet_label="Recursive Query",
            frame_detail="Who is authoritative for example.com?",
            explanation=(
                "If the resolver doesn't have the answer cached, it queries the authoritative name servers "
                "for the domain — first the root servers (.com), then the domain's own name servers. "
                "This happens transparently; your device just waits for the resolver to come back."
            ),
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(resolver_ip, _upstream_ip, proto="17 (UDP)"),
                udp_layer(53, 53),
                FrameLayer("DNS", [
                    ("Transaction ID", "0x3c9f"),
                    ("Flags", "Standard query (recursion desired: 0)"),
                    ("Questions", "A example.com"),
                ]),
            ],
        ),
        AnimStep(
            from_node="upstream", to_node="resolver",
            packet_label="DNS Response",
            frame_detail="example.com = 93.184.216.34  TTL 3600",
            explanation=(
                "The authoritative server returns the IP address and a TTL (time to live). "
                "The resolver caches this answer for the TTL duration — so repeat lookups are instant. "
                "A short TTL means the record changes often; a long TTL means it's stable."
            ),
            is_reply=True,
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(_upstream_ip, resolver_ip, proto="17 (UDP)"),
                udp_layer(53, 53),
                FrameLayer("DNS", [
                    ("Transaction ID", "0x3c9f"),
                    ("Flags", "Standard query response, No error"),
                    ("Answers", "example.com A 93.184.216.34 TTL 3600"),
                ]),
            ],
        ),
        AnimStep(
            from_node="resolver", to_node="client",
            packet_label="DNS Response",
            frame_detail=f"93.184.216.34{latency_str}",
            explanation=(
                f"The resolver forwards the answer back to your device{latency_str}. "
                f"Your device's OS caches it locally and the application can now open a TCP connection "
                f"to 93.184.216.34 directly — the domain name is no longer needed."
            ),
            is_reply=True,
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(resolver_ip, my_ip, proto="17 (UDP)"),
                udp_layer(53, _CLIENT_PORT),
                FrameLayer("DNS", [
                    ("Transaction ID", "0x1a2b"),
                    ("Flags", "Standard query response, No error"),
                    ("Answers", f"example.com A 93.184.216.34{latency_str}"),
                ]),
            ],
        ),
    ]

    subtitle = "Using your last diagnostics data" if diag_result else "Conceptual illustration using your network's addresses"
    return ProtocolSceneData("DNS", "DNS Lookup", subtitle, nodes, steps)


# ── TCP Three-Way Handshake ────────────────────────────────────────────────────

def build_tcp_scene(net_info: dict, devices: list) -> ProtocolSceneData:
    my_ip   = _local_ip(net_info)
    my_name = _hostname()

    target_ip   = ""
    target_name = "Web Server"
    for d in (devices or []):
        ip = d.get("ip", "") if isinstance(d, dict) else getattr(d, "ip", "")
        if ip and ip != my_ip:
            hn = d.get("hostname", "") if isinstance(d, dict) else getattr(d, "hostname", "")
            target_ip   = ip
            target_name = hn or "Remote Host"
            break
    if not target_ip:
        target_ip = net_info.get("gateway", "93.184.216.34")

    nodes = [
        AnimNode("client", f"{my_name}\n{_short_ip(my_ip)}", "client", 0.1, 0.5),
        AnimNode("server", f"{target_name}\n{_short_ip(target_ip)}", "server", 0.9, 0.5),
    ]

    my_mac     = find_mac_for_ip(devices, my_ip)
    target_mac = find_mac_for_ip(devices, target_ip)
    _CLIENT_PORT = 49152

    steps = [
        AnimStep(
            from_node="client", to_node="server",
            packet_label="SYN",
            frame_detail=f"Seq=0  SYN  src:{my_ip}:49152  dst:{target_ip}:443",
            explanation=(
                f"Your device opens a TCP connection by sending a SYN (synchronise) packet with a random "
                f"sequence number. This says: \"I want to connect, and my starting sequence number is X.\" "
                f"The server must reply before any data can flow."
            ),
            layers=[
                ethernet_layer(my_mac, target_mac, "0x0800", "IPv4"),
                ipv4_layer(my_ip, target_ip, proto="6 (TCP)"),
                tcp_layer(_CLIENT_PORT, 443, "SYN", seq=0),
            ],
        ),
        AnimStep(
            from_node="server", to_node="client",
            packet_label="SYN-ACK",
            frame_detail=f"Seq=0  ACK=1  SYN  src:{target_ip}:443  dst:{my_ip}:49152",
            explanation=(
                "The server acknowledges your SYN and sends its own SYN back in the same packet. "
                "ACK=1 means \"I received your byte 0\"; the server's own Seq=0 starts its sequence. "
                "This simultaneously confirms receipt and initiates the server's side of the connection."
            ),
            is_reply=True,
            layers=[
                ethernet_layer(target_mac, my_mac, "0x0800", "IPv4"),
                ipv4_layer(target_ip, my_ip, proto="6 (TCP)"),
                tcp_layer(443, _CLIENT_PORT, "SYN,ACK", seq=0, ack=1),
            ],
        ),
        AnimStep(
            from_node="client", to_node="server",
            packet_label="ACK",
            frame_detail=f"Seq=1  ACK=1  src:{my_ip}:49152  dst:{target_ip}:443",
            explanation=(
                "Your device acknowledges the server's SYN. Both sides now know the other is ready. "
                "The connection is established — data (HTTP request, TLS handshake, etc.) flows next. "
                "This three-step process takes exactly one round-trip time (RTT) to complete."
            ),
            layers=[
                ethernet_layer(my_mac, target_mac, "0x0800", "IPv4"),
                ipv4_layer(my_ip, target_ip, proto="6 (TCP)"),
                tcp_layer(_CLIENT_PORT, 443, "ACK", seq=1, ack=1),
            ],
        ),
    ]

    return ProtocolSceneData(
        "TCP", "TCP Three-Way Handshake",
        "Conceptual illustration using your network's addresses",
        nodes, steps,
    )


# ── DHCP Lease ─────────────────────────────────────────────────────────────────

def build_dhcp_scene(net_info: dict) -> ProtocolSceneData:
    my_name   = _hostname()
    gw_ip     = net_info.get("gateway", "192.168.1.1")
    dns_list  = net_info.get("dns_servers", [gw_ip])
    dns_str   = ", ".join(dns_list[:2]) if dns_list else gw_ip
    offered_ip = _local_ip(net_info) or "192.168.1.x"

    nodes = [
        AnimNode("client",      f"{my_name}\n(no IP yet)",          "client",    0.1, 0.5),
        AnimNode("broadcast",   "Network broadcast\n255.255.255.255","broadcast", 0.5, 0.5),
        AnimNode("dhcp_server", f"DHCP Server\n{_short_ip(gw_ip)}", "gateway",   0.9, 0.5),
    ]

    _XID = "0x3903f326"   # illustrative DHCP transaction ID, held constant across the DORA exchange

    steps = [
        AnimStep(
            from_node="client", to_node="broadcast",
            packet_label="DHCPDISCOVER",
            frame_detail="src:0.0.0.0  dst:255.255.255.255  port:68→67",
            explanation=(
                "When your device joins the network it has no IP address. It broadcasts a DHCPDISCOVER "
                "from 0.0.0.0 to 255.255.255.255 on UDP port 67 — visible to every device on the subnet. "
                "Any DHCP server that hears this will respond with an offer."
            ),
            is_broadcast=True,
            layers=[
                ethernet_layer("", "FF:FF:FF:FF:FF:FF", "0x0800", "IPv4"),
                ipv4_layer("0.0.0.0", "255.255.255.255", proto="17 (UDP)"),
                udp_layer(68, 67),
                FrameLayer("DHCP", [
                    ("Op", "1 (BOOTREQUEST)"),
                    ("Transaction ID", _XID),
                    ("Client MAC", _short_mac("")),
                    ("Message Type", "53 = DHCPDISCOVER"),
                ]),
            ],
        ),
        AnimStep(
            from_node="dhcp_server", to_node="client",
            packet_label="DHCPOFFER",
            frame_detail=f"Offered IP: {offered_ip}  Gateway: {gw_ip}  DNS: {dns_str}",
            explanation=(
                f"The DHCP server ({gw_ip}) reserves an address and sends an OFFER containing the proposed "
                f"IP ({offered_ip}), the subnet mask, default gateway, DNS servers, and lease duration. "
                f"If multiple servers respond, the client uses the first offer received."
            ),
            is_reply=True,
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(gw_ip, "255.255.255.255", proto="17 (UDP)"),
                udp_layer(67, 68),
                FrameLayer("DHCP", [
                    ("Op", "2 (BOOTREPLY)"),
                    ("Transaction ID", _XID),
                    ("Your IP", _short_ip(offered_ip)),
                    ("Server IP", _short_ip(gw_ip)),
                    ("Message Type", "2 = DHCPOFFER"),
                ]),
            ],
        ),
        AnimStep(
            from_node="client", to_node="broadcast",
            packet_label="DHCPREQUEST",
            frame_detail=f"Requesting {offered_ip} from {gw_ip}",
            explanation=(
                f"Your device broadcasts a REQUEST to formally accept the offered IP. "
                f"Broadcasting — rather than unicasting back — lets other DHCP servers know their offers "
                f"were declined, so they can release their reserved addresses."
            ),
            is_broadcast=True,
            layers=[
                ethernet_layer("", "FF:FF:FF:FF:FF:FF", "0x0800", "IPv4"),
                ipv4_layer("0.0.0.0", "255.255.255.255", proto="17 (UDP)"),
                udp_layer(68, 67),
                FrameLayer("DHCP", [
                    ("Op", "1 (BOOTREQUEST)"),
                    ("Transaction ID", _XID),
                    ("Requested IP", _short_ip(offered_ip)),
                    ("Server Identifier", _short_ip(gw_ip)),
                    ("Message Type", "53 = DHCPREQUEST"),
                ]),
            ],
        ),
        AnimStep(
            from_node="dhcp_server", to_node="client",
            packet_label="DHCPACK",
            frame_detail=f"Confirmed: {offered_ip}  Lease: 24 h",
            explanation=(
                f"The server sends a final ACK confirming the lease. Your device configures its interface "
                f"with {offered_ip} and is now fully connected. The lease will be renewed automatically "
                f"at 50% of the lease time — typically without any disruption."
            ),
            is_reply=True,
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(gw_ip, offered_ip, proto="17 (UDP)"),
                udp_layer(67, 68),
                FrameLayer("DHCP", [
                    ("Op", "2 (BOOTREPLY)"),
                    ("Transaction ID", _XID),
                    ("Your IP", _short_ip(offered_ip)),
                    ("Lease Time", "86400 s (24 h)"),
                    ("Message Type", "5 = DHCPACK"),
                ]),
            ],
        ),
    ]

    return ProtocolSceneData(
        "DHCP", "DHCP Lease (DORA)",
        "Conceptual illustration using your network's addresses",
        nodes, steps,
    )


# ── STP Election ───────────────────────────────────────────────────────────────

def build_stp_scene(m2_result: Optional[dict]) -> ProtocolSceneData:
    bpdus = []
    if m2_result and isinstance(m2_result, dict):
        bpdus = m2_result.get("bpdus", [])

    if not bpdus:
        root_mac      = "00:11:22:33:44:00"
        root_priority = 32768
        sw_a_mac      = "00:11:22:33:44:01"
        sw_b_mac      = "00:11:22:33:44:02"
        subtitle = "Conceptual illustration — run STP Scan in Security for live data"
    else:
        b0 = bpdus[0]
        root_mac      = b0.get("root_mac",      "00:11:22:33:44:00") if isinstance(b0, dict) else getattr(b0, "root_mac", "00:11:22:33:44:00")
        root_priority = b0.get("root_priority", 32768)               if isinstance(b0, dict) else getattr(b0, "root_priority", 32768)
        macs = list({
            (b.get("src_mac") if isinstance(b, dict) else getattr(b, "src_mac", "")) for b in bpdus
        } - {root_mac})
        sw_a_mac = macs[0] if len(macs) > 0 else "00:11:22:33:44:01"
        sw_b_mac = macs[1] if len(macs) > 1 else "00:11:22:33:44:02"
        subtitle = f"Using your last STP scan — {len(bpdus)} BPDUs captured"

    nodes = [
        AnimNode("root",   f"Root Bridge\n{root_mac.upper()}\nPriority {root_priority}", "root",   0.5,  0.1),
        AnimNode("sw_a",   f"Switch A\n{sw_a_mac.upper()}",                              "switch", 0.2,  0.7),
        AnimNode("sw_b",   f"Switch B\n{sw_b_mac.upper()}",                              "switch", 0.8,  0.7),
    ]

    _SELF_CLAIM_PRIORITY = 32768   # default bridge priority before the root election settles

    def _bpdu_layer(root_id_mac: str, root_id_priority: int, bridge_id_mac: str,
                     bridge_id_priority: int, cost: int) -> FrameLayer:
        return FrameLayer("802.1D BPDU", [
            ("Root ID", f"{root_id_priority}.{root_id_mac.upper()}"),
            ("Bridge ID", f"{bridge_id_priority}.{bridge_id_mac.upper()}"),
            ("Root Path Cost", str(cost)),
            ("Message Age", "0"),
            ("Max Age", "20"),
            ("Hello Time", "2"),
            ("Forward Delay", "15"),
        ])

    steps = [
        AnimStep(
            from_node="sw_a", to_node="root",
            packet_label="BPDU",
            frame_detail=f"Bridge ID: {sw_a_mac.upper()}  Root Claim: self",
            explanation=(
                "When a switch starts, it assumes it is the root bridge and broadcasts a BPDU "
                "(Bridge Protocol Data Unit) every 2 seconds advertising itself as root. "
                "Every switch on the network does the same — the election begins."
            ),
            is_broadcast=True,
            layers=[
                ethernet_layer(sw_a_mac, "01:80:C2:00:00:00", "LLC 0x42/0x42", "STP BPDU"),
                _bpdu_layer(sw_a_mac, _SELF_CLAIM_PRIORITY, sw_a_mac, _SELF_CLAIM_PRIORITY, 0),
            ],
        ),
        AnimStep(
            from_node="sw_b", to_node="root",
            packet_label="BPDU",
            frame_detail=f"Bridge ID: {sw_b_mac.upper()}  Root Claim: self",
            explanation=(
                "All switches simultaneously advertise themselves as root. "
                "A switch with a lower Bridge ID (priority + MAC) wins. "
                f"The root bridge here has priority {root_priority} — the lowest seen, so it wins."
            ),
            is_broadcast=True,
            layers=[
                ethernet_layer(sw_b_mac, "01:80:C2:00:00:00", "LLC 0x42/0x42", "STP BPDU"),
                _bpdu_layer(sw_b_mac, _SELF_CLAIM_PRIORITY, sw_b_mac, _SELF_CLAIM_PRIORITY, 0),
            ],
        ),
        AnimStep(
            from_node="root", to_node="sw_a",
            packet_label="BPDU (Root)",
            frame_detail=f"Root: {root_mac.upper()}  Cost: 0  Hello: 2 s",
            explanation=(
                f"The elected root bridge ({root_mac.upper()}) now sends BPDUs with Root Path Cost = 0. "
                "Other switches compare received BPDUs to find the cheapest path to root "
                "and set their root port accordingly."
            ),
            is_reply=True,
            layers=[
                ethernet_layer(root_mac, "01:80:C2:00:00:00", "LLC 0x42/0x42", "STP BPDU"),
                _bpdu_layer(root_mac, root_priority, root_mac, root_priority, 0),
            ],
        ),
        AnimStep(
            from_node="root", to_node="sw_b",
            packet_label="BPDU (Root)",
            frame_detail=f"Root: {root_mac.upper()}  Cost: 0  Hello: 2 s",
            explanation=(
                "Each non-root switch elects a root port (best path toward root) and designated ports "
                "(best path away from root on each segment). Redundant links are put into Blocking state — "
                "traffic stops but BPDUs still flow so the topology can recover if a link fails."
            ),
            is_reply=True,
            layers=[
                ethernet_layer(root_mac, "01:80:C2:00:00:00", "LLC 0x42/0x42", "STP BPDU"),
                _bpdu_layer(root_mac, root_priority, root_mac, root_priority, 0),
            ],
        ),
    ]

    return ProtocolSceneData("STP", "STP Root Election", subtitle, nodes, steps)
