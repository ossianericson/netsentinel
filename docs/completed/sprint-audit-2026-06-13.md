# Sprint Audit — 2026-06-13

Audit of all commits from 2026-06-11 through 2026-06-13.
Purpose: verify that every claimed feature is actually wired end-to-end,
not just implemented in isolation.

---

## Method

Each commit was inspected by reading the actual signal/slot chain, property
names, and render call sites in the source — not by reading commit messages or
doc strings. The audit traces every claimed feature from user action → signal →
slot → module → render, checking that every link in the chain exists.

---

## Overall Verdict

**Sprints 1–6 topology, Sprint 5 Device Audit Trail, Sprint 6 Classification
Override, and all Service Heartbeat fixes are correctly wired.**

Two silent-failure gaps were found in the Interactive topology tab (Cytoscape).
Everything else is confirmed connected.

---

## Confirmed Working ✅

### Topology — Sprint 1: Node click → DeviceDrawer
- `NetworkMapPage.node_clicked pyqtSignal(str)` emitted from both Classic and
  Cytoscape (via `_TopoBridge.node_clicked_signal`).
- Connected in `Dashboard._build_topology_tab()` to `_on_topology_node_clicked`.
- Slot looks up the device MAC from `_m1_result["devices"]` by IP, calls
  `_topology_drawer.load(mac, store)` then `open_drawer()`.
- **Manual check:** run scan → click any node → DeviceDrawer should open.

### Topology — Sprint 2: Layout persistence, zoom, segment colours
- `load_layout(scan_id)` / `save_layout()` called in `NetworkMapPage.render()`
  and the Cytoscape `_render_web()` path.
- `scan_id` is a hash of sorted device IPs — if the device set changes, the
  scan_id changes and the persisted layout resets (by design).
- `segments` kwarg threaded through `scan_wiring._on_m1_result` →
  `_network_map_page.render()` → both Classic and Cytoscape paths.
- **Manual check:** drag a node, re-scan with same devices → position persists.

### Topology — Sprint 3: Live health overlays on edges
- `TopologyEdge` list built inside `scan_wiring._on_m1_result` from
  `MetricStore.query_device_state_history()` and `query_rtt_history()`.
- Passed as `edges=_topo_edges` to `_network_map_page.render()`.
- Requires Availability Monitor to have run — on fresh install all edges grey.
- **Manual check:** start Availability Monitor, wait for some pings, re-scan →
  edges should be green/amber/red.

### Topology — Sprint 4: Diff / "Show Changes" button
- After each scan, `build_snapshot` / `diff_snapshots` / `save_snapshot`
  called in `scan_wiring._on_m1_result`.
- `self._topo_diff` stored on Dashboard.
- `btn_diff.toggled` → `Dashboard._on_topo_diff_toggled` → re-renders with
  `diff=self._topo_diff` or `diff=None`.
- `page.btn_diff` and `page.diff_label` exposed as `@property` on
  `NetworkMapPage`; Dashboard accesses them without accessing private attrs.
- **Manual check:** scan, disconnect a device, scan again → "Show Changes"
  button should reveal removed node in red.

### Topology — Sprint 5: LLDP multi-hop discovery
- `_start_lldp_discovery()` called at the end of `_on_m1_result`
  (scan_wiring.py line 925).
- `LldpWorker` created with `iface` from `_net_info["interface"]`; only starts
  if interface name is non-empty.
- `result_ready` connected to `_on_lldp_result` → calls
  `_network_map_page.update_lldp_neighbors()`.
- Classic view (matplotlib): infrastructure nodes rendered as teal squares,
  leaf nodes as diamonds; admin hint text shown at bottom when
  `lldp_admin_needed=True`.
- **Conditional:** raw socket sniffing requires Windows administrator rights.
  Non-admin → silent empty result + admin hint in Classic tab.

### Topology — Sprint 6: Interactive Cytoscape.js tab
- `NetworkMapPage` constructed in `Dashboard._build_topology_tab()`.
- `QWebEngineView` initialised inside `NetworkMapPage.__init__`; any failure
  sets `self._web_available = False` and falls back to Classic-only.
- `AA_ShareOpenGLContexts` set before `QApplication` creation in `app.py`.
- **Conditional:** requires `PyQt6-WebEngine~=6.11` (in requirements.txt).
  If unavailable or if WebEngine crashes at init, the Interactive tab is blank
  — see Gap #2 below.

### Service Heartbeat — all four fixes (commit e9325ca)

| Fix | Signal / code path | Status |
|-----|-------------------|--------|
| Expand-row crash | `ExpandingTable._on_cell_clicked`: `setSortingEnabled(False)` before `insertRow()`; `clear_detail()` re-enables | ✅ |
| Wrong detail data after sort | `_build_service_detail` looks up by `host:port` from visible table items, not `self._rows[logical_row]` | ✅ |
| Remove not working | `_remove_service` → `_refresh()` → `_populate()` which filters against `_configured`; instant, no wait for worker | ✅ |
| Add delay | `_add_from_bar()` emits `check_now_requested` → wired in `app.py:638` to `svc_worker.check_now` | ✅ |
| Diagnose action | `diagnose_service pyqtSignal(str)` → wired in `tabs.py:101` and `tabs.py:491` to `_on_service_page_diagnose` | ✅ |

### Sprint 5 — Device Change Audit Trail
- `device_events` table added in schema v12 (MAC-keyed).
- Write call sites confirmed:
  - `device_tracker.py` → `first_seen`
  - `scan_wiring.py` → `ip_changed`, `hostname_changed`
  - `scan_enrichment.py` → `class_changed`
  - `availability_worker.py` → `went_offline`, `came_online`
  - `device_detail_pane.py` → `annotation_changed`
- DeviceDrawer: two tabs (Details / History); History renders coloured dot
  timeline from `get_device_events(mac)`.
- Timeline page: "Device Changes" filter chip backed by
  `get_all_device_events()`.
- Events only appear for activity **after** schema v12 was applied; older
  installs have empty history for existing devices.

### Sprint 6 — Classification Quality + Manual Override
- `device_classification_overrides` table in schema v13 (MAC PK).
- MetricStore: `set_classification_override()`, `clear_classification_override()`
  write methods; `get_classification_override()`,
  `get_all_classification_overrides()` read methods.
- Inventory table Type column: coloured prefix indicator
  (★ override · ● ≥70% · ◑ 30–70% · ○ <30%).
- Right-click → "Override Type…" opens `_TypeOverrideDialog` (QComboBox of all
  valid types from `get_all_device_types()`).
- Override guard in `scan_enrichment._apply_dhcp_fingerprints()` and
  `_on_passive_observation()` — user overrides survive re-runs.
- DeviceDrawer Classification section: "★ Override" badge visible when set;
  "Clear Override" button wired.

---

## Gaps Found ❌

### Gap 1: LLDP admin hint missing from Cytoscape Interactive tab

**Expected:** when the user is on the Interactive tab and LLDP requires admin,
the same "Run as administrator" hint should appear.

**Actual:** the `lldp_admin_needed` flag is consumed only by the Classic
matplotlib view (`topology_widget.py:199`). The `topology_cytoscape.py`
module does not receive or render this flag. If the user switches to the
Interactive tab, there is no visible explanation for why no infrastructure
nodes appear.

**File to fix:** `modules/topology_cytoscape.py` and `ui/pages/network_map_page.py`

**Fix:** Pass `lldp_admin_needed` into `build_topology_html()` and inject a
visible banner or subtitle into the generated HTML when the flag is `True`.

---

### Gap 2: WebEngine init failure is completely silent in Interactive tab

**Expected:** if `QWebEngineView` fails to initialise (missing PyQtWebEngine,
wrong Qt version, driver crash), the user sees a clear message explaining why
the Interactive tab is blank.

**Actual:** `NetworkMapPage.__init__` catches `except Exception` on the
WebEngine import and sets `self._web_available = False`, but the `_inner_tab`
still shows the "⬡ Interactive" tab — it's just blank with no text.

**File to fix:** `ui/pages/network_map_page.py`

**Fix:** When `self._web_available = False`, replace the interactive tab's
placeholder widget with a `QLabel` that says "Interactive view requires
PyQtWebEngine (pip install PyQt6-WebEngine). Showing Classic view." and
auto-select the Classic tab.

---

## Data-Flow Summary (for reference)

```
scan completes
  └─ scan_wiring._on_m1_result()
       ├─ build TopologyEdge list from MetricStore (Sprint 3)
       ├─ build/diff TopologySnapshot (Sprint 4)
       ├─ _network_map_page.render(devices, segments, edges, diff, ...)
       └─ _start_lldp_discovery()
            └─ LldpWorker.start()
                 └─ result_ready → _on_lldp_result()
                       └─ _network_map_page.update_lldp_neighbors()

mesh enrichment completes (15 s timer)
  └─ scan_enrichment._apply_mesh_enrichment()
       └─ _network_map_page.render(merged _last_render_kwargs)
            ← preserves segments/edges/lldp/diff from initial render

Service Heartbeat add
  └─ _add_from_bar()
       ├─ _add_service()
       └─ emit check_now_requested
            └─ app.py:638 → svc_worker.check_now()
                 └─ check_done → on_check_done() → _refresh() → _populate()
```

---

## Manual Verification Checklist

Use this to walk through the app after any change.

### Network Map
- [ ] Run scan → navigate to Network Map → Classic tab renders with device nodes
- [ ] Click a node → DeviceDrawer opens showing that device's data
- [ ] Interactive tab is not blank (or shows the "requires PyQtWebEngine" message)
- [ ] Click a node in Interactive tab → DeviceDrawer opens
- [ ] Scan twice with same devices → segment colours and edge colours appear
- [ ] Scan with a device removed → "Show Changes" toggle reveals the missing node
- [ ] (Admin only) LLDP: infrastructure square nodes appear in Classic tab

### Service Heartbeat
- [ ] Expand a row → detail panel opens without crash
- [ ] Sort by Status column → click a row → detail shows data for THAT service
- [ ] Click Remove in detail panel → row disappears immediately
- [ ] Add a new service → status updates within ~5 seconds (not 60)
- [ ] Right-click a service → "Diagnose →" opens Service Diagnostics pre-filled
- [ ] Submit empty host field → red border flash (no silent fail)

### Device Audit & Classification
- [ ] Devices table → Type column shows ★/●/◑/○ prefix
- [ ] Right-click device → "Override Type…" opens with dropdown
- [ ] Set override → re-scan → type does NOT revert
- [ ] DeviceDrawer → History tab shows events (if any monitoring has run)
- [ ] Timeline page → "Device Changes" chip filters to device events

---

*Audit performed 2026-06-13. Next session should fix the two gaps above.*
