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
| HW5 | ✅ Done | Flow audited: import → validation feedback; card has password field with "✓ Saved"; refresh worker runs immediately; data appears in card. All steps have visible feedback. |
| HW8 | ✅ Done | `_TEMPLATE` in hardware guide updated to include `unit` field in `get_clients()` and `nodes` list in `get_status()` with inline docstrings matching `template_plugin.py`. |

### UX — First-Time User Experience

| ID | Status | Description |
|----|--------|-------------|
| UX1 | ✅ Done | Home page shows "Press ▶ Scan Network to discover your devices — takes about 30 seconds." when device count is zero after preload. Reverts naturally to device summary after first scan. |
| UX2 | ✅ Done | Audit complete. Added NpcapMissingBanner to IoT Behaviour tab (missing). Fixed Live Bandwidth Feature Guide entry: uses psutil (no Npcap needed). Rogue Bridge, Broadcast Storm, ARP Spoof Watch, DHCP Rogue Monitor, Bandwidth Monitor all already had banners. |

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

| ID | Status | Description |
|----|--------|-------------|
| N6 | ✅ Done | Analysis rail reordered: Broadcast Storm, Rogue Bridge (STP), IoT Behaviour, 802.11 Monitor, ARP Spoof Watch, Hop-by-Hop Trace, SNMP Device Info, Tools & Wake-on-LAN, Geolocation Map, Trend Forecasts — threat items grouped at top. |
| N7 | ✅ Done | "Plugin Modules" renamed to "Recon Plugins" everywhere — nav label, page header, feature guide, discover page. |

### HW — Hardware & Plugin Experience (continued)

| ID | Description |
|----|-------------|
| HW7 | **Per-instance IP override.** `HARDWARE_IP` in a plugin file is a compile-time constant. If two users have different gateway IPs, neither can use the same plugin file unchanged. The plugin card should let the user override the IP at import time; override is stored in settings alongside the password, and passed to the subprocess as an env var or argument. |

### UX — First-Time User Experience (continued)

| ID | Status | Description |
|----|--------|-------------|
| UX3 | — | "What to do next" suggestions quality. Not yet implemented. |
| UX4 | ✅ Done | Home page empty state shows "Try Ctrl+K to find anything on the network →" inline button; navigates to command palette. |

### XF — Cross-Feature Deep Links (continued)

| ID | Status | Description |
|----|--------|-------------|
| XF1 | ✅ Done | Right-click menu in Devices table shows "View in CVE Tracker →" only when CVE Tracker has entries matching that device IP. Navigates via `_nav_rail_go_to("CVE Tracker")`. |
| XF3 | — | Threat Intel link from Active Connections. Not yet implemented. |
| XF4 | ✅ Done | Network Grade D/F rows get a "Fix this →" QPushButton via `setCellWidget`, mapped to relevant pages (DNS & Stability, Security Overview, etc.). |
| XF5 | — | Security Overview aggregation. Not yet implemented. |
| XF6 | ✅ Done | Inventory Changes added to Monitor section of rail nav. Double-clicking a row emits `device_selected(mac)` → dashboard navigates to Devices and scrolls/selects the matching row via `_m1_highlight_mac`. |
| XF7 | ✅ Done | ModemSignalTile emits `clicked` when data is active; OverviewPage relays as `modem_tile_clicked`; dashboard navigates to the active modem plugin page (fallback: Hardware Hub). |

### ES — Empty States (continued)

| ID | Status | Description |
|----|--------|-------------|
| ES3 | ✅ Done | DHCP Lease page: inline "▶ Scan DHCP Leases" button in centered empty state widget replaces bare label. |
| ES4 | ✅ Done | Custom Triggers: QStackedWidget empty state (page 0) with description + "＋ Alert when host goes down →" pre-fills a Host Down template in the rule editor dialog. |
| ES5 | ✅ Done | Home Automation: QStackedWidget empty state (page 0) with "Configure MQTT / Home Assistant →" flat button that emits `navigate_to("MQTT / Home Assistant")`. |
| ES6 | ✅ Done | Trend Forecasts: empty state shows "Enable Network RTT logging in Log Hub to build forecast data" + "Open Network Logger →" button; `navigate_to` signal wired to dashboard. |
| ES7 | ✅ Done | IPv6 no-results status now reads "No IPv6 devices found — this is normal for most home networks" instead of looking like a scan failure. |
| ES8 | ✅ Done | Already compliant — Availability History had proper empty state; no change needed. |

### VC — Visual Consistency

| ID | Status | Description |
|----|--------|-------------|
| VC1 | ✅ Done | Group by node button shows muted hint text "Connect a router plugin to enable node grouping" when disabled. |
| VC3 | — | Loading state standardisation. Not yet implemented. |
| VC4 | ✅ Done | Modem page compat notice updated to reference Hardware Hub plugin system for other modems. Mesh Router page compat notice updated similarly (Eero, Orbi, UniFi, FritzBox). |

### MA — Monitoring & Alerts

| ID | Status | Description |
|----|--------|-------------|
| MA1 | ✅ Done | IoT anomaly alert table has an "Action" column with a flat "Investigate →" button per row, mapped by alert type: SYN_SCAN/NEW_PORT → Port Scan (TCP), NEW_DEST → Threat Intel, METADATA_PROBE → Cloud Metadata Probe, RATE_SPIKE → Live Bandwidth. |
| MA2 | ✅ Done | Notifications page footer has "Create custom alert →" flat button that navigates to Custom Triggers. |

### RP — Reports

| ID | Status | Description |
|----|--------|-------------|
| RP1 | ✅ Done | "ISP Report" renamed to "Network Health Report" with subtitle "Great for ISP support tickets" throughout nav, page header, and feature guide. |
| RP2 | ✅ Done | BaselinePage emits `drift_detected(str)` on compare when drift found; dashboard shows status-bar message + tray notification via `_tray_manager.show_notification`. |

---

## P3 — Polish (self-contained, no dependencies)

| ID | Status | Description |
|----|--------|-------------|
| D6 | ✅ Done | DiagnosisPage stores previous run's finding headlines. On re-run, shows "▲ N new · ▼ N resolved since last run" diff badge below verdict card. First run: badge hidden. |
| N8 | ✅ Done | Flyout panel footer shows "Right-click any page to pin it ★" hint on every section open — always visible, no clicks needed to discover. |
| VC2 | N/A | The Standard nav (QListWidget) that had emoji icons is permanently hidden (`setVisible(False)`) — the rail nav uses string-based icon names, not emoji. No visible inconsistency in the live UI. |
| HW6 | N/A | ZTE MC889 and TP-Link Deco pages are background data handlers — never shown in the nav. They coexist with the plugin system without conflict. No migration needed. |
| SK1 | ✅ Done | `_add_skeleton_rows()` inserts 8 muted "—" placeholder rows into the Devices table at scan start. Result handler calls `setRowCount(0)` which clears them naturally. |
| KBD | ✅ Done | Help panel gains a permanent `_help_shortcuts_lbl` showing Ctrl+K/R/E/Q, F5, Escape, Right-click, Ctrl+Shift+M. Panel always opens on click (no "go to Feature Guide" fallback); on pages without page-specific tips, tip bar reads "Keyboard Shortcuts ▾". |
| 802 | ✅ Done | Passive 802.11 monitor mode capture — WiFiMonitorPage + WiFiMonitorWorker. Interface selector, Start/Stop, live frame table (Time, Frame Type, Source MAC, SSID, Destination). Falls back silently via `unsupported` signal. Added to Analysis rail section, Feature Guide (Security group), and smoke test. |

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
