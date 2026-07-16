# Claims Audit — does NetSentinel actually do what it says?

## 1. How to read this

This document lists every place found where NetSentinel's UI, help text, README, or
`feature-reference.md` claims a behaviour the underlying code does not actually deliver. It
does **not** list crashes found by the chaos-test harness or bugs caught by the pytest suite —
those are covered elsewhere. This is specifically the class of defect where the app *tells the
user something untrue*: a column that's always blank, a status dot pinned to a constant, a
button whose label promises an action the code doesn't perform.

**Taxonomy:**

| # | Class | Meaning |
|---|---|---|
| **A** | Declared, never populated | a column/field/row exists in the UI, no producer ever fills it |
| **B** | Hardcoded state | a status indicator pinned to a constant instead of reading live state |
| **C** | Orphaned display | a row is shown with a state, but nothing ever sets that state |
| **D** | Hand-copied list drift | a list duplicated instead of derived, and the copies diverge |
| **E** | Documented but not built | docs/help/feature-guide describe behaviour the code lacks |

**Status:**
- **PROBED** — verified by actually running the code (a live probe script or the running app), not just reading it.
- **CONFIRMED** — verified by reading the exact code path; the defect is unambiguous (e.g. an unconditional literal assignment, a dataclass with no such field, a grep returning zero hits repo-wide).
- **SUSPECTED** — the evidence strongly suggests a defect but something remains unverified (noted per finding).

**Format:** findings are grouped by severity, then listed as compact blocks:
`ID — Class — one-line statement` followed by **Claim** (the exact quoted UI/doc string),
**Reality** (file:line + what the code actually does), **How to see it** (the click path), and
**Status**. IDs `F-01`–`F-07` were confirmed first, during planning, and seed the numbering;
`F-08` onward were found during the systematic sweep of all 4 claim surfaces
(`docs/feature-reference.md`, `README.md`, `ui/help.py`, `ui/pages/discover_data.py` +
`ui/help_tab.py`) plus verification of 6 previously-SUSPECTED leads. Findings that were
independently discovered more than once (e.g. by different sweep passes reading different
files that both cite the same broken code path) are recorded once, at the earlier ID — noted
inline as "independently re-confirmed via `<other file>`."

**Severity:** High = a live crash, a "Run"/action control that silently does nothing, or a
claim a user will notice is false within seconds of trying it. Medium = wrong or stale data is
shown, or a documented cross-feature link doesn't exist. Low = cosmetic/wording mismatch or a
dead UI element with no functional consequence.

---

## 2. Findings

All 89 findings from this audit have been closed. Findings that named a genuine code
defect were fixed in place; findings where the claim described functionality that was
never actually built were resolved by correcting the claim (README.md / `ui/help.py` /
`docs/feature-reference.md`) to match what the code does today. Missing high-value
functionality uncovered this way was tracked in `BACKLOG.md` (since removed — its
items are recorded below instead). Five items were subsequently built for real: 802.11
EAPOL frame classification (F-16), a real "last update" timestamp for credentialed
scans (F-78), OS Detection reusing prior port-scan results (F-72), SNMP CPU/load
polling (F-69), and SMB share risk flags that require anonymous visibility, not just a
non-hidden name (F-88). (The Protocol Visualizer step list was also subsequently built
for real — F-48's original claim is accurate again.)

The remaining four items were considered and explicitly deferred rather than built:

- **STP port-level block identification** (F-14) — would need SNMP `dot1dStpPort` MIB
  polling of the root/designated bridge, or LLDP/CDP MAC-to-port correlation; most
  home/SMB switches expose neither, and the WHO (a rogue bridge was detected) already
  works — WHERE is a nice-to-have with real implementation risk for a narrow audience.
- **SMB session enumeration** (F-56) — needs a greenfield SRVSVC `NetrSessionEnum`
  DCE/RPC call through `impacket`; no session-enumeration infrastructure exists
  anywhere in the repo to build on, and it would need new mock scaffolding to test.
  Confirmed by the user mid-sprint as a larger effort than originally scoped ("this was
  planned to be a small effort"), so it stays deferred.
- **Slack/Discord-native webhook payload** (F-68) — a per-channel "format" option in
  `_build_payload()` (`modules/notification_channels.py`); small and contained, left
  out of this pass by explicit user choice rather than for a technical reason.
- **CVE Tracker "New" badge** (F-74) — purely cosmetic (a "first seen this
  session/scan" flag per CVE); no functional or security value, and the underlying
  claim (CVEs start as "Open") is already accurate.

---

## 3. Checked and cleared

Things that look like bugs and aren't, recorded so the next audit doesn't re-flag them.

- **The DHCP hostname fix holds.** `dhcp_lease_scanner.py` still returns `hostname=""` on the Windows ARP path, but `DhcpLeaseWorker.work()` calls `_enrich_missing_hostnames()` by design (RULE-DW4).
- **No dead-state label typos.** Every string passed to `_nav_set_scan_state()` matches a real `NavLabel`. The defects found are omission and hardcoding, not drift.
- **No stub signal handlers.** An AST sweep for signal-connected methods whose body is only `pass`/`return` found zero real hits in `ui/`.
- **`PatchInfo.last_update`'s sibling fields are fine.** `os_version`, `kernel`, `pending_updates` are all genuinely assigned by `_parse_linux`/`_parse_windows` — only `last_update` (F-78) and `pending_update_names` are unpopulated.
- **`ui/scan_enrichment.py:619`'s `u.uid` read is legitimate** — it reads `credentialed_scan_helpers.UserEntry`, which genuinely has `uid`/`home`/`shell` fields (Unix `/etc/passwd`-style data), not `SMBUser` (whose broken `u.uid` read at line 667 was fixed to `u.flags`; formerly F-03).
- **Port Scan (UDP) hidden tips are accurate** — `UDP_PORTS` genuinely includes 53/161/123/5353; ICMP-unreachable-based closed-port detection matches its docstring.
- **CVE Lookup's NVD source and CVE Tracker's lifecycle states (excluding the "New" badge, F-74) check out** — real `services.nvd.nist.gov` calls, real `Open/Acknowledged/Accepted Risk/Remediated` state machine.
- **TLS certificate check cadence and threshold are accurate** — hourly interval, 30-day expiry warning, both match their defaults exactly.
- **MQTT/Home Assistant per-device entity claim is accurate** — a real Discovery payload with `unique_id: netsentinel_{mac}` is published per device.
- **Config Snapshots' Take/Compare workflow is accurate** as documented.
- **Hardware Hub's degraded/circuit-breaker thresholds and "last 100 log lines" claims are accurate** — `_DEGRADED_HOURS=24`, `_CIRCUIT_BREAK_THRESHOLD=10`, `deque(maxlen=100)` all match exactly.
- **IP Calculator, Hop-by-Hop Trace, Tools & Wake-on-LAN, Port Scanner cross-links, Rogue Bridge (STP) explainer, 802.11 Monitor capture claims, and Trend Forecasts' regression methodology** — all checked and accurate.
- **What's Wrong?, Troubleshoot, Dashboard (share card export), DNS Zone Map, Exposed to Internet, Full Device Discovery, Private Endpoint Check, Cloud Metadata Probe, DHCP Rogue Monitor, Live Bandwidth, App Traffic, Service Heartbeat, IPv6 Devices (aside from F-18), Syslog Viewer, SNMP Trap Receiver, Monitor Status** — no violations found in any `ui/help.py` entry for these pages.

---

## 4. Coverage

| Surface | Total claims | Rows/entries checked | Method |
|---|---|---|---|
| `docs/feature-reference.md` | ~73 rows | ~35 rows deep- or lightly-verified; remaining ~35 unaudited (no contrary signal found, not confirmed clean) | code read |
| `README.md` | 26 feature bullets + 1 plugin-count claim | all 27 | code read |
| `ui/help.py` `_PAGE_HELP` | 76 entries | all 76 (5-way split by nav section, plus one full independent re-pass that cross-validated ~25 of them with zero new findings) | code read, all "what" sentences + "hidden" tips traced to source |
| `ui/pages/discover_data.py` `_FEATURES` | 87 entries | full file read; ~15 highest-signal entries deep-verified against real numeric/behavioral claims; structural nav-pointer check (all "page" values resolve to live nav labels) run against every entry | code read |
| `ui/help_tab.py` hardcoded sections | full 650-line file | 100% — every keyboard shortcut and every referenced page name checked against live bindings/nav registry | code read |
| 6 previously-SUSPECTED leads (SMB fields, PatchInfo, speed test Status column, alert escalation, flyout dot race, audit error-state wiring) | 6 | 6/6 resolved to CONFIRMED | code read |
| Runtime probe (F-02) | 1 | 1/1 | live Python execution against the real code objects |

**Not covered by this pass:** the remaining ~35 unverified `feature-reference.md` rows (mostly
Monitor/Reports/Education rows with no numeric or highly-specific claim to falsify).
