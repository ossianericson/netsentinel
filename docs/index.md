# NetSentinel

**Network Security Scanner — Rogue Device Detector, STP Monitor & ISP Accountability Tool**

Find every device on your LAN. Detect rogue bridges, broadcast storms, ARP spoofing, and IoT anomalies. Prove ISP outages with timestamped evidence. All analysis runs 100% locally — nothing leaves your machine.

---

## Install

=== "Windows (recommended)"
    ```powershell
    winget install NetSentinel.NetSentinel
    ```

=== "Manual download"
    Download `NetSentinel-Setup-*.exe` from the [latest release](https://github.com/ossianericson/netsentinel/releases/latest), run as Administrator.

=== "macOS"
    Download `NetSentinel-macOS.zip`, unzip, right-click → Open (first launch bypasses Gatekeeper).

=== "Linux"
    ```bash
    chmod +x NetSentinel && sudo ./NetSentinel
    ```

---

## What it does

| Problem | How NetSentinel finds it |
|---|---|
| Random 30-second internet drops | STP tab — detects rogue Root Bridge election |
| Unknown devices on WiFi | Devices on Network — ARP scan with vendor/model ID |
| "Is the problem mine or my ISP's?" | Root Cause Analysis — correlates STP, storm, and DNS data |
| Slow browsing despite fast internet | Health Check — benchmarks 4 DNS resolvers side-by-side |
| ARP spoofing / MITM attack | ARP Spoof Watch — detects IP-MAC mapping conflicts |
| Bandwidth hog on the network | Bandwidth Usage — per-device live rx/tx monitor |
| Proving an outage to ISP support | Stability Log + Network Grade → ISP Report (HTML export) |
| Open ports on devices | Port Scan (Security Audit mode) |
| Expired TLS certificates | TLS & Exposure tab — hourly cert checks per host |

---

## Quick start

1. **Run as Administrator** — raw packet capture (Npcap on Windows) requires admin rights
2. **Click Run Scan** — sweeps your subnet via ARP, populates all tabs in 10–30 seconds
3. **Right-click any row** — every table has Copy, Port Scan, How to Fix, Wake-on-LAN
4. **Switch to Pro mode** — unlocks MTR, ARP Watch, SNMP, Automation, Security Audit tabs
5. **Run Stability Log for 30+ min** → Network Grade → Generate ISP Report

---

## Documentation

- [Architecture](architecture.md) — how the codebase is structured, adding a new feature
- [Contributing](contributing.md) — setup, tests, build, PR checklist
- [Networking Guide](networking-guide.md) — plain-English explanations of the protocols NetSentinel monitors

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
