# NetSentinel

**Find every device on your network, catch the faults that cause dropouts, and prove an outage to your ISP — all in one local app.**

Rogue bridge and broadcast storm detection, ARP spoof monitoring, port scanning and CVE lookup, and continuous stability logging. Free, open-source, and 100% local — no account, no cloud, no telemetry. Nothing leaves your machine.

---

## Install

**Windows** — [get it from the Microsoft Store](https://apps.microsoft.com/detail/9NZ124C7HJWS), or:

```powershell
winget install NetSentinel.NetSentinel
```

Or download `NetSentinel-Setup-*.exe` from the [latest release](https://github.com/ossianericson/netsentinel/releases/latest) and run as Administrator.

**macOS**

Download `NetSentinel-macOS.zip`, unzip, right-click → Open (first launch bypasses Gatekeeper). Requires `brew install libpcap` for Layer 2 features.

**Linux**

```bash
sudo apt-get install libpcap-dev   # Ubuntu/Debian
chmod +x NetSentinel && sudo ./NetSentinel
```

---

## What it answers

| Your question | Where NetSentinel answers it |
|---|---|
| "What is that unknown device on my Wi-Fi?" | **Devices** — ARP scan with MAC/OUI vendor ID, model and risk level |
| "Why does my internet drop every 30 seconds?" | **Rogue Bridge (STP)** — identifies the rogue root bridge from BPDU capture |
| "Is it my ISP or my router?" | **Root Cause Correlator** — hop-by-hop ping chain, plain-English verdict |
| "Something is slow and I don't know what" | **What's Wrong?** — sequences DNS, storm, STP, and ISP checks |
| "Is someone spoofing my gateway?" | **ARP Spoof Watch** — detects IP–MAC mapping conflicts |
| "Which app is eating my bandwidth?" | **App Traffic** — per-device protocol breakdown with CDN tagging |
| "How do I prove this outage to support?" | Stability Log + Network Grade → **ISP Report** (HTML export) |
| "Is anything of mine exposed?" | **Port Scanner** (Security Audit) — SYN stealth scan, plus CVE and TLS checks |
| "Are any of my certificates about to expire?" | **TLS Certificate Monitor** — hourly checks, 30-day pre-expiry alerts |
| "Why won't this one service load?" | **Service Diagnostics** — DNS/TCP/HTTPS/traceroute per service, failure-layer classification |

---

## Quick start

1. **Run as Administrator** — raw packet capture (Npcap on Windows) requires admin rights
2. **Click Scan** in the top bar — sweeps your subnet via ARP; populates all pages in 10–30 seconds
3. **Right-click any row** — every table has Copy, Port Scan, How to Fix, Wake-on-LAN
4. **Open What's Wrong?** for one-click root-cause analysis
5. **Run Stability Log for 30+ min** → Network Grade → Generate ISP Report

---

## Documentation

- [Feature Reference](feature-reference.md) — complete list of all 89 features by nav section
- [Architecture](architecture.md) — codebase structure, key design decisions, adding a new feature
- [Hardware Integrations](hardware-plugins.md) — bundled plugins, writing your own, `.nspkg` format
- [Scan Plugin Authoring](plugin-authoring.md) — custom security checks against the device list
- [Contributing](contributing.md) — dev setup, PR checklist, three contribution tracks
- [Chaos / Monkey Testing](chaos-testing.md) — `.\test.ps1` UI chaos runner, memory soak mode, and the `AI_REPORT.md` triage file
- [Networking Guide](networking-guide.md) — plain-English explanations of ARP, STP, DNS, TCP, DHCP
- [Incident Patterns](incident-patterns.md) — real-world faults behind the speed-drop and filtered-layer detectors; on-demand vs. tray coverage

---

## Privacy

No telemetry. No cloud. No accounts. All scanning and analysis runs locally.

External endpoints are only contacted when you explicitly trigger a feature:

| Endpoint | Feature |
|---|---|
| `speed.cloudflare.com` | Speed test |
| `services.nvd.nist.gov` | CVE lookup (Security Audit, on demand) |
| `bash.ws` | DNS leak test |
| `api.github.com` | Update check (Help tab, on demand) |

Full details: [Privacy policy](privacy-policy.md) · [Security policy](https://github.com/ossianericson/netsentinel/blob/main/SECURITY.md)
