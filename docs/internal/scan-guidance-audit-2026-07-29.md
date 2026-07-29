# Scan-Guidance Audit — 2026-07-29

Phase 2 of the [Alert Relevance & Scan-Guidance Audit plan](../../.claude/plans/based-on-last-commits-dynamic-snowflake.md
— session plan, not checked into the repo tree it references). Static output from
`python app.py --audit` (Phase 1's harness) plus targeted read-only queries against the
live DB (`%LOCALAPPDATA%\NetSentinel\NetSentinel.db`, opened `mode=ro` while the app was
running with an active WAL) and QSettings. Confirms every finding in the plan's S1–S6,
resolves S7 from "needs live confirmation" to confirmed, and surfaces one CTA mismatch the
plan's manual pass missed.

## 1. `python app.py --audit` — full snapshot

13/20 checks passed. All 13 pre-existing `--audit-alerts` checks are green (unrelated to this
plan — carried over from the earlier alert-audit work). All 7 new scan-guidance checks fail,
exactly matching the plan's S1/S3/S5/S6/S7 findings:

| code | result | maps to |
|---|---|---|
| `CTA_LABELS_RESOLVE` | FAIL — 5 dead targets | S3 |
| `CTA_TABLE_PARITY` | FAIL — 6 disagreements (**+1 vs. plan**) | S3 |
| `AUDIT_STATE_WIRED` | FAIL — 3 pages never report scan state | S1, S6 |
| `AUDIT_CARD_PARITY` | FAIL — 5 pages wired but no card row | S6 |
| `AUDIT_QUEUE_TERMINATES` | FAIL — `THREAT_INTEL` branch stalls | S1 |
| `GUIDANCE_FITS` | FAIL — `home_data_mixin.py:449` | S5 |
| `GRADE_INPUTS_GATED` | FAIL — 2 dims store-presence-gated | S7 |

**New since the plan was written:** `CTA_TABLE_PARITY` also flags `NEW_CVE` — `RULE_CTA` points
it at `"CVE Lookup"`, `notif_alert_history`'s table points it at `"CVE Tracker"`. Same disagreeing-
tables defect as the other 5, just not caught by the plan's manual read. Folding this into
Phase 3.2 (no separate fix needed — same table, same repointing pass).

Full detail lines (unchanged from Phase 1's run, reproduced here as the "before" snapshot to
diff Phase 3's fixes against):

```
FAIL  CTA_LABELS_RESOLVE  RULE_CTA targets that resolve to no real page: CERT_EXPIRED -> 'TLS & Cert Monitor', CERT_EXPIRY -> 'TLS & Cert Monitor', DEVICE_GONE -> 'Inventory', HOST_DEGRADED -> 'Inventory', HOST_DOWN -> 'Inventory'
FAIL  CTA_TABLE_PARITY  Disagreeing CTA targets: HOST_DOWN ('Host Down'): RULE_CTA='Inventory' vs notif_alert_history='Inventory Changes'; HOST_DEGRADED ('Host Degraded'): RULE_CTA='Inventory' vs notif_alert_history='Inventory Changes'; DEVICE_GONE ('Device Gone'): RULE_CTA='Inventory' vs notif_alert_history='Inventory Changes'; CERT_EXPIRY ('Cert Expiring'): RULE_CTA='TLS & Cert Monitor' vs notif_alert_history='TLS & Exposure'; CERT_EXPIRED ('Cert Expired'): RULE_CTA='TLS & Cert Monitor' vs notif_alert_history='TLS & Exposure'; NEW_CVE ('New CVE Found'): RULE_CTA='CVE Lookup' vs notif_alert_history='CVE Tracker'
FAIL  AUDIT_STATE_WIRED  Registered as an audit page but never reports scan state (RULE-SS1): CVE Tracker, DHCP Rogue Monitor, Threat Intel
FAIL  AUDIT_CARD_PARITY  Audit pages that report scan state but have no Scan Status card row: Cloud Metadata Probe, Device Risk Score, Private Endpoint Check, Recon Plugins, Windows Shares (SMB)
FAIL  AUDIT_QUEUE_TERMINATES  Branches that dispatch a tool and never advance the queue: THREAT_INTEL
FAIL  GUIDANCE_FITS  Render paths that can cut a message before its action steps: ui/pages/home_data_mixin.py:449 slices below 100 chars inside set_pending_alert_rows()
FAIL  GRADE_INPUTS_GATED  Store-presence-gated (not scan-completion-gated) dimensions: ui/pages/security_overview_page.py:525 appends a grade dimension gated only on `self._store is not None`; ui/pages/security_overview_page.py:526 appends a grade dimension gated only on `self._store is not None`
```

## 2. Live DB — alert volume (S2 baseline)

```sql
SELECT COUNT(*), SUM(CASE WHEN acked_ts IS NULL THEN 1 ELSE 0 END) FROM alert_fired;
-- 14 total, 8 unacked
```

Lifetime rule_type breakdown:

| rule_type | count | unacked |
|---|---|---|
| `NEW_OPEN_PORT` | 11 | 8 |
| `MODEM_SIGNAL_DROP` | 2 | 0 |
| `IP_CHURN` | 1 | 0 (acked) |

**S2 re-measurement baseline: 8/8 unacked = `NEW_OPEN_PORT`.** This is the number Phase 3.5's
fix (reachability signal + MAC-keyed diff + service_mapper suppression) needs to move. Re-run
this exact query after a fresh port sweep post-fix.

The 8 unacked alerts, cross-referenced against `known_device` (confirms S2's live example and
S4 in the same pass):

| host | message length | `known_device.hostname` | vendor | device_type |
|---|---|---|---|---|
| 192.168.68.51 | 170 | `Lovisas-ny-iphone` | Apple, Inc. | Unknown Device |
| 192.168.68.52 | 170 | *(null)* | Google Chromecast / Google Home / Cast Audio | Streaming Stick |
| 192.168.68.53 | 170 | *(null)* | Google | Streaming Stick |
| 192.168.68.55 ×2 | 157, 169 | `Samsung` | Samsung | Smart TV |
| 192.168.68.59 | 165 | *(null)* | Google | Streaming Stick |
| 192.168.68.61 ×2 | 156, 181 | *(null)* | Unknown | Unknown Device |

Every alerting host except `.61` already has a resolved vendor/device_type — the S2 device-type-
suppression fix (consult `service_mapper`) has real data to key off. `.61`'s MAC
(`02:a8:f1:3b:93:40`) is itself locally-administered (see below) — vendor lookup correctly
returns `Unknown` for a randomized MAC; not a lookup bug.

## 3. Live DB — S5 confirmation (message truncation)

Full text of alert id 14 (192.168.68.51, 170 chars — within the plan's cited 116–181 range):

```
Port 8443/HTTPS Alternate opened on 192.168.68.51 since the last sweep.  → Confirm this was
intentional  → If not, check the device for malware or a misconfigured service
```

`home_data_mixin.py:449`'s `msg[:50]` cuts this to `"Port 8443/HTTPS Alternate opened on
192.168.68.51 s"` — 20+ characters before the `→` marker even starts. Confirms S5 exactly as
described; `append_action()` did its job at fire time, the render path discards it.

## 4. Live DB — S4 confirmation (locally-administered MAC)

`IP_CHURN` alert (id 1, already acked, so outside the current unacked count but still evidence
for the fix):

```
host = 6a:34:64:72:f8:f0
message = "Device 6a:34:64:72:f8:f0 has used 3 different IP addresses in the last 24 hours —
           it may be missing a DHCP reservation."
```

`0x6a & 0x02 == 0x02` — locally-administered bit set. Confirms S4's IP_CHURN example exactly.

**Observation (not a new finding, worth noting for whoever picks up Phase 3.4):** the currently
*unacked* `.61` device's MAC (`02:a8:f1:3b:93:40`) is also locally-administered
(`0x02 & 0x02 == 0x02`), but `known_device.mac_randomized` reads `0` for it (and for every other
row in this table). `device_classifier`'s randomized-MAC detection isn't setting this column
correctly, at least on this profile — a latent, separate bug from anything in this plan's scope.
Flagging for a future session, not fixing here (out of scope — see the plan's "Out of scope"
section).

## 5. Live DB / QSettings — S7 confirmation (was "needs live confirmation")

This profile has run **only** Port Scan (TCP), confirmed directly from the scan-state registry
(`HKCU\Software\NetSentinel\NetSentinel\scan_registry\state`, QSettings NativeFormat):

```json
{"Port Scan (TCP)": {"state": "stale", "ts": 1785304890.87, "verdict": null, "error": null}}
```

No `"CVE Lookup"` or `"TLS & Exposure"` key exists at all — both read "Never run" on the Scan
Status card. Yet:

- `cve_lifecycle` table: **0 rows.** `_update_security_grade()` appends
  `len(set(host for e in self._cve_entries...))` = **0** — read by the grade math as "checked,
  zero findings," indistinguishable from "checked and clean."
- `cert_check` table: **134 rows** (background `CertWorker` runs hourly regardless of whether
  the user ever opens Security Overview — see architecture doc). `_tls_issues` filters these to
  expired/self-signed/<30-days entries and appends `len(self._tls_issues)`, again purely on
  `self._store is not None`.

**This confirms S7.** The same page simultaneously shows "TLS & Exposure: Never run" in its own
Scan Status card while silently counting a TLS dimension into the grade from background data —
a self-contradiction on one screen. CVE is worse: zero evidence a CVE scan ever ran, zero rows,
counted as a clean dimension regardless. Phase 3.7 moves from "fix only if confirmed" to
**confirmed — fix it.**

## 6. Ranked fix order (unchanged from the plan)

Phase 2 changes nothing about the plan's severity ranking. Proceeding with Phase 3 in order:
S1 → S3 (now 6 CTA mismatches, not 5) → S5 → S4 → S2 → S6 → S7 (confirmed) → doc drift.

## Verification hooks for Phase 3

- Re-run `python app.py --audit` after each fix; the corresponding code should flip PASS.
- Re-run the Section 2 query after a fresh port sweep to measure S2's actual noise reduction
  against the 8/8 baseline above.
- Re-check `scan_registry/state` after Phase 3.1/3.6 land — `"Threat Intel"` should appear with
  a real state after the next Security Scan panel run.

## 7. Phase 3 outcome — 20/20, same session

Every finding fixed in severity order (S1 → S3 → S5 → S4 → S2 → S6 → S7 → doc drift), each with
a failing-test-first regression per RULE-T3 (the harness's own real-tree checks served as that
RED state for the 5 AST-detectable findings; new unit/behavioural tests were added for S2's
port-sweep mechanisms, S4's device-name resolution, and S7's grade gating). Final snapshot:

```
PASS  CTA_LABELS_RESOLVE  Every RULE_CTA target is a known nav label
PASS  CTA_TABLE_PARITY  RULE_CTA and notif_alert_history's CTA table agree on every overlapping rule
PASS  AUDIT_STATE_WIRED  Every audit_item=True page has a _nav_set_scan_state producer
PASS  AUDIT_CARD_PARITY  Scan Status card rows exactly match state-reporting audit pages
PASS  AUDIT_QUEUE_TERMINATES  Every dispatch branch in _advance_security_audit reaches an advance call
PASS  GUIDANCE_FITS  No alert render path truncates a message below its action-step budget
PASS  GRADE_INPUTS_GATED  No grade dimension is counted on store-presence alone
20/20 checks passed
```

**One fix expanded beyond the plan's stated scope, found live during implementation:**
`ui/widgets/alert_drawer.py` turned out to hold a **third** independent CTA table (`_RULE_PAGE`,
uppercase-substring-keyed) the plan's manual pass never found — same disagreeing-tables defect
as S3's other two. Folded into the same fix: both `notif_alert_history._cta_page_for_rule()` and
`alert_drawer._rule_to_page()` now prefer the alert's persisted `rule_type` against the canonical
`RULE_CTA` table first, falling back to their own legacy substring heuristic only when
`rule_type` is unavailable. `get_alert_history()`/`get_recent_alerts()`/`get_unacked_alerts()`
in `modules/metric_store_queries_metrics.py` needed `rule_type` added to their `SELECT` lists to
make this possible — it wasn't previously queried by two of the three.

**S6 also required updating two hand-duplicated rollup lists** (`home_data_mixin.py::_SEC_LABELS`,
`overview_tile.py::_SEC`) that mirror `_AUDIT_SCAN_LABELS` for the Home page's Scan Center dot —
an existing ratchet test (`test_claims_audit_ratchet.py::test_rollup_lists_match_audit_labels`,
from an earlier, separately-closed claims audit) correctly caught the new drift the moment
`_AUDIT_SCAN_LABELS` grew from 9 to 16 entries.

**Not verified this session:** a live re-run of the Section 2 alert-volume query after a fresh
port sweep (needs the actual nightly sweep or a manual trigger from the running app — the
existing `NetSentinel.exe` instance predates these fixes, and this session did not restart it).
The unit/regression tests for all three S2 mechanisms pass, but the live 8/8 NEW_OPEN_PORT
baseline has not yet been re-measured after a real sweep. Full interactive walkthrough of the
plan's Verification section item 6 (Security Scan panel run, Scan Status card, "Fix this"
buttons, Home Action-needed card) is likewise a live-app check for the user to run, same as
RULE-CHAOS1's monkey-test convention — not something this session drove interactively.
