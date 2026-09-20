# Error, status & information surfacing audit — 2026-09-15

**Status (2026-09-20): S0–S8 complete and the live look is closed. S2.4 measured over a 7.4 h
source session plus a 74-page sweep: nothing to fix (§6 S2.4). That session found a real hang —
an IoT alert flood froze the GUI — fixed under RULE-WIN28 (`fff5233`). S7 done (`70ee0d1`): the
75 (a) handlers log at debug, B1/B3/B4/B4a fixed, matrix 25/25 NOT REPRODUCED, ratchet modules
304 → 224. S7b (B2, B5, B6, B7) is recorded, not coded. S8 done: B8–B14 fixed, matrix 33/33 NOT
REPRODUCED, ratchet ui 386 → 376; **the grade and the weekly digest were reading inputs that were
never there** — availability, the heaviest input at weight 0.45, had never once reached the health
score. S8b (the 7 swallowed `persist_alert` sites) is recorded, not coded. Next: S9.**
Decisions D1–D6 accepted 2026-09-15 (owner: "go with your advices"). This is the active plan
document for `/sprint start` / `/sprint end`.

**The one-line verdict.** The crash net is healthy: `netsentinel_exceptions.log` holds 23 entries
over the whole install, all traced to shipped fixes, and `netsentinel_crash.log` has not grown
since 2026-07-30. The gap is **below the crash net**: failures that are caught, never crash, and
then either reach no one, reach the wrong place, or render as a *healthy* result. S0.2 reproduced
every P1/P2 finding it tested against the real code path — 14 of 14.

---

## 1. Method and confidence

| Tag | Meaning |
|---|---|
| **matrix** | Reproduced by `docs/spikes/error-surfacing-matrix.py`: the real `app.py` wiring function / QThread worker / widget / delivery code, with a genuine fault injected (§7) |
| **read** | Confirmed by reading the code at the cited line |
| **census** | `tools/check_error_surfacing.py` (AST) — a count is a pointer, not a verdict |
| **log** | Observed in this machine's `%LOCALAPPDATA%\NetSentinel\*.log` |

Tools and guards produced by S0:

| Artefact | What it does |
|---|---|
| `tools/check_error_surfacing.py` | AST census: (a) raw exception text in user-visible sinks · (b) silent broad `except` · (c) undefined toast kinds · (d) scan labels with no error path. `python tools/check_error_surfacing.py` prints the full list |
| `tests/test_error_surfacing_ratchet.py` | 37 classifier unit tests + shrink-only ratchets on (a)–(d), baselined at 379bf5f |
| `docs/spikes/error-surfacing-matrix.py` | Re-runnable live verification matrix — S1 and S4 re-run it and expect rows to flip |
| RULE-SURF1 / RULE-SURF2 | `.apm/instructions/development-rules.instructions.md` |

The contract each surface is audited against — five questions for every failure or event:
**Detected** (noticed, or swallowed?) · **Recorded** (durable, with time, source and version?) ·
**Surfaced** (reaches a place the user sees, loudness proportional to impact, deduplicated?) ·
**Actionable** (what failed, likely why, what next, with a button when there is a next step —
RULE-A2, core value 3) · **Truthful** (can the failure ever render as clean, empty, never-run or
green? — RULE-SURF1).

---

## 2. How the app raises things today — channel inventory

| Channel | Mechanism | Persists | Dedup | Actionable | Volume |
|---|---|---|---|---|---|
| Fatal dialog | `app.py::_fatal` — plain body, raw traceback behind Details, Save report | crash logs + report | n/a | **Yes** | crash only |
| Unclean-exit strip | `ui/widgets/unclean_exit_strip.py` on Home | session records | per dead session | **Yes** | per crash |
| Alerts | AlertEngine → `_surface_alert_in_app` (status line + tray badge), Home "Action needed", Notifications page; router → opt-in balloon/webhook/email/… | `alert_fired` | cooldown + evidence gate | **Yes** — `RULE_CTA`, audited by `--audit-alerts` | ~0.5/day curated |
| Status bar | `ui/monitor_state.py::_set_status` — **one line**, last write wins | no | no | no | ~40 call sites |
| Toasts | `ui/widgets/toast.py` — kinds `success`/`error`/`info`/`action` | no | max 3 stacked | only kind `action` | ~35 sites, **3 use undefined `warning`** |
| QMessageBox | modal | no | n/a | mixed | 37 sites: 17 information, 15 warning, 4 question, 1 critical |
| Page status labels | per-page `_status`/`_status_lbl` | no | n/a | mostly raw text | most of the 95 raw sinks |
| Scan registry | `_nav_set_scan_state` → flyout/rail dots, tooltips, Security Overview card | QSettings | per label | tooltip only | 28 `fresh` / 19 `error` / 13 `not_testable` call sites |
| Home freshness pills | `FreshnessStrip.update_freshness` — ARP/DHCP/Storm/Logger | no | n/a | click → page (when OFF) | **binary ON/OFF** |
| Tray | health dot, badge, opt-in balloons | no | n/a | — | — |
| Banners | environment, Npcap, Ookla CLI, unclean-exit, first-visit context | QSettings dismissal | per key | yes | — |
| Logs | crash (faulthandler), exceptions (excepthook), shutdown, scan_timing, signal_quality, theme_switch — each its own FileHandler; **everything else** → `netsentinel_stderr.log` | rotated | no | via diagnostic report (B2) | — |

---

## 3. Findings

Priority: **P1** a persistent failure is invisible or renders as healthy · **P2** raised but not
actionable, raw, or clobbered · **P3** diagnostics and consistency.

### F1 [P1] Failures that render as healthy or never-run

| # | What | Where | Tag |
|---|---|---|---|
| F1a | ARP Spoof Watch / DHCP Rogue Monitor probe errors **clear** the flyout dot (`""` is the never-run colour) — an erroring monitor looks identical to one that never ran | `app.py:987-988`, `app.py:1013-1014` | **matrix** |
| F1b | Home freshness pills are binary — `update_freshness(arp, dhcp, storm, logger)` has no failing state, and `_push_monitor_pills` derives ON from `isRunning()`, so a running-but-failing monitor shows green `● ARP` | `ui/widgets/home_session_widgets.py:135-172`, `ui/monitor_state.py:595` | **matrix** (construct) |
| F1c | Scan labels whose failures never reach the registry — per label: | | |
| | · **Service Diagnostics** — `_on_error` emits `scan_complete`, which `app.py` maps to `"fresh"`: **a failed diagnosis turns the dot green** ("Diagnostics complete" or the previous run's verdict) | `ui/pages/service_diagnostics_page.py:418-422`, `app.py:1108-1110`, `ui/tabs.py:1058-1067` | **matrix** |
| | · **Speed Test** — `_on_test_error` returns before recording anything when the page is hidden: no status, no history row; registry keeps the last success | `ui/pages/speed_test_page.py:1531-1536` | **matrix** |
| | · **Network Logger** — error lambda only sets the page label; registry stays `"running"` and Home monitoring status stays on while the logger is dead | `ui/tabs_logger.py:404-420` | read |
| | · **Devices, WiFi Networks, DNS Zone Map** — error → page label only; registry keeps the last success as `"fresh"` | `ui/plugin_page_mixin.py:421,463`, `ui/pages/dns_zone_page.py:463` | read |
| | · **CVE Tracker** — only `data_refreshed` → fresh; the page has no failure signal at all (verify whether it can fail before wiring one) | `ui/tabs.py:266-268` | read |
| F1d | Deco per-node client fetch failure → `log.warning` + `continue`: `get_all_clients()` returns a plain list with no partial marker. The warning itself stays (owner decision 2026-07-16); the defect is that the *result* does not say it is partial | `modules/deco_client.py:301-304` | **matrix**, log |

### F2 [P1] Background failures with no user-visible surface

| Source | Today | What the user sees | Tag |
|---|---|---|---|
| Scheduled speed test | `_on_probe_error: pass` | **nothing** | **matrix** |
| REST API bind failure | shipped builds (waitress bundled): `OSError` → `_serve` emits → `app.py` handler is `print()` (stdout is a `StringIO` in the windowed build). Source runs without waitress: werkzeug calls `sys.exit(1)`; `SystemExit` is not an `Exception`, escapes `_serve`, and `crash_net`'s thread hook deliberately ignores it — **no signal, no log** | **nothing**; page probe shows "Not running" without a reason | **matrix** (dev-server path), read (waitress path) |
| Notification channels | router's tracked delivery → in-memory delivery-log `FAILED` row; **no log record reaches any handler** | only if the user opens the delivery log; lost on restart. A broken SMTP password looks like working alerting | **matrix** |
| Keyring write (MQTT password) | `pass  # silently skip persisting the secret`; read returns `""`, indistinguishable from "never set" | **nothing** — password silently not saved | **matrix** |
| Availability, Certificate, Service, Health, Passive Observer, Trend Forecast | G6 `_wire_monitor_error_surface`: `log.warning` + one status-bar note per session, "see log for details" | one transient line — names no log, no button, **overwritten by the next status write** | **matrix** |
| SNMP trap receiver | page label `⚠ {msg}` | only on its page, raw | read |
| Syslog receiver | page label: what + raw text + remediation | only on its page — the best in-repo message shape | read |
| Report scheduler | page handler | only on its page | read |
| **Startup failures, any always-on worker** *(found S3)* | every `_wire_*` in `app.py` connects **after** `Dashboard()` is built, seconds after the workers started; a cross-thread signal emitted with nothing connected is dropped | **nothing** for a failure in the first cycle — the G6 note and the syslog/SNMP page `on_error` never fire for it; a one-shot failure (passive observer start, SNMP bind) is lost for the session | **probe**: `ProactiveProbeWorker` failing at start — connected before `start()` got `['division by zero']`, connected 1 s after got `[]`. App-health wiring (S3.3) connects before `start()`; the legacy surfaces are unchanged |
| **Syslog port fallback** *(found S3)* | `SyslogReceiver.open()` tries 514 → `FALLBACK_PORT` → **port 0**, which always binds | a taken 514 is not an error: the receiver listens on a random port no device sends to, and the page says "Listening on UDP :54321". The bind-error path is practically unreachable | read. A degraded state (listening, but not where devices send), not a failure — candidate for S4/S7, not fixed |

### F3 [P2] The "always-on" in-app alert surface is a shared single line
`_surface_alert_in_app()` (`ui/dashboard.py:768-789`) writes to `_set_status()`, the same single
line ~40 other call sites write. Alerts are not lost (Action-needed card, tray badge,
Notifications page), but the status line cannot carry anything that must be seen. It prefixes
🔴🟡🟢 emoji. **read**, clobbering **matrix** (F2-G6)

### F4 [P2→P1 for diagnosability] The diagnostic record has no shape
- No root logging configuration exists: `log.warning` falls through to `logging.lastResort` and is
  written as **message only** — no timestamp, level, logger or version. `debug`/`info` are
  dropped. **matrix** (root handlers `[]`, output `'Availability monitor error: boom\n'`)
- Cost, in one example: `bfe1dd1`'s live-graph/QSS floods fix is in HEAD, yet the newest 2,000
  lines still hold 785 `Tight layout not applied`, 280 `No artists with labels`, 24
  `Unknown property cursor`, 78 `QProcess: Destroyed while process`. The file cannot say whether
  current code wrote them (suspects: `history_page.py:149`, `reports_page.py:136`,
  `hub_card.py:791`) or an older build sharing the file. **log**
- Each dedicated log (shutdown, signal_quality, theme_switch, scan_timing) re-solves formatting and
  rotation individually. **read**

### F5 [P2] RULE-A2: raw exception text in user-visible sinks — 95 sites
Census (a) recognises raw values by how they were bound: an `except … as X` name, an error-slot
parameter (`on_error`, `_on_scan_failed`), or a lambda connected to an error/failure signal.
**census**
- 26 × `worker.error.connect(lambda e: label.setText(f"⚠ {e}"))` — `ui/tabs_recon.py`,
  `ui/tabs_monitors.py`, `ui/plugin_page_mixin.py`, `ui/tabs_analysis.py`, …
- 8 × `ToastManager.show(f"Export failed: {exc}", "error")`
- ≥10 × `QMessageBox.warning/critical(…, str(exc))` — `tabs_analysis.py`, `tabs_analysis_isp.py`,
  `log_source_panel.py`, `reports_page.py`, `tabs_recon.py:1264`
- Easiest conversions — already carry what + next, only embed the raw text: `syslog_page.py:335`,
  `dhcp_lease_page.py:245`, `dns_zone_page.py:467`, `geo_map_page.py:1126`, `tabs_logger.py:407`
- No shared translation helper exists anywhere in the tree.

### F6 [P2] Toast system gaps
- Three calls use `"warning"`, which toast.py does not define — each renders with the accent
  border, an ℹ icon and **no auto-dismiss** (sticky info): `app.py:2072` (no email channel),
  `ui/dashboard.py:2076` (grade dropped), `ui/pages/inventory_page.py:2465` (need 2 sessions).
  **matrix**, census
- A 4th toast silently evicts a sticky error toast; toasts before `attach()` vanish. **matrix**
- No error toast has an action — only kind `action` carries a button. **read**

### F7 [P2] Silent broad swallows — 741
Broad handlers whose body is only `pass` or a constant/name fallback: **741** — entrypoints 37 ·
modules 304 · ui 386 · workers 14. (The earlier "~865" also counted debug-only and "other"
bodies; D6 accepts a debug log with `exc_info` as a legitimate outcome, so those are excluded.)
Top files: `ui/scan_wiring.py` 46 · `app.py` 37 · `modules/utils_net.py` 25 ·
`ui/scan_enrichment.py` 25 · `ui/dashboard.py` 19 · `ui/pages/inventory_page.py` 19 ·
`ui/nav/builder.py` 17 · `ui/pages/home_data_mixin.py` 15 · `modules/rogue_device.py` 14 ·
`modules/dns_zone_scanner.py` 11 · `ui/monitor_state.py` 11 · `ui/tabs_logger.py` 11 ·
`ui/widgets/hub_helpers.py` 11. **census**. Most are legitimate; RULE-LINT2 requires a comment,
not a visibility decision. RULE-WIN23 records that this class hid locale bugs for the life of the
product.

### F8 [P3] Vocabulary (RULE-A3)
`"Error"` ×7, `"Medium"` ×4 and `"Low"` ×1 (`os_fingerprint`), `"Warn"` ×1
(`monitor_overview_page`) — per-site check needed; some are state words. **census**

### F9 [P3] Modal confirmations for non-decisions
17 `QMessageBox.information` sites. Per-site check needed. **census**

### S0.3 — the three areas not covered by the first pass

| Area | Finding | Verdict |
|---|---|---|
| **Suppression transparency** | Maintenance windows: visible on the Maintenance page (active-window KPI, suppressed-alert count, last-500 suppression log) but nowhere on Home. Snoozes: cert rows grey out; inventory confirms by toast. Evidence-gate holds: no UI — by design (Signal Quality). Opt-in rules: the channel panel states "All alert rules are disabled by default — you must opt in." | Adequate. Optional S9.3: a Home hint while a maintenance window is suppressing alerts |
| **Capability gating** (admin / Npcap) | Nav items carry admin/Npcap pills (`ui/nav/builder.py:674`); `NpcapMissingBanner` on Security Overview, 802.11 Monitor, and two tab surfaces; workers emit remediation text ("Run as Administrator/root with Npcap installed"). The gap is the *background* path: a missing Npcap makes ARP/DHCP watch fail and the dot clears (F1a) | Consistent on pages; background half fixed by S1.1. S9.4 shrinks to a wording pass |
| **Headless** | `cli.py` writes errors to stderr and exits non-zero (e.g. `cli.py:84-89`). `svc.py` already logs start, stop and errors to the Windows Event Log via `servicemanager` (`svc.py:219-243`) | S10.1 shrinks to routing app-health conditions through these existing channels |

---

## 4. What already works — keep and reuse

- Crash net: `modules/crash_net.py`, `_fatal` (RULE-A1/A2 compliant), `modules/diagnostic_report.py`,
  unclean-exit strip, session records.
- Alert pipeline: `RULE_CTA` "Fix this" routing audited by `--audit-alerts`; evidence gating.
- `not_testable` scan state — the right semantics for "blocked, not clean".
- Plugin polling → `INFRA_UNREACHABLE` — a failure *state* that resolves.
- `syslog_page.on_error` message shape; strip dismissal-per-key pattern; `svc.py` Event Log writes.
- `AuditFinding` framework (`modules/scan_guidance_audit.py`, `alert_audit.py`).

---

## 5. Decisions — accepted 2026-09-15

| # | Decision |
|---|---|
| **D1** | "NetSentinel can't see X" failures are **app-health conditions**, separate from network alerts. `INFRA_UNREACHABLE` stays an alert |
| **D2** | Conditions render as a **strip under the Home freshness row + the existing tray health dot**, behind `experimental/app_health_v1` (RULE-EXP1); owner looks at it live before any layout expansion |
| **D3** | Conditions are **in-memory** at first; no schema bump |
| **D4** | A formatted, rotated **`netsentinel_app.log`** (timestamp, level, logger; version in the session header) at all three entry points; `stderr.log` stays raw |
| **D5** | RULE-A2 enforced by a **locale-free translator + shrink-only ratchet** (ratchet landed in S0) |
| **D6** | Broad swallows: **ratchet + triage, never rewrite**. A broad handler must log at debug with `exc_info`, mark its result degraded, or surface (ratchet landed in S0; codified as RULE-SURF2) |

---

## 6. Sprint plan

Every sprint closes with `/sprint end` (RULE-SD1) and reserves its last slot for stabilization
(RULE-STAB1). `modules/` work is test-first (RULE-TDD1); every bug fix starts RED (RULE-T3).
After each sprint, re-run `docs/spikes/error-surfacing-matrix.py` and lower any ratchet baseline
the sprint reduced. **Minimum high-value path: S1 → S2 → S3 → S4.**

### S0 — Baseline and verify ✅ 2026-09-15
- ✅ **0.1** `tools/check_error_surfacing.py` + `tests/test_error_surfacing_ratchet.py` — baselines:
  raw sinks 95 · silent broad {entrypoints 37, modules 304, ui 386, workers 14} · invalid toast
  kinds 3 · labels without error path 7.
- ✅ **0.2** Live verification matrix — 14/14 REPRODUCED (§7). Found one thing worse than
  predicted: the REST API dev-server path exits via `SystemExit` with no trace.
- ✅ **0.3** Suppression transparency, capability gating, headless (§3).
- ✅ **0.4** D1–D6 recorded (§5); RULE-SURF1 + RULE-SURF2 written.

### S1 — Stop the lies (small diffs, highest value per line) ← **next**
- **1.1** ARP/DHCP watch errors → `_nav_set_scan_state(label, "error", error=…)` instead of
  clearing the dot (`app.py:987`, `app.py:1013`). Matrix rows F1a-ARP/F1a-DHCP flip.
- **1.2** Registry error paths (F1c): Service Diagnostics `_on_error` must not emit
  `scan_complete` (emit a failure signal → `"error"`); Speed Test records the error even when
  hidden; Network Logger error → `"error"`; Devices / WiFi Networks / DNS Zone Map error slots →
  `"error"`; CVE Tracker only if the page can actually fail. Ratchet (d) → 0.
- **1.3** Toasts: define a real `warning` kind (AMBER, ⚠, finite auto-dismiss) — fixes all three
  call sites at once; never silently evict a sticky error; queue until attached. Ratchet (c) → 0.
- **1.4** Keyring write failure is told in place ("could not be saved to Windows Credential
  Manager — you will be asked again next launch"); read failure distinguished from "not set".
- **1.5** REST API `_serve` must catch `SystemExit` from the dev-server fallback and emit it, so
  the S3 wiring can ever receive a bind failure.
- **1.6** Stabilization.
- **Done when:** each item has a RED-first test; matrix rows F1a, F1c-SVC, F1c-SPD, F2-KEY,
  F6-WARN, F6-EVICT, F2-REST flip to NOT REPRODUCED (F2-REST: the error signal now arrives);
  `debug_launch` OK.

### S2 — A diagnostic record you can read  *(D4)*
- ✅ **2.1** `modules/app_logging.py` (TDD): root config per entry point (RULE-WIN26 placement) →
  `netsentinel_app.log`, `%(asctime)s %(levelname)s %(name)s: %(message)s`, UTF-8 with
  `errors="replace"` (RULE-WIN19/24), session header with version and build flavour; added to
  `log_rotation` and the diagnostic report; per-entry-point AST wiring guard.
- ✅ **2.2** Notification delivery failures recorded at `warning`, rate-limited per channel.
- ✅ **2.3** Repeating-warning limiter (`logging.Filter` keyed on logger + message template) — keeps
  the Deco warning per the 2026-07-16 decision without the flood.
- ✅ **2.4** (2026-09-19) Measured in two phases, because an idle hour cannot answer the question:
  the flood shapes come from *rendering pages*, and nobody navigates an idle window.
  **Phase A — a real source session, 7.4 h (07:59:32–15:24, pid 31440, healthy throughout, crash and
  exception logs byte-identical).** The formatted log took **11 records**, all parseable (0 lines
  that are neither a record nor a continuation), and **nothing at all after 08:53** — 6.5 h of
  silence. Top shape: the Deco per-node client fetch (`modules.deco_client`) at **6 in the first
  hour**, which is the 2026-07-16 decision working as intended, then nothing. Startup adds one
  scapy `CryptographyDeprecationWarning`, two `AutoDateLocator`, one `Tight layout not applied`.
  **Phase B — an offscreen sweep of all 74 pages** (`_nav_rail_go_to` per page, an INFO marker
  logged before each so every warning has an owner): **3 warnings total**, none of them page-driven.
  **Verdict: nothing to fix.** Of the five suspects, four — "No artists", QSS `cursor`,
  `QProcess: Destroyed while process`, scapy "MAC not found" — did not appear once, idle or swept.
  The 785/280/24/78 counts that motivated this item are `netsentinel_stderr.log` history from older
  builds sharing that file, exactly the F4 ambiguity: `bfe1dd1` had already fixed them.
  `Tight layout not applied` is current but is **one line per session** and transient: identified by
  wrapping `TightLayoutEngine.execute` and walking the canvas's parent chain (the stack has *no*
  NetSentinel frame — the attribution trap below is real), it is `_RttMiniChart` inside
  `HomeAutomationPage`, whose canvas is **280 × 16 px** during the first paint, before layout gives
  it its 3.5 × 1.4 in. Tight layout cannot fit axis decorations into 16 px, so it says so, once.
  Neither `history_page.py:149` nor `reports_page.py:139` (not `:136`) emitted anything: their
  `set_tight_layout` deprecation is a `PendingDeprecationWarning`, which Python ignores by default
  and only pytest surfaces. **Proposed cap (for the done-when): no single shape above 12/h** — the
  measured worst is 6/h in the first hour and 0.8/h over the session.
  **Attribution trap (confirmed):** stderr.log attributes `Tight layout not applied` to
  `app.py:2458`/`app.py:2670`, which is `app.exec()` — matplotlib's `warn_external` skips its own
  frames, and a paint-time draw has no Python caller below the event loop, so `showwarning` sees
  **zero** app frames. Timestamp-against-navigation works only for paint-time warnings; a
  background thread's warning (Deco) lands under whatever page is open and means nothing. To name a
  figure, wrap the layout engine and read `fig.canvas`'s parent chain.
  **Observation, not chased:** the Deco warnings stop after 08:53 and the log is silent for 6.5 h.
  Either the node fetches started succeeding or the poll stopped; nothing logs success, so the log
  cannot say which.
- ✅ **2.5** Stabilization — commit gate steps 1–3 green on the S2 tree (2026-09-17): ruff, mypy,
  pip-audit clean · suite `[PASS]` 7,824 passed / 6 skipped · `debug_launch` OK · matrix F4
  NOT REPRODUCED.
- **Done when:** matrix row F4 flips; every `app.log` line after a 1 h run has time/level/logger;
  top repeated shape under an agreed per-hour cap; diagnostic report includes `app.log`.

### S3 — App-health conditions: the model  *(D1, D3 — no UI change)* ✅ 2026-09-17
- ✅ **3.1** `modules/app_health.py` (TDD, pure Python): `ConditionSpec` (fixed text, severity
  validated against RULE-A3's set) + immutable `Condition` snapshots; `AppHealth.report_failure()` /
  `report_ok()` / `get()` / `active()` (most severe, then longest-standing, first) / `subscribe()`.
  One condition per key with a count; the newest cause's text wins within an episode; first success
  resolves; a later failure opens a new episode. Subscribers hear **transitions only**, on the
  reporting thread, outside the lock (a raising subscriber is logged with `exc_info` and cannot
  silence the others). Thread-safe — 8 threads × 500 reports lose no count. 15 tests.
- ✅ **3.2** `modules/error_text.py` (TDD): `explain(exc) → Explanation(kind, why, next_step)` from
  structure only — errno/`winerror` (10048 in use, 10013 blocked port ≠ file `PermissionError`,
  ENOSPC/112), exception type (refused, timeout, `gaierror`), HTTP status (urllib + duck-typed
  requests), SMTP reply code, keyring type, SQLite `sqlite_errorcode`; walks `__cause__`/`__context__`.
  Every test message is non-English or OS-produced; a guard test proves English text alone
  classifies nothing. 18 tests. **Decision:** worker `error` signals carry `str` only (8 ×
  `pyqtSignal(str)`, 2 × `(str, str)`), so `explain()` runs only where the exception is still in
  hand — its first consumer is the REST bind path; the Qt-wired producers use fixed catalogue text.
  Structured error payloads stay out of scope (S5-sized).
- ✅ **3.3** Producers. Text lives in one reviewable module, `modules/app_health_catalogue.py`
  (every CTA checked against `KNOWN_LABELS` by test). `app.py::_report_worker_health()` connects the
  six G6 monitors, scheduled speed test, syslog + SNMP receivers and report scheduler — **before each
  `start()`** (see §3, startup failures; `tests/test_app_health_producers.py` pins connect-before-start
  per worker from `main()`'s AST, mutation-checked). `NotificationRouter.set_app_health()`: a channel
  condition after `_CONDITION_AFTER_FAILURES = 3` consecutive failures, resolved by the next delivery
  (mutation-checked; one test drives real webhook threads to a closed port). `RestApiWorker.report_to()`:
  raised on every failure branch with the `error_text` cause, resolved once the server thread has
  stayed up `_SERVING_AFTER_S = 1.5` s — the page probe cannot stand in (it succeeds when *another*
  program holds the port). The page's lazy hot-start worker is handed over via
  `RestApiPage.worker_created` → `ui/tabs.py::_watch_rest_api_worker`, so fixing the port resolves a
  launch failure. MQTT: `MqttPage.secret_persisted(bool)`. Both REST `print()`s replaced by
  `log.warning`. Every transition is logged to the D4 app log (`netsentinel.app_health`). Severity:
  monitors Warning; passive observer, trend forecast, syslog, SNMP Info (bound at every launch whether
  used or not); notification channels High. Existing surfaces (G6 note, page labels, registry) are
  untouched — additive until S4.
- ✅ **3.4** `DecoMeshClient.get_all_clients()` returns `MeshClientList(list)` with `failed_nodes`;
  every caller unchanged, warning kept (2026-07-16 decision). Matrix F1d NOT REPRODUCED. Consuming
  it (the plugin status `extra`) is S4 — `plugins/deco_plugin.py` is hash-signed, so touching it means
  re-signing `data/plugin_hashes.json`.
- ✅ **3.5** Stabilization — see sprint log.
- **Done when:** a RULE-T7 test drives each producer's real error signal → condition active →
  success → resolved. ✅ `tests/test_app_health_producers.py` (real worker classes, never started),
  `tests/test_app_health_rest.py`, `tests/test_notification_router.py::TestRepeatedDeliveryFailureRaisesACondition`.

### S4 — App-health conditions: the surface  *(D2; RULE-EXP1 flag)* ✅ 2026-09-17 (4.5 open)
- ✅ **4.1** `ui/widgets/app_health_strip.py` under the Home freshness row (built only with
  `experimental/app_health_v1` on — **unconditional since 10.2**) + tray dot/tooltip
  (`SystemTrayManager.set_app_health`,
  `_effective_health_state`). Row = severity dot · what · why + next · "Open <page>"; raw `detail`
  and "since HH:MM" in the tooltip only. Info never opens the strip; overflow past 3 and Info wait
  behind "Show N more". No timer (RULE-WIN18), no dismiss.
- ✅ **4.2** `FreshnessStrip.update_freshness(..., failing=)`: ON-but-failing = AMBER + `⚠`
  (`STATUS_ICON_WARN`, not colour alone), tooltip names the page a click opens, and a failing pill
  clicks through. Source: the scan registry's `"error"` for ARP Spoof Watch / DHCP Rogue Monitor /
  Broadcast Storm / Network Logger (`ui/monitor_state.py::_pill_failures`), `None` until the surface
  is attached; `_nav_set_scan_state` repaints those four without `_push_monitor_pills`' DB reads.
  Matrix **F1b NOT REPRODUCED**. *Follow-up (owner, same day):* the monitoring-card and
  recommendation pill sets got the same failing state (`home_data_mixin._paint_failing_pill`).
- ✅ **4.3** `_wire_monitor_error_surface(note=not flag)`; the per-error `log.warning` stays. Only
  G6's note is removed (decision 3). Matrix **F2-G6, F2-SPD NOT REPRODUCED**; F2-REST and F2-HOOK
  now also require the strip row with its CTA.
- ✅ **4.4** `modules/scan_guidance_audit.py::audit_app_health_ctas` → `APP_HEALTH_CTA_RESOLVE` in
  `run_all` over `ALL_STATIC` + one channel condition per `CHANNEL_TYPES`. `python app.py --audit`
  PASS.
- ✅ **4.4a** `ui/app_health_bridge.py` — the only ui/ `subscribe()` (AST-guarded). Its callback only
  emits a private signal wired to its own slot with an explicit `QueuedConnection`, so surfaces run
  on the GUI thread one turn later even for a GUI-thread report. `attach_surface()` renders once at
  attach, so a failure raised before the window existed still shows.
- ✅ **4.4b** Flag-on path: `app.py::_seed_listener_pages` after `_wire_logging` — an active
  syslog/SNMP condition → `page.on_error(detail)`, else the worker's new `listen_port` →
  `on_status("Listening on UDP :N")` (that status was dropped at every launch too). Legacy path
  untouched; G6's startup gap is closed by the strip rendering from `active()`.
- ✅ **4.4c** Turning off resolves: REST API (`RestApiPage.enabled_changed` →
  `ui/tabs.py::_on_rest_api_enabled_changed`), scheduled speed tests (`_wire_speedtest_scheduling`
  gets `health`), and a removed/disabled notification channel (`NotificationRouter.set_channels`,
  TDD).
- ✅ **4.4d** `plugins/deco_plugin.py::_partial_marker` puts `extra["failed_nodes"]` in both
  `get_status()` and the `--netsentinel` shim (absent = complete; `getattr` for older
  `deco_client`). Hub card: `⚠ incomplete` in AMBER with the node names in the tooltip; device page:
  AMBER banner (`hub_helpers._partial_clients_text`). Degraded result, not a condition (decision 6).
  Re-signed — only the Deco hash changed.
- ✅ **4.4e** `SyslogWorker.bound(int)` → `app.py::_report_syslog_port` (connected before `start()`,
  AST-pinned): a port other than 514/5140 raises `listener:syslog_port` (Info). Measured: a taken
  port falls back to 5140 whether held plainly or with `SO_EXCLUSIVEADDRUSE`, so this fires only
  when 5140 is taken too.
- ✅ **4.5** Owner looked at it live 2026-09-18 — see *Live look*. **The fault recipe below does not
  work** (L4/L5): enabling the API only probes, and `http.server` shares the port. Use an
  `SO_EXCLUSIVEADDRUSE` holder on 8765 and relaunch with the API enabled. **The flag step below
  is obsolete as of 10.2** — the surface is always on; a source run needs no setup. Original
  note: a source run (quit the Store build first, RULE-WIN16) with the flag set:
  `python -c "from PyQt6.QtCore import QSettings; QSettings('NetSentinel','NetSentinel').setValue('experimental/app_health_v1', True)"`.
  Fault recipe for A2/A3: occupy the REST port (`python -m http.server 8765`), enable the REST API
  → row + amber tray; stop `http.server` and toggle the REST API off and on → row clears once the
  server has stayed up 1.5 s (switching it off alone also clears it, 4.4c). **Not** the channel
  "Send test" buttons: they call `notification_channels._deliver_*` directly, bypassing the router,
  so they can never raise or resolve a `notify:` condition. Record acceptance here.
- ✅ **4.6** Stabilization — see sprint log.
- **Decisions (owner, 2026-09-17 — all recommendations accepted):** (1) Info conditions never open
  the strip on their own — listed behind "N more" when it is already open, and on their source page;
  (2) tray dot: Critical → red, High/Warning → amber, Info → no change, a red network state wins;
  (3) 4.3 removes only G6's note — the other `_set_status` writes, alert line included, stay until
  S9.1; (4) a pill's failing state is the scan registry's `"error"` for its label — no new
  producers; (5) 4.4b: with the flag on, pages are seeded from the registry at wire time and the
  listeners' real port is read from the worker; flag-off legacy path untouched (deleted in S10.2), no
  replay buffer; (6) 4.4d: a partial Deco fetch is a degraded *result* on the plugin surfaces
  (D6 (b)), not a condition; (7) 4.4e: only the port-0 fallback raises an Info condition (5140 is
  the normal non-root fallback), via a structured `bound(int)` signal; (8) no dismiss in v1.
  Folded into 4.4c (same defect): turning scheduled speed tests off, and removing/disabling a
  notification channel, also resolve their conditions.
- **Acceptance (RULE-REQ1):** (A1) flag off — existing tests unchanged, G6 note still written;
  (A2) flag on, fault injected (REST port occupied; webhook to a closed port ×3) — a strip row with
  what/why/next and a CTA that opens the named page appears within one producer cycle; tray dot
  amber, tooltip names it; (A3) fault removed — the row disappears on the next success without a
  restart, tray returns to the network state; (A4) a visible row repaints on theme switch, both
  themes; (A5) `test_page_timer_lifecycle` still passes.
- **Done when:** with the flag on, every P1 matrix row shows a condition with a working CTA and
  resolves once the fault is removed.

### S5 — Actionable messages I: worker errors  *(D5)* ✅ 2026-09-17 (live look open)
- **Design decision (owner, 2026-09-17 — recommendation accepted): fixed text per site, raw in
  the tooltip.** Not `error_text.explain()`, which needs the exception: for 11 of the 26 lambda
  sites it was flattened to text inside `modules/` (`result.error`, `on_error(...)`) or in a child
  process (STP, storm) before the worker saw it, and where the worker does hold it (its catch-all
  `except`) the cause is a bug and `explain()` returns `unknown`. Rejected: **structured payloads**
  — `_nav_set_scan_state(error=e)` is `json.dumps`'d inside `except Exception: pass`
  (`ui/nav/builder.py:887`), so a non-`str` payload silently stops the whole registry persisting;
  plus `@pyqtSlot(str)` slots, AST-pinned app-health producers, tests. **Translating at the
  worker** — still one `str`, so the raw detail leaves the UI (tooltip, registry, app-health
  detail) and module-flattened exceptions stay invisible. Cost accepted: the visible *why* lists
  likely causes, not the diagnosed one. No `explanation=` parameter yet (RULE-DBG5: nothing would
  pass it) — S6.1 adds it with its first caller.
- ✅ **5.1** `ui/error_display.py`: `show_worker_error(label, raw, spec)` → `⚠ what. why next`;
  raw as tooltip (`safe_tooltip`) and right-click *Copy error details* **only while the label
  still shows the message** — an event filter compares `label.text()`, so the next status write
  ends the error and none of the scan-start paths needed a clear call; one `warning` per shown
  error under `netsentinel.worker_error.<key>` (per site, because S2.3's limiter keys on logger +
  template). Also `worker_error_text()` / `record_worker_error()` for a sink with no tooltip.
  Text: `ui/worker_error_catalogue.py`, 31 entries, each *why* written from what that producer can
  raise; test-enforced ≤ 140 visible chars (17 of the 24 lambda labels do not wrap), every site's
  `WE.<NAME>` resolved statically (a typo there would raise only when the scan fails), no unused
  entry. RULE-B1 hiddenimports added.
- ✅ **5.2** 26 lambdas + the five what-and-next slots + SNMP trap page. Syslog/SNMP pages reuse
  `SYSLOG_RECEIVER` / `SNMP_TRAP_RECEIVER` so page and strip agree — their status labels now wrap
  (**deviation from "no layout change"**: that text is ~190 chars; a non-wrapping label would push
  the page's minimum width past 1,000 px). Wording corrected on the way: Network Logger said
  "check network connectivity", but only `NetworkLogger.start()` creating the CSV in Documents
  reaches that signal; syslog said "check that UDP 514 is not blocked", but a taken 514 never
  errors. Scheduled Scans' `_sched_log.append(f"⚠ {e}")` (census-blind: `append` is not a sink
  attr) converted via `worker_error_text` + `record_worker_error`.
- ✅ **5.2a** *(owner, folded in)* SMB **Stop** no longer shows as a failure: `enumerate_smb`
  returns `error="Cancelled"` for a Stop between tiers, which painted "⚠ Cancelled" and a red dot.
  `SMBEnumWorker.stopped` fires when `res.error` and its own stop flag is set (never the text,
  D5); `_ReconTabsMixin._on_smb_stopped` puts back the registry entry the run replaced, or
  `"never"` on a first run.
- ✅ **5.3** Ratchet (a) **95 → 63**.
- ✅ **5.4** Stabilization — see sprint log. Matrix row **F5** added (real SNMP trap + DNS zone
  error slots, sv-SE raw): REPRODUCED on HEAD, NOT REPRODUCED after.
- ✅ **5.5** Done 2026-09-18 (*Live look*; unelevated Port Scan works here — an unresolvable host is the fault). Was: trigger a failure on a
  non-wrapping label (e.g. Port Scan (TCP) without admin), hover for the raw text, right-click
  Copy, then start the scan again and confirm the tooltip is gone; Syslog/SNMP page wrap.
- **Remaining for S6.3** (same helper): ~17 worker-error *slots* still embed raw text —
  `wifi_monitor_page`, `speed_test_page`, `threat_intel_page` ×2, `trend_page`, `baseline_page`,
  `protocol_viz_page`, `network_doc_page`, `tabs_scan` DNS bench, `tabs_recon` registry fetch,
  `hardware_browse_mixin` ×3, `wifi_heatmap_page` scan, plugin pre-scan, `network_map_page` LLDP,
  `service_diagnostics_page`. S6.4: consider teaching census (a) `append`.

### S6 — Actionable messages II: exports, dialogs, toasts
**Sizing (2026-09-17, before any code).** Census (a) 63 = **44 except-as sites** (8 export toasts ·
10 `QMessageBox` · **26 labels/status lines no S6 item named**) + **19 worker-error sinks** (18 slots
+ the `tabs_recon` registry lambda; S5's list of 17 missed `diagnosis_page._on_isp_error` and
`network_doc_page._on_error`'s second sink). What can raise inside the 44 `try` bodies: file I/O ~26,
database 3, network 1, our own validation text 2, a programming bug only ~12 (`explain()` →
`unknown`). Three findings made while sizing:
- **`ToastManager.show_toast` never existed.** Four success paths call it inside their `try`, so the
  `AttributeError` lands in the failure branch: a successful Export All Data (ZIP), Reports "Copy
  summary" and ISP complaint copy each show a *failure* modal; a successful Network Map PNG save
  shows nothing. Shipped v2.1.13–v2.1.25. RULE-SURF1's inverse.
- **Census (a) blind spots — 7 visible raw sinks it cannot count:** the `QMessageBox as _MB` alias
  (`export_mixin.py:41`), `_verdict.update(...)` ×2 (`plugin_page_mixin.py`), matplotlib
  `set_title` / `ax.text` (`live_bandwidth_page`, `app_traffic_page`), `QListWidgetItem(f"⚠ {msg}")`
  (`speed_test_page`), a local-function `_set_status` (`credential_dialog`). The `append` family has
  0 true hits after S5 (1 false positive tree-wide: `app.py`'s smoke-test list). Out of AST reach:
  raw text laundered through `.emit(str(exc))` into another file's sink (`lab_mode_page.py:85`).
- **Measured export failures (this machine):** a CSV open in Excel (`CreateFileW`, share-read only),
  a read-only file, a directory and Program Files all arrive as `PermissionError` errno 13,
  `winerror` None — structurally indistinguishable, so `permission_denied`'s "run NetSentinel with
  the required rights" would reach the Excel user. Missing folder / missing drive / path too long →
  `FileNotFoundError` errno 2; invalid name characters → `OSError` errno 22 — both `unknown`.

**Decisions (owner, 2026-09-17 — all recommendations accepted):** (1) **pass the exception, the spec
opts in** — `WorkerErrorSpec.explains: frozenset[str]` names the `error_text` kinds a site may voice
in place of its own why/next; the helper runs `explain()` itself. Rejected: an `explanation=` kwarg
(a second argument each site can omit silently — RULE-DBG5's shape), and "any known kind wins"
(`explain()` is context-free: see the Excel measurement). (2) **Every site keeps today's channel** —
toasts stay toasts, modals stay modal; loudness is S9.2's. `log_source_panel.py:808` must stay modal
regardless (it fails inside an open export dialog, which would hide a main-window toast). (3) **Split:**
S6 = 6.0–6.3a + stabilization (ratchet → 26); S6b = 6.3b + 6.4 + stabilization (→ 0). (4) Census (a)
counts `append` / `appendHtml` / `insertPlainText` / `setHtml`, `ui/` only.

- ✅ **6.0** RED-first (`tests/test_toast_call_sites.py` + four behavioural regressions, watched fail
  on the real `AttributeError`): the four `show_toast` calls → `ToastManager.show(…, "success")`, the
  confirmation moved to the `try`'s `else:`. RULE-SURF1 corollary written first (RULE-TP4).
- ✅ **6.1** `modules/error_text.py` (TDD, 4 cycles): `path_not_found`, `invalid_path` (errno 22 *with*
  `exc.filename` — a bare EINVAL stays `unknown`), `permission_denied` reworded (a real
  `CreateFileW` share-read lock must name "another program" and never "rights"/"administrator"),
  `KINDS` (test derives it from the module's own `Explanation(...)` calls). Toasts: an action button on
  any kind, `detail=` → message tooltip, both survive the pre-attach queue. `ui/error_display.py`:
  one resolver behind every helper — an exception `raw` voices `explain()`'s why/next only for a kind
  in `spec.explains`, detail `Type: message`, logged with `exc_info`; `export_failed(exc, spec, retry)`
  (**deviation from the plan's `site` string:** a spec per site, so the catalogue's static-resolution
  and every-entry-used tests cover exports too, and each names what was not saved). "Choose another
  location" only with `retry` *and* a `LOCATION_KINDS` cause. **9 sites**, each confirmation moved to
  `else:`. Catalogue: `WorkerErrorSpec.explains`, `FILE_KINDS`, explained text ≤ 220 chars (test).
- ✅ **6.2** `show_error_dialog(parent, raw, spec, retry)` — `what.` / why + next as informative text /
  raw behind *Show Details*, optional retry run after the dialog closes, through `run_dialog`.
  **11 dialogs.** Log range export parents the dialog to the open Export Log dialog and offers no
  button (pressing Export CSV asks again); the plugin wizard opts in to `disk_full` only (fixed
  folder). `NoPdfBackendError(RuntimeError)` (TDD). **Found while wiring it — measured with real
  headless Edge:** a missing folder and Program Files both raised "No PDF backend available — install
  Edge", because Edge exits non-zero with no reason, so every unwritable location fell through to the
  no-engine error on a machine that *has* Edge. `save_pdf_report` now opens the target for append
  before any backend runs (never truncates; removes a file it created), so the real
  `FileNotFoundError`/`PermissionError` reaches `explain()` — RED-first, then re-probed with Edge:
  missing folder → `FileNotFoundError`, Program Files → `PermissionError`, writable path still prints.
- ✅ **6.3a** The 19 worker-error sinks, 18 new catalogue entries, each *why* read from its producer.
  Pages whose `_set_status` carries colour (hardware, service diagnostics, Wi-Fi heatmap, 802.11
  monitor) keep calling it for the colour, then `show_worker_error` attaches the detail. Pre-scan: the
  one-line status bar gets `what.`, the verdict banner the full message (also the `_verdict.update`
  blind spot). AbuseIPDB appends to the local-feed verdict via `worker_error_text` +
  `record_worker_error`. Network Map's duplicate `log.warning` removed (the helper logs). **Three
  existing tests pinned the raw text** and were changed to assert the catalogue text:
  `test_dns_benchmark_tab`, `test_protocol_viz_page::test_live_error_stops_and_shows_translated_message`
  (named "translated", asserted the raw `boom`), and `test_scan_error_state_wiring`'s `MagicMock`
  status label (the S5 trap).
- **6.5** Stabilization — ratchet (a) **63 → 45 → 26** (all 26 are S6b's except-as sites). Matrix
  **17/17 NOT REPRODUCED**: new rows F6-EXPORT and F6-SUCCESS, both REPRODUCED against HEAD with the S6
  product files stashed first (raw `[Errno 2] …` path with no action; "Copy Failed" carrying the
  `show_toast` AttributeError).
- ✅ **6.6** Done 2026-09-18 by the agent, headless on the real path (*Live look*) — found and fixed
  L2 (toast cut its next step) and L3 (Copy summary failed on real data). Was: export over a CSV open in Excel
  (toast text, hover detail, "Choose another location" reopens the dialog); Copy summary succeeds with
  no "Copy Failed".

### S6b — Actionable messages III: labels, census closure
**Sizing (2026-09-17, d49cbd1, before any code).** Census (a) still 26, the same set. What each `try`
can raise, read from the called code: **11 only a bug** (`scan_enrichment` NL filter, `scan_wiring`
baseline — `load/save_device_baseline` swallow internally — and topology, `tabs_analysis` chart /
correlator / grading, `tabs_logger` analysis, `tabs_recon` risk scorer, `plugin_page_mixin` scan
startup, and both IoT sites, whose body only starts a `threading.Thread`). **12 opt in:** 6 writes to a
fixed folder → `disk_full` (auto-report, catalogue plugin copy, Register copy, `.nspkg` import, survey
save, Network Doc snapshot), 2 writes to a chosen path → `FILE_KINDS` (Export Report, heatmap PNG), 2
reads → `permission_denied` (floor plan, survey load), 2 Home Automation writes → `database_busy` +
`disk_full`. **3 fixed text only:** the Home Automation read, IP Calculator (user input), the update
check. Two measurements behind those: a real WAL write lock arrives as `OperationalError`
`sqlite_errorcode` 5 → `database_busy`, while a read under the same lock succeeds; and every network
kind is wrong advice for the update check — unresolvable host → "check the host name", refused →
"check the address and port", GitHub's anonymous rate-limit **403** → `auth_rejected` "check the user
name, password or API key" (the raw text arrived in sv-SE). Dashboard status-bar sites are **4**, not 5.
All 6 remaining blind spots re-verified; a wider scan found 2 more (below) and 2 false positives
(AbuseIPDB `no_result`, the hardware `DEPS:` card — both our own wording). None came in with S6.

**Decisions (owner, 2026-09-17 — all recommendations accepted):** (1) the update check moves off the
GUI thread in S6b (6.3c). (2) The IoT thread-affinity defect (finding below) is its own RED-first item
after S6b; S6b converts the two GUI-thread except sites and documents the `on_error=` lambda as a
census blind spot. (3) Plugin-protocol text (`FILE:`/`DEPS:`/`AUTH:`/`NET:`/`ERR:`) is plugin-authored
and stays; only `hub_helpers._classify_error`'s unmatched fallback is raw — fixed in both sinks it
reaches (credential dialog, hub card). (4) `.nspkg` validation and IP Calculator input: fixed text, the
specific reason in the tooltip; chart titles wrap.

*Findings while sizing:* **IoT Behaviour writes Qt widgets from a `threading.Thread`** —
`tabs_analysis._run_iot_learn._do_learn` (`progress_cb` → `QLabel.setText`,
`_populate_iot_baseline_table`) and `_run_iot_monitor._start` (the same, plus IoTMonitor's `on_error`
lambda). The drain-timer comment in the same function names this as an access-violation crash. Plugins
are copied to two folders: catalogue install and the plugin wizard use `~/.netsentinel/plugins`,
Register and `.nspkg` import use `get_app_data_dir()/plugins` (ARCH RULE 23) — not checked whether
anything breaks.

- ✅ **6.3b** The 26 except-as label/status sites + the census-blind sinks (plugin verdict, Live
  Bandwidth title, App Traffic chart text, Speed Test server list item, AbuseIPDB "could not test",
  credential dialog + hub card via `_classify_error`'s fallback). Dashboard status-bar sites (4) use
  `worker_error_text` + `record_worker_error` (a `QStatusBar` message has no tooltip). IP
  Calculator: fixed text with an example, the stdlib `ValueError` text in the tooltip — and **no log
  record**: a typo is the user's input, not an app fault. 33 new catalogue entries. **Deviation from
  "no layout change" (the S5 precedent):** the Home Automation and Wi-Fi heatmap status labels now
  wrap — both take explained text (~190–220 chars) and a non-wrapping label would widen the page;
  both are full-width rows in a vertical layout, so wrapping only makes them taller. Two sinks take
  `what.` only, because their label sits in a control row next to a stretch (App Traffic) or is a
  one-line status bar (scan startup, the `_on_prescan_error` precedent); Live Bandwidth's chart title
  carries the full message wrapped, since the page has no status label at all.
- ✅ **6.3c** Help-tab update check on a `_UpdateCheckThread` (the `ui/header.py::_start_update_check`
  shape), registered in `ui/shutdown.py::DASHBOARD_WORKER_ATTRS`, re-entry guarded per RULE-WIN13.
  It emits the **exception object**, so the helper still logs a traceback.
- ✅ **6.4** Census learned chart titles/`Axes.text`, `QListWidgetItem`, bare-name `_set_status`,
  `not_testable` slots and the `ui/` append family (not `.update` — pinned by its site test), plus
  `find_stringified_exception_args` (an except-as caller must pass the exception, not `str(exc)`).
  **Also needed a translator exemption:** `worker_error_text(WE.X, exc)` is the correct S6b pattern
  and mentions the caught name, so without it the census counted its own fix — 5 false hits.
  Ratchet (a) **26 → hard zero** (+ the new guard at zero); RULE-A2 rewritten to invariant + pattern
  + enforcer and moved out of RULE-ENFORCE1's "ratchet, not yet zero" line.
- ✅ **6.5b** Stabilization — suite, gates and matrix below.
- ✅ **6.6b** Done 2026-09-18 by the agent, headless on the real path (*Live look*). Was: Help → Check for updates
  while offline (the window must stay responsive, then show the fixed text), and IP Calculator with a
  bad address (fixed text + example, the exact reason on hover). Note the test suite overwrites
  `alert_rules/*` enables — re-arm them after any suite run, before judging alerting live.

*Next, deferred by owner decision (2):* the IoT Behaviour thread-affinity defect — its own RED-first
item, since the `on_error=` sink cannot be fixed from a background thread and folding a crash-class
fix into a text sprint would bury it.

### S6c — IoT Behaviour thread affinity  *(RULE-WIN27)* ✅ 2026-09-18
**Sizing (2026-09-18, against d32647a, before code).** The two IoT sites are the only `threading.Thread`
targets in `ui/` that write widgets — the other four (dashboard WAN IP ×2, header update check,
notification Send-test) already marshal by signal. Five defects, one root: the background thread
*owned* state. (1) `learn()`'s `progress_cb`, the baseline-table fill and the final status ran on the
thread (8 writes); (2) an exception escaped the thread, leaving "Learning for N s…" on screen for good;
(3) `_iot_monitor_obj` was assigned after `load_or_create()` (up to a 60 s learning pass), so Stop in
that window stopped nothing and the thread then started the sniffer with no drain timer; (4) a second
Start orphaned the first sniffer; (5) the `on_error=` lambda showed the module's raw text.

**Measured before choosing wording.** Scapy 2.7.0 re-raises the sniffer thread's exception from
`AsyncSniffer.join()`: with no capture driver (`scapy.arch.windows._NotAvailableSocket`, what scapy
installs when Npcap is missing) `learn()` raises `RuntimeError` at once and saves nothing. A read-only
baseline file raises `PermissionError` errno 13. `IoTMonitor.start()` returns in 0.2 ms and `stop()` in
7 ms — safe on the GUI thread. On this box unelevated capture works (Npcap not admin-restricted).

**Decisions (owner, 2026-09-18 — all recommendations accepted):** (1) three Dashboard signals (the
`_wan_ip_ready` pattern) rather than a QThread worker — `learn()` blocks in `sniffer.join()` with no
cancel, so a worker in the shutdown drain list would spend the whole shared deadline; (2) the Stop and
double-Start fixes are in scope; (3) RULE-WIN27 gets an AST guard.

- ✅ **6c.1** RULE-WIN27 written first (RULE-TP4) + `tests/test_ui_thread_affinity.py`: every
  `threading.Thread`/`Timer` target in `ui/`, including the lambdas it hands on and one level into
  same-class methods. RED on exactly the two IoT sites (8 writes), green on the other four.
- ✅ **6c.2** RED-first `tests/test_iot_thread_affinity.py` (7): real widgets, real signals, real threads,
  only the `modules/iot_baseline` calls replaced; a spy records each write's thread and forwards only
  GUI-thread writes. Watched fail 7/7 for the named reasons. One was worse than sized: a monitor start
  error showed the raw text and was then **overwritten by "Monitoring 1 IoT device(s)…"** — a failure
  rendered as healthy.
- ✅ **6c.3** Fix: `_iot_progress(int, str)` / `_iot_ready(int, object)` / `_iot_failed(int, object)` on
  Dashboard; the threads only emit. Runs are tagged (`_iot_learn_run` / `_iot_monitor_run`), so a
  stopped or superseded run's late signals are dropped. `IoTMonitor` is built and started in a
  GUI-thread slot; `on_error` emits `_iot_failed`, which halts the run before "Monitoring…" can be
  written. New entries `IOT_LEARN_RUN` (explains `disk_full`, the fixed-folder precedent) and
  `IOT_MONITOR_RUN`. `modules/` unchanged.
- ✅ **6c.4** Matrix row IOT-THREAD — see §7.
- ✅ **6c.5** Done 2026-09-18 by the agent with real capture (*Live look*). Was: IoT Behaviour after a Devices scan → Learn (30 s)
  updates the status and fills the table; Start → Stop during the learning pass leaves "Anomaly monitor
  stopped." and no sniffer running.

*Found while building, not fixed:* (a) `IoTMonitor.start()` never reports a capture failure — scapy
stores it on the sniffer (`running=True`, `exception=RuntimeError`) and `on_error` is not called, so
with no Npcap and baselines already on disk the page says "Monitoring…" while seeing nothing. The page's
`NpcapMissingBanner` covers the common case; closing it needs a `modules/` accessor (RED-first).
(b) `learn()` cannot be cancelled (its sniffer is internal) — Stop drops the run's result but the
capture runs to its end. (c) The baseline is written to `~/Documents/NetSentinel/` (ARCH RULE 23 allows
only the network logger there). (d) The notification Send-test result shows
`f"{type(exc).__name__}: {str(exc)[:120]}"` — a RULE-A2 sink laundered through a local and a signal,
the census's documented blind spot, so census (a)'s zero is visible sites only.

### Live look — 2026-09-18 (source run, `c43f228` + the fixes below)
Source build with `experimental/app_health_v1` on; Store build quit first (RULE-WIN16). The owner
clicked S4.5 and S5.5; for S6.6, 6.6b and 6c.5 the owner asked the agent to run them, which it did
**headlessly on the real code paths** (native platform, nothing shown, widgets rendered to PNG and
inspected) — no input injection into the owner's session. Crash and exception logs unchanged all
session (6,784,379 B / mtime 2026-07-30; 58,671 B / 2026-09-05).

| Item | Result |
|---|---|
| **S4.5** strip | ✅ owner. Both rows (REST, scheduled reports) with what/why/next and working "Open …", amber tray, repaint on both themes (A2/A4); the REST row cleared on turning the API off and on, no restart (A3, via 4.4c). **The recipe was wrong twice** — see findings L4/L5 |
| **S5.5** worker-error label | ✅ owner + log. Port Scan (TCP) runs fine unelevated here (Npcap not admin-restricted), so the fault was an unresolvable host (`192.168.256.1`): one-line label, hover raw, Copy, registry `error`. Tooltip/Copy end on the next status write — confirmed programmatically too (`_ErrorDetail._active()` False after it) |
| **S6.6** export + copy | ✅ agent. Real `InventoryPage._export_csv` into a real share-read lock: toast names another program, never rights/administrator; hover = raw `PermissionError`; "Choose another location" re-runs the export; traceback in the log. Rendering exposed **L2** (fixed). Copy summary **failed on real data** — **L3** (fixed); after the fix it builds on a backup of the live DB |
| **6.6b** update check + IP Calculator | ✅ agent. Update check with `HTTPS_PROXY` at a dead port (a real refused connection): click returns in 14 ms, fixed text, raw sv-SE `WinError 10061` on hover. IP Calculator `192.168.1.300`: fixed text + example, exact reason on hover, no log record |
| **6c.5** IoT Behaviour | ✅ agent, **real capture** (6 LAN devices from the ARP table, baseline path redirected to temp): Learn 30 s → "Baseline learned…" at +30.0 s, 6 table rows; Start → Stop at +3 s → "Anomaly monitor stopped." still showing after the uncancellable 60 s pass, no monitor built, no leftover threads |
| **S2.4** 1 h log noise | ⏳ still open — the owner closed the app between checks five times; needs one uninterrupted hour |

**Fixed in this session** (each RED-first, then GREEN):
- **L1 — every fixed-width spin box cut its value** (owner-reported: Port Scan rate showed "500 p").
  The global `QLineEdit { padding: 4px 8px; }` also reaches a spin box's internal line edit, so
  `SPINBOX_WIDTH_*` 100/72/92 left 33/15/25 px of text area: 16 of 22 sites clipped (every port box
  "65535", "5000 pps", "1440 min", "8760", "120"). Text area = width − 67 from 82 px up, floored at
  15 px below. Constants → **122/94/106**. `sizeHint()` is useless (158 px for every box) and
  offscreen fonts measure ~2× wider, so `tests/test_spinbox_text_fit.py` sweeps every site by AST
  and measures in a native child (`tests/_spinbox_fit_child.py`). RULE-QSS5 corollary.
- **L2 — S6's error toasts cut off their own next step.** `adjustSize()` sized the fixed-300 px toast
  from `sizeHint()` (the message at its unconstrained width) and the S6 action button sat inline,
  squeezing the message to 94 px: 195 px of text got 90, ending "…The file may be open in". Now
  `_Toast.fitted_height()` = `heightForWidth(_WIDTH)`, the action has its own row.
  `tests/test_toast_fits_message.py` (3, all RED first). New **RULE-UI2**.
- **L3 — scheduled reports and Reports → Copy summary failed on any real network.**
  `query_uptime_table()` returns an empty window as `None` with the key present, so
  `r.get("24.0", 100.0)` (RULE-NET1's trap) returned `None` and `min()` raised; a second copy in the
  fleet average. 5 of 26 live devices had no 24 h samples. An empty window now renders "—" and never
  counts as 100 %; all-empty rows are counted in the total only. 2 RED-first tests in
  `tests/test_report_scheduler.py`. This is the `scheduler:reports` condition the strip raised at
  every launch — the first defect the app-health surface found on its own.

**Found, not fixed:**
- **L4** — S4.5's recipe cannot raise the condition: enabling the REST API only *probes* the port
  (the page never starts a worker unless the probe fails), and the probe succeeds against another
  program. Working recipe: an `SO_EXCLUSIVEADDRUSE` holder on 8765 + relaunch with the API enabled.
- **L5** — `python -m http.server` binds with `SO_REUSEADDR`, which on Windows lets a second bind
  share the port: it produces no bind failure at all.
- **L6** — the dev-server path reports only "server exited with code 1": werkzeug prints the real
  cause (sv-SE `WinError 10013`) and calls `sys.exit(1)`, so `explain()` never sees it. Source runs
  only; shipped builds use waitress.
- **L7** — the Qt (non-native) save dialog opens in the process working directory: every export
  passes a bare filename, so a source run saves into the repo, and an installed build likely offers
  an unwritable folder. Default to Documents.
- **L8** — CVE Tracker's Export sits behind the empty state; with no tracked CVEs it cannot be
  found (the matrix row calls the method directly, so it never saw this).
- **L9** — IP Calculator keeps the previous valid value's bits in the Binary Address Visualiser next
  to the invalid-input error.
- **L10** — IoT Behaviour's Learn button reads "(60 s)" while the duration box (default 30 s) decides.
- **L11** — shutdown drain hit its 3 s deadline twice with `PluginPollingWorker` /
  `ProactiveProbeWorker` still running (a close ~10 s after launch); clean exit otherwise.

### IoT alert flood froze the GUI — RULE-WIN28  *(found 2026-09-19 during S2.4, owner-approved fix)*
The S2.4 session hung five minutes after the owner started IoT Behaviour's anomaly monitor: window
white, Windows "Not Responding", **and both crash logs flat** — the hang is invisible to the crash
net, which is why it reads to the user as a crash and to every log as nothing. Diagnosed live with
py-spy (RULE-DBG2): the GUI thread pinned in `_drain_iot_alerts` (`ui/tabs_analysis.py:531`), the
alert table at **9,788 → 9,910 rows in 5 s**, one core at 100 %, 687 → 775 MB in 2½ min. Two
pre-existing defects, each harmless alone (Phase 1 of `/debug` cleared both recent commits: the
drain dates from v2.1.29, and S6c only moved the queue hand-off):
- **Producer:** `iot_baseline.py` raised `NEW_PORT` for *every TCP packet* to a port absent from the
  baseline — no dedup and no SYN check, while the new-IP check beside it does dedup. A device
  *answering* clients sends to each client's ephemeral port, so serving anything is a flood.
- **Consumer:** `while True: get_nowait()` drained the whole queue in one 100 ms tick, each alert
  costing an `insertRow` + a `QPushButton` cell widget + `scrollToBottom` + an AlertEngine pass.

Fixed test-first (rule written before the fix, RULE-TP4): NEW_PORT only on an outbound SYN and once
per (device, port) via a per-monitor set — *not* by appending to `baseline.known_ports`, because the
CRITICAL `_ALWAYS_ALERT_PORTS` branch is checked first and a local set leaves the shared baseline
untouched; drain bounded to `_IOT_DRAIN_PER_TICK = 50`, table capped at `_IOT_ALERT_ROWS_MAX = 500`
newest rows with the status line reporting the total.

| Measured on identical input | Pre-fix (`fad2d53` worktree) | Fixed |
|---|---|---|
| 6,000-alert backlog, 50 ms heartbeat timer | **1 beat in 34 s** (loop frozen) | 208 beats, worst gap 78 ms |
| …table rows / drain time | 6,000 / 34.0 s | 500 newest / 13.1 s |
| 60 s real capture, 17 ARP devices, empty baselines | 284 NEW_PORT for 26 real (device, port) pairs | 0 (nothing qualified) |
| …same capture including this machine (it opens connections) | **2,203** (1,919 from one device ≈ 115k/h) | **2**, both real connections |

Tests: `test_iot_baseline.py` +4 (replies to ephemeral ports, repeated SYNs, an always-alert port,
a baselined port), `test_iot_thread_affinity.py` +3 (bounded batch, newest-rows cap and total, an
AST guard that no `while True` wraps `get_nowait()` in `ui/`). All 7 watched fail first.

### S7 — Swallowed failures I: detection modules  *(D6)* ✅ 2026-09-19
**Sizing (2026-09-18, against `c43f228`, before code).** Census (b) counts **85** silent broad handlers
in the eight files: `utils_net` 25 (12 in non-Windows branches) · `rogue_device` 14 · `dns_zone_scanner`
11 · `network_diagnostics` 8 · `wifi_scanner` 8 · `name_resolver` 7 · `combined_discovery` 6 ·
`smb_enumerator` 6. First read: mostly (a) (best-effort platform reads, per-method name lookups where a
miss is normal, recv loops ending on a timeout, UI-callback guards, import fallbacks). **No (c)
expected** — these are on-demand scans; a failed run is not a standing "can't see X" condition.
(b) candidates, not yet triaged:
- **DNS Zone AXFR — confirmed RULE-SURF1 lie in a Security Audit tool.** `axfr_transfer` swallows every
  exception (`dns_zone_scanner.py:239`) and returns `[]`, and the progress line says "AXFR complete: 0
  record(s)"; `scan()` then writes the verdict "**AXFR refused by** <server>" at `LOW`. An unreachable or
  timed-out server reads as the server refusing a zone transfer — the *safe* outcome. `DnsZoneResult`
  has no failure field.
- `combined_discovery._arp_sweep` (L135): a failed ARP sweep with TCP still finding devices is not
  marked partial — the existing `not_testable` fires only on zero devices.
- `smb_enumerator._net_view_shares` (L355): a `net view` failure returns no shares — check how the
  tiers combine before calling it (b).
- `network_diagnostics` `_traceroute` (L270), `_dns_leak_test` (L301), `_speed_test` (L207): a failure
  becomes empty hops or a `-1` sentinel — check what What's Wrong? / Health Check render.
- `wifi_scanner`: a netsh failure already lands in `WifiScanResult.error` with advice — likely (a).
`combined_discovery` and `smb_enumerator` already carry `not_testable`/`not_testable_reason`;
`WifiScanResult` carries `error`.

**Decisions (owner, 2026-09-18 — all recommendations accepted):** (1) (a) = `log.debug("…",
exc_info=True)`, **no narrowing** of exception types (narrowing changes what propagates — stability
covenant); those records are written only under `NETSENTINEL_LOG_LEVEL=DEBUG` (root stays WARNING,
own loggers INFO), which is D6 as accepted. (2) (b) reuses existing fields; the one new contract is
`DnsZoneResult.axfr_error: str` — a fixed, locale-free reason chosen by exception type (timeout /
refused / unreachable), never `str(exc)`; verdict "Could not reach <server> for AXFR" at `UNKNOWN`,
page registry state `not_testable`. Not a whole-result flag: that run's mDNS results are real. (3)
**Checkpoint after 7.1:** triage all 85, bring the (a)/(b)/(c) split to the owner, then choose the
S7/S7b cut (the S6 precedent) before any (b) code. (4) The worksheet is generated tool output; only
(b)/(c) verdicts are recorded here — (a) sites document themselves once converted. Every (b) that
renders wrong today gets a matrix row REPRODUCED against a HEAD worktree first (DNS-AXFR: real
`axfr_transfer` against a closed loopback port).

**7.1 triage — checkpoint (2026-09-18, against `c166d87`; owner cut pending, no (b) code yet).**
`python tools/check_error_surfacing.py --worksheet <paths>` lists each hit with its function, the `try`'s
first statement, the fallback, the handler's own comment and shape facts (import / loop / OS branch /
nested) — it measured `utils_net` at **17** non-Windows handlers, not 12. **Split: (a) 75 · (b) 10 ·
(c) 0.** (a) per file: `utils_net` 25/25 · `rogue_device` 13/14 · `wifi_scanner` 8/8 · `name_resolver`
7/7 · `network_diagnostics` 7/8 · `dns_zone_scanner` 7/11 · `smb_enumerator` 5/6 · `combined_discovery`
3/6. Three (a) calls rest on a measurement rather than a reading: `arp -a` with no entries **exits 1**, so
`get_arp_snapshot`'s handler mostly sees a legitimately empty table; `net view` to an unreachable host
exits 2 after **21 s**, past `_net_view_shares`'s 15 s timeout, and the all-silent tier combination
already marks that run `not_testable`; Health Check already paints the `-1`/`""` sentinels of
`_speed_test`, `_get_public_ip`, DNS and HTTP as a red "—" or FAIL.

| # | Site (handlers) | What the user sees today | Carrier | Cut |
|---|---|---|---|---|
| B1 | `dns_zone_scanner.py:239` + `scan()` guard :414 (2) | **Two shapes, both measured on loopback.** (i) Unreachable / refused / timed out → the AXFR button runs `scan(…, mdns_timeout=0.0)`, so it shows "No DNS zone data found. **Try providing a DNS server for AXFR.**" at `LOW` — the server just provided. "AXFR refused by" is reached only when mDNS found services, which that button never runs. (ii) **A complete zone from a server that keeps the TCP connection open (RFC 7766) is discarded:** the recv loop reads to EOF, the timeout skips the parse, `axfr_transfer` returns `[]` (fake server, SOA/A/SOA: 2 records when it closes, 0 when it holds). An open AXFR — the exposure this tool exists to report — reads as no data | `axfr_error` (agreed) | S7 |
| B2 | `dns_zone_scanner.py:386` + guard :420 (2) | mDNS query cannot be sent (no route for 224.0.0.251) → "0 service(s)" / "No DNS zone data found". Not measured | none — `mdns_error` would be a 2nd new field | S7 if approved |
| B3 | `combined_discovery.py:135`, `:170` (2) | ARP sweep / TCP SYN raise without Npcap or elevation → "Found N device(s) … using: arp-cache, icmp-ping", registry `fresh`; the two most complete methods are absent and nothing says they failed | none — `error` means whole failure, `not_testable` means zero devices | S7 with a new field, or S7b |
| B4 | `smb_enumerator.py:427` (1) | **The shipped Tier-2 path** (impacket is not a dependency): `_run` swallows a failed `net use` login, every later `net` command runs as the scanner's own Windows account, and the result is `tier=2` with no error | `not_testable` + reason (needs B4a) | S7 |
| B5 | `rogue_device.py:162` (1) | IPv6 neighbour read fails → every device's "CLEAN — No known issues" silently includes a rogue-RA check that did not run. Not observed failing | none (dict contract) | S7b / record |
| B6 | `network_diagnostics.py:270` (1) | traceroute cannot run (Linux without `traceroute`) → empty table, identical to every hop silent; the correlator reads it as "no ISP evidence" | none | S7b / record |
| B7 | `combined_discovery.py:96` (1) | no default route → a blank CIDR sweeps a guessed `192.168.1.0/24`, named in the verdict but not flagged as a guess (and forced to /24 — ARCH RULE 26) | none | S7b / record |

- **B4a** (same tier combination, not a handler): `SMBEnumResult.plain_verdict` ignores `not_testable`
  and `_on_smb_result` paints GREEN when there are no risk flags. Measured: `enumerate_smb("192.0.2.1")`
  → `not_testable=True`, verdict "Machine: 192.0.2.1 · Domain/WG: — · OS: — · 0 share(s)" — a green
  "clean" line for an unreachable host; only the flyout dot is violet. One line, as
  `DiscoveryResult.plain_verdict` already does; B4's carrier depends on it.
- **7.2 design note:** the census counts `result.x = <constant>` in a broad handler as
  `silent_default`, so a (b) fix that only assigns a field stays counted. Every (b) handler also logs at
  debug with `exc_info` — the D6 outcome anyway.

**Found, not fixed (outside the swallows):**
- **SMB2 banner probe is malformed** — its NetBIOS header declares 144 bytes, the packet carries 104,
  so a conforming server waits for the rest and handler :329 swallows the 5 s timeout every time.
  Measured on 127.0.0.1: `os=''` in 8.0 s (3 s NetBIOS + 5 s banner). Tier 1 has likely never read an
  OS version. Latent with it: `anonymous_ok = True` on *any* negotiate response would raise the RED
  "Anonymous SMB session allowed" flag for every SMB host the day the length is fixed — fix together.
- Tier 1 marks every `net view` share `visible_anonymous`, but `net view` runs as the logged-in user:
  127.0.0.1 measured "2 non-hidden disk share(s) exposed: 1, Users".
- `_net_exe_enum` reports `net localgroup` — the scanner's own groups — as the target's (the `net user`
  class D5–D9 fixed). read.
- **Baseline → Take Snapshot always fails:** `_SnapshotWorker` emits `discover()`'s `DiscoveryResult`
  through `pyqtSignal(list)` → `TypeError` (measured), which lands on its error path.
- RULE-A2 in `modules/` text that reaches a label: `discover()` progress "…: skipped ({exc})",
  `_dns_leak_test` verdict "DNS leak test unavailable: {exc}". Census (a) scans UI sinks only.
- read, not reproduced: `rogue_device.scan()` guards the IPv6-RA flag with `ip != gateway_ip`, which
  cannot hold when the gateway is unknown or a VPN's — the real router could then read "ROGUE ROUTER
  DETECTED".

**Owner cut (2026-09-19).** S7 = the 75 (a) + B1 (both shapes) + B3 + B4 + B4a. B3 gets one new
field, `DiscoveryResult.methods_failed: List[str]`, named in fixed text by `plain_verdict`, with the
registry still `fresh` when devices were found. B1(ii): stop at the second SOA instead of reading to
EOF; a timeout before it keeps the records that arrived, sets `axfr_error="timeout"` and says the zone
is partial. **S7b = B2, B5, B6, B7: recorded only**, no code this sprint. The out-of-scope findings
above stay logged.

**S7 result (2026-09-19, against `fff5233`; committed as `70ee0d1`).**
- **Matrix rows first.** B1-UNREACH, B1-HOLD, B3, B4 and B4a (§7) all read **REPRODUCED against HEAD
  in a separate worktree**, then NOT REPRODUCED on the fixed tree. AXFR's port 53 is hard-coded, so
  B1-HOLD runs a fake server on 127.0.0.2:53 and B1-UNREACH aims at a closed 127.0.0.3. B3 uses scapy's
  own no-Npcap sockets (`_NotAvailableSocket` at L2, native `L3WinSocket` at L3 — measured: both raise
  on an unelevated shell exactly as a box without Npcap does). B4 fakes `net use` exiting 2 through
  `subprocess`, so no login is attempted.
- **B1** — `axfr_transfer()` now returns `(records, error)`, and `scan()` is its only production
  caller. A one-line wrapper that kept the old list shape was tried first, and the RULE-DBG5 orphan
  ratchet rejected it as test-only code. `_read_axfr_stream()` parses each length-prefixed message
  as it arrives and stops at the closing SOA. **One stop condition beyond the cut, needed to keep the fix
  honest:** it also stops at a response that carries no zone (RCODE ≠ 0, or no answers). Without it, a
  server that answers REFUSED *and holds the connection* would now time out and read "Could not reach
  … for AXFR", which trades one lie for another. The reason is chosen by exception type (`TimeoutError`
  → timeout, `ConnectionRefusedError` → refused, `gaierror` or `EHOSTUNREACH`/`ENETUNREACH` →
  unreachable, else failed), never `str(exc)`. Verdict order: unreachable with no records →
  "Could not reach <server> for AXFR — <why>. Check the address, then try again." at `UNKNOWN`;
  requested but no zone → "AXFR refused by <server>." (the AXFR button runs mDNS off, so before S7 it
  could never say this); partial → "N DNS record(s) via AXFR, but the transfer stopped early — <why> —
  so the zone is partial."; the mDNS count appears only when mDNS ran. The page gained
  `scan_not_testable(str)`, wired in `ui/tabs.py` to `_on_dns_zone_not_testable` → registry
  `not_testable`. That signal is plumbing for the agreed registry state, not a new data contract. A
  partial zone still emits `scan_complete` (its records are real).
- **B3** — a private `_MethodUnavailable`. `_arp_sweep` raises it when it failed before finding
  anything. `_tcp_probe_host` re-raises it, and `_tcp_sweep` raises only when **every** host's probe
  raised: some hosts failing is a partial sweep, logged and kept. `discover()` collects the names into
  `methods_failed` (progress "tcp-syn: could not run"). The verdict appends "— ARP sweep and TCP SYN
  could not run: they need Npcap and administrator rights." ("administrator (root) rights" off
  Windows), and the zero-device `not_testable` verdict gets the same note. `_on_discovery_result` is
  unchanged: still `fresh` with devices.
- **B4** — `_net_use_login()` is keyed on `CalledProcessError.returncode` (RULE-WIN23). Any failure
  sets `not_testable` with a fixed reason that carries the exit code. Nothing after it runs (every
  later `net` command would run as this PC's own account), and `enumerate_smb()` merges the Tier-1
  data as before. **Deviation from "log with exc_info":** `CalledProcessError` and `TimeoutExpired`
  print `cmd` in their message, and the `net use` argv carries the password. `_redact_argv()` blanks it
  before the record is written, and a test asserts the password is absent from the formatted record.
- **B4a** — `SMBEnumResult.plain_verdict` puts "⚠ Could not test <host> — <reason>" first, as
  `DiscoveryResult` does. **The verdict alone would not have stopped the GREEN:** `_on_smb_result`
  picks its colour from risk flags only, so it also gained one branch: not_testable → `VIOLET` (RED risk
  flags still win).
- **(a) 75** — `_log.debug("<what failed>", exc_info=True)` on a module `_log` in all eight files (five
  gained a logger). `pass  # reason` became `_log.debug(...)  # reason`; every other fallback is kept
  below the log call. No exception type narrowed, no import inside a function. Applied by a script
  that refused to run unless its 75 target lines matched the census worksheet exactly and the only
  leftovers were the five S7b handlers.
- **Tests:** `tests/test_error_surfacing_s7.py`, 30 tests. 25 were watched fail for the named reasons
  (the verdicts, `axfr_error`, `methods_failed`, `not_testable`, the missing debug records, the GREEN
  paint). 5 are guards that pass at HEAD by design: the old `axfr_transfer` return shape (since
  replaced by a partial-zone `(records, "timeout")` test), a partial zone stays `scan_complete`, a SYN failure on some hosts only is not "failed", Tier-1 data is kept, a
  successful login still enumerates. The ratchet was lowered first and watched RED (299 vs 224).

**Found, not fixed (S7):**
- **The DNS leak test has never worked.** `_dns_leak_test` calls `_json.loads`, and `_json` is
  undefined (ruff F821; the gate selects only F401/F811/F841). Step 3 raises `NameError` on every
  run, and the outer handler turns it into "DNS leak test unavailable: name '_json' is not defined"
  (the RULE-A2 finding above, same function). Present at `fff5233`.
- `discover()`'s ARP-cache read is not filtered by the CIDR: B3's run on `127.0.0.0/30` "found 18
  devices", which is the whole LAN cache.
- The DNS Zone status label sits in the toolbar row without word wrap. S5's error text (~130 chars)
  and the new verdicts (~113) stay inside the 140-char budget, but a long server name lengthens the
  verdict. Not measured natively.

- ✅ **7.1** Census emits a per-file triage worksheet (`--worksheet [PATH ...]`, 8 RED-first tests in
  `test_error_surfacing_ratchet.py`): each silent broad handler classified
  **(a)** expected → debug log with `exc_info` · **(b)** degrades a result → result carries
  degraded/partial/not_testable · **(c)** disables a feature → app-health condition.
- ✅ **7.2** Apply to `utils_net.py`, `rogue_device.py`, `dns_zone_scanner.py`,
  `network_diagnostics.py`, `wifi_scanner.py`, `name_resolver.py`, `combined_discovery.py`,
  `smb_enumerator.py` — RED-first test for every (b)/(c). 75 (a) + B1/B3/B4/B4a, above.
- ✅ **7.3** Lower ratchet (b) for `modules`: **304 → 224**. The five S7b handlers remain.
- ✅ **7.4** Stabilization — see the §8 row.
- **S7b** *(recorded, no code)* — B2 (mDNS send failure reads as "0 service(s)"; needs a second new
  field, `mdns_error`), B5 (a failed IPv6 neighbour read silently includes a rogue-RA check that did
  not run), B6 (traceroute that cannot run reads as all-silent hops), B7 (a guessed
  `192.168.1.0/24` sweep, not flagged, forced to /24). Each needs its own contract decision first.

### S8 — Swallowed failures II: UI refresh paths and grading inputs ✅ 2026-09-20
- **8.1** Same triage for `scan_wiring.py`, `scan_enrichment.py`, `dashboard.py`,
  `inventory_page.py`, `nav/builder.py`, `home_data_mixin.py`, `network_map_page.py`,
  `tabs_logger.py` — a swallowed refresh is a stale page with no indication → mark stale.
- **8.2** `health_score.py`, `digest_builder.py` — the grade/digest must name missing inputs.
- **8.3** Lower ratchet (b) for `ui`; stabilization.

**S8 triage (2026-09-20).** `tools/check_error_surfacing.py --worksheet` over the ten files:
**173 handlers** — digest_builder 7, health_score 9, dashboard 19, nav/builder 17,
home_data_mixin 15, inventory_page 19, network_map_page 5, scan_enrichment 25, scan_wiring 46,
tabs_logger 11. The great majority are genuine **(a)**: enrichment overlays, cache writes,
audit-trail rows, QSettings/JSON reads — best-effort by design, and `scan_enrichment.py`'s 25
are (a) to a one. Owner cut: **B8–B14**, key-only for B8; `persist_alert` and the ARCH RULE 2
gap recorded as S8b.

**S8 result (2026-09-20, against `70ee0d1`).**
- **Matrix rows first.** B8, B9, B10, B11, B12-ROW, B12-UNDO, B13-ANN and B14 (§7) each read
  **REPRODUCED against HEAD in a separate worktree**, then NOT REPRODUCED on the fixed tree —
  **33/33**. The three ack/annotation rows were re-anchored to the *toast* after their first
  run, because `captured_records()` filters at production level and would have read a
  `log.debug` companion as silence; the re-anchored predicates were then re-verified against
  HEAD, so none of them is a row that can only ever pass.
- **B8** — `_availability_score` read `row["24h"]`; `query_uptime_table` keys each window by
  `str(hours)`, so it emits `"24.0"`. The read never matched, `uptimes` was always empty, and
  the function returned `None` **every time it has ever run**. `compute()` then substituted its
  optimistic `80.0` default for the heaviest input in the composite (weight 0.45), and
  `_generate_copy`'s red-state branch — guarded by `avail_score is not None` — was unreachable
  code, so "Connectivity problems detected — some devices are unreachable" could never be
  shown. Measured on a real store where one device was DOWN for half the window: **score 91,
  green, "healthy for 7 days."** Both sides now derive from one `_AVAIL_WINDOW_HOURS`
  constant, so they cannot drift apart again. **Owner cut: key only.** Fixing it moves that
  case to 77 — still green, because 0.45 × 50 + 0.35 × 100 + 0.20 × 100 = 77.5 and the green
  threshold is 75. Re-tuning the weights is a deliberate behaviour change to the ambient score
  on Home and is **not** in this sprint; recorded here as the open question.
- **B9** — `_grade_kpi` called `store.get_grade_result()`. That method has never existed on
  MetricStore (`query_last_grade()` is the accessor), so the tile was permanently "—" with a
  grade sitting in the table. `score` is now read as `row.get("score") or 0`: a NULL score
  would otherwise raise on the `>= 80` comparison and land in the same swallow.
- **B10** — the new-device tile and table filtered `event_type in ("join", "new")`, but
  `record_device_event` **rejects** anything outside `JOINED / LEFT / UP / DOWN / DEGRADED /
  RECOVERED` with a `ValueError`, so those two strings can never appear in the table. The
  digest reported 0 new devices every week. Both now pass `event_types=["JOINED"]` to the
  store — the idiom already used by `home_data_mixin`, `weekly_report` and `tabs_logger` —
  which removes the duplicated vocabulary rather than correcting it in place.
- **B11** — `r.get("168.0", r.get("24.0", 100.0))`. A window key is *present and None* for a
  device with no samples in it, and `.get(key, default)` falls back only on a **missing** key,
  so the None passed through and `None >= 99` raised — collapsing the entire table into
  "Uptime data unavailable." One device last seen 10 days ago was enough to erase every other
  device's uptime. A missing measurement now renders "—": reading it as 100 % would have been
  a fabrication, which is the same defect one layer down.
- **B12** — `_ack_alert_row` ran `setVisible(False)` + `deleteLater()` **outside** the guard,
  so a refused write cleared the row exactly like a successful one and the alert returned at
  the next 30 s refresh with no explanation. `_undo_ack_all` returned silently, which made the
  toast's own Undo affordance report a reversal it had not delivered. Both now keep the state
  and say so; `_ack_all_alerts` surfaces instead of leaving the card untouched and mute.
- **B13** — `_save_annotations` discarded the user's own label / location / owner / asset tag /
  notes on a failed write, with the drawer behaving as if they were stored. Same shape for the
  cleared type override (both call sites), the alert opt-in toggle and a renamed segment. One
  `_edit_not_saved()` helper covers all five and logs the exception at debug.
- **B14** — `sched_scan/next_ts` is advanced **before** `_start_scan()` is attempted, and the
  failure was swallowed, so a scheduled scan that could not start rolled silently forward to
  its next window. The advance is deliberate and stays (not advancing would retry on every
  timer tick), which is precisely why the failure needs a surface of its own: a new
  `SCHEDULED_SCAN` ConditionSpec, mirroring the existing `SCHEDULED_SPEED_TEST` one-for-one,
  raised on failure and resolved on the next success. `detail` is `explain(exc).why`, never
  `str(exc)` — `Condition.detail` is rendered in the app-health strip tooltip (RULE-A2).
- **Why none of this was caught by the suite.** `tests/test_health_score.py` stated in its
  fixture docstring *"Uptime rows use `{"24h": pct}` format matching query_uptime_table
  output"* — it **encoded the defect as the contract** and mocked a store returning the key
  the real one never emits, so every availability assertion passed against a fiction. On the
  digest side `MagicMock` auto-creates `get_grade_result`, so B9's AttributeError could not
  occur under test, and `test_build_digest_html_no_crash_with_minimal_store` wraps its
  assertion in `pytest.skip` on `TypeError` — which is exactly B11's exception. The fixture is
  corrected (12 occurrences) and `test_b8_availability_key_matches_what_the_store_emits`
  asserts the agreement against a **real** `MetricStore`, which is the assertion whose absence
  let this live.
- **Found, not fixed (S8b).** (1) Seven `persist_alert(...)` swallows — scan_wiring ×3,
  dashboard ×3, scan_enrichment ×1 — where an alert the user saw live never enters history, so
  the Alerts page, the digest, `_alert_score` and `_stable_hours` all disagree with it.
  Surfacing a repeated DB write failure properly needs a **new** app-health condition, so it
  was recorded rather than assumed. (2) `home_data_mixin.py::_check_logger_milestones` runs
  raw SQL through `self._store._conn.execute(...)` from the UI layer — an ARCH RULE 2
  violation `tests/test_metric_store_encapsulation.py` cannot see, because it greps only
  `_execute_write(` / `_execute_read(`. Tightening that guard will likely surface other sites.

### S9 — Consistency and polish ✅ 2026-09-20
Sized against `e0e999a` before any code, from a fresh census rather than S0's counts. Owner cut:
**9.1 + 9.2 + 9.4 (failure text only) + 10.1a**; **9.5 cut entirely**, 9.3 cut (coupled to 10.2),
REST `GET /health` cut, 10.1b recorded rather than coded.

- ✅ **9.1** RULE-A3 literal review (F8). Of the 13 literals F8 counted, **11 are not severity
  labels and were deliberately left alone** — recorded here so the next reader does not reopen
  them: `"Error"` ×6 are scan-registry / health *state* words (`monitor_state`,
  `security_overview_page`, `service_page`, `tabs_recon`, `hub_card`, `scan_status_md`), and
  `"Medium"` ×4 / `"Low"` ×1 in `os_fingerprint` are OS-guess **confidence**, not severity. Two
  were real:
  - `monitor_overview_page.set_storm_status` wrote the internal risk vocabulary verbatim —
    `Storm` / `Warn` / `Clean` — while `scan_enrichment` rendered `risk_to_label()` for the same
    measurement. Headline → plain English (`Flooding` / `Elevated` / `Normal`), subtitle →
    `risk_to_label()`, so the two surfaces now agree. The catch-all branch translates `"CLEAN"`
    explicitly, because `risk_to_label()` returns an unrecognised input **unchanged** — which is
    the leak it exists to prevent.
  - Found while fixing that: the Broadcast Storm page's own **"Storm level" stat** showed the raw
    level at 18 px bold, directly above a status line already reading "Storm level: Needs
    attention". One page, one measurement, two vocabularies. Same one-line fix.
- ✅ **9.1b** status-line glyphs. 83 `ui/` sites write `✓`/`⚠`/`✗`/`○` as literals instead of the
  `STATUS_ICON_*` constants — but the vocabulary they spell is already consistent, so migrating
  all 83 is an 83-site diff with no user-visible change and was **not** done. The one real
  inconsistency sat inside a single method: `credential_dialog._on_failure` wrote `✗` when
  `plugin_error_text()` recognised the plugin's text and `⚠` (via `show_worker_error`) when it did
  not — so the same failure of the same button looked harder whenever NetSentinel could explain
  it. `tests/test_error_surfacing_s6b.py` **held that inconsistency as the contract**: its
  parametrize pinned the `✗` case as a literal. Both cases now derive the glyph from
  `STATUS_ICON_WARN`.
- ✅ **9.2** `QMessageBox.information` → toast where nothing is decided. **12 of the 17 sites stay
  modal**: the 9 "How to Fix" dialogs plus "Finding Details", "Contributing findings" and
  "Protocol Info" are RULE-A1 detail views, not confirmations. Owner decision: the two
  "Diagnostic report saved" modals (`feedback_dialog`, `unclean_exit_strip`) also stay — they
  carry `REDACTION_NOTE`, which a user should read before sharing the file, and a toast
  auto-dismisses. Converted:
  - `reports_page._export_pdf` — the leftover from S6.0. Its own neighbour `_copy_summary`, and
    every other export in the app, already toasted.
  - `log_source_panel._export_visible` — **the ladder was inverted here**: "No rows match the
    current filter." was a modal while a successful write said *nothing at all*. The non-event is
    now an info toast and the write a success toast, in the `else:` of the guarded block
    (RULE-SURF2; RULE-SURF1's inverse corollary).
  - `network_map_page._on_export` — the refusal is a warning toast naming the next step; the same
    file's two success paths already toasted.
- ✅ **9.4** capability-gating wording. **The pass S0.3 anticipated was already done by S5**:
  `_PACKET_CAPTURE` is one shared string behind 7 entries, and the five `modules/` sites that
  interpolate `{exc}` into their own capability text reach only the *tooltip*, because every one
  of their UI sinks routes through `show_worker_error` — traced site by site, not assumed. One
  entry was wrong: `WE.APP_TRAFFIC` read "Reading connections or interface counters failed. /
  Start monitoring again." while `AppTrafficClassifier.run()` has exactly **two** error paths and
  both are capability gaps (Scapy missing; the capture refusing without Npcap and administrator).
  It named neither, and told a user with no driver to retry forever. Now `_PACKET_CAPTURE` +
  "Check both, then start it again.", matching its three sibling monitors and the 140-char budget.
- ⛔ **9.3** cut. The cheapest form is an `Info` condition on the S4 strip, which is flag-gated —
  so with today's shipped default the hint would not exist at all. Revisit after 10.2.
- ⛔ **9.5** cut. 76 registered rail items; a genuine walk produces prose, not behaviour, and
  S1–S8 already walked every page that has an error path. The machine-checked equivalent is
  `python tools/check_error_surfacing.py --worksheet`, which regenerates on demand and cannot rot.

### S10 — Headless surfaces and closure
- ✅ **10.1a** *(2026-09-20)* The four headless sinks — and the blind spot that hid them.
  `svc.py:251` (Windows Event Log), `svc.py:289` (`svc status`), `cli.py:92` (`_resolve_output`)
  and `app.py:386` (`--report`) each interpolated the caught exception straight into the only
  thing their user sees, **and the (a) ratchet could not see any of them**: its sink set is Qt
  widget methods, and neither `servicemanager.LogErrorMsg` nor `print(file=sys.stderr)` is one.
  Each now reads what/why/next through `modules.error_text.explain()`, with the raw text and its
  traceback in `netsentinel_app.log`:
  - the Event Log entry goes through `svc._headless_error()` and names the log to read;
  - `svc status` gets a **domain** next step ("Install it with: netsentinel-svc install"),
    because `explain()`'s generic "try again" cannot help with a service never installed;
  - `app --report` keeps its full traceback — that is the point of a diagnostic surface — and
    only gains a first line a person can act on.

  Census widened with `_HEADLESS_SINK_ATTRS` / `_HEADLESS_SINK_NAMES`, scoped to the entry points
  exactly as `_UI_ONLY_SINK_ATTRS` is scoped to `ui/` (owner decision S6.4). **It immediately
  counted its own fix** — the same trap S6b hit with `worker_error_text` — until `_headless_error`
  was registered in `_TRANSLATORS`. (a) is back to **0** under the wider net; (b) is unchanged at
  651, so no ratchet moved.
- ⏸ **10.1b** recorded, not coded. `svc.py` builds no `AppHealth`, and **no condition is reachable
  from either headless entry point**: every `report_failure` call site is in `app.py`'s GUI
  wiring, `modules/notification_router.py` or `workers/rest_api_worker.py`. "Routing conditions
  through svc/cli" as written would mean *adding producers* — new capability, not surfacing. If
  wanted later: an `AppHealth` in `svc.py` plus a `LogWarningMsg` subscriber, so a week of failing
  `NetworkLogger` DNS/ARP probes stops being invisible between "service started" and "service
  stopped".
- ⛔ **10.1c** REST `GET /health` cut — a new endpoint, and the feature set is closed.
- ✅ **10.2** *(2026-09-20)* `experimental/app_health_v1` retired; the surface ships on.
  RULE-EXP1's deletion gate ("verified in the live app") was met by S4.5 — where the strip
  found `scheduler:reports` failing at every launch on its own — so this removed the flag
  rather than defaulting it True: one path ships, and it is the one the release's chaos run
  exercises. Gone: `FLAG_KEY` / `app_health_ui_enabled`, `_wire_monitor_error_surface`'s
  `note` parameter *and its one-time status-bar note*, `_wire_app_health`'s `surface`, the
  `if _app_health_ui:` around `_seed_listener_pages`, the strip gate in `home_page.py`, and
  `_pill_failures`' `None` return (now always a `dict`; every consumer already normalised with
  `failing or {}`).

  Two things the located diff above did not name, both found by running the tests rather than
  reading:
  - **A sixth gate, in `ui/nav/builder.py:899`.** `_nav_set_scan_state` repainted a failing
    Home pill only `if ... _app_health_bridge is not None` — the flag's proxy, one indirection
    away from anything a grep for `app_health_ui_enabled` or the key would find. Caught by
    `test_a_registry_error_repaints_the_pills_at_once`, not by the new retirement test, whose
    net is the flag's own names.
  - **`docs/spikes/error-surfacing-matrix.py`'s F2-G6 row had to change in the same commit.**
    It branched on `if "note" in signature(_wire_monitor_error_surface)`, so deleting `note`
    would have dropped it into the legacy branch, which asserts `len(notes) == 1` — a note the
    code can no longer write. It would have reported REPRODUCED for the opposite of the real
    reason, corrupting exactly the 10.3 re-run it feeds. Now keyed on the parameter's *absence*.

  Guarded by `test_the_experimental_flag_is_fully_retired` (the names are gone from
  `ui/`+`app.py`, module docstrings excluded — a docstring cannot read a setting) and
  `test_main_wires_the_whole_surface_with_no_gate` (no `surface=`/`note=` kwarg, and none of
  the three wiring calls sits inside an `if`). Matrix re-run on the final tree: **41 rows,
  0 REPRODUCED, 0 inconclusive.**
- ⏸ **10.3** full chaos run (RULE-CHAOS1 — the owner runs it, the agent never launches it) plus a
  final matrix re-run; closes this document.

---

## 7. Live verification matrix (S0.2)

`PYTHONIOENCODING=utf-8 python docs/spikes/error-surfacing-matrix.py` — 2026-09-15, 379bf5f.
No Dashboard is constructed (registry-backed settings cannot be sandboxed); `LOCALAPPDATA` is
redirected; network faults are loopback-only; the failing keyring backend is in-process.

| Row | Fault injected | Observed | Verdict | Flips in |
|---|---|---|---|---|
| F4 | `log.warning` with the GUI's libraries loaded | root handlers `[]`; stderr receives `'Availability monitor error: boom\n'`; debug record dropped | REPRODUCED | S2 |
| F1a-ARP | `_wire_arp_watch` + real `ProactiveProbeWorker`, probe raises "Npcap is not installed" | only UI effect: `_set_flyout_dot('ARP Spoof Watch', '')` | REPRODUCED | S1 |
| F1a-DHCP | same, `_wire_dhcp_watch` | only UI effect: `_set_flyout_dot('DHCP Rogue Monitor', '')` | REPRODUCED | S1 |
| F1b | introspect `FreshnessStrip.update_freshness`; render `arp=True` | parameters `(arp, dhcp, storm, logger)`; renders `'● ARP'` | REPRODUCED | S4 |
| F1c-SVC | real `ServiceDiagnosticsPage._on_error("DNS resolution failed…")` | emits `scan_complete`; `app.py` maps it to `"fresh"` | REPRODUCED | S1 |
| F1c-SPD | real `SpeedTestPage._on_test_error(…)` while hidden | no status, no history row | REPRODUCED | S1 |
| F1d | real `DecoMeshClient.get_all_clients`, 1 of 2 nodes raises `MeshApiError` | plain `list` of 1, no partial marker; one warning record | REPRODUCED | S3 |
| F2-SPD | `_wire_speedtest_scheduling` + real worker, probe raises | UI effects: none | REPRODUCED | S4 |
| F2-G6 | `_wire_monitor_error_surface`, 2 errors, then one progress update through the real `_set_status` | 1 note ("see log for details"); bar then shows `'Scanning 12/254 hosts…'` | REPRODUCED | S4 |
| F2-REST | real `RestApiWorker` bound to an exclusively occupied loopback port (dev-server path — waitress not installed here) | **no error signal**; `SystemExit` escaped the `rest-api-server` thread | REPRODUCED | S1 (signal), S4 (surface) |
| F2-HOOK | real `NotificationRouter._deliver` to a closed loopback port | delivery log `FAILED`; zero records reach any log handler | REPRODUCED | S2 (log), S4 (surface) |
| F2-KEY | `keyring.backends.fail.Keyring`; real `mqtt_page._set_secret` | no exception, `_get_secret() == ''`, zero records | REPRODUCED | S1 |
| F6-WARN | real `ToastManager.show(…, "warning")` | accent border, no auto-dismiss timer | REPRODUCED | S1 |
| F6-EVICT | error toast, then 3 success toasts; one toast before `attach()` | error toast evicted; pre-attach toast dropped | REPRODUCED | S1 |

**S6 (2026-09-17): rows F6-EXPORT and F6-SUCCESS added** — the real `CvePage._export_csv` into a
folder that does not exist, and a real successful `ReportsPage._copy_summary`. Both REPRODUCED with
the S6 product files stashed (the half-stashed tree left 3 other rows inconclusive — pages that
already import the new helpers — so that run is only evidence for the two new rows); after S6
**17/17 NOT REPRODUCED**.

**S6b (2026-09-17): rows F6b-DB and F6b-UPD added** — the real Home Automation save through a real
`MetricStore` while a second connection holds a real `BEGIN EXCLUSIVE` on the same file, and the real
Help-tab update check against a request that takes 1.5 s. Both REPRODUCED against **HEAD in a separate
git worktree** (`⚠  Save failed: database is locked`; the click returned after 1.53 s) — a worktree
rather than a partial stash, so the baseline cannot be confused by half-stashed files and the working
tree is never at risk. After S6b **19/19 NOT REPRODUCED**.

**S6c (2026-09-18): row IOT-THREAD added** — the real `_run_iot_learn` → real `learn()` with scapy's own
`_NotAvailableSocket` as `conf.L2listen` (the no-Npcap state) and a temp baseline path; a spy counts
label writes made off the GUI thread. REPRODUCED against a HEAD worktree (`off-thread writes=1;
label='Learning for 30 s — keep devices active…'`); after S6c NOT REPRODUCED (`off-thread writes=0`,
label = the `IOT_LEARN_RUN` text). **Harness trap, same class as F2-HOOK:** the first version waited for
the label to *change*, and the progress line ("Learning baselines for…") lands before the failure does —
so it read a still-learning label as fixed. The row now waits for a final state (the label no longer
starts with "Learning"). **20/20 NOT REPRODUCED.**

**S7 (2026-09-19): rows B1-UNREACH, B1-HOLD, B3, B4 and B4a added**, all REPRODUCED against a
`fff5233` worktree before any fix:
- **B1-UNREACH:** the real AXFR button against 127.0.0.3 emitted `scan_complete` and read "No DNS zone
  data found. Try providing a DNS server for AXFR."
- **B1-HOLD:** a fake server on 127.0.0.2:53 sent SOA/A/SOA and held the connection. Records: 0.
- **B3:** the real `discover()` with scapy's no-Npcap sockets reported `failed=None` and "Found 18
  device(s) … using: arp-cache, icmp-ping, mdns".
- **B4:** a failed `net use` gave `tier=2`, `not_testable=False`, shares `['Public']` and groups
  `['Administrators', 'Users']`, all read as the scanner's own account.
- **B4a:** a not_testable Tier-1 result was painted `green=True` with the verdict "Machine: 127.0.0.2
  · … · 0 share(s)".

After S7, **25/25 NOT REPRODUCED**:
- **B1-UNREACH:** `scan_not_testable`; "Could not reach 127.0.0.3 for AXFR — it refused the
  connection on TCP port 53. Check the address, then try again."
- **B1-HOLD:** records=2.
- **B3:** `failed=['arp-sweep', 'tcp-syn']`.
- **B4:** `not_testable=True`, no shares, no groups.
- **B4a:** `green=False`, "⚠ Could not test 127.0.0.2 — …".

Every row waits for a final state (the page's result signal), not the first progress line. B3 reports
INCONCLUSIVE on an elevated shell, where `L3WinSocket` works and there is no fault to inject. The runs
on the fixed tree exited `0xC0000409` (PowerShell; Git Bash shows it as 127) after printing
`MATRIX COMPLETE`, and the HEAD run exited 0. This is the documented teardown race: read the last
line.

**S9/S10 (2026-09-20): rows S9-STORM, S9-GLYPH, S9-PDF, S9-LOGEXP, S9-MAPEXP, S9-APPTRAF,
S10-EVTLOG and S10-STDERR added**, all REPRODUCED against an `e0e999a` worktree before any fix,
then **41/41 NOT REPRODUCED**. `_modals()` joins `_toasts()` as a harness fixture, because S9.2 is
about *which* of the two channels a site chose — a row watching only one cannot tell a converted
site from a silent one. S10-EVTLOG drives the real `SvcDoRun` with `PROGRAMDATA` redirected and a
recording stand-in for `servicemanager`; S10-STDERR drives `cli._resolve_output`,
`svc._cmd_status` and `app._headless` and reads their real stderr. Before:

- **S9-STORM:** `{'STORM': ('Storm', …), 'WARNING': ('Warn', …), 'CLEAN': ('Clean', …)}`.
- **S9-GLYPH:** `['✗  Authentication failed — bad password', '⚠ The connection test failed. …']`.
- **S9-PDF / S9-MAPEXP:** `modals=[('information', …)]; toasts=[]`.
- **S9-LOGEXP:** nothing to export → a modal; a real write → `toasts=[]`.
- **S9-APPTRAF:** `'⚠ App traffic monitoring stopped. Reading connections or interface counters
  failed. Start monitoring again.'` — names neither Npcap nor administrator.
- **S10-EVTLOG:** `'NetSentinel Logger encountered an error: [Errno 13] Access is denied'`.
- **S10-STDERR:** the CLI line carried a raw **sv-SE** `[WinError 183] Det går inte att skapa en
  fil som redan finns` — exactly the localization RULE-WIN23 is about, reaching a user verbatim.

**S10-STDERR's predicate had to go back to HEAD.** Its first version matched the raw marker
`"sub"`, which is part of the *path* the fixed message still legitimately names, and compared
against `explain(NotADirectoryError(…))` when Windows actually raises `FileExistsError(WinError
183)` — so it read REPRODUCED on the fixed tree for two reasons that had nothing to do with the
defect. It now derives the expected classification by attempting the `mkdir` itself, and was
re-verified REPRODUCED against the `e0e999a` worktree before being trusted. Same rule the S8 ack
rows established: a predicate that changed after seeing the fix is not evidence until it has been
re-proved against HEAD.

**S8 (2026-09-20): rows B8, B9, B10, B11, B12-ROW, B12-UNDO, B13-ANN and B14 added**, all
REPRODUCED against a `70ee0d1` worktree before any fix, then **33/33 NOT REPRODUCED**. The four
grading rows drive a real `MetricStore` (`_s8_store()`) holding one device DOWN for half the 24 h
window, one device last seen 10 days ago, one recorded grade and one JOINED event — every defect
here is a disagreement between what the store emits and what the reader asks for, which a mock
cannot expose. Before:

- **B8:** `availability=None` against `table=[{'ip': …, '24.0': 50.0}]`; `score=91 state='green'`,
  headline "Everything looks good — your network has been healthy for 7 days".
- **B9:** `tile` showed "—" with `query_last_grade()` returning grade B.
- **B10:** `events=['JOINED']`, `kpi` showed 0, table "No new devices joined this week."
- **B11:** table was "Uptime data unavailable." for **both** devices, because of the one.
- **B12-ROW:** `hidden=True; deleted=True; toasts=[]` — the refused write cleared the row silently.
- **B12-UNDO / B13-ANN:** `toasts=[]`.
- **B14:** `next_ts_advanced=True; records=[]`.

After S8: `availability=50.0` (score 77, see §6 S8 on why that is still green); the Grade tile
reads B; the new-device tile reads 1; the uptime table renders both devices with "—" for the one
with no 7-day samples; all three ack/annotation rows carry a `warning` toast; B14 logs and raises
`SCHEDULED_SCAN`.

**Read the three ack/annotation rows' history before trusting them.** They first probed
`captured_records()`, which filters at production level — so the `log.debug` companion to each
new toast was dropped and they read as REPRODUCED *after* the fix. The predicates were re-anchored
to the toast (`_toasts()`), which is the surface the rows are actually about, and then re-verified
against the `70ee0d1` worktree so none of them is a row that can only ever pass. A row that
changes its predicate after seeing the fix has to go back to HEAD.

**S5 (2026-09-17): row F5 added** — the real SNMP trap and DNS zone error slots handed an sv-SE
`WinError 10048` string. REPRODUCED on 352f907 (both labels showed it), NOT REPRODUCED after S5.
F2-HOOK harness race fixed in the same sprint: it stopped waiting at the third `FAILED` status, but
`_mark_failed` raises the condition and logs *after* releasing its lock, so the row could read the
strip first (one spurious REPRODUCED seen); it now also waits for the record and the condition —
15/15 NOT REPRODUCED in a loop.

**S4 re-run (2026-09-17): 14/14 NOT REPRODUCED.** F1b, F2-SPD and F2-G6 were re-anchored to the
S4 surface (a strip row with its CTA that clears on the next success), and F2-REST / F2-HOOK now also
require that row. Each keeps a pre-S4 branch, so against an older tree the rows should still read
REPRODUCED — not re-verified against a stashed baseline this sprint.

Not exercised live: the waitress bind-failure path shipped builds take (waitress is not installed
in this dev environment — `requirements.txt` pins it); Network Logger, Devices, WiFi Networks,
DNS Zone Map and CVE Tracker registry paths (read only).

---

## 8. Sprint log

| Sprint | Status | Date | Notes |
|---|---|---|---|
| S0 | ✅ done | 2026-09-15 | Tool + ratchets (43 tests), matrix 14/14, S0.3 areas, D1–D6, RULE-SURF1/2. One production line changed: the first gate run was red on a failure already at HEAD (`test_no_bare_pass` → `modules/crash_net.py:108`, uncommented `except OSError: pass` from `5dba4bb`); fixed with a comment only, owner-approved. RULE-SD1: suite `[PASS]` 7,769 passed / 5 skipped · `debug_launch` OK · no new pages · no UI feature (ratchet tests are the deliverable) · no user-facing change to verify live — matrix ran the real code paths offscreen |
| S1.2 | ✅ done | 2026-09-16 | Registry error paths (F1c). Ratchet **(d) 7 → 0**: every scan label can now reach `"error"`. New signals `ServiceDiagnosticsPage.scan_failed` / `SpeedTestPage.test_failed` / `DnsZonePage.scan_failed` / `CvePage.refresh_failed`; Network Logger, Devices and WiFi Networks error slots now write the registry. Matrix rows **F1c-SVC and F1c-SPD flipped to NOT REPRODUCED** (verified against a stashed pre-fix baseline on the same script). Two extras found while wiring: Service Diagnostics' `scan_complete` had **two** subscribers (`ui/tabs.py` + `app.py`) and the later `app.py` one overwrote the verdict with `None` — all three transitions now live in `ui/tabs.py`; and `SpeedTestPage._on_test_error`'s `isVisible()` early return was dropped, so a scheduled failure records a history row off-screen. RED-first: `tests/test_error_surfacing_s1.py`, 6 tests, watched fail (6F, right reasons) then pass. RULE-SD1: suite `[PASS]` 7,774 passed / 6 skipped · `debug_launch` OK · nav reachability 10 passed · no new pages |
| S1.1/1.3/1.4/1.5/1.6 | ✅ done | 2026-09-16 | **Ratchet (c) 3 → 0** alongside (d). 1.1 ARP/DHCP: error state + **dot-ownership transfer** — `_push_monitor_pills` no longer writes those two dots (it repainted them `GREEN if isRunning()`, and a `ProactiveProbeWorker` keeps running after a probe raises, so it stomped the error); ARP page now mirrors DHCP's existing registry wiring. Home pills untouched (F1b). 1.3 toasts: real `warning` kind (AMBER/⚠/6 s), sticky kinds never evicted, pre-`attach()` toasts queued (bounded at 8). 1.4 keyring: `_set_secret` returns bool + `_secret_is_readable()`; MQTT save shows a warning toast and the placeholder distinguishes "unreadable" from "unset". Other four sites still deferred to S6. 1.5 REST: `_serve` extracted to `_serve_once()` and catches `SystemExit` — **confirmed live**, F2-REST's observed line now carries a real error message (the row stays REPRODUCED only because `app.py`'s handler is still `print()`, which is S3/S4). 1.6: matrix script's REST worker stopped + pages released, verdict counting fixed (it compared strings to bools and reported 0/0/0), `MATRIX COMPLETE` completion line added. **Matrix 7/14 NOT REPRODUCED** (was 0/14 at S0): F1a-ARP, F1a-DHCP, F1c-SVC, F1c-SPD, F2-KEY, F6-WARN, F6-EVICT. RULE-SD1: suite `[PASS]` 7,788 passed / 6 skipped · `debug_launch` OK · nav 10 passed · ruff/import-lint/mypy (native + linux) clean |
| — | ⚠️ note | 2026-09-16 | **`tools/check_import_lint.py` only scans git-tracked files** (`git ls-files`). S0's four new files were invisible to that gate until they were committed; the first tracked run then found a real `py/import-and-import-from` violation in `error-surfacing-matrix.py`. A gate run on an untracked file proves nothing — commit first, or run the checker on the path directly |
| — | 🐞 open | 2026-09-16 | Matrix script still exits `0xC0000409` despite stopping the REST worker and releasing both pages. **Not an app fault** — `netsentinel_crash.log` is byte-identical across a run, so faulthandler never saw it; a live Qt thread loses a race with `os._exit(0)`. All rows print first. The `MATRIX COMPLETE` line is the completion signal to read instead (RULE-GATE1); documented in the script's own docstring. Not pursued further |
| S2 | ✅ done (2.4 deferred) | 2026-09-17 | 2.1 `modules/app_logging.py` + `modules/version.py` (D4 log at all three entry points, after `rotate_logs()`), 2.2 router delivery warnings rate-limited per channel, 2.3 `RepeatLimiter`. Matrix **F4 NOT REPRODUCED**. 2.4 deferred by owner (needs a source-run live hour; the Store build predates the log). RULE-SD1: suite `[PASS]` 7,824 passed / 6 skipped · `debug_launch` OK · no new pages · ruff/mypy/pip-audit clean. Committed separately from S3 (patch applied to the index) |
| S3 | ✅ done | 2026-09-17 | App-health model, no UI change (§6 S3). Matrix **11/14 NOT REPRODUCED** (was 7): F1d flipped; F2-REST re-anchored from S1's `print()` string match to "condition raised" (observed text says it is drawn in S4); F2-HOOK had flipped in S2. Still REPRODUCED by design: F1b, F2-SPD, F2-G6 (S4 surface rows). Ratchets unchanged — S3 does not target (a)/(b). Findings logged in §3: startup failures dropped by post-`Dashboard()` wiring (probe-confirmed); syslog port-0 fallback. RULE-SD1: suite `[PASS]` 7,904 passed / 6 skipped · `debug_launch` OK (it does not run `main()`, so the new `main()` wiring was checked statically — ruff F821 clean, every new name bound before use — plus the AST connect-before-start test) · no new pages · ruff, mypy native + linux, import lint **with untracked files** clean · smoke test OK. Not verified live: no UI change, and a source launch is blocked while the Store build holds the single-instance mutex. The first full run was red twice: `test_app_logging` rotation-order test matched the first *text* `app_logging`, which S3's smoke-list entry moved above `rotate_logs` (test re-anchored on the import; real order verified in all three entry points), and `test_threat_intel_worker::test_feed_refresh_lifecycle` timed out on a live feed download (3/3 green in isolation, ~0.6 s; untouched by S2/S3 — network-dependent, watch for recurrence) |
| S4 | ✅ done (4.5 open) | 2026-09-17 | App-health surface behind `experimental/app_health_v1`, all 8 owner decisions recommended-as-planned (§6 S4). Matrix **14/14 NOT REPRODUCED** (was 11): F1b, F2-SPD, F2-G6 flipped; F2-REST/F2-HOOK tightened to need the drawn row. `--audit` all PASS incl. new `APP_HEALTH_CTA_RESOLVE`. RED-first for every modules/ change and each 4.4c/4.4e wiring (watched fail: audit 4, router 3, REST/speed-test 5, syslog port 6, Deco 2); RULE-T7: `tests/test_app_health_surface.py` (18) + `test_app_health_bridge.py` (6). RULE-SD1: suite `[PASS]` 7,956 passed / 5 skipped (run twice — the second on the final tree, after two review fixes) · `debug_launch` `window.show() called OK` (it idles in the event loop until closed — a `timeout` kill after that line is expected; it runs flag-OFF and never runs `main()`, so the flag-on path is covered by tests + matrix only) · nav reachability 10 passed · smoke OK · ruff F401/F811/F841, import lint with the new files `git add -N`'d, mypy native + linux clean. **Not verified live** — 4.5 needs a source run with the flag set (recipe in §6). Found while building: (1) Home has **three** monitor pill sets — only the freshness strip is tri-state; the monitoring card `_pill_*` and `_rec_pill_*` still paint a failing monitor green (candidate for the 4.5 look / S8); (2) the notification "Send test" buttons bypass the router, so they can neither raise nor resolve `notify:` conditions; (3) `modules/snmp_trap_receiver.py`'s docstring says it falls back to a random port — the code raises after 162 + fallback; (4) the syslog/SNMP pages dropped "Listening on UDP :N" at every launch (fixed on the flag-on path by 4.4b); (5) matrix harness: pumping F1c-SPD's deferred SpeedTestPage deletion inside `redirect_stderr(StringIO)` invalidated stdout (WinError 6) and silently ate every later row — pump moved outside the redirect, mechanism not isolated. Test-side trap: emitting `auto_speedtest_changed(True, …)` really starts the worker, and a running QThread destroyed at teardown ends pytest with exit 127 and no summary line |
| S5 | ✅ done (5.5 open) | 2026-09-17 | Worker errors as what/why/next (§6 S5): fixed per-site text, raw as tooltip + Copy + app log — owner accepted all four recommendations (design C; 140-char budget, no layout change; SMB Stop folded in; Scheduled Scans log line converted). **Ratchet (a) 95 → 63.** Matrix **15/15 NOT REPRODUCED** (new row F5 REPRODUCED on 352f907 first). RED-first: `test_error_display.py` (10), `test_worker_error_catalogue.py` (5, incl. static resolution of every `WE.<NAME>` — a typo there raises only when the scan fails), `test_error_surfacing_s5.py` (12: five pages + SNMP, one real lambda via `ConnectionsPage._refresh`, SMB worker + page Stop). RULE-SD1: suite `[PASS]` 7,987 passed / 5 skipped on the final tree (the run took 70 min vs 9.5 min for the first run this session on near-identical code — machine load suspected, not investigated) · `debug_launch` `window.show() called OK` on a log newer than the launch · ruff, import lint, mypy native + linux, pip-audit clean · no new pages. **Not verified live** — 5.5 joins the S2.4/S4.5 source run. Found while building: (1) the first suite run was red 7× in `test_scan_error_state_wiring.py` — its `_FakeHost` used `MagicMock()` status labels, which cannot parent the helper's detail filter; replaced with real `QLabel`s (the file already used real `_table()` widgets), helper not loosened; (2) **F2-HOOK harness race** — see §7; (3) **deviation:** the syslog/SNMP status labels now wrap, to carry the strip's ~190-char condition text; (4) a first `debug_launch` check read a stale `netsentinel_debug.log` (mtime hours old) and passed falsely — the gate check must require a log newer than the launch |
| S6 | ✅ done (6.6 open) | 2026-09-17 | Sized before code (§6 S6: 63 = 44 except-as + 19 worker sinks) and split into S6 + S6b; owner accepted all four recommendations. 6.0 `show_toast` false failures (RULE-SURF1 corollary + `test_toast_call_sites.py`), 6.1 exports (9) with `explain()` opt-in and "Choose another location", 6.2 dialogs (11) + `NoPdfBackendError` + the Edge location probe, 6.3a worker sinks (19). **Ratchet (a) 63 → 26.** Matrix **17/17 NOT REPRODUCED** (F6-EXPORT, F6-SUCCESS new; REPRODUCED on the stashed baseline first). RED-first: `test_toast_call_sites.py` (2) + four 6.0 regressions, `test_error_text.py` +5 (4 cycles), `test_report_pdf.py` +4, `test_error_display.py` +10, `test_error_surfacing_s6_toast.py` (5); RULE-T7: `test_error_surfacing_s6.py` (real CVE export into a missing folder and a `CreateFileW`-locked file, PDF export, 15 worker slots parametrized, pre-scan / network doc / AbuseIPDB). RULE-SD1: suite `[PASS]` **8,045 passed / 5 skipped** in 9 min 46 s · `debug_launch` `Dashboard() instantiated OK` + `window.show() called OK` on a log newer than the launch, no tracebacks · nav reachability 10 passed · no new pages · ruff, import lint (new tests `git add -N`'d), mypy native + linux, pip-audit clean. **Not verified live** — 6.6 joins the S2.4/S4.5/S5.5 source run. Found while building: (1) **headless Edge exits non-zero with no reason for an unwritable PDF target**, so the no-engine error was the answer on every machine that has Edge (fixed, §6 6.2); (2) three existing tests pinned raw error text (§6 6.3a); (3) import lint caught `import ctypes` + `from ctypes import wintypes` in two new tests — the `\| tail` on that first run had hidden its exit code (RULE-GATE1 shape), re-run bare; (4) the Bash heredoc collapsed `"\\n".join` in a replacement script again (the diagnosis-page edit failed its assert and nothing was written — patched with Edit). Next: **S6b** (6.3b + 6.4) |
| S6b | ✅ done | 2026-09-17 | Sized against `d49cbd1` before code (§6 S6b), owner accepted all recommendations. 6.3b the 26 label/status sites + 6 census-blind sinks + 2 more the wider sweep found (the IoT `on_error=` lambda, the hub card's `_classify_error` fallback), 6.3c the update check off the GUI thread, 6.4 census widening + the stringified-exception guard. **Ratchet (a) 26 → hard zero**, and RULE-A2 is now tool-enforced. Matrix **19/19 NOT REPRODUCED** (F6b-DB, F6b-UPD new, both REPRODUCED first against a HEAD worktree). RED-first throughout: 6 census unit tests watched fail on the real tree (26 → 31 after widening), then `test_error_surfacing_s6b.py` (38: real SQLite lock, real missing folder, a real non-image file, a real refused loopback connection, 6 bug-only labels parametrized, the plugin protocol, the credential dialog driven through its own buttons) watched fail 33/36 for the right reasons. RULE-SD1: suite `[PASS]` **8,089 passed / 6 skipped** in 9 m 32 s · `debug_launch` `Dashboard() instantiated OK` + `window.show() called OK` on a log 185 s old, no tracebacks · nav reachability 10 passed · structural guards (bare pass, encoding, dialog leak, page timers) 26 passed · ruff, import lint, mypy native + linux clean · no new pages. **Not verified live** — 6.6b joins the S2.4/S4.5/S5.5/6.6 source run. Found while building: (1) **the census counted its own fix** — `worker_error_text(WE.X, exc)` mentions the caught name, so the widened scanner read 5 correct sites as raw until it learned that helper translates; (2) `_classify_error`'s unmatched branch returned its input unchanged, which is why plugin text needed `plugin_error_text() -> Optional[str]` rather than a text comparison at each site; (3) the Bash heredoc collapsed `"\\n"` into a real newline again, breaking an f-string in the ratchet test (patched with Edit, [[feedback-bash-heredoc-collapses-backslashes]]); (4) import lint caught `import ui.pages.hardware_integration_page` + a `from` import of it in the new test file. Deferred by decision: the IoT thread-affinity defect (§6 S6b findings) is its own next item |
| S4 follow-up | ✅ done | 2026-09-17 | Owner: "do recs". (1) Home's other two pill sets (monitoring card `_pill_*`, recommendation row `_rec_pill_*`) now paint ON-but-failing too — one painter, `_paint_failing_pill`, amber + `⚠`, failure tooltip, the pill's own description tooltip restored on recovery; RED-first `test_the_other_two_home_pill_sets_are_not_green_for_a_failing_monitor_either`. (3) `modules/snmp_trap_receiver.py` docstring corrected: 162 → 16200, then `OSError` — no random-port fallback. Not changed: Send-test buttons bypassing the router (a finding, no recommendation made). Gate: suite `[PASS]` 7,957 passed / 5 skipped · `debug_launch` OK · ruff/mypy clean |
| S6c | ✅ done (6c.5 open) | 2026-09-18 | IoT Behaviour thread affinity (§6 S6c), sized against `d32647a` before code; owner accepted all three recommendations. RULE-WIN27 written first (RULE-TP4) with its AST guard — RED on exactly the two IoT threads (8 writes), green on the other four `ui/` thread sites. RED-first `test_iot_thread_affinity.py` 7/7 failed for the named reasons, incl. one worse than sized (a monitor start error was overwritten by "Monitoring…"). Fix: 3 Dashboard signals, run-tagged slots, `IoTMonitor` built on the GUI thread, `IOT_LEARN_RUN`/`IOT_MONITOR_RUN`; `modules/` unchanged; IoT tests 5/5 green in a loop. Matrix **20/20 NOT REPRODUCED** (IOT-THREAD new, REPRODUCED against a HEAD worktree first; its first version had a wait-for-first-change race, fixed — §7). RULE-SD1: suite `[PASS]` **8,101 passed / 6 skipped** in 10 m 0 s · `debug_launch` `Dashboard() instantiated OK` + `window.show() called OK` on a log 4 s newer than the launch, 0 tracebacks · nav reachability 10 passed · ruff, import lint (new tests `git add -N`'d — it caught an `import`+`from` pair in the new test), mypy native + linux clean · no new pages. **Not verified live** — 6c.5 joins the source run. Four findings logged in §6 S6c, not fixed |
| Live look | ✅ done (S2.4 open) | 2026-09-18 | Source run with `experimental/app_health_v1` on; owner clicked S4.5/S5.5, agent ran S6.6/6.6b/6c.5 headless on the real paths at the owner's request (§6 *Live look*). **The app-health strip found a real defect on its own**: `scheduler:reports` at every launch. Fixed RED-first: **L1** every fixed-width spin box cut its value (16/22; widths 122/94/106, native AST-swept test, RULE-QSS5 corollary), **L2** S6 error toasts cut their own next step (`heightForWidth`, action on its own row, RULE-UI2), **L3** scheduled reports + Copy summary failed on any real network (`None` uptime window). Logged L4-L11 (S4.5 recipe wrong twice, dev-server hides the bind cause, save dialog opens in the cwd, CVE Export hidden when empty, IP Calculator stale bits, IoT Learn label, drain deadline). Gate: suite `[PASS]` **8,109 passed / 5 skipped** in 10 m 32 s · `debug_launch` `Dashboard() instantiated OK` + `window.show() called OK` on a fresh log, 0 tracebacks · ruff, import lint (new tests `git add -N`'d), mypy native + linux clean · crash/exception logs unchanged all session. S2.4 still needs one uninterrupted hour |
| S7 | ✅ done (`70ee0d1`) | 2026-09-19 | Owner cut: 75 (a) + B1 (both shapes) + B3 + B4 + B4a; S7b = B2/B5/B6/B7 recorded only (§6 S7). Matrix rows B1-UNREACH, B1-HOLD, B3, B4, B4a added and **REPRODUCED against a `fff5233` worktree** before any fix, then **25/25 NOT REPRODUCED** on the final tree (twice). New contracts: `DnsZoneResult.axfr_error`, `DiscoveryResult.methods_failed` (both owner-approved), and `DnsZonePage.scan_not_testable` as plumbing for the agreed registry state. `axfr_transfer()` now returns `(records, error)`. **Ratchet (b) modules 304 → 224**, watched RED at 299 first. RULE-T7 tests: `test_error_surfacing_s7.py`, 30 tests; 25 watched fail for the named reasons, 5 are guards. Two deviations, both in §6: the AXFR reader also stops at an error RCODE (otherwise REFUSED plus a held connection becomes a new "Could not reach" lie), and B4 redacts the password from the exception's argv before `exc_info`. Gate: ruff, import lint (new test `git add -N`'d), mypy native + linux clean. `debug_launch`: `Dashboard() instantiated OK` + `window.show() called OK` on a log written 4 s after launch, 0 tracebacks. Crash and exception logs byte-identical all session. **Suite `[FAIL]`: 8,153 passed / 5 skipped / 1 failed.** The failure is `test_threat_intel_worker.py::test_feed_refresh_lifecycle`, which downloads live feeds within a 10 s budget. `rules.emergingthreats.net` took **18.7 s** (curl, measured at the time). The same file failed at HEAD in the worktree (1 of 2 runs) and imports no S7 module; S3 logged the same flake. The first run also caught a real defect of mine: RULE-DBG5's orphan ratchet flagged the `axfr_transfer` wrapper as test-only (50 vs 49), fixed by folding it into one function. Found, not fixed: `_dns_leak_test` has never worked (`_json` undefined, F821 outside the gate), the ARP-cache read ignores the CIDR, and the DNS Zone status label does not wrap. **Next: S8** (§6 S8; UI refresh paths and grading inputs). |
| S8 | ✅ done | 2026-09-20 | Triage first (§6 S8): **173 handlers** across the ten files, the great majority genuine (a) — `scan_enrichment.py`'s 25 are (a) to a one. Owner cut: **B8–B14**, key-only for B8; `persist_alert` (7 sites) + the ARCH RULE 2 gap recorded as S8b. Matrix rows B8/B9/B10/B11/B12-ROW/B12-UNDO/B13-ANN/B14 added and **REPRODUCED against a `70ee0d1` worktree** before any fix, then **33/33 NOT REPRODUCED**. **The headline: availability had never once reached the health score** — `_availability_score` read `row["24h"]` while `query_uptime_table` emits `str(hours)`, so the heaviest input (weight 0.45) always took its optimistic 80.0 default and the red-state "devices are unreachable" headline was unreachable code; a device DOWN half the window measured **91, green, "healthy for 7 days"**. The weekly digest was reading three inputs that were never there: a Grade tile calling `get_grade_result()` (never existed on MetricStore), a new-device filter on `("join", "new")` (the store *rejects* both — the vocabulary is `JOINED`), and an uptime table that collapsed entirely because `.get(key, default)` does not fall back on a present-but-None value. New contract: `SCHEDULED_SCAN` ConditionSpec, mirroring `SCHEDULED_SPEED_TEST` (B14 — `next_ts` advances before the scan is attempted, deliberately, so the condition is the only trace a missed run leaves). **Ratchet (b) ui 386 → 376.** RULE-T7 tests: `test_error_surfacing_s8.py`, 23 tests; **17 watched fail against HEAD** for the named reasons, 6 are guards. **Why the suite never caught B8–B11:** `tests/test_health_score.py` encoded the defect as the contract — its fixture docstring claimed `{"24h": pct}` "matches query_uptime_table output" and mocked a store returning the key the real one never emits (12 occurrences, now corrected); `MagicMock` auto-creates `get_grade_result` so B9 could not occur under test; and `test_build_digest_html_no_crash_with_minimal_store` wraps its assertion in `pytest.skip` on `TypeError`, which is exactly B11's exception. Three matrix rows first probed `captured_records()` and read REPRODUCED *after* the fix — a `log.debug` companion is filtered at production level — so they were re-anchored to the toast and **re-verified against HEAD**. Gate: ruff, import lint, mypy native + linux clean; **suite `[PASS]` 8,177 passed / 5 skipped / 0 failed** (S7's live-feed flake did not recur); `debug_launch` `Dashboard() instantiated OK` + `window.show() called OK`, 0 tracebacks, crash log byte-identical (6,784,379 b, mtime 2026-07-30) and exceptions log mtime 2026-09-05 — both predate this session. Found, not fixed: the 7 `persist_alert` swallows, and `home_data_mixin:1012` running raw SQL via `self._store._conn.execute()` from the UI layer, which `test_metric_store_encapsulation.py` cannot see because it greps only `_execute_write(`/`_execute_read(`. **Next: S9** (§6 S9; consistency and polish). |
| S9 + S10.1a | ✅ done | 2026-09-20 | Sized against `e0e999a` from a fresh census before any code (§6 S9/S10). Owner cut: **9.1 + 9.2 + 9.4-scoped + 10.1a**; 9.5 cut entirely, 9.3 cut (coupled to 10.2), REST `/health` cut, 10.1b recorded. Matrix rows S9-STORM/GLYPH/PDF/LOGEXP/MAPEXP/APPTRAF and S10-EVTLOG/STDERR added and **REPRODUCED against an `e0e999a` worktree** before any fix, then **41/41 NOT REPRODUCED**. **Most of F8 was never a defect:** 11 of its 13 literals are scan-*state* or OS-guess-*confidence* words, now recorded as no-change so the next reader does not reopen them. The two real ones were the Monitor Overview storm tile writing `Storm`/`Warn`/`Clean` verbatim, and — found while fixing it — the Broadcast Storm page's own "Storm level" stat doing the same at 18 px directly above a status line already rendering `risk_to_label()`: one page, one measurement, two vocabularies. **9.4's wording pass was already done by S5** — `_PACKET_CAPTURE` covers 7 entries, and the five `modules/` sites that interpolate `{exc}` reach only the *tooltip* because every UI sink routes through `show_worker_error` (traced site by site, not assumed); the one real defect was `WE.APP_TRAFFIC`, whose why/next described a failure its producer cannot raise and told a driverless user to retry forever. **9.2 converted 3 of 17 sites** — 12 are RULE-A1 detail views and the 2 "Diagnostic report saved" modals stay by owner decision (they carry `REDACTION_NOTE`); the sharpest was `log_source_panel._export_visible`, where the ladder was **inverted** — the non-event was a modal and the successful write was silent. **10.1a's headline: four headless sinks the (a) ratchet is structurally blind to.** The census knows Qt widget methods, so `servicemanager.LogErrorMsg` and `print(file=sys.stderr)` were invisible — and a CLI user was getting the raw sv-SE `[WinError 183] Det går inte att skapa en fil som redan finns` verbatim. Census widened with entry-point-scoped headless sinks (mirroring S6.4's `ui/` scoping) and **it immediately counted its own fix**, exactly as S6b's did, until `_headless_error` joined `_TRANSLATORS`. **(a) back to 0 under the wider net; (b) unchanged at 651 and the orphan ratchet unchanged at 49 — no ratchet moved.** RULE-T7 tests: `test_error_surfacing_s9.py`, 27 tests; **21 watched fail against the `e0e999a` worktree** for the named reasons, 5 are guards. **Two existing tests held the old behaviour as the contract** and were corrected to derive rather than re-pin: `test_error_surfacing_s6b.py` pinned the credential dialog's `✗` as a literal — the very inconsistency 9.1b fixes — and pinned `APP_TRAFFIC`'s old `what`. **S10-STDERR's predicate had to go back to HEAD:** its first version matched `"sub"`, part of the path the *fixed* message still legitimately names, and compared against `NotADirectoryError` where Windows raises `FileExistsError` — so it read REPRODUCED on the fixed tree for two reasons unrelated to the defect. Re-derived from the real `mkdir` and re-proved REPRODUCED at `e0e999a` before being trusted. **Caught on diff review, not by a test:** the `reports_page` success toast first landed *inside* the guarded `try` — RULE-SURF1’s inverse corollary, the exact S6.0 defect, where a confirmation guarded by the same handler reports finished work as failed. Moved to `else:` and pinned by a new guard test, verified to fail with the right message against a reconstructed buggy variant (a bare `pytest.raises` failed on the wrong line, because the buggy shape *swallows* the error). Storm-tile headline widths measured **natively** (Segoe UI, `platform=windows`): 90 px widest against ≥176 px available — an offscreen probe would have lied (live-look L1). Gate: ruff, import lint (new test `git add -N`'d — it caught an `import`+`from` pair for `log_source_panel`), mypy native + linux clean; suite `[PASS]` **8,204 passed / 5 skipped / 0 failed in 10 m 02 s**; `debug_launch` **`Dashboard() instantiated OK` + `window.show() called OK` on a log written 4 s after the launch, 0 tracebacks**; crash log byte-identical (6,784,379 b, mtime 2026-07-30) and exceptions log mtime 2026-09-05 — both predate this session. The first suite run was red on `test_no_bare_pass`: three `except SystemExit: pass` in my own new matrix rows (RULE-LINT2), comment-only fix. **Next: S10.2 — needs owner sign-off, it is a shipped-behaviour change — then S10.3 (owner-run chaos + final matrix re-run + closure).** |
| S10.2 | ✅ done | 2026-09-20 | The RULE-EXP1 flag is **removed**, not defaulted True: S4.5's live look satisfied the rule's deletion gate, and one shipping path means the release's chaos run tests what ships. Six gates gone — `FLAG_KEY`/`app_health_ui_enabled`, `_wire_app_health(surface=)`, `_wire_monitor_error_surface(note=)` **and its one-time status-bar note**, the `if _app_health_ui:` around `_seed_listener_pages`, `home_page.py`'s strip gate, and `_pill_failures`' `None` return. **Two sites the plan's located diff did not name, both found by running tests rather than reading code:** (1) a sixth gate in `ui/nav/builder.py:899`, where a failing Home pill repainted only `if _app_health_bridge is not None` — the flag's proxy, invisible to any grep for the flag's own names, caught by `test_a_registry_error_repaints_the_pills_at_once`; (2) the matrix's F2-G6 row branched on `"note" in signature(...)`, so deleting `note` would have dropped it into the legacy branch asserting a note the code can no longer write — REPRODUCED for the opposite of the real reason, corrupting the very 10.3 re-run it feeds. Now keyed on the parameter's *absence*. Deleting a flag is mostly a **test**-deletion job: `_flag()` and the flag-off strip test went, and four more tests were fallout — including one whose `window` was a `SimpleNamespace`, fine while `surface=False` skipped `AppHealthBridge(parent=window)` and a `TypeError` the moment it did not. RED watched on both new guards before any source change. **The third rewritten test passed before the fix** — this machine's registry still had the flag on from S4.5, so it was reading real developer state, not the code. Matrix re-run on the final tree: **41 rows, 0 REPRODUCED, 0 inconclusive**. **Verified in live app (RULE-T6):** ran `app.py` itself with the corrected S4.5 fault (TCP 8765 held `SO_EXCLUSIVEADDRUSE`, REST API enabled) — log records `condition raised: rest_api:serve`, and the real window on Home draws the strip under the freshness row with the amber dot, *The REST API could not start*, the why+next sentence and **Open REST API**, all four in the live UIA tree and in a native screenshot, 0 tracebacks. **Three traps from that run, none of them app defects, all worth knowing before the next live check:** (1) the nav reads `nav/last_page` from the **INI** via `QSettings(settings_path(), IniFormat)` while `rest_api/*` reads `QSettings("NetSentinel","NetSentinel")` — two backends in one app, so writing the registry left the app on Network Logger with the strip merely off-screen, which reads exactly like "the strip is broken"; (2) slicing the app log's *decoded text* by a **byte** offset hides the new records once the log carries localized sv-SE error text — the first run reported `raised=[]` against a log that contained the record; (3) an **Info** condition cannot open the strip by design, so the syslog random-port fault is the wrong probe here — it needs a Warning. Next: S10.3 (owner-run chaos + closure). |
