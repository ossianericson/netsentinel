# NetSentinel Remote Sensor Logger — Implementation Specification

**Status:** approved design, not yet implemented
**Date:** 2026-07-07
**Scope:** a headless Raspberry Pi sensor (`logger/` — 100 % standalone, never imported by the desktop app), a zero-touch SD-card provisioning flow driven from the NetSentinel desktop UI, and the NetSentinel-side ingest path (worker + page + wizard, files listed in §2.2).
**Supported base image:** Raspberry Pi OS **Lite 64-bit (Bookworm, 2023-10 or later)** on Raspberry Pi 4 / 5.
**Targets:** < 60–80 MB RSS, negligible idle CPU, 24/7 unattended operation, user never logs into the Pi.

This document is written to be implemented directly: signatures, payloads, file contents, and behaviours are normative. Where the desktop app is referenced, the cited symbols exist today (verified against the codebase at v2.1.25).

---

## 1. High-Level Architecture

### 1.1 System component diagram

```
┌────────────────────────── Raspberry Pi (headless) ──────────────────────────┐
│                                                                             │
│  netsentinel-logger (systemd service, user "netsentinel", CAP_NET_RAW)      │
│                                                                             │
│   ┌───────────────┐   ┌──────────────┐   ┌───────────────┐                  │
│   │ PingSampler   │   │ Scheduler     │   │ paho network  │                 │
│   │ thread        │   │ thread        │   │ loop thread   │                 │
│   │ 1 Hz ICMP per │   │ min-heap jobs:│   └──────┬────────┘                 │
│   │ target, 30 s  │   │  discovery    │          │                          │
│   │ stat windows  │   │  dns probes   │          │                          │
│   └──────┬────────┘   │  system snap  │          │                          │
│          │            │  export flush │          │                          │
│          │            │  spool sweep  │          │                          │
│          │            └──────┬────────┘          │                          │
│          │                   │ ThreadPoolExecutor(3)                        │
│          ▼                   ▼                                              │
│   ┌───────────────────────────────────────────┐                             │
│   │ AnomalyEngine (in-caller-thread, locked)  │                             │
│   └──────────────────┬────────────────────────┘                             │
│                      ▼                                                      │
│   ┌───────────────────────────────────────────┐    ┌─────────────────────┐  │
│   │ Pipeline.emit(topic, payload, qos, retain)│───►│ CSV / JSONL export  │  │
│   │  • stamp ts + sensor_id                   │    │ (rotating daily)    │  │
│   │  • spool (SQLite WAL, write-then-publish) │    └─────────────────────┘  │
│   │  • publish via MqttClient                 │                             │
│   └──────────────────┬────────────────────────┘    ┌─────────────────────┐  │
│                      │                             │ optional REST API   │  │
│                      ▼                             │ 127.0.0.1:8787 GET  │  │
│   ┌───────────────────────────────────────────┐    └─────────────────────┘  │
│   │ spool.db  (/var/lib/netsentinel-logger)   │                             │
│   │  spool table + anomaly_state table        │                             │
│   └───────────────────────────────────────────┘                             │
│                                                                             │
│  mosquitto (broker-on-Pi mode, apt package)  ◄── logger publishes localhost │
│  avahi-daemon: advertises _netsentinel-sensor._tcp + netsentinel-{id}.local │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ MQTT (user/password, port 1883;
                                 │ TLS optional, off by default)
                                 ▼
┌────────────────────────── NetSentinel desktop app ──────────────────────────┐
│  workers/mqtt_ingest_worker.py (QThread, one paho client per sensor)        │
│      subscribe netsentinel/sensor/+/#  →  message_received(dict)            │
│                                 │                                           │
│  Dashboard._on_sensor_message dispatcher                                    │
│   ├─ ping/*, dns/*      → MetricStore.record_rtt(host="{id}:{target}", …)   │
│   ├─ devices/snapshot   → DeviceTracker.process_scan(devices)               │
│   ├─ system, status     → MetricStore.record_plugin_snapshot("sensor:{id}") │
│   │                       + Log Hub dynamic source (update_plugin_sources)  │
│   └─ anomaly            → AlertFired → record_alert_fired + NotificationRouter│
│                                                                             │
│  ui/pages/remote_sensor_page.py — fleet table + "Provision New Sensor"      │
│  ui/widgets/sensor_setup_wizard.py — writes SD-card boot partition (FAT32)  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Data flow

1. **Producers** (PingSampler, scheduled jobs) compute *aggregated* results — never per-packet messages. A 30 s ping window of 30 samples becomes **one** MQTT message. This is the single most important efficiency decision: broker traffic, spool writes, and desktop DB writes all scale with windows, not packets.
2. Every producer result passes through **AnomalyEngine** (pure evaluation, may emit an extra `anomaly` payload) and then **`Pipeline.emit()`** — the only code path that touches MQTT, the spool, and the file exporters. One choke point = one place for buffering, stamping, and sanitization.
3. `Pipeline.emit()` for non-retained topics: INSERT into the SQLite spool **first**, then publish (QoS 1). The paho `on_publish` ack marks the row `published=1`. If the broker is unreachable, rows simply accumulate; on reconnect a drain job replays pending rows oldest-first. Retained topics (`status`, `devices/snapshot`) are *not* spooled — replaying stale retained state is worse than absent state.
4. The desktop app's ingest worker receives messages, parses the topic into `(sensor_id, data_class, subpath)`, and routes each class to an existing MetricStore/DeviceTracker/alert entry point (§7.4). No new tables are required in the desktop app.

### 1.3 Threading / scheduling strategy

Plain `threading` — **no asyncio**. Every library in the stack (paho, icmplib, zeroconf, sqlite3, psutil) is sync/thread-native; asyncio would add wrapper shims for zero RAM benefit. Total ~6 mostly-sleeping threads:

| Thread | Owner | Cadence | Duty |
|---|---|---|---|
| main | `main.py` | 30 s | signal handling (SIGTERM/SIGHUP), sd_notify `WATCHDOG=1` — pet only if all threads report fresh heartbeats |
| PingSampler | `probes/ping.py` | 1 Hz per target | ICMP echo, window stats; drift-free `next_deadline += interval` monotonic scheduling |
| Scheduler | `scheduler.py` | event-driven | min-heap of `(next_run, job)`; submits due jobs to the executor |
| executor ×3 | `ThreadPoolExecutor` | on demand | discovery cycle, DNS probes, system snapshot, export flush, spool sweep — a slow discovery sweep can never delay system metrics |
| paho loop | `loop_start()` | event-driven | MQTT I/O, acks, reconnect callbacks |
| REST (optional) | `api.py` | on demand | `ThreadingHTTPServer`, GET-only, localhost |

Scheduling is **monotonic-deadline** based (`time.monotonic()`), never `sleep(interval)` accumulation, so cadence does not drift and is immune to NTP steps. Every periodic component records `last_beat` per name; the main thread refuses to pet the systemd watchdog if any beat is older than 3× its interval → systemd restarts the whole service. That watchdog-restart loop is the primary self-healing mechanism (§8.2).

### 1.4 Memory / CPU budget

| Component | RSS estimate |
|---|---|
| CPython 3.11 base + stdlib | ~18 MB |
| paho-mqtt, PyYAML, sdnotify | ~4 MB |
| psutil | ~4 MB |
| icmplib | ~2 MB |
| zeroconf (persistent listener) | ~8 MB |
| working set (windows, spool cursors, thread stacks) | ~8 MB |
| **Total** | **~40–45 MB** — inside the 60–80 MB target with headroom |

scapy is explicitly banned (50+ MB RSS on import, needs root). CPU: 1 Hz ICMP + one /24 sweep per 5 min + psutil snapshot per 60 s is < 1 % of one Pi 4 core on average. `MemoryMax=150M` in the unit is a kill-switch backstop, not the target.

---

## 2. Project Structure

### 2.1 `logger/` (this folder — standalone, no imports from/to the desktop app)

```
logger/
├── SPEC.md                            # this document
├── pyproject.toml                     # package "netsentinel-logger"; deps; console script
│                                      #   netsentinel-logger = netsentinel_logger.main:main
│                                      # [tool.pytest.ini_options] rooted here (never collected
│                                      # by the desktop suite, which roots at repo /tests)
├── requirements.txt                   # pinned versions; copied into the SD-card payload
├── README.md                          # quick-start; points at SPEC.md and deploy/install.sh
├── config.example.yaml                # the fully commented config from §5
│
├── netsentinel_logger/                # the Python package (pure Python — sdist is arch-independent)
│   ├── __init__.py                    # __version__ = "1.0.0" only
│   ├── main.py                        # CLI (--config, --check, --version), wiring, signals,
│   │                                  # sd_notify READY/WATCHDOG loop
│   ├── config.py                      # YAML load, ${ENV} interpolation, dataclass schema,
│   │                                  # validation with field-path errors
│   ├── scheduler.py                   # Scheduler thread + Job dataclass (monotonic min-heap)
│   ├── pipeline.py                    # Pipeline.emit() fan-out: stamp → spool → MQTT → export
│   ├── mqtt_client.py                 # paho v2 wrapper: LWT, backoff reconnect, ack → spool,
│   │                                  # safe_segment() topic sanitizer
│   ├── spool.py                       # SQLite spool + anomaly_state key/value store
│   ├── anomaly.py                     # 4 rules, HysteresisRule, EWMA, state persistence
│   ├── exporters.py                   # rotating daily CSV + JSONL writers, retention sweep
│   ├── api.py                         # optional read-only ThreadingHTTPServer
│   └── probes/
│       ├── __init__.py
│       ├── ping.py                    # PingSampler thread + pure compute_window()
│       ├── dns_probe.py               # stdlib UDP DNS A-query latency probe (~40 lines)
│       ├── discovery.py               # ICMP sweep + /proc/net/arp + zeroconf + optional arp-scan
│       └── system_metrics.py          # psutil + vcgencmd/sysfs CPU temp snapshot
│
├── deploy/                            # everything installed onto the Pi
│   ├── netsentinel-logger.service     # hardened runtime unit (§6.5)
│   ├── netsentinel-provision.service  # stage-2 one-shot firstboot unit (§6.3)
│   ├── provision.sh                   # stage-2 script: apt/pip install, broker, avahi (§6.3)
│   ├── firstrun.sh                    # stage-1 early-boot script template (§6.2)
│   ├── secrets.env.example            # NSL_MQTT_PASSWORD=... template
│   ├── 50-netsentinel-logger.conf     # sysctl: net.ipv4.ping_group_range (unprivileged-ICMP fallback)
│   ├── mosquitto-netsentinel.conf     # broker-on-Pi listener config (§6.4)
│   ├── avahi-netsentinel.service      # _netsentinel-sensor._tcp advertisement XML (§6.4)
│   └── install.sh                     # manual/SSH install path (§6.6) — also called by provision.sh
│
├── tools/
│   └── smoke.py                       # hardware-in-loop post-install verification (§8.4)
│
└── tests/
    ├── conftest.py                    # FakeMqttClient, FakeClock, tmp spool, fixture loaders
    ├── fixtures/
    │   ├── proc_net_arp.txt           # sample kernel ARP table
    │   └── config_full.yaml           # every option set, for round-trip test
    ├── test_config.py                 # defaults, ${ENV} interpolation, validation errors
    ├── test_scheduler.py              # no-drift deadlines with FakeClock; heartbeat ages
    ├── test_spool.py                  # write/ack, replay order, cap eviction, crash recovery
    ├── test_ping_stats.py             # jitter/loss math on fixed sample vectors
    ├── test_discovery.py              # ARP-table parse, merge of arp/mdns sources
    ├── test_anomaly.py                # hysteresis fire/clear, EWMA persistence, fresh-install seeding
    ├── test_pipeline.py               # spool-then-publish ordering, retained-not-spooled
    ├── test_topics.py                 # topic sanitization + every §4 example payload vs schema
    └── test_exporters.py              # CSV/JSONL rotation and retention
```

### 2.2 Desktop-app files (implemented later, per this spec — NOT inside `logger/`)

| File | Purpose | Pattern it follows |
|---|---|---|
| `workers/mqtt_ingest_worker.py` | QThread MQTT subscriber, one client per sensor | `workers/syslog_worker.py` |
| `ui/pages/remote_sensor_page.py` | Remote Sensors fleet page (Extend section) | existing pages + `_build_pro_nav()` registration |
| `ui/widgets/sensor_setup_wizard.py` | QWizard that provisions the SD card | `ui/widgets/` dialog conventions |
| `modules/sensor_registry.py` | QSettings/keyring-backed sensor list (no PyQt imports) | RULE 22-A keyring usage |
| `tests/test_mqtt_ingest_worker.py`, `tests/test_sensor_wizard_files.py`, `tests/test_sensor_registry.py` | app-side tests (§8.4) | RULE-T2 lifecycle tests |

Build changes: bundle `logger/dist/netsentinel_logger-{ver}.tar.gz` + `logger/requirements.txt` + the `deploy/` templates as data files in `NetSentinel.spec` so the wizard can copy them to the SD card; add `paho.mqtt` guard identical to `modules/mqtt_publisher.py` (lazy `try/except ImportError`).

---

## 3. Detailed Module Breakdown

Conventions for all logger modules: pure Python 3.11+, type-hinted, no module-level side effects, every external effect (clock, sockets, subprocess, publish) injected as a callable so tests substitute fakes.

### 3.1 `config.py`

**Responsibility:** load + validate the YAML config into frozen dataclasses; interpolate `${ENV_VAR}` references; produce actionable errors.

```python
class ConfigError(Exception): ...            # message includes YAML field path, e.g. "ping.interval_s: must be > 0"

@dataclass(frozen=True) class SensorCfg:     # sensor_id (default: socket.gethostname()), location
@dataclass(frozen=True) class MqttCfg:       # host, port=1883, username, password (resolved from env),
                                             # base_topic="netsentinel", tls_enabled=False, tls_ca_cert=None,
                                             # heartbeat_interval_s=300
@dataclass(frozen=True) class PingCfg:       # targets: list[str], interval_s=1.0, report_window_s=30
@dataclass(frozen=True) class DnsCfg:        # resolvers: list[str], query_name="example.com", interval_s=60
@dataclass(frozen=True) class DiscoveryCfg:  # enabled=True, subnet="auto", interval_s=300,
                                             # use_arp_scan=False, mdns_enabled=True
@dataclass(frozen=True) class SystemCfg:     # interval_s=60, interface="auto"
@dataclass(frozen=True) class AnomalyCfg:    # per-rule enabled flags + thresholds (§3.8 defaults)
@dataclass(frozen=True) class BufferCfg:     # path="/var/lib/netsentinel-logger/spool.db",
                                             # max_rows=200_000, max_age_hours=72
@dataclass(frozen=True) class ExportCfg:     # csv_enabled=False, jsonl_enabled=False,
                                             # dir="/var/lib/netsentinel-logger/export",
                                             # rotate_daily=True, retention_days=14
@dataclass(frozen=True) class ApiCfg:        # enabled=False, bind="127.0.0.1", port=8787
@dataclass(frozen=True) class LoggingCfg:    # level="INFO", file=None  (None → stderr → journald)
@dataclass(frozen=True) class LoggerConfig:  # one field per section above

def load_config(path: Path) -> LoggerConfig
```

`${NSL_MQTT_PASSWORD}` style interpolation applies to any string value; a reference to an unset variable is a `ConfigError`. `mqtt.password` defaults to `${NSL_MQTT_PASSWORD}`. Library: **PyYAML** (`yaml.safe_load`).

### 3.2 `scheduler.py`

**Responsibility:** run periodic jobs at drift-free monotonic deadlines; expose per-job heartbeat ages for the watchdog.

```python
@dataclass class Job: name: str; interval_s: float; fn: Callable[[], None]

class Scheduler(threading.Thread):
    def __init__(self, executor: ThreadPoolExecutor,
                 clock: Callable[[], float] = time.monotonic): ...
    def add_job(self, name: str, interval_s: float, fn: Callable[[], None]) -> None
    def trigger_now(self, name: str) -> None          # used by SIGHUP → immediate discovery
    def heartbeat_ages(self) -> dict[str, float]      # seconds since each job last *completed*
    def stop(self) -> None                            # joins within 5 s
```

Implementation: `heapq` of `(deadline, seq, job)`; on pop, `executor.submit(_run_guarded, job)`; `_run_guarded` wraps `job.fn()` in try/except (log + continue — one crashing job never kills the thread), records completion time, pushes `deadline + interval_s` (skipping missed slots forward if the system slept). Stdlib only.

### 3.3 `mqtt_client.py`

**Responsibility:** own the single paho client; LWT; reconnect with backoff; surface acks and reconnects to the pipeline.

```python
def safe_segment(s: str) -> str
    # replaces each of  : . / + #  and whitespace with "_"
    # SAME charset as the desktop app's mqtt_publisher._safe() — topic compatibility is normative

class MqttClient:
    def __init__(self, cfg: MqttCfg, sensor_id: str,
                 on_ack: Callable[[int], None],        # paho mid → Spool.mark_published
                 on_reconnect: Callable[[], None]): ...# pipeline schedules spool drain here
    def connect(self) -> None                          # non-blocking; loop_start()
    def publish(self, topic: str, payload_json: str, qos: int, retain: bool) -> int | None
                                                       # returns mid, or None if disconnected
    def is_connected(self) -> bool
    def stop(self) -> None                             # publishes offline status, disconnects cleanly
```

Normative details:
- paho-mqtt **2.x**, `mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"nsl-{sensor_id}", protocol=mqtt.MQTTv311)` — greenfield code does **not** inherit the desktop app's v1 compat shim.
- LWT before connect: `will_set(f"{base}/sensor/{sid}/status", json.dumps({"state": "offline", "sensor_id": sid}), qos=1, retain=True)` — mirrors the desktop app's own `netsentinel/status` LWT pattern.
- `on_connect`: publish retained online `status` (§4 payload), then invoke `on_reconnect`.
- Reconnect: paho's `reconnect_delay_set(min_delay=1, max_delay=120)` + `loop_start()` auto-reconnect. Never busy-loop.
- TLS: if `tls_enabled`, `client.tls_set(ca_certs=cfg.tls_ca_cert)` — one call, off by default (user decision: user/password without TLS is the default posture; the option exists for shared-broker deployments).

### 3.4 `spool.py`

**Responsibility:** crash-safe outbound buffer + persistent key/value state, in one SQLite file.

Schema (exact):

```sql
PRAGMA journal_mode=WAL;
PRAGMA auto_vacuum=INCREMENTAL;
CREATE TABLE IF NOT EXISTS spool (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        INTEGER NOT NULL,           -- payload epoch seconds
    topic     TEXT    NOT NULL,
    payload   TEXT    NOT NULL,           -- JSON exactly as published
    qos       INTEGER NOT NULL DEFAULT 1,
    published INTEGER NOT NULL DEFAULT 0  -- 0 pending, 1 acked
);
CREATE INDEX IF NOT EXISTS idx_spool_pending ON spool(published, id);
CREATE TABLE IF NOT EXISTS anomaly_state (
    key   TEXT PRIMARY KEY,               -- "ewma:rx", "known_mac:aa:bb:…", "seeded"
    value TEXT NOT NULL,                  -- JSON
    ts    INTEGER NOT NULL
);
```

```python
@dataclass class SpoolRow: id: int; ts: int; topic: str; payload: str; qos: int

class Spool:
    def __init__(self, path: Path): ...                # one connection, check_same_thread=False + RLock
    def append(self, topic: str, payload_json: str, qos: int, ts: int) -> int
    def mark_published(self, row_id: int) -> None
    def pending_batch(self, limit: int = 500) -> list[SpoolRow]   # WHERE published=0 ORDER BY id
    def sweep_retention(self, max_rows: int, max_age_hours: int) -> int  # returns rows deleted
    def state_get(self, key: str) -> Any | None
    def state_set(self, key: str, value: Any) -> None
    def close(self) -> None
```

Retention semantics (sweep job every 10 min): delete `published=1` older than 1 h; delete `published=0` older than `max_age_hours`; if total rows > `max_rows`, delete oldest pending first — **the sensor degrades by dropping oldest history, never by growing unbounded**. `PRAGMA incremental_vacuum(200)` per sweep; full `VACUUM` never runs automatically (SD-card I/O spike). Mid→row-id mapping: `Pipeline` keeps an in-memory `{mid: row_id}` dict, entries dropped on ack; on process restart unacked rows are simply pending again (QoS 1 → possible duplicate delivery; the desktop side is idempotent, §7.4).

### 3.5 `pipeline.py`

**Responsibility:** the single emit path.

```python
class Pipeline:
    def __init__(self, mqtt: MqttClient, spool: Spool, exporters: list[Exporter],
                 sensor_id: str, base_topic: str,
                 clock: Callable[[], int] = lambda: int(time.time())): ...
    def emit(self, topic_suffix: str, payload: dict,
             qos: int = 1, retain: bool = False) -> None
    def drain(self) -> None            # replay pending_batch() loop; called on reconnect + every 60 s
    def stop(self) -> None
```

`emit()` behaviour (normative order):
1. `payload.setdefault("ts", clock())`; `payload.setdefault("sensor_id", sensor_id)`.
2. Full topic = `f"{base_topic}/sensor/{safe_segment(sensor_id)}/{topic_suffix}"` (suffix segments already sanitized by callers via `safe_segment`).
3. Hand payload to each exporter (never raises outward).
4. If `retain`: publish directly (not spooled). Else: `row_id = spool.append(...)`; publish; on `mid` map `mid → row_id` for the ack callback.
5. Thread-safe via one internal `Lock` (emit is called from sampler, executor, and paho threads).

### 3.6 `probes/ping.py`

**Responsibility:** continuous ICMP sampling and window statistics — the stability-monitoring core.

```python
@dataclass class PingWindow:
    target: str; window_s: int; sent: int; received: int
    rtt_ms: float; rtt_min_ms: float; rtt_max_ms: float
    jitter_ms: float; loss_pct: float

def compute_window(samples: list[float | None], window_s: int, target: str) -> PingWindow
    # None = timeout. rtt_ms = mean of successes; jitter_ms = mean absolute consecutive
    # difference (RFC 3550 style); loss_pct = 100 * timeouts/sent. Pure function — the unit-test surface.

class PingSampler(threading.Thread):
    def __init__(self, targets: list[str], interval_s: float, window_s: int,
                 on_window: Callable[[PingWindow], None],
                 ping_fn: Callable[[str, float], float | None] = _icmplib_ping,
                 clock: Callable[[], float] = time.monotonic): ...
    def heartbeat_age(self) -> float
    def stop(self) -> None
```

`_icmplib_ping(target, timeout_s) -> float | None`: `icmplib.ping(target, count=1, timeout=timeout_s, privileged=_PRIVILEGED)` → `rtt` in ms or None. `_PRIVILEGED` is probed once at startup (try a raw-socket ping; on `PermissionError` fall back to unprivileged DGRAM mode — works when the sysctl drop-in from §6 is installed). Targets iterate round-robin inside one thread; per-target deadline = drift-free monotonic. Library: **icmplib ≥ 3.0**.

### 3.7 `probes/dns_probe.py`, `probes/discovery.py`, `probes/system_metrics.py`

**`dns_probe.py`** — no dnspython; a fixed A-query datagram built with `struct` (~40 lines):

```python
@dataclass class DnsResult: resolver: str; query: str; lookup_ms: float; success: bool
def probe(resolver_ip: str, qname: str, timeout_s: float = 3.0) -> DnsResult
```
Random 16-bit transaction ID, QTYPE A, QCLASS IN; success = any response with matching ID and RCODE 0 within timeout; latency = send→receive wall time. UDP socket, stdlib only.

**`discovery.py`** — ARP + ICMP + mDNS **without scapy**:

```python
@dataclass class DiscoveryResult:
    devices: list[dict]      # {"mac","ip","hostname","vendor","sources",["arp","mdns"],"first_seen","last_seen"}
    joined: list[dict]; left: list[dict]

class Discovery:
    def __init__(self, cfg: DiscoveryCfg, state: Spool,
                 sweep_fn=None, neigh_fn=None, mdns_fn=None): ...   # injectable for tests
    def run_cycle(self) -> DiscoveryResult
```

Cycle algorithm (normative):
1. Resolve subnet: `"auto"` → the /24 of the default-route interface (parse `ip route get 1.1.1.1` or psutil addrs), else the configured CIDR (max /22 — refuse larger).
2. `_icmp_sweep(cidr)`: icmplib `ping(count=1, timeout=1)` across hosts, ≤ 64 concurrent via a semaphore. The sweep's real job is forcing the **kernel** to ARP-resolve every live host.
3. `_read_neighbor_table()`: parse `/proc/net/arp` (skip incomplete `00:00:…` entries and flags ≠ 0x2) → `{ip: mac}`. This yields exactly what `arp-scan` would, with zero extra privileges — a file read.
4. If `use_arp_scan` and the binary exists: merge `arp-scan --interface … --numeric --quiet {cidr}` output (finds ICMP-silent devices). Optional accelerator only; apt-installable.
5. If `mdns_enabled`: query the persistent `zeroconf` listener's cache (`_services._dns-sd._udp` browse running since startup) → `{ip: hostname}` merge.
6. Vendor: OUI prefix lookup against a bundled `oui_small.csv` (top ~2 000 consumer OUIs, ~60 KB; the desktop app does its own full vendor enrichment on ingest, so the sensor's vendor field is best-effort).
7. Diff against `state` (`known_mac:{mac}` keys): compute `joined` / `left` (left = absent for 3 consecutive cycles — a `miss_count` per MAC in state, reset on sight). Persist first_seen/last_seen.

**`system_metrics.py`**:

```python
def read_cpu_temp() -> float | None     # subprocess vcgencmd measure_temp; fallback
                                        # /sys/class/thermal/thermal_zone0/temp; None off-Pi
def snapshot(iface: str | None, prev: NetCounters | None) -> tuple[dict, NetCounters]
    # dict = the §4 "system" payload minus ts/sensor_id:
    # cpu_temp_c, cpu_pct (psutil.cpu_percent(interval=None)), load_1m, mem_used_pct,
    # disk_used_pct (root fs), rx_bytes_per_s, tx_bytes_per_s (delta vs prev counters),
    # logger_rss_mb (psutil.Process().memory_info().rss)
```
Library: **psutil ≥ 5.9**; `vcgencmd` via `subprocess.run(timeout=2)`.

### 3.8 `anomaly.py`

**Responsibility:** four deterministic rules; hysteresis; state persisted in `anomaly_state` so restarts never re-fire storms.

```python
class HysteresisRule:
    def __init__(self, fire_after: int, clear_after: int): ...
    def update(self, breached: bool) -> str | None      # returns "fired" | "cleared" | None

class AnomalyEngine:
    def __init__(self, cfg: AnomalyCfg, state: Spool, emit: Callable[[dict], None]): ...
    def on_ping_window(self, w: PingWindow) -> None     # rules 2 & 3, per-target state
    def on_system(self, snap: dict) -> None             # rule 4
    def on_discovery(self, res: DiscoveryResult) -> None# rule 1
    def persist(self) -> None                           # EWMA → state; every 5 min + shutdown
```

| # | Rule | Severity | Default trigger | Notes |
|---|---|---|---|---|
| 1 | `new_device` | INFO | MAC with no `known_mac:` state key | first cycle after fresh install seeds silently (`seeded` flag) — a reboot never re-announces the whole LAN |
| 2 | `packet_loss` | WARNING (CRITICAL at 100 %) | `loss_pct ≥ 10.0` for 3 consecutive windows; clear after 3 clean | per-target |
| 3 | `high_latency` | WARNING | `rtt_ms ≥ 150.0`, same hysteresis machinery | per-target |
| 4 | `traffic_change` | WARNING | rate > `max(ewma × 4.0, 50 000 B/s)` for 3 ticks | per-direction EWMA, α = 0.05, persisted |

Every fire/clear emits one `anomaly` payload (§4.8); `cleared` carries severity `HEALTHY` — the app's exact severity vocabulary (`INFO|WARNING|CRITICAL|HEALTHY`), so the ingest side builds `AlertFired` with **no translation table**.

### 3.9 `exporters.py`, `api.py`, `main.py`

**`exporters.py`** — secondary integration (CSV/JSON files):

```python
class Exporter(Protocol):
    def write(self, data_class: str, payload: dict) -> None
    def sweep(self, retention_days: int) -> None

class CsvExporter(Exporter): ...    # export/{data_class}-YYYY-MM-DD.csv; header from sorted keys
class JsonlExporter(Exporter): ...  # export/{data_class}-YYYY-MM-DD.jsonl; one JSON object per line
```
`data_class` ∈ `ping|dns|system|devices|anomaly`. Both off by default. Retention sweep runs on the scheduler.

**`api.py`** — optional read-only REST (off by default), stdlib `http.server.ThreadingHTTPServer`:
- `GET /health` → `{"status":"ok","sensor_id":…,"uptime_s":…,"mqtt_connected":bool,"spool_pending":int}`
- `GET /latest` → last payload per data class (in-memory cache the Pipeline maintains)
- `GET /devices` → last `devices/snapshot` payload
No auth (localhost bind by default); binding to non-loopback requires the config to set it explicitly, and the README flags the risk.

**`main.py`** — composition root:

```python
def main() -> int                     # argparse: --config PATH, --check (validate config, exit), --version
class App:
    def __init__(self, cfg: LoggerConfig): ...   # builds spool, mqtt, pipeline, probes, engine, scheduler
    def start(self) -> None
    def stop(self) -> None            # order: probes → scheduler → engine.persist() → pipeline → mqtt → spool
    def watchdog_ok(self) -> bool     # all heartbeat ages < 3× their interval
```
Main loop: `sd_notify("READY=1")`, then every 30 s `sd_notify("WATCHDOG=1")` iff `watchdog_ok()`. SIGTERM → clean stop; SIGHUP → `scheduler.trigger_now("discovery")`. Library: **sdnotify** (3 KB, no libsystemd link).

### 3.10 Dependency list (pinned in `requirements.txt`)

| Package | Constraint | Why |
|---|---|---|
| paho-mqtt | `>=2.0,<3` | current API (CallbackAPIVersion.VERSION2) |
| psutil | `>=5.9` | system metrics; aarch64 wheels on PyPI |
| PyYAML | `>=6.0` | config |
| icmplib | `>=3.0` | pure-Python ICMP, privileged + unprivileged modes |
| zeroconf | `>=0.130` | mDNS browse, pure Python |
| sdnotify | `>=0.3` | watchdog integration |

Dev-only: `pytest`, `ruff`, `mypy`. **Nothing else** — no scapy, no dnspython, no requests, no Flask.

---

## 4. Data Formats & MQTT Schema

### 4.1 Topic tree

All sensor topics live under the desktop app's existing base topic with a reserved segment:

```
netsentinel/sensor/{sensor_id}/…
```

This cannot collide with the app's outbound topics (`netsentinel/status`, `netsentinel/devices/…`, `netsentinel/alerts/…`, `netsentinel/uptime/…`), supports any number of sensors, and one wildcard — **`netsentinel/sensor/+/#`** — subscribes to everything. `sensor_id` and target/resolver segments are sanitized with `safe_segment()` (`: . / + #` and whitespace → `_`), identical to the desktop app's `_safe()`.

| Topic suffix | QoS | Retain | Cadence | Payload |
|---|---|---|---|---|
| `status` | 1 | **yes** | LWT + connect + every `heartbeat_interval_s` (300 s) | §4.2 |
| `ping/{target}` | 1 | no | per report window (30 s) | §4.3 |
| `dns/{resolver}` | 1 | no | per DNS cycle (60 s) | §4.4 |
| `system` | 1 | no | 60 s | §4.5 |
| `devices/snapshot` | 1 | **yes** | after each discovery cycle (300 s) | §4.6 |
| `devices/event` | 1 | no | on join/leave only | §4.7 |
| `anomaly` | 1 | no | on rule fire/clear | §4.8 |

QoS 1 everywhere (the spool + broker dedup make it safe; QoS 0 would silently drop spooled replays). Retain only on idempotent state (`status`, `devices/snapshot`); time-series are never retained. Retained topics are not spooled.

Payload conventions (normative, matching the desktop codebase): **snake_case keys; numeric epoch-seconds field named `ts`; units suffixed into key names** (`rtt_ms`, `loss_pct`, `cpu_temp_c`).

### 4.2 `status` (retained; LWT payload is the same shape with `"state": "offline"`)

```json
{"state": "online", "ts": 1783300000, "sensor_id": "pi-garage",
 "version": "1.0.0", "uptime_s": 86211, "spool_pending": 0}
```

### 4.3 `ping/{target}` — one aggregated window (30 samples → 1 message)

```json
{"ts": 1783300030, "sensor_id": "pi-garage", "target": "1.1.1.1",
 "window_s": 30, "sent": 30, "received": 29,
 "rtt_ms": 12.4, "rtt_min_ms": 9.1, "rtt_max_ms": 41.0,
 "jitter_ms": 2.8, "loss_pct": 3.3}
```

### 4.4 `dns/{resolver}`

```json
{"ts": 1783300060, "sensor_id": "pi-garage", "resolver": "192.168.1.1",
 "query": "example.com", "lookup_ms": 18.7, "success": true}
```

### 4.5 `system`

```json
{"ts": 1783300060, "sensor_id": "pi-garage", "cpu_temp_c": 52.1,
 "cpu_pct": 3.5, "load_1m": 0.12, "mem_used_pct": 34.2, "disk_used_pct": 41.0,
 "rx_bytes_per_s": 15234.0, "tx_bytes_per_s": 4021.0, "logger_rss_mb": 41.3}
```

### 4.6 `devices/snapshot` (retained = "current inventory as this sensor sees it")

```json
{"ts": 1783300120, "sensor_id": "pi-garage", "device_count": 14,
 "devices": [
   {"mac": "aa:bb:cc:dd:ee:ff", "ip": "192.168.1.23", "hostname": "shelly-plug",
    "vendor": "Espressif", "sources": ["arp", "mdns"],
    "first_seen": 1783200000, "last_seen": 1783300120}
 ]}
```
Device dicts are intentionally shape-compatible with `DeviceTracker.process_scan()` (`mac/ip/hostname/vendor`; unknown keys ignored). A /24 snapshot is ≤ ~40 KB JSON.

### 4.7 `devices/event`

```json
{"ts": 1783300120, "sensor_id": "pi-garage", "event": "joined",
 "mac": "aa:bb:cc:dd:ee:ff", "ip": "192.168.1.23",
 "hostname": "shelly-plug", "vendor": "Espressif"}
```
`event` ∈ `joined | left`. Display-only on the desktop side (inventory truth comes from the snapshot → `process_scan` diff).

### 4.8 `anomaly`

```json
{"ts": 1783300125, "sensor_id": "pi-garage", "rule": "packet_loss",
 "severity": "WARNING", "state": "fired", "target": "1.1.1.1",
 "message": "Packet loss 18.5% on 1.1.1.1 (threshold 10%, 3 consecutive windows)",
 "value": 18.5}
```
`rule` ∈ `new_device | packet_loss | high_latency | traffic_change`; `severity` ∈ `INFO | WARNING | CRITICAL | HEALTHY`; `state` ∈ `fired | cleared` (cleared ⇒ severity HEALTHY).

### 4.9 How NetSentinel subscribes and parses

Subscription: `netsentinel/sensor/+/#`, QoS 1. Topic parse (in the ingest worker):

```python
# netsentinel/sensor/{sensor_id}/{data_class}[/{subpath}]
_, _, sensor_id, data_class, *rest = topic.split("/")
subpath = rest[0] if rest else None      # ping target, dns resolver, "snapshot"/"event"
```

The worker emits `message_received({"sensor_id", "data_class", "subpath", "payload"})`; routing per class is §7.4. Parsers must tolerate unknown keys (forward compatibility) and clamp `ts` to `min(ts, now + 300)` (clock-skew guard; the Pi runs systemd-timesyncd, but a cold-boot Pi without RTC can briefly publish 1970 timestamps — payloads with `ts < now − 30 days` are stored but excluded from "last seen" computations).

---

## 5. Configuration (YAML)

Location on the Pi: `/etc/netsentinel-logger/config.yaml` (0640 `root:netsentinel`). Override with `--config`. Secrets are **not** in this file (§6.1). This exact content ships as `logger/config.example.yaml` and is the template the setup wizard renders:

```yaml
# NetSentinel Remote Sensor Logger configuration
# Reload: the service reads this file at startup only — `systemctl restart netsentinel-logger`.
# Any string value may reference an environment variable as ${VAR_NAME}.

sensor:
  # Unique id for this sensor. Used in every MQTT topic and payload.
  # Allowed: letters, digits, dash, underscore. Default: the Pi's hostname.
  sensor_id: pi-garage
  # Free-text location tag, included in the status payload. Optional.
  location: "Garage rack, shelf 2"

mqtt:
  # Broker to publish to. In broker-on-Pi mode this is localhost.
  host: 127.0.0.1
  port: 1883
  username: netsentinel
  # Password comes from the environment (systemd EnvironmentFile) — never write it here.
  password: ${NSL_MQTT_PASSWORD}
  # Must match the NetSentinel desktop app's base topic (Settings → MQTT). Default "netsentinel".
  base_topic: netsentinel
  # Retained status heartbeat interval, seconds.
  heartbeat_interval_s: 300
  # Optional TLS to the broker. Off by default (LAN deployment, password auth).
  tls_enabled: false
  tls_ca_cert: null            # path to CA bundle when tls_enabled: true

ping:
  # Stability monitoring targets. Mix LAN (router) and WAN (public anycast) targets
  # to distinguish "my WiFi is bad" from "my ISP is bad".
  targets:
    - 192.168.1.1
    - 1.1.1.1
    - 8.8.8.8
  interval_s: 1.0              # one ICMP echo per target per interval
  report_window_s: 30          # samples aggregated into one MQTT message per target

dns:
  # Resolvers to measure lookup latency against (raw UDP query, not the system resolver).
  resolvers:
    - 192.168.1.1
    - 1.1.1.1
  query_name: example.com
  interval_s: 60

discovery:
  enabled: true
  # "auto" = the /24 of the default-route interface. Or an explicit CIDR (max /22).
  subnet: auto
  interval_s: 300
  # Use the arp-scan binary if installed (finds ICMP-silent devices). Optional:
  #   sudo apt install arp-scan
  use_arp_scan: false
  mdns_enabled: true

system:
  interval_s: 60
  # "auto" = default-route interface; used for rx/tx byte rates.
  interface: auto

anomaly:
  new_device:
    enabled: true              # INFO event when an unseen MAC appears
  packet_loss:
    enabled: true
    threshold_pct: 10.0
    fire_after: 3              # consecutive breached windows to fire (~90 s)
    clear_after: 3
  high_latency:
    enabled: true
    threshold_ms: 150.0
    fire_after: 3
    clear_after: 3
  traffic_change:
    enabled: true
    ewma_alpha: 0.05
    ratio: 4.0                 # fire when rate > ewma * ratio
    floor_bytes_per_s: 50000   # suppress noise on near-idle links

buffer:
  path: /var/lib/netsentinel-logger/spool.db
  max_rows: 200000             # ≈ 60–80 MB; oldest pending rows dropped beyond this
  max_age_hours: 72            # pending rows older than this are dropped

export:
  # Secondary integration: local CSV / JSONL files (one per data class per day).
  csv_enabled: false
  jsonl_enabled: false
  dir: /var/lib/netsentinel-logger/export
  rotate_daily: true
  retention_days: 14

api:
  # Optional read-only HTTP API (GET /health, /latest, /devices). No auth — keep it on loopback.
  enabled: false
  bind: 127.0.0.1
  port: 8787

logging:
  level: INFO                  # DEBUG | INFO | WARNING | ERROR
  file: null                   # null = stderr → journald (recommended); or a path under /var/lib
```

Secrets file `/etc/netsentinel-logger/secrets.env` (0600 `root:root`, loaded by systemd `EnvironmentFile`):

```bash
NSL_MQTT_PASSWORD=<generated-by-wizard-or-admin>
```

Rationale: a keyring needs a session D-Bus/unlock that a headless Pi doesn't have; a root-only env-file is the standard systemd secret pattern and keeps the shareable YAML free of secrets.

---

## 6. Installation — Zero-Touch Provisioning & systemd

### 6.1 The zero-touch flow (primary path — user never logs into the Pi)

```
User                          NetSentinel desktop app                    Raspberry Pi
────                          ───────────────────────                    ────────────
1. Flash Raspberry Pi OS
   Lite 64-bit (Bookworm)
   with Raspberry Pi Imager;
   keep SD card in the PC
                              2. Remote Sensors → "Provision New
                                 Sensor" wizard:
                                 • detects the SD card's FAT32 boot
                                   partition (config.txt + cmdline.txt)
                                 • collects: sensor name/location,
                                   Ethernet-or-WiFi, broker mode,
                                   ping targets
                                 • generates a random MQTT password →
                                   writes it to the SD card AND the
                                   app's OS keyring (user never sees it)
                                 • writes firstrun.sh, userconf.txt,
                                   payload dir (§6.2) to the FAT partition
3. Eject SD, insert in Pi,
   power on
                                                                         4. Boot 1: firstrun.sh (stage 1,
                                                                            no network needed) → reboot
                                                                         5. Boot 2: netsentinel-provision
                                                                            .service (stage 2): apt + pip
                                                                            install, broker, avahi, enable
                                                                            logger → sensor starts publishing
                              6. Ingest worker sees retained
                                 status=online → sensor appears in
                                 the Remote Sensors table
```

Why not a custom OS image: pi-gen CI builds, ~500 MB hosted artifacts per release, users trusting a third-party OS image, patch staleness — and per-user config (WiFi/credentials/name) still has to be injected via the boot partition afterwards. Stock-OS + firstrun achieves the identical UX. A prebaked image (removing the firstboot-internet requirement) is documented as an optional future phase.

The key enabler: the Pi's **boot partition is FAT32**, so the Windows desktop app can write provisioning files onto it directly. This is the same mechanism Raspberry Pi Imager itself uses.

### 6.2 SD-card payload written by the wizard

Boot partition (FAT32 root) after provisioning:

```
firstrun.sh                    ← stage-1 script (below)
cmdline.txt                    ← original line + appended:
                                 " systemd.run=/boot/firmware/firstrun.sh
                                   systemd.run_success_action=reboot
                                   systemd.unit=kernel-command-line.target"
userconf.txt                   ← "netadmin:<sha512-crypt hash>" — break-glass login,
                                 generated password shown ONCE in the wizard
ssh                            ← empty file, only if "enable SSH" was checked (default off)
netsentinel/
├── netsentinel_logger-1.0.0.tar.gz   ← sdist bundled inside the NetSentinel build
├── requirements.txt                  ← pinned deps (installed from PyPI at firstboot)
├── config.yaml                       ← rendered from §5 template with wizard answers
├── secrets.env                       ← NSL_MQTT_PASSWORD=… (deleted from FAT by stage 2)
├── netsentinel-logger.service        ← §6.5
├── netsentinel-provision.service     ← stage-2 unit (§6.3)
├── provision.sh                      ← stage-2 script (§6.3)
├── install.sh                        ← shared install logic (§6.6)
├── 50-netsentinel-logger.conf        ← sysctl ping_group_range drop-in
├── mosquitto-netsentinel.conf        ← broker-on-Pi only (§6.4)
├── mosquitto_passwd.plain            ← "netsentinel:<password>" (consumed + deleted by stage 2)
├── avahi-netsentinel.service         ← mDNS advertisement XML (§6.4)
└── wifi.nmconnection                 ← NetworkManager keyfile (WiFi only; moved off FAT by stage 1)
```

`userconf.txt` is the officially supported headless user-creation mechanism on Raspberry Pi OS; the hash is SHA-512-crypt, produced by a small vendored pure-Python implementation in the wizard (`sha512_crypt(password, salt)` — ~60 lines, golden-tested against `openssl passwd -6` output). Plaintext secrets live on the FAT partition only between wizard-write and stage-2 consumption (minutes); stage 2 deletes them and the README states this window explicitly.

**`firstrun.sh` (stage 1 — early boot, no network, must be fast and infallible):**

```sh
#!/bin/sh
# NetSentinel sensor provisioning, stage 1 (early boot via systemd.run)
set -e
BOOT=/boot/firmware
PAYLOAD=$BOOT/netsentinel
log() { echo "[nsl-firstrun] $1" >> "$PAYLOAD/firstboot.log"; }

log "stage 1 start $(date -u +%FT%TZ)"
# 1. Hostname = netsentinel-{sensor_id} (also becomes the .local mDNS name)
SENSOR_ID=$(sed -n 's/^ *sensor_id: *//p' "$PAYLOAD/config.yaml" | head -1)
echo "netsentinel-${SENSOR_ID}" > /etc/hostname
sed -i "s/127.0.1.1.*/127.0.1.1\tnetsentinel-${SENSOR_ID}/" /etc/hosts

# 2. WiFi (if provisioned): install NetworkManager keyfile + regulatory domain
if [ -f "$PAYLOAD/wifi.nmconnection" ]; then
    raspi-config nonint do_wifi_country "$(sed -n 's/^#country=//p' "$PAYLOAD/wifi.nmconnection")" || true
    install -m 600 -o root -g root "$PAYLOAD/wifi.nmconnection" \
        /etc/NetworkManager/system-connections/netsentinel.nmconnection
    rm -f "$PAYLOAD/wifi.nmconnection"
fi

# 3. Move payload off the FAT partition; arm stage 2
mkdir -p /opt/netsentinel-provision
cp -r "$PAYLOAD"/. /opt/netsentinel-provision/
install -m 644 /opt/netsentinel-provision/netsentinel-provision.service \
    /etc/systemd/system/netsentinel-provision.service
systemctl enable netsentinel-provision.service

# 4. Disarm stage 1: strip our args from cmdline.txt
sed -i 's| systemd.run=[^ ]*||; s| systemd.run_success_action=[^ ]*||; s| systemd.unit=kernel-command-line.target||' \
    "$BOOT/cmdline.txt"
rm -f "$BOOT/firstrun.sh"
log "stage 1 done — rebooting"
exit 0     # systemd.run_success_action=reboot
```

**Why two stages:** `systemd.run=` executes in early boot, before networking — the wrong context for apt/pip. Stage 1 does only offline work and arms a normal one-shot unit; stage 2 runs on the next boot with `network-online.target` properly ordered. This mirrors how Raspberry Pi Imager's own customization behaves and is robust against slow WiFi association.

### 6.3 Stage 2 — `netsentinel-provision.service` + `provision.sh`

```ini
[Unit]
Description=NetSentinel sensor firstboot provisioning (stage 2)
After=network-online.target time-sync.target
Wants=network-online.target
ConditionPathExists=/opt/netsentinel-provision/provision.sh

[Service]
Type=oneshot
ExecStart=/bin/sh /opt/netsentinel-provision/provision.sh
RemainAfterExit=no
TimeoutStartSec=15min

[Install]
WantedBy=multi-user.target
```

`provision.sh` behaviour (normative; full script in `deploy/`):
1. All output `tee`'d to `/opt/netsentinel-provision/firstboot.log` **and copied to `/boot/firmware/netsentinel/firstboot.log` at the end of every run, success or failure** — if provisioning fails, the user puts the SD card back in the PC and the wizard's "Troubleshoot from SD card" button reads this log. A `provision-status.json` (`{"state": "ok"|"failed", "step": …, "ts": …}`) is written next to it for machine parsing.
2. Wait for DNS (`getent hosts deb.debian.org`, retry 30 × 10 s).
3. `apt-get update && apt-get install -y python3-venv avahi-daemon` (+ `mosquitto` in broker-on-Pi mode). Retry apt once on failure.
4. Run `install.sh` (§6.6): user, dirs, venv, pip install sdist + pinned requirements, sysctl, config/secrets/unit installation.
5. Broker-on-Pi mode: install `mosquitto-netsentinel.conf` → `/etc/mosquitto/conf.d/`; `mosquitto_passwd -c -b /etc/mosquitto/netsentinel_passwd netsentinel "<pw>"` using `mosquitto_passwd.plain`, then delete the plaintext; `systemctl enable --now mosquitto`.
6. Install `avahi-netsentinel.service` XML → `/etc/avahi/services/`.
7. `systemctl enable --now netsentinel-logger.service`.
8. Delete `secrets.env` + any plaintext from `/boot/firmware/netsentinel/` (keep `config.yaml` copy for reference, log, status file). `systemctl disable netsentinel-provision.service`. Failure path: status=failed + step name; the unit stays enabled so the next boot retries, up to 3 attempts (`attempt` counter in status file), then gives up and leaves the log.

### 6.4 Broker-on-Pi and mDNS advertisement

`mosquitto-netsentinel.conf`:

```
listener 1883
allow_anonymous false
password_file /etc/mosquitto/netsentinel_passwd
```

`avahi-netsentinel.service` (advertises the broker + identifies the sensor; the hostname `netsentinel-{id}.local` gives the app a DHCP-proof address):

```xml
<?xml version="1.0" standalone='no'?><!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">NetSentinel Sensor %h</name>
  <service>
    <type>_netsentinel-sensor._tcp</type>
    <port>1883</port>
    <txt-record>sensor_id={SENSOR_ID}</txt-record>
    <txt-record>version=1.0.0</txt-record>
  </service>
</service-group>
```

**Offline-detection semantics per mode** (normative, the desktop UI must reflect this): broker-on-Pi → if the Pi dies the broker dies with it, so "sensor offline" = ingest client TCP disconnect (LWT can't outlive the broker). Shared/existing broker → LWT works normally; offline = retained `status` flips to `offline`.

### 6.5 Runtime systemd unit — `netsentinel-logger.service`

```ini
[Unit]
Description=NetSentinel Remote Sensor Logger
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
User=netsentinel
Group=netsentinel
EnvironmentFile=-/etc/netsentinel-logger/secrets.env
ExecStart=/opt/netsentinel-logger/venv/bin/netsentinel-logger --config /etc/netsentinel-logger/config.yaml
Restart=always
RestartSec=5
WatchdogSec=90
# Privileges: raw ICMP sockets only
AmbientCapabilities=CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_RAW
NoNewPrivileges=yes
# Hardening
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/netsentinel-logger
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
# Resource backstops (targets are far lower — see §1.4)
MemoryMax=150M
CPUQuota=50%

[Install]
WantedBy=multi-user.target
```

Notes: `Type=notify` + `WatchdogSec=90` — the main thread pets the watchdog every 30 s only when all worker heartbeats are fresh, so a hung thread gets the whole service restarted by systemd. Add `AF_PACKET` to `RestrictAddressFamilies` only if the `arp-scan` accelerator is enabled. The env-file dash prefix makes it optional (anonymous-broker labs).

### 6.6 Manual install path (`deploy/install.sh` — for SSH users; also invoked by stage 2)

```bash
# as root, with logger sdist + requirements.txt + deploy/ files present
useradd --system --home /var/lib/netsentinel-logger --shell /usr/sbin/nologin netsentinel || true
install -d -m 750 -o root  -g netsentinel /etc/netsentinel-logger
install -d -m 750 -o netsentinel -g netsentinel /var/lib/netsentinel-logger
python3 -m venv /opt/netsentinel-logger/venv
/opt/netsentinel-logger/venv/bin/pip install --no-cache-dir -r requirements.txt netsentinel_logger-*.tar.gz
install -m 644 50-netsentinel-logger.conf /etc/sysctl.d/ && sysctl --system   # unprivileged-ICMP fallback
install -m 640 -g netsentinel config.yaml /etc/netsentinel-logger/
install -m 600 secrets.env /etc/netsentinel-logger/                            # or create manually
install -m 644 netsentinel-logger.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now netsentinel-logger
```

Post-install verification (both paths): `/opt/netsentinel-logger/venv/bin/python /opt/netsentinel-provision/tools/smoke.py --broker localhost` (§8.4), or from the desktop just watch the Remote Sensors page.

Sysctl drop-in `50-netsentinel-logger.conf`:

```
net.ipv4.ping_group_range = 0 2147483647
```

---

## 7. Integration Guide — NetSentinel Desktop App

### 7.1 Broker recommendations

| Deployment | Recommendation |
|---|---|
| Default (one Pi, no infra) | **Mosquitto on the Pi** — installed automatically by provisioning; app connects to `netsentinel-{id}.local:1883` |
| Multiple sensors | One shared Mosquitto on an always-on LAN host (or one of the Pis); wizard's "Use existing broker" mode |
| Home Assistant users | Reuse the HA Mosquitto add-on; also lets the app's existing outbound MQTT publisher and this sensor share one broker |

Auth: username/password minimum (`allow_anonymous false`); TLS optional (the logger supports it; the app's client would need a matching `tls_set` — noted as future work since the app has no TLS today).

### 7.2 `workers/mqtt_ingest_worker.py`

QThread modeled on `workers/syslog_worker.py`. **One paho client per configured sensor** (broker-on-Pi means N sensors = N brokers), each with `client_id=f"netsentinel-ingest-{sensor_id}"` — distinct from the outbound publisher's `netsentinel` client id, or the broker kicks one connection off.

```python
class MqttIngestWorker(QThread):
    message_received = pyqtSignal(dict)   # {"sensor_id","data_class","subpath","payload"}
    sensor_online    = pyqtSignal(str)    # sensor_id
    sensor_offline   = pyqtSignal(str)
    error            = pyqtSignal(str)

    def __init__(self, sensors: list[SensorEntry], parent=None): ...
    def run(self): ...                    # connect all clients, loop until stop()
    def stop(self): ...                   # clean disconnects, quit thread
    def reload_sensors(self, sensors: list[SensorEntry]) -> None
```

Behaviour: subscribe `f"{base_topic}/sensor/+/#"` QoS 1 per client; paho lazy import with the same `try/except ImportError` guard as `modules/mqtt_publisher.py`; reconnect backoff via `reconnect_delay_set(1, 120)`; on repeated connect failure re-resolve `netsentinel-{id}.local` (Windows resolves mDNS natively; fall back to a zeroconf browse of `_netsentinel-sensor._tcp` and match the `sensor_id` TXT record — DHCP-proof). Offline detection per §6.4 semantics. Wired in `app.py` after `window = Dashboard(...)` (RULE-DW2), gated on `mqtt/ingest_enabled`; add `paho.mqtt.client` to `NetSentinel.spec` hiddenimports (RULE-B1).

### 7.3 `modules/sensor_registry.py` (settings + secrets)

- QSettings key `sensors/registry` — JSON list of `{"id","location","broker_host","broker_port","username","mode"}` (`mode` ∈ `on_pi | existing`).
- QSettings key `mqtt/ingest_enabled` — master toggle.
- Passwords: keyring service `"NetSentinel"`, key `f"sensor/{id}/mqtt_password"` (RULE 22-A — never in QSettings/INI).

```python
@dataclass class SensorEntry: id: str; location: str; broker_host: str;
                              broker_port: int; username: str; mode: str
class SensorRegistry:
    def all(self) -> list[SensorEntry]
    def add(self, e: SensorEntry, password: str) -> None
    def remove(self, sensor_id: str) -> None     # also deletes the keyring entry
    def password_for(self, sensor_id: str) -> str | None
```

### 7.4 Routing table (dashboard handler `_on_sensor_message`, mirrors `_on_hardware_plugin_result` conventions)

| `data_class` | Destination (existing symbols — all verified) | Notes |
|---|---|---|
| `ping`, `dns` | `MetricStore.record_rtt(host=f"{sensor_id}:{target}", rtt_ms=…, loss_pct=…, jitter_ms=…, ts=…)` | the `sensor_id:` prefix namespaces remote series away from local probes; DNS maps `lookup_ms→rtt_ms`, `success=false → loss_pct=100.0` |
| `devices` / `snapshot` | `DeviceTracker.process_scan(payload["devices"])` | the **only** writer for scan-driven inventory (single-writer invariant — never call `upsert_known_device`/`record_ip_observation` directly). Retained-message replay on app start is safe: `process_scan` is a diffing upsert |
| `devices` / `event` | Log Hub display only | inventory truth comes from the snapshot diff |
| `system`, `status` | `MetricStore.record_plugin_snapshot(f"sensor:{sensor_id}", payload)` + `LogHubPage.add_plugin_entry(...)`; `update_plugin_sources([f"sensor:{sensor_id}"])` on first sight | the dynamic-source path gives a per-sensor Log Hub chip and a per-source "Logging to DB" toggle for free |
| `anomaly`, `state=="fired"` | `AlertFired(rule_name=f"Sensor {sensor_id}: {rule}", rule_type="SENSOR", host=payload.get("target", sensor_id), message=…, severity=…, ts=…, value=…)` → `MetricStore.record_alert_fired(...)` + `NotificationRouter.dispatch(alert)` + `_show_alert_toast` | severity vocabulary matches 1:1, no mapping needed |
| `anomaly`, `state=="cleared"` | same, severity `HEALTHY` | resolution event |

Throttling: `system` snapshots persist to `plugin_log` at most once per `logging/plugin_<name>_interval` (existing Log Hub toggle machinery); `record_rtt` writes are already one-per-30 s-window per target — no extra throttle needed.

### 7.5 `ui/pages/remote_sensor_page.py` — Remote Sensors page

Registered in `_build_pro_nav()` under the **Extend** section (joins Hardware; no new rail icon needed — `plug`/`cpu` already exist in `_LUCIDE` if one is wanted). Layout:

- **Fleet table** (one row per registered sensor): Sensor ID, Location, State (● online / ● offline / ● never seen — GREEN/RED/BORDER per `ui/styles.py`), Last heartbeat ("N min ago"), CPU temp, RSS, Version, Broker. Fed live from the ingest worker's signals + latest `status`/`system` payloads.
- **Row context menu:** Open in Log Hub (filtered to `sensor:{id}` source) · View latest device snapshot · Remove sensor (deletes registry + keyring entries; confirm dialog).
- **Header actions:** "Provision New Sensor…" (opens the wizard) · "Ingest enabled" toggle (`mqtt/ingest_enabled`).
- Empty state: explainer panel ("A remote sensor is a Raspberry Pi that watches a network segment 24/7 and reports here…") + the provision button — consistent with the app's plain-English-first value.

### 7.6 `ui/widgets/sensor_setup_wizard.py` — Provision New Sensor wizard

QWizard pages (each page's normative behaviour):

1. **Prerequisites** — instructions + link to download Raspberry Pi Imager; "flash Raspberry Pi OS Lite (64-bit), then come back with the SD card still inserted". Detect-button rescans.
2. **SD card detection** — enumerate mounted volumes via `QStorageInfo.mountedVolumes()`; a candidate is a removable FAT/FAT32 volume whose root contains `config.txt` **and** `cmdline.txt`. Multiple candidates → user picks; zero → troubleshooting hints. **Never** offer non-removable drives.
3. **Sensor identity** — sensor id (validated `[a-z0-9-_]{1,32}`, default `pi-<random4>`), location text.
4. **Network** — Ethernet (nothing to configure) or WiFi (SSID, password, country code) → rendered into `wifi.nmconnection`.
5. **Broker** — radio: "Run the broker on this sensor (recommended)" (host becomes `netsentinel-{id}.local`) vs "Use an existing broker" (host/port/username/password fields). On-Pi mode generates username `netsentinel` + `secrets.token_urlsafe(24)` password.
6. **Monitoring defaults** — ping targets (prefilled: default gateway of the *current* PC network + 1.1.1.1 + 8.8.8.8), discovery on/off. Everything else uses config defaults; "advanced users can edit /etc/netsentinel-logger/config.yaml later".
7. **Review & write** — shows every file it will write; on confirm: render templates (bundled in the app build) → write to the FAT volume → patch `cmdline.txt` (idempotent: refuse if `systemd.run=` already present, offer "re-provision" which rewrites cleanly) → `SensorRegistry.add(entry, password)` → show the break-glass `userconf.txt` credentials **once** with a "copy" button.
8. **Done / watch** — "Eject the card, boot the Pi. First boot takes 3–6 minutes and needs internet." A status widget polls the ingest worker for the sensor's retained `status` topic and flips to ✓ when it arrives. Buttons: "Troubleshoot from SD card" (reads `netsentinel/provision-status.json` + `firstboot.log` from a re-inserted card and renders the failing step) · Close.

File generation is implemented as **pure functions** (`render_config_yaml(answers) -> str`, `render_firstrun(answers) -> str`, `patch_cmdline(existing: str) -> str`, `sha512_crypt(pw, salt) -> str`) so tests golden-test the outputs without an SD card (§8.4).

### 7.7 Desktop build changes

- `NetSentinel.spec`: add data files — logger sdist, `logger/requirements.txt`, `logger/deploy/*` templates; add `paho.mqtt.client` hiddenimport.
- `bump_version.py`: extend to also bump `logger/netsentinel_logger/__init__.py.__version__` and rebuild the sdist (RULE-R1 keeps versions in lockstep).

---

## 8. Performance & Robustness

### 8.1 Optimization techniques (all normative)

- **Aggregate before publishing** — windows, not packets (§1.2). ~4 000 msgs/day/sensor at defaults.
- **One SQLite connection**, WAL mode, `synchronous=NORMAL`; writes batched per emit; `incremental_vacuum` only — protects the SD card (the dominant Pi failure mode is flash wear).
- **No polling loops** — every thread blocks on a deadline or a socket; idle CPU is the ICMP send/recv only.
- **Persistent zeroconf listener** instead of per-cycle browse (browse startup is the expensive part).
- **Discovery concurrency capped** (semaphore 64) — a /22 sweep must not spike load or trip IDS.
- Log level INFO writes ~10 lines/hour steady-state; DEBUG is for diagnosis only.

### 8.2 Error-handling strategy

| Failure | Handling |
|---|---|
| Broker unreachable / MQTT drop | spool accumulates; paho auto-reconnect (1→120 s backoff); on reconnect `drain()` replays oldest-first in 500-row batches |
| Spool full | drop oldest pending rows (never grow, never crash); WARNING log line |
| One job raises | `_run_guarded` logs with traceback, job reschedules normally — one bad discovery cycle never kills the service |
| Thread hangs | its heartbeat goes stale → main thread stops petting the watchdog → systemd restarts the service (`Restart=always`, 5 s) |
| SQLite corruption (SD wear) | open fails → move file aside to `spool.db.corrupt-<ts>`, recreate empty, log CRITICAL — telemetry continuity beats history preservation |
| Pi clock skew at cold boot | desktop ingest clamps `ts` (§4.9); `time-sync.target` ordering on stage 2 |
| Config invalid | `--check` validates; service exits non-zero with the field-path error → visible in `systemctl status` and, during provisioning, in `firstboot.log` |
| vcgencmd missing (non-Pi host) | `cpu_temp_c: null`; everything else works — enables development on any Linux box |

### 8.3 Logging

Python `logging`, format `%(asctime)s %(levelname)s %(name)s: %(message)s`, to **stderr → journald** by default (`journalctl -u netsentinel-logger`); optional file handler (RotatingFileHandler 5 × 2 MB) only if `logging.file` is set. Never log secrets; log broker host but not password. Provisioning logs are separate (§6.3) and intentionally end up on the FAT partition where Windows can read them.

### 8.4 Testing

**Logger unit tests** (`logger/tests/`, own pytest root — never collected by the desktop suite): everything injected — `FakeClock` (manual advance), `FakeMqttClient` (records publishes; scripted connect/disconnect/ack sequences), canned `ping_fn`/`resolve_fn`/fixture ARP tables; **real SQLite** on `tmp_path` (fast, no reason to mock). Coverage priorities: spool replay ordering + cap eviction + crash recovery (kill between append and ack → row replays); anomaly hysteresis sequences + fresh-install seeding + EWMA persistence round-trip; window math on fixed vectors (including all-timeout and single-sample edges); scheduler no-drift under a jumping clock; **every §4 example payload validated against a checked-in schema dict** (`test_topics.py`) — this is the contract test both codebases share.

**Desktop-app tests** (repo `tests/`): ingest worker start/stop lifecycle (RULE-T2); topic-router unit tests feeding the §4 example payloads through `_on_sensor_message` against a mocked store (asserts the exact `record_rtt`/`process_scan`/`record_alert_fired` calls); wizard golden tests — `render_config_yaml`/`render_firstrun`/`patch_cmdline`/`sha512_crypt` outputs against checked-in expected files (no SD card, no Qt needed); registry round-trip with a mocked keyring.

**Hardware-in-loop:** `logger/tools/smoke.py` — run manually on the Pi after install: pings 1.1.1.1, one DNS probe, one discovery cycle, one system snapshot, publishes each to `--broker`, prints a pass/fail table, exit code for scripting. Referenced by §6.6 as the post-install check.

**Soak criterion:** 72 h run on a Pi 4 with defaults: RSS < 60 MB, no spool growth with broker up, clean replay after a 1 h broker outage, zero service restarts.

---

## Appendix A — Future work (explicitly out of scope for v1)

- Prebaked pi-gen OS image (removes the firstboot-internet requirement); CI-built, checksummed.
- TLS on the desktop app's MQTT clients (publisher + ingest) to match the logger's optional TLS.
- Sensor-side OTA update channel (systemd path unit watching a `netsentinel/sensor/{id}/cmd` topic is the natural hook — deliberately absent from v1 to keep the sensor attack surface read-only).
- Multi-VLAN sensors (multiple discovery subnets per sensor).
