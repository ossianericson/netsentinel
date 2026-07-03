# NetSentinel — V6 Backlog: "Find Real Problems For Me"

**Version baseline:** v2.1.22
**Status:** Approved long-term roadmap, 2026-07-02. Explicit user request — this
backlog is the exception to the "no new features" policy in project-vision.
**Theme:** Close the gap between "data we collect" and "problems we surface
automatically". v2.1.22 (SERVICE_DOWN escalation, BASELINE_DROP, Morning
Briefing) found real issues on a real network; every item below extends that
pattern.
**How to use:** Copy one sprint section into a new chat. Each section is
self-contained. Tick items here as they ship.

---

## Why these items (survey findings, 2026-07-02)

1. **Collected but never alerted** — jitter (`rtt_sample.jitter`), modem 5G
   signal (`modem_signal_log`), mesh health (`mesh_signal_log`), IP history
   (`device_ip_history`), network grade (`grade_result`), config snapshots are
   all in MetricStore with zero alert rules attached. The user must open a page
   to notice a problem.
2. **Built but not wired** — `modules/alert_baseline.py` (7-day per-host
   baselines, mean+2σ anomaly thresholds, `Baseline.is_mature` gating) and
   `modules/iot_baseline.py` (NEW_DEST / NEW_PORT / METADATA_PROBE / SYN_SCAN /
   RATE_SPIKE behavioural detection) exist and are tested, but neither feeds
   the background AlertEngine.
3. **On-demand only** — every Security Audit scanner runs only on click. No
   scheduled variant, no diffing between runs, so a port that silently opens
   on the NAS is never noticed.

**Reusable plumbing that already exists** (do NOT rebuild):
`workers/proactive_probe_worker.py` (generic interval worker with
maintenance/quiet-hours suppression), `modules/proactive_digest.py`
(`is_due()` gating), `modules/digest_bullets.py`, AlertEngine cooldown /
consolidation / resolution tracking, `modules/speed_drop_detector.py`
(rolling-median drop detection, reusable for any float series).

## Guardrails — apply to EVERY sprint

- Everything **opt-in** with conservative defaults — no new background network
  activity without an explicit toggle.
- Every new rule type: 300 s cooldown, maintenance-window suppression,
  consolidation, and a "recovered" resolution alert — same discipline as
  HOST_DOWN.
- Every new detection gets a Morning Briefing / digest bullet and a
  plain-English remediation line.
- Modules stay PyQt-free (ARCH RULE 1); periodic work via
  `ProactiveProbeWorker`-style QThread workers (RULE 4); TDD per repo skills.
- New rule types go in `modules/alert_types.py` `RULE_TYPES` + `_RULE_CTA`
  routing in `alert_engine.py` + per-rule toggle on the Notifications page.

---

## Sprint 1 — Alert on data we already collect

**Effort:** M | **Benefit:** Highest ROI — zero new collection, zero new privileges; five real-issue detectors from existing tables.

- [x] **1.1 JITTER_HIGH** — sustained jitter above threshold (default >20 ms
      for 10 min) from `rtt_sample.jitter`. New rule type; CTA routes to
      Network Logger. Today jitter only powers RootCauseCorrelator.
- [x] **1.2 MESH_DEGRADED** — from `mesh_signal_log`: fires when
      `online_count < unit_count` (node dropped) or worst RSSI < −75 dBm.
      CTA → Mesh Router page.
- [x] **1.3 MODEM_SIGNAL_DROP** — from `modem_signal_log`: SINR/RSRP degrades
      vs 7-day baseline (reuse `alert_baseline.py` mean+2σ) OR band downgrade
      event (5G → LTE). CTA → 5G Modem page.
- [x] **1.4 GRADE_REGRESSION** — network health grade declines (e.g. A→C).
      Requires small schema change: `grade_result` currently keeps latest only;
      retain history. CTA → Network Grade page.
- [x] **1.5 IP_CHURN** — device gets ≥3 distinct IPs in 24 h from
      `device_ip_history` (DHCP instability / missing reservation).
      CTA → Devices page.
- [x] **1.6** Digest bullet in `digest_bullets.py` + Morning Briefing rollup
      for each of the five new rule types.

## Sprint 2 — Wire the dormant baseline engines

**Effort:** M | **Benefit:** Anomaly detection that adapts to each network instead of static thresholds.

- [x] **2.1 Per-host RTT anomaly** — new RTT_ANOMALY rule type
      (`modules/alert_engine_checks2.py`); a `BaselineLearner` is refreshed
      hourly in `app.py` and evaluated every availability cycle against each
      host's own mean+sigma RTT baseline. Gated on `Baseline.is_mature`
      (`BaselineMetric.is_valid` + `days_covered >= 7`) so the learning
      period cannot produce false positives.
- [x] **2.2 IoT behaviour watch** — new IOT_BEHAVIOR rule type. Reused the
      existing manually-started `IoTMonitor` drain loop in
      `ui/tabs_analysis.py` (opt-in via the page's "Start Anomaly Monitor"
      button) rather than adding a second background worker; each drained
      `IoTAlert` (NEW_DEST / NEW_PORT / METADATA_PROBE / SYN_SCAN /
      RATE_SPIKE) now also flows through
      `AlertEngine.evaluate_iot_behavior_checks()` into the same toast/digest
      pipeline as every other rule type.
- [x] **2.3 Trend-forecast alerts** — new TREND_FORECAST rule type. A new
      always-on hourly `ProactiveProbeWorker` runs
      `trend_analyser.run_full_trend_report()` (pure DB analysis, no new
      network probing) and fires an early-warning alert only for results
      with a projected `eta_hours` that have not already crossed their
      threshold (an already-crossed value stays RTT_THRESHOLD/
      LOSS_THRESHOLD's job — firing both would be a duplicate alert).

All three rules: opt-in/disabled by default, Notifications page toggle,
Morning Briefing digest bullet (`modules/digest_bullets.py`), and CTA
routing to the relevant page — same discipline as Sprint 1.

## Sprint 3 — Scheduled security posture + diffing

**Effort:** L | **Benefit:** The big one. The value is not the scan — it's the **diff between runs**.

- [x] **3.1 Nightly port-scan sweep** of known inventory devices (opt-in,
      quiet-hours aware, via a `ProactiveProbeWorker`-pattern worker).
      Store per-device open-port snapshots in MetricStore; diff vs previous
      sweep → **NEW_OPEN_PORT** alert: "Port 23/telnet opened on 192.168.1.40
      (NAS) since last sweep". Implemented in `modules/port_sweep.py`, reusing
      `modules/config_baseline.py`'s snapshot/diff engine (no new schema).
- [x] **3.2 Scheduled CVE re-check** for already-fingerprinted services →
      **NEW_CVE** alert when a tracked service gains a CVE since last check
      (CVE lifecycle tracker tables exist, schema v8). Implemented in
      `modules/cve_recheck.py`.
- [x] **3.3 Auto-TLS enrolment** — `CertWorker` today checks only manually
      configured hosts; auto-enrol discovered hosts with 443/8443 open so
      CERT_EXPIRY coverage needs no user setup. Implemented in
      `modules/cert_auto_enroll.py`, fed by each port-sweep result; removed
      auto-targets are tracked in `cert_monitor/auto_excluded` so they are
      never silently re-added.
- [x] **3.4 Weekly exposure check** — schedule the existing "Exposed to
      Internet" scan; alert on any newly exposed port. Implemented in
      `modules/exposure_watch.py`, same snapshot/diff reuse as 3.1.
- [x] **3.5 Scan registry integration** — scheduled runs call
      `_nav_set_scan_state()` so flyout dots / Security Overview Scan Status
      stay fresh without clicks. Wired in `app.py` (`_wire_port_sweep`,
      `_wire_cve_recheck`, `_wire_exposure_watch`), reusing the existing
      "Port Scan (TCP)" / "CVE Lookup" / "Exposed to Internet" labels.

  Opt-in toggles live on the Security Overview page's new "Scheduled Posture
  Scans" card (off by default). Per-rule alert toggles (New Open Port / New
  CVE Found / New Internet Exposure) live on the Notifications page.

## Sprint 4 — Passive always-on guards

**Effort:** M | **Benefit:** The classic "real attack" detectors run continuously instead of only while their page is open.

- [x] **4.1 ARP spoof background watch** — new `modules/arp_watch.py` wraps
      `arp_monitor.scan()` in a `ProactiveProbeWorker` cycle (15 min, opt-in,
      quiet-hours aware) instead of only running while ARP Spoof Watch is
      open. New **ARP_SPOOF** rule type (`alert_engine_checks4.py`) fires on
      GATEWAY_HIJACK (CRITICAL) / IP_TAKEOVER / MAC_CLONE (WARNING) — no new
      detection logic, arp_monitor.py's own classification is reused.
- [x] **4.2 DHCP rogue background listener** — new `modules/dhcp_watch.py`
      wraps `dhcp_detector.scan()` in a `ProactiveProbeWorker` cycle (30 min,
      opt-in). New **ROGUE_DHCP** rule type fires CRITICAL on any offer from
      an unexpected server. Both toggles live on the Security Overview
      "Scheduled Posture Scans" card alongside the Sprint 3 toggles, reusing
      `posture_scheduling_changed` end-to-end.
- [x] **4.3 Config drift auto-snapshot** — `ui/scan_wiring.py`'s existing
      DEVICE-5 auto-snapshot block (fires after every scheduled discovery
      scan) now also diffs the new snapshot against a **user-blessed
      baseline** (`★ Set as Baseline` context-menu action on Config
      Snapshots, `ui/pages/baseline_page.py`) via the existing
      `config_baseline.diff_snapshots()` engine. New **CONFIG_DRIFT** rule
      type fires on added/removed devices and `device_type` (role) changes
      versus that baseline — separate from the pre-existing rolling
      auto-snapshot toast, which only compares consecutive auto-snapshots.

  All three rules: opt-in/disabled by default, Notifications page toggle,
  Morning Briefing digest bullet (`modules/digest_bullets.py`), CTA routing
  to ARP Spoof Watch / DHCP Rogue Monitor / Config Snapshots. Fixed a
  pre-existing gap found along the way: `NEW_OPEN_PORT`/`NEW_CVE`/
  `NEW_EXPOSURE` (Sprint 3) had Notifications-page checkboxes but no
  matching `AlertRule` in `_default_rules()`, so those toggles silently had
  no effect — added the three missing default rules in
  `modules/alert_suppressor.py`.

## Sprint 5 — Correlation & narrative

**Effort:** M | **Benefit:** Smarter findings, not more findings. Depends on Sprints 1–4 signals existing.

- [x] **5.1 Root Cause Correlator inputs** — feed mesh/modem signal,
      BASELINE_DROP, and IoT alerts into `root_cause_correlator.py` so
      "slow internet" can resolve to "your 5G modem dropped to LTE at 14:02".
      Implemented as `_correlate_recent_alerts()` consuming
      `store.get_recent_alerts()`, threaded through `DiagnosisWorker(store=...)`.
- [x] **5.2 Speed↔signal correlation** — when BASELINE_DROP fires and the
      saved per-test modem snapshot shows poor SINR, the alert says
      "radio, not ISP". `evaluate_baseline_metrics()` now accepts
      `current_sinr`/`prior_sinr` and reuses `alert_baseline.modem_sinr_dropped()`;
      `scheduled_speed_test.py` reads the modem_signal_log to supply them.
- [x] **5.3 Weekly security digest** — "what changed this week": new devices,
      new open ports, new CVEs, approaching cert expiries. Rather than
      duplicating the existing Sunday weekly-digest pipeline
      (`digest_builder.py` + `dashboard._check_weekly_digest()`, already
      dispatched via NotificationRouter), extended `digest_builder.py` with
      "New Open Ports" and "Certificates Expiring Soon" sections.
- [x] **5.4 Alert-fatigue guardrails** — global sensitivity control
      (Conservative/Balanced/Aggressive) on the Notifications page, on top of
      the per-rule enable toggles already shipped alongside each V6 rule.
      `modules/alert_sensitivity.py` scales thresholds/cooldowns/min-samples;
      applied once at startup in `app.py` (`alerts/sensitivity` QSettings key,
      default "balanced" = shipped defaults unchanged).

---

## Ordering rationale

- Sprint 1 first: pure wiring of existing data — fastest path to "the app told
  me something real".
- Sprint 3 is the highest absolute security value but needs opt-in UX,
  quiet-hours, and snapshot storage design, so it follows the wiring sprints.
- Sprint 5 last: correlation quality depends on the new signals existing.
