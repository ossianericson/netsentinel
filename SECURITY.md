# Security Policy

## Supported Versions

NetSentinel follows a **rolling-release model** — only the latest release receives security patches.
Older releases are not backported.

| Version | Supported |
|---|---|
| Latest release | ✅ Yes |
| Any older release | ❌ No — please upgrade |

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

### Preferred: GitHub Private Vulnerability Reporting

Open a private advisory directly in this repository:
👉 **[Report a vulnerability](https://github.com/ossianericson/netsentinel/security/advisories/new)**

GitHub encrypts the report end-to-end and notifies the maintainer without public disclosure.

### Fallback: Email

If you cannot use GitHub's advisory system, email **ossian.ericson@gmail.com** with:

- A description of the vulnerability
- Steps to reproduce
- The potential impact (what an attacker could achieve)
- Your severity assessment (CVSS score if you have one)

Encrypt sensitive details with the [PGP key on Keybase](https://keybase.io/ossianericson) if needed.

### Response SLAs

| Milestone | Target |
|---|---|
| Acknowledgement | 24 hours |
| Severity assessment | 72 hours |
| Critical (CVSS ≥ 9.0) patch | 7 days |
| High (CVSS 7.0–8.9) patch | 14 days |
| Medium (CVSS 4.0–6.9) patch | 30 days |
| Low (CVSS < 4.0) | Next scheduled release |

Reporters are credited in release notes unless they request anonymity.

---

## CVSS Severity Classification

| Severity | CVSS Score | Example |
|---|---|---|
| Critical | 9.0–10.0 | Remote code execution, privilege escalation to SYSTEM |
| High | 7.0–8.9 | Local privilege escalation, credential theft |
| Medium | 4.0–6.9 | Information disclosure, UI spoofing with user interaction |
| Low | 0.1–3.9 | Crash requiring local access, minor info leak |
| Informational | 0.0 | Hardening recommendation, best-practice deviation |

---

## Threat Model

NetSentinel is a **local desktop application** with no cloud backend. Understanding what data it
touches is essential for assessing its attack surface.

### Data handling

| Data type | Where it lives | Sent externally? |
|---|---|---|
| Raw network packets (Scapy/Npcap) | **RAM only** — never written to disk | Never |
| Device fingerprints (ARP/mDNS/DHCP) | Local SQLite DB (`~/.netsentinel/`) | Never |
| Speed test results | Local SQLite DB | Only when test is run (user-initiated) |
| RTT/latency samples | Local SQLite DB | Never |
| Threat intelligence blocklists | Local SQLite DB (downloaded from Feodo/ET/URLhaus on demand) | Never auto-updated |
| GeoLite2 city DB | Local file (downloaded once on user request) | Never |
| Modem / mesh signal data | Local SQLite DB | Never |
| AbuseIPDB lookups | User's own API key; single IP lookup only | Only when user clicks "Check IP" |

### User-initiated network connections (exhaustive list)

The application **never makes automatic background network calls** beyond what the user explicitly
triggers. The complete set of connections is:

| Trigger | Destination | Protocol |
|---|---|---|
| "Update Feeds" button | Feodo Tracker, Emerging Threats, URLhaus | HTTPS |
| "Quick Download" GeoLite button | raw.githubusercontent.com/P3TERX/GeoLite.mmdb | HTTPS |
| "Run Speed Test" button | Ookla Speedtest servers | HTTPS |
| "Check IP (AbuseIPDB)" context menu | api.abuseipdb.com | HTTPS |
| "Check IP (AbuseIPDB)" context menu | Only if user has entered their own API key | — |
| Port Scan (SYN) | User-specified targets only | TCP/SYN |
| Traceroute / MTR | User-specified targets only | ICMP/UDP |

### Out-of-scope threats

- Attacks requiring physical access to the machine
- Denial-of-service against the local UI process
- Vulnerabilities in third-party dependencies — report these upstream
- Issues requiring the attacker to already have Administrator / SYSTEM privileges

### In-scope threats

- Code injection via parsed data (PCAP files, imported JSON/CSV, blocklist files)
- Privilege escalation beyond what the user explicitly authorised during a scan
- Data exfiltration through a compromised module or malicious blocklist feed
- Man-in-the-middle attacks on GeoLite / blocklist downloads (mitigated: HTTPS + SHA256 pinning planned)
- Symlink / path traversal attacks on local DB or config files

---

## Verifying a Release

Every release is signed and includes a SHA256 checksum file. You can verify any download before
running it.

### 1 — SHA256 checksum

Download `SHA256SUMS.txt` from the [release page](https://github.com/ossianericson/netsentinel/releases/latest).

**Windows (PowerShell)**
```powershell
$expected = (Get-Content SHA256SUMS.txt | Select-String "NetSentinel-Setup").ToString().Split(" ")[0]
$actual   = (Get-FileHash "NetSentinel-Setup-*.exe" -Algorithm SHA256).Hash.ToLower()
if ($expected -eq $actual) { "✅ Checksum OK" } else { "❌ MISMATCH — do not run" }
```

**macOS / Linux**
```bash
sha256sum --check SHA256SUMS.txt
```

### 2 — Cosign signature (keyless / Sigstore)

The Windows installer is signed with [cosign](https://github.com/sigstore/cosign) using GitHub
Actions OIDC — no long-lived private key exists. The signature is rooted in Sigstore's public
transparency log.

```bash
# Install cosign: https://docs.sigstore.dev/cosign/system_config/installation/
cosign verify-blob \
  --bundle NetSentinel-Setup-*.exe.bundle \
  --certificate-identity-regexp "https://github.com/ossianericson/netsentinel/.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "NetSentinel-Setup-*.exe"
```

A passing `cosign verify-blob` proves the file was produced by this repository's GitHub Actions
workflow and has not been tampered with since signing.

### 3 — VirusTotal scan

Each release description includes a direct link to the VirusTotal analysis of the installer
run during the CI build. Look for **"VirusTotal: 0/72"** in the release notes.

---

## Scope

### In scope

- NetSentinel GUI (`app.py`, `ui/`, `modules/`, `workers/`)
- NetSentinel CLI (`cli.py`)
- NetSentinel Windows Service (`service.py`)
- Installer (`installer.iss`) and MSIX package (`packaging/`)
- GitHub Actions release workflow (supply-chain security)

### Out of scope

- Third-party libraries (report to their maintainers)
- The operating system, Npcap driver, or Qt framework
- Attacks requiring physical access or pre-existing SYSTEM privileges
- Self-XSS or UI redressing that requires the attacker to already control the machine
