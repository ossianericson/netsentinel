"""
protocol_animator_extra — five additional protocol scene builders.

Extends protocol_animator.py with: OSPF Hello/LSA, NAT address translation,
VLAN 802.1Q tagging, TLS 1.3 handshake, ICMP traceroute.

Uses the same AnimNode/AnimStep/ProtocolSceneData data contracts.
No PyQt imports.  All builders are pure functions.
"""
from __future__ import annotations

from modules.protocol_animator import (
    AnimNode,
    AnimStep,
    ProtocolSceneData,
    _hostname,
    _local_ip,
    _short_ip,
)


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
        ),
    ]

    return ProtocolSceneData(
        "VLAN", "VLAN Tagging (802.1Q)",
        "Conceptual illustration — two switches, VLAN 10 end-to-end with trunk tagging",
        nodes, steps,
    )


# ── TLS 1.3 Handshake ──────────────────────────────────────────────────────────

def build_tls_scene(net_info: dict, devices: list) -> ProtocolSceneData:  # noqa: ARG001
    my_ip   = _local_ip(net_info)
    my_name = _hostname()
    target_ip = net_info.get("gateway", "93.184.216.34")

    nodes = [
        AnimNode("client", f"{my_name}\n{_short_ip(my_ip)}",         "client", 0.15, 0.5),
        AnimNode("server", f"HTTPS Server\n{_short_ip(target_ip)}:443", "server", 0.85, 0.5),
    ]

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
        ),
    ]

    return ProtocolSceneData(
        "ICMP", "ICMP Traceroute",
        "Conceptual illustration — your gateway is hop 1; hop 2 is illustrative",
        nodes, steps,
    )
