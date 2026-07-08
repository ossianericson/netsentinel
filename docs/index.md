# NetSentinel

**Network Security Scanner — Rogue Device Detector, STP Monitor & ISP Accountability Tool**

Find every device on your LAN. Detect rogue bridges, broadcast storms, ARP spoofing, and IoT anomalies. Prove ISP outages with timestamped evidence. All analysis runs 100% locally — nothing leaves your machine.

---

## Install

**Windows**

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

## What it diagnoses

| Symptom | How NetSentinel finds it |
|---|---|
| Random 30-second internet drops | STP tab — identifies rogue root bridge from BPDU capture |
| Unknown device on WiFi | Devices page — ARP scan with MAC/OUI vendor ID and risk level |
| "Is it my ISP or my router?" | Root Cause Correlator — 5-hop ping chain, plain-English verdict |
| Slow browsing despite fast internet | What's Wrong? — sequences DNS, storm, STP, and ISP checks |
| ARP spoofing / MITM attack | ARP Spoof Watch — detects IP–MAC mapping conflicts |
| Bandwidth hog on the network | App Traffic — per-device protocol breakdown with CDN tagging |
| Proving an outage to ISP support | Stability Log + Network Grade → ISP Report (HTML export) |
| Open ports on a device | Port Scanner (Security Audit) — SYN stealth scan |
| Expired or expiring TLS certs | TLS Certificate Monitor — hourly checks, 30-day pre-expiry alerts |
| Service is unreachable | Service Diagnostics — DNS/TCP/HTTPS/traceroute per service, failure-layer classification |

---

## Quick start

1. **Run as Administrator** — raw packet capture (Npcap on Windows) requires admin rights
2. **Click Scan** in the top bar — sweeps your subnet via ARP; populates all pages in 10–30 seconds
3. **Right-click any row** — every table has Copy, Port Scan, How to Fix, Wake-on-LAN
4. **Open What's Wrong?** for one-click root-cause analysis
5. **Run Stability Log for 30+ min** → Network Grade → Generate ISP Report

---

## Documentation

- [Feature Reference](feature-reference.md) — complete list of all 83+ features by nav section
- [Architecture](architecture.md) — codebase structure, key design decisions, adding a new feature
- [Hardware Integrations](hardware-plugins.md) — bundled plugins, writing your own, `.nspkg` format
- [Scan Plugin Authoring](plugin-authoring.md) — custom security checks against the device list
- [Contributing](../CONTRIBUTING.md) — dev setup, PR checklist, three contribution tracks
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

Full details: [PRIVACY.md](../PRIVACY.md) · [SECURITY.md](../SECURITY.md)
