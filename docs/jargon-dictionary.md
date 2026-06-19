# NetSentinel Jargon Translation Dictionary
## S1-1 Deliverable — Plain-English Reference

*Audit date: 2026-06-15*
*Input for S1-3 (JargonTooltip deployment) and S1-4 (alert message rewriting)*

---

## How to use this document

Every term below is a technical label that appears somewhere in the NetSentinel UI.
The "User-facing translation" column is what a non-technical user should read instead
of (or alongside) the raw term.

All terms are loaded from `data/glossary.json` and rendered via `JargonTooltip`.
This document serves as the authoritative source for new entries.

---

## Term Inventory

| Technical term | Where it appears | User-facing translation |
|---|---|---|
| ARP | ARP Spoof Watch page, scan results | How devices announce their hardware address on the local network |
| AXFR | DNS Zone Mapping page | A request to download all DNS records from a server at once |
| BPDU | Rogue Bridge (STP) page, scan results | Control packets sent between switches to prevent network loops |
| BSSID | WiFi pages, scan results | The unique hardware ID of a specific wireless radio (not the network name) |
| CIDR | Devices table, network segments, subnet column | Shorthand for a block of IP addresses, e.g. 192.168.1.0/24 means all 256 addresses in that range |
| CVE | CVE Lifecycle Tracker, security findings | A numbered public record of a specific security flaw in a specific product |
| CVSS | CVE pages | A 0–10 severity score for a security vulnerability (9+ = Critical) |
| DHCP | DHCP Lease Inventory, device rows | The service that automatically assigns IP addresses when devices connect |
| DNS | DNS & Stability page, What's Wrong? findings | Translates website names (google.com) into the numbers computers use to find them |
| DNS Leak | Diagnostics results | When DNS queries go to your ISP instead of staying private (VPN bypass) |
| DORA | Protocol Visualizer | The four steps a device takes to get an IP address from DHCP |
| Gateway | Network info, routing results | Your router — the device all your internet traffic flows through |
| Jitter | RTT charts, trend forecasts | How much your ping time varies from one moment to the next |
| Latency | Speed Test, RTT charts | How long a packet takes to travel to a destination and back, in milliseconds |
| MAC Address | Devices table, all scan results | A unique 12-character ID built into every network device's hardware |
| mDNS | DNS Zone Mapping, device discovery | How devices find each other by name (printer.local) without a central server |
| MTR | Hop-by-Hop Trace page | A diagnostic tool that shows every router between you and a destination |
| OUI | Devices table, manufacturer column | The first 6 characters of a MAC address that identify the manufacturer |
| Packet Loss | RTT charts, availability history | The percentage of messages sent that never arrived |
| QoS | Recommendations, router info | Router settings that give priority to video calls over less time-sensitive traffic |
| RFC 1918 | Private Endpoint Checker, exposure results | The standard defining private IP ranges (10.x, 172.16–31.x, 192.168.x) |
| Rogue Device | Rogue device alerts, scan results | An unknown device on your network that you did not authorise |
| RTT | RTT charts, availability history, alerts | Round-Trip Time — how long a ping takes, measured in milliseconds |
| SINR | Modem Signal page | A measure of 5G signal quality vs. interference (above 20 dB = excellent) |
| SNMP | SNMP Trap Receiver, device info | A protocol routers and switches use to send status updates to monitoring tools |
| SSID | WiFi pages | The name of a Wi-Fi network (what you see when you scan for Wi-Fi) |
| STP | Rogue Bridge page, Protocol Visualizer | A protocol switches use to prevent network loops from crashing the network |
| Subnet | Devices table, segment pill bar | A group of IP addresses that share the same network prefix |
| TCP Handshake | Protocol Visualizer, service checks | The three-message setup sequence before two devices can exchange data |
| TLS | TLS & Cert Monitor | The encryption that makes HTTPS secure |
| Traceroute | Hop-by-Hop Trace page | Reveals every router between you and a destination, with delays at each hop |
| TTL | DNS results, packet analysis | A counter that limits how far a packet travels — also how long DNS records are cached |
| Uptime | Availability History, SLA reports | The percentage of time a device was reachable |
| VLAN | Network Infrastructure page | A way to logically separate devices on the same switches |

---

## Risk Level Display Map (S1-5)

Internal risk codes must NEVER appear raw in user-facing text.
Use this translation in all UI display contexts:

| Internal code | User-facing label | Colour |
|---|---|---|
| `CLEAN` | All clear | Green |
| `LOW` | Minor notice | Green |
| `MEDIUM` | Needs attention | Amber |
| `WARNING` | Needs attention | Amber |
| `HIGH` | Action required | Red |
| `STORM` | Critical — act now | Red |
| `UNKNOWN` | Not assessed | Grey |

---

## Alert Message Template (S1-4)

Every alert message must follow this formula:
```
[What happened] + [actual numbers] + [how it compares to normal] + [what to do next]
```

Examples (before → after):
- `"High RTT on 192.168.1.1: 450 ms (threshold 200 ms)"` → `"192.168.1.1 is responding slowly (450 ms, normally under 200 ms) — this may affect video calls and real-time applications."`
- `"Host DOWN: 192.168.1.50"` → `"192.168.1.50 has gone offline and is not responding to pings."`
- `"Service DOWN: Netflix (192.168.1.1:443)"` → `"Netflix is not responding on 192.168.1.1 (port 443) — the service may be offline or blocked by a firewall."`

---

*Update this document when new technical terms are added to the UI.*
