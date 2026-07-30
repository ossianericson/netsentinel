# Idle RSS leak — background timers on never-shown lazy pages

**Date:** 2026-07-30
**Status:** ROOT-CAUSED and FIXED for the two measured offenders; 10 further
candidates audited and listed below (not yet fixed).
**Supersedes the working theory in:** `docs/spikes/wild-soak-rss-leak-investigation.md`

---

## One-paragraph summary

The long-running wild-soak RSS growth is **not caused by navigation, and not
caused by Network Map**. It is caused by `QTimer`s started in page constructors.
`ui/nav/lazy_page.py`'s background chunk-builder constructs *every* lazy page a
few seconds after startup whether or not the user ever opens it, so a timer
started in `__init__` runs for the entire app session on a page nobody has
looked at. The two measured offenders each rebuilt a `QTableWidget` on every
tick; `QTableWidgetItem` is a C++ object, so the resulting growth was **native
and completely invisible to `tracemalloc`** — which is why five earlier rounds of
tracemalloc / UMDH / VMMap diagnostics found nothing. Measured on a real
Dashboard idling on Home with a real `MetricStore`: main-process RSS
**+556 MB/hr before, −19.6 MB/hr (dead flat) after**.

---

## Why the investigation went wrong for so long

`tools/page_isolation_soak.py` samples RSS **after each navigation**. Wall-clock
growth from these always-on timers therefore gets attributed to whichever page
happened to be visited most recently. That produced a completely coherent — and
completely wrong — story: "Network Map is the driver, at ~2× every other page."

Three measurements broke it:

| Experiment | Result | Conclusion |
|---|---|---|
| 25 real `Home ↔ NetworkMapPage` hide/show cycles, bare `setCurrentWidget` | **+0.03 MB/cycle** | Page hide/show is not the leak |
| Same, but with the real `_nav_crossfade_to` `QGraphicsOpacityEffect` | **+0.035 MB/cycle** | The crossfade is not the leak either |
| Real Dashboard: 120 navigations vs. sitting idle, equal duration | nav **−705 MB/hr**, idle **+122 / +164 MB/hr** | **Navigating *lowered* RSS. Idle time raises it.** |

The control page-pair in the original soak (Home ↔ Overview, 136 MB/hr) matches
the measured idle rate (143 MB/hr) almost exactly — because they are the same
background leak, not a per-page cost.

### The decisive trap

A soak harness that samples on an event **cannot distinguish "this event costs
memory" from "memory grows with wall-clock time and this event is how often I
look."** Any per-event attribution needs a do-nothing control phase of equal
duration. The isolation harness never had one.

---

## Root cause

Two pages, both lazily constructed at startup, both starting a timer in
`__init__`, neither with a `hideEvent()`:

### 1. `ui/pages/connections_page.py` — 5 s

```python
# WRONG — setChecked fires `toggled` -> _on_auto_toggled -> _auto_timer.start()
self._chk_auto.toggled.connect(self._on_auto_toggled)
self._chk_auto.setChecked(True)          # starts a 5s timer AT CONSTRUCTION
```

Every tick: full `psutil` process/socket enumeration + whole-table rebuild
(~10 `QTableWidgetItem` per connection row).

Note the start is **indirect** — via a Qt signal. No realistic static/AST check
follows that path, which is why the regression test is a runtime one.

### 2. `ui/pages/timeline_page.py` — 60 s

```python
# WRONG — runs forever on a page that may never be opened
self._timer = QTimer(self)
self._timer.setInterval(60_000)
self._timer.timeout.connect(self._reload)
self._timer.start()                       # <-- at construction
```

Every tick: store re-query + whole-table rebuild. This is the ~60 s jump cadence
visible in the raw measurement (`+15.15`, `+6.90`, `+3.63` MB at t=45/105/165).

### The fix (both)

Start in `showEvent()`, stop in `hideEvent()`, resume gated on the widget's own
intent flag (RULE-WIN17's pattern). For the checkbox case, keep the visible
default but suppress the signal during construction:

```python
self._chk_auto.blockSignals(True)
self._chk_auto.setChecked(True)     # still checked in the UI...
self._chk_auto.blockSignals(False)  # ...but the timer is not running yet
```

---

## Why `hideEvent()` alone (RULE-WIN15) is not sufficient

**A widget that is constructed but never made visible never receives a
`hideEvent`.** RULE-WIN15 closes the "user navigated away" case; it is
structurally incapable of closing the "user never went there at all" case — and
with lazy page construction, that is the *common* case, since every page is
built at startup and most are never opened. RULE-WIN18 covers the other end of
the same lifecycle. Both halves are required.

---

## Measurements

Idle on Home, real `MetricStore` (copy of the real DB), populated Network Map,
split per process. `PHASE`/`DURATION` harnesses were throwaway scratch scripts.

**Before:**
```
   t |     main |    child |  d_main | d_child
  45 |   574.2M |   123.1M | +15.15  |  +1.11
 105 |   581.0M |   123.7M |  +6.90  |  +0.37
 165 |   584.7M |    98.0M |  +3.63  |  +0.41
main 559.2 -> 584.7 MB   (+556 MB/hr)
```

**After:**
```
main 560.9 -> 559.6 MB   (-19.6 MB/hr)   # every sample +0.00 / -0.0x
```

**tracemalloc proof that the leak is native:** over the same window RSS grew
448.9 → 482.2 MB (+495 MB/hr) while Python-tracked memory went 0.9 → 1.7 MB.
tracemalloc *did* still name the offender's line
(`connections_page.py:539/540`, the `QTableWidgetItem` construction) even though
it could not see the bytes — the Python-side wrapper allocation was the
fingerprint, ~512 KB/interval, while the C++ objects behind it were the mass.

### `QtWebEngineProcess` is a red herring

The WebEngine child oscillates ~97 MB → ~123 MB, dumps ~25 MB, repeats — a
**bounded sawtooth** (Chromium's own GC), not a leak. Because prior harnesses
summed main+children into one number (correctly, per RULE-DBG4), this sawtooth
added ±25 MB of noise to every sample and made the real signal — a flat main
process with periodic small steps — very hard to see. **Always split main vs.
children before concluding anything about a multi-process app's memory.**

---

## Audit: remaining construction-time timers (NOT yet fixed)

Found by AST scan of `ui/` for `self.<x> = QTimer(...)` + `self.<x>.start()`
reachable from `__init__`. Ordered by likely impact.

| File | Timer | Every | Handler | `hideEvent`? |
|---|---|---|---|---|
| ~~`ui/pages/security_overview_page.py`~~ | `_refresh_timer` | 5 s | `_load_data` | **FIXED — see below** |
| ~~`ui/pages/dhcp_lease_page.py`~~ | `_timer` | 300 s | `_run_scan` | **FIXED — see below** |
| `ui/skeleton.py` | `_timer` | 1 s | `_animate` | NO |
| `ui/dashboard.py` | `_pulse_timer` | 10 s | `_refresh_pulse_bar` | n/a (shell) |
| `ui/pages/hardware_integration_page.py` | `_tick_timer` | 30 s | `_tick_timestamps` | NO |
| `ui/pages/maintenance_page.py` | `_timer` | 60 s | `_refresh_table` | NO |
| `ui/pages/monitor_overview_page.py` | `_age_timer` | 60 s | `_refresh_ages` | NO |
| `ui/pages/overview_page.py` | `_age_timer` | 60 s | `_refresh_tile_ages` | NO |
| `ui/pages/trigger_builder_page.py` | `_auto_eval_timer` | 60 s | `_auto_evaluate` | NO |
| `ui/pages/home_automation_page.py` | `_refresh_timer` | 120 s | `_load_devices` | NO |
| `ui/pages/inventory_page.py` | `_auto_timer` | (dynamic) | `_refresh` | NO |

`ui/pages/threat_intel_page.py::_threat_timer` and
`ui/pages/timeline_page.py::_tl_search_timer` are **false positives** —
single-shot debounce timers started from a `textChanged` lambda, not at
construction.

The remaining nine were left unfixed deliberately: the stability covenant asks
for the smallest verified diff, and each should be fixed with its own
before/after measurement and added to `_PAGE_FACTORIES` in
`tests/test_page_timer_lifecycle.py`.

---

## Follow-up: the two flagged above, measured and fixed (2026-07-30)

**Both predictions in the original audit were wrong on the specifics.** Measuring
first changed what each fix was actually for.

### `security_overview_page` — not an RSS leak at all

Predicted "same shape and cadence as the confirmed `connections_page` offender."
Measured: **flat**. Never-shown page, real `MetricStore` on a copy of the real DB,
idling 5 min (`--page security`), main-process RSS:

| DB state | steady-state RSS drift |
|---|---|
| real DB (0 unacked alerts) | `53.12 → 53.47 MB` over 4.5 min ≈ **+5 MB/hr** |
| + 25 seeded unacked alerts | `54.52 → 55.05 MB` over 4.5 min ≈ **+7 MB/hr** |

Seeding 25 alerts exercises the per-row `QPushButton` rebuild in
`_rebuild_unacked_alerts_table()` — 300 buttons/min — and RSS still did not move.
`setRowCount(0)` deletes cell widgets, so Qt reclaims them properly. The
`connections_page` mechanism does **not** generalise to every table-rebuilding
timer; the mass there was very likely the `psutil` socket enumeration, not the
`QTableWidgetItem` churn.

The real cost is CPU/IO, and it is measurable. Same harness, 3 min, CPU seconds
consumed by the process:

| | CPU over 3 min idle |
|---|---|
| control (`--page none`, no page built) | 0.03 s |
| **before** (timer running, never shown) | **0.33 s** |
| **after** (timer deferred to `showEvent`) | **0.05 s** |

≈ 6 s of CPU per hour and ~2,160 SQLite reads per hour, forever, on a page the
user never opened — now indistinguishable from the do-nothing control. Note this
page is built **eagerly** in `_init_pages()` (no `_lazy_or_build` wrapper), so
unlike every other entry in the audit table its timer started during
`Dashboard.__init__` for every user on every launch.

### `dhcp_lease_page` — not an active network scan

The audit called it "an active network scan … unexpected network traffic." That
overstates it: `dhcp_lease_scanner.scan()` is **passive**. On Windows it shells
out to `ipconfig /all` + `arp -a` (reads of the local ARP cache); on POSIX it
reads lease files and `nmcli`. **No packets are sent.** The real defect is the
subprocess spawns and the QThread, on a page nobody opened.

RSS is the wrong axis for a 300 s timer (a 3-minute window contains zero ticks),
so the evidence is behavioural — counting real calls to
`dhcp_lease_scanner.scan()`:

| | before | after |
|---|---|---|
| never shown (8 s) | **1 scan**, timer `[300000]` active | **0 scans**, no timers |
| after real show | 1 | 1 |
| after real hide | timer still active | timer stopped |

The construction-time `_run_scan()` moved to a first-show-only call gated on
`_auto_scanned`, so opening the page still lands on populated leases rather than
the empty state — verified live: 16 rows, content stack index 1.

### Live walk (RULE-T6)

Real `Dashboard`, real `MetricStore`, driven through the real
`_nav_rail_go_to()`:

```
== SECURITY OVERVIEW ==
  constructed, never navigated : timers [] not-current, hidden
  after nav TO the page        : timers [5000] CURRENT, visible
  after nav AWAY               : timers [] not-current, hidden
  after nav BACK               : timers [5000] CURRENT, visible
== DHCP LEASES ==
  before ever navigating       : scans 0
  after nav TO the page        : scans 1  timers [300000]  rows 16  stack 1
  after nav AWAY               : timers [] not-current, hidden
  after nav BACK               : scans 1  timers [300000]   (no re-scan)
```

**Harness trap, cost two false alarms.** The first run of this walk reported the
Security Overview timer *not* stopping on navigate-away and DHCP never scanning
— both looked like real defects. Neither was:

1. `_nav_rail_go_to("Overview")` is a **dead label** (the real one is `"Home"`).
   The app logs `dead navigation: no page registered for label 'Overview'`, so
   the "navigate away" step never happened and the page correctly stayed visible
   with its timer running. Read that log line before believing the assertion.
2. The pump loop called `processEvents()` with no sleep. The nav crossfade is a
   160 ms `QPropertyAnimation`, which needs real wall-clock time to finish
   (RULE-T5) — without it the target page never becomes current, so its
   `showEvent` never fires.

A nav-driven verification harness must assert the navigation *succeeded*
(`_stack.currentWidget() is page`) before interpreting anything downstream of it.

---

## Regression coverage

`tests/test_page_timer_lifecycle.py` — verified RED before the fix, GREEN after:

1. `test_never_shown_page_runs_no_timers` — construct, never show, assert
   `findChildren(QTimer)` has nothing active. Catches both the direct and the
   signal-driven start.
2. `test_timer_starts_on_show_and_stops_on_hide` — real
   `QStackedWidget.setCurrentWidget` transitions, not bare `.hide()`/`.show()`.
3. `test_connections_auto_checkbox_stays_checked_by_default` — pins that the
   `blockSignals` fix did not silently flip the user-visible default.

**Teardown trap:** `ConnectionsPage.__init__` starts a `ConnectionSnapshotWorker`.
Deleting the page while that QThread runs kills the pytest process with **no
summary line and exit code 0** — the RULE-GATE1 truncation mode, which reads as a
pass. The tests route every teardown through a helper that stops all timers and
joins all `QThread` children first. This bit twice during this session (the same
shape also appeared in `tests/test_network_map_page.py`'s `page` fixture).

---

## Reverted during this session

Three earlier `network_map_page.py` fixes are **correct and were kept**: the
`BandwidthOverlayWorker` `deleteLater` (RULE-WIN8), the `_on_bw_snapshot` dedup
guard, and the `showEvent` `fit_view` gating. A fourth change — removing
`hideEvent()` entirely on the theory that restarting the Scapy sniffer was
itself the leak — was **reverted**, since the leak turned out to be elsewhere and
RULE-WIN15 compliance was correct as originally written.
