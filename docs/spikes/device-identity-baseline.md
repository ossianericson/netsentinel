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

## Reproducing

```
python tools/identity_replay.py                    # full history
python tools/identity_replay.py --days 30          # bounded window
python tools/identity_replay.py --json out.json    # machine-readable
```

Read-only (`mode=ro`); safe to run while the app is running.
