# NetSentinel Backlog

## Vision

NetSentinel exists to answer one question: "what is happening on my network right now?" It does this in three ways that no other free tool combines.

First, it replaces five separate CLI utilities with a single interface that speaks plain English — the de-facto tool anyone reaches for when their network is broken. Second, it works with whatever hardware you own, not just supported brands — an open plugin protocol lets any Python script become a first-class integration, and an AI assistant can write that script in ten minutes. Third, it shows you *why* something is happening, not just that it is — every detection event comes with an explanation of the underlying protocol and what you should do about it.

Everything on this backlog serves one of those three goals. If an item does not clearly serve one, it does not belong here.

---

## Priority 0 — Hardware Plugin Data Flow  ← build this next

The plugin import, validation, and test sandbox shipped in v1.9.8. This sprint completes the feature: data from a plugin flows into the rest of the app exactly like the built-in Deco and ZTE integrations. Until this is done the plugin system is a tutorial, not a feature.

**Validation plan before merging:** disable Deco credentials and ZTE modem login, then use only the in-app Integrate Hardware guide + an AI assistant to recreate both scripts from scratch. If the workflow produces working plugins that populate the Devices table and topology, the protocol is proven for any hardware.

---

### P0-A. PluginWorker — run plugin in background thread, emit structured result

**What:** A `PluginWorker(QThread)` that runs `subprocess.run([sys.executable, script_path, "--netsentinel"])` and parses stdout as JSON. The `--netsentinel` flag is detected by a shim injected at the bottom of the template — it calls `get_info()`, `get_status()`, and `get_clients()` and prints a single JSON object. This keeps the plugin's own `if __name__ == "__main__"` block intact for standalone testing.

**Output contract (stdout JSON):**
```json
{
  "info":    { "name": "...", "type": "...", "ip": "...", "firmware": "..." },
  "status":  { "wan_ip": "...", "uptime_sec": 3600, "download_mbps": 94.2, ... },
  "clients": [ { "ip": "...", "mac": "...", "hostname": "..." }, ... ]
}
```

**Signals:** `result(dict)`, `error(str)`

**Effort:** S

**Files:**
- `workers/plugin_worker.py` — new worker, mirrors structure of `workers/mesh_worker.py`
- `ui/pages/hardware_integration_page.py` — replace `_TestWorker` with `PluginWorker`; the existing Test button already shows output, now the result dict is also emitted upward

---

### P0-B. Plugin clients → Devices table

**What:** After a plugin worker result arrives, convert `clients` list into a dict keyed by normalised MAC, cache it as `self._plugin_enrichment` in dashboard.py, and pass it into `_apply_mesh_enrichment`. Client rows enriched by a plugin get a subtle source badge (e.g. "via GL.iNet") in the hostname column — same mechanic as the existing Deco name replacement, just a different label.

**Effort:** S

**Files:**
- `ui/dashboard.py` — `_on_plugin_result(data: dict)` handler; extend `_apply_mesh_enrichment` to handle both `_mesh_enrichment` and `_plugin_enrichment`
- `ui/pages/hardware_integration_page.py` — emit `plugin_result = pyqtSignal(dict)` from the page; wire to `_on_plugin_result` in dashboard

---

### P0-C. Plugin status → Overview hardware tile

**What:** `get_status()` returns `wan_ip`, `uptime_sec`, `download_mbps`, `upload_mbps`. Show these in a tile on the Overview page labelled with `HARDWARE_NAME` — same visual pattern as the modem signal tile. Grey/hidden when no plugin is active. Updates each time the worker runs.

**Effort:** S

**Files:**
- `ui/pages/overview_page.py` — add `update_plugin_status(data: dict)` method; tile is hidden by default and shown only when data arrives
- `ui/dashboard.py` — call `update_plugin_status` from `_on_plugin_result`

---

### P0-D. Topology diagram — plugin clients grouped under hardware node

**What:** When plugin clients are present, the topology renders a new node between the gateway and the client row labelled with `HARDWARE_NAME` (e.g. "GL.iNet AX1800"). Plugin clients attach to this node. Uses the existing three-tier mesh layout — the plugin node is treated as a single-satellite mesh unit with `role="plugin"`.

**Effort:** M

**Files:**
- `ui/topology_widget.py` — extend `_render_mesh` to accept plugin clients as a synthetic satellite node when `mesh_units` is empty but `plugin_enrichment` is present
- `ui/dashboard.py` — pass `plugin_enrichment` into topology `render()` call

---

### P0-E. Periodic refresh + auto-run on import

**What:** When a plugin is active, re-run `PluginWorker` every 5 minutes (configurable). Also run immediately on app start if a plugin is registered. This makes plugin data live, not just test-on-demand.

**Effort:** S

**Files:**
- `ui/dashboard.py` — `QTimer` started after first successful plugin run; same pattern as mesh auto-worker at line 8926

---

## Priority 1 — Clear explanations for every detection event

**"What just happened?"** — After every scan result, every BPDU detection, every CVE match, every alert, a collapsible panel at the bottom of the relevant page explains in plain English what the protocol is, why this result matters, and what to do about it. Collapsed by default so it does not obstruct experienced users.

This is not an educational feature — it is a usability feature. "BPDU detected" means nothing to 95% of users. "A device on your network is claiming to be the root bridge — this causes periodic 30-second disconnections" is actionable. Every confused home user benefits from this, not just students.

`ui/widgets/explainer_panel.py` already exists. This is wiring it to detection results on each page.

**Effort:** M — one page at a time, shippable incrementally.

---

## Priority 2 — ISP comparison (requires backend)

Anonymous opt-in only, zero PII. Submits: ISP name, country code, anonymised speed, latency, and uptime percentage once per day. Shows the user how their connection compares to the median for their ISP and country.

**Why it matters:** "Your latency is 42 ms" is not actionable. "Your latency is 42 ms — 38% worse than the median for your ISP in your country" is. Creates a re-engagement hook and produces data that benefits all users.

**Honest flag:** This is the only item on the backlog that requires server infrastructure. That makes it a different category of work — ongoing costs, API maintenance, privacy policy update. Do not start this until the plugin data flow is complete and there is a clear plan for the backend. Effort is L and that L is mostly the backend, not the UI.

**Files:**
- `modules/isp_telemetry.py` — new module, opt-in only, no passive collection fallback
- `ui/pages/speed_test_page.py` — opt-in toggle and comparison panel
- Backend endpoint — document the API contract before any code is written

---

## Priority 3 — Polish

Self-contained items, no dependencies between them.

- **Skeleton loading rows while scan workers run** — prevents layout jump when data arrives; placeholder rows styled in `TEXT_MUTED`, swapped out when the worker emits results.
- **"Abyss" WCAG AA high-contrast theme** — true black background, high-contrast text, no low-opacity elements. Accessibility requirement for some users.
- **Keyboard shortcut reference card in Help panel** — the shortcut list currently only appears in Settings.
- **Per-page documentation link** — small `?` on each page header linking to the relevant wiki section.
- **Passive 802.11 monitor mode capture** — puts a supported NIC into monitor mode via Npcap, reads raw 802.11 management/probe/beacon frames. Useful on networks with AP client isolation. Silently falls back to standard capture if unsupported. Power-user feature, not a default.

---

## Parking lot — revisit only if there is clear demand

- **CompTIA Network+ / CCNA curriculum alignment** — badges on each page showing which exam objective it covers; exportable study-session report. S effort but creates institutional positioning that may conflict with the hardware plugin angle. Only worth doing if educators ask for it directly.
