# Architecture

NetSentinel follows a strict three-layer separation to keep network logic testable
without a display and to prevent UI code from ever writing to the database directly.

```
UI LAYER       ui/dashboard.py (shell/router), ui/pages/*.py (page widgets)
               Reads from MetricStore for display. Never writes directly.

DATA LAYER     modules/metric_store.py  ←→  NetSentinel.db (AppData)
               Single source of truth for all persisted metrics.

MODULE LAYER   modules/*.py
               Pure business logic — no PyQt imports, no direct DB writes.
```

## Key modules

| Module | Role |
|---|---|
| `modules/combined_discovery.py` | Main scan orchestrator |
| `modules/metric_store.py` | SQLite time-series DB (WAL mode) |
| `modules/alert_engine.py` | Alert evaluation and routing |
| `modules/speed_tester.py` | 3-tier speed test cascade (Ookla CLI → speedtest-cli → pure-Python) |
| `modules/service_diagnostics.py` | DNS/TCP/HTTPS/ICMP/traceroute service probes |
| `modules/network_segments.py` | Automatic /24 subnet grouping |
| `modules/device_stability.py` | IP stability scoring and role inference |

## Workers

All network I/O runs in `workers/` (`QThread` subclasses). They emit `result_ready`
and `error` signals back to the UI thread. Blocking I/O on the main thread is
forbidden.

## File write locations

All file writes go through `get_app_data_dir()` from `modules/utils.py`:

- **Windows:** `%LOCALAPPDATA%\NetSentinel\`
- **macOS:** `~/Library/Application Support/NetSentinel/`
- **Linux:** `$XDG_CONFIG_HOME/NetSentinel/`

The installed exe lives in `Program Files` which is read-only for standard users.

## Adding a new scan module

1. `modules/<name>.py` — pure Python, no PyQt imports
2. `workers/<name>_worker.py` — QThread, emits `result_ready(object)` and `error(str)`
3. `ui/pages/<name>_page.py` — receives `store: MetricStore` as constructor parameter
4. Register in `dashboard._build_pro_nav()` under the correct nav section
5. Add `tests/test_<name>.py` with at least one import test and one behavioural test

Full codebase conventions and all development rules live in
[`CLAUDE.md`](https://github.com/ossianericson/netsentinel/blob/main/CLAUDE.md).
