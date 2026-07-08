# Chaos / Monkey Testing

NetSentinel ships with an automated UI chaos tester that drives the real app
through thousands of random interactions to shake out crashes, focus-steal
edge cases, widget-lifecycle bugs, and slow memory leaks that unit tests can't
reach. It is **Windows-only** (uses pywinauto UIA automation) and **developer-run** —
never part of CI or the commit gate.

The output is a single self-contained `AI_REPORT.md` you can paste straight into
a chat with an AI assistant for triage.

---

## One command

```powershell
.\test.ps1 [budget] [-Soak] [-PlanOnly]
```

`test.ps1` (repo root) is a thin shim over `tools\run_all_monkey_tests.ps1`.

| Command | What it does |
|---|---|
| `.\test.ps1` | Runs until you press Ctrl+C. |
| `.\test.ps1 1h` | Runs for a ~1-hour wall-clock budget, then finalizes the report. |
| `.\test.ps1 20h` | Overnight run — one coverage cycle then a long memory soak. |
| `.\test.ps1 8h -Soak` | Skip the coverage cycle; spend the whole budget on the memory soak. |
| `.\test.ps1 20h -PlanOnly` | Print the resolved plan and exit — launches nothing. |

**Budget format:** `1h`, `45m`, `300s`, or a bare number (interpreted as
minutes). Omit it to run until Ctrl+C.

**Prerequisites** (dev extras — see `requirements-dev.txt`):

```powershell
pip install -r requirements-dev.txt   # pywinauto, psutil, Pillow
```

Run from an interactive desktop session. The real-mouse phase moves your actual
cursor, so don't use the PC while a run is in progress.

---

## The two-phase model

A long run is deliberately split into two different kinds of work, because they
catch different classes of bug.

### Phase 1 — coverage cycle (~1 hour, always first)

One systematic sweep of every page, then five weighted chaos phases, then a
closing sweep. This is the broad functional pass — it exercises every control on
every page at increasing randomness.

| Phase | Script | Weight | What it does |
|---|---|---|---|
| Systematic sweep | `systematic_test.py` | — | Visits every page and every control once. |
| Monkey mild | `monkey_test.py` | 1 | Random UIA control clicking, low chaos. |
| Monkey moderate | `monkey_test.py` | 2 | Random UIA control clicking, medium chaos. |
| Monkey wild | `monkey_test.py` | 3 | Random UIA control clicking, high chaos. |
| Monkey wild (real mouse) | `monkey_mouse_test.py` | 2 | Moves the actual cursor over control centres, header, chaos points. |
| Scan / navigate churn | `scan_navigate_test.py` | 1 | Starts a scan, navigates away, checks for damage. |

Each phase is a **fresh app launch** — the app is started and closed inside every
phase. Seeds rotate so different runs walk the UI differently.

### Phase 2 — memory soak (the rest of a long run)

After the coverage cycle, if enough budget remains, the runner switches to a
long-haul soak: **mild → moderate → wild only** (no mouse/scan — those are
one-time coverage extras), each running as a **single, uninterrupted process**
for hours, split roughly **12% / 33% / 55%** of the remaining budget.

Why this exists: the coverage cycle restarts the app every 5–16 minutes, which
resets memory each time and caps how far a slow leak can ever compound before
you'd notice. A soak phase keeps **one process alive for hours**, so a creeping
leak has time to become visible. `--tracemalloc` is on for these phases, so the
report can point at specific allocation sites.

Soak mode is skipped (the runner keeps doing short cycles instead) when under an
hour of budget remains after the coverage cycle — too little time to be worth it.

### `-Soak` — skip straight to the soak

When you specifically want the memory-leak hunt and don't want to wait an hour
for the coverage cycle, `-Soak` goes straight into the soak from the start:

```powershell
.\test.ps1 8h -Soak        # opening sweep -> mild/moderate/wild soak -> closing sweep
.\test.ps1 -Soak           # indefinite: 1h/2.5h/4.5h laps, repeating until Ctrl+C
```

The whole budget is spent on the soak (minus the two bracketing sweeps).

Use `-PlanOnly` with any of these to preview the exact phase durations before
committing hours to a run.

---

## The report

Every run writes to:

```
%USERPROFILE%\Documents\NetSentinel\test_output\run_<timestamp>\AI_REPORT.md
```

`AI_REPORT.md` is **rewritten after every phase**, so a hang, a closed window, or
Ctrl+C still leaves a complete, paste-ready report of everything that finished.

It contains:

- **Phase results table** — cycle, phase, chaos level, seed, planned vs actual
  duration, exit code, crashes, exceptions, iterations, focus-steals, and
  **Peak RSS (MB)**. Watch the Peak RSS column trend across the `(soak)` rows —
  a steady climb across mild → moderate → wild (or lap-over-lap on an indefinite
  run) is the signature of a leak.
- **Findings** — for any phase that crashed or errored, the actual crash-file
  contents and extracted tracebacks are embedded inline. For soak phases, the
  **first and last tracemalloc top-20 snapshots** are embedded so you can compare
  start-of-phase vs end-of-phase allocation sizes and spot the growing site.

Paste the whole file into a chat and ask for a per-phase summary and a
prioritised fix list. Known harmless noise to ignore: pywinauto focus warnings
and `QThreadStorage` teardown warnings.

---

## Running a single phase by hand

The orchestrator just sequences these; you can run any one directly:

```powershell
python tools\systematic_test.py                                  # coverage sweep, every page
python tools\monkey_test.py --source --chaos wild --duration 1800 --seed 99
python tools\monkey_test.py --source --chaos wild --duration 3600 --tracemalloc  # leak hunt
```

`--source` launches the app from source (`python app.py`); omit it to drive an
installed exe instead. `--tracemalloc` writes top-20 allocation snapshots every
60 s to `%LOCALAPPDATA%\NetSentinel\tracemalloc_snapshots.log`.

---

## When to run it

Per the project's `RULE-CHAOS1`: a clean run is required before every version
bump. The AI agent never launches a chaos run itself — a human starts it and
pastes `AI_REPORT.md` back for triage.
