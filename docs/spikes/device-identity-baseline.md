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

## A4 — arbitrating the registry against the heuristic (2026-08-12)

`claim_from_scan()` returned the MAC-registry claim **instead of** the heuristic claim
whenever the registry had an entry, so `arbitrate()` — the one mechanism built to catch
"sources disagree" — was structurally bypassed for exactly the source most likely to be
wrong. A4 adds `claims_from_scan()` (plural), which emits both, behind
`QSettings("experimental/identity_arbitrate_registry", False)` (RULE-EXP1).

**Full-history replay, both live databases, 2026-08-12.** Every `known_device` row run
through the real shipped `claim_from_scan()` (flag OFF) and `arbitrate(claims_from_scan())`
(flag ON), with the live gateway MAC resolved so the gateway path was actually exercised:

| | AppData DB | Repo-root DB |
|---|---|---|
| rows measured | 34 | 37 |
| rows with a registry hit (the only rows A4 can affect) | 10 | 10 |
| registry + heuristic agree, or heuristic abstains | 9 | 9 |
| genuine conflict | 1 | 1 |
| **`device_type` changed** | **0** | **0** |
| confidence changed, same type | 3 | 3 |

Every device whose verdict moves, by name — the complete list, not a count:

| MAC | Device | Verdict |
|---|---|---|
| `78:c8:81:d7:9f:fe` | PS5-D79FFE / Sony | Games Console **0.90 → 0.93** (registry + vendor heuristic corroborate) |
| `dc:a6:32:2c:41:c7` | LIBREELEC / Raspberry Pi | Single Board Computer **0.90 → 0.93** (same shape) |
| `d8:3a:dd:de:11:a7` | PINAS / Raspberry Pi | Single Board Computer **0.90 → 0.76**, evidence gains `conflicts with: File / NAS Server (0.30 from heuristic)` |

`d8:3a:dd:de:11:a7` is the network's only genuine registry-vs-heuristic disagreement and the
reason A4 exists. Note it reads vendor `Microsoft` in the AppData DB and `Raspberry Pi` in the
repo DB — the v2.2.6 IEEE-authority fix (`eaf044d`) landing in one build and not yet the other.

**Why zero type flips.** Without `open_ports`/`os_family` the heuristic tops out at
vendor 0.40 + hostname 0.30 = 0.70, so the registry's 0.90 wins every conflict on the type
axis. A4 changes what the verdict *reports*, not who wins. A flip needs a heuristic score
above 0.90 — four discriminators firing at once, or `is_gateway`, which returns 1.0.

**The gateway carve-out (decision D1, reversed by this measurement).** The first pass let the
`is_gateway` claim compete, on the reasoning that a gateway is definitionally a router. The
replay showed that flipping the reference network's Deco gateway `3c:64:cf:e0:27:02` from
`Mesh Network Node` (registry, 0.90) to `Router / Gateway` at **0.69** — the *only* device the
gateway path touches here, and the flip made its label less specific and less confident. That
row stores no hostname (`NULL` in both DBs), so `_MESH_HOSTNAME_RE` can never fire for it and
the shortcut always answers the generic label. The two claims are not really in conflict: one
is about ROLE and the other about PRODUCT, and the product already implies the role, but
`arbitrate()` has no notion of specificity and scores the specialisation as a disagreement.
`claims_from_scan()` therefore withholds the heuristic claim when the device is the gateway
*and* the registry knows the product. A gateway the registry has never heard of still gets its
heuristic claim. With the carve-out, A4 changes zero `device_type` values on this network.

**What this replay cannot show, and does not claim.** `class_changed` churn, no-op share and
`device_type` agreement are written **only** by `ui/scan_enrichment.py` during a GUI-driven
scan; a headless replay never touches that code path, so those rows are unchanged above by
construction — the same methodology limit as the v2.2.4 measurement further up this file.
`known_device` also stores no `open_ports`/`os_family`, so this measures the vendor+hostname
axis only; a live scan with open ports can score the heuristic higher than anything here.

**Live-widget verification (RULE-T6).** The real `_DeviceDrawer.load()` was driven against the
real repo-root database for `d8:3a:dd:de:11:a7`, flag off then on, reading back the labels a
user sees:

```
flag OFF:  Single Board Computer / Confidence: 90% (high) / Evidence: hostname:PINAS
flag ON :  Single Board Computer / Confidence: 76% (high) /
           Evidence: registry: MAC registry model-specific match;
                     conflicts with: File / NAS Server (0.30 from heuristic)
```

The OFF line is the defect in one screenful: the percentage describes the registry claim that
won, the evidence line describes the hostname claim that **lost**, and nothing on the panel
says the two disagreed.

## Phases 1–6 — measured against a live GUI scan (2026-08-13)

Every measurement above closes with the same caveat: `class_changed` churn and `device_type`
agreement are written **only** by `ui/scan_enrichment.py` during a GUI-driven scan, so a headless
replay cannot move them. This entry is the run that finally exercises that path — a full scan
invoked in the running app (UIA `Invoke` on the header `▶ Scan` button, no mouse, no focus steal),
against `0411b6f` (phases 1–6) as HEAD, with the database allowed to settle for 90 s of no new
`device_events` before measuring.

**Read the database provenance before reading any number here.** The pre-change figures this run
was set against — **73.3 % agreement, 71.0 % confidence coverage, 0.235 `class_changed`/device-day**
— come from the **AppData** database (`%LOCALAPPDATA%\NetSentinel\NetSentinel.db`, 34 rows). A
source launch (`python app.py`) resolves `_default_db_path()` tier 1 and writes the **repo-root**
`NetSentinel.db` (37 rows) instead, and there is no `--db` flag or env var to redirect it. So the
live scan below could not touch the baseline's database, and the AppData DB is *unchanged* by this
run — still on the pre-v23 schema, with no `capabilities` column. Reproducing those three numbers
requires `--db "%LOCALAPPDATA%\NetSentinel\NetSentinel.db"`; the default run reports the repo DB.
Treat the two as different networks-of-record, not as before/after of each other.

### The scan

Invoked 2026-08-13 11:20:26 Z, settled 11:26 (timestamps here are UTC, matching `device_events.ts`;
local time was +02:00). 15 of the 37 `known_device` rows had `last_seen` refreshed, `scan_count`
incremented on each, and the Devices page rendered 17 rows.

| | |
|---|---|
| `class_changed` rows written by this scan | **4** |
| ...of which no-ops (`old_value == new_value`) | **0** |
| `class_changed` written by the whole fixed-build session (since 11:12:23 Z) | **10**, 0 no-ops |
| Last no-op `class_changed` anywhere in the database | **2026-08-07 07:17:55** — six days before this run |

### Churn — read the window, not the headline

`--days 2` on this database is **not** a live-code number, and the default full-history run is
worse. The 2-day window's right edge sits on 2026-08-11, the 12.5-hour v2.2.6 release-readiness
chaos run, which wrote ~3,000 `class_changed` rows on its own:

| Window | span | `class_changed` | no-op share | per device-day |
|---|---|---|---|---|
| Full history (default run) | 43.9 d | 47,175 | **50.7 %** | 29.045 |
| `--days 2` (as asked) | 2.0 d | 3,068 | **0.0 %** | 41.459 |
| Post-chaos (after 2026-08-11 20:55 Z, `--days 1.6005`) | 1.6 d | 26 | **0.0 %** | **0.439** |
| Fixed build in charge (since 11:12:23 Z) | — | 10 | **0.0 %** | — |

The no-op column is the finding, and it is unambiguous in every window that contains only
post-guard writes: **0 %**. The lifetime 50.7 % is pre-guard history that can never drain, exactly
as the memory note for this program warns. The per-device-day figure is the one to distrust: 41.459
over two days and 0.439 over 1.6 days describe the same database, and the difference is entirely
one chaos run sitting inside the wider window.

`max_distinct_types_by_mac` is **5** lifetime but **3** within `--days 2` — still short of
acceptance criterion 3 (≤ 2 in 30 days), and still measured mostly on chaos-era rows.

### Confidence, agreement, identity — repo DB, post-scan

| Metric | Value |
|---|---|
| `known_device.confidence > 0`, of rows with a vendor or hostname | 19/27 (**70.4 %**) |
| `device_type` agreement with the newest `class_changed` event | 16/31 (**51.6 %**) |
| `classify_identity()` | 27 identified / 10 anonymous / **0 not-a-device** |
| IPs claimed by more than one MAC | 8 |
| Rows carrying the new `capabilities` column (schema v23) | **11** |

**Agreement did not move, and the reason is structural rather than a residual defect.** It was
51.6 % before the scan and 51.6 % after. Only 15 devices were online, and all four rows the scan
rewrote already agreed; the 22 offline rows keep whatever the 08-11 chaos run last wrote as their
"newest event" forever. On this database the metric is therefore bounded by *what is currently
powered on*, not by classifier quality — a device that never appears again can never have its audit
trail re-synced. That is a property of the metric, not a result, and it is the reason the 73.3 %
AppData figure and the 51.6 % repo figure are not comparable in either direction.

The `capabilities` column is doing precisely its job: both PlayStations keep `Games Console` while
recording `Spotify Connect`, and four Chromecast targets keep `Streaming Stick` while recording
`Cast target` — media announcements no longer make a product claim.

### Did the corrections land?

The "20 of 34 rows change" prediction was HEAD's classifier verdict compared against the values
**stored** in the AppData rows; replaying that same comparison today gives 24/34, the AppData rows
having drifted since. That set cannot be checked on the Devices page at all, because the running
app does not read that database.

The equivalent same-inputs diff on the repo DB — real shipped `classify_registry_first()` at
`55be48b` vs at `0411b6f`, over all 37 rows — changes **6 rows**, and each maps 1:1 onto a shipped
item:

| MAC | Pre (55be48b) | Post (0411b6f) | Stored now | Landed? |
|---|---|---|---|---|
| `20:1e:88:f7:2a:3d` | Unknown Device | Computer / Workstation | Computer / Workstation | **yes** |
| `2c:7b:a0:0d:37:8e` | Unknown Device | Computer / Workstation | Computer / Workstation | **yes** |
| `64:4a:7d:79:c5:d9` | Unknown Device | Computer / Workstation | Computer / Workstation | **yes** |
| `92:35:ca:16:8f:38` (`iPad-2`) | **Domain Controller** | iPhone / iPad | iPhone / iPad | **yes** |
| `f0:72:ea:51:d3:b8` | Video Doorbell | Unknown Device | Video Doorbell | no — by design |
| `00:22:61:d8:ee:58` (`Barnens-rum`) | Unknown Device | Smart Speaker / Audio | **File / NAS Server** | **no — defect** |

`92:35:ca:16:8f:38` is the Phase 0 headline row (`iPad-2` rendering as **Domain Controller**), now
carrying `iPhone / iPad` in the database — the `dc-` anchoring fix, confirmed on the original
device. The three `Computer / Workstation` rows are the PC-NIC-vendor rule.

`f0:72:ea:51:d3:b8` not healing is **intended**: `device_reenrichment.py` documents "it upgrades, it
never blanks", and the new verdict is `Unknown Device`. Its docstring adds "the next scan re-derives
it properly anyway" — which is true only for a device a scan can see, and this one is offline, so
item (3) of phases 1–6 has not taken effect on this row and will not until it reappears.

### Live-widget verification (RULE-T6)

The rendered Devices table was read back out of the running app via UIA (17 rows; the `All` filter
and flat `List` view still render only the current scan's devices — the other 21 `known_device` rows
are offline or privacy-MAC ghosts and never reach the table). **14 of 17 rows render exactly the
stored `device_type`.** The three that differ render the fresher scan-local verdict, and in two
cases that verdict is the *better* one — `64:e7:d8:6f:81:de` renders `Unknown Device` where the
stored row still says `Smart TV`, which is the Phase 0 complaint running in reverse.

### What the live scan found that no replay could

Two of the four `class_changed` rows this scan wrote are the arbitrated classifier being **overridden
by a weaker source on the live path** — the exact defect class phases 1–6 exist to close.

`00:22:61:d8:ee:58` (hostname `Barnens-rum`, IEEE vendor `Frontier Silicon Ltd`, an internet-radio /
multiroom-audio module) already stores `capabilities = ["Media renderer (DLNA)", "Spotify Connect"]`,
and `classify_with_evidence()` answers **`Smart Speaker / Audio`, confidence 0.40, evidence
`['vendor']`**. The live scan nonetheless wrote `Unknown Device → File / NAS Server`, twice.
`f4:ca:e7:80:31:02` (`LGwebOSTV-EAg4-1`) shows the same shape: HEAD's classifier says `Smart TV`, the
stored row said `IoT Device` at confidence **0.085**.

The cause turned out to be **two independent defects that compound**, and the investigation is worth
recording because three plausible single-cause hypotheses were each disproven by measurement first.
Both are fixed in the follow-up entry below.

**A sampling error worth not repeating.** The first hypothesis — that
`passive_observer.py`'s `mediaserver`/`_daap._tcp` entries still make a product claim — was recorded
here as *disproven*, on the strength of a 150 s passive listen and one SSDP M-SEARCH that showed the
device advertising only MediaRenderer. It was actually **correct**: a later 100 s window caught
`urn:schemas-upnp-org:device:mediaserver:1 → File / NAS Server` from that exact address. Frontier
Silicon announces MediaServer on a different NOTIFY cycle than MediaRenderer, and an M-SEARCH
response does not necessarily enumerate every root device the box will later advertise. **Absence in
one passive window is not absence** — for a periodic announcement, only a positive observation is
evidence, and the negative needs a window several announce-cycles long before it means anything.

Two other hypotheses were disproven and stayed disproven, both by direct measurement rather than
code reading: the `{445, 548}` ports rule (both ports probed **closed**; only 80 and 8080 are open),
and the vendor/hostname rules (which produce the correct answer on their own).

### What this measurement cannot show, and does not claim

- **The AppData baseline is untouched.** 73.3 % / 71.0 % / 0.235 were not re-measured after a scan,
  because no source-launched scan can reach that database. They remain the last word on that
  inventory until the installed build next runs, which will also migrate it to schema v23 and fire
  the re-enrichment pass for the first time there.
- **Agreement is capped by presence.** See above — 22 of 37 rows cannot move it while offline.
- **The classifier replay sees less than a live scan.** `classify_registry_first(mac, vendor,
  hostname)` has no `open_ports`, `os_family` or mDNS/SSDP evidence, so a bare-replay "stored vs
  verdict" gap (17/37 on the repo DB) counts abstentions as disagreements and overstates the real
  gap. The same-inputs old-vs-new diff (6/37) is the honest number; the stored value is frequently
  the better one.
- **One scan is one sample.** The 0 % no-op share is measured over 10 post-fix `class_changed` rows,
  not over a soak. The durable regression gate remains
  `tests/test_identity_churn_ratchet.py`, not this run.

## Stable arbitration — the oscillation's real root cause (2026-08-13)

The device above cycled `Smart Speaker / Audio → File / NAS Server → Smart TV` across three days on
unchanged evidence. The cause is in `arbitrate()` itself — the function phase 3 added to end exactly
this.

**`arbitrate()` decides ties by claim arrival order.** It groups claims by device_type, scores each
group, then `scored.sort(key=score, reverse=True)`. Python's sort is **stable**, so an exact tie
resolves to whichever group was inserted first, and insertion order follows the order claims arrived
in. The vendor heuristic scores 0.40 and a passive "low" announcement also scores 0.40 — so real
devices tie constantly, and the winner is whichever source happened to run first that scan:

```
arbitrate([audio, nas]) -> Smart Speaker / Audio      arbitrate([nas, audio]) -> File / NAS Server
arbitrate([audio, tv])  -> Smart Speaker / Audio      arbitrate([tv, audio])  -> Smart TV
```

That is the Phase 0 complaint — *"it converges on whichever writer fired last"* — alive inside the
function written to end it. It did not remove the non-determinism; it moved it from "last writer
wins" to "first claim in the list wins on ties". The tie also drives the confidence collapse:
`_CONFLICT_PENALTY` scales by how close the runner-up scored, so a near-tie loses almost the whole
0.35. The LG TV's stored **0.085** is exactly the 0.40-vs-0.30 case.

**A second, independent defect in the same direction.** `classify_with_evidence()` returns on the
**first** matching rule in `_RULES`, so precedence is *position in a hand-ordered list*, not strength
of evidence. Measured: a device matching the `{445,548}` ports rule (0.20) and a vendor rule (0.40)
returns the ports answer at 0.20 and discards the vendor evidence entirely.

### What shipped, behind `experimental/identity_stable_arbitration` (RULE-EXP1)

`arbitrate_stable()` alongside the untouched `arbitrate()`, plus `classify_with_evidence(best_rule=)`:

1. **Order independence** — ties break on evidence tier (identity over capability), then on a stable
   alphabetical key, so the verdict is a pure function of the claim *set*.
2. **Hysteresis** — a challenger must beat the incumbent by 0.10 to replace it, and the incumbent is
   defended **at the confidence it was stored with**. That distinction is the whole fix: every row
   the old path had wrong carried confidence 0.0, so a flat defence would have frozen the defect in
   place under the guise of stability. Measured before this refinement, `00:22:61:d8:ee:58` kept
   `File / NAS Server` under the very fix written to correct it.
3. **`mediaserver` is a capability** — completing phases 1–6, which neutralised MediaRenderer but
   left its mirror image claiming `File / NAS Server` at 0.40. Real NAS evidence is untouched
   (`_smb._tcp`, `_afpovertcp._tcp`, `_nfs._tcp`, the `synology|qnap|…` vendor rule, `{445,548}`).

| Measured across all 37 rows | shipped | stable |
|---|---|---|
| rows whose verdict depends on claim order | **8** | **0** |
| stored labels rewritten (real claim sets) | 8 | **3** — all three corrections |

**Two defects in the fix were found by measurement, not by the unit tests**, and both are worth
carrying forward as patterns:

- **The early return for "no informative claims" bypassed hysteresis**, blanking 6 rows (iPhone /
  iPad, Smart TV, Video Doorbell) to `Unknown Device` — all randomized MACs with no hostname, so the
  heuristic has nothing to work from *every* scan. A scan that observed nothing is not a scan that
  disproved the stored label. A test in this file had asserted the wrong behaviour; the replay
  corrected it.
- **`DeviceInfo.confidence` is not the incumbent's strength.** It is a scan-time field defaulting to
  0.0, filled only once this scan arbitrates that device, so feeding it as `incumbent_confidence`
  claims a registry-grade stored label is evidenced at 0.0. Live consequence: the Deco gateway was
  demoted from `Mesh Network Node` (registry, 0.90) to the generic `Router / Gateway` (passive SSDP,
  0.85) — the exact regression A4's gateway carve-out exists to prevent. The incumbent is the row in
  `known_device`; its strength is `known_device.confidence`. Found only by live verification.

**Live verification (RULE-T6).** Flag on, real GUI scan, values read back off the rendered Devices
table: `Barnens-rum` renders **Smart Speaker / Audio** (was `File / NAS Server`), the LG TV renders
**Smart TV** (was `IoT Device`), and the Deco gateway holds **Mesh Network Node** at 0.90. The
Galaxy Tab kept `Tablet` — a headless replay had predicted `best_rule` would prefer the
better-evidenced but less specific `Android Device` (0.70, vendor+hostname) over `Tablet` (0.30,
hostname only); the live scan has more evidence than the replay, so it did not. **Score is not
specificity** — that tension is real, unresolved in general, and the reason this ships behind a flag.

**Before promoting the flag**, bump `_REENRICH_GENERATION` in `modules/device_reenrichment.py` so
existing installs re-run the healing pass under the new arbiter — otherwise the rows that most need
the fix keep their old labels, which is that module's entire reason for existing.

## Reproducing

```
python tools/identity_replay.py                    # full history
python tools/identity_replay.py --days 30          # bounded window
python tools/identity_replay.py --json out.json    # machine-readable
```

Read-only (`mode=ro`); safe to run while the app is running.

**Pass `--db` explicitly.** The default is the AppData path, but a source-launched app writes the
repo-root `NetSentinel.db` — measuring the default while the app under test writes the other file
compares two unrelated inventories (see the 2026-08-13 entry above).

```
python tools/identity_replay.py --db NetSentinel.db --days 2
python tools/identity_replay.py --db "%LOCALAPPDATA%\NetSentinel\NetSentinel.db" --days 2
```

Where a window may span a chaos run, take the churn number from a window that starts after it
(`--days` accepts a fraction) — otherwise a single soak dominates the rate.
