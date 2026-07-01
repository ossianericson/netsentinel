# Validated Incident Patterns

Two detection patterns in NetSentinel were built directly from real faults observed
on the author's own network. Both faults were fixed by the ISP/network before the
in-progress detector could be confirmed catching them live — this page records what
each pattern catches, why it needed a dedicated detector (existing checks missed
it), and exactly how far each one currently reaches: on-demand scan only, or also
the always-on tray/background path.

---

## Pattern 1 — Relative speed drop vs. your own typical

**Module:** `modules/speed_drop_detector.py` · **Wired into:** `ui/pages/speed_test_page.py`

**Real incident:** line normally ran ~740 Mbps down; ISP-side fault dropped it to
~94 Mbps. Still "fast internet" by any absolute measure, and 94 Mbps never crossed
the existing 5 Mbps absolute floor in `modules/root_cause_correlator.py` — so
nothing fired. The only way to see the fault was to compare against the user's own
history, not a fixed constant.

**Detection logic** (`evaluate_speed_drop`):
1. Requires ≥4 prior speed-test samples (`min_samples`) — no verdict on a fresh install.
2. Takes the median of prior downloads as "typical" (median, not mean, so one
   outlier great/bad test doesn't skew the baseline).
3. Ignores the typical baseline itself if it's below `floor_mbps` (25 Mbps default)
   — a line that's normally slow isn't a "drop" candidate.
4. `drop_pct = (typical - current) / typical * 100`. ≥50% → `Warning`, ≥75% → `High`.
5. Returns a `SpeedDropVerdict` with a headline and a generic restart checklist
   (router → modem → re-test → contact ISP with the measurement).

**Where it fires today:**

| Path | Status |
|---|---|
| On-demand (user clicks "Run Speed Test") | ✅ Wired — banner on Speed Test page + `speed_drop_detected` signal → high-priority Home suggestion card |
| Tray / background | ❌ Not wired — no code path runs a speed test without the page open |

**Why tray coverage doesn't exist yet:** a full speed test consumes real
bandwidth and — per the product's least-friction/no-hidden-resource-use values —
should never fire without the user asking for it or explicitly scheduling it.
There is currently **no scheduled/automatic speed test** anywhere in the app;
`modules/scheduler.py` (`ScanScheduler`) only runs device-discovery scans on an
interval. Closing this gap means building a new opt-in "Scheduled Speed Test"
automation (a new feature, not a wiring fix) — see Plan below.

---

## Pattern 2 — `filtered` failure layer + custom-host probing

**Module:** `modules/service_diagnostics.py` (`DiagnosticEngine`) · **Wired into:**
`ui/pages/service_diagnostics_page.py`, `workers/service_diagnostics_worker.py`,
`ui/pages/diagnosis_page.py`

**Real incident:** `github.com` answered ICMP pings fine, but every TCP SYN to its
Azure Front Door range timed out — classic ISP-side or middlebox port/range
filtering, not a real outage. Two things were missing: (1) the diagnostic pipeline
only covered a fixed streaming/gaming service catalog, so `github.com` couldn't be
probed at all; (2) even if it could, the pipeline had no vocabulary for "reachable
at layer 3, blocked at layer 4" — it would have mis-reported this as a remote
outage.

**Detection logic:**
1. `DiagnosticEngine.run_custom(hostname)` runs the same DNS → TCP → HTTPS → ICMP →
   traceroute pipeline as catalog services, for any typed hostname.
2. New `failure_layer = "filtered"` fires when: ICMP loss stays below
   `_ICMP_HEALTHY_LOSS_PCT` (50%) **while** TCP/HTTPS fail, **and** independent
   reference hosts stay reachable. That combination rules out "your whole
   connection is down" (that's `local_network`/`isp`/`routing`) and "the remote
   service is actually down" (`remote_outage`) — leaving only a targeted block
   between you and that one destination: firewall, VPN, or ISP-side filtering.
3. The failure-layer taxonomy end to end: `device → local_network → dns → isp →
   routing → remote_outage → filtered`.

**Where it fires today:**

| Path | Status |
|---|---|
| On-demand (Service Diagnostics page, "Custom host…" picker, or Diagnosis page "a service is unreachable" tile) | ✅ Wired — full DNS/TCP/HTTPS/ICMP/traceroute pipeline runs and classifies |
| Tray / background (Service Heartbeat) | ❌ Only a TCP up/down check — `workers/service_worker.py` → `modules/service_monitor.py` does a raw TCP connect every 60s and nothing else. On failure it silently updates the Service Heartbeat table; there is no escalation to DNS/ICMP/reference-host analysis, no `failure_layer` classification, and no tray notification or `AlertEngine`/`NotificationRouter` wiring at all for a heartbeat failure today. |

**Why this gap is closeable without a new opt-in feature:** unlike the speed-test
case, the background heartbeat is already running continuously for every
monitored service — no new resource-consent question to raise. The only missing
piece is escalation logic on TCP failure, using code that already exists in
`modules/service_diagnostics.py`. See Plan below.

---

## Plan — closing the tray/background gap

### Service heartbeat → filtered-layer escalation (feasible now, no new opt-in required)

1. On a TCP heartbeat failure in `ServiceMonitor.run_check()`, don't just mark
   `up=False` — call a lightweight subset of `DiagnosticEngine` (ICMP ping to the
   failed host + one or two reference hosts) to decide `filtered` vs
   `remote_outage` vs "just down."
2. Throttle: only escalate on the *first* failure after an up→down transition, not
   every 60s tick, to avoid hammering ICMP/reference hosts.
3. Route the classified result through the existing `AlertEngine` /
   `NotificationRouter` → tray notification path (`app.py` already wires
   `window._tray_manager.show_notification(...)` for other ambient events) so a
   filtered service reads as *"GitHub blocked by your network (firewall/ISP),
   not down"* in the tray toast, distinct from a generic "service down."
4. Persist the classification on the `ServiceCheckPoint` row so the Service
   Heartbeat table can show the same distinction the on-demand page shows.

Estimated surface: `modules/service_monitor.py` (add classification call),
`workers/service_worker.py` (no change — signal payload already passes through),
`ui/pages/service_page.py` (display `failure_layer` in the table), `app.py`
(wire down→filtered transitions to `NotificationRouter`/tray). Needs
`tests/test_service_monitor.py` coverage per RULE-T1/T3 and a behavioral test
per RULE-T7.

### Scheduled speed test → drop detection (new feature, needs explicit scope-in)

1. New opt-in automation: "Scheduled Speed Test" (interval picker, off by default —
   speed tests use real bandwidth, must never run without consent).
2. On completion of a scheduled run, call `evaluate_speed_drop()` against stored
   history exactly as the page does today, and route a `Warning`/`High` verdict to
   the tray via `NotificationRouter`, plus the existing Home suggestion path.
3. This is new user-facing surface area (a new automation with its own settings,
   consent, and interval UI) — out of scope to build silently; flag for
   `RULE-REQ1` acceptance criteria before implementation.

Both plan items reuse existing detection modules unchanged — the gap is entirely
in *when* they're invoked, not in the detection logic itself.
