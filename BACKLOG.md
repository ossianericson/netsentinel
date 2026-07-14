# Backlog

High-value functionality that was previously described in the README, `ui/help.py`, or
`docs/feature-reference.md` but is not actually implemented. These claims were corrected
during the 2026-07 claims-audit documentation-sync pass (`docs/internal/claims-audit.md`)
so the app only describes what it actually does today. This file is where that deferred
work lives for future development — nothing here is scheduled.

Each item lists the finding it traces back to, what's missing, and roughly what building
it for real would require.

---

## STP port-level block identification

**Traces to:** F-14. README claimed Rogue Bridge (STP) detection "identifies which ports
it forces offline."

**Missing:** `BPDUInfo` (`modules/stp_detector.py`) has no port field — only `interface`,
the local capture NIC. There's no way to say *which switch port* got blocked.

**What it would take:** BPDU capture alone can't see remote switch port state; a real
implementation needs either SNMP `dot1dStpPort` MIB polling of the root/designated
bridge (if it exposes SNMP) or LLDP/CDP correlation to map MAC-to-port. Meaningful new
capability, not a wiring fix.

---

## 802.11 EAPOL / 4-way handshake capture

**Traces to:** F-16. README/help claimed 802.11 Monitor captures EAPOL frames.

**Missing:** `_classify()` in `workers/wifi_monitor_worker.py` recognizes
Beacon/ProbeReq/ProbeResp/Auth/AssoReq/AssoResp/Deauth only.

**What it would take:** add `scapy.layers.eap.EAPOL` detection to the classifier and a
new frame-type row in the results table. Contained, but real new parsing logic and a UI
row — not a rewording.

---

## Protocol Visualizer clickable step list

**Traces to:** F-48. Help text claimed "click any step in the step list to jump directly
to it."

**Missing:** `ui/pages/protocol_viz_page.py` only has ◀◀/▶/▶▶/↺ buttons and a "Step X of
Y" label — no list widget, no jump-to-index API.

**What it would take:** a `QListWidget` (or similar) enumerating steps with a
click-to-jump handler wired to the existing step-index state.

---

## SMB session enumeration

**Traces to:** F-56. `SMBEnumResult.sessions` is declared but never populated by either
the Tier-1 (NetBIOS/anonymous) or Tier-2 (impacket/`net.exe`) path — the verdict text
used to always claim "0 session(s)" (now removed from the display; see
`modules/smb_enumerator.py::plain_verdict`).

**What it would take:** a real SRVSVC `NetrSessionEnum` RPC call through impacket,
authenticated with the same credentials as the Tier-2 scan. New capability, not a
wiring fix.

---

## Slack/Discord-native webhook payload

**Traces to:** F-68 (SUSPECTED — confirmed by reading, not live-tested against a real
endpoint). Help text implied webhooks work with Slack/Discord out of the box.

**Missing:** `_build_payload()` in `modules/notification_channels.py` emits a custom JSON
schema lacking Slack's `"text"` key or Discord's `"content"`/`"embeds"` keys.

**What it would take:** a per-channel-type payload format (e.g. a "format" dropdown:
generic JSON / Slack / Discord) so the same webhook URL field can target either service
directly.

---

## SNMP CPU / load polling

**Traces to:** F-69. Help text claimed SNMP Device Info queries "CPU load."

**Missing:** `SNMPResult` (`modules/snmp_poller.py`) has no CPU/load field — only
sysDescr/sysName/interface counters/uptime are polled.

**What it would take:** query a CPU-load OID (e.g. `hrProcessorLoad` from HOST-RESOURCES-MIB,
vendor-specific fallbacks for routers that don't expose it) and add a field + display row.

---

## CVE Tracker "New" badge

**Traces to:** F-74. Help text claimed newly discovered CVEs get a "New" badge.

**Missing:** `CVE_STATES` (`ui/pages/cve_page.py`) is
`["Open", "Acknowledged", "Accepted Risk", "Remediated"]` — no "New" state or highlight
logic exists. (Newly discovered CVEs do start as "Open," which is the accurate claim now
in the help text.)

**What it would take:** track a "first seen this session/scan" flag per CVE and render a
badge/highlight for it — cosmetic but requires new state, not just a state-machine value.

---

## OS Detection reusing prior port-scan results

**Traces to:** F-72. Help text claimed "accuracy improves when port scan data is
available."

**Missing:** `workers/scan_worker.py` and `modules/os_fingerprint.py` hardcode a fixed
port set `(80, 443, 22, 8080)` regardless of any prior scan.

**What it would take:** thread the most recent port-scan result for a host into the
fingerprinter so it can probe additional confirmed-open ports instead of (or alongside)
the fixed set.

---

## Real "last update" timestamp for credentialed scans

**Traces to:** F-78. `PatchInfo.last_update` (`modules/credentialed_scan_helpers.py`) is
declared but never assigned by `_parse_linux`/`_parse_windows` — the UI now shows "—"
instead of a false blank.

**What it would take:** platform-specific parsing (`wmic qfe` / `Get-HotFix` timestamp on
Windows, `/var/log/dpkg.log` or `rpm -qa --last` on Linux) to get a real "when was this
last patched" value.

---

## SMB share risk flag: auth-state awareness

**Traces to:** F-88. Help text claimed shares are flagged specifically when "visible
without a password."

**Missing:** `SMBShare` has no auth-required field; `ui/scan_enrichment.py`'s risk flag
fires on any non-hidden disk share regardless of whether the scan authenticated
successfully or anonymously.

**What it would take:** track whether the share enumeration succeeded via anonymous/null
session vs. supplied credentials, and only flag shares reachable in the anonymous case.
