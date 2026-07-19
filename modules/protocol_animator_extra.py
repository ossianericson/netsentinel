"""
protocol_animator_extra — five additional protocol scene builders.

Extends protocol_animator.py with: OSPF Hello/LSA, NAT address translation,
VLAN 802.1Q tagging, TLS 1.3 handshake, ICMP traceroute.

Uses the same AnimNode/AnimStep/ProtocolSceneData data contracts.
No PyQt imports.  All builders are pure functions.
"""
from __future__ import annotations

from typing import Any, Optional

from modules.protocol_animator import (
    AnimNode,
    AnimStep,
    FrameLayer,
    ProtocolSceneData,
    _hostname,
    _local_ip,
    _short_ip,
    build_arp_scene,
    build_dhcp_scene,
    build_dns_scene,
    build_stp_scene,
    build_tcp_scene,
)
from modules.protocol_frames import ethernet_layer, find_mac_for_ip, ipv4_layer, tcp_layer, udp_layer


# ── OSPF Hello / LSA Flood ─────────────────────────────────────────────────────

def build_ospf_scene(net_info: dict) -> ProtocolSceneData:
    gw_ip = net_info.get("gateway", "192.168.1.1")
    my_ip = _local_ip(net_info) or "192.168.1.50"

    nodes = [
        AnimNode("router_a", f"Router A\n{_short_ip(my_ip)}",        "client",  0.10, 0.5),
        AnimNode("router_b", f"Router B\n{_short_ip(gw_ip)}",        "gateway", 0.55, 0.5),
        AnimNode("lsdb",     "Link-State DB\n(shared topology)",      "server",  0.90, 0.5),
    ]

    steps = [
        AnimStep(
            from_node="router_a", to_node="router_b",
            packet_label="OSPF Hello",
            frame_detail="Multicast 224.0.0.5  Proto 89  Hello interval: 10 s",
            explanation=(
                f"Router A multicasts an OSPF Hello every 10 s to 224.0.0.5 (AllSPFRouters). "
                f"The Hello carries: Router ID, area ID, hello/dead intervals, and the list of "
                f"known neighbors. When Router B sees itself listed in A's Hello, both confirm "
                f"a two-way relationship and begin the Database Exchange process."
            ),
            is_broadcast=True,
            layers=[
                ethernet_layer("", "01:00:5E:00:00:05", "0x0800", "IPv4"),
                ipv4_layer(my_ip, "224.0.0.5", ttl=1, proto="89 (OSPF)"),
                FrameLayer("OSPF", [
                    ("Type", "1 (Hello)"),
                    ("Router ID", _short_ip(my_ip)),
                    ("Area ID", "0.0.0.0"),
                    ("Hello Interval", "10 s"),
                    ("Dead Interval", "40 s"),
                ]),
            ],
        ),
        AnimStep(
            from_node="router_b", to_node="router_a",
            packet_label="DBD (LSA headers)",
            frame_detail="Database Description  Seq=1  I=1 M=0 MS=1",
            explanation=(
                "Routers exchange Database Description (DBD) packets containing only LSA headers — "
                "type, router ID, and sequence number — not full LSA payloads. "
                "Each router compares the headers against its own database and requests any "
                "missing or stale records via a Link-State Request (LSR)."
            ),
            is_reply=True,
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(gw_ip, my_ip, ttl=1, proto="89 (OSPF)"),
                FrameLayer("OSPF", [
                    ("Type", "2 (DBD)"),
                    ("Sequence", "1"),
                    ("Flags", "I=1 M=0 MS=1"),
                ]),
            ],
        ),
        AnimStep(
            from_node="router_b", to_node="lsdb",
            packet_label="LSU (full LSAs)",
            frame_detail="Router LSA type 1  LS seq=0x80000001  age=0  — flooding area 0",
            explanation=(
                "The Link-State Update (LSU) carries complete LSA records flooding to every router "
                "in the OSPF area. LSAs describe topology elements: router links (type 1), transit "
                "networks (type 2), and external routes (type 5). All routers acknowledge with LSAck "
                "and store the LSAs — the Link-State Database converges when all copies match."
            ),
            layers=[
                ethernet_layer("", "01:00:5E:00:00:05", "0x0800", "IPv4"),
                ipv4_layer(gw_ip, "224.0.0.5", ttl=1, proto="89 (OSPF)"),
                FrameLayer("OSPF", [
                    ("Type", "4 (LSU)"),
                    ("LSA Type", "1 (Router LSA)"),
                    ("LS Sequence", "0x80000001"),
                    ("Age", "0 s"),
                ]),
            ],
        ),
        AnimStep(
            from_node="lsdb", to_node="router_a",
            packet_label="SPF Calculation",
            frame_detail="Dijkstra: LSDB → shortest-path tree → routing table installed",
            explanation=(
                "Once the LSDB is complete, every router independently runs Dijkstra's Shortest "
                "Path First algorithm on the identical database. Because all routers share the same "
                "topology view, they all compute the same result and install consistent next-hop "
                "entries — no routing loops and guaranteed convergence after any topology change."
            ),
            is_reply=True,
            layers=[
                FrameLayer("OSPF", [
                    ("Type", "N/A — internal computation, not a captured frame"),
                ]),
                FrameLayer("SPF Result", [
                    ("Algorithm", "Dijkstra shortest-path-first"),
                    ("Input", "Link-State Database (all received LSAs)"),
                    ("Output", "Shortest-path tree → routing table installed"),
                ]),
            ],
        ),
    ]

    return ProtocolSceneData(
        "OSPF", "OSPF Hello & LSA Flood",
        "Conceptual illustration — gateway used as Router B neighbor",
        nodes, steps,
    )


# ── NAT Address Translation ────────────────────────────────────────────────────

def build_nat_scene(net_info: dict) -> ProtocolSceneData:
    private_ip = _local_ip(net_info) or "192.168.1.50"
    gw_ip      = net_info.get("gateway", "192.168.1.1")
    public_ip  = "203.0.113.1"   # RFC 5737 documentation range
    server_ip  = "93.184.216.34"

    nodes = [
        AnimNode("client", f"Your Device\n{_short_ip(private_ip)}", "client",  0.10, 0.5),
        AnimNode("nat",    f"NAT Router\n{_short_ip(gw_ip)}",       "gateway", 0.50, 0.5),
        AnimNode("server", f"Web Server\n{server_ip}",               "server",  0.90, 0.5),
    ]

    steps = [
        AnimStep(
            from_node="client", to_node="nat",
            packet_label="TCP SYN",
            frame_detail=f"src: {private_ip}:49152  dst: {server_ip}:443",
            explanation=(
                f"Your device ({private_ip}) sends a TCP SYN with a private RFC 1918 source address. "
                f"Private ranges (10.x.x.x, 172.16–31.x.x, 192.168.x.x) are not routable on the "
                f"public internet — the router must rewrite the source before forwarding."
            ),
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(private_ip, server_ip, proto="6 (TCP)"),
                tcp_layer(49152, 443, "SYN", seq=0),
            ],
        ),
        AnimStep(
            from_node="nat", to_node="server",
            packet_label="TCP SYN (translated)",
            frame_detail=f"src: {public_ip}:50001  dst: {server_ip}:443  [NAT table entry added]",
            explanation=(
                f"The NAT router rewrites the source IP from {private_ip} to its public address "
                f"({public_ip}) and assigns a unique public port (50001). It records this mapping "
                f"in the NAT table: {public_ip}:50001 ↔ {private_ip}:49152. "
                f"All return traffic for this flow is de-translated using this entry."
            ),
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(public_ip, server_ip, proto="6 (TCP)"),
                tcp_layer(50001, 443, "SYN", seq=0),
                FrameLayer("NAT Table", [
                    ("Original", f"{private_ip}:49152"),
                    ("Translated", f"{public_ip}:50001"),
                ]),
            ],
        ),
        AnimStep(
            from_node="server", to_node="nat",
            packet_label="TCP SYN-ACK",
            frame_detail=f"src: {server_ip}:443  dst: {public_ip}:50001",
            explanation=(
                f"The server replies to the public address ({public_ip}:50001) — it has no knowledge "
                f"of the private device behind it. This is a feature, not a limitation: NAT provides "
                f"implicit inbound firewall protection because unsolicited inbound packets have no "
                f"NAT table entry and are silently dropped."
            ),
            is_reply=True,
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(server_ip, public_ip, proto="6 (TCP)"),
                tcp_layer(443, 50001, "SYN,ACK", seq=0, ack=1),
            ],
        ),
        AnimStep(
            from_node="nat", to_node="client",
            packet_label="TCP SYN-ACK (de-NAT)",
            frame_detail=f"src: {server_ip}:443  dst: {private_ip}:49152  [NAT table lookup]",
            explanation=(
                f"The router looks up port 50001 in its NAT table, rewrites the destination from "
                f"{public_ip}:50001 back to {private_ip}:49152, and forwards the packet. "
                f"Your device receives it as if the server contacted it directly. "
                f"This is Port Address Translation (PAT/NAPT) — the most common form of NAT."
            ),
            is_reply=True,
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(server_ip, private_ip, proto="6 (TCP)"),
                tcp_layer(443, 49152, "SYN,ACK", seq=0, ack=1),
                FrameLayer("NAT Table", [
                    ("Original", f"{public_ip}:50001"),
                    ("Translated", f"{private_ip}:49152"),
                ]),
            ],
        ),
    ]

    return ProtocolSceneData(
        "NAT", "NAT Address Translation",
        "Conceptual illustration — public IP is representative (RFC 5737)",
        nodes, steps,
    )


# ── VLAN Tagging 802.1Q ────────────────────────────────────────────────────────

def build_vlan_scene(net_info: dict) -> ProtocolSceneData:  # noqa: ARG001
    nodes = [
        AnimNode("pc_a", "PC-A\nVLAN 10  Access Port", "client",  0.05, 0.5),
        AnimNode("sw1",  "Switch 1\nAccess + Trunk",    "switch",  0.35, 0.5),
        AnimNode("sw2",  "Switch 2\nTrunk + Access",    "switch",  0.65, 0.5),
        AnimNode("pc_b", "PC-B\nVLAN 10  Access Port",  "server",  0.95, 0.5),
    ]

    steps = [
        AnimStep(
            from_node="pc_a", to_node="sw1",
            packet_label="Ethernet Frame",
            frame_detail="Untagged  EtherType:0x0800  — enters access port  VLAN 10 assigned",
            explanation=(
                "PC-A sends an ordinary untagged Ethernet frame into its access port. "
                "Access ports belong to exactly one VLAN; the switch assigns VLAN 10 based on "
                "port configuration. End devices never see VLAN tags — only the switch does."
            ),
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                FrameLayer("802.1Q Tag", [
                    ("Status", "Untagged — access port assigns VLAN 10 internally"),
                ]),
            ],
        ),
        AnimStep(
            from_node="sw1", to_node="sw2",
            packet_label="802.1Q Tagged Frame",
            frame_detail="TPID:0x8100  PCP:0  DEI:0  VLAN-ID:10  (4-byte tag inserted after src MAC)",
            explanation=(
                "On exit from the trunk port, Switch 1 inserts a 4-byte 802.1Q tag after the "
                "source MAC address. The tag contains TPID (0x8100), 3 priority bits (PCP), "
                "a Drop Eligibility bit (DEI), and a 12-bit VLAN ID (here: 10). "
                "Tagged frames carry VLAN context across inter-switch trunk links."
            ),
            layers=[
                ethernet_layer("", "", "0x8100", "802.1Q"),
                FrameLayer("802.1Q Tag", [
                    ("TPID", "0x8100"),
                    ("PCP", "0"),
                    ("DEI", "0"),
                    ("VLAN ID", "10"),
                ]),
            ],
        ),
        AnimStep(
            from_node="sw2", to_node="pc_b",
            packet_label="Ethernet Frame (tag stripped)",
            frame_detail="VLAN-ID:10 matched  →  tag removed  →  untagged frame forwarded to access port",
            explanation=(
                "Switch 2 receives the tagged frame on its trunk port, strips the 802.1Q tag, "
                "and forwards the plain Ethernet frame to PC-B's access port (also VLAN 10). "
                "End devices never see the tag — it exists only on trunk links between switches."
            ),
            is_reply=True,
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                FrameLayer("802.1Q Tag", [
                    ("Status", "Tag removed — VLAN 10 matched destination access port"),
                ]),
            ],
        ),
        AnimStep(
            from_node="sw1", to_node="sw2",
            packet_label="VLAN 20 Frame (separate)",
            frame_detail="TPID:0x8100  VLAN-ID:20  — same trunk, different broadcast domain",
            explanation=(
                "A second stream from a VLAN 20 device travels the same trunk link simultaneously. "
                "VLANs are separate broadcast domains — VLAN 10 and VLAN 20 traffic cannot reach "
                "each other directly. Inter-VLAN communication requires a Layer 3 router or an "
                "SVI (Switched Virtual Interface) on a Layer 3 switch."
            ),
            is_broadcast=True,
            layers=[
                ethernet_layer("", "", "0x8100", "802.1Q"),
                FrameLayer("802.1Q Tag", [
                    ("TPID", "0x8100"),
                    ("PCP", "0"),
                    ("DEI", "0"),
                    ("VLAN ID", "20"),
                ]),
            ],
        ),
    ]

    return ProtocolSceneData(
        "VLAN", "VLAN Tagging (802.1Q)",
        "Conceptual illustration — two switches, VLAN 10 end-to-end with trunk tagging",
        nodes, steps,
    )


# ── TLS 1.3 Handshake ──────────────────────────────────────────────────────────

def build_tls_scene(net_info: dict, devices: list) -> ProtocolSceneData:
    my_ip   = _local_ip(net_info)
    my_name = _hostname()
    target_ip = net_info.get("gateway", "93.184.216.34")

    nodes = [
        AnimNode("client", f"{my_name}\n{_short_ip(my_ip)}",         "client", 0.15, 0.5),
        AnimNode("server", f"HTTPS Server\n{_short_ip(target_ip)}:443", "server", 0.85, 0.5),
    ]

    my_mac     = find_mac_for_ip(devices, my_ip)
    target_mac = find_mac_for_ip(devices, target_ip)
    _CLIENT_PORT = 51820

    steps = [
        AnimStep(
            from_node="client", to_node="server",
            packet_label="ClientHello",
            frame_detail="TLS 1.3  cipher suites: AES-256-GCM, ChaCha20  key_share: x25519",
            explanation=(
                "The TLS handshake starts with ClientHello: the highest TLS version supported (1.3), "
                "a list of acceptable cipher suites, and the client's ECDH key_share (public key for "
                "x25519). TLS 1.3 sends key material in the first message — removing a full round trip "
                "vs TLS 1.2 and making 0-RTT session resumption possible."
            ),
            layers=[
                ethernet_layer(my_mac, target_mac, "0x0800", "IPv4"),
                ipv4_layer(my_ip, target_ip, proto="6 (TCP)"),
                tcp_layer(_CLIENT_PORT, 443, "PSH,ACK", seq=1, ack=1),
                FrameLayer("TLS Record", [
                    ("Content Type", "22 (Handshake)"),
                    ("Version", "TLS 1.3"),
                    ("Handshake Type", "1 (ClientHello)"),
                    ("Cipher Suites", "TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256"),
                    ("Key Share", "x25519"),
                ]),
            ],
        ),
        AnimStep(
            from_node="server", to_node="client",
            packet_label="ServerHello + Certificate",
            frame_detail="Chosen: TLS_AES_256_GCM_SHA384  server key_share + cert chain",
            explanation=(
                "The server replies with its chosen cipher suite and its own ECDH key_share. "
                "Both sides now independently derive the same session keys using ECDH — private "
                "keys never leave either machine (perfect forward secrecy). "
                "The certificate chain proves the server's identity, signed by a trusted CA."
            ),
            is_reply=True,
            layers=[
                ethernet_layer(target_mac, my_mac, "0x0800", "IPv4"),
                ipv4_layer(target_ip, my_ip, proto="6 (TCP)"),
                tcp_layer(443, _CLIENT_PORT, "PSH,ACK", seq=1, ack=2),
                FrameLayer("TLS Record", [
                    ("Content Type", "22 (Handshake)"),
                    ("Handshake Type", "2 (ServerHello)"),
                    ("Chosen Cipher", "TLS_AES_256_GCM_SHA384"),
                    ("Key Share", "server x25519 public key"),
                    ("Certificate", "cert chain, signed by trusted CA"),
                ]),
            ],
        ),
        AnimStep(
            from_node="client", to_node="server",
            packet_label="Certificate Verify + Finished",
            frame_detail="[Encrypted]  Client verifies cert chain  →  Finished MAC over transcript",
            explanation=(
                "The client verifies the server's certificate against its trusted root CA store. "
                "If valid, it sends a Finished message — an HMAC over the entire handshake transcript "
                "encrypted with the derived session key. This proves both parties have the same keys "
                "and that no message was altered in transit. The connection is live after this step."
            ),
            layers=[
                ethernet_layer(my_mac, target_mac, "0x0800", "IPv4"),
                ipv4_layer(my_ip, target_ip, proto="6 (TCP)"),
                tcp_layer(_CLIENT_PORT, 443, "PSH,ACK", seq=2, ack=2),
                FrameLayer("TLS Record", [
                    ("Content Type", "22 (Handshake, encrypted)"),
                    ("Handshake Type", "20 (Finished)"),
                    ("Verify Data", "HMAC over full handshake transcript"),
                ]),
            ],
        ),
        AnimStep(
            from_node="server", to_node="client",
            packet_label="Server Finished + App Data",
            frame_detail="[Encrypted]  Handshake complete  1-RTT  Application data begins",
            explanation=(
                "The server sends its own Finished and may begin sending application data immediately. "
                "All subsequent traffic is encrypted with AES-256-GCM or ChaCha20-Poly1305 and "
                "authenticated with SHA-384. TLS 1.3 eliminates RSA key exchange, RC4, and SHA-1 — "
                "every session uses ECDH and therefore achieves perfect forward secrecy by design."
            ),
            is_reply=True,
            layers=[
                ethernet_layer(target_mac, my_mac, "0x0800", "IPv4"),
                ipv4_layer(target_ip, my_ip, proto="6 (TCP)"),
                tcp_layer(443, _CLIENT_PORT, "PSH,ACK", seq=2, ack=3),
                FrameLayer("TLS Record", [
                    ("Content Type", "23 (Application Data)"),
                    ("Handshake Type", "20 (Finished)"),
                    ("Cipher", "AES-256-GCM, authenticated with SHA-384"),
                ]),
            ],
        ),
    ]

    return ProtocolSceneData(
        "TLS", "TLS 1.3 Handshake",
        "Conceptual illustration — 1-RTT ECDH handshake with your gateway as server",
        nodes, steps,
    )


# ── ICMP Traceroute ────────────────────────────────────────────────────────────

def build_icmp_scene(net_info: dict) -> ProtocolSceneData:
    my_ip   = _local_ip(net_info) or "192.168.1.50"
    gw_ip   = net_info.get("gateway", "192.168.1.1")
    hop2_ip = "10.0.0.1"          # illustrative ISP hop
    dest_ip = "93.184.216.34"

    nodes = [
        AnimNode("client", f"Your Device\n{_short_ip(my_ip)}",    "client",  0.05, 0.5),
        AnimNode("hop1",   f"Hop 1 (gateway)\n{_short_ip(gw_ip)}", "gateway", 0.37, 0.5),
        AnimNode("hop2",   f"Hop 2 (ISP)\n{hop2_ip}",              "server",  0.63, 0.5),
        AnimNode("dest",   f"Destination\n{dest_ip}",               "server",  0.92, 0.5),
    ]

    steps = [
        AnimStep(
            from_node="client", to_node="hop1",
            packet_label="Probe  TTL=1",
            frame_detail=f"UDP dst:{dest_ip}:33434  TTL=1  (or ICMP Echo with TTL=1 on Windows)",
            explanation=(
                f"Traceroute sends a probe with TTL=1. The first router ({gw_ip}) decrements TTL "
                f"to 0, discards the packet, and replies with ICMP Time Exceeded (type 11, code 0). "
                f"The elapsed time reveals both the first hop's IP address and the RTT to it."
            ),
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(my_ip, dest_ip, ttl=1, proto="17 (UDP)"),
                udp_layer(33434, 33434),
            ],
        ),
        AnimStep(
            from_node="hop1", to_node="client",
            packet_label="ICMP Time Exceeded",
            frame_detail=f"src: {_short_ip(gw_ip)}  Type 11 Code 0  TTL exceeded in transit",
            explanation=(
                f"Hop 1 ({gw_ip}) sends the ICMP Time Exceeded reply. Traceroute records this IP "
                f"and prints the RTT. It then sends the next probe with TTL=2, which passes through "
                f"hop 1 (TTL→1) and expires at the second router. Each round reveals one more hop."
            ),
            is_reply=True,
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(gw_ip, my_ip, ttl=64, proto="1 (ICMP)"),
                FrameLayer("ICMP", [
                    ("Type", "11 (Time Exceeded)"),
                    ("Code", "0 (TTL exceeded in transit)"),
                    ("Originating Probe TTL", "1"),
                ]),
            ],
        ),
        AnimStep(
            from_node="client", to_node="hop2",
            packet_label="Probe  TTL=2",
            frame_detail=f"UDP dst:{dest_ip}:33435  TTL=2  — expires at hop 2",
            explanation=(
                f"With TTL=2 the probe reaches {hop2_ip} (an ISP router) where TTL→0 again. "
                f"The ISP router returns its own ICMP Time Exceeded, revealing itself. "
                f"Most internet paths have 10–20 hops; each probe adds one TTL increment."
            ),
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(my_ip, dest_ip, ttl=2, proto="17 (UDP)"),
                udp_layer(33435, 33435),
            ],
        ),
        AnimStep(
            from_node="dest", to_node="client",
            packet_label="ICMP Port Unreachable",
            frame_detail=f"src: {dest_ip}  Type 3 Code 3  Port unreachable — trace complete",
            explanation=(
                f"When a probe reaches the destination ({dest_ip}) with TTL > 0, the host has "
                f"no listener on the high UDP port and returns ICMP Port Unreachable (type 3, code 3). "
                f"This signals traceroute is complete. On Windows, probes are ICMP Echo instead of UDP "
                f"— the final reply is then ICMP Echo Reply (type 0) rather than Port Unreachable."
            ),
            is_reply=True,
            layers=[
                ethernet_layer("", "", "0x0800", "IPv4"),
                ipv4_layer(dest_ip, my_ip, ttl=64, proto="1 (ICMP)"),
                FrameLayer("ICMP", [
                    ("Type", "3 (Destination Unreachable)"),
                    ("Code", "3 (Port Unreachable)"),
                ]),
            ],
        ),
    ]

    return ProtocolSceneData(
        "ICMP", "ICMP Traceroute",
        "Conceptual illustration — your gateway is hop 1; hop 2 is illustrative",
        nodes, steps,
    )


# ── Shared dispatch ─────────────────────────────────────────────────────────────
# Lives here (not in protocol_animator.py) because it must reach all ten builders
# and protocol_animator_extra already depends on protocol_animator, not vice versa
# — moving the dispatch into the base module would create a cyclic import.

def build_scene_for_key(
    key: str,
    net_info: dict,
    devices: list,
    diag_result: Any = None,
    m2_result: Optional[dict] = None,
) -> ProtocolSceneData:
    """Build the ProtocolSceneData for any of the ten supported protocol keys.

    Single source of truth for protocol -> builder dispatch, used by both the
    Protocol Visualizer page and the Lab Mode runner (Lab Mode Upgrade Phase L1).
    """
    if key == "ARP":
        return build_arp_scene(net_info, devices)
    elif key == "DNS":
        return build_dns_scene(net_info, diag_result)
    elif key == "TCP":
        return build_tcp_scene(net_info, devices)
    elif key == "DHCP":
        return build_dhcp_scene(net_info)
    elif key == "STP":
        return build_stp_scene(m2_result)
    elif key == "OSPF":
        return build_ospf_scene(net_info)
    elif key == "NAT":
        return build_nat_scene(net_info)
    elif key == "VLAN":
        return build_vlan_scene(net_info)
    elif key == "TLS":
        return build_tls_scene(net_info, devices)
    elif key == "ICMP":
        return build_icmp_scene(net_info)
    return build_arp_scene(net_info, devices)
