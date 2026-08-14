# Changelog

All notable changes to NetSentinel are documented here. The current version summary lives in [README.md](README.md#changelog); the full history is below.

---

### v2.2.7

**Added**
- Devices now record what they can *do* separately from what they *are*. A device announcing AirPlay, Chromecast or Spotify Connect proves it can receive media — not that it is a TV — so those announcements are stored as capabilities in a new `known_device.capabilities` column (schema v23) and shown as "Can do" in the Inventory drawer, instead of deciding the device's identity outright. They previously claimed a device type at `high` confidence (0.85), above the vendor/hostname heuristic's 0.70 ceiling, so a device speaking two media protocols alternated identity forever. Measured on the reference network: **69.1% of all 11,248 recorded device-type changes were a passive capability label**, 16 of 34 devices were carrying `Smart TV` or `Streaming Stick` because of it, and an iPhone was relabelled `Smart TV` twice in one day
- `modules/device_reenrichment.py` — a once-per-generation healing pass that re-runs vendor lookup and arbitrated classification over existing `known_device` rows. Every other fix in this release only affects what is written next, so an install carrying a wrong label would keep it until something happened to rewrite that row. It upgrades only — an uninformative verdict cannot displace a real label, it never touches a user override, and it preserves `last_seen` rather than reporting every corrected device as just-seen. Measured on a copy of the live database: 34 rows examined, 8 vendors and 15 device types corrected
- `modules/vendor_hints.py` — `vendor_from_hostname()`, word-boundary anchored so `greenest-server` is not read as Nest. A locally-administered (privacy) MAC carries no OUI at all, so vendor lookup can never answer for one however large the database grows; a hostname is the only remaining evidence. OS names deliberately map to nothing — LibreELEC and DietPi run on hardware from many makers
- `modules/device_classifier_rules.py` — the 79-entry `_RULES` table, split out of `device_classifier.py`, which was at exactly its 780-line RULE-AH1 budget
- A `Computer / Workstation` classification rule. The single most common device class had no reachable path: Intel, Dell, Lenovo and MSI NICs all returned `Unknown Device` at confidence 0.0, because the existing `Windows PC` rule requires an OS family and open ports (445/3389/5900) that a passive scan never has. Placed last so it fills a gap rather than pre-empting anything; ASUSTek and HP are deliberately excluded, since they sell routers and printers on the same OUIs
- `experimental/identity_stable_arbitration` (QSettings, default off) — makes a device's classification a pure function of the evidence set rather than of the order the evidence arrived in, and requires a challenger to beat the stored label by 0.10 before replacing it

**Changed**
- A MAC-registry match is now arbitrated against the vendor/hostname heuristic instead of replacing it. The registry was returned *instead of* the heuristic claim whenever it had an entry, so the one mechanism built to catch "sources disagree" was bypassed for exactly the source most likely to be wrong — the Devices-page tooltip showed the winning claim's confidence beside the losing claim's evidence, with nothing saying they disagreed

**Fixed**
- The curated MAC table was consulted before the IEEE database and its device type was sticky, so it silently overrode both. **58 of its entries contradicted the real IEEE assignment** — a Raspberry Pi named `pinas` rendered as vendor `Microsoft`, type `Games Console`, because `d8:3a:dd` (Raspberry Pi Trading Ltd) sat inside an Xbox block. All 58 are removed, 3 OUIs defined in two dicts are resolved, and every `_LENOVO` entry is gone: all eight were ODM OUIs (LCFC, Wistron, Intel, Dell, Sony) that ship under many brands and identify no product. An IEEE-agreement check over every entry and an AST duplicate-key check now gate the table — both were red before this change
- Hostname classification rules matched inside unrelated words. All 82 patterns used a bare substring search, first match wins, so `iPad-2` classified as `Domain Controller` (it contains "ad-"), `Jonas-PC` as `File / NAS Server`, `Camilla-iPhone` as `IP Camera`, `BRAD-WORKSTATION` as `Domain Controller`, and `natverk-printer` as `Smart TV` — which also pre-empted the print rule further down the list. `ad-`, `nas`, `cam`, `tv` and `dc` are now boundary-anchored, guarded by a corpus of ~150 ordinary given names asserting none of them classifies as infrastructure
- A registry entry could claim a model-specific device type from an OUI shared across a whole product range: `f0:72:ea` was entered as "Google Nest Doorbell", so a Nest Wifi **router** rendered as a `Video Doorbell` at 90% confidence, outranking every other source. An OUI identifies an organisation, not a product
- Devices on a randomized (privacy) MAC showed no vendor at all, beside identical devices that happened to have a real OUI — one `Chromecast-Audio` read `Unknown` while its twin read `Google`. Two separate paths needed the hostname fallback, not one: a mesh-enriched device's name arrives from the router's client list long after the scanner has finished, so fixing only the scanner would have shipped inert for the exact device that motivated it
- Devices-page tooltips were unreadable in Arctic Clean. The earlier fix for tooltip illegibility forced a white foreground against an assumed dark background, but Qt paints the themed near-white tooltip background at that call site — producing white-on-near-white, the same illegibility arrived at from the opposite direction. Tooltips now emit background and foreground together as a pinned pair, so the text carries its own ground whatever Qt puts behind it. The test asserted the hardcoded white and so could never have caught this; it now computes the WCAG contrast ratio of the emitted pair and asserts ≥ 4.5:1
- Every Hewlett-Packard device was a `Print Server`, since HP matched the printer vendor rule on vendor alone; HP now needs a print port or a printer hostname, while Brother and Lexmark still match on vendor. The `Print Server` rule also had no hostname pattern at all, so a device named `office-printer` was `Unknown Device`
- `tools/check_import_lint.py` crashed the whole lint gate with `FileNotFoundError` when a tracked `.py` file was deleted in the working tree but not yet staged — `git ls-files` still lists it
- The device re-enrichment summary above never actually printed. A bare `import logging` inside `main()`'s single-instance-failure branch makes `logging` local to the *whole* function, so the re-enrichment log line raised `UnboundLocalError` on the normal path where that branch is skipped — and, sitting inside its own `except Exception: pass`, left no trace at all. A new gate (RULE-LINT7) now fails on any import that shadows an outer name this way; it models control flow, so the 44 legitimate `try: import X / except ImportError: return` optional-dependency sites are not reported

**Removed**
- The `experimental/identity_arbitrate_registry` flag is deleted rather than defaulted on, following the `native_chrome` precedent: a permanently-on flag is a branch nobody tests. Re-measured across both reference databases (71 `known_device` rows) with the preceding fixes in place, it produced 0 device-type changes and 3 confidence changes, all upward, from genuine registry-and-heuristic corroboration. A test asserts no source file still reads the key

**Internal**
- The macOS release build failed on a test, not on the product: `test_rail_smooth_progress_bar.py` pumped a fixed 0.4 s against a 250 ms animation, and a loaded runner left the final frame unprocessed (`assert 8 == 9`) while the animation code was correct. Because `release` needs all three build jobs, one flaky assertion blocked the release *and* the WinGet submission. The test now polls for its condition instead of guessing a wall-clock duration
- Two CodeQL `py/unused-global-variable` alerts cleared at the source: `device_classifier_rules.py` declares `__all__` (CodeQL counts a cross-file import as no use at all), and `mac_registry`'s run-once guard mutates a dict instead of rebinding a bool (CodeQL reports per-definition, so it cannot see the *next* call reading a flag it just stored). Both are documented as the two ways the local checker is looser than the real scan
- A known limit, recorded because it is unresolved rather than because it bites today: score is not specificity. Better-evidenced but less specific verdicts (`Android Device`, 0.70 from vendor + hostname) can outrank more specific ones (`Tablet`, 0.30 from hostname alone). This is why stable arbitration ships behind a flag; before promoting it, bump `_REENRICH_GENERATION` so existing installs re-run the healing pass under the new arbiter. Baseline figures, the disproven hypotheses, and the passive-window sampling error that briefly mis-recorded a root cause are in `docs/spikes/device-identity-baseline.md`

---

### v2.2.6

**Changed**
- The `RTT Anomaly` alert rule is now enabled by default. It had been grouped with the fixed-threshold rules that ship off, which misfiled it — it learns each host's own normal latency (mean + 2σ) instead of comparing against a constant, which is the property that keeps the others opt-in. Measured at 0.15 alerts/day over 28.8 days of the reference network: quieter than `Modem Signal Drop`, which already ships on. If you have ever pressed Save on the Notifications page, your own choices are untouched

**Fixed**
- "Device gone" and "New device" alerts were identified by IP address rather than by MAC, so on an address shared by more than one device — routine after a DHCP lease is reused, and true of 7 of 20 addresses on the reference network — **acknowledging one device's alert silently muted a different device**, and the two shared a cooldown so the second alert never fired at all. The MAC was already available at every one of those points. Alert history also now shows the device's real name on those rows instead of a bare address
- Devices sharing an address could inherit a neighbour's alert priority: on the reference network 4 device rows were alerting at a tier above their own, 2 of them borrowing the mesh access point's `critical` rating from a shared address
- Jitter was never actually measured for your router, so the `Jitter High` rule had no local data source at all despite being wired for one. The gateway is nominated for jitter sampling from network info that is not always resolved when monitoring starts, and that one empty reading was frozen for the rest of the session — measured on the reference database as 1,067 latency samples for the gateway carrying zero jitter values, against 287 each for the two internet targets. The nomination is now refreshed on every rescan
- Passive mDNS/SSDP observations were attributed by IP because nothing ever resolved their MAC — the v2.2.4 fix that added MAC matching shipped inert, since the ARP lookup it depended on had no caller. A powered-off TV could be relabelled a Router / Gateway and then a Smart Speaker. Verified live: 8 of 8 observations now carry an ARP-resolved MAC, where 6 of 7 previously landed on the wrong device
- An IP claimed by several devices resolved to whichever database row came back first when choosing a display name, which is undefined ordering. Such an address now resolves to the bare address — naming the wrong device is worse than naming none — while addresses with only one nameable device keep their name

**Removed**
- A superseded translation layer on the "What's Wrong?" page that rendered service diagnostics inline, along with two remediation entries only it could produce. The design that shipped opens the dedicated Service Diagnostics page instead; the removed code had no caller outside a test file that described it as an integration test

**Internal**
- `tools/check_orphan_functions.py` plus a CI ratchet: sweeps the tree for functions and methods that only tests reference. This is the shape that let the v2.2.4 passive-observation fix ship completely inert, and it is now caught by the suite rather than by a user report
- RULE-ID1 and a CI guard against reintroducing address-keyed device identity

---

### v2.2.5

**Fixed**
- `device_classifier.py`: `classify()`/`classify_with_evidence()`'s unconditional `vendor_re` gate silently overrode the earlier conditional one, making 9 `hostname_re`-keyed device labels (iPhone/iPad, Smart TV, Streaming Stick, etc.) unreachable whenever vendor lookup failed — exactly the randomized-MAC case those rules exist for
- `python app.py --audit`'s `IDENTITY_CHURN` check used a flat 7-day trailing window and showed a false FAIL on every existing install for a week after upgrading; a meta-table timestamp now bounds the no-op check without affecting the per-device-day churn check
- Removed an unreachable `else` branch in the passive-observation table-row match (CodeQL py/unreachable-statement)

---

### v2.2.4

**Added**
- `tools/identity_replay.py` — read-only measurement harness for device classification churn, the identity-program counterpart to `tools/alert_replay.py`; reports class-change churn per device-day, no-op share, `known_device.device_type` agreement with its own audit trail, confidence coverage, and IP-collision count. Baseline: `docs/spikes/device-identity-baseline.md`
- `modules/device_classification.py` — the arbiter that decides what a device *is* when several sources disagree: `arbitrate()` combines competing classification claims into one verdict, favouring corroboration from independent sources over whichever source ran last, and reducing confidence when sources genuinely conflict instead of silently picking the newest one
- A confidence-and-evidence tooltip on the Devices page's Device Type column, naming why a device is classified the way it is (vendor match, hostname match, open ports, MAC registry hit)
- `IDENTITY_CHURN` check in `python app.py --audit` — fails if classification churn or its no-op share regress past the program's thresholds

**Fixed**
- The device-classification audit trail recorded a "type changed" event even when the type hadn't actually changed — 47.5% of all recorded events on a real 31-device network were exactly this, from a writer that compared against a stale in-memory snapshot instead of the value it was about to write
- Passive mDNS/SSDP device-type observations were matched to a device by IP address, so on any of the (commonly several) IP addresses currently shared by more than one MAC, an observation about one device could silently reclassify a different one
- Five independent classification writers (scan-time heuristic, MAC-registry lookup, DHCP VCI fingerprint, passive mDNS/SSDP, hostname-triggered re-classify) each overwrote `device_type` unconditionally with no memory of competing evidence — measured at 219.5 audit-trail events/day (7.08/device-day) on a stable 31-device network, agreeing with the type actually shown to the user only 23.1% of the time. Every writer now submits a claim to a shared arbiter instead
- `classify_with_evidence()`'s confidence score was computed on every classification and never stored anywhere — `known_device.confidence` was 0.0 on every row of every install. It's now persisted from the scan's own classification and from every passive/DHCP/hostname-sync upgrade that changes a device's type
- Multicast, broadcast and other non-device addresses could still be classified and written into the passive-observation and DHCP-fingerprint enrichment paths despite already being excluded from the main scan write path

---

### v2.2.3

**Added**
- Alerts are now ranked by relevance (confidence + importance tier) wherever a claim list has a cap, instead of raw chronological or scan order — the Home "Action needed" card, the Overview feed and the log hub's critical/warning/other ladder now surface what matters most first
- Eight alert rules — including gateway loss, mesh node drop-off, modem signal drop and unreachable infrastructure — are now enabled by default on a fresh install, instead of every rule shipping off
- New `INFRA_UNREACHABLE` rule: alerts when a modem, router, access point or switch plugin stops responding, and resolves when it answers again
- `MESH_DEGRADED` now actually fires when a Deco mesh node drops offline
- New `DNS_LATENCY` rule: alerts when DNS resolution goes slow, with a self-learned per-network baseline
- Gateway loss (`HOST_DOWN`) now reaches the alert engine from real LAN monitoring, not just the two fixed internet-health targets
- Jitter measurement now feeds the `JITTER_HIGH` rule, which previously had no data source at all
- Devices are now ranked by corroborated importance (critical / infrastructure / personal / transient) instead of a single unreliable "infrastructure" flag, for deciding which devices are eligible to raise an alert

**Fixed**
- The Home "Action needed" card was showing the five oldest unacknowledged alerts instead of the most relevant ones
- A repeat outage on the same device fired a fresh `HOST_DOWN` alert roughly every two minutes instead of once per outage
- The RTT baseline behind `RTT_ANOMALY` could never mature, so the rule could never fire no matter how long a device had been monitored
- `python app.py --audit` misread every genuinely-enabled alert rule as missing its opt-in on Windows, because a stored `"true"` string wasn't recognised as boolean `True`
- An updated bundled plugin (e.g. the 5G modem) could silently stop being polled after an app update, with the only trace being an error on a Hardware page card the user may never open
- Mesh and modem alerts were unintentionally disabled whenever the unrelated "Monitor logging" setting was off
- Multicast/SSDP groups could be tracked and even promoted to "infrastructure" as if they were real devices; a device going offline and back repeatedly re-announced its absence every hour instead of once per departure
- Non-device inventory rows (like multicast groups) were never removed from the device list, and DHCP-server evidence wasn't reaching device role inference
- `Log Hub` and `Hardware` pages could leave background timers running after being closed, or even if never opened

---

### v2.2.2

**Fixed**
- Four more pages started a repeating `QTimer` straight from their constructor — `cert_page` and `uptime_page` (300 s), `service_page` and `maintenance_page` (60 s). The lazy page-builder constructs every page shortly after startup whether or not the user ever opens it, so each rebuilt its whole table for the entire session on a page nobody had looked at. This is the same RULE-WIN18 defect fixed in v2.2.0, in four pages the hand-maintained factory list never covered; `test_page_timer_lifecycle.py` now has a static AST pass that flags any `ui/pages/*.py` connecting to a non-single-shot `QTimer.timeout` without a factory, so coverage can no longer rot silently
- `ui/widgets/skeleton.py` carried the same defect one level down, reached through a helper rather than a page. `insert_skeleton_rows()` started a 650 ms pulse timer stopped only by `clear_skeleton_rows()`, and `ServicePage.__init__` inserts skeleton rows then calls `_refresh()`, which returns early when the page isn't visible — so on a never-opened page the rows were never cleared and the pulse ran all session, allocating a `QBrush` + `QColor` per skeleton cell per tick. Fixed in the widget via a visibility-gated pulse controller, covering all four call sites at once
- `modules/zte_plugin.py::get_status()` built a fresh `ZteMC889Client` and called `login()` on every poll, and `PluginPollingWorker` polls a modem-type plugin every 30 s. Each `login()` creates a new `requests.Session`, whose HTTPS adapter builds an `SSLContext` and calls `load_default_certs()` — so an idle app paid a full Windows certificate-store enumeration plus two extra HTTPS round-trips every 30 s. `get_signal_data()` already re-authenticates itself when a session goes stale, so one cached client is what the class was designed for; the cache is dropped on `ZteAuthError`/`ZteApiError` so a revoked cookie or rebooted modem can still recover
- `time.strftime("Snoozed →%H:%M", ...)` on the Notifications page passed a non-ASCII format string through the C-runtime locale codec on Windows, which raises `UnicodeEncodeError` on a non-UTF8 locale. This was the confirmed trigger for two native `Qt6Core.dll` crashes in the 2026-07-31 chaos run, reachable from both `_bulk_snooze()` and the per-row snooze path
- `ui/pages/timeline_page.py::_render()` tore down and reconstructed every event row on each 60 s refresh — one `QFrame` plus up to four `QLabel`s per event across a 200-event feed. The teardown was correct, so this was never a leak; it was pure churn, and `QFrame`/`QLabel` are C++ objects so tracemalloc could never see it. Rows and date headers now come from pools and are re-filled in place, giving zero widget construction per tick at steady state
- `tools/monkey_test.py`'s own health-monitor restart silently destroyed all tracemalloc history since phase start — `app.py` truncates the snapshot log on every launch (RULE-TM1), and the harness's single end-of-phase copy never saw the earlier process. One 8 h soak lost ~1.5–3.5 h of data this way. The live log is now salvaged to `tracemalloc_pre_restart_<N>.log` before the kill and merged back in chronological order

**Added**
- `tools/vmmap_leak_probe.py` — three-phase RSS breakdown by native region type (startup ramp / steady heap climb / late image jump) without needing gflags or a multi-hour soak
- `tools/umdh_leak_probe.py` — targeted UMDH snapshot pair bracketing the steady-growth window, automating the wait/snapshot timing that caused two documented false starts. Ships with `--manage-ust`, which arms `+ust` and always reverts it in a `finally` — including Ctrl+C, a failed snapshot, and a diff timeout
- `docs/spikes/idle-rss-bench.py` — idle-Dashboard RSS trend over a real `MetricStore`, reporting main and child process RSS separately rather than summed (the WebEngine sawtooth is ±25 MB of noise); plus `docs/spikes/startup-arm.ps1` for per-arm time-to-window
- `--procdump` / `-Procdump` — attaches Sysinternals ProcDump to the launched app so a real fault or stall captures a full dump automatically instead of relying on after-the-fact log correlation (RULE-DBG2)
- `-MildOnly` / `-ModerateOnly` / `-WildOnly` — run a single continuous soak phase at exactly one chaos level, skipping the coverage cycle and both systematic sweeps, which measured 25–28 min each in practice against a 5-min budget estimate and dominated any short targeted re-run
- RULE-CHAOS3, documenting that the chaos harness always writes to `%USERPROFILE%\Documents\NetSentinel\test_output\run_<timestamp>\` rather than the repo's own `test_output\`, and which log to read first

**Changed**
- The chaos harness now refuses to start while gflags `+ust` stack-trace tracing is armed on `python.exe` or `NetSentinel.exe`, naming the exact elevated command to clear it. `+ust` puts a stack trace on every heap allocation process-wide, persists across reboots, and is invisible at runtime — nothing looks wrong, the numbers are just false. Left armed by accident it took app startup from 5.8 s to 99 s and the test suite from 9 min to 68 min, produced two test "failures" that were pure artifact, and invalidated a day of memory measurements. `--allow-gflags` / `-AllowGflags` is the deliberate bypass
- `--tracemalloc` is now opt-in (`-Tracemalloc`) rather than on for every soak phase. An A/B run established that tracemalloc itself caused the mid-soak hangs — 0 hangs and 0 restarts without it, against 1–2 on every prior run, with `cdb` showing the main thread stuck inside tracemalloc's own traceback capture. Its per-allocation cost also distorts the RSS numbers a soak exists to measure, and it never found this leak: the growth is native, which is why five rounds of tracemalloc came back empty
- `--procdump` now uses hang-detection mode (`-h`) instead of exception mode (`-e 1`). Every launch throws a routine, immediately-handled `pybind11::attribute_error` during native-extension startup that `-e 1` cannot distinguish from a real fault — confirmed via `cdb` on 6 of 6 dumps captured across two chaos runs, none of them related to the bug under investigation

---

### v2.2.1

**Changed**
- The red `admin` pill on the six Security Audit flyout items is now suppressed when NetSentinel is already running elevated. The pill is a warning ("you cannot run this as you are"), not a label, so it said nothing to a user who had already elevated — `ui/nav/builder.py::_nav_rail_toggle()` re-evaluates it on every flyout open
- `ui/monitor_state.py::_refresh_section_badges()` now puts an amber left-dot on the Security Audit rail button and appends " — not running as Administrator" to its tooltip when unelevated, so the state is visible before the flyout is opened. `set_left_dot()` is a separate paint slot from the badge, so the existing numeric alert pill is untouched

**Fixed**
- `tools/monkey_test.py`: a long unattended chaos run could click the Settings "Start minimised to the system tray" checkbox, which `app.py` honours by launching tray-only with no window at all. The value is registry-persisted, so every later relaunch in that run — and every future run on the machine — started hidden and `_connect()` timed out with nothing to drive, surfacing as an unexplained "lost focus". The checkbox is now in `_BLACKLIST` on app-lifecycle grounds (RULE-CHAOS2), and a new `_reset_hazardous_settings()` clears an already-set value before each `_launch_exe()` / `_launch_source()`

---

### v2.2.0

**Fixed**
- Root cause of the multi-release memory growth that had survived five rounds of tracemalloc/UMDH/VMMap diagnostics: `ui/nav/lazy_page.py`'s background chunk-builder constructs *every* lazy page a few seconds after startup whether or not the user opens it, so any `QTimer` started in `__init__` ticks for the whole session on a page nobody has looked at. Two offenders, both rebuilding a `QTableWidget` every tick — `ui/pages/connections_page.py` (5 s, full `psutil` socket enumeration) and `ui/pages/timeline_page.py` (60 s, store re-query). `QTableWidgetItem` is a C++ object, so the growth was native and invisible to Python-level profilers, which is why every earlier diagnostic round came back empty. Both timers now start in `showEvent()` and stop in `hideEvent()`; measured on a real Dashboard idling on Home against a real `MetricStore`, main-process RSS went from **+556 MB/hr to −19.6 MB/hr (flat)**
- `ui/pages/security_overview_page.py` ran a 5 s refresh timer from construction — and unlike every other lazy page it is built *eagerly* in `_init_pages()`, so this ran on every launch for every user regardless of whether the page was ever opened. Not an RSS leak (measured flat: +5 MB/hr, +7 MB/hr with 25 seeded unacked alerts, because `setRowCount(0)` lets Qt reclaim the per-row widgets) but a permanent CPU/IO cost of ~6 s of CPU and ~2,160 SQLite reads per hour: 0.33 s CPU per 3 min idle against a 0.03 s do-nothing control, 0.05 s after the fix
- `ui/pages/dhcp_lease_page.py` fired a lease scan at construction and kept a 300 s timer running on a never-opened page, spawning subprocesses and a `QThread` for a view the user had not asked for. Now 0 scans and no timers until first show, with the initial scan moved to a first-show-only call so opening the page still lands on populated leases rather than an empty state
- `ui/pages/network_map_page.py`: three independent defects — `_start_bw_worker()` built a fresh `BandwidthOverlayWorker` on every `showEvent()` but `_stop_bw_worker()` only dropped the Python reference, never `deleteLater()`'d it, so each discarded `QThread` survived as a permanent C++ child of the page (RULE-WIN8); `_on_bw_snapshot()` re-serialized the entire topology into a `runJavaScript()` call every 5 s whether or not traffic had changed; and `showEvent()` scheduled a `fit_view()` JS push on every single visit even with no new scan data
- `tests/test_connections_page.py` monkeypatched the `@pyqtSlot`-decorated `_refresh` on the *class*; once monkeypatch restored it, PyQt could no longer resolve the slot, so every later `ConnectionsPage()` in the same pytest process died with a `connect() failed` error. Test factories now override on a subclass instead

**Added**
- RULE-WIN18 and `tests/test_page_timer_lifecycle.py` — a runtime (not AST) guard that every page with a background timer starts it in `showEvent()` and stops it in `hideEvent()`. Runtime by necessity: `connections_page` started its timer *indirectly*, via `setChecked(True)` firing `toggled` into the start handler, which no realistic static check would follow. `hideEvent()` alone (RULE-WIN15) is not sufficient — a widget constructed but never shown never receives one
- `tools/page_isolation_soak.py` — page-pair memory isolation harness built during this investigation, plus `docs/spikes/idle-rss-leak-lazy-page-timers.md` documenting the three measurements that overturned the previous root-cause theory and auditing the remaining construction-time timers
- Full Documentation card on the Help & Shortcuts page, linking to the published docs site so a non-technical user can reach it from inside the app instead of only from README/GitHub

---

### v2.1.52

**Changed**
- README, docs site, and Microsoft Store listing now lead with the same plain-English positioning (device discovery, fault diagnosis, security audit) instead of three different pitches; added a "What it answers" table above Install, regrouped Features under the same Discover/Monitor/Diagnose/Report/Audit/Automate headings as the At-a-glance table, and filled out the Audit group to match the four capabilities the At-a-glance table already promised (OS detection, credential testing, TLS monitor, CVE lookup)
- Updated the README quality claim to the longest chaos run to date (15h, 31,372 interactions) and dropped the peak-RSS sentence, which cited a flat run while three later runs peaked 1,432-2,880 MB and made an open issue read as resolved; `docs/_config.yml` now publishes `docs/` via GitHub Pages, excluding `internal/` and `spikes/`

**Fixed**
- `ui/widgets/protocol_canvas.py`: `ProtocolCanvas` had no `hideEvent()`, so its 30fps `QTimer` kept ticking and repainting after navigating away from Protocol Visualizer or Lab Mode — the same RULE-WIN15 leak shape as the already-fixed Network Map and Live Bandwidth workers, and the top suspect from the wild-soak RSS bisect that localized the multi-release RSS regression to v2.1.32-v2.1.36

---

### v2.1.51

**Added**
- `modules/scan_guidance_audit.py` — a 7-invariant audit harness (dead CTA labels, CTA table parity, scan-state wiring, Scan Status card parity, security-audit queue termination, alert-guidance render truncation, grade-dimension gating) wired into `app.py --audit`, guarding against the alert/scan-wiring bug class that produced 5 consecutive one-off fix releases (v2.1.46–v2.1.50)

**Fixed**
- Devices table showed a blank Vendor/Risk column on every startup, before any scan ran — `_restore_cached_scan()` populated `_m1_table` from cached data without disabling live sorting first, so Qt's default column-0 sort indicator resorted rows mid-populate and scattered Vendor/Risk onto the wrong rows. The startup cache-restore path now guards against this the same way the live-scan path already did
- A window minimized while maximized and restored from the tray came back small and docked top-left instead of maximized — `AppHeaderMixin.show_main_window()` called `showNormal()` unconditionally on any minimized window, dropping the maximized state. Now checks `WindowMaximized` first
- The test suite was silently overwriting the developer's real saved window geometry on every run — three subprocess-isolated Dashboard tests (`_lazy_pages_child.py`, `_startup_minimised_child.py`, `_theme_switch_deferred_child.py`) called `dash.close()`, whose `closeEvent()` writes to the real repo-root `NetSentinel.ini`. All three now redirect `settings_path` to an isolated temp file, plus a session-scoped `conftest.py` backstop that snapshots/restores the real ini around the whole suite
- Resolved all 7 findings from the scan-guidance audit (Phase 2+3): Threat Intel now advances the Security Audit queue and reports scan state; 6 dead/wrong CTA targets fixed across `notif_alert_history.py` and a previously-undocumented duplicate table in `alert_drawer.py`; Home "Action needed" card no longer truncates guidance text at 50 chars; device-name resolution extended to IP-based lookup on all three alert render surfaces; port-sweep now distinguishes "unreachable" from "genuinely nothing open" and matches devices by MAC to survive DHCP lease reuse; CVE Tracker and DHCP Rogue Monitor now report scan state (Scan Status card reconciled 9→16 rows); security grade no longer counts CVE/TLS from store presence alone, gated on the scan registry instead

---

### v2.1.50

**Fixed**
- Device discovery could return zero devices with a blank Vendor column on some machines. `modules/network_environment.py::_widest_subnet()` picked scan scope by widest netmask without excluding link-local (`169.254.0.0/16`) adapters, so a disconnected Wi-Fi radio, Bluetooth PAN, or idle virtual NIC's APIPA `/16` beat the real LAN's narrower subnet, and `effective_scan_scope_cidr()` bounded the scan to a network with nothing on it — `partition_by_scope()` then classified every real ARP entry as out-of-scope (measured live: 0 in-scope devices before the fix, 15 after). A machine with only link-local addresses now fails open (unbounded scan) instead of silently scoping to nothing. The blank Vendor column was a downstream symptom, not a `lookup_vendor`/`mac_lookup`/`device_classifier` fault — `ui/scan_enrichment.py` now also fills Vendor/Device Type on mesh- and plugin-synthesized rows via the offline `mac_registry` lookup, and the header device count includes those synthesized rows

**Changed**
- Regenerated the `03_devices.png` / `04_app_traffic.png` Microsoft Store screenshots

---

### v2.1.49

**Fixed**
- App Traffic, Live Bandwidth, and Timeline rows showed a bare MAC address instead of a device's known name, even when `known_device` already had one. Added `ui/device_labels.py::DeviceLabelResolver` (fed label map -> `known_device` custom name/hostname/vendor -> offline OUI lookup -> MAC) and switched all three views to resolve names at render time instead of baking a label in at capture time, so a label map arriving later now corrects rows already on screen. Also fixed `AppTrafficPage` keying its snapshot history by display label (a renamed device grew a duplicate, MAC-keyed entry) and `AppTrafficWorker.set_label_map()` rebinding its own dict instead of updating the running `AppTrafficMonitor`, which silently discarded every label update issued after `start()`

- `modules/iot_baseline.py`: a device baselined during a quiet stretch could end up with an `avg_pps` of a few hundredths, so the pure ratio check behind `RATE_SPIKE` fired on a handful of stray packets — both values round to "0"/"0.0" at the alert's own display precision, producing a nonsensical alarm with no real signal behind it. Added `RATE_SPIKE_MIN_PPS` as an absolute floor `current_pps` must clear before the ratio check applies, so a genuine sustained burst against a near-zero baseline still fires but stray packets against it no longer do

**Changed**
- Made the documentation site publishable: excluded `docs/internal/` and `docs/spikes/` from the MkDocs build (previously compiled into `gh-pages` even though absent from `nav`), added 5 previously-orphaned pages to the nav (feature-reference, incident-patterns, hardware-plugins, plugin-authoring, chaos-testing), fixed 6 dead links including a `master`-branch `edit_uri` on a repo whose default branch is `main`, and added a `mkdocs build --strict` CI guard that fails the job if any internal/spikes page reaches the build output
- `.github/winget/NetSentinel.NetSentinel.locale.en-US.yaml`: rewrote the winget listing to lead with LAN scanning, diagnosis, and security audit instead of specific hardware models; consolidated vendor hardware into one bullet and added the ISP Accountability Report and Stability Logger, which were missing entirely
- Regenerated the Microsoft Store screenshot set (previous set was 23 releases stale); `tools/store_screenshots.py` now verifies each capture via breadcrumb match, content-uniformity check, and scan-idle wait, catching a silent-navigation defect where a no-op saved the previous page under the new page's filename
- Rewrote the Microsoft Partner Center listing copy (`assets/store/partner-center-listing.md`) to lead with device discovery, fault diagnosis, and security audit instead of specific vendor hardware, and states the Administrator/Npcap requirements up front; added `assets/store/check_listing_lengths.py` to validate every field against Partner Center's length limits before submission

---

### v2.1.48

**Fixed**
- Acknowledging an alert did not stick, from three independent causes found against a live DB holding 87 unacked alerts: `ui/pages/notif_alert_history.py` collapses rows by `(rule_name, host)` into "xN" entries but only ever wrote the group's representative id, so acking every visible row of 43 grouped rows left 44 alerts unacked; the bulk acknowledge action was effectively unreachable (labelled "Dismiss", with the bulk bar only appearing after a row was already selected and single-click opening the 320px drawer on every Ctrl/Shift-click, fighting the multi-select it needed); and `modules/alert_engine.py` deduped on cooldown alone, so a condition that stayed true re-alerted every 5 minutes forever regardless of acknowledgement — measured at 247 "Service Down" fires with a 5.0-minute median gap for a single host
- `modules/alert_engine.py`: acknowledging now places a per-`(rule, host)` hold — default 24 h, configurable under Notifications -> Configure — seeded from `alert_fired.acked_ts` via the new `MetricStore.get_recent_acks()` so holds survive a restart with no schema change; a resolution clears the hold, so a genuinely new occurrence still alerts
- Home page "Action needed" card reported "5 of N" with no total and no bulk action, so acknowledging the visible rows just promoted the next five within 30s; it now reports the real backlog and offers "Acknowledge all (N)" with an undo toast backed by the new `MetricStore.unacknowledge_alerts()`
- Alert History stretched the Rule column — a short fixed vocabulary in a very wide column that read as permanently empty — while never showing the alert message in the table at all; columns are now Time/Rule/Host/Message/Severity/Status with Message stretching
- The Home card's per-alert acknowledge button has shipped as an unlabelled empty box: an inline stylesheet MERGES with the global QSS rather than replacing it (RULE-QSS5), so the 22x18 button inherited `MAIN_STYLE`'s `QPushButton { padding: 5px 14px; }`, leaving -8px of label rect and eliding the check mark to nothing — measured at 0 ink pixels inside the border, byte-identical to `setText("")`, vs 11 with padding pinned
- `ui/widgets/alert_drawer.py` never stopped its parented `_EvidenceWorker` QThread; destroying a running QThread aborts the process natively (RULE-WIN4) — it killed a test run with exit 127 and no summary line
- The in-app "What's New" section shipped stale for two consecutive releases (v2.1.47 showed v2.1.46's bullets under a "What's New in v2.1.47" heading) because it is hand-written prose `bump_version.py` deliberately never rewrites, so nothing structural linked it to a release; `ui/help_tab.py` now hoists it to a `_WHATS_NEW_VERSION`/`_WHATS_NEW_ENTRIES` pair that `bump_version.py::_preflight_whats_new()` checks before the first file is written, and the heading renders from the constant so a bypassed gate degrades to stale-but-truthful rather than mislabelled (RULE-R1b)

**Changed**
- `tests/`: removed three definition-only module-level globals flagged by CodeQL `py/unused-global-variable`, found by pointing `tools/check_import_lint.py`'s unused-global scan at `tests/` (RULE-LINT6 normally scopes it to `modules`/`ui`/`workers`, which is why they reached GitHub) — internal tooling, no user-facing change

---

### v2.1.47

**Fixed**
- Security Audit -> Windows Shares (SMB) page: the Shares/Users tabs rendered unreadable dark-on-dark text in Midnight Pro because `ui/styles.py` had no global `QTabBar::tab` rule; also closed the same gap for `QPlainTextEdit` and `QDoubleSpinBox`, siblings of already-styled widget classes
- Menu separators (`QMenu::separator`) rendered from the native, non-theme-aware palette instead of the active theme across 15 of the 19 files that call `addSeparator()`

**Changed**
- `tools/run_test_suite.py` (RULE-GATE1): the commit-gate test runner now fails closed on three independent conditions — a real summary line, zero failure counts, and a clean exit code — so a mid-run crash or silent early exit can no longer be misread as a passing suite (internal tooling, no user-facing change)

**Added**
- `tests/test_qss_widget_coverage.py`, `tests/test_qss_derived_contrast.py`, `tests/test_qss_tab_styling.py` — regression coverage pinning theme colour rendering across every style-painted widget subcontrol the app uses (RULE-QSS4)

---

### v2.1.46

**Added**
- `modules/alert_audit.py` — pure-Python invariant self-test for the alert/notification pipeline, driven by `python app.py --audit-alerts` (13/13 invariants)
- `modules/alert_remediation.py` — canonical per-rule-type remediation text for all 25 `RULE_TYPES`, moved out of `ui/widgets/alert_drawer.py` so it is unit-testable and reusable
- `ui/pages/notif_routing_matrix.py` — collapsed-by-default per-rule x per-channel advanced routing matrix card on the Notifications page
- `docs/internal/vt-false-positive-runbook.md` — manual override procedure for a VirusTotal false-positive release flag

**Changed**
- `scripts/vt_scan.py` (RULE-REL1): the release VirusTotal gate no longer fails on any single engine's nonzero hit — it now classifies by combined malicious+suspicious hit count, surfacing `<=2` as a non-blocking "flagged" warning (with engine names) and only blocking the release when hits exceed that threshold
- `.github/workflows/release.yml`: the "Prepend security section" step now runs with `if: always()` so the VirusTotal verdict is never silently dropped from release notes when the scan step itself fails
- `scripts/update_release_body.py`: release notes now render the VirusTotal verdict status-aware instead of a bare link that looked identical regardless of outcome
- Settings -> Active Integrations dropped its three duplicate, non-functional "Send test" rows (Email/Webhook/Pushover) in favour of a single link to the real Notifications page config

**Fixed**
- `modules/notification_router.py`: desktop toast balloons and default-on channels were reaching users who never opted into notifications across 17 call sites plus 3 ungated tray balloons; all in-app toast delivery now routes exclusively through the router-gated callback
- 8 of 25 alert rule types had no remediation text; every rule type now resolves to actionable "how to fix" guidance
- HEALTHY-severity alerts now route resolution notifications while still respecting maintenance windows and per-device scope
- Notification channel secrets (SMTP, Pushover, Telegram, ntfy) now survive an app restart via the OS keychain restore path
- Removed the write-only `notif/any_rule_enabled` QSettings key that nothing ever read

---

### v2.1.45

**Added**
- `app.py`: `--gc-census` diagnostic mode (`NETSENTINEL_GC_CENSUS=1`) logs the top 30 live Python object counts by class name to `gc_census.log` every 60s, complementing `--tracemalloc` (RULE-TM1) with visibility into live QWidget/QObject wrapper counts that raw heap-byte tracing can't see
- `app.py` / `tools/monkey_test.py`: `--vmem-census` diagnostic mode buckets committed process memory by region type (Private/Mapped/Image) x protection via `VirtualQuery` every 60s — the native-memory counterpart to `--tracemalloc`/`--gc-census`, added because both Python-visible angles stayed flat while wild-soak RSS kept climbing; also adds `docs/spikes/wild-soak-rss-leak-investigation.md`, a full narrative write-up of the multi-session investigation

**Fixed**
- `modules/single_instance.py`: the single-instance guard's `QLocalServer` probe-then-listen dance had a TOCTOU race — a process that lost the race fell back to running as a fully independent second instance instead of exiting, letting repeated Start-menu/taskbar icon clicks open 5+ windows (worst on MS Store cold starts); replaced with an atomic `CreateMutexW` gate checked before `QApplication` is even constructed, with `QLocalServer` demoted to a best-effort "bring the existing window to front" signal sent after the mutex has already decided (RULE-WIN16)

---

### v2.1.44

**Fixed**
- `ui/pages/network_map_page.py`: the Traffic Overlay's Scapy `AsyncSniffer` worker (default-on the first time the page is shown) had no `hideEvent()`, so it kept pushing `runJavaScript()` updates into the embedded `QWebEngineView` every 5s for the rest of the app session after a single visit to the page — an unbounded ~46 KB/push leak in the `QtWebEngineProcess.exe` child process, invisible to `tools/monkey_test.py`'s RSS sampling (RULE-WIN15). `hideEvent()` now stops/resumes the worker across navigation, and `monkey_test.py`'s RSS sampling now sums child processes too (RULE-DBG4), closing the blind spot for this whole class of leak
- `ui/pages/live_bandwidth_page.py`: `IfaceBwPoller` started unconditionally in `__init__` with no `hideEvent()`, so its 1Hz poll + full matplotlib redraw kept running in the main process for the rest of the app session after a single visit (same RULE-WIN15 shape as the Network Map fix); now stopped on `hideEvent()` and resumed on `showEvent()`

---

### v2.1.43

**Fixed**
- `ui/header.py`: a native `SW_RESTORE` that bypasses Qt's own `showNormal()` (the chaos harness's focus-reclaim path, and some OS window-management flows) left the top-level QWidget's `isVisible()` stuck `False` even though the window was back on screen — Qt painted nothing and collapsed the accessibility tree to the 6 native-frame scaffolding controls; `changeEvent()` now calls `self.show()` on the minimized→restored edge whenever the widget is still marked hidden (RULE-WIN14)
- `ui/pages/history_page.py`: `_start_refresh_worker()` overwrote the previous `QThread` refresh worker on every page navigation without `deleteLater()`-ing it, leaking a worker per visit (~1.5 KB/navigation)
- `ui/nav/rail.py`: `_nav_rail_toggle()` rebuilt all 9 rail button icons (`QSvgRenderer`/`QPixmap`/`QPainter`/`QIcon` from scratch) on every toggle even though only one button's checked state actually changed; `setChecked()` now skips the icon rebuild when the value is unchanged
- `tools/monkey_test.py`: `_window_ok()` and `_focus_heartbeat()` both called `self._win.exists()`, a method `UIAWrapper` doesn't have, inside a broad except-and-continue — both silently no-op'd on every call, forcing a full window re-enumeration on each liveness check and leaving the proactive focus-reassertion thread dead since it was written; both now use a shared `_hwnd_still_ours()` (`IsWindow` + PID match)
- `tools/monkey_test.py`: minimizing the native-chrome window clears `WS_VISIBLE`, dropping it out of `Desktop(backend="uia").windows()` entirely rather than just failing the size check, so a minimized window falsely restarted the app under test (5 of 6 restarts in the 2026-07-23 wild-soak run); `_window_ok()` now falls back to the cached HWND plus `IsWindow`/PID/`IsIconic` to recognize "same window, just minimized"
- `tools/monkey_test.py`: the real-quit phase computed the titlebar-X click from a minimized window's `rectangle()`, which isn't its on-screen rect, so the click missed and shutdown was misreported as a 25s "shutdown hang"; the window is now restored before the close click

---

### v2.1.42

**Fixed**
- `ui/header.py`: the minimize button (and other header buttons) stopped responding after restoring the window from the system tray — `changeEvent()`'s native hit-test cache refresh ran mid-`showNormal()` while child widgets still reported `isVisible() == False`, writing an empty client-rect cache; `showEvent()` now unconditionally refreshes the cache once the window is genuinely visible again
- `ui/nav/builder.py` / `ui/scan_wiring.py` / `ui/tabs_analysis.py` / `ui/tabs_recon.py`: Cloud Metadata Probe, Private Endpoint Check, Recon Plugins, and Device Risk Score never called `_nav_set_scan_state()` (RULE-SS1), so their flyout dot stayed dark ("Never run") even after a genuine HIGH/FAIL finding — the Security Audit rail badge could read clean while a real finding sat unread on the page; all three scan-state slots (start/result/error) are now wired on each
- `ui/widgets/device_popover.py`: right-clicking a device row on a secondary monitor dragged the popover back onto the primary monitor because the cursor position was clamped against `primaryScreen().availableGeometry()` instead of `screenAt(global_pos)` — fixed at all five call sites
- `modules/dhcp_lease_scanner.py`: raised `AttributeError` instead of returning `[]` on platforms lacking the Windows-only `CREATE_NO_WINDOW` flag, because the `creationflags` value was built outside the module's own try/except fallback
- Arctic Clean contrast: fixed several near-invisible colours that skip the RULE-AH3 hex scan by using named-colour/`rgba()` literals — the speed-gauge tip dot, overview tile hover background and scrollbar handle, five topology legend proxy lines, and the device-popover alert badge foreground; `modules/network_benchmark.py`'s raw `#888` literal now routes through `modules/colours.py`
- `tests/conftest.py`: the full test suite was silently overwriting the developer's real saved theme setting to Arctic Clean — `apply_theme()` makes a real `QSettings` write, and per-test restores were skipped whenever a test failed mid-file; a new session-scoped autouse fixture snapshots and restores the real theme in a `finally` block regardless of suite outcome

---

### v2.1.41

**Fixed**
- `ui/system_tray.py`: right-clicking the tray icon a second time after the autostart query finished raised the same "wrapped C/C++ object ... has been deleted" crash previously fixed only in `settings_cards.py` — `_start_autostart_worker()`'s own separate copy of the pattern now tolerates the prior `AutostartWorker`'s C++ object already having been destroyed via `finished`->`deleteLater()`
- `ui/system_tray.py`: hovering the tray icon showed raw `<span style='color:...'>` HTML markup instead of styled text, because `QSystemTrayIcon.setToolTip()`'s native OS tooltip is plain-text-only and was wrapped in `safe_tooltip()`'s HTML `<span>` (meant for widget tooltips); also drops the "Grade: ?" segment when no scan has run yet instead of showing an unhelpful placeholder

---

### v2.1.40

**Fixed**
- `ui/pages/settings_cards.py`: toggling "Start NetSentinel automatically" a second time after the first query/set completed raised a "wrapped C/C++ object ... has been deleted" crash (reported from the Microsoft Store build) — `_start_autostart_worker()`'s re-entry guard now tolerates the prior `AutostartWorker`'s C++ object already having been destroyed via its own `finished`->`deleteLater()` wiring
- `ui/widgets/alert_drawer.py`: the alert drawer's action-button row (Acknowledge / Snooze / Network Logger / Fix this / Troubleshoot) rendered with clipped text because up to 5 buttons no longer fit one row in the fixed 320px drawer; the row now wraps to additional lines instead of clipping
- `ui/pages/inventory_page.py`: Current Devices on the Inventory Change History page was hard-capped at 200px regardless of window size while the change-history table below it took all the remaining space; the two now share a resizable splitter

---

### v2.1.39

**Changed**
- Feature Guide: promoted Protocol Visualizer and Lab Mode to the top of "Start here" and the recommended-pages list; removed the stale "New in this version" group (it was still pointing at window chrome from v2.1.30 and theme switching from v2.1.29 — nine releases out of date, and steering onboarding attention away from the higher-value tools)

**Fixed**
- Alert History tab got stuck showing skeleton-row placeholders when opened via the alert badge or other shortcuts, because the tab-index switch happened before the page's cross-fade transition had actually made it visible, so the visibility-gated refresh silently bailed and never retried; the two Alert History tables also now expand to fill the window instead of stopping at a fixed 200px height
- Dialog `.exec()` leak across 26 files (RULE-WIN8 general case): 47 call sites created a dialog with a parent but never called `deleteLater()`, so the parent's C++ side kept every dialog alive forever after the local Python variable went out of scope — the same leak previously fixed only for the Ctrl+K command palette. Measured ~521 KB retained per un-cleaned-up dialog, matching the RSS-growth pattern seen in the 2026-07-21 wild-chaos monkey run. New `ui/dialog_utils.py::run_dialog()` guarantees `deleteLater()` via try/finally, and `tests/test_dialog_leak_guard.py` is a new AST guard preventing bare `.exec()` calls from creeping back in
- Tooltips illegible in Arctic Clean theme (RULE-UX7): every `.setToolTip()` call rendered black-on-black because the QSS tooltip rule wasn't consistently applied. New `ui/styles.py::safe_tooltip()` forces readable text via inline HTML; all 220 tooltip call sites across `ui/` now route through it
- `gateway_mac` `None` crash (RULE-NET1): `_norm_mac()` raised an unhandled `AttributeError` when `gateway_mac` was legitimately `None` (before ARP resolution completes), preceding a confirmed wild-chaos `STATUS_STACK_BUFFER_OVERRUN` crash. Hardened `_norm_mac()` to tolerate `None`, and fixed the identical latent shape in `ui/plugin_page_mixin.py::_check_hw_autodetect()`

---

### v2.1.38

**Added**
- `modules/network_environment.py` — detects home/VPN/corporate/large-subnet networks and derives real scan scope (`scope_cidr`) and a per-network authorization fingerprint
- `modules/adaptive_timing.py` — derives probe timeouts from measured gateway RTT instead of a fixed home-LAN constant, so large/high-latency networks stop timing out prematurely
- `ui/widgets/environment_banner.py` plus a one-time pre-scan "Scan Anyway / Cancel" notice — warns before scanning an unfamiliar or large network
- `ui/scan_settings.py` — environment-aware scan defaults (cache-flush, scan scope, SYN rate cap, host exclusion list), all overridable in Settings → Network Scanning
- Real `n/total` scan progress and an honest watchdog that no longer falsely reports "took too long and was stopped" while a scan is still running on a large network
- Network Map now collapses subnets above 150 devices into one node per /24 (double-click to expand)
- 7-day hostname-resolution cache (`known_device.hostname_resolved_at`, schema v21) so repeat scans on large/VPN networks skip re-resolving unchanged hostnames
- Streaming device discovery — devices now appear in the scan table as soon as ARP identifies them, filling in hostname/vendor as resolution completes, instead of waiting for the whole scan to finish
- A new "Could not test" (`not_testable`) scan state, distinct from both "clean" and "error", across Port Scan (TCP/UDP), CVE Lookup, Threat Intel, TLS & Exposure, Login Test, OS Detection, and Full Device Discovery — the Security Overview grade and Device Risk Score now say "Insufficient data" instead of reporting a blocked probe as a clean result

**Changed**
- Cache flush before scanning now defaults on for home networks (unchanged) and off for VPN/corporate/large-subnet networks, overridable in Settings
- Active probing now asks for authorization on an unrecognized network: Port Scan (TCP/UDP) soft-caps its rate if declined, Login Test refuses to run at all (a login attempt has no safe "reduced" form)
- Scan scope is now bounded to the real local subnet width on non-home networks instead of assuming every network is a /24; out-of-scope devices are counted, never silently dropped

**Fixed**
- Onboarding coach mark losing its screen anchor and reappearing on every launch instead of staying dismissed
- `syn_scanner.py`: a stale placeholder variable silently dropped every genuinely-filtered (no-response) port from scan results
- `internet_exposure.py`: a failed WAN-IP lookup could still show the green "no exposed services" verdict instead of reporting the check couldn't run
- `risk_scorer.py`: a device with only the generic "Vendor risk (UNKNOWN)" placeholder finding showed "No significant risks detected" instead of "Insufficient data" when its actual scans were blocked
- `tls_checker.py`: an unreachable host's certificate check was silently dropped instead of being recorded as could-not-test
- `credentialed_scan.py`: an SSH connection failure (host unreachable) was indistinguishable from a genuine wrong-password result

---

### v2.1.37

**Added**
- Lab Mode: in-app Achievements panel replacing the "Download Badge (PNG)" export — a `QPainter`-rendered hexagon+shield medallion (earned/locked) plus a 4th panel showing all 10 exercise badges and per-certification (Network+/CCNA/Security+) objective coverage, with a completion toast linking straight to it (`modules/lab_achievements.py`, `ui/widgets/badge_medallion.py`, `ui/widgets/lab_scoreboard.py`)
- `modules/curriculum_map.py` — Qt-free curriculum loader shared by the objective badges and the new achievement math, replacing a duplicated loader that only `ui/` could import
- `modules/autostart.py` / `modules/startup_task.py` — Store-aware autostart backend using the WinRT StartupTask API on Store/MSIX builds instead of the HKCU Run key (not the sanctioned mechanism there, and previously produced a "lying checkbox"); `startup/start_minimised` is now a discoverable Settings checkbox

**Changed**
- Inventory Changes page now skips its 15s auto-refresh table rebuild while the page isn't the active nav tab, fixing unbounded RSS growth (507MB → 1.3GB+ over a 6h chaos soak) traced to off-screen `PulsingDot` animation churn

**Fixed**
- Saved window position/size is now clamped to a currently-connected screen before being restored (`_clamp_rect_to_screen()` in `ui/app_settings.py`), preventing the window landing off-screen or oversized after a monitor arrangement or resolution change
- Store/MSIX builds always started maximized regardless of the saved tray-only setting; tray-only launches now stay hidden correctly while still showing the tray icon
- `ui/nav/rail.py`'s `_SmoothProgressBar` crashed with a deleted-C++-object error on a second animation past 250ms because `set_smooth_value()` never cleared `self._anim` after the animation self-deleted
- 5 drifted/missing `data/curriculum_map.json` keys that silently dropped badges for those lab scenarios
- `NetSentinel.spec` was missing `ui.widgets.objective_badge` and `data/curriculum_map.json` from the bundle, which would have silently broken curriculum badges in the installed build

---

### v2.1.36

**Added**
- Lab Mode: animated canvas (`ui/widgets/lab_canvas_card.py`'s `LabCanvasCard`, embedding the Protocol Visualizer's `ProtocolCanvas` + `FrameAnatomyPanel`) behind `experimental/lab_visuals`; per-scenario completion and best-verdict tracking (`modules/lab_progress.py`, persisted via QSettings) with a completion badge and "N of 10 complete" strip on the picker, and earned objective badges on a PASS; cross-linked with the Protocol Visualizer via a dual Feature Guide listing, a dismissible Home nudge card, and a "See how {protocol} works" cross-sell on the result screen
- `ui/shutdown.py` — module-level, unit-testable shutdown drain that logs entry, per-worker stop/wait timings, and total elapsed to `netsentinel_shutdown.log`
- Chaos harness now drives the real quit path (clicks the titlebar X, the same route `_quit_app` takes) instead of ending on a tray-hide, so shutdown-path regressions are caught by future chaos runs

**Changed**
- `experimental/lazy_pages` graduated to permanent (flag removed) and expanded to `AppTrafficPage`/`ConnectionsPage`, cutting `Dashboard()` construction time ~13% (3.92s → ~3.40s measured)
- Theme switching: merged the Dashboard-level and application-level `setStyleSheet()` calls into one, removing a double whole-app re-polish that was the real cause of multi-second switch stalls; the theme swatch now shows a wait cursor and a completion toast and disables itself for the duration of a switch
- Shutdown: all workers are now signal-stopped concurrently against one shared 3-second deadline instead of serially with no overall bound (previously up to ~90s worst case); the dashboard's raw-socket/Npcap workers no longer use `terminate()`; process exit now uses `TerminateProcess` instead of `os._exit` to remove the remaining Store-build crash/hang exposure; the on-close database checkpoint is now passive (non-blocking)
- Header verdict badge is now clickable and routes to the specific page that raised the current severity (Devices, Rogue Bridge (STP), Broadcast Storm, WiFi Networks, or DNS & Stability) instead of being a dead end
- Alert History gained an "Unacknowledged only" filter so an unacked alert older than the widest history window (7d) is still reachable; `NEW_DEVICE`/`DEVICE_GONE` alerts now persist like their `IP_CHURN` sibling; a 5th status-bar pulse segment shows live unacked-alert count/severity
- Settings page no longer shows a false "unsaved changes" warning — every field already saved on change; replaced with a transient "Saved" confirmation

**Fixed**
- `ctypes` HANDLE-marshalling bug in `is_store_app()` (`modules/utils.py`) made Store-package detection silently return `False` on every machine since v2.1.33 — Store builds advertised a GitHub download and `winget upgrade`, neither of which a Store user can act on; both banners now correctly detect the package and link to the Store product page instead
- Startup white/black flash caused by a parentless `protovizNudgeCard` (Home page) briefly becoming its own top-level native-chrome window before being added to its layout (RULE-WIN7)
- Maximized-restore geometry correction racing Qt's first paint under CPU contention, which could flash the unpainted maximized backbuffer white/black on 2nd+ launches
- Low-contrast `FreshnessStrip` "Last scan"/"Next scan" labels on the nav bar (1.93:1 in Arctic Clean, now 6.58:1/7.44:1) and invisible `QSpinBox` up/down stepper glyphs
- `QSpinBox` +/- buttons unclickable app-wide under the real Windows 11 Qt style across 15 more call sites, plus residual text clipping; centralized in `style_spinbox()` with an AST test guarding every call site
- `QTimer`/table leak in skeleton loading rows when a scan never completed, which could later call `.stop()` on an already-deleted `QTimer` after CPython reused the table's `id()`
- Duplicated synchronous data-prune running on every startup on top of the async prune worker `app.py` already runs
- 3 open CodeQL alerts (two incomplete URL substring-sanitization checks, one unused import) and an import-and-import-from collision in `test_shutdown_drain.py`

---

### v2.1.35

**Added**
- `modules/metric_store_writes_batch.py` (`_BatchWritesMixin`) — `record_app_traffic_samples()` / `record_availability_cycle()` batch a whole write burst into one SQLite transaction; wired into `ui/tabs.py`'s app-traffic sample handler and `modules/availability_monitor.py::run_cycle`, cutting commits from 25→1 and 102→12 per cycle respectively
- Covering indexes `idx_known_device_last_seen` / `idx_grade_result_ts` (schema v20) for the known-device and grade-history queries
- `modules/suggestion_engine.py` — pure, unit-testable extraction of the Home page's "what to do next" suggestion logic from `ui/tabs_logger.py`, with 5 new rules: certificate-expiring-soon, trend-forecast-degrading, grade-regression, new-devices-since-last-visit, and an ARP/storm → Protocol Visualizer cross-sell; suggestions are now priority-sorted (high > medium > low) instead of insertion order

**Changed**
- `DeviceTracker.process_scan()` now reads `known_device` once per scan cycle instead of up to 5 times

**Fixed**
- `ui/native_chrome.py` / `ui/header.py`: opening Network Map's `QWebEngineView` forced Qt to destroy and recreate the top-level window handle, dropping the native-chrome subclass and permanently exposing Windows' real title bar above the custom header (with a "restart" flash a few seconds after startup) — the web view's container is now marked native ahead of time, and `AppHeaderMixin` reinstalls the chrome subclass on any future handle recreation as a safety net
- 24 more close/dismiss buttons across the app (toast, alert drawer, page header, overview tile, log hub, notification history, monitor state, diagnosis page, coach mark, quick check window, weekly report/usage insights cards, Ookla CLI banner, plugin hub) that could silently fail to paint their bare-glyph icon under native Windows text rendering — widens the v2.1.34 Home-page fix to the rest of the app
- Resolved two open CodeQL alerts: a cyclic import between `protocol_frames.py` and `protocol_animator.py`, and a URL substring-sanitization test assertion tightened to exact-equality

---

### v2.1.34

**Added**
- `ui/widgets/protocol_canvas.py`: cinematic rendering overhaul for the Protocol Visualizer — curved bezier packet paths with fading motion trails, arrival pulse rings, staggered broadcast rings, role glyphs, a backdrop dot-grid, a step-progress strip, and a 0.5x/1x/2x speed toggle
- `ui/widgets/frame_anatomy_panel.py` + `modules/protocol_frames.py`: collapsible Frame Anatomy inspector on the Protocol Visualizer — real layered Ethernet/IP/UDP/TCP and per-protocol payload breakdowns across all 10 scene builders, using real scan data where available
- `ui/widgets/protocol_storyboard.py`: "Copy image" / "Save PNG..." canvas export and a "Storyboard" filmstrip export (one panel per animation step) for the Protocol Visualizer, plus a right-click context menu exposing all three actions
- `modules/live_protocol_feed.py` + `workers/live_protocol_worker.py`: LIVE MODE for the Protocol Visualizer (ARP/DNS) — watch real captured traffic animate on the canvas as it happens, behind `experimental/protoviz_live` (default off), gated by the same admin/Npcap capability pattern as `LldpWorker`

**Changed**
- Protocol Visualizer now defers construction behind `experimental/lazy_pages` like the other 10 deferred pages, buffering fed scan-context so the first-ever visit in a session still shows current data instead of an empty state
- Restored `ProtocolCanvas`'s own built-in minimum height (240px) on the Protocol Viz page — the richer canvas visuals no longer feel cramped under the page's old 120px override
- Removed two dead widget modules (`ui/widgets/overview_tile_monitor.py`, `ui/widgets/scan_summary_sheet.py`) that were bundled into the shipped exe via `NetSentinel.spec` but never imported anywhere — shrinks the installed exe, no behaviour change
- Refreshed stale test-count figures in `README.md` and `docs/architecture.md` (suite had grown to 5,469 tests across 411 files; docs still read 5,243/398 and 5,291/405 respectively)

**Fixed**
- `ui/widgets/device_detail_pane.py`: device history drawer's close button (Network Map, Devices/Inventory) — a bare Unicode "x" glyph silently failed to paint on native Windows text rendering; replaced with a QPainter-painted icon via a shared `_wire_close_icon()` helper
- `modules/smb_enumerator.py`: guarded `subprocess.CREATE_NO_WINDOW` (Windows-only) behind a `getattr(..., 0)` fallback in `_net_view_shares`/`_net_exe_enum`, matching the existing pattern in `service_diagnostics_probes.py`
- `ui/pages/home_page.py`: three dismiss buttons (browser-dashboard strip, delta banner, post-scan sheet) rendered as invisible tofu (U+FFFD replacement character) on native Windows text rendering — the file's close-glyphs had been mojibake since v2.1.13; replaced with the same painted-icon pattern used for the device drawer close button

---

### v2.1.33

**Added**
- `ui/pages/protocol_viz_page.py`: clickable "Steps" list on the Protocol Visualizer — click any step to jump directly to it, with two-way sync between playback and the highlighted row (closes claims-audit F-48)
- 802.11 EAPOL frame classification in `workers/wifi_monitor_worker.py` (F-16)
- SNMP CPU/load polling in `modules/snmp_poller.py` (F-69)

**Changed**
- Network Map: mesh-only Wi-Fi clients that never answer ARP (e.g. the scanning PC itself) are now synthesized once in `NetworkMapPage.render()`, so the Classic and Interactive (Cytoscape) maps always agree on the device set
- Login Test now shows real last-update timestamps for credentialed scans instead of a placeholder (F-78)
- OS Detection reuses prior port-scan results instead of re-scanning (F-72)
- SMB share risk flags now require anonymous visibility, not just a non-hidden share name (F-88)
- Microsoft Store builds now point users at the Store's own update page instead of GitHub/`winget upgrade`, which is disallowed for Store installs
- `BACKLOG.md` retired — the four items left unbuilt (F-56, F-14, F-68, F-74) now carry "considered, deferred" notes directly in `docs/internal/claims-audit.md`

**Fixed**
- `ui/widgets/overview_tile.py`: dropped the unsupported QSS `cursor:default` property (Qt has no such property; it warned on every stylesheet apply) in favor of `setCursor()`
- `ui/live_graph.py`: stopped repeated `ax.legend()` / `set_tight_layout` stderr warnings by only calling `legend()` when a labelled artist exists and using explicit `subplots_adjust` margins
- Home page pending-alerts row label: a mixed f-string/non-f-string `themed_ss()` template left an unparseable QSS brace, logging "Could not parse stylesheet of object QLabel(...)" on every startup while restoring the last scan; guarded by `tests/test_themed_ss_callable_braces.py`

---

### v2.1.32

Shutdown-stability fix. No user-facing features or settings changed.

**Fixed**
- Always-on background monitors (`syslog` / `SNMP-trap` receivers, the passive SSDP/mDNS observer, and scheduled posture probes) are now stopped when the app quits, before the hard `os._exit(0)`. They were created in `app.py` but never registered with `Dashboard.closeEvent()`, so a raw-socket receiver could be mid `recvfrom()` during process teardown and crash with `STATUS_ACCESS_VIOLATION` — or hang — on exit
- `SnmpTrapWorker`/`SyslogWorker` now close their socket in `stop()` to interrupt the blocking read immediately, and `closeEvent` drains these workers without `terminate()` — calling `TerminateThread` on a thread inside a raw socket / Npcap call is what corrupted the teardown
- Removed the dead post-`app.exec()` cleanup block in `app.py` (unreachable because `closeEvent` hard-exits first); relocated the hardware-integration poll-worker `closedown()` into `closeEvent`

---

### v2.1.31

Documentation-accuracy release. No user-facing features or settings changed.

**Changed**
- Refreshed stale test-count figures in `README.md` and `docs/architecture.md` (suite had grown to 5,243 tests across 398 files; docs still read 4,890/344 and 5,109/370 respectively)
- Logged the 2026-07-13/14 overnight chaos soak in `project-vision.instructions.md` — 9,729 UIA interactions across mild/moderate/wild laps (1,291 / 3,397 / 5,041), zero crash-log growth, zero exceptions, flat peak RSS (674 → 775 → 750 MB)

---

### v2.1.30

Window and accessibility fixes. The headline is a long-standing UI Automation fault at startup: NetSentinel is now correctly readable by screen readers (Narrator, NVDA) from the moment it launches.

**Added**
- `ui/uia_warmup.py` — forces UIAutomationCore's one-time lazy init during startup, from a context where the COM call it makes is legal

**Changed**
- **Aero Snap, Snap Layouts, Win+arrow, drag-to-snap, shake and native edge-resize now work** — the custom header is drawn into a REAL Win32 window with only the frame *painting* suppressed (`WM_NCCALCSIZE`), instead of the frameless `WS_POPUP` Windows never considered snappable. This is now the default for every Windows user; the `experimental/native_chrome` flag is gone rather than merely defaulted on, so a stale stored `false` cannot keep anyone on the old window (`ui/native_chrome.py`)

**Fixed**
- Screen readers and other UI Automation clients could not attach cleanly at startup — the first `WM_GETOBJECT` the process answered raised `0x8001010d` (`RPC_E_CANTCALLOUT_ININPUTSYNCCALL`), because UIAutomationCore's one-time init needs an outgoing COM call and Windows always delivers that message inside an input-synchronous `SendMessage`
- The maximize button covered the taskbar instead of docking to the work area
- The window no longer starts a title-bar's height (~32px) below where it was left, leaving a strip of bare desktop above the header

---

### v2.1.29

Ships Instant Theme Switching — clicking a theme swatch in Settings now restyles the whole running app immediately, no restart required. Closes out the multi-phase live-theme-conversion project (all `ui/` files now read theme tokens live).

**Changed**
- `_on_theme` (`ui/pages/settings_cards.py`) now always applies the theme live via `apply_theme()` — removed the `experimental/live_theme_switch` QSettings flag and the legacy restart-required path
- Theme picker description now reads "Takes effect immediately" instead of "restart the app to apply"

**Fixed**
- 802.11 Monitor page (`ui/pages/wifi_monitor_page.py`) crashed on both "Start Monitoring" and "Stop Monitoring" — `_set_status()` was passed a resolved colour value instead of the expected theme-token name, raising `AttributeError`
- Resolved a CodeQL `py/unused-global-variable` alert in `ui/pages/log_source_panel.py` — added an explicit `__all__` so its cross-module constants/helpers (consumed only via `log_hub_page.py`'s import) are recognised as public

---

### v2.1.28

Stability and architecture-hygiene release — a batch of resource-leak, thread-safety, and data-correctness fixes, plus enforcement of the three-layer UI/data/module separation (ARCH RULE 1). No new features.

**Changed**
- Enforced the three-layer architecture boundary (ARCH RULE 1) — all UI writes to `MetricStore` now route through the module layer, `modules/settings_io.py` is PyQt-free, and the UI no longer imports `modules/alert_engine.py`

**Fixed**
- Closed leaked sockets, subprocesses, and child processes on error/timeout paths — across the discovery/enumeration modules, the STP/broadcast-storm scan, the DNS zone-transfer (AXFR) socket, and the Ookla CLI speed-test child
- Moved `netsh` firewall block/unblock calls off the GUI thread so a firewall action no longer stalls the UI (RULE 4)
- Stopped the vendor-lookup worker cooperatively instead of `terminate()`, and guarded against scan re-entrancy destroying in-flight workers
- Coalesced `HistoryPage` refresh requests so concurrent refresh workers no longer pile up
- Preserved `known_device.ip` on a vendor-only upsert and preserved unset fields on a partial `save_device_annotations` update, closing two silent data-loss paths
- Translated five raw worker-exception error slots into plain English (RULE-A2)
- Marked failed toast deliveries as `FAILED` rather than `DELIVERED`, logged previously-silenced snooze-registry failures, hardened notification strings, and fixed a scan status that could stay stuck on "Running"
- Dropped `NEW_OPEN_PORT` from the Security Audit acknowledge scope and routed audit dispatch through the `NavLabel` enum

---

### v2.1.27

Polish and stability release — sharpens the two built-in themes for contrast, fixes an intermittent startup COM-reentrancy fault, speeds up first paint, and repairs a CI gap that was silently hiding most of the test suite. No new features.

**Changed**
- Kept the theme lineup at two polished options (`Arctic Clean` light, `Midnight Pro` dark) and folded in the only measurable clarity wins from the experimental Sentinel palettes: `Arctic Clean` table headers deepened to indigo `#14205A` (white-on-header contrast 11.6→15.2:1) and `Midnight Pro`'s accent brightened to royal-blue `#3B82F6` (accent-on-card 4.32→4.63:1, now clears WCAG AA), with the full Midnight accent family (`SIDEBAR_SEL`, `BLUE`, `CHART_TITLE`, info/update-bar text) re-tinted to match
- Faster first paint — the Network Map's `WebEngine` view and the Threat Intel table now build lazily in `showEvent()` instead of during Dashboard construction; behind the opt-in `experimental/lazy_pages` flag, 10 leaf pages also defer construction until first shown
- APM instruction pipeline is now Claude-only — dropped the unused Copilot/Gemini targets and removed the generated `AGENTS.md`, `GEMINI.md`, and `.github/instructions/` outputs (dev tooling only)

**Fixed**
- Startup COM-reentrancy fault — the system-tray icon's `show()` and the remaining `Shell_NotifyIcon` call-outs are now deferred to `showEvent()` / guarded, stopping an intermittent `STATUS_ACCESS_VIOLATION` fault on some Windows machines (`ui/system_tray.py`, `ui/header.py`)
- CI was silently running only part of the test suite — a Dashboard test reaching `closeEvent()` → `os._exit(0)` terminated pytest early with a green exit; the offending Dashboard tests are now subprocess-isolated and `tests/test_suite_completes.py` guards against the regression, and the chaos-test focus guard was hardened to log and reclaim rather than skip
- `--tracemalloc` memory-soak launches again — tracemalloc now traces 1 frame and activates 3 s into the event loop instead of inline before `app.exec()`, so the window appears in ~11 s rather than timing out the soak harness (dev tooling only)

---

### v2.1.26

Internal tooling and dev-process release — consolidates monkey-test tooling into one budget-driven runner, closes a sleep/screensaver gap that could kill unattended chaos runs, repairs the APM instruction-compilation pipeline, and fixes a page-help popover that could get stuck open. No user-facing feature changes.

**Added**
- `logger/SPEC.md`, `logger/PLAN.md` — normative spec and phased build plan for a headless Raspberry Pi remote sensor logger feeding NetSentinel over MQTT (design-only, no code yet)
- `docs/chaos-testing.md` — documents the consolidated monkey-test workflow, linked from `docs/index.md` and `CONTRIBUTING.md`
- Memory-soak mode in `tools/run_all_monkey_tests.ps1` (`test.ps1 <hours> -Soak`) — after the first coverage cycle, runs one long-lived mild/moderate/wild process with `--tracemalloc` instead of restarting every few minutes, so slow memory leaks compound instead of resetting each cycle; `AI_REPORT.md` gains a Peak RSS column and embedded first/last tracemalloc snapshots

**Changed**
- Replaced 7 redundant `run_tests_*.bat`/smoke-test scripts with one budget-driven runner (`test.ps1 [1h|20h|blank]`) that cycles a coverage sweep plus 5 weighted chaos phases with rotating seeds and rewrites `AI_REPORT.md` after every phase
- Re-audited `docs/internal/future-features.md` against the current tree — moved 4 shipped items into a "Recently shipped" section, added Status notes to 10 partial items, corrected 2 factual errors

**Fixed**
- Page-help popover (`?` button) no longer gets stuck open after navigating to another page — `PageHeaderBar.hideEvent()` now auto-dismisses it; removed the unused "What can I do here?" tooltip-overlay feature (`ui/widgets/help_mode_overlay.py`)
- Chaos-test orchestrator no longer stalls indefinitely if the machine sleeps mid-run — `tools/test_setup.ps1` now holds `SetThreadExecutionState` for the entire run instead of relying on per-phase, admin-only `powercfg` calls that left every inter-phase gap unprotected
- APM governance pipeline: `netsentinel-apm.md` had the wrong filename suffix so its plan-first/stability rules silently produced zero generated output; restored as `session-workflow.instructions.md` and migrated 3 orphaned rule files (changelog, tests, pr-description) into the compiled pipeline

---

### v2.1.25

Internal maintainability release — an 8-part tech-debt backlog (P1–P8) drawn from a commit-history audit, closing the recurring bug classes the previous 90 commits kept re-fixing. No user-facing features or settings changed and behaviour is unchanged; all 4,875 tests pass (8 skipped). Each sprint shipped with its own ratchet test so the debt cannot silently regrow.

**Added**
- `ui/nav/labels.py` — a `NavLabel` registry giving every nav page label a single typed constant, replacing the raw string literals that were scattered across 23 files; `_nav_rail_go_to()` now logs a loud warning on an unknown label instead of silently doing nothing; guarded by `tests/test_nav_label_registry.py` (P1)
- `workers/base_worker.py` — a `BaseWorker(QThread)` base class with standard `result_ready`/`error`/`progress` signals, a templated `run()` that wraps an overridable `work()` in try/except, and a uniform `request_stop()`; 9 workers migrated onto it; guarded by `tests/test_base_worker.py` and `tests/test_worker_base_class.py` (P3)
- `tools/check_import_lint.py` — an import-hygiene gate (RULE-LINT5) catching CodeQL `py/import-and-import-from` and `py/cyclic-import`, neither of which ruff can detect; wired into `ci.yml` and the RULE-CI1 pre-push hook and guarded by `tests/test_import_lint.py` (P8)

**Changed**
- Converged all nav routing onto the `NavLabel` registry — migrated the four hand-maintained label copies (`_AUDIT_SCAN_LABELS`, `test_nav_completeness`, `discover_data.py`, and the nav builder) and the `navigate_to` wirings in `ui/tabs.py` onto the shared constants, so a page rename can no longer create a silent dead link (P1)
- De-forked `tools/systematic_test.py` — it now imports the blacklist / window-attach / click-guard machinery from `tools/monkey_test.py` (as the other chaos tools already did) instead of re-implementing it, so a safety fix lands once rather than needing to be applied in two places (P2)
- Consolidated shared network primitives into `modules/utils_net.py` — `tcp_probe()`, `get_arp_snapshot()`, and `parallel_map()` replace 14 hand-rolled socket probes, 5 ARP-table reads, 3 rogue subprocess pings, and 14 inline `ThreadPoolExecutor` fan-outs; guarded by `tests/test_utils_net_ratchet.py` (P4)
- Converged 11 duplicated private `_table()` factories onto `ui.tabs_helpers._table()`, resolving their drift (grid lines, resize mode, edit triggers) once so every page's tables behave identically; guarded by `tests/test_table_factory_consolidation.py` (P5)
- Added a QSS recipe layer to `ui/styles.py` (`qss_label`, `qss_muted_label`, `qss_frame`, `qss_chip`, `qss_dismiss_button`) and migrated the three heaviest inline-style files (`home_page.py`, `overview_tile.py`, `settings_cards.py`) onto it; RULE-QSS3, guarded by `tests/test_qss_recipe_adoption.py` (P6)
- Trimmed `ui/dashboard.py` by extracting its self-contained tab builders into `ui/tabs_monitors.py`, `ui/tabs_help.py`, and `ui/export_mixin.py`, and decomposed the ~300-line `_on_m1_result` in `ui/scan_wiring.py` into named single-responsibility steps (P7)
- Extended `tools/check_import_lint.py` with a cross-file unused-global-variable check (RULE-LINT6) and tightened ruff's `dummy-variable-rgx` in `pyproject.toml` to match CodeQL's narrower exemption — closing two blind spots where a dead module-level global or an underscore-prefixed dead local slipped past local linting
- Refreshed the line-count and test-count figures in `README.md` and `docs/architecture.md` (~136,000 lines of Python, 4,875 tests across 343 files)

**Fixed**
- Resolved 46 pre-existing CodeQL `py/import-and-import-from` alerts across ~40 test files, 3 bundled plugins (`asus_plugin.py`, `netgear_plugin.py`, `openwrt_plugin.py`), and `geo_map_page.py` (P8)
- Resolved 4 more open CodeQL alerts — a dead `_log` global (`network_logger.py`), a dead `_cb` local (`snmp_poller.py`), and two unused-public-export false-negatives (`dashboard.py` `_color_for_level`, `nav/labels.py` `KNOWN_LABELS`) — plus 4 additional dead locals surfaced by the tightened lint config (`app.py`, `ui/tabs.py`, `ui/widgets/overview_tile.py`, `tests/test_coach_marks.py`)

---

### v2.1.24

**Added**
- Per-device "Alert me if this device goes down" / "Stop alerting on this device" toggle in the Devices/Inventory context menu (`MetricStore.set_device_alert_opt_in()`, `known_device.alert_opt_in` — schema v19)
- "Unresolved Security Alerts" card on Security Overview — lists unacknowledged security-relevant alerts with an inline "✓ Acknowledge" button per row, reusing `MetricStore.acknowledge_alert()`

**Changed**
- Device-health alerts (`HOST_DOWN`, `RTT_THRESHOLD`, `FLAP`, `JITTER_HIGH`, `RTT_ANOMALY`, `IOT_BEHAVIOR`, `TREND_FORECAST`, `IP_CHURN`, `LOSS_THRESHOLD`, `HOST_DEGRADED`) now fire only for infrastructure-role devices or devices the user has explicitly opted in — previously every device seen in a scan (including guest phones and transient IoT devices) could trigger these; genuine security events (`NEW_DEVICE`, `ARP_SPOOF`, `ROGUE_DHCP`, `NEW_OPEN_PORT`, `NEW_CVE`, `NEW_EXPOSURE`, `CONFIG_DRIFT`, `CERT_EXPIRY`, `CERT_EXPIRED`) remain unaffected by opt-in
- Security Audit rail badge now counts only security-relevant unacked alerts (`SECURITY_RELEVANT_RULE_TYPES`) instead of every unacked alert, so the badge number matches the new Unresolved Security Alerts list on Security Overview
- `MetricStore.record_alert_fired()` now persists a stable `rule_type` column (schema v19); `get_unacked_alerts()` accepts a `rule_types` filter
- Refreshed the line-count and test-count figures in `README.md` and `docs/architecture.md` (~135,000 lines of Python, 4,800+ tests across 330+ files)

**Fixed**
- `speed_tester.py`: the speed-test server-list fetch now retries with backoff and falls back to a last-good cache on failure
- Eliminated a parentless-widget startup flash in `hub_card.py` (Configure button) and `rest_api_page.py` (external-access warning) — widgets are added to their layout before visibility is toggled (RULE-WIN7); guarded by new `tests/test_widget_visibility_order.py`
- Resolved 7 open CodeQL alerts (unused imports/globals, mixed returns)

**Security**
- Hardened the hardware-plugin AI prompts, the plugin template wizard, and 8 bundled plugins against prompt injection

---

### v2.1.23

**Added**
- `modules/lab_badge.py` — renders a Lab Mode completion badge PNG (hexagon/shield motif, scenario title, completion date); new "Download Badge (PNG)" button on the Lab Mode result panel alongside "Try Again"/"Export Report (HTML)"
- `modules/diagnostic_card.py::build_card_data_from_diagnosis()` — quiet "Share this result" strip on the "What's Wrong?" result panel with "Copy as image"/"Copy as Markdown" buttons, shown on every completed run
- `MetricStore.query_previous_grade()` — Network Grade tab now shows a "Your grade improved — share it" strip with "Copy as image"/"Copy as Markdown" buttons, but only on a genuine score improvement between the last two grade runs
- "Copy as Reddit post" and "Copy as email to ISP" buttons on the ISP Accountability Report, reusing `report_isp.generate_isp_complaint_text()` and the new `forum_export.build_isp_forum_markdown()`

**Fixed**
- `ui/styles.py`: added an `alpha()` helper and swept ~60 QSS sites that appended hex alpha as `{COLOR}22` — Qt parses 8-digit hex as `#AARRGGBB` (alpha-first), which scrambled those colours (mostly rendering invisible hover tints, and the Home "live challenge" banner as an opaque dark red); guarded by new `tests/test_qss_hex_alpha.py` (RULE-QSS2)
- `home_page.py`: the Home "live challenge" banner now renders as translucent amber via `AMBER_BG` instead of dark red
- `header.py`: the top-bar "▶ Scan" button now reads as a solid primary button at rest instead of being invisible until hover; the gear and time-range controls use a faint `alpha(WHITE, …)` hairline border so they no longer draw a harsh white box on the dark header bar in Arctic Clean
- `home_data_mixin.py`: the live-challenge banner now leads with the event's own wording (e.g. `New device detected`) instead of labelling every Network Logger event a "Connectivity issue"

---

### v2.1.22

**Added**
- `modules/report_sanitizer.py` — shared sanitizer for public sharing: aliases private IPs to stable `192.168.1.N` placeholders, strips MAC addresses/hostnames, and omits public IPs entirely; makes no network calls
- `modules/forum_export.py` — builds sanitized, forum-ready Markdown summaries for `DiagnosisPage` ("What's Wrong?") and `ServiceDiagnosticsPage` results; wired to new "Copy for Reddit/Discord" buttons on both pages
- `modules/topology_share.py` — renders a sanitized Network Map PNG independently of the on-screen view, so a new "Share (Sanitized PNG)" toolbar button on `NetworkMapPage` can never leak real IPs/MACs/hostnames
- `modules/service_escalation.py` — a `SERVICE_DOWN` heartbeat failure now triggers a background `DiagnosticEngine` probe and a follow-up notification classifying *why* the service is unreachable (filtered by a firewall/VPN/ISP vs. a genuine outage); new "Diagnose why (recommended)" sub-toggle under the `Service Down` alert rule
- `modules/proactive_digest.py` / `workers/proactive_probe_worker.py` — reusable due-check/day-tracking base (used by Morning Briefing) and a generic interval-loop `QThread` for future background probes
- `modules/scheduled_speed_test.py` and a new `BASELINE_DROP` `AlertRule` type — opt-in "Automatic Speed Tests" card on the Speed Test page (1h/3h/6h/12h/24h interval) fires a tray notification when download speed drops severely against your own rolling history, reusing `speed_drop_detector`'s verdict/copy
- `modules/digest_bullets.py` — Morning Briefing now summarizes overnight `SERVICE_DOWN` escalations and `BASELINE_DROP` speed trends, each gated on the corresponding feature's own opt-in state, capped at `MAX_BULLETS` with a "+N more" suffix
- Recurring daily "quiet hours" maintenance windows (`modules/maintenance_window.py`) — suppress scheduled speed tests and their notifications overnight without pausing the underlying heartbeat/monitoring data collection

**Changed**
- `MaintenanceWindowManager.record_suppression()` is now wired into `AlertEngine` via a new `set_suppression_recorder()` hook, so suppressed alerts actually appear in the maintenance suppression log
- `modules/alert_engine.py` maintenance-checker logic split into a new `_MaintenanceSuppressionMixin` (in `modules/alert_suppressor.py`) to stay under the 600-line module budget
- `modules/device_stability.py` and `modules/device_tracker.py` no longer call `MetricStore._execute_write()`/`_execute_read()` directly — all device inventory writes/reads (IP history, annotations, change-event audit trail, stability scoring, topology snapshots) now go through new public `MetricStore` methods; same for `modules/topology_snapshot.py` and the `/devices`/`/uptime` routes in `modules/rest_api.py`
- `modules/metric_store.py` split: device-inventory write methods (`record_ip_observation`, `upsert_known_device`, `record_device_state`, etc.) moved to new `modules/metric_store_writes_device.py` (`_DeviceWritesMixin`) to stay under the module LOC budget

**Fixed**
- Startup flash of a native OS-decorated window (title bar + min/max/close) for a fraction of a second: `ui/tabs_scan.py` (STP Capture / Broadcast Storm empty-state buttons), `ui/pages/home_page.py` (`setupCompleteCard`), and `ui/pages/log_source_panel.py` (Network Logger source-toggle buttons) were calling `.setVisible(...)` on a widget *before* it was added to its parent layout — Qt treats a still-parentless widget as an independent top-level window and gives it full native chrome. Fix: call `.setVisible(...)` only after `addWidget()`
- `device_ip_history.seen_count` no longer double-increments per scan: `ui/scan_wiring.py` was calling `record_ip_observation()` directly in the same handler where `DeviceTracker.process_scan()` (the intended single write path) also calls it, doubling `seen_count`/`scan_count` and skewing `ip_stability` every scan

---

### v2.1.21

**Added**
- `DiagnosticEngine.run_custom()` in `modules/service_diagnostics.py` — Service Diagnostics can now probe any typed hostname (e.g. `github.com`) via a "Custom host…" entry in the picker, not just the streaming/gaming catalog
- New `filtered` failure-layer classification: flags the ICMP-succeeds-but-TCP-fails signature of a firewall, VPN, or ISP silently blocking a connection, distinguishing it from a genuine `remote_outage`

**Changed**
- Navigation colour tokens extracted from hardcoded `rgba()` values into 8 named semantic tokens in `ui/styles.py` (`NAV_RAIL_HOVER_BG`, `NAV_RAIL_ACTIVE_BG`, `NAV_RAIL_FOCUS_BORDER`, `NAV_ITEM_HOVER_FG`, `NAV_ITEM_ACTIVE_FG`, `NAV_FLYOUT_FOCUS_BORDER`, `NAV_ITEM_PIN_HOVER_FG`, `CARD_BORDER`); Arctic Clean sidebar is now white chrome; `rail.py` `refresh_theme()` re-applies full QSS for live switching
- Badge/info-box/inline-warning/banner colours moved into per-theme palette dicts; Midnight Pro card background elevated to `#1C2128`; Arctic Clean canvas cooled to `#EEF2F7`

**Fixed**
- Dark-theme `BORDER` token (`rgba(255,255,255,0.08)`) crashed matplotlib (`ValueError: Invalid RGBA argument`) and silently rendered opaque black in `QColor`; new `CHART_SPINE` plain-hex token routes all non-QSS consumers (spines, edges, dividers, pens) safely
- Monitor resume banner and alert banners now render inside the content area only — both were inserted into the root `QVBoxLayout` and bled over the 48 px nav rail
- `setupCompleteCard` and `recurringIntroCard` now use semantic fill tokens (`GREEN_BG`, `INFO_BOX_BG`) instead of plain `BG_CARD`
- Arctic Clean active nav item text contrast raised from `#0078D4` (~3.7:1) to `#1F4E80` (~6.9:1, WCAG AA+)

---

### v2.1.20

**Added**
- `modules/scan_status_md.py` — renders the Security-Audit scan registry as a GitHub-flavoured Markdown table; "⧉ Copy as Markdown" button on the Security Overview `Scan Status` card copies a shareable status snapshot (tool, state, last-run age, finding) to the clipboard for tickets and email

**Changed**
- Theme lineup consolidated to two polished themes — `Arctic Clean` (light, cohesive cool-slate chrome) and `Midnight Pro` (dark); `Obsidian Neon` and `Abyss` removed. A saved theme that no longer exists falls back to `Midnight Pro` on next launch
- `ui/styles.py`: badge, info-box, inline-warning and IP-calculator cell colours are now theme-aware (moved into the per-theme palette dicts) instead of being baked for a single theme — fixes low-contrast "bar same as background" rendering on the non-design theme
- `Arctic Clean`: sidebar softened from near-black to a cohesive cool slate; primary accent refined from royal blue to slate blue (`#2C6CB0`)
- Monitor resume banner restyled to a neutral surface with a crisp green left accent (was a muddy translucent fill); dismiss `×` and "Stop all" now use visible neutral tokens
- New theme-aware `INPUT_BORDER` token raises form-field border contrast; "Forget Saved Password" recoloured to a destructive red treatment (amber reserved for warnings/stale state); health status card uses a crisp neutral border with a coloured left accent
- `tests/test_theme_consistency.py` extended with a WCAG-AA contrast gate over badge/info-box/inline-warning/banner foreground-on-background pairs and the input-border token, locking theme quality against regression
- Consolidated the APM governance layer (dedupe, de-rot, prune); hardened the chaos-test harness and pinned `wingetcreate`
- `ruff` requirement bumped to `>=0.15.20`

**Fixed**
- Credential loading repaired in 8 bundled hardware plugins
- `protocol_animator` and report charts now use embedded `Figure`/`Line2D` instead of the pyplot state machine
- Restore window focus after dismissing UI banners and cards
- Resolved 4 CodeQL `py/import-and-import-from` alerts in test files
- Untracked `NetSentinel.ini` temp file; ignore `NetSentinel.ini.*`

---

### v2.1.19

**Changed**
- `.claude/skills/check.md` — new session-start health-snapshot skill (`/check`)
- `.claude/skills/triage.md` — new bug triage skill (`/triage`) writes structured records to `.triage/`
- `.claude/skills/debug.md` — added Phase 6 "Improve" section: after every fix, evaluate whether a new `RULE-*` should be written while the mechanism is fresh

---

### v2.1.18

**Added**
- `modules/device_types.py` — canonical device-type label constants (`TYPE_SMART_PLUG`, `TYPE_SMART_THERMOSTAT`, `TYPE_SMART_BULB`, Matter); import from here, never hardcode strings (P1-1–P1-4)

**Fixed**
- Nest vendor regex no longer collides with generic Nest thermostats; wearable dead-code path removed (P0-1, P0-2)

---

### v2.1.17

**Fixed**
- Monitor resume bar now uses informational blue styling instead of amber/warning — resuming a monitor from the previous session is expected behaviour, not a caution event
- "Action needed" card on Home page no longer appears for offline devices; card is now reserved for genuine unacknowledged user-configured alerts only

---

### v2.1.16

**Added**
- `modules/protocol_animator_extra.py` — five additional scene builders (OSPF Hello/LSA, NAT translation, VLAN 802.1Q, TLS 1.3 handshake, ICMP traceroute); Protocol Visualizer expanded from 5 to 10 protocols with a 2-row button grid
- Security Overview Scan Center card — per-audit verdict, last-run timestamp, and staleness timer; scan registry persists results across restarts
- Scan Status tile on the Overview page with live verdict chips for all 5 audit categories
- Last Run chips on the Security Overview header row for at-a-glance audit freshness

**Fixed**
- Security Overview "Run Audit" button now navigates to the correct audit page (was running silently in background with no visible feedback)
- Verdict strings wired into all 5 Scan Status card rows (rows previously showed blank verdict)

---

### v2.1.15

**Added**
- `ui/widgets/inventory_dialogs.py` — `_DeviceLabelDialog`, `_TypeOverrideDialog`, `_ScanCompareDialog`, `_SegmentEditorDialog` extracted from `inventory_page.py` (Sprint 11)
- Settings page category chip bar (`All | Appearance | Monitoring | Alerts | Integrations | Advanced`) with `QSettings("settings/last_category")` persistence
- `ui/guided_tour.py` — 5-step first-run guided tour using `tour/v2_done` key; auto-starts on first launch, restartable from Settings → Advanced
- `ui/widgets/scan_radar_widget.py` — phosphor-green radar sweep animation on Home page during scan wait state (Sprint 6)
- `modules/alert_engine_checks.py` — `_AlertChecksMixin` split from `alert_engine.py` for cert/service check evaluation (file budget relief, Sprint 2)
- Empty state cards with inline "Run Scan" CTA on 8 pages: Connections, CVE, DHCP Lease, DNS Zone, Geo Map, Security Overview, Threat Intel, Uptime (Sprint 5, RULE-UX5)
- Right-click context menus on all 19 scan result tables with "Copy" and "How to Fix" actions (Sprint 4, RULE-UX3)
- Loading states and skeleton placeholders on scan-dependent pages (Sprint 7, RULE-UX2)
- Radar sweep and scan progress bar moved inline into Home page action bar (replaces separate widget)
- RULE-T2 worker lifecycle tests for 22 workers; REST API security tests (`test_rest_api_security.py`)
- Behavioral integration tests for 18 additional pages (`BaselinePage`, `CertPage`, `DhcpLeasePage`, `DnsZonePage`, `GeoMapPage`, `HomeAutomationPage`, `IpCalculatorPage`, `LabModePage`, `LiveBandwidthPage`, `MaintenancePage`, `MonitorOverviewPage`, `MqttPage`, `NetworkDocPage`, `ProtocolVizPage`, `SnmpTrapPage`, `SyslogPage`, `TimelinePage`, `TrendPage`)

**Fixed**
- Devices table blank after scan — `DeviceInfo.get()` was eagerly evaluated before data arrived; now lazy
- Three Inventory scan bugs: vendor not persisted after enrichment, mesh enrichment overwriting live data, blank cells on re-scan
- Scan wiped Devices table for ~10 s on every scan — previous table data now preserved during scan and replaced atomically on completion
- Discovered Devices showing only raw IPs after restart — `_m1_table` now seeded from network map cache on startup
- Redundant left sidebar removed from Settings page; chip bar is now the sole category navigator
- Parented `QTimer(self)` replaces all unparented `QTimer.singleShot` calls in widget classes (RULE-WIN5)
- Removed `__import__` abuse in plugin system; bare `except` blocks annotated with RULE-LINT2 comments
- Chaos foreground claim now asserted before chaos iterations begin, preventing first-iteration miss

---

### v2.1.14

**Fixed**
- `ui/command_palette.py`: `hideEvent` now calls `parent().activateWindow()` so closing the palette returns focus to the main window instead of falling through to the Windows Desktop
- `ui/pages/hardware_integration_page.py`: re-entry guards (`_browse_active`, `_register_active` flags) on `_on_browse` and `_register_plugin` prevent duplicate file/credential dialogs from rapid clicks
- `tools/monkey_test.py`: added RULE-LINT2 inline comment to bare `pass` in `except` block

---

### v2.1.13

**Fixed**
- Monitor resume bar dismiss button (✕) now uses amber accent colour instead of `TEXT_SECONDARY`, making it visible across all three themes

---

### v2.1.12

**Added**
- `ui/perf_audit.py` — `warn_if_nav_slow()` nav timing warnings and `profile_page_init()` cProfile wrapper for page-init instrumentation
- `ui/widgets/feedback_dialog.py` — local in-app feedback dialog; writes timestamped entries to `feedback.log` with no network calls; accessible via Ctrl+K "Give Feedback"
- `STATUS_ICON_OK/WARN/CRIT/UNKNOWN` shape constants in `ui/styles.py`; applied in service heartbeat, uptime, and monitor verdict displays so status is not conveyed by colour alone
- Focus rings (`QPushButton:focus` CSS) on activity-rail buttons and flyout items for keyboard navigation
- `tests/test_status_icons.py`, `tests/test_keyboard_nav.py`, `tests/test_empty_state_audit.py`, `tests/test_loading_state_audit.py`, `tests/test_theme_consistency.py`, `tests/test_feedback_dialog.py`, `tests/test_perf_audit.py` — UX audit test suite

**Fixed**
- Stripped UTF-8 BOM from `ui/nav/rail.py` that caused silent `SyntaxError` in `ast.parse`-based test checks
- `test_no_duplicate_methods.py` now correctly exempts `@pyqtProperty` getter/setter pairs from the duplicate-method check

---

### v2.1.11

**Added**
- `modules/cdn_ranges.py` — static CDN/streaming-provider IP range classifier (Netflix/YouTube/Twitch/Disney+) for App Traffic device drill-downs
- `modules/traffic_insights.py` — household usage narrative, ISP plan utilization, and QoS overlap recommendation builders
- `modules/service_bandwidth_overlay.py` — bandwidth-sharing context note for Service Diagnostics
- `ui/widgets/usage_insights_card.py` — home page "Usage insights" card (weekly category breakdown, plan utilization, dismissible QoS suggestion)
- `app_traffic_sample` table (schema v17) persists App Traffic history; new "Last 24 Hours by Category" chart on the App Traffic page with click-to-drill-down by device and CDN
- "Internet Plan" settings card — optional monthly data cap feeding plan utilization on the home page

---

### v2.1.10

**Added**
- Persistent device map: after each scan, pinned and static-candidate offline devices (infrastructure roles, IP-stable seen 3+ times) are appended to the Inventory snapshot with freshness state `pinned`, `cached` (<24 h), or `stale` (<7 d); implemented in `ScanResultMixin._merge_scan_with_persistent()` (`ui/scan_wiring.py`)
- "Hide offline" toggle in the Current Devices card header hides `cached`/`stale` rows without discarding the persistent map; resets on navigation

**Fixed**
- `ui/scan_wiring.py`: `_store_ref` used before assignment in `_on_m1_result` inventory block; replaced with `_inv_store` to fix silent `UnboundLocalError` that prevented segment detection from running

---

### v2.1.9

**Fixed**
- `modules/topology_cytoscape.py`: removed re-export block that created a cyclic import with `topology_cytoscape_html`
- `modules/topology_cytoscape_html.py`: promoted lazy `build_cytoscape_elements` imports to module-level now that the cycle is broken
- `tests/test_topology_cytoscape_html.py`: unified import form to `from modules import topology_cytoscape_html` to resolve CodeQL `py/import-and-import-from`

---

### v2.1.8

**Changed**
- Overview tiles: staleness callout shown when data is >24 h old ("Data from X days ago — rescan?" in amber); 30 min+ shown in amber, 2 h+ in red
- Notifications page: split into "Configure" tab (channel cards, alert rules, dependency tree) and "Alert History" tab; switching to history auto-refreshes the log
- Alert history: storm banner appears when ≥5 alerts from the same /24 subnet arrive within 60 s, with a direct link to the dependency tree card
- Auto-resume: monitors (ARP Watch, Live Bandwidth, Scheduled Scans) that were running on last close are restarted on the next launch with an opt-out amber banner

**Fixed**
- `ui/nav/builder.py`: removed invalid `_nav_add_subgroup()` calls in `_build_pro_nav()` that crashed the app with `KeyError: -1`

---

### v2.1.7

**Added**
- `modules/topology_cytoscape_html.py` — HTML/JS page template builder for Cytoscape map split from `topology_cytoscape.py`
- `ui/pages/notif_dep_card.py` — `_NotifDepMixin`: alert dependency tree card; parent–child alert suppression with `_AddDepDialog`; QSettings persistence
- `ui/widgets/alert_drawer.py`: inline acknowledge form with name/comment fields; ack info badge shown on already-acknowledged alerts
- `ui/pages/network_map_page.py`: "Lock Layout" toggle — freezes node positions so re-scans update data without resetting the Cytoscape layout; incremental `window.updateTopology()` used after first load to prevent positional drift

**Fixed**
- `modules/topology_cytoscape.py`: `build_elements_for_update()` exported for incremental topology refreshes without full HTML reload

---

### v2.1.6

**Added**
- `modules/snmp_poller.py`: SNMP interface error metrics — `ifInErrors`/`ifOutErrors` polled per interface; stored in MetricStore and surfaced in SNMP Device Info page

**Fixed**
- Startup cache restore — Network Map and topology widget now render from MetricStore cache on startup without requiring a rescan
- Interactive Network Map blank after scan — Cytoscape.js JS error when master mesh node was referenced as a parent
- Classic and Interactive topology satellite assignments now match the Devices table

---

### v2.1.5

**Fixed**
- All matplotlib chart backgrounds now use `ui/styles.py` tokens
- `QTimer.singleShot` calls replaced with parented `QTimer(self)` instances across widget classes
- `app.py` wiring refactor — always-on worker signals connected after `Dashboard` construction
- Network Map interactive view: hierarchical top-down Cytoscape.js layout and LLDP hint + WebEngine fallback polish

---

### v2.1.4

**Added**
- `modules/lldp_scanner.py` — LLDP/CDP neighbor scanner; passive sniff + active frame mode; raw TLV parser; `LldpNeighbor` dataclass
- `workers/lldp_worker.py` — `LldpWorker` QThread; 15-second sniff in 3-second slices; emits `result_ready(list[LldpNeighbor])`; no-op when not admin
- `modules/topology_snapshot.py` — `TopologySnapshot`, `TopologyDiff`; save/load/diff topology state; change detection for new/removed/moved devices
- `ui/topology_widget.py`: LLDP overlay layer, topology diff overlay, zoom controls, node click → `DeviceDrawer`, health overlays on edges
- `ui/scan_wiring.py`: `_on_lldp_result()` slot wired into `_on_m1_result()` to auto-launch LLDP scan after every device discovery
- `tests/test_lldp_scanner.py` — 11 tests covering import, dataclass, TLV parsing, mocked sniff, and worker lifecycle
- `tests/test_topology_snapshot.py` — tests for `TopologySnapshot` save/load/diff

**Changed**
- `modules/topology_layout.py`: layout keyed on scan-derived `compute_scan_id()` hash so saved positions survive interface changes without poisoning unrelated scans
- Topology map segment pill colours now reflect `NetworkSegment.colour` from `modules/network_segments.py`

---

### v2.1.3

**Added**
- MetricStore schema v13: `device_classification_overrides` table — user-set type overrides survive all enrichment re-runs permanently
- `modules/device_classifier.py`: `get_all_device_types()` — sorted list of every valid device type label for UI dropdowns
- `inventory_page.py`: `_TypeOverrideDialog` — right-click "Override Device Type…" on any device; type combobox with Set/Clear/Cancel
- `inventory_page.py`: confidence indicator prefix in Type column (★ user override, ● high ≥70%, ◑ medium 30–70%, ○ low <30%)
- `inventory_page.py`: Classification section in device detail drawer — current type, override badge, confidence level, evidence list, Clear Override button
- `ui/scan_enrichment.py`: override guard in `_apply_dhcp_fingerprints()` and `_on_passive_observation()` — user-set overrides block all automatic enrichment upgrades
- `tests/test_device_classifier.py`: 5 new tests for `get_all_device_types()`

---

### v2.1.2

**Added**
- `modules/network_segments.py` — `NetworkSegment` dataclass, `auto_detect_segments()`, `classify_device_segment()`, `merge_segments()`; groups scan devices into colour-coded /24 subnets
- MetricStore schema v11: `network_segments` table (CIDR unique, `auto_created` flag, user-editable name/colour)
- `inventory_page.py`: colour-coded segment pill bar above the device table with multi-select filter; Segment `●` column; `_SegmentEditorDialog` for right-click segment editing
- `ui/scan_wiring.py`: segments auto-detected and persisted after every full scan; stored user-defined segments win over auto-detected ones on CIDR conflict
- `tests/test_network_segments.py`: 15 tests covering detection, classification, merge logic, and scaling guard

---

### v2.1.1

**Fixed**
- `modules/rogue_device.py`: proxy-ARP deduplication — IPs sharing the gateway MAC are collected in `proxy_arp_ips` and excluded from device results so the gateway never appears twice
- `modules/rogue_device.py`: gateway device always classified as `Router / Gateway` via `is_gateway` parameter, chip-OUI heuristic, and consumer-hostname sanity check
- `ui/scan_enrichment.py`: gateway hostname guard in plugin enrichment loop — plugin client entries whose IP matches the gateway are skipped
- `ui/scan_enrichment.py`: gateway MAC filtered from `_plugin_enrichments` so the router's own MAC never appears as a client device
- `ui/scan_enrichment.py`: IP-keyed hostname sync skips the gateway `DeviceInfo` object to prevent the mesh/table-cell sync from overwriting the gateway hostname
- `ui/scan_enrichment.py`: post-enrichment device-type cell sync writes `DeviceInfo.device_type` back to the Devices table for all devices with a known type
- `tests/test_scan_enrichment.py`: regression test for shared-MAC (proxy-ARP) sync

---

### v2.1.0

**Added**
- `modules/service_mapper.py` — device_type/vendor → `ServiceInfo` list mapping engine; feeds Service Diagnostics and Service Heartbeat
- `modules/service_diagnostics.py` — `DiagnosticEngine` with service catalog (Netflix, YouTube, Steam, Xbox, PS5, Disney+, Twitch, Spotify) and failure-layer classification
- `modules/service_diagnostics_probes.py` — low-level DNS/TCP/HTTPS/ICMP/traceroute probes used by `DiagnosticEngine`
- `workers/service_diagnostics_worker.py` — `ServiceDiagnosticsWorker` QThread wrapping `DiagnosticEngine.run()`
- `ui/pages/service_diagnostics_page.py` — Service Diagnostics page in the Monitor section; service picker combobox, traceroute toggle, live probe results with per-layer verdict cards
- `DiagnosisPage`: "A service is unreachable" symptom tile — runs `ServiceDiagnosticsWorker`, translates `failure_layer` into a synthetic finding card with plain-English remediation steps
- `ServicePage`: "Diagnose →" right-click context menu item — maps the selected service host to a `SERVICE_CATALOG` entry and navigates to `ServiceDiagnosticsPage` with that service pre-selected
- `ServiceDiagnosticsPage.set_service(id)` — public method to pre-select a service programmatically and focus the Run button
- `tests/test_sprint5_integration.py` — 22 tests covering layer translation, CTA map, `_find_service_id()`, widget state, and `set_service()` pre-selection

**Fixed**
- `ui/scan_enrichment.py`: vendor/type enrichment now populates on first scan — async OUI lookup for Unknown devices without requiring a re-scan
- `modules/service_diagnostics_probes.py`: IPv6 address cast to `str` before assignment; `CREATE_NO_WINDOW` guarded with `getattr` for non-Windows platforms; traceroute reach-check now correctly references `result.host`

---

### v2.0.1

**Fixed**
- Sorting any table column no longer crashes with `TypeError` — PyQt6 `Qt.SortOrder` enum now correctly accessed via `.value` before storing to `QSettings`
- `setTextAlignment()` calls in `dhcp_lease_page`, `dns_zone_page`, and `threat_intel_page` now pass the `Qt.AlignmentFlag` enum directly instead of wrapping in `int()`
- All tables using the shared `_table()` helper now auto-size columns to content (`ResizeToContents`) instead of a fixed 120 px default; last column stretches to fill available space
- Network Grade table columns (Dimension, Grade, Your Value, Ideal, Verdict) no longer truncate text

---

### v2.0.0

**Added**
- `packaging/AppxManifest.xml`: declared `windows.startupTask` (uap5, disabled by default) — enables user-controlled auto-start via Settings → Apps → Startup for Microsoft Store builds
- `app.py`: `--startup-logger` flag — starts the app minimised to the system tray and auto-starts the Network Logger; fired by the Windows startup task when the user opts in

**Changed**
- `ui/system_tray.py`: "Launch at Startup" registry entry now registers `--startup-logger` instead of `--minimised`, so enabling auto-start also begins background logging
- `ui/pages/settings_cards.py`: startup checkbox label updated to reflect that auto-start runs as a background logger

---

### v1.9.x

Development sprint versions (v1.9.48 – v1.9.99). See [git commit history](https://github.com/ossianericson/netsentinel/commits/main) for details.

**Highlights**
- PyInstaller single-exe packaging, Windows Installer (Inno Setup), WinGet distribution
- Plugin ecosystem with `.nspkg` format, signed plugins, multi-instance hardware Hub cards
- CodeQL security hardening and 4,100+ automated tests
- Monkey/chaos tester: 10,001 UIA interactions across 62 pages, zero crashes
- Microsoft Store certification build
