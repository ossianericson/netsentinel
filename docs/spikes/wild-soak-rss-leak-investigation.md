# Wild-Soak RSS Growth Investigation — Full History

**Status as of 2026-07-29: a fix has been applied for the bisect's top suspect
(`ProtocolCanvas` missing `hideEvent()`), but this is not yet confirmed as *the* primary
driver — see Session 6.** Sessions 1–5 (through 2026-07-24) found and fixed five real,
separate bugs, none of which explained the bulk of the growth. This document exists
because the hunt has spanned multiple sessions and a significant amount of investigation
time, and needs a single place a human can read start-to-finish without piecing it back
together from chat history or scattered memory notes.

---

## TL;DR

- **The symptom:** running `tools/monkey_test.py` in "wild chaos" mode (randomized UI
  interaction at scale, used for pre-release stability testing) shows RSS (resident
  memory) climbing from a ~500MB baseline to 1.4–1.9GB over the course of an hour, in
  bursts, sometimes partially plateauing, sometimes spiking further. Peaks recorded
  across different runs: 1432MB, 1440.8MB, 1639.8MB, 1649.1MB, 1780.7MB, 1783.4MB,
  1916.6MB.
- **The app never crashes because of it.** Every soak run in this entire investigation
  completed cleanly — 0 exceptions, 0 crashes, byte-identical crash logs, clean shutdown.
  This is a memory-growth characteristic under synthetic stress, not a reported user
  problem.
- **Five real bugs were found and fixed** (dialog leak, two missing-`hideEvent()` worker
  leaks, a monkey-test harness blind spot, a stale-handle crash). All were genuine,
  all shipped. **None of them explains the bulk of the RSS growth.** Each was quantified
  and found to be 2–3 orders of magnitude too small.
- **The driver is confirmed to be native memory** (not Python objects, not a growing
  Python data structure) but has not been traced to a specific allocation site or line
  of code.
- **No further fix has been attempted** for the main driver — every round that got this
  far stopped at "confirmed mechanism category" rather than "here is the line to change,"
  per this project's own debugging discipline (RULE-DBG: never patch before the
  mechanism is confirmed).

---

## Timeline

### Session 1 — 2026-07-21: origin

A 5-hour wild-chaos monkey run (10,293 iterations) was analyzed for an unrelated reason
(a native crash, `STATUS_STACK_BUFFER_OVERRUN`, traced to an `AttributeError` in MAC
address handling — fixed, `8e83f9e`, unrelated to everything below). While reviewing
that run's logs, a second pattern was noticed: RSS climbing **~200–250MB/hour** from a
~500-800MB baseline to peaks of 1000–1475MB across the run's process legs. This is the
first recorded observation of the pattern that consumed every session since.

Initial guess: matplotlib canvases on "chart-heavy" pages (Timeline, Protocol Viz, Root
Cause Correlator). **This guess was wrong** — none of those three pages use matplotlib
at all (confirmed by grep in the next session).

### Session 2 — 2026-07-22/23: dialog `.exec()` leak found and fixed

Pivoted to checking whether an already-known leak *shape* in this codebase (a Qt dialog
created with `parent=self` whose Python handle is later reassigned or dropped — the
C++ object is never freed because the parent still owns it) had unfixed instances
beyond the one place it had already been fixed (the Ctrl+K command palette).

It did, at scale: **47 call sites across 26 files**, zero `deleteLater()` anywhere.
Live-quantified with a standalone repro script (500 dialog opens with/without the fix):
**~521 KB leaked per un-cleaned-up dialog open.**

**Fixed:** `ui/dialog_utils.py::run_dialog()` helper + all 47 call sites migrated +
an AST guard test so no bare `.exec()` call can be reintroduced. Committed `93d96ec`,
shipped in v2.1.39.

**Not yet known at this point:** whether this was the (or a) main driver. The plan was
to re-run a soak test with the fix in place and compare the growth slope.

### Session 3 — 2026-07-23: dialog fix did NOT fix it; two more leaks found and ruled out

Ran a fresh ~87-minute wild-only soak with the dialog fix in place. Result: **the
growth rate looked the same or worse** — two independent process segments both showed
roughly **+450MB per ~20 minutes**, well above the original ~200-250MB/hour figure that
started this thread. The dialog fix, while real, was not sufficient (and may not have
been hit often in this action mix at all).

The run's action histogram was ~57% "toggle" clicks on the nav-rail flyout button — a
new, untested lead. **Nav-rail flyout toggle path:** built two repro scripts, drove it
6,000+ times. Result: a bounded, decaying one-time cache warm-up (~25.6MB total, 99% of
it in the first 1,500 toggles, then flat to noise for the remaining 4,500+). **Ruled
out** — three orders of magnitude too small and the wrong shape (plateaus; the observed
RSS growth doesn't).

Same session, next candidate: **History Page's refresh worker.** Confirmed as a real,
textbook instance of the same leak shape as the dialog bug (a `QThread` reassigned on
every page visit, never freed) — 1:1 growth in live worker instances across 6,000
navigations, unambiguously confirmed. But magnitude: **~1.5 KB per navigation**, ~9MB
total over 6,000 navigations. **Fixed anyway** (`21cdca5`) despite being confirmed too
small to be the driver, because it was a clean, well-understood, cheap fix.

Also fixed this session (unrelated, not memory): the false "shutdown hang" / false
restart pattern in the chaos harness itself, and a redundant icon-rebuild inefficiency
in the nav rail (not a leak, just wasted CPU).

**Status at end of session 3: three mechanisms checked, all real bugs, all fixed,
none explain the driver. Growth rate unchanged.**

### Session 4 — 2026-07-24: two more real leaks found (both in embedded chart/browser
pages), both ruled out; a harness blind spot discovered and fixed

**Network Map's embedded browser view (`QWebEngineView`):** found a genuine missing
`hideEvent()` — a packet-sniffing background worker (`BandwidthOverlayWorker`) started
the first time the page was shown and never stopped when the user navigated away,
pushing a JavaScript update into the embedded Chromium view every 5 seconds forever. A
live repro simulating 2,400 such background pushes (~3.3 hours of real time) found
**+107.72MB in the WebEngine's own separate OS process, only +0.71MB in the main
process** — a real, unbounded-looking leak, but one that lives entirely in a *child
process* the monkey-test harness's RSS sampling had never looked at (it only ever
sampled the single main PID). **Fixed both the app bug and the harness blind spot**
(added `hideEvent()`, and taught `monkey_test.py` to sum RSS across the main process
and all its children — this fix, `RULE-DBG4`, matters for every future soak
measurement, including the one described in the next section). Committed `e44c1a6`.

Same session: **Live Bandwidth page** had the identical missing-`hideEvent()` shape —
a 1Hz polling worker + full matplotlib chart redraw that never stopped after
navigating away. This looked like the strongest matplotlib-retention candidate (highest
tick rate, heaviest per-tick work, confirmed always-running). Measured: **+3.99MB per
simulated hour** in the main process — two orders of magnitude too small. **Fixed
anyway** (`05859ef`) because it was real and cheap to fix; this result substantially
weakened the general "matplotlib retention" hypothesis as a path to the real driver.

Both fixes shipped together with a version bump as **v2.1.44** (release `d9b9ab1`),
monkey-test-before-release requirement explicitly waived by the user for this one
release (documented separately).

**User explicitly chose to pause the "guess which page leaks" approach at this point**
— five candidates checked (dialog, nav-rail toggle, History Page worker, Network Map
WebEngine, Live Bandwidth), all real-or-ruled-out, none the driver. The approach was
about to become progressively guessier (next candidates would have been things like
"QTableWidget row repopulation" or "QPixmap/QIcon caching" with no strong reason to
suspect them over anything else) — a sign that continuing to guess individual pages had
stopped being efficient.

### Session 5 — 2026-07-24 (new session): switch to data-driven, whole-process
measurement instead of guessing pages

This is where the approach changed fundamentally: instead of hypothesizing about a
specific page and building a targeted repro, measure the *whole process's* memory
during a real wild-chaos run and let the data point at the mechanism.

**Round 1 — `tracemalloc` (Python-heap byte tracking).** Ran a full 1-hour wild-chaos
soak with Python's built-in allocation tracer active. Result: Python's own heap bytes
stayed flat at **~23MB** the entire hour while RSS climbed to a peak of **1780.7MB**.
**Conclusion: rules out any growing Python data structure as the driver, definitively.**
The gap between tracemalloc's ~23MB and the actual RSS growth (hundreds of MB) holds
steady rather than narrowing as the run progresses.

**Round 2 — `gc.get_objects()` census (Python object COUNT, not bytes).** Built new
instrumentation (`NETSENTINEL_GC_CENSUS`, now committed and available for future use)
to separately check whether the *count* of live Python objects — specifically Qt widget
wrapper objects — was growing, since a C++ widget outliving its Python wrapper is a
different failure mode than a growing-bytes leak and tracemalloc can't see it. Result:
object counts (including specifically `QLabel`, `QTableWidgetItem`, and other
widget-wrapper classes) stayed flat (+4% to +14%) across a full hour while RSS climbed
to 1639.8MB. **Conclusion: rules out a widget-retention leak too.** Both Python-visible
angles are now exhausted — the driver has no Python-side footprint at all.

**Round 3 — native memory region census (`VirtualQuery` walk of the process's own
address space).** Built new instrumentation (`NETSENTINEL_VMEM_CENSUS`, committed) that
buckets the process's committed memory by type (private read-write memory vs. loaded
DLL images vs. memory-mapped files) every 60 seconds. Result: **localized the leak to
one specific bucket — MEM_PRIVATE READ-WRITE memory** (the kind of memory the C runtime
heap and direct `VirtualAlloc` calls use), climbing **~558MB/hour**, correlating almost
perfectly with the measured RSS climb (r = +0.94). The DLL-image bucket jumped once in
the first few minutes (one-time dependency loading) then sat completely flat for the
rest of the hour — ruled out. Memory-mapped files stayed bounded/oscillating — ruled
out.

**Round 4 — naming the actual allocation call sites (`gflags` + Windows `UMDH`
stack-trace diffing).** This is the heaviest technique tried: enabling Windows'
user-mode stack-trace database for the process, taking a snapshot early and late in a
run, and diffing them to get an actual call stack for every growing allocation. This
required elevated privileges (two false starts: the stack-trace overhead itself
triggered the harness's own hang-detection into a false restart, and reverting the
elevated setting afterward required a human to click through a Windows UAC prompt that
cannot be automated). Once working, it **did** name real, specific growing call sites:
- A `QTimer` tick on the main thread whose connected slot **reconstructs a `QLabel`,
  `QFrame`, and `QVariantAnimation` from scratch on every single tick** instead of
  updating them in place — no source file was pinned down (Qt's shipped binaries have
  no public symbols for this), just the mechanism shape.
- A SQL query (`sqlite3_step`) running on a background thread whose per-call memory
  wasn't being fully released.

But these named sites, plus everything else the stack-trace diff could see, added up
to only **~17% of the actual measured RSS growth** in that run's window (~30.5MB out of
~184MB). **The other ~83% is memory allocated via direct `VirtualAlloc`, which bypasses
the mechanism this technique traces entirely** — a real, anticipated limitation, not a
failure of the method.

**Round 5 — VMMap early/late snapshot comparison** (this most recent round). Rather
than repeating the heavy gflags/UMDH process, took two snapshots of the same live
process's memory map (5 minutes and 45 minutes into a run) using Sysinternals VMMap and
diffed them directly — cheaper, no elevated privileges needed. Findings:
1. VMMap's own memory-type categories already distinguish "went through the Windows
   heap manager" from "raw, untracked `VirtualAlloc`" — the same distinction Round 4
   worked much harder to get.
2. **The 17%/83% split from Round 4 is not a stable ratio.** In this round's run, the
   heap-tracked portion was actually the *majority* (55%) of the growth, not a small
   minority — meaning which allocation mechanism dominates depends heavily on which
   specific things wild-chaos happens to click in a given window, not a fixed property
   of whatever is leaking.
3. **A large, initially alarming false lead was resolved.** The DLL-image memory bucket
   appeared to grow by +444MB in this run — seemingly contradicting Round 3's finding
   that this bucket is flat after an early one-time load. Traced directly to specific
   files: `Qt6WebEngineCore.dll` plus several NVIDIA GPU driver DLLs being loaded for
   the first time — i.e., Network Map's embedded browser view being opened for the
   first time somewhere in this particular run's random action sequence, rather than in
   the first few minutes like Round 3's run happened to hit it. **This is a one-time,
   bounded cost, not a leak** — it just doesn't always happen early, so a single
   snapshot pair can make it look like continuous growth if you don't check what the
   memory actually is.
4. **A live, concrete instance of the harness blind spot found and fixed in Session 4
   was caught red-handed again.** The main process's own memory growth didn't fully
   account for the RSS number the monkey-test harness reports (which sums main +
   children). A live process check found a `QtWebEngineProcess.exe` child running with
   its own ~130MB memory footprint that this round's measurement technique hadn't been
   pointed at.
5. **One new, unconfirmed lead:** among the genuinely-growing raw (non-heap) private
   memory, several new same-size reserved memory blocks appeared (32MB, 18.5MB, 14.75MB
   chunks, each only partially filled) with no attributable owner — the shape of a
   custom memory-pool/arena allocator reserving space up front and filling it in over
   time. A plausible but **unconfirmed** guess is NetSentinel's own SQLite database
   layer (`MetricStore`, which runs in WAL mode and is queried continuously by
   background workers) — this lines up with Round 4's finding of a growing
   `sqlite3_step` call on a background thread, but nothing beyond a shape-level
   coincidence connects them yet.

No fix was attempted this round either — the same discipline every round has followed:
confirm the actual mechanism before writing a fix.

---

### Session 6 — 2026-07-29: a cheaper technique finds a fix candidate

Sessions 1-5 all took the same approach: instrument a live process and watch it run.
This session used a fundamentally different, much cheaper technique instead — the chaos
harness runs **fixed seeds at fixed durations**, so peak RSS from the same phase (same
seed, same duration) is directly comparable across the project's archived
`AI_REPORT.md` run outputs (`C:\Users\ossia\Documents\NetSentinel\test_output\`) without
running anything new. Nobody had compared those phase tables across historical runs
before.

That comparison bisected the regression to **v2.1.32-v2.1.36**: the `Monkey wild (UIA)
(soak) [lap 1]` phase (seed 99, 4h30m, near-identical iteration counts) went from
**580.1MB peak at v2.1.31** to **1,431.7MB peak at v2.1.39** — same phase, same seed,
same duration, 2.5× the RSS, every confound the earlier rounds worried about controlled
for. A 16-minute non-soak `Monkey wild (UIA)` phase shows the same climb (500.5MB →
839.5MB from v2.1.31 to v2.1.39), so validating a fix does not require a multi-hour soak.
Full numbers: memory `project-wild-soak-rss-bisect-window-20260729`.

That window pointed at `ui/widgets/protocol_canvas.py`'s `ProtocolCanvas` — it landed in
v2.1.34, and its second embedding (`ui/widgets/lab_canvas_card.py`, used by Lab Mode)
landed in v2.1.36, the first run confirmed leaking. Reading the actual code (not just
matching the shape from memory) confirmed the suspicion directly: `ProtocolCanvas`
starts a 30fps `QTimer` in `play()`/`enter_live()` and had **no `hideEvent()` at all** —
the exact RULE-WIN15 shape as the already-fixed Network Map and Live Bandwidth leaks
above, and exactly why it would be invisible to every technique tried in Sessions 1-5:
it's native paint/timer overhead, not a Python allocation or a growing data structure.

Fixed by adding a `hideEvent()`/`showEvent()` pair directly on `ProtocolCanvas` (not on
either embedding page) — a live check confirmed Qt propagates a real `hideEvent()` down
through nested child widgets when a `QStackedWidget` switches pages, so one fix on the
shared widget covers both embedding sites. See `RULE-WIN17` in
`development-rules.instructions.md` for the full mechanism writeup and the wrong/correct
code. Regression coverage: `tests/test_protocol_canvas.py` (5 new tests, confirmed RED
against the pre-fix code before the fix was applied).

**Honest caveat, consistent with every fix in this document's table:** this matches the
bisect window's shape and timing precisely and is a real, confirmed defect — but it has
not yet been live-validated as accounting for the actual measured RSS climb. The next
step is re-running the same 16-minute wild chaos phase (seed 99) and comparing peak RSS
against the numbers above. If it doesn't fully close the gap, the bisect memory's
lower-confidence candidates (v2.1.35's native-chrome subclass reinstall on `QWebEngineView`
handle recreation, v2.1.34's `experimental/lazy_pages` extension) are the next leads.

---

## What's fixed (real bugs, all shipped)

| Bug | Where | Fix | Commit | Magnitude found |
|---|---|---|---|---|
| Dialogs never freed after closing | 47 sites, 26 files across `ui/` | `run_dialog()` helper + AST guard | `93d96ec` (v2.1.39) | ~521 KB/dialog open |
| History Page worker never freed on re-visit | `ui/pages/history_page.py` | `deleteLater()` before reassigning | `21cdca5` | ~1.5 KB/navigation |
| Network Map's packet sniffer never stopped on navigate-away | `ui/pages/network_map_page.py` | added `hideEvent()` | `e44c1a6` (v2.1.44) | +107.72MB/2,400 pushes, but in a **child process** |
| Live Bandwidth's 1Hz poller + chart redraw never stopped | `ui/pages/live_bandwidth_page.py` | added `hideEvent()`/`showEvent()` pair | `05859ef` (v2.1.44) | +3.99MB/simulated hour |
| Monkey-test harness only measured the main process, blind to any child-process leak | `tools/monkey_test.py` | sum RSS across main + all children | (same session as Network Map fix) | — |
| ProtocolCanvas's 30fps QTimer never stopped on navigate-away (2 embedding sites) | `ui/widgets/protocol_canvas.py` | added `hideEvent()`/`showEvent()` pair | *(Session 6, uncommitted)* | matches the v2.1.32-v2.1.36 bisect window exactly; not yet live-validated |

Every one of these is a genuine, confirmed, fixed defect. The first five were each 2-3
orders of magnitude too small to explain the ~450MB/20min growth rate that's been the
target since session 3 — the ProtocolCanvas fix is different in kind: it's the first one
found via a bisect that directly targeted the regression window rather than guessing at
a page, so it has a real chance of being the actual primary driver, but that has not
been confirmed by a live re-run yet (see Session 6's caveat above).

## What's confirmed about the actual driver

- Not a growing Python data structure (tracemalloc: bytes flat).
- Not a widget-wrapper retention leak (gc census: object counts flat).
- **Is** native memory — specifically a mix of C-runtime-heap-routed and raw
  `VirtualAlloc` private memory.
- The proportion between those two categories is **not stable** run-to-run — it
  depends on which specific wild-chaos actions get hit in a given window.
- At least some of it is one-time, bounded cost that gets mistaken for continuous
  growth if a measurement window happens to catch it mid-event (the WebEngine/GPU
  driver DLL loading case).
- At least some of it is genuinely ongoing — a QTimer that rebuilds widgets from
  scratch every tick instead of updating them, and a background-thread SQLite call
  with unclear retention, are both real named contributors, just not (yet) sized as
  the majority.

## What's still open

0. **Whether the Session 6 `ProtocolCanvas` fix actually closes the gap is not yet
   confirmed.** It is the first candidate found via a technique (cross-version bisect on
   fixed seed/duration phases) that directly targets the regression window instead of
   guessing at a page, and the code-level mechanism matches exactly — but "matches the
   shape" is not the same claim as "measured to explain the growth," and every entry in
   the table above that made it to a live measurement turned out to be too small. Confirm
   with a live re-run before treating this as closed.
1. **No specific line of code had been identified as the main driver as of Session 5.**
   Every technique tried through that session (tracemalloc, gc census, region-type
   census, UMDH stack diffing, VMMap snapshot diffing) narrows the *category* of memory
   involved but stops short of a single allocation site responsible for the bulk of the
   growth.
2. **The reserved-arena-pattern lead from Round 5** (same-size 32MB/18.5MB/14.75MB
   blocks, unattributed) is the most specific unconfirmed thread — SQLite/MetricStore
   is a guess, not a finding.
3. **The heaviest available technique not yet tried:** attaching a live debugger
   (WinDbg/`cdb`) with a breakpoint on `VirtualAlloc` calls in the relevant size range,
   to capture the actual call stack the moment one of those allocations happens, rather
   than inferring it from a before/after snapshot. This would be a real time investment
   with an uncertain payoff.
4. **The app has never crashed or become unstable because of this** across any run in
   this entire investigation. This is a stress-test memory characteristic, not a
   reported field problem — worth weighing against how much further time to invest.

## Honest bottom line

Sessions 1-5 found and fixed five real bugs without identifying the actual driver of the
RSS growth observed under wild-chaos stress testing — an increasingly precise description
of *what it isn't* and *what general category it's in*, not a fix. Session 6 changed
technique (a cross-version bisect on archived run data instead of live instrumentation)
and landed on a sixth real, confirmed bug — `ProtocolCanvas`'s missing `hideEvent()` —
whose timing and shape match the regression window precisely. Whether that closes the
gap is the open question a live re-run needs to answer; if it doesn't, the next move is
either the more invasive live-debugging session described above or accepting the
remainder as a known, unresolved, non-crashing characteristic.
