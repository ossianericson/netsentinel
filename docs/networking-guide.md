# Networking Concepts: A Practical Guide

This guide explains the networking concepts that NetSentinel monitors and reports on. It is written for curious people who are not networking experts — think of it as a knowledgeable friend explaining things over coffee. No jargon left unexplained, no hand-waving.

---

## Contents

1. [How your home network works](#1-how-your-home-network-works)
2. [How network scanning works](#2-how-network-scanning-works)
3. [Reading RTT and latency](#3-reading-rtt-and-latency)
4. [Spanning Tree Protocol and rogue bridges](#4-spanning-tree-protocol-and-rogue-bridges)
5. [ARP spoofing and man-in-the-middle attacks](#5-arp-spoofing-and-man-in-the-middle-attacks)
6. [Broadcast storms](#6-broadcast-storms)
7. [DNS — why speed matters and what a DNS leak is](#7-dns--why-speed-matters-and-what-a-dns-leak-is)
8. [Open ports and port scanning](#8-open-ports-and-port-scanning)
9. [Tools in NetSentinel](#tools-in-netsentinel)

---

## 1. How your home network works

Your router is doing two jobs at once: it is a gateway to the internet (WAN side) and a local traffic manager (LAN side).

On the WAN side, your ISP assigns your router a single public IP address — something like `84.23.101.55`. Everything leaving your house uses that one address. On the LAN side, your router creates a private network, typically in the `192.168.x.x` or `10.0.x.x` range, and assigns each device its own local IP via **DHCP** (Dynamic Host Configuration Protocol). DHCP is just an automatic "here is your temporary address" system — your laptop asks, the router answers.

There are two kinds of addresses in use simultaneously:

- **IP address** — a logical address that can change (DHCP hands out a different one if you reconnect). This is like a house number.
- **MAC address** — a hardware address burned into the network adapter at the factory. It does not change. This is like a serial number.

Within your LAN, devices use MAC addresses to actually reach each other. When your laptop wants to talk to `192.168.1.1` (your router), it first has to find out *which* physical device owns that IP — it does this via ARP (covered in section 2).

**DNS** (Domain Name System) translates human-readable names into IP addresses. When you type `google.com`, your device asks a DNS server "what IP is that?" and gets back `142.250.x.x`. By default, your router's IP is used as the DNS server, and it forwards queries to your ISP's resolvers. This lookup happens before every new connection, which is why a slow or broken DNS makes the whole internet feel sluggish even when the actual download speeds are fine.

---

## 2. How network scanning works

Before any device can send data to another device on the same network, it needs to map an IP address to a MAC address. The protocol that does this is called **ARP** — Address Resolution Protocol.

It works like this: a device broadcasts a message to the entire network: "Hey, who has IP `192.168.1.1`? Tell me your MAC address." The device that owns that IP replies privately: "That's me — my MAC is `aa:bb:cc:dd:ee:ff`." The sender caches this mapping in its ARP table so it does not have to ask again for a while.

Network scanning exploits exactly this mechanism. Instead of waiting for devices to announce themselves, a scanner sends ARP requests for every IP in the subnet — `192.168.1.1`, `192.168.1.2`, all the way to `192.168.1.254`. Any device that is online responds. The scanner collects all the MAC addresses and can then look them up against a vendor database (the first three bytes of a MAC identify the manufacturer) to figure out what kind of device responded.

This is how NetSentinel builds its device list. ARP scanning is reliable, fast, and works without administrator privileges on most systems because it operates at Layer 2 — the same layer your router uses constantly. It only sees devices on your local subnet; it cannot scan across the internet or through a router boundary.

The device list you see in the "Devices on Network" tab is the result of this ARP sweep, enriched with hostname lookups, vendor data, and OUI-based model inference.

---

## 3. Reading RTT and latency

**RTT** (Round-Trip Time) is how long it takes a packet to travel from your machine to a destination and back. It is measured in milliseconds (ms). When NetSentinel pings `8.8.8.8` and reports `12 ms`, it means the packet crossed your LAN, went through your router, traversed the internet to Google's server, and came back in 12 milliseconds.

What these numbers mean in practice:

| RTT to internet | Interpretation |
|---|---|
| < 20 ms | Excellent — no perceptible delay for any use |
| 20–50 ms | Good — fine for gaming, VoIP, video calls |
| 50–100 ms | Acceptable — noticeable delay in competitive gaming; VoIP still fine |
| 100–200 ms | Poor — VoIP callers may notice; gaming impacted |
| > 200 ms | Bad — conversations have awkward pauses; games feel unresponsive |

**Jitter** is the variation in RTT between consecutive packets. If your RTTs are `15 ms, 14 ms, 16 ms, 15 ms`, jitter is near zero — good. If they are `15 ms, 80 ms, 12 ms, 120 ms`, jitter is high — bad. Jitter matters more than raw latency for real-time applications.

Why does jitter matter for VoIP and gaming? Your voice app receives audio packets and plays them out. If packets arrive at irregular intervals, the app either introduces a buffer (which adds latency) or plays gaps (which makes your voice sound choppy). For gaming, high jitter means the server's view of your position disagrees with yours — rubber-banding, teleporting, and being shot "around corners."

RTT spikes to values like `350 ms, 500 ms, 1200 ms` that appear every 30 seconds are a classic signature of STP reconvergence — your network is briefly rebuilding its forwarding table. This is covered in the next section.

---

## 4. Spanning Tree Protocol and rogue bridges

### Why STP exists

Ethernet networks have a problem: loops. If you connect switch A to switch B with two cables (for redundancy), broadcast frames circulate forever between them — a broadcast storm (section 6). Spanning Tree Protocol (STP) solves this by having all the switches on a network elect a "root bridge" and then logically block any port that would create a loop. The result is a loop-free tree topology. Some ports are in "forwarding" state (traffic flows); others are in "blocking" state (held in reserve for failover).

### The 30-second drop

When the spanning tree topology changes — because a device joins or leaves, or the root bridge changes — all switches must recalculate the tree. During this reconvergence, some ports go through a sequence of states: blocking → listening → learning → forwarding. In classic STP (802.1D), each transition takes 15 seconds by default, so a full reconvergence takes **30 seconds**. During those 30 seconds, traffic through the affected ports is dropped.

This is exactly why you see "internet drops every 30 seconds" — and it is rarely your ISP.

### The rogue bridge problem at home

Modern consumer devices — mesh router nodes, network-enabled smart TVs, some NAS boxes — run STP internally and will participate in your network's STP election if you connect them via Ethernet. The device with the lowest **Bridge ID** (a combination of priority value and MAC address) wins the election and becomes the root bridge.

If a Google Nest node, for example, has a lower bridge ID than your actual router, it wins the election and becomes the root. Your real router is now a non-root bridge. Every 30 seconds (or whenever the Nest renegotiates), STP reconverges and your connection drops for up to 30 seconds.

### How to fix it

1. Identify which device is winning the root bridge election (NetSentinel's STP Monitor tab shows you this).
2. On your real router or managed switch, set the STP priority to the lowest possible value (`4096` or even `0`) so it always wins the election.
3. If the rogue device cannot have STP disabled, connect it via WiFi only, or put it on a separate VLAN that does not participate in your main STP domain.
4. On unmanaged consumer switches, enable **Rapid PVST+** or **RSTP** if available — it reduces reconvergence time from 30 seconds to 1–2 seconds.

---

## 5. ARP spoofing and man-in-the-middle attacks

### How it works

ARP has a fundamental design flaw: it is stateless and trusting. Any device can send an unsolicited ARP reply ("gratuitous ARP") claiming to own any IP address, and other devices on the network will update their ARP tables without question.

An attacker exploits this to perform a **man-in-the-middle (MITM) attack**:

1. The attacker sends a forged ARP reply to your laptop: "The IP `192.168.1.1` (your router) is at MAC `aa:bb:cc:11:22:33`" (the attacker's MAC).
2. Simultaneously, they send a forged ARP reply to your router: "The IP `192.168.1.100` (your laptop) is at MAC `aa:bb:cc:11:22:33`."
3. Now all traffic between your laptop and the router flows through the attacker's machine. They can read it, modify it, or selectively drop it.

This is particularly dangerous on networks without full HTTPS enforcement. Even with HTTPS, an attacker in the middle can perform SSL stripping on unaware clients, or monitor the metadata of your traffic (which sites you visit, when, how much data).

### What NetSentinel detects

NetSentinel's ARP Monitor watches for:

- **Duplicate IP entries** — two different MAC addresses claiming the same IP
- **ARP cache changes** — an IP that was previously mapped to one MAC is now mapping to a different one
- **Gratuitous ARP flooding** — a device repeatedly broadcasting ARP replies it was never asked for

When detected, NetSentinel flags the suspicious device with a `High` or `Critical` severity and identifies both the original and the new claimant MAC address, along with their vendor information, so you can tell whether it is a legitimate device change (you replaced a router) or a genuine attack.

---

## 6. Broadcast storms

### What causes them

A broadcast storm happens when broadcast frames multiply faster than the network can process them. The classic trigger is a loop in the network topology — two switches connected by two cables with no spanning tree to block one of them. A single broadcast frame enters the loop and circulates forever, duplicating at each switch hop. Within seconds the network is saturated.

Less obviously, broadcast storms can also be caused by:

- A malfunctioning network card sending frames continuously
- A misconfigured device flooding the network with ARP requests
- A worm or malware doing a rapid ARP or UDP broadcast sweep
- A switch port in an error state

### How to identify the source

NetSentinel's Broadcast Storm Analyser uses packet capture (requires Npcap on Windows) to measure broadcast frame rates per second and identify which MAC address is the source. A healthy home network sees a few broadcast frames per second at most. Rates above 100 frames/second indicate a problem; rates in the thousands indicate an active storm.

The analyser shows you:

- Current broadcast rate (frames/second)
- Which MAC address and associated device is generating the most broadcasts
- Whether the rate is consistent (misconfigured device) or spiking (transient loop)

### Impact on performance

During a broadcast storm, every device on the network must process every broadcast frame — even if the frame is not addressed to it. This burns CPU on your router, switches, and every connected device. The practical result is that all network traffic slows dramatically or stops entirely, even for devices not involved in the storm source.

---

## 7. DNS — why speed matters and what a DNS leak is

### Why DNS speed matters

Every new TCP connection your device makes — every website, API call, or app update — starts with a DNS lookup. If your DNS resolver takes 300 ms to answer, and a single webpage triggers 40 DNS lookups, that is 12 seconds of lookup time before a single byte of content is transferred. DNS slowness is one of the most common reasons an internet connection "feels slow" even when a speed test shows good numbers.

DNS resolvers vary significantly in response time depending on your location:

| Resolver | Address | Notes |
|---|---|---|
| Cloudflare | `1.1.1.1` | Usually fastest in Europe and North America |
| Google | `8.8.8.8` | Slightly slower than Cloudflare but extremely reliable |
| Quad9 | `9.9.9.9` | Filters known malicious domains |
| Your ISP | varies | Often the slowest; may also hijack NXDOMAIN responses |

NetSentinel's Health Check tab benchmarks all four back-to-back so you can make an evidence-based decision about which resolver to configure on your router.

### What a DNS leak is

When you use a VPN, all your traffic — including DNS queries — should flow through the VPN tunnel to the VPN provider's resolver. A **DNS leak** happens when DNS queries bypass the tunnel and go directly to your ISP's resolver. The result: your ISP can still see every domain you look up even though you believe your traffic is private.

DNS leaks happen because Windows (and some other operating systems) have a "smart multi-homed name resolution" feature that sends DNS queries to multiple resolvers simultaneously and uses whichever answers first. If your ISP's resolver answers faster than the VPN's, your queries leak.

NetSentinel's DNS leak test sends queries through your system resolver and checks whether the responding server's IP belongs to your VPN provider or your ISP.

---

## 8. Open ports and port scanning

### What port numbers mean

When a device wants to offer a service — a web server, a file share, an SSH login — it opens a **port**: a numbered channel that incoming connections can reach. Port numbers below 1024 are "well-known" ports assigned to standard services:

| Port | Service |
|---|---|
| 22 | SSH (remote terminal) |
| 80 | HTTP (unencrypted web) |
| 443 | HTTPS (encrypted web) |
| 445 | SMB (Windows file sharing) |
| 3389 | RDP (Windows Remote Desktop) |
| 8080 | Alternate HTTP (routers, cameras, home automation) |
| 1883 | MQTT (IoT messaging) |

Ports 1024–65535 are used by applications and operating systems for dynamic and private purposes.

### What unexpected open ports indicate

If a device on your network has port 22 open and you did not intentionally install an SSH server on it, that is worth investigating — it could be a misconfiguration, a feature you did not know was enabled, or malware. Smart TVs, cameras, NAS devices, and routers routinely open ports you do not expect.

The risk scale roughly goes: management ports on internal devices (lower risk, but unnecessary exposure) → `3389` or `445` open to the internet (high risk, common ransomware entry points) → unknown service on an unknown port (investigate).

### SYN scan vs connect scan

There are two common ways to probe a port:

**Connect scan** — completes the full TCP handshake. The target device always logs it. Used when you do not need stealth.

**SYN scan (half-open scan)** — sends a SYN packet and waits for a SYN-ACK (port open) or RST (port closed), then sends a RST without completing the handshake. Faster and less likely to appear in application logs. Requires raw socket access (administrator/root).

NetSentinel uses a SYN scanner (in `modules/syn_scanner.py`) when running with elevated privileges for faster, lower-noise internal scans, and falls back to connect scanning otherwise. Results are enriched with service name, vendor, and a risk severity label.

---

## Tools in NetSentinel

| Concept covered above | NetSentinel tab |
|---|---|
| ARP scanning — device discovery | Devices on Network |
| ARP spoofing and MITM detection | ARP Monitor (Security Audit section) |
| RTT, latency, jitter measurement | DNS & Outages; Availability History |
| STP / rogue bridge detection | Rogue Bridge (STP Monitor) — requires Npcap |
| Broadcast storm detection and source identification | Broadcast Storm Analyser — requires Npcap |
| DNS benchmarking and DNS leak test | Health Check |
| DNS latency over time | DNS & Outages |
| Port scanning — open ports, risk scoring | SYN Scanner; Risk Assessment (Security Audit) |
| Network grade (overall health score) | Network Grade |
| ISP accountability report | Network Grade → Generate ISP Report |
| Device inventory and MAC/vendor lookup | Devices on Network |
| Availability and uptime history | Availability History; Uptime & SLA |
