# Contributing to NetSentinel

Thanks for your interest. There are three contribution tracks — pick the one that fits you.

---

## Track 1 — Add a rogue device signature (no Python required)

Edit [`offenders.json`](offenders.json) to flag a device that misbehaves on home networks. This is the lowest-friction contribution and has the highest user impact.

### Schema

```json
{
  "vendor": "Device Brand Name",
  "ouis": ["aa:bb:cc", "dd:ee:ff"],
  "known_issues": [
    "One-line description of the Layer-2 behaviour that causes problems"
  ],
  "risk_level": "HIGH",
  "forum_reference": "https://link-to-bug-report-or-forum-thread",
  "remediation": "Plain-English fix for the end user."
}
```

### Required fields

| Field | Type | Notes |
|---|---|---|
| `vendor` | string | Human-readable brand name. Used in reports and the UI. |
| `ouis` | array of strings | One or more 6-hex-char OUI prefixes (`aa:bb:cc`). Lowercase, colon-separated. |
| `known_issues` | array of strings | At least one entry. Each string is one sentence describing a specific misbehaviour. |
| `risk_level` | string | One of: `HIGH`, `MEDIUM`, `LOW` — see table below. |
| `remediation` | string | Actionable plain-English advice. |

### `risk_level` values

| Value | When to use |
|---|---|
| `"HIGH"` | Device actively disrupts the network (rogue root bridge, rogue DHCP, ARP spoofing, IPv6 RA injection). |
| `"MEDIUM"` | Device degrades performance or exposes attack surface but does not actively block traffic. |
| `"LOW"` | Minor nuisance or cosmetic issue — flagged for awareness but not harmful in normal use. |

`forum_reference` is optional but strongly encouraged — a link to a vendor bug tracker or public write-up gives reviewers confidence the issue is real.

### Verification before submitting

- Confirm the OUI prefix at [Wireshark OUI lookup](https://www.wireshark.org/tools/oui-lookup.html).
- Check for duplicates: search the file for your OUI prefix before adding.
- The OUI must be the first three octets of the device's MAC address as it appears in `arp -a` output, not the full MAC.

---

## Track 2 — Submit a hardware plugin

If your router, modem, or access point is not in the [12 bundled integrations](docs/hardware-plugins.md#bundled-integrations), the highest-value contribution is a working plugin script. No PyQt knowledge required — just Python and your hardware's admin API.

See the [Hardware Integrations guide](docs/hardware-plugins.md) for the full authoring walkthrough, including the AI-assisted prompt workflow and the `.nspkg` bundle format.

**Submission template** — open a GitHub Issue titled `[Hardware Plugin] Brand Model XYZ`:

```
Hardware: Brand Model XYZ
Firmware tested: vX.Y.Z
Access method: HTTP REST / HTML scrape / SNMP / SSH
pip dependencies: requests, beautifulsoup4   (or none)
get_status() returns: wan_ip, uptime_sec, connected_clients, download_mbps, upload_mbps

[attach your .py file]
```

---

## Track 3 — Code contribution

### Dev setup

```bash
git clone https://github.com/ossianericson/netsentinel
cd netsentinel
pip install -r requirements.txt
python app.py              # GUI — add sudo / Run as Administrator for full scan
python cli.py scan         # Headless
python -m pytest tests/ -v --tb=short   # Run all tests
```

**UI chaos testing (Windows):** to shake out crashes and memory leaks by driving the real app through thousands of random interactions, see the [Chaos / Monkey Testing guide](docs/chaos-testing.md) — one command (`.\test.ps1`) produces a paste-ready `AI_REPORT.md`.

**Platform setup:**

- **Windows:** install [Npcap](https://npcap.com) for packet-capture features (STP, storm detection, ARP monitor, DHCP detector). Run as Administrator for those tabs.
- **macOS:** `brew install libpcap`; run with `sudo python app.py`; first launch requires right-click → Open (Gatekeeper bypass).
- **Linux (Ubuntu/Debian):** `sudo apt-get install libpcap-dev`; if Qt fails to launch: `sudo apt-get install libxcb-cursor0`.

### Bumping the version

Never edit version strings manually. Use the script:

```bash
python bump_version.py 2.1.14
```

This updates all 12 tracked locations atomically, runs the consistency test suite, and creates the version commit.

### Reporting security vulnerabilities

Do not open a public issue. Use [private vulnerability reporting](https://github.com/ossianericson/netsentinel/security/advisories/new) — response within 48 hours.

---

## Writing a scan plugin

Scan plugins analyse the discovered device list and return security findings. They run in a sandbox and appear in the Security Audit section.

See [docs/plugin-authoring.md](docs/plugin-authoring.md) for the full interface reference, a working example, and submission guidelines.

---

## PR checklist

Before submitting a pull request, confirm all of the following:

- [ ] `python -m pytest` passes with no failures or errors.
- [ ] `ruff check . --select=F401,F811,F841` exits 0 (no unused imports or variables).
- [ ] For offenders.json entries: OUI verified, `risk_level` is one of the three allowed values, `remediation` is present and actionable.
- [ ] For code changes: no new network calls in tests; all tests mock I/O.
- [ ] For plugins: required interface is present and matches the contract in `docs/plugin-authoring.md`.
- [ ] No credentials, API keys, or secrets anywhere in the diff.
- [ ] `requirements.txt` updated if a new dependency is introduced.
- [ ] The PR description states what problem it solves and on which device/firmware version the behaviour was observed (for offenders.json entries).
