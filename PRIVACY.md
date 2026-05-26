# Privacy Policy

**Last updated: 2026-05-26**

NetSentinel is a local desktop application. This document describes exactly what data the
application reads, what it stores, and what it sends over the network.

---

## TL;DR

- **Zero telemetry.** No analytics, no crash reporting, no usage statistics — ever.
- **No cloud backend.** There is no NetSentinel server. Your data never leaves your machine
  unless you explicitly trigger a feature that requires a network call (see table below).
- **No AI features.** No data is sent to AI services.
- **100 % offline core.** Device scanning, ARP analysis, STP detection, broadcast storm
  analysis, and all passive monitoring work entirely offline.

---

## What NetSentinel Stores Locally

All persistent data lives in a single SQLite database under `%LOCALAPPDATA%\NetSentinel\`
(Windows) or `~/.netsentinel/` (macOS / Linux). No data is written anywhere else.

| Table / File | Contents | Retention |
|---|---|---|
| `devices` | MAC, IP, hostname, vendor (OUI), first/last seen | Until you clear it |
| `device_events` | APPEARED / DISAPPEARED events with timestamps | Until you clear it |
| `alerts` | Security alerts (rogue bridge, storm, ARP spoof, etc.) | Until you clear it |
| `speed_test_results` | Timestamp, download/upload Mbps, ping, ISP name, server | Until you clear it |
| `rtt_samples` | RTT samples for latency monitoring | Rolling 90 days |
| `modem_signal_log` | ZTE MC889 5G signal snapshot (RSRP, SINR, band, etc.) | Until you clear it |
| `mesh_signal_log` | TP-Link Deco mesh signal snapshot | Until you clear it |
| `threat_intel` | Blocklist entries (IP/domain, confidence, category, source) | Replaced on each update |
| `GeoLite2-City.mmdb` | MaxMind GeoLite2 city DB (offline IP geolocation) | Until you delete it |
| `QSettings` | UI preferences (window size, selected interface, intervals) | Standard OS settings store |

NetSentinel does **not** log raw packets to disk. Packets are captured in RAM by Scapy/Npcap and
discarded after analysis.

---

## Network Connections

NetSentinel makes **no automatic background network calls**. Every outbound connection is triggered
by an explicit user action.

| User action | Destination | Data sent | Data received |
|---|---|---|---|
| "Update Feeds" (Threat Intel) | Feodo Tracker (abuse.ch) | Nothing | IP/domain blocklist |
| "Update Feeds" (Threat Intel) | Emerging Threats (proofpoint.com) | Nothing | IP blocklist |
| "Update Feeds" (Threat Intel) | URLhaus (abuse.ch) | Nothing | URL/domain blocklist |
| "Quick Download" (GeoLite) | raw.githubusercontent.com | Nothing | GeoLite2 MMDB file |
| "Run Speed Test" | Ookla Speedtest servers | Test traffic | Speed result |
| "Check IP (AbuseIPDB)" | api.abuseipdb.com | Single IP address + your API key | Abuse reports |
| Port Scan | User-specified host/range | TCP SYN packets | Port state |
| Traceroute / MTR | User-specified host | ICMP/UDP probes | Hop latency |
| DNS Leak Test | User-specified or default resolvers | DNS query | DNS response |

### AbuseIPDB

The "Check IP" feature sends a single IP address to [AbuseIPDB](https://www.abuseipdb.com/).
This feature:

- Requires the user to enter their own AbuseIPDB API key in Settings
- Only runs when the user explicitly selects "Check IP (AbuseIPDB)" from a context menu
- Sends only the IP address and the user's API key — no other device data
- Is governed by AbuseIPDB's own [Privacy Policy](https://www.abuseipdb.com/privacy-policy)

---

## No Telemetry

NetSentinel contains **no telemetry, analytics, or error-reporting code** of any kind.
There are no calls to:

- Sentry, Datadog, Mixpanel, Amplitude, or any other analytics platform
- Update servers or version-check endpoints
- Any NetSentinel-owned server (there is no NetSentinel server)

You can verify this by reading the source code or running a network monitor while using the app.

---

## No AI Features

No data from NetSentinel is sent to any AI or machine learning service. There are no LLM
integrations, cloud inference calls, or model-training pipelines.

---

## Third-Party Data Sources

| Source | Purpose | Their privacy policy |
|---|---|---|
| Feodo Tracker (abuse.ch) | C2 server IP blocklist | [abuse.ch privacy](https://abuse.ch/privacy-policy/) |
| Emerging Threats (Proofpoint) | IP reputation blocklist | [Proofpoint privacy](https://www.proofpoint.com/us/privacy-policy) |
| URLhaus (abuse.ch) | Malicious URL/domain blocklist | [abuse.ch privacy](https://abuse.ch/privacy-policy/) |
| AbuseIPDB | IP abuse check (opt-in) | [AbuseIPDB privacy](https://www.abuseipdb.com/privacy-policy) |
| P3TERX GeoLite mirror | Offline IP geolocation DB | [GitHub privacy](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) |

---

## Your Rights

Because NetSentinel stores all data locally on your machine, you have full control:

- **View**: open `%LOCALAPPDATA%\NetSentinel\netsentinel.db` with any SQLite browser
- **Export**: use File → Export from within the app
- **Delete**: clear tables from within the app, or delete the entire `%LOCALAPPDATA%\NetSentinel\` folder

There is no account, no cloud copy, and no third party to contact for deletion — your data is
only on your machine.

---

## Contact

Privacy questions: **ossian.ericson@gmail.com**

Security issues: see [SECURITY.md](SECURITY.md)
