# Signal Quality — measured baseline (Phase 0)

Measured 2026-08-04 with `python tools/alert_replay.py`, against a real
`%LOCALAPPDATA%\NetSentinel\NetSentinel.db` holding **25.4 days** of history for a
30-device home network. Raw summary: `signal-quality-baseline.json`.

This is the "before" number for the Signal Quality Program. Every later threshold
change is judged against it; the acceptance criteria in the program plan are
expressed in these units.

## Headline

| Metric | Value |
|---|---|
| Observed claims/day (what the app actually surfaced) | **76.5** |
| Replayed alerts/day, through the current scope gate | **85.5** |
| Replayed alerts/day, ungated | **160.3** |
| Share of candidate alerts the scope gate admits | **53.4 %** |

The app as shipped is quiet only because all 25 alert rules ship `enabled=False`.
A user who enables the rules they believe they want receives **~85 alerts a day**
from a 30-device home network. That is the core finding: the alerting layer cannot
be turned on in its current form.

## Observed claims (1,939 total / 25.4 days)

| Source | Count | /day |
|---|---|---|
| `device_event` RECOVERED | 657 | 25.9 |
| `device_event` LEFT | 569 | 22.4 |
| `device_event` DEGRADED | 490 | 19.3 |
| `device_event` DOWN | 192 | 7.6 |
| `device_event` JOINED | 2 | 0.1 |
| `alert_fired` (all types) | 29 | 1.1 |

## Replayed alerts (all rules force-enabled)

| rule_type | ungated | via scope gate | /day |
|---|---|---|---|
| HOST_DOWN | 1,637 | 983 | 38.8 |
| LOSS_THRESHOLD | 806 | 479 | 18.9 |
| HOST_DEGRADED | 663 | 281 | 11.1 |
| RTT_THRESHOLD | 620 | 265 | 10.5 |
| FLAP | 174 | 60 | 2.4 |
| HOST_DOWN/resolved | 164 | 101 | 4.0 |

## Defects this quantifies

**1. `HOST_DOWN` is level-triggered, not edge-triggered.** 1,637 firings against
only 164 resolutions — a **10:1 ratio**. `_eval_rule_for_host` fires on every cycle
where `state == "DOWN"`, bounded only by a 120 s cooldown, so a device offline
overnight produces roughly 240 alerts for one outage. `device_event` records the
same outage as a single `DOWN`. The alert layer is an order of magnitude louder
than the event layer for the identical fact.

**2. The same outage is reported twice under different names.** `HOST_DOWN`
(`state == "DOWN"`) and `LOSS_THRESHOLD` (`rtt < 0`) both fire from the same cycle
for the same unreachable host — 1,637 + 806 firings describing one condition.

**3. `LEFT` re-fires hourly.** 569 events across 30 MACs; the top eight emitted
34–37 each. `device_tracker.py:253-261` suppresses a repeat only if a prior `LEFT`
exists within `gone_threshold_s` (1 h), so an absent device re-announces its
absence every hour. The gateway emitted 7.

**4. Fixed thresholds applied to devices whose normal is different.**
`192.168.68.54` (Chromecast) averages **194.3 ms** against
`availability_monitor.py`'s `degraded_threshold = 150.0`, so it sits permanently on
the boundary: 306 state events from one device. The top five churn sources are a
Chromecast, a laptop, a printer, a PS5 and a streaming stick — all devices that
legitimately sleep.

**5. `inferred_role` is wrong, and downstream of an already-wrong `device_type`.**
The scope gate admits 53.4 % of candidate alerts on the strength of this column.
Observed assignments:

| Device | Classified as | Role |
|---|---|---|
| `92:35:ca:16:8f:38` hostname `iPad-2` | **Domain Controller** | — |
| `f0:72:ea:51:d3:b8` vendor `Google Nest / Nest Wifi / Google Wifi Router` | **Video Doorbell** | **none** |
| `d8:3a:dd:de:11:a7` hostname `PINAS`, vendor Microsoft | Games Console | infrastructure |
| `5c:93:a2:5c:47:19` hostname `PS4-C8208A` | Games Console | infrastructure |
| `88:3d:24:21:77:66` vendor Google | Streaming Stick | infrastructure |
| `00:21:b7:a3:09:1a` Lexmark printer | Unknown Device | infrastructure |
| `01:00:5e:7f:ff:fa` / `239.255.255.250` | — | infrastructure |
| 3 anonymous privacy-MAC devices | Unknown Device | infrastructure |

The real mesh AP (Google Nest Wifi) carries **no** infrastructure role, while a
PS4, a Chromecast, a printer, an SSDP **multicast address** and three
unidentifiable MACs all do. Phase 2 therefore cannot simply tighten the promotion
rule — it must stop treating `device_type` as primary evidence and use
corroborating signals (gateway IP match, DHCP server identity, the mesh plugin's
own node list) instead.

**6. Privacy MACs are an identity problem, not a rotation problem.** 8 of 30
devices have the U/L bit set, but they are stable (483–606 scans, 0.71–0.88 IP
stability); `JOINED` fired twice in 25 days. They are not churning — they are
unidentifiable, and three of them were promoted to `infrastructure`.
`known_device.mac_randomized` is read by the query layer and written by nobody.

## Measured after Phase 2 (importance tiers)

Same database, re-measured 2026-08-05. `tier gate` replaces the `inferred_role`
boolean with a `device_importance.Tier` floor of `INFRASTRUCTURE`, and
re-derives the role from corroborating evidence rather than trusting the stored
column.

| Gate | alerts | /day | admits |
|---|---|---|---|
| ungated | 3,883 | 163.6 | 100 % |
| role gate | 2,180 | 91.9 | 56.1 % |
| **tier gate** | **157** | **6.6** | **4.0 %** |

**Two caveats on comparing this to the headline table above.** The window is now
**23.7 days**, not 25.4 — pruning has since dropped the oldest rows, so absolute
counts are not directly comparable and the per-day rates are the figures to use.
And the role gate now measures *higher* than the 85.5/day recorded above (91.9),
because Phase 2 also fixed a defect in the gate itself: `is_device_alert_in_scope()`
matched `ip = ? OR mac = ?` but read only `rows[0]`, so with several MACs at one
address the verdict depended on row order. The original 85.5 was therefore an
*under*-count of the legacy gate's real volume.

Alert-eligible rows fall from **10 of 30 to 2 of 30** — the gateway
(`192.168.68.1`, TP-Link Deco) and the mesh AP (`192.168.68.64`, Google Nest
Wifi), which previously had *no* role at all. Everything the old gate admitted
in error — a PS4, an Xbox, a streaming stick, a Lexmark printer, three
unidentifiable privacy MACs and the SSDP multicast group — is now below the
floor. The gateway's own coverage is unchanged (its alerts go 4 → 6: with the
noise suppressed, fewer simultaneous `HOST_DOWN`s reach the `(network)`
consolidation threshold at [alert_engine.py:272](../../modules/alert_engine.py#L272),
so two are reported against the gateway by name instead of folded into one
aggregate).

The 6.6/day that remains is still dominated by the level-triggered `HOST_DOWN`
defect (#1 above), which Phase 3 addresses; the tier gate reduces *who* the app
speaks about, not yet *how often* it repeats itself about them.

## Measured after Phase 3 (edge trigger + baseline)

Same database, re-measured 2026-08-05, 23.7-day window. Phase 2 changed *who*
the app speaks about; Phase 3 changes *how often it repeats itself*. Both
columns below are the same tier gate over the same rows — the only difference
is the two Phase 3 switches, so this is a clean A/B rather than two runs.

| rule_type | Phase 2 | Phase 3 |
|---|---|---|
| HOST_DOWN | 93 | **7** |
| HOST_DOWN/resolved | 7 | 7 |
| LOSS_THRESHOLD | 44 | **0** |
| HOST_DEGRADED | 6 | 6 |
| RTT_THRESHOLD | 5 | 5 |
| FLAP | 2 | 2 |
| **TOTAL** | **157** | **27** |
| **per day** | **6.61** | **1.14** |

**HOST_DOWN now equals its own resolutions exactly — 7 and 7.** That identity is
the defect closing: every outage the app reports is an outage it also closes.
The 13:1 ratio measured here (93:7, the same shape as the 1,637:164 in the
headline table) was one alert per *cycle* against one resolution per *episode*.
`AlertEngine.set_availability_edge_trigger()` moves the trigger to the edge, so
an outage spanning 40 cycles is one claim.

**LOSS_THRESHOLD falls to zero, and that is not lost coverage.** All 44 firings
were the same unreachable host `HOST_DOWN` was already reporting in the same
cycle — `state == "DOWN"` and `rtt < 0` are one observation. The suppression
only applies where an enabled `HOST_DOWN` rule actually covers that host, so a
user running `LOSS_THRESHOLD` alone still gets every one of them.

`LOSS_THRESHOLD` deliberately stays *level*-triggered outside that case. A host
dropping every other packet never reaches two consecutive failures, so it never
becomes DOWN and never trips FLAP either — edge-triggering it as well would
report a persistent half-broken link once and then go quiet about it forever.

HOST_DEGRADED, RTT_THRESHOLD and FLAP are untouched by design: Phase 3's engine
half only addresses the two defects above. Their remaining 13 firings come from
the two devices the tier gate admits, and are the honest residue.

### What this measurement cannot see

The replay reads `device_state` rows **already written** under the old
classification, so it measures the alert layer only. Phase 3b's monitor-side
changes act when those rows are *written*:

- **Per-device DEGRADED thresholds** (`device_baseline.degraded_threshold`)
  replace the global 150 ms constant with the device's own `mean + 2σ`. The
  reference network's Chromecast at `192.168.68.54` averages 194.3 ms and still
  tops the churn table at **305 state events**; a threshold below its own mean
  is what produces them.
- **DOWN confirmation** (2 consecutive failures) stops a single dropped ping
  becoming a DOWN + RECOVERED pair.

Those show up in the OBSERVED table of a *future* run, once the app has run with
`experimental/signal_quality_v2` on. Observed claims stand at **80.3/day** today.
Acceptance criterion 2 (`192.168.68.54`: 306 → ≤ 10) is measured there, not here.

The global default is a floor and never a ceiling — learning may only raise a
device's threshold. A fast host that starts answering in 40 ms instead of 4 ms
still trips the global rule, so "learned baseline" cannot become a mute button.

## Phase 4 — the mesh signal that produced nothing

Phase 4 wires in the signals the user called real. Four of its five landed as
planned. The mesh one turned out to be the program's own founding defect,
one level deeper than anyone had looked.

**`mesh_signal_log` was empty because nothing ever wrote to it.**
`ui/scan_enrichment.py::_on_mesh_result()` holds both mesh payloads — the
`evaluate_mesh_checks()` call (MESH_DEGRADED) and the `record_mesh_snapshot()`
call (acceptance criterion 6). Those are the only production call sites of
either function. And `_on_mesh_result()` has no caller: no `.connect()`
anywhere in `ui/`, `workers/` or `app.py`, no mesh worker in `workers/`, no
dynamic dispatch, and `git log -S` returns only the commit that introduced it.
Outside its own `def` line, every reference is in `tests/`.

A real Deco poll lands in `_on_hardware_plugin_result()`, whose router/mesh
branch enriched the Devices table and returned.

**This is why the earlier check passed.** "Does `evaluate_mesh_checks()` have a
live production caller?" is *true* — the call site exists. It is only false one
level further up. The preceding commit's hoist of the snapshot write out of the
`logging/mesh_enabled` toggle was therefore a correct fix applied to code that
never ran. A caller check has to run to the root, not to the first hit.

**Fixed** by extracting the shared computation into
`_evaluate_and_log_mesh_health()` and calling it from the path the plugin
actually takes — against the nodes the plugin reported, *before* the single-AP
topology fallback, so a synthesized placeholder node never enters the table as
though it were a real mesh reading.

**Criterion 6 met, verified live** against the repo database, 2026-08-06:

| rowid | ts | unit_count | online_count | worst_unit | worst_rssi |
|---|---|---|---|---|---|
| 1 | 10:36:54 | 5 | 5 | NULL | NULL |
| 2 | 10:43:15 | 5 | 5 | NULL | NULL |

The first rows in that table's history, from real polls of a live 5-node Deco
mesh. The 5-minute throttle holds in production too — the two rows are 381 s
apart.

### MESH_DEGRADED could not fire — fixed 2026-08-06, and the rows above were the proof

> **Superseded below.** The analysis in this subsection was correct except for
> the shape mismatch, which a live capture disproved. See "MESH_DEGRADED's data
> source, and the shape mismatch that wasn't".

`evaluate_mesh_checks()` decides with:

```python
degraded = online_count < unit_count or (worst_rssi is not None and worst_rssi < _MESH_WEAK_RSSI)
```

Both inputs are dead on the plugin path. `MeshUnit` (`modules/deco_client.py`)
is `name, mac, ip, role` — no `online`, no `rssi` — and the plugin's node dicts
(`plugins/deco_plugin.py`) project the same four fields. So `online_count` can
only ever equal `unit_count`, and `worst_rssi` is always `None`: exactly what
rows 1 and 2 show. The predicate is permanently `False`.

There is also a shape mismatch beneath the missing fields. Unplugging a
satellite makes `unit_count` *drop* (the node leaves the list); the rule tests
`online_count < unit_count`, which needs an API that reports a node as
present-but-offline. Fixing this means fetching per-node status from the Deco
API — a **missing data source**, not a wiring gap, and the same class as the
`JITTER_HIGH` defect (`jitter_ms` is `-1.0` on all 112,145 `rtt_sample` rows).
Deliberately left for its own item rather than folded into this fix.

### MESH_DEGRADED's data source, and the shape mismatch that wasn't

The predicate never needed changing — only the projection feeding it. The Deco's
`admin/device?form=device_list` response already carries per-node state;
`MeshUnit` and `plugins/deco_plugin.py` simply dropped it. Captured live from
the running mesh, one node unplugged:

```
Kitchen  device_ip=None  role=slave  group_status=disconnected
         inet_status=offline  signal_level={'band5': 0, 'band2_4': 0}
```

**The node stays in the list.** `unit_count` holds at 5 while `online_count`
drops to 4 — exactly the shape `evaluate_mesh_checks()` already tested for. The
"unplugging a satellite makes unit_count drop" concern recorded above was
wrong, and only a live capture could have settled it.

`deco_client._node_online()` reads `group_status`, not `inet_status`: a node can
legitimately be joined to the mesh while the WAN behind it is down, and that is
INFRA_UNREACHABLE's or HOST_DOWN's claim to make. A payload with no
`group_status` key is treated as online — absent evidence is not evidence of
absence, and inventing an outage for a firmware that omits the field would fire
the rule on every poll.

`worst_rssi` stays `None` deliberately. The Deco reports `signal_level` as a 1–3
bar scale per band while `_MESH_WEAK_RSSI` is −75.0 dBm, so feeding bars into a
column named for dBm would make the stored history mean two different things.
The weak-backhaul half of the predicate stays dormant rather than wrong. (Note
`signal_level` values are strings while connected and ints once disconnected —
nothing may assume the type.)

### Criterion 5 — VERIFIED live, 2026-08-06

"Killing the modem produces an alert within 3 minutes; so does unplugging a mesh
node; so does gateway loss. Each verified live, not by unit test."

All three clauses measured against a **recorded stimulus timestamp**, on the
running app, with `experimental/signal_quality_v2` on and the five rules armed:

| Clause | Stimulus | Alert | Latency |
|---|---|---|---|
| Modem loss | outbound block on `192.168.254.1`, 14:11:46 | `INFRA_UNREACHABLE` CRITICAL | **51 s** |
| Gateway loss | scoped block on `192.168.68.1`, 14:16:55 | `HOST_DOWN` CRITICAL | **94 s** |
| Mesh node unplug | node reported offline by the Deco API, 14:34:47 | `MESH_DEGRADED` WARNING | **15 s** |

Each also resolved when the stimulus was removed: the modem's HEALTHY row landed
59 s after the rule was deleted ("unreachable for 90s"), and the mesh reported
"back to full health". The gateway produced **one** `HOST_DOWN` across three
consecutive DOWN cycles (+94 s, +161 s, +230 s) — the Phase 3 edge trigger doing
its job under a real outage rather than a replayed one.

Two method notes worth keeping:

- **An agent *can* take this measurement**, contrary to the note this section
  used to carry. A Windows Firewall block scoped to a single destination IP
  does not cut the internet: LAN traffic routes via the Deco, and forwarded
  packets carry the remote server's address, not the gateway's. The gateway
  clause was further scoped to ICMPv4 + TCP 80/443 so UDP 53 kept resolving.
  Every block was armed with a detached auto-removal job first, so a lost
  session could not strand the network.
- **The stimulus timestamp must come from the same clock as the alert.**
  PowerShell 5.1's `Get-Date -UFormat %s` returns a *local-time* epoch — 7200 s
  ahead of real epoch on a UTC+2 machine — which silently makes every delta
  meaningless. All timestamps here come from Python's `time.time()`.

Phase 4 is **closed**. Phase 5 is unblocked.

#### The gateway clause found a defect the modem clause could not

`HOST_DOWN` fired at +94 s, but `INFRA_UNREACHABLE` never fired for the Deco —
where the modem's had fired at +51 s from an identical stimulus. The plugin
health record showed why:

```
AUTH: Deco login failed for 192.168.68.1: HTTPConnectionPool(host=..., port=80):
      Max retries exceeded ... [WinError 10013] ...
```

`DecoMeshClient._ensure_client()` caught **every** exception from `authorize()`
— including a transport-level `requests.ConnectionError` — and re-raised it as
`MeshAuthError` reading "Deco login failed … Check that the password is
correct". `_fmt_err()` then matched the word "login" and returned `AUTH:`, and
`hardware_integration_page._emit_reachability()` deliberately treats `AUTH:` as
*reachable* (the device answered and rejected us). So a router that was
completely off the network was reported as a credentials problem and raised
nothing.

The existing "network before auth" keyword guard could not catch it: urllib3
says "Max retries exceeded", not "refused" or "timed out", and the trailing OS
`strerror` is **localised** (Swedish on this machine), so no English network
keyword appeared anywhere in the string.

Fixed on both sides, because either alone leaves the hole open for the next
differently-worded wrapper: the client now lets a `ConnectionError` fall through
to the next protocol like a timeout and ends in `MeshApiError` ("no answer on
HTTP or HTTPS"), and `_fmt_err()` walks the `__cause__`/`__context__` chain for a
Connection/Timeout type instead of trusting message text alone. Genuine
wrong-password errors still classify `AUTH:` — that carve-out is correct and is
pinned by tests.

#### Four earlier attempts, four different reasons they measured nothing

Kept because the preconditions they exposed are what made the successful run
above work first time. A firewall block on the modem's management IP alone
(`192.168.254.1`) was always a sound method — every failure below was in the
preconditions, not the method.

| # | Why it was void |
|---|---|
| 1 | No stimulus was applied at all. |
| 2 | The modem plugin was not polling: its deployed copy was stale, so the hash guard refused to start the worker (fixed — see the bundled-plugin redeploy). |
| 3 | Every `alert_rules/*/enabled` key had been reset to `False` by the last full test-suite run, so the rule was off. `conftest.py` restores `ui/theme` but nothing restores these. |
| 4 | The app exited at launch on the single-instance mutex (RULE-WIN16) — it was relaunched ~1.5 s after the previous process was killed, before the mutex was released. The watch ran against a dead process. |

**The correct sequence**, which none of the four followed end to end: launch the
app → wait for a *healthy* poll to confirm the device is actually being polled →
re-arm and verify the rule keys (after any suite run, never before) → then apply
the block → watch. Never restart the app after blocking.

A fifth attempt was abandoned before it started: repeated `login()` calls across
those restarts tripped the modem's own lockout, so the plugin could no longer
authenticate (`AUTH:` — correctly *not* treated as unreachable). The precondition
of a healthy poll was unreachable until the modem idles and the lockout clears.

**Evidence that did come out of it, and it is not nothing:** with the block
applied, the plugin returned its `NET:` error and the app recorded it —
`modem_signal_log` rows at 13:11:34 and 13:14:41 carry `network_type=NULL,
signal_bars=NULL`, against `ENDC`/`5` on the healthy poll at 13:08:33. So
*detects unreachable → returns error → app records it* was demonstrated live;
the last hop into `INFRA_UNREACHABLE` was closed by the measured run above.

## The two rules that could not fire, and what reviving them costs

`JITTER_HIGH` and `RTT_ANOMALY` were the other two "rule with no data source"
defects. Both are fixed; neither is in the curated default-on set yet, so
neither changes what a user sees today.

**`JITTER_HIGH` had no producer.** `jitter_ms` was `-1.0` on all 112,497
`rtt_sample` rows — a single distinct value across the whole table — because
`AvailabilityMonitor.run_cycle()` probes with `_ping_once()`. `_on_cycle` then
filters `jitter_ms >= 0`, discarding every sample. The producer was missing, not
the filter.

Sampling is **bounded to the gateway plus `DEFAULT_TARGETS`**, not applied to
every device. `icmp_ping()` shells out to `ping.exe` once per sample and
`run_cycle()` walks its targets sequentially with a 2 s timeout each: at ~28 LAN
targets, three samples apiece is up to 168 s of worst-case cycle time against a
60 s interval, so the cycle would overrun itself whenever several hosts were
down. Jitter is an uplink-quality signal anyway.

**`RTT_ANOMALY`'s maturity gate was a tautology against itself.**
`_refresh_host_baselines()` queried exactly `_BASELINE_DAYS * 24` hours and then
computed `days_covered` from the oldest row *inside that same window*, so it
could never reach the 7 days `Baseline.is_mature` demands. Measured before the
fix: **6.9876 days** on the richest host, **0 of 3** mature — against 29.86 days
of real history for that host.

The window and the threshold answer different questions — "what should the mean
be computed from?" (recency) versus "how long have we been watching?"
(confidence) — and conflating them is what killed the rule. Statistics still
come from the 7-day window; `days_covered` now comes from the host's first-ever
sample via `MetricStore.query_rtt_first_seen_by_host()` (one grouped scan,
covered by `idx_rtt_host`).

**Reviving it exposes the opposite defect — measured, and handed to Phase 6.**
Fixing maturity took the live database from 0 to **21 of 26 hosts mature**, and
a very stable host learns a very tight threshold — `192.168.68.57` at 1.2 ms,
`192.168.68.1` at 2.0 ms. The gateway would be "responding slower than its usual
pattern" on any 3 ms reply. Measured over the same 6.9 days, upper bound with no
cooldown applied:

| | no floor | with a 150 ms floor |
|---|---|---|
| ungated (legacy path) | 121.3 /day | 55.9 /day |
| v2 tier gate (`_DEFAULT_MIN_TIER = INFRASTRUCTURE`) | 2.48 /day | **0.15 /day** |

A floor of 150 ms would not be an invented number — it is
`availability_monitor.DEFAULT_DEGRADED_THRESHOLD`, the app's existing definition
of a slow host — and it would be a floor, never a ceiling, so a host that
normally answers in 600 ms keeps its higher learned threshold. Same shape as
`_DNS_ABSOLUTE_FLOOR_MS`.

**It is deliberately NOT applied in Phase 4.** It was implemented, and reverted:
it is a *defaults* decision that belongs with the curated default-on set
(criterion 7), and it changes semantics that
`tests/test_alert_engine_v6_sprint2.py` already pins — mean 20 ms / sigma 5 ms,
observed 45 ms, currently fires and should keep firing until someone decides
otherwise on purpose. Two passing tests had to be rewritten to accommodate it,
which is the signal that the change belonged to a different phase. The rule
ships disabled, so nothing surfaces meanwhile. The measurement above is the
input for that decision; the recommendation is recorded in
`alert_engine_checks2.py` beside the code it would change.

Note what the tier gate does here: 14 of the 15 hosts that would trip the
floored predicate are `transient`, and the v2 path already suppresses those. The
2.48/day a floor would remove is almost entirely the gateway being called slow
at 3 ms.

**`tools/alert_replay.py` is structurally blind to both rules.** It drives
`evaluate_cycle()` only, while `app.py::_on_cycle` calls
`evaluate_jitter_checks()` and `evaluate_rtt_anomaly_checks()` separately — so
the replay's flat **27 alerts / 1.1 per day** across these changes is *not*
evidence that they are free. The numbers above were measured directly against
the same history instead.

## `--audit`'s RULES_OPT_IN had never run in its failing state

`python app.py --audit` reported `RULES_OPT_IN` failing for all five armed
rules. The check compares `settings_get(rule_settings_key(r.name), False) is not
True`, but `app.py` hands it a raw reader —
`lambda key, default=None: qs.value(key, default)`, with no `type=bool`. On
Windows QSettings uses NativeFormat (the registry), which returns a stored
boolean as the **string** `"true"`, so `"true" is not True` flagged every
genuinely enabled rule.

It had never been observed because all 25 built-in rules ship `enabled=False` —
nothing was ever enabled, so the check had only ever run in its passing state.
**Phase 6's curated default-on set (criterion 7) turns rules on by default and
would have tripped it for every user.** `alert_audit.py` already owned
`_truthy()` and already used it for `TOAST_OPT_IN`; the fix is that same helper
applied to the check that was missed.

## Phase 2 closeout — purge, not suppress

Acceptance criterion 3 reads "`239.255.255.250` and every other `NOT_A_DEVICE`
entry is **absent** from `known_device`". Phase 1 stopped new multicast rows
being written and Phase 2 cleared their `inferred_role`, but neither removed the
rows already there — **nothing in the tree deleted a `known_device` row at all**,
so the SSDP group stayed in the inventory with 654 scans against it, counted as
a device and displayed as one.

Two shapes were considered. **Purge won**: `MetricStore.delete_known_device()`
plus a one-time `device_stability.purge_non_devices()` migration, run at startup
behind `signal_quality/non_devices_purged_v1`.

The record/claim split the program is built on is not violated by this, because
`known_device` is not the recording layer. `device_state`, `device_event` and
`device_ip_history` are the append-only records; `known_device` is an inventory
**claim**. Deleting the row retracts a false claim and destroys no record —
verified on a byte-copy of the live database, where the purged MAC kept all
1,043 `device_state` rows, 8 `device_event` rows and its `device_ip_history`
entry. No foreign key exists anywhere in the schema, so nothing cascades.

The alternative — keep the row, add an `is_not_a_device` column, filter at every
read — was rejected on cost and collision: it needs a schema version that the
already-planned Phase 6 migration (`known_device` += `presence_state`,
`gone_notified_ts`, `importance_tier`, `importance_source`) would immediately
supersede, plus updating six-plus independent read sites, and it forces the
criterion to be restated rather than met.

Only `NOT_A_DEVICE` is purged. `ANONYMOUS` devices are real hosts the app cannot
name — 8 of these 30 carry a randomised MAC — and deleting those would remove
live devices from the user's inventory.

**No "Forget device" UI.** That is a new feature, and the feature set is closed
(v2.1.0+); the purge is a data-correctness migration only. It remains the
obvious home for one if a user ever asks.

## Phase 5 + 6 — ranking every surface, and turning the curated set on

Phases 1–4 decided *whether* the app may speak. Phase 5 decides *in what order*,
and Phase 6 decides *what is on out of the box*. They shipped together, schema
first, because `relevance.score()` reads `confidence` and `importance_tier` —
exactly the fields the Phase 6 migration adds. Building relevance first would
have meant building against columns that did not exist.

### Schema v21 → v22

`record_alert_fired()` persisted **6 of AlertFired's 12 fields**. Alert history
could not distinguish a resolution from an alert except by inferring it from
`severity = 'HEALTHY'`, and the evidence behind a claim was discarded at the
moment it was recorded.

```
alert_fired  += confidence, evidence_json, dedup_key, resolved_ts,
                is_resolution, value        + idx_af_dedup(dedup_key, ts)
known_device += presence_state, gone_notified_ts,
                importance_tier, importance_source
```

Three things fell out of it that are worth recording:

**The write path had eight bypasses.** `app.py` carried eight hand-written
`store.record_alert_fired(...)` calls alongside `scan_persistence.persist_alert()`.
Widening the row without collapsing those first would have landed the new columns
on some alerts and not others. `persist_alert()` is now the single choke point,
and a field added to the dataclass reaches history everywhere at once.

**`idx_af_dedup` cannot live in the DDL block.** `apply_sqlite_schema()` runs
`executescript(_DDL)` *before* the `ALTER TABLE` migrations, so on an upgrading
database `CREATE INDEX ... ON alert_fired(dedup_key, ts)` raises "no such column"
and takes the whole schema apply down with it. It moved to a
`_POST_MIGRATION_INDEXES` pass that runs after the columns exist.

**`importance_tier` is a cache and says so.** `get_device_importance_tier()`
still recomputes per call for the alert gate — the stored values this model
replaced were wrong for 8 of 13 devices, so a cached verdict must never become
authority. The column exists so `relevance` can rank a whole claim list from one
read instead of a query per row, and `refresh_importance_tiers()` recomputes it
set-wise per scan and at startup. Verified on the repo database immediately after
migration: **2 critical, 6 personal, 26 transient** — the 2 being the gateway and
the mesh AP, matching Phase 2's "2 of 30 alert-eligible" exactly.

`known_device.presence_state`/`gone_notified_ts` retire the `query_device_events()`
lookback Phase 1 used to edge-trigger `LEFT`. Same behaviour, one fewer query per
absent device per scan, and no longer dependent on event-table retention
outliving the absence. A NULL stamp reads as "not yet reported", which is also
the correct reading for every row upgrading from v21.

### relevance.py — ordering only

`score(claim) -> float`, from severity × importance tier × confidence × recency,
plus an actionability bonus and a bounded dismissal penalty. It is **not** a
severity, not a probability, and never shown to a user. RULE-A3's
`Info/Warning/High/Critical` and the internal `RISK_COLORS` scale are both
untouched; a `Claim` carries its producer's severity string through verbatim.

The design rule that runs through the module is **absence of information never
ranks a claim down** — the program plan names over-suppression as the failure
mode to watch. An unknown tier outranks a known-`transient` one; an absent
confidence outranks a low one; an unrecognised severity still scores above zero.
A fresh install knows none of these things about anything.

Two findings from building it:

- **A flat recency floor destroys ordering in the tail.** An exponential decay
  underflows within a few weeks, so every claim older than ~200 days scored an
  identical floor value and a year-long Timeline rendered its tail in arbitrary
  order. The floor is now a hyperbolic tail, so recency is *strictly* decreasing
  forever while the exponential still does the real work inside the first days.
- **`get_unacked_alerts()` orders `ts ASC`, and the Home card took `[:5]`.** The
  one card whose entire job is "what needs attention" was showing the five
  **oldest** unacked alerts — a gateway outage thirty seconds old was invisible
  behind five stale warnings from the previous week. This is the single largest
  user-visible win in the phase and it was a one-line consequence of ranking
  before truncating.

### Which surfaces were routed, and which deliberately were not

The distinction that matters is **priority queue vs. chronological record**.

| Surface | Change |
|---|---|
| Home "Action needed" card | Fully reordered — it is a priority queue |
| Timeline | Relevance chooses which 200 survive the cap; display stays newest-first |
| Overview activity feed | Same split, 20-row cap |
| Log hub alert correlation | Replaced a hand-rolled `critical/warning/other` ladder — a second, weaker copy of the ranking rule |
| Scan announcements | Four surfaces consolidated (below) |

A timeline reordered by importance stops being a timeline. But its row cap was
always a relevance judgement — it was simply being made by accident, as
"whichever N happen to be newest", so a chatty source could push a gateway
outage off the page entirely.

**Checked and deliberately left alone:** `inventory_page` and
`device_detail_pane` only *count* events for one MAC; `monitor_overview_page`
buckets them into sparkline counts; `alert_drawer` counts per host. None has an
ordering or a cap, so there is nothing for relevance to decide. Alert History
caps in SQL (`LIMIT 500`) and carries its own severity filter and sort — routing
it would mean changing the query, and it is a ledger the user already controls.

### The four ungated new-device surfaces

A scan announced its new devices four independent times — a status line, a Live
Bandwidth annotation, a naming toast, and the MQTT feed — each with its own idea
of what mattered. The status line listed the first three devices *in scan order*
and the toast named `new_devices[0]`, so a scan that discovered a new router and
four IoT bulbs would name whichever the scanner answered first.

`_surface_new_devices()` consolidates them: one status line, one annotation, at
most one toast, all about the most *relevant* device. The tray notification keeps
its own opt-in gate; the MQTT feed is deliberately excluded, being a
machine-readable event stream rather than a claim competing for attention.

`--audit`'s `UNGATED_TRAY` check caught the move immediately — its allow-list is
keyed by enclosing function name, and the tray call had left `_m1_track_devices`.
The gate itself was intact; the allow-list needed the new function. Exactly what
that check exists for.

### Criterion 7 — the curated default-on set

**A curated set already existed, in the wrong layer.**
`ui/pages/notif_channel_panels.py` held
`_RECOMMENDED_RULES = {Host Down, New Device, High RTT, Cert Expiring, Host Flapping}`,
consumed by the first-run overlay and the "Enable recommended" button. It
predated this program entirely: none of Phase 4's four real signals were in it.
It is now a re-export of one definition in the model layer.

The shipped set is that list ∪ Phase 4's four signals, minus `High RTT` — dropped
on the owner's call because it is level-triggered against a fixed 200 ms
threshold, the defect class this program exists to remove:

`Host Down` · `New Device` · `Cert Expiring` · `Host Flapping` ·
`Infrastructure Unreachable` · `Mesh Degraded` · `Modem Signal Drop` · `DNS Latency`

**The lever is the QSettings fallback, not `_default_rules()`.** All four readers
(`app.py` twice, the Notifications page, and `alert_audit`'s `RULES_OPT_IN`)
hardcoded `False` as the default for an absent key; they now call
`default_enabled(name)`. The dataclass keeps `enabled=False`, because
`AlertEngine()` is constructed headlessly by the test suite and by
`tools/alert_replay.py` — flipping the field would have changed what those
*measure* rather than what a user receives. An explicit stored key still wins in
both directions, so anyone who has ever pressed Save keeps exactly what they
chose, including everything they turned off.

**Measured, not projected.** `alert_replay` is structurally blind to several of
these rules, so the curated set was measured directly against the repo database's
own `alert_fired` history — 580 rows over 34 days:

| Rule | Alerts (excl. resolutions) | Rate |
|---|---|---|
| `MODEM_SIGNAL_DROP` | 12 over a 30-day producer window | **0.40/day** |
| `INFRA_UNREACHABLE` | 2 | stimulus-only |
| `MESH_DEGRADED` | 2 | stimulus-only |
| `HOST_DOWN` | 1 | stimulus-only |
| `NEW_DEVICE`, `CERT_EXPIRY`, `FLAP`, `DNS_LATENCY` | 0 in 34 days | 0 |

Every `HOST_DOWN`/`INFRA_UNREACHABLE`/`MESH_DEGRADED` firing in that history
lands on **2026-08-06** — the criterion-5 verification day, i.e. they fired
because a stimulus was applied and were silent on the other 33 days.
`MODEM_SIGNAL_DROP` is the only member with a background rate, and at 0.40/day
it is real 5G signal behaviour on a real modem, not noise.

**Curated-set total ≈ 0.5/day**, against the 163.6/day an ungated engine produced
— criterion 8 met with margin.

That same query incidentally proved the schema change was needed:
`is_resolution` is 0 for every historical row by construction, while
`severity = 'HEALTHY'` identifies 1 of the 2 `HOST_DOWN` rows, 2 of the 4
`INFRA_UNREACHABLE` and 3 of the 15 `MODEM_SIGNAL_DROP`. The severity inference
was genuinely the only signal there was.

**Verified live (RULE-T6):** all 27 `alert_rules/*/enabled` keys deleted to
simulate a clean install, then `python app.py --audit` reported 20/20 with
`DELIVERABILITY` naming exactly the eight curated rules and nothing else.

### `DELIVERABILITY` — teaching the check, not shipping a default channel

Turning rules on by default breaks the old check: it required an *enabled
channel* whose `min_severity` accepts the rule's typical severity, and desktop
toasts are strictly opt-in.

Shipping a default channel was rejected. `notif/toast_enabled` defaulting to
`False` is a deliberate decision with a test file written specifically to pin it
(`tests/test_first_run_notif_optin.py` exists because it once defaulted
*checked*), and flipping it would start showing OS balloons to existing installs
that never asked for them.

The check was wrong instead. `ui/dashboard.py::_surface_alert_in_app()` is
documented in its own docstring as "always on, never gated" — status bar, tray
badge, Alert History, the Home card and the alert drawer all receive every fired
alert regardless of notification settings, and since Phase 5 in ranked order. In-app
surfacing is a real delivery path; `DELIVERABILITY` was modelling "delivery" as
"external channel", which was harmless only while no rule could be enabled
without the user configuring one.

It now passes when a rule reaches *any* surface, and stays informative rather
than vacuous by naming the in-app-only rules:

```
PASS  DELIVERABILITY  Every enabled rule reaches a surface; in-app only
      (no notification channel accepts them): Host Down, New Device,
      Cert Expiring, Host Flapping, Mesh Degraded, Modem Signal Drop,
      Infrastructure Unreachable, DNS Latency
```

### `RTT_ANOMALY`'s absolute floor — applied

Measured in Phase 4, deferred as a defaults decision, applied here at **150.0 ms
= `availability_monitor.DEFAULT_DEGRADED_THRESHOLD`** — the app's existing
definition of a slow host, not an invented number, and the same shape as
`_DNS_ABSOLUTE_FLOOR_MS`.

Without it, fixing the maturity gate meant a very stable host learned a very
tight `mean + 2σ` — 1.2 ms on one host, 2.0 ms on the gateway — so the gateway
was "responding slower than its usual pattern" on any 3 ms reply. Technically
true; not a claim any user would call real. Through the v2 tier gate the floor
takes the rule from **2.48/day to 0.15/day**.

It is a floor and never a ceiling: a host that normally answers in 600 ms keeps
its higher learned threshold, so learning can only ever make the rule quieter
about a given host.

Two tests in `test_alert_engine_v6_sprint2.py` pinned the old semantics (mean 20
/ σ 5 / observed 45 ms fires). They were rewritten as a **pair** asserting both
halves — below the floor never fires, above the floor *and* above mean+σ·stddev
does — because the semantics are the thing being changed, not an obstacle to it.
The rule still ships disabled, so nothing surfaces for anyone who has not opted in.

### Two smaller engine fixes

**`AlertRule.min_consecutive`** generalises
`_SERVICE_DOWN_MIN_CONSECUTIVE_FAILS`, a hardcoded 3 that only `SERVICE_DOWN`
had. The first attempt made it a plain field defaulting to 1 — which silently
removed the grace period from every hand-constructed `SERVICE_DOWN` rule, since
the old constant applied to *all* of them and only `_default_rules()` would have
carried the new value. The default is therefore keyed by **rule type**
(`DEFAULT_MIN_CONSECUTIVE_BY_RULE_TYPE`), so behaviour is identical for every
existing caller. `HOST_DOWN` stays at 1 deliberately: its confirmation lives in
the monitor layer, and stacking a second one would push the first gateway alert
past criterion 5's three-minute budget.

**Restart-safe dedup.** `_last_fired` was in-memory, so every restart reset every
cooldown and a still-true condition re-alerted on launch. `load_last_fired()`
seeds it from `get_last_fired_by_rule_host()` — derived from the `alert_fired`
record itself rather than a second persistence path, so dedup state cannot drift
from the history the user is looking at. Resolutions are excluded: a resolution
is not a firing, and seeding one would mute the next genuine alert for a whole
cooldown after every recovery.

### Criterion 2 stays open

`192.168.68.54`'s state churn (306 → ≤ 10) is measured from *observed* claims
written while the app runs with `experimental/signal_quality_v2` on. It cannot be
replayed — the replay reads `device_state` rows already written under the old
classification. The flag is on and the curated rules are now armed by default, so
the next chaos run collects it.

## The curation decision for the two revived rules — measured 2026-08-09

Phase 4 fixed `JITTER_HIGH` and `RTT_ANOMALY` and left both out of the curated
set, recorded as "revived in Phase 4, never curated" — a deferral with no
scheduled decision behind it. Both were measured directly against the live
database (read-only, `mode=ro`) rather than through `alert_replay`, which is
structurally blind to both: it drives `evaluate_cycle()` only, while
`app.py::_on_cycle` calls `evaluate_jitter_checks()` and
`evaluate_rtt_anomaly_checks()` separately.

**`JITTER_HIGH` — not enough evidence to curate. Recommend leaving it off.**

The producer works. `rtt_sample.jitter_ms` is no longer `-1.0` on every row —
but only **84 of 26,048 rows (0.3%)** carry a real value, spanning **41
minutes**, because the app has run only briefly since v2.2.3 shipped the
producer (daily `rtt_sample` volume on this machine runs 0–342, and every
jitter-bearing row is from today).

| | |
|---|---|
| 10-minute windows evaluated | 12 |
| Windows that would fire at `threshold_ms=20.0` | **0** |
| Observed jitter | 8.8.8.8 mean 3.6 ms / p95 10.1 / max 12.2; 1.1.1.1 mean 1.7 / p95 3.6 / max 4.0 |
| Hosts with any jitter data | **2** — `8.8.8.8`, `1.1.1.1` |

Forty-one minutes cannot support a per-day rate, and quoting one would be the
exact thing the Phase 0 methodology note warns against. Two further reasons hold
independently of how much data arrives later:

- **The gateway is not sampled.** The Phase 4 note describes sampling as "bounded
  to the gateway plus `DEFAULT_TARGETS`"; measured, only the two public DNS
  resolvers carry jitter. So the rule currently speaks only about the uplink to
  two external IPs — and `DNS_LATENCY`, already curated, covers that ground with
  a self-learned per-network baseline rather than a fixed 20 ms constant.
- **A fixed `threshold_ms=20.0` is the defect class this programme exists to
  remove** — the same objection that dropped `High RTT` (fixed 200 ms) from the
  curated set on the owner's call. Curating a second fixed-threshold rule would
  reverse that decision by accident.

**`RTT_ANOMALY` — the measurement supports curating it; the call is the owner's.**

Unlike jitter, this one has real history behind it: **28.8 days**, and **18 of 24
hosts** have exceeded the 150 ms absolute floor at some point in it, so the rule
is neither dormant nor hair-trigger. Phase 6 already measured its rate through
the v2 tier gate with the floor applied at **0.15/day** — quieter than
`MODEM_SIGNAL_DROP` (0.40/day), which *is* curated, and it is a learned-baseline
rule rather than a fixed-threshold one, so it does not carry the objection that
disqualifies `JITTER_HIGH` and `High RTT`.

The stated reason for exclusion is only that it was revived late, and no
principled objection to it is recorded anywhere. Note what curating it would
actually add: the tier gate admits 2 of 30 devices, and 14 of the 15 hosts that
would trip the floored predicate are `transient`, so in practice this is the
gateway reporting that it is answering unusually slowly *and* above 150 ms.

Left as-is pending an explicit call, because `DEFAULT_ENABLED_RULES` is a
shipped-defaults decision of the same kind the owner made by hand for the other
eight, and changing what a fresh install alerts on is not a measurement's to
make.

## Regression pinning

`tests/test_signal_noise_ratchet.py` pins claims/day so a later change cannot
give the reduction back. It runs against a **deterministic synthetic fixture**
rather than captured real history, because this database prunes — the window
already moved 25.4 → 23.7 days — and a ratchet whose denominator drifts measures
pruning rather than noise. The fixture reproduces the defect shapes above and
measures 508.6/day through the legacy role gate against **0.858/day** through
the v2 path (5.577/day at Phase 2), the same order as the live 91.9 → 1.1. Its
per-rule ceilings dropped with it, and `LOSS_THRESHOLD` was **removed** from
`TIER_PER_RULE_CEILING` entirely — a rule type absent from that dict must fire
zero times, so its return would fail the ratchet rather than pass quietly. It
also asserts structurally
that the multicast group and both unnameable privacy MACs stay out of scope
while the gateway and the mesh AP stay in — a rate can hold flat while the gate
starts speaking about the wrong hosts.

## Reproducing

```
python tools/alert_replay.py                       # full history
python tools/alert_replay.py --days 13             # bounded window
python tools/alert_replay.py --json out.json       # machine-readable
python tools/alert_replay.py --gateway 192.168.68.1  # feed the tier gate real evidence
```

Read-only (`mode=ro`); safe to run while the app is running.
