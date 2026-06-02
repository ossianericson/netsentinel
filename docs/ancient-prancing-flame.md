# NetSentinel — Product Backlog Audit & Prioritized Plan
*Audit date: 2026-06-02 | Revised: 2026-06-02 | Session: Sprint A2+A4+B1 complete | Version at audit: v1.9.69*

---

## Context

Full audit of repository architecture, test coverage, UX quality, and feature completeness.
Two lenses applied:
1. **End-user understandability** — can someone with zero networking knowledge use this to learn?
2. **Real-world usefulness** — does it catch real problems on a real network and tell you what to do?

The codebase is technically excellent (89/89 modules tested, 63 nav pages wired, zero FIXME debt,
zero hex colours outside styles.py). The critical gaps are **UX depth** and **educational scaffolding**
— the app is feature-complete but under-explained for the target audience.

---

## Design Principles (derived from audit)

These four principles must govern every fix step, every remediation text, every empty state,
and every new UX copy written in this project. They are not optional.

### Principle 1 — The app is the diagnostic tool
NetSentinel already ran `nslookup`, `ping`, `tracert`, and the speed test.
A fix step that says "open Command Prompt and run nslookup" is telling the user to
duplicate what the app just did. **Never ask a user to run a command-line tool.**

Fix steps must say what was found, not ask the user to find it again:
> ✓ "NetSentinel measured your DNS latency at 340 ms — above the 200 ms threshold."
> ✗ "Open Command Prompt and run: nslookup google.com"

### Principle 2 — Fix at the router, not the device
Changing DNS on a single Windows machine fixes one device.
Changing it on the router fixes every device on the network.
Fix steps should always prefer the router web interface over OS-level settings dialogs.

> ✓ "Open your router's settings page at http://[gateway_ip] and change the DNS server to 1.1.1.1"
> ✗ "Open Network Adapter settings → IPv4 Properties and set DNS manually"

The `gateway_ip` value is already in `DiagnosticsResult.gateway_ip`. It must be threaded
through to every remediation string so links use the actual IP, not a placeholder.

### Principle 3 — App-measured data in ISP escalations
When a finding concludes "contact your ISP", the fix step must include the specific numbers
NetSentinel measured so the user has evidence to quote.

> ✓ "Call your ISP. Tell them: NetSentinel measured [X]% packet loss and [Y] ms latency
>    over [N] minutes. Please investigate packet loss beyond hop 1."
> ✗ "Run a speed test at speedtest.net and compare with your plan speed."

### Principle 4 — Close the loop with a rescan
Every fix step must end with a verification instruction that uses the app:
> "After making this change, click Rescan in NetSentinel to confirm the problem is gone."

### Principle 5 — CLI is allowed in Education section only
Lab Mode exercises and Protocol Visualizer panels *may* show CLI commands as **learning
content** — the purpose there is to teach users what the tool does under the hood.
This is intentional and should not be changed.
CLI commands are banned everywhere else: diagnostics, fix steps, alert drawer, homepage, notifications.

---

## Sprint A — Progressive Disclosure & Novice Layer
*Impact: highest. Every new user hits these gaps within the first 5 minutes.*

### ✅ A1 — Network Grade: explain the 8 dimensions inline *(done 2026-06-02)*
**Problem:** The grade page shows A–F but never tells the user what the 8 dimensions are, why they
matter, or how to improve a specific one. "STP Health" and "Broadcast Storm Level" appear in the
score with zero context.

**Work:**
- Add a collapsible "How this grade is calculated" panel to `ui/pages/overview_page.py`
- List all 8 dimensions (Uptime, Latency, Jitter, DNS Speed, Download Speed, Device Safety,
  STP Health, Broadcast Storm Level) with one-sentence plain-English descriptions
- For each dimension that scored less than A, show a one-line actionable tip with a link to
  the relevant page (e.g., "STP Health: C — a device is acting as an unexpected network bridge.
  Go to Rogue Bridge (STP) to investigate.")
- Clicking a dimension name navigates to the relevant page

### ✅ A2 — Unified empty state component *(done 2026-06-02)*
**Problem:** All major pages show a blank table or bare CTA when no scan has run. Users don't
understand what the page will show them, so the CTA has no motivation.

**Work:**
- Create `ui/widgets/empty_state_card.py` — a reusable `EmptyStateCard(icon, title, what_it_shows, why_it_matters, btn_label)` widget
  (do not duplicate the pattern 5 times)
- Apply to the 5 most-visited pages: `overview_page.py`, `inventory_page.py`,
  `security_overview_page.py`, `uptime_page.py`, `cert_page.py`

Required structure:
```
[Icon]  What this page shows
        One sentence: what data appears here after a scan.

        Why it matters
        One sentence: what problem it helps you catch.

        [Primary CTA button]
```

Example — Devices page:
> **What this page shows:** Every device currently connected to your network — phones, laptops,
> smart TVs, routers — with their IP address, MAC address, and manufacturer.
>
> **Why it matters:** You can't secure a device you don't know exists.
>
> [▶ Scan Network]

### ✅ A3 — App-native remediation (eliminate all CLI references outside Education) *(done 2026-06-02)*
**Problem:** Fix steps in `modules/diagnosis_page.py` (3 instances) and
`modules/root_cause_correlator.py` (2 instances) tell users to run terminal commands or
visit external websites, violating Principles 1–3.

**Specific violations found:**
| File | Line | Violation | Replacement |
|------|------|-----------|-------------|
| `diagnosis_page.py` | 55 | "Open Command Prompt and run: nslookup google.com" | "NetSentinel measured your DNS at [X ms] — if slow, change DNS on your router at http://[gateway_ip]" |
| `diagnosis_page.py` | 66 | "Run a ping -t 8.8.8.8 in Command Prompt" | "NetSentinel's ping test showed [X]% packet loss. See Connection Stability page for a full timeline." |
| `diagnosis_page.py` | 91 | "run ipconfig /release then ipconfig /renew" | "Disconnect from Wi-Fi and reconnect, or unplug and replug the Ethernet cable." |
| `root_cause_correlator.py` | 350 | "open Network Adapter settings → IPv4 Properties" | Remove — router fix covers all devices; keep only the router instruction |
| `root_cause_correlator.py` | 368 | "Run a speed test at speedtest.net from the same device" | "NetSentinel measured [X Mbps] on this device. If below your plan speed, call your ISP with this number." |

**Additional work:**
- Thread `gateway_ip` from `DiagnosticsResult` through `correlate()` in `root_cause_correlator.py`
  so every "open your router settings" link becomes `http://[actual_gateway_ip]`
- Add a `verify_step` to the `CorrelatedFinding` dataclass:
  `verify_step: str = ""` — shown as "To confirm this is fixed: [step]"
- Populate `verify_step` for each finding type:
  - DNS issues → "Go to DNS & Stability in NetSentinel and run a fresh DNS test"
  - Speed issues → "Go to Speed Test in NetSentinel and run a new test"
  - Connectivity drops → "NetSentinel's Connection Monitor will automatically detect when the drops stop"
  - Rogue bridge → "Go to Rogue Bridge (STP) — the device should no longer appear in the list"

### ✅ A4 — Jargon glossary: tooltip definitions for technical terms *(done 2026-06-02)*
**Problem:** Terms like "STP", "BPDU", "RFC 1918", "DHCP offer", "CVSS score", "Jitter", "QoS"
appear in the UI without definitions. Advanced users know them; everyone else is lost.

**Work:**
- Create `ui/widgets/jargon_tooltip.py` — a `QLabel` subclass that underlines a term and shows
  a plain-English definition popup on hover (no click required)
- Create `data/glossary.json` — 30–40 key terms with 1-sentence definitions.
  Priority terms: STP, BPDU, ARP, DHCP, DNS, CVSS, RFC 1918, Jitter, QoS, Broadcast Storm,
  Latency, Packet Loss, MAC Address, OUI, MTR, TLS, SNMP, mDNS, SSID, BSSID
- Apply the widget to: `protocol_viz_page.py`, `overview_page.py`, `diagnosis_page.py`, `discover_data.py`

---

## Sprint B — Educational Scaffolding
*Impact: high. Makes the educational use-case viable for structured learning contexts.*

### ✅ B1 — Connect Lab Mode ↔ Protocol Visualizer *(done 2026-06-02)*
**Problem:** Lab Mode exercises tell you *that* ARP spoofing happened but don't explain *how* it
works. The Protocol Visualizer animates ARP perfectly but is unreachable from inside a lab exercise.

**Work:**
- Add a "See how this works →" button at the start of each Lab Mode exercise
  in `ui/pages/lab_mode_page.py` that navigates to Protocol Visualizer with the relevant protocol
  pre-selected
- Add a "▸ What is ARP?" collapsible panel at the top of the "Find a Rogue Device" exercise
  (inline, 3-sentence explainer + diagram link)
- Mirror for other protocols: DNS exercise → DNS diagram, DHCP exercise → DHCP diagram
- Note: Lab Mode exercises *may* show CLI commands as learning content (Principle 5) — preserve these

### B2 — More lab scenarios (target: 10 total, currently ~4)
**Problem:** Only ~4 lab exercises exist. A student completing a CompTIA Network+ unit needs
at least one exercise per major topic area.

**Proposed new scenarios** (add to `modules/lab_scenarios.py`):
1. "Trace a slow DNS lookup" — runs DNS benchmark, compares resolvers
2. "Find an open port" — runs port scan on gateway, identifies service names
3. "Detect a DHCP conflict" — runs DHCP lease scan, flags duplicate IPs
4. "Measure network jitter" — runs RTT logger, identifies unstable connection
5. "Identify device manufacturers" — OUI lookup exercise
6. "Read a network topology map" — guided topology page walkthrough

Each needs: goal, 3–5 steps, hint per step, solution reveal, PASS/PARTIAL scoring.
Each may include CLI commands where the goal is to teach what a tool does.

## Sprint C — Real-World Alerting & Monitoring UX
*Impact: high for daily use. The monitoring features exist but the feedback loop is weak.*

### C1 — Monitoring status explainer on Home page
**Problem:** Monitoring pills (ARP Watch, DHCP Watch, etc.) are grey/offline by default.
A novice user doesn't know if they're broken, intentionally off, or need setup steps.

**Work:**
- Add a tooltip/popover to each monitoring pill in `ui/pages/home_page.py`:
  "ARP Watch continuously monitors for MAC address impersonation. Click to enable."
- Distinguish visually between "off by design" (grey, with toggle) and "running" (green dot)
- Add a "Start all monitoring" button when all are off (visible only on first launch, dismissible)

### C2 — Notification setup in onboarding
**Problem:** `ui/first_run_dialog.py` has 3 slides but never asks the user to set up notifications.

**Work:**
- Add a 4th slide: "Get notified when something changes"
- Show three options: Desktop notification (on by default), Email (enter address), Skip
- Wire selection to the same backend as `ui/pages/notifications_page.py`

### C3 — Actionable alert drawer
**Problem:** The alert drawer shows details but "What to do" likely links to a page without
explaining what to do *on that page*.

**Work:**
- Audit `alert_drawer.py` — verify each alert type has a "next action" CTA
- For the 5 most common alert types (new device, rogue device, DNS slow, port exposed, outage):
  add a "Fix this" button that opens the relevant page AND highlights the flagged item
- All "what to do" copy must follow Principles 1–4 (no CLI, router fix, app-measured data,
  rescan to close)

### C4 — ISP Accountability Report: shareable with evidence
**Problem:** `modules/report_isp.py` exists but needs to be genuinely useful for a non-technical
user to send to their ISP.

**Work:**
- Verify the report output is printable/email-friendly (PDF preferred)
- Add "Copy summary for ISP support" button that generates a ready-to-read script:
  "On [date], my connection at [ISP] experienced [X] outages totalling [Y] minutes.
  NetSentinel measured average download of [Z] Mbps against a contracted [P] Mbps.
  Packet loss peaked at [Q]%. Please investigate."
- The script uses NetSentinel's measurements — no "run speedtest.net" (Principle 3)
- Add a "Legal statement" checkbox for UK/EU users invoking ISP SLA rights

---

## Sprint D — ISP Comparison (Priority 1 roadmap item)
*Impact: killer differentiator. Makes NetSentinel genuinely unique vs every other network scanner.*

### D1 — Anonymous opt-in ISP telemetry
**Work** (from BACKLOG Priority 1):
- Create `modules/isp_telemetry.py`:
  - Collects: ISP name, country (GeoIP), anonymised speed (±15% noise), latency median, uptime%, loss%
  - Submits once per day, opt-in only, no IP address, no device data
- MVP (no backend): show "Your download this week vs your own 30-day average" on Speed Test page
  — uses NetSentinel's own measurement history, not an external test
- Full version: backend comparison against ISP+country median (Phase 2, requires infra)

---

## Sprint E — Technical Debt (RULE violations)
*These are blocking by project rules but lower user-facing priority.*

### E1 — Worker lifecycle tests (RULE-T2 violations, 21 workers)
All workers under `workers/` must have start/stop lifecycle tests per RULE-T2.
Priority order: `scan_worker.py`, `threat_intel_worker.py`, `plugin_worker.py`,
`availability_worker.py`, `speed_test_worker.py` (5 highest-impact first).

Test pattern per RULE-T2:
```python
def test_worker_lifecycle(qt_app):
    w = ScanWorker()
    w.start()
    QTest.qWait(100)
    w.stop()
    w.wait(2000)
    assert not w.isRunning()
```

### ✅ E2 — 7 pages missing scan_requested signal (RULE-UX5 violations) *(done 2026-06-02)*
Pages with a QStackedWidget empty state but no `scan_requested = pyqtSignal()`:
`cert_page.py`, `diagnosis_page.py`, `home_automation_page.py`, `lab_mode_page.py`,
`service_page.py`, `speed_test_page.py`, `trigger_builder_page.py`

Fix pattern: add `scan_requested = pyqtSignal()`, emit from the empty-state CTA button,
wire in `app.py` to the appropriate worker start method.

### E3 — Split metric_store_queries.py (RULE-AH1, 619 lines)
Split into two files:
- `metric_store_queries_uptime.py` — uptime/availability query methods
- `metric_store_queries_metrics.py` — RTT/speed/CVE metric query methods

---

## Sprint F — Polish & Retention
*Lower priority. Improves daily feel but not core functionality.*

### F1 — "Abyss" WCAG AA high-contrast theme (4th theme)
True black (`#000000`) background, no low-opacity elements, all text ≥ 4.5:1 contrast.

### F2 — Keyboard shortcut reference card
Add to Help tab: full table of shortcuts with platform variants.

### F3 — Per-page documentation link
Add a `?` link to each `PageHeader` pointing to the relevant `_PAGE_HELP` entry as a
persistent link, not just a hover tooltip.

### F4 — Settings search: full-text match
Extend `settings_page.py` search to also match setting labels and help text within cards.

### F5 — "Reset to defaults" in Settings
Add a "Reset all settings to defaults" option (confirmation dialog required).

---

## Prioritized Sprint Queue

| Sprint | Theme | Est. Effort | User Impact |
|--------|-------|-------------|-------------|
| **A** | Progressive disclosure, novice layer, app-native remediation | M | ★★★★★ |
| **E2** | RULE-UX5 blocking violations (7 pages) | XS | ★★☆☆☆ (internal) |
| **B** | Educational scaffolding | M | ★★★★☆ |
| **C** | Real-world alerting & monitoring UX | S | ★★★★☆ |
| **D** | ISP comparison | L | ★★★★★ (differentiator) |
| **E1+E3** | Remaining technical debt | S | ★★☆☆☆ (internal) |
| **F** | Polish & retention | S | ★★★☆☆ |

**✅ Sprint A1 + A3 + E2 — COMPLETED 2026-06-02**
- A3: 5 CLI violations eliminated; `gateway_ip` threaded into remediations; `verify_step` field added to `CorrelatedFinding`; `test_sprint_e2_signals.py` + `test_diagnosis_page.py` added
- A1: Collapsible "How is this grade calculated?" panel added to Overview page with 8 dimension descriptions + nav links
- E2: `scan_requested = pyqtSignal()` added to all 7 pages; wired in `app.py` to `_start_full_scan`

**✅ Sprint A2 + A4 + B1 — COMPLETED 2026-06-02**
- A2: `ui/widgets/empty_state_card.py` created; applied to inventory, uptime, cert, security_overview pages; overview CTA copy improved
- A4: `data/glossary.json` (30 terms); `ui/widgets/jargon_tooltip.py`; applied to protocol_viz (button tooltips), overview (grade panel), diagnosis (finding card chips)
- B1: `LabScenario.protocol` field; `explore_protocol` signal + "See how X works →" buttons on all 4 scenario cards; `select_protocol()` public API on `ProtocolVizPage`; wired in `app.py`
- Also fixed: `ui/tabs_recon.py` crash (`@pyqtSlot("QPoint")` → `@pyqtSlot(QPoint)`); `test_colours.py` theme-independence fix

**Next sprint: B2 + C1 + C3**
- B2 (medium): 6 new lab scenarios (DNS trace, port scan, DHCP conflict, jitter measure, OUI lookup, topology walkthrough)
- C1 (small): Monitoring status tooltips/popovers on Home page monitoring pills
- C3 (medium): Actionable alert drawer — "Fix this" buttons for top 5 alert types with navigate + highlight

---

## What is NOT missing (confirmed working)

- All 89 modules have test coverage — no module gaps
- All 63 nav pages are registered, wired, and have help entries
- PyInstaller spec includes all modules/workers/pages — no import gaps
- Zero FIXME/HACK/STUB in production code
- All colours in styles.py — zero hex violations
- First-run dialog exists and is friendly
- Protocol Visualizer is pedagogically strong (real data + explanations)
- Lab Mode exercises are self-contained and functional
- Feature Guide covers 100+ features with mostly plain-English descriptions
- "What's Wrong?" diagnosis is the best feature for novices — symptom → verdict → fix steps
- CLI commands in Lab Mode / Education are intentional teaching content — do not remove

---

## Key files to touch per sprint

| Sprint | Files |
|--------|-------|
| A1 | `ui/pages/overview_page.py` |
| A2 | new `ui/widgets/empty_state_card.py`, then `overview_page.py`, `inventory_page.py`, `security_overview_page.py`, `uptime_page.py`, `cert_page.py` |
| A3 | `modules/diagnosis_page.py` (3 violations), `modules/root_cause_correlator.py` (2 violations + gateway_ip threading + verify_step field) |
| A4 | new `ui/widgets/jargon_tooltip.py`, new `data/glossary.json`, + 4 page files |
| B1 | `ui/pages/lab_mode_page.py`, `ui/pages/protocol_viz_page.py` |
| B2 | `modules/lab_scenarios.py`, `ui/pages/lab_mode_page.py` |
| B3 | new `data/curriculum_map.json`, new `ui/widgets/objective_badge.py`, Lab Mode + Protocol Viz pages |
| B4 | `ui/pages/discover_data.py`, `ui/pages/discover_page.py` |
| C1 | `ui/pages/home_page.py` |
| C2 | `ui/first_run_dialog.py` |
| C3 | `ui/widgets/alert_drawer.py` |
| C4 | `modules/report_isp.py`, `ui/pages/reports_page.py` |
| D1 | new `modules/isp_telemetry.py`, `ui/pages/speed_test_page.py` |
| E1 | new `tests/test_*_worker.py` (21 files) |
| E2 | 7 page files (cert, diagnosis, home_automation, lab_mode, service, speed_test, trigger_builder) |
| E3 | `modules/metric_store_queries.py` → split into 2 files |
