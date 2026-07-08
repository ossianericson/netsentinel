# NetSentinel Remote Sensor Logger — Implementation Plan

Companion to [SPEC.md](SPEC.md). The spec defines **what** to build (normative — when in doubt, SPEC.md wins);
this file defines **the build order, session boundaries, and done-gates**. Update the checkboxes as work ships —
this file is the cross-session progress tracker.

Ground rules for every implementation session (per `.claude/rules/session-workflow.md`):
start with a plan, smallest diff, no scope creep beyond the phase, note discoveries at the end.
The desktop app is touched **last** (Phase 3) so previously-verified app paths stay intact while
the standalone logger proves itself.

---

## Phase 1 — Logger core package (pure Python; develops and tests on any OS, no Pi needed)

Build order follows the dependency chain — each item lands with its tests in the same commit.

- [ ] Scaffold: `pyproject.toml` (package `netsentinel-logger`, console script, pytest config rooted here),
      `requirements.txt`, `README.md`, `config.example.yaml` (copy §5 verbatim), package skeleton
- [ ] `config.py` + `tests/test_config.py` (defaults, `${ENV}` interpolation, field-path errors)
- [ ] `spool.py` + `tests/test_spool.py` (append/ack, replay order, cap eviction, crash recovery, state kv)
- [ ] `scheduler.py` + `tests/test_scheduler.py` (no-drift with FakeClock, guarded jobs, heartbeat ages)
- [ ] `mqtt_client.py` + `tests/conftest.py` FakeMqttClient (LWT, safe_segment, ack/reconnect callbacks)
- [ ] `pipeline.py` + `tests/test_pipeline.py` (stamp → spool → publish order; retained-not-spooled; drain)
- [ ] `probes/ping.py` + `tests/test_ping_stats.py` (compute_window math incl. all-timeout / single-sample edges)
- [ ] `probes/dns_probe.py` (struct-built A query; unit test with a canned response socket)
- [ ] `probes/system_metrics.py` (vcgencmd/sysfs fallbacks; returns nulls gracefully off-Pi)
- [ ] `probes/discovery.py` + `tests/test_discovery.py` + `tests/fixtures/proc_net_arp.txt`
      (ARP parse, source merge, join/leave diff with miss_count)
- [ ] `anomaly.py` + `tests/test_anomaly.py` (hysteresis sequences, fresh-install seeding, EWMA persistence)
- [ ] `exporters.py` + `tests/test_exporters.py` (rotation, retention)
- [ ] `api.py` (three GET endpoints against Pipeline's latest-cache)
- [ ] `main.py` (App wiring, signals, sd_notify, `--check`)
- [ ] `tests/test_topics.py` — every SPEC §4 example payload validated against a schema dict
      (**the shared contract test** — Phase 3's router tests reuse these payloads)

**Gate:** `pytest logger/tests` fully green on the dev machine; `netsentinel-logger --check` and `--version` work;
desktop test suite still green (proves the pytest roots don't collide).

## Phase 2 — Deploy assets + first hardware bring-up (needs a Pi)

- [ ] `deploy/netsentinel-logger.service`, `50-netsentinel-logger.conf`, `secrets.env.example`, `install.sh` (§6.5–6.6)
- [ ] `deploy/mosquitto-netsentinel.conf`, `deploy/avahi-netsentinel.service` (§6.4)
- [ ] `deploy/firstrun.sh`, `deploy/netsentinel-provision.service`, `deploy/provision.sh` (§6.2–6.3;
      shellcheck clean; status-file + log-copyback behaviour exactly as specced)
- [ ] `tools/smoke.py` (§8.4)

**Gate (manual, on a real Pi over SSH — the last time SSH is ever needed):** §6.6 manual install path succeeds
on Raspberry Pi OS Lite 64-bit Bookworm; `smoke.py` passes; service survives reboot and a forced kill
(watchdog restart observed); broker outage → spool grows → reconnect replays; RSS < 60 MB after 1 h.

## Phase 3 — Desktop app integration (repo `modules/`, `workers/`, `ui/` — follows all app rules)

- [ ] `modules/sensor_registry.py` + `tests/test_sensor_registry.py` (QSettings JSON + keyring, mocked)
- [ ] `workers/mqtt_ingest_worker.py` + `tests/test_mqtt_ingest_worker.py` (RULE-T2 lifecycle;
      lazy paho import guard; client-id per sensor; wired in app.py per RULE-DW2; RULE-B1 hiddenimport)
- [ ] Dashboard `_on_sensor_message` routing (§7.4) + router tests driving the §4 example payloads
      against a mocked MetricStore/DeviceTracker/NotificationRouter
- [ ] `ui/pages/remote_sensor_page.py` — fleet table, registered in `_build_pro_nav()` Extend section
- [ ] `ui/widgets/sensor_setup_wizard.py` — 8 pages (§7.6); file generation as pure functions
      (`render_config_yaml`, `render_firstrun`, `patch_cmdline`, `sha512_crypt`) + golden tests
      (`sha512_crypt` verified against `openssl passwd -6` vectors)
- [ ] `NetSentinel.spec`: bundle logger sdist + requirements + deploy templates as data files
- [ ] `bump_version.py`: also bump `logger/netsentinel_logger/__init__.py` + rebuild sdist (RULE-R1)

**Gate:** repo commit gate passes (tests + `tools/debug_launch.py`); Remote Sensors page renders;
end-to-end against the Phase-2 Pi: live metrics land in `rtt_sample`, devices appear via `process_scan`,
a forced anomaly raises a toast + alert row, Log Hub shows the `sensor:{id}` source chip.

## Phase 4 — Zero-touch validation + soak (release gate)

- [ ] Full wizard run against a freshly-flashed blank SD card → Pi boots → sensor online, no SSH used
- [ ] Failure path: provision with wrong WiFi credentials → reinsert card → "Troubleshoot from SD card"
      shows the failing step from `provision-status.json` / `firstboot.log`
- [ ] Re-provision path: wizard on an already-provisioned card (idempotent cmdline patch) works
- [ ] 72 h soak per SPEC §8.4 (RSS < 60 MB, no spool growth, clean replay after 1 h broker outage,
      zero unexpected restarts)

**Gate:** all four checked → version bump, CHANGELOG, release per repo release rules (user gates tags).

---

## Session sizing

Phase 1 is 2–3 sessions (split at pipeline / after probes). Phase 2 is one session plus hands-on Pi time.
Phase 3 is 2 sessions (worker+routing, then page+wizard). Phase 4 is hands-on validation, no coding session
unless bugs surface. Each session updates this file's checkboxes in its final commit.
