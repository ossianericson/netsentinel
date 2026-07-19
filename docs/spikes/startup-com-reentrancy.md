# Spike: Startup-phase Windows fatal exception 0x8001010d (RULE-SPIKE1/2)

## Windows API / constraint involved

`RPC_E_CANTCALLOUT_ININPUTSYNCCALL` (HRESULT `0x8001010D`) — COM refuses an
outgoing call while the STA thread is already inside a synchronous
input-related call (a `SendMessage`-class call from the window-message /
input subsystem). `faulthandler.enable()` (`app.py:818`) catches it as a raw
SEH fault and dumps a full thread stack to `netsentinel_crash.log`, but the
fault is not a Python exception — no `try/except` anywhere in the call chain
can catch it, and it does not reach `netsentinel_exceptions.log`. The process
is simply gone.

This is not a new fault class for this codebase — see the "Known prior
occurrences" section below — but this spike documents a **third, distinct
site**: startup, before the main window is ever shown.

## Evidence (2026-07-08 soak run)

`.\test.ps1 8h -Soak` (mild-chaos lap, seed 1) — full artifacts in
`Documents\NetSentinel\test_output\run_20260708_175518\soak_01_mild\`.

Timeline from `monkey.log`:
- `18:22:58` chaos actions start (PID 22336)
- `18:24:33` window gone before iteration 1 — process died
- `18:24:35`–`18:27:24` restart #1 (PID 32176) — hung again within 2s of connecting
- `18:27:25`–`18:28:33` restart #2 (PID 11724) — **never got a window at all**;
  timed out after 60s. Harness gave up after 3 failed attempts, having burned
  12m27s of a planned 54m30s phase (96% of budget lost to this one failure).
- The very next phase (`soak_01_moderate`, PID 3856) also timed out waiting
  for a window at `18:29:40` — same failure mode on a fresh launch.

`netsentinel_crash.log` (last entry, timestamp-correlated to the `18:28:33`
give-up):

```
Current thread 0x00002c6c (most recent call first):
  File "C:\Code\netsentinel\app.py", line 1049 in _splash_msg
  File "C:\Code\netsentinel\app.py", line 1447 in main
  File "C:\Code\netsentinel\app.py", line 1620 in <module>
Windows fatal exception: code 0x8001010d
```

`app.py:1447` is `_splash_msg("Restoring last scan…")` — the crash lands
inside that call's `app.processEvents()` (line 1050-1051). By this point in
`main()`:
- `Dashboard(...)` has been fully constructed (`app.py:1322`), which
  constructs `SystemTrayManager(self)` (`ui/dashboard.py:226`), whose
  `__init__` calls `self._tray.show()` (`ui/system_tray.py:200`) — a
  `QSystemTrayIcon.show()`, backed by the Win32 `Shell_NotifyIcon` COM/shell
  call.
- A dozen-plus background `QThread` workers are already started and wired
  (`avail_worker`, `cert_worker`, `svc_worker`, posture workers, etc. —
  `app.py:1176`–`1367`), several doing network I/O concurrently.
- `window.show()` has **not** yet run (`app.py:1458`) — the crash happens
  before the main window is shown.

## Known prior occurrences of the same fault code

1. `docs/spikes/window-snap-subclass.md` — `ui/header.py`'s native
   `WM_NCHITTEST` subclass callback (`_proc`) hit the identical
   `0x8001010d` when Windows' Snap Layout hover-preview fired on the main
   thread while a background `QThread` was doing network I/O (Threat Intel
   "Update Feeds"). **Ruled out as today's cause** — that code path is gated
   behind `experimental/snap_layout_hover` (default `False`), and the
   registry on this machine confirms it is still `false`
   (`HKCU\Software\NetSentinel\NetSentinel\experimental`).
2. `app.py:1164`–`1172` — a standing workaround pre-warms `tplinkrouterc6u`
   (Windows COM-based crypto) on the main thread specifically because
   importing it from a background `QThread` raises this same code.

Both prior occurrences share the same shape: **a main-thread call that calls
out to COM/native Win32, happening concurrently with active background
`QThread` I/O.** Today's crash fits that shape too (tray icon `Shell_NotifyIcon`
call-out + a dozen already-running worker threads), just at a new call site
(startup, not a later page navigation).

## PyQt6-specific constraints

- `QSystemTrayIcon.show()` is a thin wrapper over `Shell_NotifyIcon`, a
  COM/shell call. Constructing it while other threads hold the STA busy is
  exactly the reentrancy shape COM disallows.
- `_splash_msg()`'s `app.processEvents()` (`app.py:1038-1051`) is called five
  times during startup (`app.py:1105, 1174, 1320, 1447, 1455`), each one a
  **nested** event-loop pump inside `main()`, which is itself already running
  inside the outer `app.exec()`-equivalent startup sequence. Nested pumps are
  a well-documented trigger for COM reentrancy edge cases on Windows.
- pywinauto's UI Automation backend is itself COM-based. The monkey harness
  begins polling the process's windows (`Checking for startup overlays…`,
  `tools/monkey_test.py:1143`) as soon as a window is connectable — which
  can overlap with the app's own startup sequence for several minutes on a
  loaded test machine, giving many opportunities for the two COM actors (app
  startup, UIA client) to collide.

## Known incompatibility with PyInstaller frozen exe

Not evaluated in this spike — reproduction was from source
(`python C:\Code\netsentinel\app.py`), matching how the monkey harness always
launches it. No reason to expect the frozen build behaves differently since
the fault is in COM/Shell interaction, not PyInstaller's import machinery,
but this should be re-checked if the fix is validated only from source.

## Proof-of-concept result: root cause narrowed, fix not yet implemented

Reproduced via the pasted chaos-test artifacts (not re-run live — per
RULE-CHAOS1 the agent does not launch monkey sessions itself). The exact
call-out site (tray icon vs. some other COM touch during
`window._restore_cached_scan()` at `app.py:1449`) is not 100% pinned down —
`_restore_cached_scan()` runs network-map rendering and cache population
which hasn't been individually audited for COM/native calls. The tray-icon
`Shell_NotifyIcon` call is the strongest single candidate because it is a
confirmed COM call-out that happens earlier in the same `main()` call chain,
matching the exact mechanism (COM call-out + concurrent background
`QThread` I/O) already proven to cause this fault code in
`window-snap-subclass.md`.

## Secondary finding: orphaned daemon subprocess

`workers/scan_worker.py`'s Scapy/Npcap process-isolation workers
(`_stp_scan_process_target`, `_storm_scan_process_target`) run as
`multiprocessing.Process(daemon=True)`. Daemon-process cleanup only happens
on a *graceful* Python interpreter exit. The monkey harness's restart logic
hard-kills stale `python.exe` PIDs (`[setup] Killed stale process`) — if
either scan-isolation subprocess is active at that moment, it is orphaned
instead of cleaned up. Confirmed live during this investigation: a
`multiprocessing.spawn_main` worker (parent PID no longer existing) was
still running 2h16m after its parent died, from this exact run. Not
established as the *cause* of the window-timeout failures, but a real
resource leak produced by the same failure sequence.

## Verdict

**Root cause class confirmed (COM call-out + concurrent background QThread
I/O during startup), exact call-out site not proven with certainty.**

### Fix attempt 1 — CONFIRMED INEFFECTIVE (2026-07-08, second repro run)

Shipped as: `QTimer.singleShot(0, self._tray.show)` in
`SystemTrayManager.setup()` (deferring the `Shell_NotifyIcon` call) +
`QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents` on `_splash_msg()`'s
`processEvents()` calls in `app.py`.

A fresh chaos run (`run_20260708_195156`) hit the **exact same fault at the
exact same call site, twice**, immediately after this fix shipped.

Why it failed: `singleShot(0, ...)` only defers to the *next Qt event-loop
turn* — and `_splash_msg()`'s own `processEvents()` call **is** that next
turn (nothing runs between `Dashboard.__init__` returning and that splash
call pumps events). The deferred tray-icon `.show()` almost certainly fired
*during the very same pump it was meant to avoid*.

The `ExcludeUserInputEvents` half also targeted the wrong mechanism: the
second repro run's monkey harness never even connected to the window (zero
synthetic UIA input was ever delivered), yet the fault fired twice anyway.
Whatever the real call-out trigger is, it is not synthetic input arriving
during the pump. Reverted in the same change that shipped Fix 2, rather than
leaving in place a comment asserting a disproven theory.

Also newly confirmed: **the fault is not immediately fatal to the process.**
In the second repro run the app survived both fault occurrences and ran
successfully, unattended, for 14+ minutes afterward. The original run's
"process death" was very likely the monkey harness's own health-monitor
treating a multi-second COM-retry stall as a hang and hard-`taskkill`-ing
it — not the fault itself killing the process.

### Fix 2 — implemented 2026-07-08

Moved the tray icon's actual `.show()` call out of `setup()` entirely (no
`singleShot` — it doesn't help) and into `AppHeaderMixin.showEvent()`
(`ui/header.py`), guarded by a one-shot flag following the same pattern
already used there for `_install_snap_subclass()` and the welcome overlay.
`showEvent()` only fires after the real `window.show()` runs in `main()` —
well past every `_splash_msg` pump, so the COM call-out and the nested
event-loop pumps can no longer overlap.

`SystemTrayManager.setup()` still constructs `self._tray = QSystemTrayIcon(...)`
synchronously (unchanged) so `is_available()` (`self._tray is not None`)
keeps returning `True` immediately for the 3 gating checks in `app.py` that
run before `window.show()` (health_worker → tray connect, quiet notifier,
morning briefing). Only the `.show()` call itself moved, via the new
`SystemTrayManager.show_tray_icon()` method.

Verified: `ruff check` clean, `tests/test_system_tray.py` passes,
`tools/debug_launch.py` shows `window.show() called OK`. **Not yet verified
against the actual fault** — that requires a live chaos/monkey run (RULE-CHAOS1,
user-initiated only) to confirm the fault stops reproducing.

### Fix 2 — CONFIRMED INEFFECTIVE (2026-07-08, live soak run_20260708_210704)

`soak_01_mild` (launched 21:27:35) timed out waiting for a window at 21:28:58
(`monkey.log`). `netsentinel_crash.log`'s mtime (21:27:41) shows exactly one
new fault landed during this run — everything else in that file is weeks of
accumulated history from other runs (the log is append-only and never
rotated; always check mtime against the run's own timestamps before trusting
a `grep -c` count). The new entry, at the tail of the file:

```
Current thread 0x00005f9c (most recent call first):
  File "C:\Code\netsentinel\app.py", line 1049 in _splash_msg
  File "C:\Code\netsentinel\app.py", line 1447 in main
  File "C:\Code\netsentinel\app.py", line 1620 in <module>
```

Identical call chain to the original repro. Worse this time: no further
crash-log entries were written for the rest of the run, but
`netsentinel_exceptions.log`/`tracemalloc_snapshots.log` kept growing for
~53 more minutes (background `QThread` workers stayed alive), and the window
never appeared — the run only ended when the harness sent a
`KeyboardInterrupt` at 22:21:26 to force it down. Full hang, not the
transient blip Fix 1's repro run showed.

**Why Fix 2 didn't work:** it fixed exactly one of three `Shell_NotifyIcon`
call-out sites on `SystemTrayManager`. `.show()` (the one Fix 2 guarded) is
not the only method that reaches into `Shell_NotifyIcon` — `showMessage()`
(inside `show_notification()`) and `.setIcon()`/`.setToolTip()` (inside
`_refresh_icon()`, reached via `set_health()`/`set_grade()`/
`increment_badge()`/`reset_badge()`/`set_badge()`) do too, and neither was
guarded. This spike's own "Fix 2" section above already named the 3 startup
call sites that gate on `is_available()` before `window.show()` — health_worker
→ tray connect, quiet notifier, morning briefing — but treated them as inert
availability checks. They aren't: when the gate passes, `app.py:1372-1374`
and `app.py:1382-1385`/`1398-1403` call straight into `show_notification()`/
`set_health()`, both of which touch the native tray icon, in the same
`main()` startup window `showMessage`/`_splash_msg` overlap that caused the
original fault.

### Fix 3 — implemented 2026-07-08 (same session as the Fix 2 soak result)

Generalized the invariant from "don't call `.show()` before `showEvent()`" to
"don't call *any* native tray method before the icon has actually been
shown." Added `SystemTrayManager._shown` (`False` in `__init__`, set `True`
in `show_tray_icon()`), and guarded `show_notification()` and
`_refresh_icon()` to no-op while `_shown` is `False` — both are already
documented elsewhere as best-effort/cosmetic, so silently dropping a
startup-time call is consistent with existing behaviour, not a new risk.
`show_tray_icon()` also calls `_refresh_icon()` once right after setting
`_shown = True`, so any badge/grade/health state set while hidden (e.g. an
early `HealthWorker` result) is applied immediately instead of waiting for
the next natural update.

Verified: `ruff check` clean, `tools/check_import_lint.py` clean,
`tests/test_system_tray.py` passes (7 tests, including 3 new regression
tests for the guard and the flush-on-show behaviour), full suite and
`tools/debug_launch.py` pending as of this edit.

**Not yet verified against the actual fault** — same caveat as Fix 2: only a
live chaos/monkey soak (RULE-CHAOS1, user-initiated) can confirm this stops
the fault from reproducing.

## Follow-up (not done in this pass)

- Run a chaos/monkey soak to confirm Fix 3 actually stops the fault from
  reproducing.
- Exact call-out site still not proven with 100% certainty independent of
  the tray icon family of calls — `window._restore_cached_scan()` is no
  longer a suspect for the Fix-2-era occurrence specifically (the fault
  landed inside `_splash_msg` itself, before `_restore_cached_scan()` runs),
  but hasn't been individually audited and ruled out for other occurrences.
- Consider whether `_install_snap_subclass()`'s deferred "COM-apartment fix"
  (referenced in `window-snap-subclass.md`'s Follow-up) should be designed
  once, covering all sites that call out to COM/native Win32 from the main
  thread, rather than patched per call-site. Fix 3 is the second time a
  narrowly-scoped guard missed a sibling call site on the same object —
  worth a grep sweep (`self\._tray\.\w+\(`) across the codebase for any
  other class with multiple native call-out methods and only one guarded.

---

## Real root cause + the deferred-construction fix (2026-07-09)

The COM-fault framing above was a downstream symptom. `procdump -h` on a live
`python app.py` (not the chaos harness) caught the main/GUI thread mid-recursion
in `QBoxLayout::heightForWidth ↔ addWidget ↔ QWidgetItemV2::heightForWidth →
QFontMetrics::boundingRect` — a synchronous Qt layout/text-shaping cascade during
`Dashboard.__init__`, not a COM call. A scratchpad cProfile probe measured
`Dashboard()` construction ≈ 3.3 s, dominated by eager construction of all ~60
page widgets plus a ~0.6 s polish/`heightForWidth` cascade in the single
`root.addWidget(_main, 1)` at `ui/dashboard.py`. Windows' `IsHungAppWindow`
flagged this as a startup "hang"; the chaos harness's 60 s window-wait gave up
before construction finished.

**Phase 1 (committed 6d2702b):** two page-local `showEvent` deferrals, not behind
a flag — `network_map_page` `QWebEngineView` build (~185 ms) and `threat_intel_page`
`_fill_table` (~120 ms).

**Phase 2 (this pass): flag-gated chunked deferred page construction.**
- `experimental/lazy_pages` (QSettings, default False) read once in
  `Dashboard.__init__`. Off ⇒ the eager path is byte-for-byte unchanged (RULE-EXP1).
- `ui/nav/lazy_page.py`: `_LazyPageHost` (a "Loading…" placeholder holding a
  factory) + `_LazyPageMixin` (the swap logic + background chunk-builder).
- In `_build_tabs`, a conservative set of 10 self-contained *leaf* pages is
  wrapped in factory closures and passed to `_lazy_or_build()`. Under the flag the
  factory is deferred and a placeholder is registered in the `QStackedWidget` +
  `_nav_label_to_widget` in its place; the `_build_pro_nav()` string literals never
  move, so the static nav-completeness / nav-label-registry parsers stay green.
- The deferred set (all verified to have no incoming cross-page wiring, no app.py
  RULE-DW2 signal wiring, and no `_build_tabs`-tail table/overlay references):
  IP Calculator, WiFi Heatmap, 802.11 Monitor, Troubleshoot, DNS Zone Map,
  DHCP Leases, Config Snapshots, REST API, Feature Guide, Help & Reference.
- Two triggers materialize a placeholder into its real page and re-point the
  stack + `_nav_label_to_widget` + `_NavEntry.page`: (1) an on-first-nav hook in
  `_nav_rail_go_to()`; (2) a background `QTimer(self)` chunk-builder (RULE-WIN5)
  started ~400 ms after `showEvent`, materializing 2 pages / 150 ms until drained.
  `_materialize_all_pages()` force-drains for any code that iterates every page.
- Verified: ruff + import-lint clean; `tests/test_lazy_pages.py` (host idempotency,
  nav-materializes-every-deferred-label, eager-path-builds-real-pages, drain);
  nav-completeness / nav-label-registry / systematic-coverage / module-loc green;
  `debug_launch` (flag off) → `window.show() called OK`; live flag-on drive
  (scratchpad) → 10 hosts queued, all materialize on nav, background builder
  drains to 0, window visible.
- **Not yet done:** cProfile flag-on-vs-off construction-time delta measurement,
  and a live chaos/monkey soak with the flag on to confirm the startup "hang"
  no longer trips `IsHungAppWindow`.

---

## Every-launch startup measurement (2026-07-17)

Scratchpad cProfile probe (`startup_probe.py`, not in-tree — see the pattern note
above about `NETSENTINEL_PROFILE_PAGES=1` under an outer cProfile swallowing
attribution). Pre-imported matplotlib + scapy before timing to isolate
construction cost from first-import cost. `MetricStore()` profiled against a
scratchpad **copy** of the real portable `NetSentinel.db` (~50 MB, ~30 days of
data) — never the live dev DB in place, since `prune_old_data()` deletes rows.
Two runs per flag state; numbers below are representative (low variance).

| Stage | flag OFF | flag ON | Δ |
|---|---|---|---|
| `MetricStore()` total | 0.002–0.008 s | 0.002–0.008 s | ~0 (see below) |
| `Dashboard()` construction | 2.78–2.84 s | 2.26–2.29 s | **≈ −0.53 s** |
| `_restore_cached_scan()` | 0.28–0.30 s | 0.35 s | noise (flag-independent) |
| `window.show()` + `processEvents()` | 0.45–0.50 s | 0.45–0.45 s | noise (flag-independent) |
| **Total (all four stages)** | **≈ 3.57–3.63 s** | **≈ 3.07–3.09 s** | **≈ −0.5 s (≈ 14–15%)** |

`python -X importtime -c "import ui.dashboard"` cumulative = **104 ms** — a minor
slice next to the ~2.3–2.8 s `Dashboard()` construction total, consistent with
the 2026-07-09 finding that startup cost is dominated by widget
construction/`addWidget` (not imports). Biggest cumulative import contributors:
`modules.utils` 39.7 ms (drags in `urllib.request`/`http.client`/`email.*` —
looks like a keyring/SMTP-adjacent transitive import, not investigated further,
out of scope this session), `modules.mac_lookup` 22.2 ms, `PyQt6.QtCore` 16.9 ms.

**`MetricStore()` / `prune_old_data()` finding — reverses the plan's assumption.**
Against the real ~50 MB/30-day dev DB, `MetricStore()` construction (WAL
checkpoint + schema init + prune) totals 2–8 ms, and `prune_old_data()`'s own
cProfile cumtime rounds to **0.000 s** — i.e. sub-millisecond. The plan's Step 2
(add `prune_on_init` to skip the duplicate `__init__`-time prune on the GUI path,
since `app.py`'s `prune_worker` already runs the same prune off-thread
immediately at startup) is still correct as a **duplication/correctness fix** —
the exact same rollup + ~12 `DELETE`s genuinely runs twice, once synchronously
on the main thread and once off-thread seconds later — but it will not produce
a measurable startup-time win on data shaped like this dev DB. Recorded here so
Step 2 is not oversold as a perf fix in the session summary.

**Verdict on `experimental/lazy_pages`:** the flag is a real, repeatable
**≈ 0.5 s / ≈ 15%** reduction in the synchronous pre-window-visible critical path
(`Dashboard()` construction alone drops ≈ 19%, from the 11 deferred leaf pages no
longer building eagerly). `_restore_cached_scan()` and `window.show()` are
flag-independent, as expected — neither touches the lazy-page mechanism. This is
the number the plan's Step 3 decision gate needed: **worth proposing** the
default flip, but per the plan of record and RULE-CHAOS1 it still requires a
user-run chaos/monkey soak with the flag ON before any default change — not
executed this session.
