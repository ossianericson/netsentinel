# NetSentinel — Architecture Reference

> Target audience: contributors adding a new feature. Read time: ~10 minutes.

---

## 1. High-Level Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  app.py  (entry point)                                                        │
│  Creates QApplication, instantiates MetricStore / AlertEngine /              │
│  NotificationRouter, then opens Dashboard(store, alert_engine, notif_router) │
└───────────────────────────┬──────────────────────────────────────────────────┘
                            │ injects shared singletons
                            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  UI Layer  (ui/)                                                              │
│  dashboard.py  ←  QMainWindow shell (1,967 L); nav/monitor/plugin via mixins │
│  ui/pages/*.py ←  one QWidget per feature page                               │
│  ui/styles.py  ←  all colours / QSS (no hex literals elsewhere)              │
└───────────────────────────┬──────────────────────────────────────────────────┘
                            │ starts / connects signals
                            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Worker Layer  (workers/)                                                     │
│  One QThread subclass per long-running task.                                  │
│  Emits Qt signals: result / status / error / progress                        │
│  Heavy or crash-prone work (Scapy/Npcap) runs in a subprocess.               │
└───────────────────────────┬──────────────────────────────────────────────────┘
                            │ calls pure-Python functions / classes
                            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Module Layer  (modules/)                                                     │
│  Pure Python — no PyQt6, no ui/ imports.                                      │
│  Each module exposes a scan() / run() function and dataclass result types.   │
│  Optional dependencies (scapy, paramiko, …) are lazy-imported inside         │
│  the function that needs them.                                                │
└───────────────────────────┬──────────────────────────────────────────────────┘
                            │ reads / writes
                            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Storage Layer  (modules/metric_store.py)                                     │
│  SQLite (WAL mode, thread-local connections).                                 │
│  Optional PostgreSQL via SQLAlchemy — same public API.                        │
│  Instantiated ONCE in app.py and injected everywhere.                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer Breakdown

### Entry Point — `app.py`

`app.py` is the only file that wires everything together.

| Responsibility | Detail |
|---|---|
| Dependency guard | Checks Python >= 3.9, PyQt6 installed |
| Crash hardening | Enables `faulthandler`, installs `sys.excepthook` |
| Windows exe polish | Patches `subprocess.Popen` to suppress CMD flash in frozen build |
| Single-instance guard | `QLocalServer` — second launch signals the first and exits |
| Shared singletons | Creates `MetricStore`, `AlertEngine`, `NotificationRouter`, `MaintenanceWindowManager` — once each |
| Dashboard | Passes all singletons into `Dashboard(store, alert_engine, notif_router, maint_manager)` |
| Headless / smoke modes | `--headless` (HTML report, no GUI) and `--smoke` (import check for CI) |

### UI Layer — `ui/`

| File/Directory | Role |
|---|---|
| `ui/dashboard.py` | `Dashboard(QMainWindow)` — 1,967-line shell; inherits `ScanResultMixin`, `AppHeaderMixin`, `TabBuilderMixin`, `_NavBuilderMixin`, `_MonitorStateMixin`, `_PluginPageMixin` |
| `ui/nav/builder.py` | `_NavBuilderMixin` — all nav structure building, runtime switching, command palette, pin management |
| `ui/monitor_state.py` | `_MonitorStateMixin` — verdict/badge/pill display, KPI tiles, `VerdictPanel`, `RiskBadge` |
| `ui/plugin_page_mixin.py` | `_PluginPageMixin` — plugin page lifecycle, hardware auto-detect, `_launch_modules_impl` |
| `ui/scan_wiring.py` | `ScanResultMixin` — all `_on_*_result` scan handlers |
| `ui/header.py` | `AppHeaderMixin` — frameless top bar, drag/snap, update bar |
| `ui/tabs.py` | `TabBuilderMixin` — all feature tab builders (inherits scan/network/diag/analysis/recon sub-mixins) |
| `ui/pages/*.py` | One `QWidget` per feature page; receives shared singletons; manages its own workers |
| `ui/styles.py` | Single source of truth for all colour tokens and global QSS |
| `ui/live_graph.py` | Reusable rolling time-series chart widget |
| `ui/topology_widget.py` | Network topology canvas |
| `ui/system_tray.py` | `SystemTrayManager` — minimize-to-tray, toast notifications, badge counter |

**Rules that apply here:**
- All colour values must be imported from `ui/styles.py` — no raw hex strings.
- New pages must render meaningful content within 200 ms (use MetricStore cache before the worker finishes).
- Raw exceptions must never be shown; translate them via a `_friendly_error()` helper.

### Worker Layer — `workers/`

Each file contains one or more `QThread` subclasses.  Workers:

1. Accept configuration in `__init__`.
2. Do all I/O inside `run()`, importing the module lazily there.
3. Emit typed Qt signals: `result`, `status`, `error`, sometimes incremental signals (e.g. `bpdu_found`, `hop_result`).
4. Provide a `stop()` method that sets a `threading.Event` to request graceful shutdown.
5. Must emit a `status` signal at least once every 5 seconds for long-running operations.

Crash-prone Scapy/Npcap operations (STP scan, storm analysis) run inside a **separate `multiprocessing.Process`**. The worker bridges the subprocess queue to Qt signals so a C-level driver crash cannot kill the main process.

### Module Layer — `modules/`

Pure Python, no Qt. Each module:

- Exposes one or more `scan()` / `run()` / `check_*()` top-level functions.
- Returns typed dataclasses (never raw dicts where avoidable).
- Accepts `progress_cb`, `stop_event`, and optional `on_*` callback parameters for streaming output.
- Does not construct `MetricStore`; receives it as an injected parameter when needed.
- Maximum 600 lines per file; split at that threshold.

### Storage Layer — `modules/metric_store.py`

See Section 4 for the full schema overview.

---

## 3. The Module → Worker → Page Pattern

This is the universal data-flow pattern for every feature in NetSentinel.

### Concrete example: Rogue Device Scan (Module 1)

**1. User clicks "Run Scan" in `Dashboard`**

```python
# ui/plugin_page_mixin.py  (_PluginPageMixin — inherited by Dashboard)
worker = Module1Worker(offenders_path=self._offenders_path, parent=self)
worker.result.connect(self._on_m1_result)   # slot on Dashboard
worker.status.connect(self._set_status)
worker.error.connect(self._on_worker_error)
worker.start()
```

**2. Worker imports and calls the module — inside `run()`**

```python
# workers/scan_worker.py  — Module1Worker.run()
from modules.rogue_device import scan     # lazy import — never at module level
data = scan(self.offenders_path)          # pure Python, no Qt
self.result.emit(data)                    # signal crosses thread boundary safely
```

**3. Page slot receives the result on the UI thread**

```python
# ui/scan_wiring.py  (ScanResultMixin — inherited by Dashboard)
@pyqtSlot(dict)
def _on_m1_result(self, data: dict):
    self._m1_result = data
    # update tables, verdict panel, etc.
```

**Signal catalogue** (all workers follow this pattern):

| Signal | Payload | When |
|---|---|---|
| `status` | `str` | Progress messages during execution |
| `result` | dataclass or `dict` | Scan finished successfully |
| `error` | `str` | Non-fatal or fatal error message |
| `<item>_found` | domain object | Incremental findings (e.g. `bpdu_found`) |

### PreScanWorker

Before any module worker runs, `PreScanWorker` flushes DNS/ARP/IPv6 caches and pings the /24 subnet to populate the ARP table. It emits `done` when complete, which triggers the module workers in sequence.

---

## 4. Central Data Store — `metric_store.py`

`MetricStore` is the **only** persistence layer. It wraps SQLite (default) or PostgreSQL (optional, via SQLAlchemy). Schema version is tracked in the `meta` table and bumped on migration.

### Schema overview (v7)

| Table | Purpose | Key columns |
|---|---|---|
| `rtt_sample` | Per-host RTT / packet-loss time series | `ts`, `host`, `rtt_ms`, `loss_pct`, `jitter_ms` |
| `device_state` | Availability snapshots per device | `ts`, `ip`, `mac`, `state` (UP / DEGRADED / DOWN), `rtt_ms` |
| `device_event` | Change events | `ts`, `ip`, `event_type` (JOINED / LEFT / UP / DOWN / DEGRADED / RECOVERED) |
| `known_device` | Device inventory (one row per MAC) | `mac` PK, `ip`, `hostname`, `vendor`, `device_type`, `first_seen`, `last_seen`, `is_authorized`, `custom_name`, `room`, `category`, `is_pinned` |
| `ha_detected` | Home-automation protocol signatures | `ip`, `ha_type`, `confidence` |
| `cert_check` | TLS certificate check results | `host`, `port`, `days_remaining`, `is_expired`, `is_self_signed` |
| `service_check` | TCP service/port heartbeat | `host`, `port`, `label`, `up`, `rtt_ms` |
| `config_snapshot` | Configuration baseline snapshots | `label`, `data_json` |
| `speed_test` | Internet speed test results | `download_mbps`, `upload_mbps`, `ping_ms`, `server_name` |
| `cve_lifecycle` | CVE remediation state per host | `cve_id`, `host`, `service`, `state`, `cvss_score` |
| `alert_fired` | Alert history with ack/escalation | `rule_name`, `host`, `severity`, `message`, `acked_ts`, `escalated` |

### Usage rules

- `MetricStore` is instantiated **once** in `app.py`. Never construct it inside a page widget or module.
- All timestamps are Unix integer seconds (UTC).
- WAL journal mode is enabled — safe for concurrent reads from multiple threads.
- Each calling thread gets its own `sqlite3.Connection` via `threading.local()`.
- Records older than `retain_days` (default: 90) are auto-pruned on open.

---

## 5. Alert Pipeline

```
MetricStore / MonitoringCycle
        │
        │  evaluate_*() calls
        ▼
┌──────────────────┐
│   AlertEngine    │  — pure Python, no Qt
│  (alert_engine)  │  — rule types: RTT_THRESHOLD, LOSS_THRESHOLD,
│                  │    HOST_DOWN, HOST_DEGRADED, NEW_DEVICE,
│                  │    DEVICE_GONE, CERT_EXPIRY, CERT_EXPIRED,
│                  │    FLAP, SERVICE_DOWN
│                  │  — cooldown prevents duplicate firings
│                  │  — flap suppression: HOST_DOWN silenced while flapping
│                  │  — parent/child suppression: child alerts muted
│                  │    when parent device is DOWN
└────────┬─────────┘
         │  on_alert callback  →  AlertFired dataclass
         ▼
┌──────────────────────┐
│  NotificationRouter  │  — pure Python, no Qt
│  (notification_      │  — channels registered with severity + rule_type filter
│   router)            │  — delivery is asynchronous (threading.Thread)
└──┬───────┬───────┬───┘
   │       │       │
   ▼       ▼       ▼
TOAST   WEBHOOK  EMAIL_SMTP
(UI     (HTTP    (smtplib
 tray   POST)    TLS/
 cb)             STARTTLS)
```

Additional channel types added in v1.4.0: Pushover, Ntfy, Telegram.

**Key design rule**: `AlertEngine` and `NotificationRouter` are pure Python. The TOAST channel is wired by the UI layer injecting a callback — the modules never import `PyQt6` directly.

Channel configuration (credentials, URLs) is persisted in `QSettings` by the UI layer. The router only holds runtime state.

---

## 6. Progressive Navigation System

The sidebar has three modes selectable by the user. The mode is persisted in `QSettings` and restored on startup.

| Mode | Audience | What is visible |
|---|---|---|
| **Home** | Home users | Core scans: device scan, diagnostics, overview, connectivity logger |
| **Standard** | Power users | Home + monitoring pages: uptime, certs, services, inventory, alerts, reports |
| **Pro** | Security professionals | Standard + security audit tools: SYN scan, CVE lookup, credentialed scan, SMB enum, threat intel, REST API, SNMP traps, syslog, and all remaining pages |

Mode switching hides/shows sidebar items and persists the selection. A "Pro" indicator appears in the top bar when Pro mode is active.

The sidebar itself is a `QListWidget` with collapsible section headers and sub-groups. A Ctrl+F shortcut focuses the sidebar search box from anywhere in the app.

---

## 7. Plugin System

The plugin system lets users drop Python scripts into a `plugins/` folder without modifying the application.

### Plugin search order

1. `plugins/` sibling to the executable / `app.py`
2. `~/.config/NetSentinel/plugins/`

### Plugin contract

A plugin file must expose:

```python
PLUGIN_META = {
    "name":        "My Plugin",
    "version":     "1.0.0",
    "description": "What it checks",
    "author":      "Your Name",
    "tags":        ["cloud", "AD"],   # optional
}

def run(devices: list, **kwargs) -> PluginResult:
    ...
```

`PluginResult` fields: `plugin_name`, `findings` (list of strings), `risk_level` (LOW / MEDIUM / HIGH / CRITICAL), `raw_data` (dict), `error` (str).

### Runtime flow

```
Dashboard (Pro mode)
  → PluginWorker(QThread)
      → modules/plugin_system.run_plugin(info, devices)
          → importlib.util loads the .py file
          → calls plugin.run(devices)
          → returns PluginResult
      → worker emits result signal
  → plugins page slot updates table
```

`modules/plugin_registry.py` manages discovery and caching of loaded plugins. A bundled example plugin is written to the `plugins/` folder on first run as a contributor template.

---

## 8. Mesh Router Enrichment Pattern

The Mesh & Router feature is a **cross-page enrichment** rather than a self-contained scan — it augments the result set produced by Module 1 (Rogue Device / Device Fingerprinter) with richer data from the router's own API.

### Data flow

```
ARP scan (Module1Worker)
  → Dashboard._on_m1_result()
      → stores scan result + detects gateway_ip
      → renders topology (flat star, or mesh tree if enrichment already present)
      → _check_mesh_autodetect()
          → pre-fills gateway IP on Mesh & Router page
          → _check_mesh_autorun()  [if keyring has saved creds for that IP]
              → skips if a worker is already running (isRunning() guard)
              → otherwise starts MeshWorker silently on every scan

MeshRouterPage  (user-triggered OR silent auto-run after every ARP scan)
  → MeshWorker(host, password).start()
      → modules/deco_client.DecoMeshClient
          → 3-step LuCI auth (keys → auth → login)
          → admin/device?form=device_list          → MeshUnit list
          → admin/client?form=client_list per node → MeshClient list
      → emits result dict {provider, host, units, clients}
  → Dashboard._on_mesh_result()
      → stores _mesh_units (list[MeshUnit]) and _mesh_enrichment (MAC → MeshClient)
      → _apply_mesh_enrichment()
          → overrides col 1 (Hostname) with Deco-assigned name
          → populates col 6 (Node) + col 7 (Band) with speed tooltip
          → reveals hidden Node/Band columns in M1 table
          → mirrors enrichment onto DeviceInfo objects for exports
          → re-renders topology as 3-tier mesh tree
          → _update_m4_deco_chips() → reveals band-usage KPI bar on WiFi Networks page
```

### Key files

| File | Role |
|---|---|
| `modules/deco_client.py` | Pure-Python Deco API client; returns `MeshUnit` / `MeshClient` dataclasses |
| `workers/mesh_worker.py` | `QThread` wrapping `DecoMeshClient`; emits `result`, `error`, `status` |
| `ui/pages/mesh_router_page.py` | Config card (gateway IP + password + keyring), nodes table, clients table; emits `scan_done` |
| `ui/topology_widget.py` | `TopologyWidget.render()` — flat star without mesh data; 3-tier mesh tree when `mesh_units` + `mesh_enrichment` are passed |
| `ui/scan_enrichment.py` | `_apply_mesh_enrichment` / `_check_mesh_autorun` / `_update_m4_deco_chips` (extracted from `dashboard.py` Sprint 18) |
| `ui/scan_wiring.py` | `_on_mesh_result` handler |

### TP-Link Deco auth notes

The Deco XE75 (and other Deco models) uses a 3-step LuCI-style login with AES-CBC + RSA-PKCS1v15 encryption. The critical detail: the login POST must use a form-encoded body (`data=`) with `Content-Type: application/json` explicitly overridden. Sending an actual JSON body (which `requests` does when you use `json=`) returns 403; the default form Content-Type returns "no such callback". The `tplinkrouterc6u` library (PyPI) handles this correctly.

Per-node client assignment requires one API call per node with `{"device_mac": "MAC-UPPERCASE-HYPHEN"}`. The default query returns all clients but without node assignment. All names in API responses are base64-encoded.

### Adding support for a new router vendor

1. Add a new client class to `modules/deco_client.py` (or a new `modules/<vendor>_client.py`) that returns the same `MeshUnit` / `MeshClient` dataclasses.
2. In `workers/mesh_worker.py`, add a branch in `_run_deco()` keyed on `self._provider`:

```python
if self._provider == "deco":
    client = DecoMeshClient(self._host, self._password)
elif self._provider == "eero":
    from modules.eero_client import EeroClient
    client = EeroClient(self._host, self._password)
# ...
client.login()
units   = client.get_mesh_units()
clients = client.get_all_clients(units=units)
self.result.emit({"provider": self._provider, "host": ..., "units": units, "clients": clients})
```

3. Add a provider selector to `MeshRouterPage` (dropdown in the config card).
4. No changes needed in `dashboard.py` — `_apply_mesh_enrichment` consumes `MeshUnit` / `MeshClient` regardless of provider.

### Silent auto-run behaviour

After every ARP scan the dashboard calls `_check_mesh_autorun(gateway_ip)`. If `keyring.get_password("NetSentinel/mesh", gateway_ip)` returns a password, a `MeshWorker` is started silently — re-fetching on every scan so the mesh data stays fresh. The only guard is an `isRunning()` check: if a previous fetch is still in flight the new one is skipped. There is no session-lifetime lock. The enrichment result fires through the same `_on_mesh_result` slot whether triggered manually or automatically. A reference to the worker is kept in `self._mesh_auto_worker` to prevent it being garbage-collected mid-run.

---

## 9. Key Architectural Rules

These rules are enforced in `apm.yml` and some are CI-blocking.

### Testing (blocking)

| Rule | Requirement |
|---|---|
| RULE-T1 | Every new `modules/` file needs `tests/test_<name>.py` with at least one import test and one behavioural test |
| RULE-T2 | Every new `workers/` file needs a lifecycle test: import → instantiate → `start()` → `stop()` → assert `not isRunning()` |
| RULE-T3 | Every bug fix must include a regression test that fails before the fix |
| RULE-T4 | `app.py _smoke_test()` must be updated with every new module or worker |

### Release integrity (blocking)

| Rule | Requirement |
|---|---|
| RULE-R1 | Use `python bump_version.py X.Y.Z` — never edit the 13 version locations manually |
| RULE-R2 | WinGet locale manifest must include all metadata fields, never the minimal skeleton |

### Architecture health

| Rule | Requirement |
|---|---|
| RULE-AH1 | Module files must not exceed 600 lines; split at that threshold |
| RULE-AH2 | Workers must emit a `status` signal at least every 5 seconds during long operations |
| RULE-AH3 | No raw hex colour strings outside `ui/styles.py` and `modules/colours.py` (CI failure) |
| RULE-AH4 | Optional dependencies (scapy, paramiko, speedtest, npcap-dependent libs) must be lazy-imported inside the function that needs them, with a `try/except ImportError` and graceful fallback |

### UX baseline

| Rule | Requirement |
|---|---|
| RULE-UX1 | New pages must show content within 200 ms (use MetricStore cache as initial source) |
| RULE-UX2 | Actions taking > 500 ms must show a visible loading state before they start |
| RULE-UX3 | Every `QTableWidget` with scan results needs a right-click context menu with Copy and How to Fix |
| RULE-UX4 | New pages must not intercept or consume the Ctrl+F shortcut |
| RULE-A1 | Every feature needs a plain-English summary visible by default, and full technical detail accessible via a collapsible section |
| RULE-A2 | Translate all worker errors to actionable messages; no raw Python tracebacks in the UI |
| RULE-A3 | Severity labels are exactly: Info, Warning, High, Critical — no others |

### Application data paths

Data files are written to `get_app_data_dir()` from `modules/utils.py`:

| Platform | Path |
|---|---|
| Windows | `%LOCALAPPDATA%\NetSentinel\` |
| macOS | `~/Library/Application Support/NetSentinel/` |
| Linux | `$XDG_CONFIG_HOME/NetSentinel/` or `~/.config/NetSentinel/` |

---

## 9. Adding a New Feature: Checklist

Follow these steps when adding a feature that involves a new scan or monitoring capability.

### Step 1 — Write the module

Create `modules/<feature_name>.py`:

```python
"""
<FeatureName> — one-line description.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE AH4).
  • MetricStore injected as parameter when persistence is needed.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional
import threading

@dataclass
class FeatureResult:
    findings: list = field(default_factory=list)
    plain_verdict: str = ""
    error: str = ""

def scan(
    progress_cb: Optional[Callable[[str], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> FeatureResult:
    if progress_cb:
        progress_cb("Starting scan...")
    # ... implementation ...
    return FeatureResult(plain_verdict="All clear.")
```

- Do not import `PyQt6` or anything from `ui/`.
- Lazy-import optional dependencies inside the function body.
- Keep the file under 600 lines.

### Step 2 — Write the worker

Add a class to `workers/scan_worker.py` (or create `workers/<feature>_worker.py`):

```python
class FeatureWorker(QThread):
    result = pyqtSignal(object)   # FeatureResult
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, param: str, parent=None):
        super().__init__(parent)
        self._param = param
        self._stop = threading.Event()

    def run(self):
        try:
            from modules.feature_name import scan
            data = scan(
                progress_cb=lambda m: self.status.emit(m),
                stop_event=self._stop,
            )
            if data.error:
                self.error.emit(data.error)
            else:
                self.result.emit(data)
        except Exception as exc:
            self.error.emit(f"Feature error: {exc}")

    def stop(self):
        self._stop.set()
```

### Step 3 — Write the page

Create `ui/pages/<feature>_page.py`:

```python
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from workers.scan_worker import FeatureWorker

class FeaturePage(QWidget):
    def __init__(self, store=None, parent=None):
        super().__init__(parent)
        self._store  = store
        self._worker = None
        self._build_ui()
        self._load_cached()   # show MetricStore data immediately (< 200 ms)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        self._lbl_status = QLabel("Ready.")
        self._btn_run    = QPushButton("Run")
        self._btn_run.clicked.connect(self._run)
        lay.addWidget(self._lbl_status)
        lay.addWidget(self._btn_run)

    def _load_cached(self):
        # Query MetricStore for last result and populate the table/label
        pass

    def _run(self):
        self._btn_run.setEnabled(False)
        self._worker = FeatureWorker(param="value", parent=self)
        self._worker.status.connect(self._lbl_status.setText)
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(lambda: self._btn_run.setEnabled(True))
        self._worker.start()

    def _on_result(self, data):
        self._lbl_status.setText(data.plain_verdict)

    def _on_error(self, msg: str):
        self._lbl_status.setText(f"Error: {msg}")
```

### Step 4 — Register in `Dashboard._build_tabs()`

Find the appropriate nav section and add:

```python
from ui.pages.feature_page import FeaturePage
_feature_page = FeaturePage(store=self._store)
self._nav_add_page("◈", "Feature Name", _feature_page)
```

If the page should only appear in Standard or Pro mode, wrap with a mode check:

```python
if self._nav_mode in ("standard", "pro"):
    self._nav_add_page("◈", "Feature Name", _feature_page)
```

### Step 5 — Write tests

Create `tests/test_<feature_name>.py`:

```python
import pytest
from modules.feature_name import scan, FeatureResult

def test_import():
    from modules import feature_name  # noqa: F401

def test_scan_returns_result():
    result = scan()
    assert isinstance(result, FeatureResult)

# workers/test_feature_worker.py (or add to existing worker test file)
def test_worker_lifecycle(qtbot):
    from workers.scan_worker import FeatureWorker
    w = FeatureWorker(param="test")
    w.start()
    qtbot.wait(200)
    w.stop()
    w.wait(2000)
    assert not w.isRunning()
```

### Step 6 — Update smoke test and version

Add the new module to `_smoke_test()` in `app.py`:

```python
"modules.feature_name",
```

If the worker is in a new file, add it too:

```python
"workers.feature_worker",
```

### Summary checklist

- [ ] `modules/<feature_name>.py` — pure Python, no Qt, lazy optional imports, under 600 lines
- [ ] `workers/<feature>_worker.py` (or added to `scan_worker.py`) — `QThread`, lazy module import in `run()`, `stop()` method
- [ ] `ui/pages/<feature>_page.py` — `QWidget`, shows cached data within 200 ms, no raw hex colours
- [ ] Registered in `Dashboard._build_tabs()` with an appropriate nav section and mode guard
- [ ] `tests/test_<feature_name>.py` — import test + behavioural test
- [ ] Worker lifecycle test — start / stop / assert not running
- [ ] `app.py _smoke_test()` updated
- [ ] No raw hex colour strings added (import from `ui/styles.py` / `modules/colours.py`)
- [ ] All error signals translate to actionable messages (no raw tracebacks in UI)
- [ ] Severity labels are one of: Info, Warning, High, Critical
