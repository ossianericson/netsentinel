# NetSentinel Backlog

## Vision

NetSentinel exists to answer one question: "what is happening on my network right now?" It does this in three ways that no other free tool combines.

First, it replaces five separate CLI utilities with a single interface that speaks plain English — the de-facto tool anyone reaches for when their network is broken. Second, it works with whatever hardware you own, not just supported brands — an open plugin protocol lets any Python script become a first-class integration, and an AI assistant can write that script in ten minutes. Third, it shows you *why* something is happening, not just that it is — every detection event comes with an explanation of the underlying protocol and what you should do about it.

Everything on this backlog serves one of those three goals. If an item does not clearly serve one, it does not belong here.

---

## Completed (feature/p0-plugin-data-flow — v1.9.18)

The following were built in the plugin data-flow sprint and are done:

- **PluginWorker** — runs plugin via `--netsentinel` subprocess shim, emits `{"info","status","clients"}` JSON
- **Plugin clients → Devices table** — `_apply_mesh_enrichment` handles both Deco and plugin enrichment; `unit` field populates Node column; fallback synthesised from `plugin_name` if absent
- **Plugin status → topology** — `_plugin_nodes` drives topology mid-layer; synthesised for single-router plugins that omit `nodes`
- **Periodic refresh** — 5-min auto-worker for each active plugin
- **Discovery banner** — AST-parses bundled plugins, flags unimported matches after scan, cache cleared on each plugin result
- **`template_plugin.py`** — complete authoring template based on verified deco_plugin.py structure
- **`fritzbox_plugin.py`** — FritzBox integration using `fritzconnection`
- **Group by node button** — disabled until enrichment data arrives; re-enabled with node data
- **Speed test empty state** — stacked widget; empty panel before first run
- **Keychain security notes** — Hardware Hub password field + plugin card password field
- **24 QueuedConnection fixes** — all worker lambda connects use `Qt.ConnectionType.QueuedConnection`
- **Dashboard fallbacks** — missing `unit`/`nodes` fields handled in dashboard, not requiring plugin authors to know about them

---

## P0 — Bugs / Broken Experiences ✅ All done

| ID | Status | Description |
|----|--------|-------------|
| P0-N3 | ✅ Done | `_modem_page` and `_mesh_router_page` confirmed as background data handlers only (never in nav). Dead `label == "Modem"` nav-change check removed. Plugin pages (Extend section) are the visible UI for hardware. |
| P0-N5 | ✅ Done | All "Port Scan (SYN)" labels standardised to "Port Scan (TCP)". Two `_nav_rail_go_to("Port Scan (SYN)")` calls fixed. Standard nav entry fixed. Help panel text fixed. overview_page.py scan button fixed. |
| P0-HW1 | ✅ Done | Already implemented in prior sprint: `_pg.test_requested.connect(self._on_plugin_page_test)` at dashboard.py line 2401; `_on_plugin_page_test` delegates to `HardwareIntegrationPage._run_plugin`. |

---

## P1 — High Impact UX

### D — Diagnostic Consolidation ✅ Done

| ID | Status | Notes |
|----|--------|-------|
| D1 | ✅ Done | "Health Check" removed from Standard nav; "Connectivity Tests" removed from Analysis rail. `_dia_tab` still exists as hidden widget (used by ISP Report auto-run). `_diagnosis_page` is now the only visible diagnostic entry point. |
| D2 | ✅ Done | "Root Cause Analysis" removed from Diagnostics subgroup and Analysis rail. |
| D3 | ✅ Done | Rail item renamed "Diagnose" → "What's Wrong?". `_open_diagnosis` updated. `_DISCOVERY_PAGES` entry updated. Pulse bar click updated. |
| D4 | ✅ Done | `_btn_diagnose` on Home page is now solid primary blue, equal weight to Scan button. Text updated to "◆ What's Wrong?". |
| D5 | ✅ Done | DiagnosisPage healthy result shows "Get a Network Grade score →" link button. Hidden when findings are present. Wired through existing `navigate_to` signal → `_on_overview_navigate` → `_nav_goto_label`. |

### N — Navigation Cleanup

| ID | Status | Description |
|----|--------|-------------|
| N1 | ✅ Done | Extend section rail button tooltip updated to "Extend — N plugins active" on every `_on_hardware_plugin_result` call (both modem and router paths). |
| N2 | ✅ Done | Duplicate "DHCP Leases" removed from Advanced standard nav. `_nav_adv_rows` compat ref updated. |
| N4 | ✅ Done | Syslog/SNMP Trap standalone entries only exist in dead Standard nav code — rail nav (the only visible nav) has "Network Logger" (Log Hub) as the single entry point. No visible duplication for users. |

### HW — Hardware & Plugin Experience

| ID | Status | Description |
|----|--------|-------------|
| HW2 | ✅ Done | `_save_password` already updates `_pw_status` label: "✓ Saved" (green) on success, "Error" (red) on failure, auto-clears after 3 s. Already implemented. |
| HW3 | ✅ Done | Discovery banner "Configure →" button already navigates to Hardware page. |
| HW4 | ✅ Done (folded into N1) | Extend section tooltip badge shows active plugin count. |
| HW5 | pending | **Plugin onboarding completeness.** Audit the full first-time flow: import → password → Test → data appears. Verify every step has visible feedback. |
| HW8 | ✅ Done | `_TEMPLATE` in hardware guide updated to include `unit` field in `get_clients()` and `nodes` list in `get_status()` with inline docstrings matching `template_plugin.py`. |

### UX — First-Time User Experience

| ID | Status | Description |
|----|--------|-------------|
| UX1 | ✅ Done | Home page shows "Press ▶ Scan Network to discover your devices — takes about 30 seconds." when device count is zero after preload. Reverts naturally to device summary after first scan. |
| UX2 | pending | **Npcap gating messaging.** Audit all 6 Npcap-gated features for consistent "requires Npcap" error messaging. |

### XF — Cross-Feature Deep Links

| ID | Status | Description |
|----|--------|-------------|
| XF2 | ✅ Done | `_on_alert_navigate` maps all 10 rule types to correct rail nav labels. Fixed case bug ("TLS & Exposure") and fallback label ("Devices"). Tests updated. |

### ES — Empty States

| ID | Status | Description |
|----|--------|-------------|
| ES1 | ✅ Done | WiFi Heatmap already has canvas empty-state text + "Import Floor Plan" toolbar button + status label. Workflow explanation present in subtitle. |
| ES2 | ✅ Done | Config Snapshots: added `_empty_lbl` shown when no snapshots exist; "No snapshots yet. Take your first snapshot to start tracking configuration drift." Toggled in `_refresh_table`. |
| ES9 | ✅ Done | NetworkGradeTile empty state is now a clickable "Run Network Grade →" button that triggers the rerun callback. Disabled/plain-text after grade loads. Modem tile hint updated from "Modem tab" to "Hardware". |

---

## P2 — Meaningful Improvements (good features made great)

### N — Navigation Cleanup (continued)

| ID | Description |
|----|-------------|
| N6 | **Analysis rail section split.** The Analysis section mixes threat detection (Broadcast Storm, Rogue Bridge, IoT Behaviour) with analysis tools (Hop-by-Hop Trace, ARP Spoof Watch, Root Cause Analysis). These answer different questions. Consider splitting into "Threat Detection" and "Deep Analysis" sub-sections in the rail, or reorganising the item order so threat items are grouped at the top. |
| N7 | **"Plugin Modules" in Security Audit renamed.** Users confuse this (custom recon plugins) with Hardware Hub plugins. Rename to "Recon Plugins" with a tooltip: "Custom port-scanner and enumeration scripts — not hardware driver plugins." |

### HW — Hardware & Plugin Experience (continued)

| ID | Description |
|----|-------------|
| HW7 | **Per-instance IP override.** `HARDWARE_IP` in a plugin file is a compile-time constant. If two users have different gateway IPs, neither can use the same plugin file unchanged. The plugin card should let the user override the IP at import time; override is stored in settings alongside the password, and passed to the subprocess as an env var or argument. |

### UX — First-Time User Experience (continued)

| ID | Description |
|----|-------------|
| UX3 | **"What to do next" suggestions quality.** The Home page suggestions section should guide a new user through the most valuable next step after their first scan, not show generic items. Evaluate whether the current suggestion logic actually prioritises "new device joined", "high-risk CVE", and "run Network Grade" in that order for a first-time user. |
| UX4 | **Ctrl+K discoverability.** The Ctrl+K shortcut is the best feature in the app for discovering functionality. Its hint is in the collapsible Quick Tips section below the fold — too hidden. Add a one-line "Try Ctrl+K to find anything →" prompt in the Home page empty state, visible before the first scan. |

### XF — Cross-Feature Deep Links (continued)

| ID | Description |
|----|-------------|
| XF1 | **CVE hits in Devices table deep link.** When a device row shows a CVE flag, the right-click menu should include "View in CVE Tracker →" which navigates to that device's CVE entry. |
| XF3 | **Threat Intel link from Active Connections.** When a remote IP in Active Connections matches a known bad IP in the Threat Intelligence cache, show a flag icon in that row. Clicking navigates to Threat Intel and highlights that IP. |
| XF4 | **Network Grade fix links.** When a grade dimension scores D or F, the card should show a "Fix this →" link that navigates to the relevant page (e.g. "DNS: F" → "DNS & Outages", "Security: D" → "Security Overview"). |
| XF5 | **Security Overview aggregation.** The Security Overview page should aggregate findings from all audit scans run so far, not require the user to run each scan individually to see the combined picture. After any audit scan completes, push its findings into the Security Overview. |
| XF6 | **Inventory Changes deep link.** Clicking a device row in Inventory Changes should open that device highlighted in the Devices table (filter/scroll to that MAC). |
| XF7 | **Modem tile navigation.** When a modem plugin is active, clicking the ModemSignalTile on Overview should navigate to that plugin's device page. |

### ES — Empty States (continued)

| ID | Description |
|----|-------------|
| ES3 | **DHCP Lease page.** Empty before DHCP scan runs. Add an inline "Scan DHCP leases" button so users understand the page is data-driven and know how to populate it. |
| ES4 | **Custom Triggers.** Empty state should explain what a trigger is and offer a template ("Alert me when a new device joins") as a one-click starting point. |
| ES5 | **Home Automation page.** Empty state should explain the HA integration and link to MQTT setup if MQTT is not yet configured. |
| ES6 | **Trend Forecasts.** Needs Log Hub data to work. Empty state should say "Enable Network RTT logging in Log Hub to start building forecast data" with a direct link to Log Hub. |
| ES7 | **IPv6 Devices.** Most home networks have no IPv6. The empty state should say "No IPv6 devices found — this is normal for most home networks" rather than looking like a scan failure. |
| ES8 | **Availability History.** Before first scan the page is blank. Add a brief empty state with a "Run a scan to start tracking device availability" prompt. |

### VC — Visual Consistency

| ID | Description |
|----|-------------|
| VC1 | **Group by node hint when disabled.** Add 10px muted hint text below the button: "Connect a router plugin to enable grouping". |
| VC3 | **Loading state standardisation.** Some pages show "Loading…" text, others show spinners, others show nothing at all while a worker runs. Standardise to a subtle inline spinner + muted text label across all scan-driven pages. |
| VC4 | **Compatibility notice updates.** The Modem page (ZTE MC889) and Mesh Router page (TP-Link Deco) have compatibility notice strips. Verify these mention the Hardware Hub plugin system as the path for other hardware models. |

### MA — Monitoring & Alerts

| ID | Description |
|----|-------------|
| MA1 | **IoT Behaviour anomaly action.** When an anomaly fires, the user needs a "Investigate" or "Quarantine" CTA. Currently the anomaly appears in the table but there is no suggested next action. Add a context-sensitive action row below the anomaly finding. |
| MA2 | **Custom Triggers discoverability.** The trigger builder is powerful but impossible to find. Add a "Create custom alert →" link-button in the Notifications page empty/footer area. |

### RP — Reports

| ID | Description |
|----|-------------|
| RP1 | **Rename "ISP Report".** "ISP Report" is unclear to home users who have never filed an ISP complaint. Rename to "Network Health Report" with subtitle "Great for ISP support tickets". |
| RP2 | **Baseline drift notifications.** When a Config Snapshot detects drift after a scan, the user should receive a toast notification. Currently drift is only visible if the user navigates to the Snapshots page. |

---

## P3 — Polish (self-contained, no dependencies)

| ID | Description |
|----|-------------|
| D6 | DiagnosisPage re-analysis diff: show "1 new finding since last run" when severity changed vs previous result. |
| N8 | Right-click to pin nav items: mention this somewhere visible on first launch, not only in the collapsible Quick Tips section. |
| VC2 | Nav icon consistency: most pages use Unicode math symbols but Security Audit uses emoji (🔎, 🛡, 🧠). Pick one system and apply it throughout. |
| HW6 | Legacy Modem/Mesh pages (ZTE MC889 / TP-Link Deco XE75) run parallel to the plugin architecture. Long-term these should be converted to plugin-backed pages — the plugin provides data, the existing rich UI stays. Not urgent; the current two-system approach works. |
| SK1 | Skeleton loading rows while scan workers run: prevents layout jump when data arrives; placeholder rows styled in `TEXT_MUTED`, swapped out when the worker emits results. |
| A11Y | "Abyss" WCAG AA high-contrast theme: true black background, high-contrast text, no low-opacity elements. |
| KBD | Keyboard shortcut reference card in Help panel — the shortcut list currently only appears in Settings. |
| 802 | Passive 802.11 monitor mode capture — puts a supported NIC into monitor mode via Npcap, reads raw management/probe/beacon frames. Falls back silently if unsupported. Power-user feature. |

---

## P1-Carry — Explainer Panels (from previous sprint)

**"What just happened?"** — After every scan result, every BPDU detection, every CVE match, every alert, a collapsible panel explains in plain English what the protocol is, why this result matters, and what to do about it.

`ui/widgets/explainer_panel.py` already exists. This is wiring it to detection results on each page, one page at a time, shippable incrementally.

**Order:** Broadcast Storm → Rogue Bridge (STP) → ARP Spoof Watch → IoT Behaviour → Protocol Visualizer (already done).

---

## P2-Carry — ISP Comparison (requires backend)

Anonymous opt-in only, zero PII. Submits ISP name, country code, anonymised speed, latency, and uptime percentage once per day. Shows the user how their connection compares to the median for their ISP and country.

"Your latency is 42 ms — 38% worse than the median for your ISP" is actionable. Creates a re-engagement hook.

**Honest flag:** Only item on the backlog that requires server infrastructure — ongoing costs, API maintenance, privacy policy update. Do not start until plugin data flow is complete and there is a clear backend plan. Effort is L and that L is mostly the backend.

---

## Parking Lot

- **CompTIA Network+ / CCNA curriculum alignment** — badges on each page showing which exam objective it covers. S effort but creates institutional positioning that may conflict with the hardware plugin angle. Only worth doing if educators ask directly.
- **Per-page documentation link** — small `?` on each page header linking to the relevant wiki section. Requires a wiki to exist first.
