# NetSentinel Hardware Plugin System — Robustness Hardening Plan

**Goal:** The plugin system must be structurally correct for every plugin, every time,
regardless of how the plugin was added, how many plugins are running simultaneously,
or what order events fire in.  Every failure found in this session revealed a pattern
flaw — not a one-off bug — so every fix below targets the pattern.

**Context:** The previous plan (`PLUGIN_ECOSYSTEM_PLAN.md`) delivered features.
This plan delivers robustness.  All items in the previous plan are shipped (v1.9.48).
The four bug classes found in this session — env-var pollution, divergent code paths,
timing-dependent enrichment, and UI not reflecting registry state — are the seed for
every item below.

---

## Root-Cause Audit (session 2026-05-29)

### Bug class 1 — Global env-var used for per-plugin IP passing
`NETSENTINEL_PLUGIN_IP` is a single `os.environ` key shared by every plugin and every
thread.  When the ZTE modem poller sets it to `192.168.254.1`, the Deco connection
tester reads it and tries to authenticate against the modem.  The tester also had no
`finally` block, so a test failure left the wrong IP in the environment permanently.

### Bug class 2 — Two registration code paths with different behaviour
`_on_browse` (manual `.py` import) and `_import_bundled` (bundled / community) are
separate functions that share almost no code.  `_on_browse` was missing: credential
dialog, AppData copy, and instance-registry entry.  Any future feature added to one
path silently fails for users of the other path.

### Bug class 3 — UI not reactive to plugin registry changes
`_on_plugin_page_added` appended to `_nav_sections["Extend"]["entries"]` but never
called `load_section` on the flyout widget.  The flyout only reflected the change the
next time the user clicked the Extend rail button.  Same problem on remove.

### Bug class 4 — Enrichment timing depends on race between scan and poll
Plugin poll results arrive up to 120 s after a scan completes.  `_apply_mesh_enrichment`
returns immediately when `_m1_result` is None (no scan yet), so early polls are silently
discarded.  The `_plugin_enrichments` dict was also keyed inconsistently (file path at
startup, `hw_name` at poll time), creating duplicate entries.

---

## P0 — Unified Registration Pipeline

### P0-1  Single `_register_plugin` function replaces both code paths
Both `_on_browse` and `_import_bundled` must funnel through one function:

```
_register_plugin(path, source: "browse" | "bundled" | "community" | "nspkg")
```

Steps (always in this order, regardless of source):
1. Validate script (`_validate_script`)
2. Check unsigned warning if not bundled
3. Check and install PYPI deps (`PipInstallDialog`)
4. Copy to AppData stable path
5. Show credential dialog → live test → returns `(accepted, confirmed_ip)`
6. Write instance registry entry using `confirmed_ip` (not meta default)
7. Rebuild hub card
8. Start poll worker
9. Emit `plugin_page_added` → nav updates

This eliminates the category of "feature works for bundled plugins but not for manually
added ones" forever.

### P0-2  `_show_credential_dialog` returns `(bool, str)` — confirmed IP
Current signature: `_show_credential_dialog(...) -> bool`
New signature: `_show_credential_dialog(...) -> tuple[bool, str]`
The second value is the IP the user actually typed in the dialog (may differ from the
meta default).  The caller uses this confirmed IP for both the instance registry entry
and the keyring key.  This closes the gap where the user changes the IP in the dialog
but the plugin is registered at the original meta IP.

### P0-3  Deprecate path-based registry (`_save_paths` / `_load_paths`)
The path-list system predates multi-instance support.  All paths go through
`_load_instances` / `_save_instances` now.  Steps:
- On startup, migrate any `hardware/paths` QSettings entries to the instance registry
  (one instance per path, `inst_ip` from meta default)
- After migration, delete the `hardware/paths` key
- Remove `_save_paths`, `_load_paths`, `_start_poll_worker(path)` (kept only for
  migration shim, then removed)
- `tests/test_registration_pipeline.py` verifies that browse, bundled, and community
  sources all produce identical instance-registry entries

---

## P1 — Eliminate `NETSENTINEL_PLUGIN_IP` Global State

### P1-1  Replace env var with direct module-attribute injection  ✅ v1.9.50
Instead of setting `os.environ["NETSENTINEL_PLUGIN_IP"]`, the worker injects the IP
directly into the freshly-loaded module before calling any plugin function:

```python
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod._NETSENTINEL_INSTANCE_IP = self._instance_ip   # injected, not env
mod._NETSENTINEL_INSTANCE_ID = self._instance_id
```

Plugin credential helpers check `globals().get("_NETSENTINEL_INSTANCE_IP")` before
falling back to `HARDWARE_IP`.  **Note:** `globals()` is the correct mechanism —
`sys.modules[__name__]` fails because modules loaded via `module_from_spec` are not
automatically registered in `sys.modules`.  No env var involved.

This is thread-safe: each `exec_module` produces an independent module object with its
own namespace.

### P1-2  `_PluginConnectionTester` uses the same injection  ✅ v1.9.50
The tester already loads a fresh module per test.  After `exec_module`, inject
`mod._NETSENTINEL_INSTANCE_IP = self._ip` before calling `get_info()` / `get_status()`.
Remove the `os.environ` set entirely (the `finally` guard added in this session remains
as a safety net until all bundled plugins are updated to check module-attribute first).

### P1-3  Update all bundled plugins to read `_NETSENTINEL_INSTANCE_IP`  ✅ v1.9.50
`deco_plugin.py`, `zte_plugin.py`, and any future bundled plugins update
`_load_credentials()` to check module attribute before env var before `HARDWARE_IP`:

```python
def _load_credentials():
    _ip = (globals().get("_NETSENTINEL_INSTANCE_IP")
           or os.environ.get("NETSENTINEL_PLUGIN_IP")
           or HARDWARE_IP)
    _iid = globals().get("_NETSENTINEL_INSTANCE_ID") or ""
    ...
```

Backwards-compatible: plugins that haven't been updated still work via env var.

### P1-4  `tests/test_env_var_isolation.py`  ✅ v1.9.50
- Verifies two `_PluginConnectionTester` instances running concurrently do not
  interfere with each other's IP
- Verifies `NETSENTINEL_PLUGIN_IP` is restored to its pre-test value after success
- Verifies `NETSENTINEL_PLUGIN_IP` is restored after failure / exception
- Verifies module-attribute injection is preferred over env var when both are set

---

## P2 — Event-Driven Device Enrichment

### P2-1  Decouple enrichment from scan timing
`_apply_mesh_enrichment` currently returns early when `_m1_result` is None.  This
silently discards plugin data that arrives before the first scan.

New model: plugin poll results are always stored in `_plugin_enrichments` regardless
of scan state.  When a scan completes (`_on_m1_result`), enrichment is applied
immediately using whatever plugin data is already cached.  When plugin data arrives
after a scan, enrichment is applied immediately using the existing `_m1_result`.

Neither side waits for the other.  The only coordination needed is that
`_apply_mesh_enrichment` is called from both sides.  This is already true — the
remaining issue is the early-return guard.

### P2-2  Consistent `_plugin_enrichments` keying
All writes to `_plugin_enrichments` use the instance ID (stable, unique, does not
change between sessions) as the key:

```python
self._plugin_enrichments[inst_id] = {norm_mac: client_dict, ...}
```

Startup pre-population, `_on_hardware_plugin_result`, and the topology rebuild all
use instance ID.  The duplicate-key bug (path at startup, hw_name at poll) is
structurally impossible when the key is always the instance ID.

`PluginPollingWorker` already emits `_instance_id`.  Change `_on_hardware_plugin_result`
to use `data["_instance_id"]` as the key instead of `data.get("_path", hw_name)`.

### P2-3  Topology re-render on every plugin data update
`_on_hardware_plugin_result` for router/AP/mesh plugins currently calls
`_apply_mesh_enrichment` (which updates the table) but does not re-render the topology
widget.  Add a topology refresh at the end of the router/AP branch — same call as in
`_on_m1_result` but using the existing device list.

### P2-4  `tests/test_enrichment_timing.py`
Four scenarios tested:
1. Plugin poll arrives before first scan → enrichment cached; applied when scan completes
2. Plugin poll arrives after scan → enrichment applied immediately
3. Two plugins both have data for the same MAC → later poll wins (stable merge order)
4. Plugin removed mid-session → its enrichment entries purged from `_plugin_enrichments`

---

## P3 — Reactive Navigation & UI

### P3-1  Flyout reload is the responsibility of `_on_plugin_page_added` / `_on_plugin_page_removed`  ✅ v1.9.50
(Implemented in this session.)  Formalise as a rule: any mutation of `_nav_sections`
entries **must** be followed by a `load_section` call if the affected section is
currently open, and an `open()` call if the section should become visible.
Add a helper `_reload_section(name: str, force_open: bool = False)` to encapsulate
this pattern so future code cannot forget it.

### P3-2  Auto-navigate to the new plugin's device page on successful add  ✅ v1.9.50
After `plugin_page_added` fires and the nav item is created, navigate the stack to the
new `PluginDevicePage`.  This confirms to the user that the add succeeded and shows live
status immediately.  Use the existing `_nav_rail_go_to(label)` — no new machinery.

### P3-3  Command palette updated synchronously on plugin add/remove
`_on_plugin_page_added` must also refresh the command palette's action list.
Currently `_nav_label_to_widget` is updated (used by the palette) but the palette
widget itself caches entries at build time.  Add a `refresh()` call on the palette.

### P3-4  Plugin page label survives display-name rename
If the user renames a plugin instance from "TP-Link Deco XE75" to "Office Mesh",
the nav item label, breadcrumb, command palette entry, and `_plugin_pages` key must
all update atomically.  Add `plugin_renamed = pyqtSignal(str, str, str)` (path, old,
new) and a `_on_plugin_page_renamed` handler.

---

## P4 — Credential Robustness

### P4-1  "Update Credentials" action on each HubCard  ✅ v1.9.50
When a plugin card is in error state with an `AUTH:` prefix, show a "Re-enter
Password" button (not just text).  Clicking it opens `_show_credential_dialog` with
the current instance IP pre-filled.  On success, restarts the poll worker.
This eliminates the need to delete and re-add a plugin just because a password changed.

### P4-2  Per-instance keyring namespace  ✅ v1.9.50
Current keyring keys are inconsistent: `NetSentinel/mesh`, `NetSentinel/hardware`,
`NetSentinel/hardware/<ip>`.  New convention:

```
keyring.set_password("NetSentinel/plugin", instance_id, password)
```

`_load_credentials()` checks this namespace first, then falls back to the legacy
namespaces for backwards compatibility.  The credential dialog always writes to the
new namespace.  This means two instances of the same plugin type at different IPs
have completely independent credentials.

### P4-3  Credential pre-fill on Retry
When the user clicks Retry on a failed card (auth error), the credential dialog opens
with both the IP and an empty password field (never pre-fill password).  The current
IP from the instance registry is shown.

### P4-4  `tests/test_credential_robustness.py`
- `_show_credential_dialog` returns the IP actually entered, not the default
- Keyring write uses confirmed IP, not meta IP
- Multi-instance: two instances at different IPs have independent keyring entries
- "Update Credentials" re-registers the credential without touching the instance entry
- Backwards-compat: legacy `NetSentinel/hardware/<ip>` is still read on first lookup

---

## P5 — Plugin Isolation & Thread Safety

### P5-1  Concurrent poll guard per instance
If a poll cycle takes longer than the interval (e.g. a slow device), a new cycle must
not start while the previous one is still running.  `PluginPollingWorker` tracks whether
a poll is in progress and skips a cycle if so, logging "Previous poll still running —
skipping cycle".

### P5-2  Lock `_plugin_enrichments` mutations
`_plugin_enrichments` is written from worker threads (via Qt signal, which is queued to
the main thread) and read from the main thread.  Because Qt queued signals already
serialize onto the main thread, this is currently safe — but only by convention.
Add an explicit assertion (`assert QThread.currentThread() is QApplication.instance().thread()`)
at every write site so future code cannot accidentally write from a background thread.

### P5-3  Module namespace isolation between instances
Each call to `importlib.util.module_from_spec` creates a fresh namespace.  Verify that
module-level globals in the plugin (e.g. a cached `_client` object) do not persist
between poll cycles by confirming the spec is re-loaded each time.  Add a test that
modifies a module-level variable in one poll cycle and confirms it is reset in the next.

### P5-4  `tests/test_plugin_isolation.py`
- Two `PluginPollingWorker` instances for the same plugin file run concurrently;
  verify their module namespaces are independent
- Concurrent poll guard: if `trigger_now()` is called while poll is in progress,
  the second poll does not start until the first finishes
- Stale module cache: verify module-level state does not bleed between poll cycles

---

## P6 — Resilience & Recovery

### P6-1  Exponential backoff on repeated poll errors
Instead of polling every 60 s regardless of error state, apply backoff:
- 1 error: next poll at normal interval
- 3 consecutive errors: 2× interval
- 6 consecutive errors: 4× interval (capped at 300 s)
- Circuit breaker (10 errors): pause polling; "Retry" button resets counter

The current circuit breaker trips hard at 10 errors with no recovery path other than
re-enabling manually.  Backoff reduces noise on a temporarily unreachable device while
the circuit breaker still protects persistently broken plugins.

### P6-2  Stale file detection on every poll cycle
At the start of `_run_once`, check `Path(self._path).exists()`.  This is already done
(returns early with an error emit).  The missing piece: the error is emitted as a
generic string, not a structured prefix.  Change to `FILE: plugin file not found at
{path}` so `_classify_error` can surface "Plugin file was moved or deleted — re-import
it" with a direct "Re-import" button on the card.

### P6-3  AUTH error → credential prompt, not circuit-breaker
When `_classify_error` identifies an `AUTH:` prefix, the card should show the
"Re-enter Password" button (P4-1) immediately and reset the consecutive-error counter
to zero.  An auth failure is not a transient error — retrying with the wrong password
every 60 s is pointless and should not count toward the circuit breaker.

### P6-4  Plugin file watcher
Use `QFileSystemWatcher` to watch each registered plugin file.  If the file changes on
disk (user edits it), offer a "Reload plugin" toast rather than waiting for the next
poll cycle to discover the change.  If the file is deleted, immediately set the card to
`FILE:` error state.

### P6-5  `tests/test_plugin_resilience.py`
- Backoff: verify interval doubles after 3 errors, caps at 300 s
- Recovery: verify backoff resets to base interval after a successful poll
- AUTH errors do not count toward circuit breaker
- File deletion triggers `FILE:` error without waiting for next poll cycle

---

## P7 — Integration Test Coverage for Discovered Gaps

All four bug classes found in this session currently have zero regression tests.
These tests prevent the same class from recurring.

### P7-1  `tests/test_env_var_isolation.py`  (covers Bug class 1)
Already described in P1-4.

### P7-2  `tests/test_registration_pipeline.py`  (covers Bug class 2)
- Mocking `QFileDialog`, `_show_credential_dialog`, and `_import_bundled` internals,
  verify that a script added via browse produces the same instance-registry entry as
  one added via bundled path
- Verify that cancelling the credential dialog during browse does NOT write to QSettings
- Verify that a script without `CREDENTIAL_LABEL` skips the dialog silently

### P7-3  `tests/test_flyout_refresh.py`  (covers Bug class 3)
- After `_on_plugin_page_added` fires, the flyout's item list contains the new label
  without any user interaction
- After `_on_plugin_page_removed` fires, the flyout's item list no longer contains
  the removed label
- After add, `_nav_open_section` is set to `"Extend"`

### P7-4  `tests/test_enrichment_timing.py`  (covers Bug class 4)
Already described in P2-4.

### P7-5  Regression test for IP keying consistency
- `_plugin_enrichments` uses instance ID as key after a poll result
- `_plugin_enrichments` uses instance ID as key after startup pre-population
- `_apply_mesh_enrichment` sees exactly one entry per instance (no duplicates)

---

## Implementation Order

| # | Item | Complexity | Version |
|---|---|---|---|
| 1 | P0-2: `_show_credential_dialog` returns `(bool, str)` | S | v1.9.49 |
| 2 | P0-1: `_register_plugin` unified function | M | v1.9.49 |
| 3 | P0-3: deprecate path-based registry + migration | S | v1.9.49 |
| 4 | P2-2: instance-ID keying for `_plugin_enrichments` | S | v1.9.49 |
| 5 | P2-1: remove early-return guard from `_apply_mesh_enrichment` | S | v1.9.49 |
| 6 | P7-2: `test_registration_pipeline.py` | S | v1.9.49 |
| 7 | P7-3: `test_flyout_refresh.py` | S | v1.9.49 |
| 8 | P7-4: `test_enrichment_timing.py` | S | v1.9.49 |
| 9 | P1-1: module-attribute injection replaces env var | M | ✅ v1.9.50 |
| 10 | P1-2: tester uses attribute injection | S | ✅ v1.9.50 |
| 11 | P1-3: update bundled plugins to read module attribute | S | ✅ v1.9.50 |
| 12 | P1-4: `test_env_var_isolation.py` | S | ✅ v1.9.50 |
| 13 | P4-2: per-instance keyring namespace | S | ✅ v1.9.50 |
| 14 | P4-1: "Update Credentials" on AUTH-error cards | M | ✅ v1.9.50 |
| 15 | P3-1: `_reload_section` helper | S | ✅ v1.9.50 |
| 16 | P3-2: auto-navigate to new plugin page on add | S | ✅ v1.9.50 |
| 17 | P6-1: exponential backoff | M | ✅ v1.9.51 |
| 18 | P6-3: AUTH errors exempt from circuit breaker | S | ✅ v1.9.51 |
| 19 | P6-2: structured `FILE:` error prefix | S | ✅ v1.9.51 |
| 20 | P5-1: concurrent poll guard | S | ✅ v1.9.51 |
| 21 | P6-4: `QFileSystemWatcher` for plugin files | M | ✅ v1.9.51 |
| 22 | P7-5: regression tests for IP keying | S | ✅ v1.9.51 |
| 23 | P2-3: topology re-render on plugin data update | S | ✅ v1.9.52 (in `_apply_mesh_enrichment`) |
| 24 | P3-3: command palette refresh on add/remove | S | ✅ v1.9.52 (palette rebuilt on every open) |
| 25 | P3-4: display-name rename propagation | M | ✅ v1.9.52 |
| 26 | P4-3: credential pre-fill on Retry | S | ✅ v1.9.52 (via P4-1: `_on_update_credentials`) |
| 27 | P5-3: module namespace isolation verification | S | ✅ v1.9.52 (`test_plugin_isolation.py`) |
| 28 | P4-4: `test_credential_robustness.py` | M | ✅ v1.9.52 |
| 29 | P5-4: `test_plugin_isolation.py` | M | ✅ v1.9.52 |
| 30 | P6-5: `test_plugin_resilience.py` | M | ✅ v1.9.52 |

S = small (half-day), M = medium (full day).

---

## Design Principles Extracted From This Session

These are the rules that would have prevented every bug found today.  They should be
added to `CLAUDE.md` as blocking rules before the next sprint begins.

1. **No shared mutable state between plugin instances.**  IP, credentials, and module
   state must be scoped to the instance, never to the process.  `os.environ` is
   process-scoped — do not use it for per-plugin data.

2. **One registration code path.**  If adding a plugin can happen via N entry points,
   every invariant must be enforced in a shared function, not duplicated across all N.

3. **UI reflects registry state synchronously.**  Any mutation to `_nav_sections` must
   be followed immediately by a flyout reload.  "The user will see it next time they
   open the section" is not acceptable.

4. **Enrichment is not a one-shot event.**  Plugin data and scan data arrive
   independently.  Neither waits for the other.  Store and merge whenever either
   arrives.

---

*Plan created 2026-05-29.  Addresses bug classes found in session post-v1.9.48.*
