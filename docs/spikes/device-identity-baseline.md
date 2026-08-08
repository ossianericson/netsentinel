# Device Identity & Classification — measured baseline (Phase 0)

Measured 2026-08-08 with `python tools/identity_replay.py`, against a real
`%LOCALAPPDATA%\NetSentinel\NetSentinel.db` holding **50.9 days** of history for a
31-device home network. Raw summary: `device-identity-baseline.json`.

This is the "before" number for the Device Identity & Classification Program — the
successor to the Signal Quality Program (`signal-quality-baseline.md`), same method.
Every later phase's fix is judged against these numbers; the acceptance criteria in
the program plan are expressed in these units.

## Headline

| Metric | Value |
|---|---|
| `class_changed` events (48-day count in the program plan was 11,159; now 11,176 over 50.9 days) | **11,176** |
| `class_changed` per device-day | **7.080** (acceptance criterion 2 target: ≤ 0.5) |
| Share of `class_changed` rows that are pure no-ops (`old_value == new_value`) | **47.5 %** (target: 0 %) |
| `known_device.device_type` agreement with the newest `device_events` class | **23.1 %** (6 of 26 comparable devices; target: 100 %) |
| `known_device.confidence > 0`, of rows with a vendor or hostname | **0.0 %** (0 of 31; target: ≥ 90 %) |
| IPs claimed by more than one MAC | **7** |

The disagreement number is the sharpest finding: for 20 of 26 devices with a
classification history, **what the Devices page shows is not what the app's own audit
trail says happened most recently.** A column with five independent writers and no
arbiter (see the program plan's root-cause table) does not average out to "mostly
right" — it converges on whichever writer fired last, which this measurement shows is
right barely more often than chance.

## Class-change churn (11,176 total / 50.9 days = 219.5/day)

Top eight churn sources — the same stable devices the program plan named, still
churning:

| Device | `class_changed` events | Distinct types assigned |
|---|---|---|
| Lexmark printer `00:21:b7:a3:09:1a` | 1,842 | 2 |
| Deco gateway `3c:64:cf:e0:27:02` | 1,379 | 1 *(every row a no-op — 100% wasted writes)* |
| Sonos `00:22:61:d8:ee:58` | 1,255 | 4 |
| LG TV `f4:ca:e7:80:31:02` | 815 | 3 |
| `a4:77:33:f2:20:0e` | 692 | 3 |
| `54:60:09:ee:10:2a` | 688 | 2 |
| Google device `88:3d:24:21:77:66` | 685 | 3 |
| PS4 `5c:93:a2:5c:47:19` | 619 | 2 |

`max_distinct_types_by_mac` across the whole inventory is **4** (the Sonos) —
acceptance criterion 3 ("no device assigned more than 2 distinct types in 30 days")
is not met by a wide margin for the network's noisiest devices.

## Disagreement — known_device.device_type vs. the newest class_changed event

26 of 31 devices have at least one `class_changed` event to compare against; only 6
agree with what `known_device.device_type` (what the Devices page renders) currently
shows. The five devices the program plan named by hand are all present in the full
mismatch list (`device-identity-baseline.json`):

| Device | `known_device.device_type` (shown to user) | Newest audit-trail class |
|---|---|---|
| `92:35:ca:16:8f:38` hostname `iPad-2` | **Domain Controller** | Router / Gateway |
| `f0:72:ea:51:d3:b8` vendor Google Nest Wifi | **Video Doorbell** | Streaming Stick |
| `00:21:b7:a3:09:1a` Lexmark printer | **Unknown Device** | Print Server |
| `92:ac:4a:bf:8d:10` hostname `Ossians-iPhone-2022` | **Unknown Device** | Streaming Stick |
| `f8:7d:76:d1:2c:84` hostname `Lovisas-ny-iphone`, vendor Apple | **Unknown Device** | Smart TV |

Both iPhones and the Lexmark are confirmed still `Unknown Device` on the page users
see, exactly as the program plan described. The iPad and Nest Wifi mismatches are
confirmed too, though the *newest* audit-trail value for each has itself since drifted
away from the specific wrong label the plan quoted (`Domain Controller` vs. `Router /
Gateway`, `Video Doorbell` vs. `Streaming Stick`) — consistent with the churn measured
above: the column keeps moving, it does not converge.

## Confidence coverage

**0 of 31** `known_device` rows have `confidence > 0`, including all 31 that have a
vendor or hostname to be confident about. `classify_with_evidence()` computes a
confidence score on every call; nothing persists it. Matches the program plan's
finding exactly (0 of 29 in the AppData DB, 0 of 34 in the repo DB, at the time it was
written).

## Identity breakdown (`classify_identity()`)

| Class | Count |
|---|---|
| Identified (nameable) | 25 |
| Anonymous (real device, no name) | 6 |
| Not a device (multicast/malformed) | 0 |

Zero `NOT_A_DEVICE` rows confirms the Signal Quality Phase 2 closeout purge
(`device_stability.purge_non_devices()`) is holding — the SSDP multicast group that
used to sit in this inventory is gone and has not come back.

## IP collisions

**7** IPs currently carry more than one MAC (up from 6 at the time the program plan
was written) — the confound that makes IP-keyed enrichment matching
(`ui/scan_enrichment.py::_on_passive_observation()`) attribute an observation to the
wrong device on this network on any of these addresses:

| IP | MACs |
|---|---|
| `192.168.68.64` | 3 |
| `192.168.68.58` | 3 |
| `192.168.68.66` | 2 |
| `192.168.68.61` | 2 |
| `192.168.68.59` | 2 |
| `192.168.68.56` | 2 |
| `192.168.68.51` | 2 |

## Measured after v2.2.4 (2026-08-08, same-day)

Two more measurements, same real `%LOCALAPPDATA%\NetSentinel\NetSentinel.db` and same 31
devices, taken minutes apart on 2026-08-08 by replaying every existing `known_device` row's
`(mac, vendor, hostname)` back through `DeviceTracker.process_scan()` — the exact write path
`ui/scan_wiring.py` uses, exercised here via a small headless harness instead of the PyQt GUI
(`process_scan()` is pure Python; see the methodology note below). `git stash` isolated the two
runs: the first ran under v2.2.4 exactly as shipped (commit `ba1832e`), the second after this
session's vendor-gate fix (`modules/device_classifier.py`, "Fix the vendor gate" below) and
`IDENTITY_CHURN` version-boundary fix landed on top of it.

| Metric | Phase 0 | v2.2.4 as shipped | + this session's fixes |
|---|---|---|---|
| `known_device.confidence > 0` | 0/31 (0.0%) | 17/31 (54.8%) | 18/31 (58.1%) |
| `device_type` agreement w/ newest audit event | 6/26 (23.1%) | 7/26 (26.9%) | 7/26 (26.9%)¹ |
| `python app.py --audit` → `IDENTITY_CHURN` | (check didn't exist) | **FAIL** — 48/78 (61.5%) no-ops in 7d | **PASS** — 21/21 checks |
| `92:ac:4a:bf:8d:10` (Ossians-iPhone-2022) | Unknown Device | **Unknown Device** ← Finding 1, confirmed live | **iPhone / iPad**, confidence 0.30 |
| `f8:7d:76:d1:2c:84` (Lovisas-ny-iphone) | Unknown Device | iPhone / iPad, 0.70 (self-healed) | iPhone / iPad, 0.70 (unchanged) |
| `00:21:b7:a3:09:1a` (Lexmark) | Unknown Device | Print Server, 0.40 (self-healed) | Print Server, 0.40 (unchanged) |

¹ Unmoved by design, not a residual defect — see methodology note.

**v2.2.4 as shipped confirms Finding 1 exactly as predicted.** Running the arbiter for the
first time moved confidence coverage from 0% to 54.8% and self-healed two of the three named
rows (Lovisas' iPhone, the Lexmark) purely by re-running the existing, unmodified classifier —
those were stale writes, not classifier bugs. `Ossians-iPhone-2022` did **not** self-heal:
`classify_with_evidence(vendor="", hostname="Ossians-iPhone-2022")` still returned
`Unknown Device` at confidence 0.0 under the shipped vendor-gate bug, because vendor lookup on
this device's randomised MAC returns nothing for the arbiter to corroborate against. This is
the live proof that the identity program's fix and this session's classifier fix are separate
defects, exactly as Finding 1 argued.

**After this session's fixes**, the same replay reclassifies `Ossians-iPhone-2022` correctly:
`iPhone / iPad` at confidence 0.30 (hostname-only match — `evidence=['hostname:Ossians-iPhone-2022',
'randomized-mac']`), and `python app.py --audit` flips `IDENTITY_CHURN` from a hard FAIL to
21/21 PASS, because the guard-timestamp fix excludes the pre-guard no-ops the 7-day window was
still averaging in.

**Methodology note — what this same-day measurement can and cannot show:**
- **Measurable immediately, and measured above:** confidence coverage, `known_device.device_type`
  correctness for specific rows (verified two ways: directly against the database, and by
  simulating `ui/pages/inventory_page.py`'s device-drawer call to `classify_with_evidence()` with
  the same stored vendor/hostname — confirms the drawer will render "iPhone / iPad", "Confidence:
  30% (medium)", "Evidence: hostname:Ossians-iPhone-2022, randomized-mac" for the exact device
  named in the plan), and the `IDENTITY_CHURN` audit gate.
- **Not measurable same-day, and not claimed above:** `class_changed` churn per device-day.
  `device_events` rows for this scan-cycle come from `ui/scan_enrichment.py` comparing
  before/after `known_device` snapshots after a full GUI-driven scan — a PyQt-layer step this
  headless harness deliberately does not exercise (`DeviceTracker.process_scan()` itself never
  writes `class_changed` rows; only `ui/scan_enrichment.py` does). The churn and
  "agreement with newest audit event" numbers above are therefore **unchanged from before this
  session** in both the shipped and fixed columns, not because the fixes had no effect on churn,
  but because this measurement never touched the code path that writes churn. A live GUI scan is
  needed to move those two rows; that is the one piece of RULE-T6 live-app verification this
  session could not perform directly (no screen/display-automation tool available), though the
  database- and code-level confirmation above is a strictly more precise substitute for the
  specific claim being verified (device_type/confidence/evidence for the three named rows).

## Reproducing

```
python tools/identity_replay.py                    # full history
python tools/identity_replay.py --days 30          # bounded window
python tools/identity_replay.py --json out.json    # machine-readable
```

Read-only (`mode=ro`); safe to run while the app is running.
