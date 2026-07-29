# Partner Center — Store listing copy (v2.1.48)

Paste-ready text for **Product → Store listings → English (United States)**.
Every field below is within its Partner Center limit; counts are in
`assets/store/check_listing_lengths.py`. Screenshot upload order is in
`20260728_111325/README.md`.

Positioning note: the previous copy led with ZTE 5G modem and TP-Link Deco
specifics — hardware almost no visitor owns. This leads with device discovery,
fault diagnosis and security audit, and demotes vendor hardware to one line.

---

## Short description

> Limit 1,000. Only the first ~150 characters show in search results and tiles,
> so the hook has to land early.

```
Find every device on your network, catch the faults that cause dropouts, and prove an outage to your ISP — all in one local app. NetSentinel scans your LAN, identifies each device by vendor and model, watches for rogue hardware and attacks, and records timestamped evidence you can hand to support. No account, no cloud, no telemetry.
```

---

## Description

> Limit 10,000. Partner Center renders plain text — blank lines separate
> paragraphs, and bullets are literal characters.

```
NetSentinel replaces a shelf of separate utilities with one desktop application. It finds what is on your network, explains what is going wrong in plain English, and produces evidence you can act on.

Everything runs locally. There is no account, no cloud backend and no telemetry. Every outbound connection is started by you and documented.


WHAT IT ANSWERS

• "What is that unknown device on my Wi-Fi?" — a full inventory with IP, MAC, hostname, vendor, model and risk level for every device.

• "Why does my internet drop every 30 seconds?" — captures spanning-tree BPDUs and identifies the device that stole the root bridge role, a classic cause of repeating short outages.

• "Is it my ISP or my router?" — a hop-by-hop ping chain isolates where the loss actually starts, then states a plain-English verdict.

• "How do I prove this outage?" — the ISP Accountability Report exports a traceroute table, packet-loss percentages, DNS latency and a timestamped outage log as a single HTML file for a support ticket.

• "Is anything exposed?" — port scanning, OS fingerprinting, CVE lookup, TLS certificate expiry checks and credential testing, with a letter grade summarising your posture.

• "Something is slow but I do not know what" — one click sequences DNS, broadcast-storm, spanning-tree and ISP checks, then reports findings ranked by likely cause.


DISCOVER

• Device inventory — ARP, mDNS, NetBIOS and DHCP discovery; vendor and model identified from the MAC address
• Network topology map — an interactive diagram of how your devices actually connect
• Wi-Fi scanner — hidden SSIDs, rogue access points, WPS-enabled networks, co-channel interference and signal levels
• DHCP lease inventory and DNS zone mapping
• Wi-Fi signal heatmap — import a floor plan and map coverage room by room


MONITOR

• Stability logger — continuous ping, RTT, jitter and DNS logging to timestamped CSV; runs unattended for hours or days
• Availability history — UP / DEGRADED / DOWN charts per device with 1 hour to 7 day zoom
• Live bandwidth and per-application traffic breakdown
• Active connections — which process owns which socket, with one-click firewall block
• Syslog receiver and SNMP trap receiver
• Alerts by desktop toast, email, webhook, Pushover, ntfy or Telegram


DIAGNOSE

• One-click "What's Wrong?" triage across DNS, storm, spanning-tree and ISP checks
• Root cause correlator — ranks findings and gives a single overall verdict
• Service diagnostics — DNS, TCP, HTTPS, ICMP and traceroute probes against streaming and gaming services or any hostname, classifying which layer failed
• Broadcast storm analyser — measures flood levels and names the offending device
• ARP spoof watch — real-time detection of the IP-to-MAC conflicts that indicate an active man-in-the-middle


SECURITY AUDIT

• SYN and UDP port scanning with service banner grabbing
• OS fingerprinting and CVE lookup against discovered service versions
• TLS certificate monitoring with 30-day pre-expiry warnings
• Credential testing over SSH, SMB, FTP and Telnet
• Threat intelligence lookups and a per-device risk score
• Rogue DHCP server detection and SMB share enumeration


LEARN

• Protocol visualizer — animated, step-by-step diagrams of ten protocols (ARP, DNS, TCP, DHCP, STP, OSPF, NAT, VLAN, TLS, ICMP) drawn with your own network's real addresses, not textbook placeholders
• Lab mode — guided exercises mapped to CompTIA Network+ and CCNA objectives, with hints, solutions and exportable HTML results
• A subnet calculator and a networking glossary reachable from any page


AUTOMATE

• Read-only REST API on localhost
• MQTT publishing with Home Assistant discovery
• Shell command hooks on device-down, high-latency and new-device events
• Scheduled scans and scheduled report delivery
• Hardware integrations for TP-Link Deco, Ubiquiti UniFi, AVM FRITZ!Box, MikroTik, OpenWrt, Netgear, ASUS, Synology, Home Assistant and ZTE 5G modems


BEFORE YOU BUY — REQUIREMENTS

NetSentinel is free and open source under the MIT licence.

Most passive features work with no special privileges. Active scanning — port scans, OS detection and credential testing — requires running as Administrator. Layer 2 features — spanning-tree detection, broadcast storm analysis, ARP spoof watch and 802.11 monitor mode — additionally require Npcap (free, from npcap.com), which is not bundled.

Use it only on networks you own or are explicitly authorised to test.
```

---

## What's new in this version

> Limit 1,500. Keep it user-facing — no rule numbers, no file paths.

```
Alert acknowledgement fixes

• Acknowledging an alert now sticks. Previously a condition that stayed true would re-alert every five minutes regardless of acknowledgement, and acknowledging a grouped row only cleared one of the alerts behind it.

• Acknowledging now places a hold on that alert for 24 hours by default, configurable under Notifications → Configure. A resolved-then-recurring condition still alerts, so nothing genuinely new is suppressed.

• The Home page "Action needed" card now shows the real backlog count instead of just the visible rows, and offers "Acknowledge all" with an undo.

• Fixed the acknowledge button on the Home alert card rendering as an empty box instead of a check mark.

• Alert History now shows the alert message. The column was missing entirely, while the much shorter Rule column was stretched across the width.

• Fixed the in-app "What's New" list showing the previous release's changes.
```

---

## Product features

> Up to 20 entries, 200 characters each. Rendered as the "Features" list near
> the top of the listing — these get read far more than the description body.

```
Full device inventory — IP, MAC, hostname, vendor, model and risk level for everything on your LAN
Interactive network topology map showing how your devices actually connect
One-click "What's Wrong?" diagnosis with plain-English findings and a ranked root cause
ISP Accountability Report — traceroute, packet loss and outage log exported as evidence for a support ticket
Rogue bridge detection — finds the device stealing spanning-tree root and causing repeated short dropouts
Broadcast storm analyser that names the flooding device from packet-level evidence
ARP spoof watch — real-time detection of man-in-the-middle IP/MAC conflicts
Security audit — SYN/UDP port scan, OS fingerprint, CVE lookup, TLS expiry and credential testing
Network grade A–F across uptime, latency, jitter, DNS speed and device safety
Continuous stability logging to timestamped CSV — runs unattended for days
Wi-Fi scanner for hidden SSIDs, rogue APs, WPS and co-channel interference
Wi-Fi signal heatmap over an imported floor plan
Live bandwidth, per-app traffic and process-to-socket connection mapping
Protocol visualizer — ten animated protocol walkthroughs using your own network's real addresses
Lab mode with guided exercises mapped to CompTIA Network+ and CCNA objectives
Alerts via desktop toast, email, webhook, Pushover, ntfy or Telegram
Read-only local REST API and MQTT publishing with Home Assistant discovery
Hardware integrations for Deco, UniFi, FRITZ!Box, MikroTik, OpenWrt, Netgear, ASUS and Synology
Offline geolocation mapping with no API key required
100% local — no account, no cloud backend, no telemetry
```

---

## Search terms

> Up to 7 terms, 30 characters each. These are invisible to visitors and exist
> only to widen search matching, so they deliberately avoid words already
> prominent in the title and description.

```
who is on my wifi
internet keeps dropping
ip scanner
nmap gui
wifi analyzer
packet sniffer
network mapper
```

Dropped from the previous set: `network analyzer` (near-duplicate of `network mapper`,
and "analyser" already appears in the description) and `bandwidth monitor` (both words
are already prominent in the copy, so the slot bought nothing). Added
`internet keeps dropping` — the symptom a non-technical visitor actually types, and none
of those three words appear in the title or short description — and `wifi analyzer`, the
category name people search when they don't know the tool exists.

---

## Screenshot captions

> 200 characters each. Upload in this order — see
> `20260728_111325/README.md` for why.

| # | File | Caption |
|---|---|---|
| 1 | `03_devices.png` | Every device on your network, grouped by access point, with vendor, model, risk level and a plain-English verdict for each one. |
| 2 | `05_network_map.png` | See how your network is actually wired — internet, modem, router, mesh nodes and every device beneath them, with live traffic rates. |
| 3 | `07_security_overview.png` | One security dashboard: port scans, CVE lookups, TLS expiry and login tests, each with its own freshness state and finding. |
| 4 | `10_protocol_viz.png` | Watch ARP, DNS, TCP, DHCP, STP and five more protocols animate step by step — using your own network's real addresses, not textbook examples. |
| 5 | `01_home.png` | Your network at a glance: speed, stability and device count, with the monitors you have running and what to check next. |
| 6 | `12_geo_map.png` | Plot where suspicious traffic is going on an offline world map. No API key and no lookups leaving your machine. |
| 7 | `08_threat_intel.png` | Cross-reference the addresses your devices talk to against threat intelligence, with reputation scores and reported activity. |
| 8 | `09_speed_test.png` | Speed test history over time, so you can show your ISP a pattern instead of a single reading. |
| 9 | `04_app_traffic.png` | See which applications and hosts are actually consuming your bandwidth, broken down by category. |
| 10 | `06_service_diag.png` | Probe a streaming service, game or any hostname across DNS, TCP, HTTPS and traceroute, and find out which layer is failing. |

---

## Other listing fields

| Field | Value |
|---|---|
| Short title (50) | `NetSentinel` |
| Copyright and trademark info | `© 2026 Ossian Ericson. MIT licence.` |
| Developed by | `Ossian Ericson` |
| Privacy policy URL | `https://github.com/ossianericson/netsentinel/blob/main/PRIVACY.md` |
| Website | `https://ossianericson.github.io/netsentinel` |
| Support contact info | `https://github.com/ossianericson/netsentinel/issues` |
| Additional system requirements | `Active scanning requires running as Administrator. Layer 2 features (spanning-tree detection, broadcast storm analysis, ARP spoof watch, 802.11 monitor mode) additionally require Npcap from npcap.com, which is not bundled.` |

**Website** now points at the documentation site (GitHub Pages, enabled 2026-07-29 from
`main` → `/docs`) rather than the source repository — a docs site converts better for
non-developer visitors. `docs/_config.yml` keeps `internal/` and `spikes/` off the
published site.
