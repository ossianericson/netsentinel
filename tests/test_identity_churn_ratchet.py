"""
Churn ratchet for the Device Identity & Classification Program — the identity
counterpart to tests/test_signal_noise_ratchet.py.

The alerting programme's premise was "is the app too noisy?" must be a number.
The identity programme's is the same: "does the app keep changing its mind about
what a device is?" must be a number, not an opinion. `tools/identity_replay.py`
produces that number; this file pins it so a later change cannot quietly give it
back. Ceilings only ever move downward.

**Why this exists alongside `--audit`'s IDENTITY_CHURN check.** That check reads
whichever database is on the machine. It is the right shape for a live install
and the wrong shape for a regression gate: it passes vacuously on a fresh or
empty database, its denominator moves as retention prunes rows, and its no-op
half is bounded below by the `identity_noop_guard_since` meta stamp (v2.2.5), so
two runs either side of an upgrade are not comparable. Exactly the reasoning
test_signal_noise_ratchet.py records for preferring a synthetic fixture over
captured real history — the live number is measured in
`docs/spikes/device-identity-baseline.md`; this pins regression. Neither
substitutes for the other.

**What is actually driven.** Both columns below write through the real
`MetricStore.record_device_change_event()` — the single choke point that carries
the no-op guard — and the v2 column arbitrates through the real
`modules/device_classification.py::arbitrate()`. Nothing about the outcome is
hardcoded in the fixture: it is five writers disagreeing about five devices over
a scan sequence, and what the two columns measure is what those writers produce.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.device_classification import (  # noqa: E402
    ClassificationClaim,
    arbitrate,
)
from modules.metric_store import MetricStore  # noqa: E402
from tools import identity_replay  # noqa: E402

# ── Ratchet baselines — LOWER THESE when a change makes the app steadier, ────
# ── never raise them. A rise means classification started churning again. ────
#
# Measured against the fixture below on 2026-08-09, over its 18-hour window:
#   legacy (5 unconditional writers per scan): 40.533 class_changed/device-day
#   v2     (one arbitrated verdict per scan):   1.333 class_changed/device-day
#
# The live reference-network equivalent at Phase 0 was 7.080/device-day with
# 47.5% no-ops (device-identity-baseline.md). The fixture is smaller and much
# denser (10 scans in 18 h), so absolute rates are not comparable to the live
# ones — the 30x *ratio* between the two columns is what is being pinned.
#
# Both rates scale with the fixture's window, so these ceilings move if SCANS or
# SCAN_INTERVAL_H change. test_the_arbiter_writes_once_per_device_and_stops
# below is the window-independent statement of the same invariant.
V2_CLASS_CHANGED_PER_DEVICE_DAY_CEILING = 1.34
LEGACY_CLASS_CHANGED_PER_DEVICE_DAY_CEILING = 41.0

#: Acceptance criterion 3 — "no device assigned more than 2 distinct types".
V2_MAX_DISTINCT_TYPES = 2

#: Acceptance criterion 4 — share of rows with a vendor or hostname that carry
#: a non-zero confidence. `classify_with_evidence()` computed this from the
#: start and nothing persisted it; every row read 0.0 on every install until
#: v2.2.4.
V2_MIN_CONFIDENCE_COVERAGE = 0.90

# The fixture's own shape. Changing these changes every number above.
SCANS = 10
SCAN_INTERVAL_H = 2


# ── Fixture devices ──────────────────────────────────────────────────────────
# Drawn from the reference network's actual churn table, not invented: these are
# the shapes that produced 11,176 class_changed events over 50.9 days.

DEVICES = [
    # (mac, ip, hostname, vendor, what each writer independently believes)
    #
    # The Lexmark printer: top churn source at 1,842 events, 2 distinct types.
    # The registry knows it; the bare heuristic does not.
    dict(
        mac="00:21:b7:a3:09:1a", ip="192.168.68.60",
        hostname="ET0021B7A3091A", vendor="Lexmark International",
        writers={
            "registry":       ("Print Server", 0.90),
            "heuristic":      ("Unknown Device", 0.00),
            "dhcp":           ("Print Server", 0.75),
            "passive-mdns":   ("Print Server", 0.60),
            "hostname-sync":  ("Unknown Device", 0.00),
        },
    ),
    # The Deco gateway: 1,379 events, EVERY ONE a no-op. All five writers agree
    # and always did — this device exists in the fixture to prove the guard at
    # the write choke point actually suppresses the write rather than the
    # arbiter merely happening not to change its mind.
    dict(
        mac="3c:64:cf:e0:27:02", ip="192.168.68.1",
        hostname="deco", vendor="TP-Link",
        writers={
            "registry":       ("Router / Gateway", 0.90),
            "heuristic":      ("Router / Gateway", 0.70),
            "dhcp":           ("Router / Gateway", 0.75),
            "passive-ssdp":   ("Router / Gateway", 0.60),
            "hostname-sync":  ("Router / Gateway", 0.70),
        },
    ),
    # The Sonos: 1,255 events across FOUR distinct types — the network's worst,
    # and the single reason acceptance criterion 3 was missed. Genuine
    # disagreement between every source.
    dict(
        mac="00:22:61:d8:ee:58", ip="192.168.68.62",
        hostname="Sonos-00226 1D8EE58", vendor="Sonos, Inc.",
        writers={
            "registry":       ("Smart Speaker", 0.90),
            "heuristic":      ("Unknown Device", 0.00),
            "dhcp":           ("Streaming Stick", 0.35),
            "passive-mdns":   ("Smart Speaker", 0.60),
            "hostname-sync":  ("Smart TV", 0.30),
        },
    ),
    # Ossians-iPhone-2022: randomised MAC, so vendor lookup returns nothing and
    # only the hostname identifies it. This is the v2.2.5 vendor-gate case — the
    # device that could not be classified at all under v2.2.4 as shipped.
    dict(
        mac="92:ac:4a:bf:8d:10", ip="192.168.68.57",
        hostname="Ossians-iPhone-2022", vendor="",
        writers={
            "heuristic":      ("iPhone / iPad", 0.30),
            "dhcp":           ("Unknown Device", 0.00),
            "passive-mdns":   ("iPhone / iPad", 0.60),
            "hostname-sync":  ("iPhone / iPad", 0.30),
        },
    ),
    # The Google Nest Wifi mesh AP: the device the old pipeline called a Video
    # Doorbell while it carried the alert-eligible infrastructure role. One
    # writer is confidently wrong; corroboration between the other two is what
    # has to beat it.
    dict(
        mac="f0:72:ea:51:d3:b8", ip="192.168.68.64",
        hostname="", vendor="Google Nest / Nest Wifi",
        writers={
            "registry":       ("Mesh Network Node", 0.90),
            "heuristic":      ("Video Doorbell", 0.70),
            "passive-ssdp":   ("Mesh Network Node", 0.60),
            "hostname-sync":  ("Video Doorbell", 0.70),
        },
    ),
]

#: Writer order within one scan. The legacy path applies these in sequence and
#: whichever is last wins — the defect. The order is deliberately the one that
#: makes the *wrong* answer win for the Sonos and the Nest, because "last writer
#: wins" being occasionally right is what made the bug survive.
WRITER_ORDER = ["registry", "heuristic", "dhcp", "passive-mdns", "passive-ssdp",
                "hostname-sync"]


def _ts(scan_index: int) -> str:
    """device_events.ts is a TEXT datetime, not an epoch int."""
    hour = scan_index * SCAN_INTERVAL_H
    return f"2026-02-{1 + hour // 24:02d} {hour % 24:02d}:00:00"


def _seed_inventory(store: MetricStore, confidences: dict, types: dict) -> None:
    for dev in DEVICES:
        store.upsert_known_device(
            mac=dev["mac"], ip=dev["ip"], hostname=dev["hostname"],
            vendor=dev["vendor"], device_type=types.get(dev["mac"], ""),
            confidence=confidences.get(dev["mac"], 0.0),
        )


def _simulate(db_path: Path, arbitrated: bool) -> dict:
    """Run SCANS scan cycles against a fresh store and return the write stats.

    `arbitrated=False` reproduces the pre-v2.2.4 pipeline: each writer applies
    its own answer unconditionally, in WRITER_ORDER, so the stored type is
    whichever fired last. `arbitrated=True` is the shipped pipeline: every
    writer's opinion is a claim, and one verdict per device per scan is written.
    """
    store = MetricStore(db_path=db_path, prune_on_init=False)
    current: dict = {d["mac"]: "" for d in DEVICES}
    confidence: dict = {d["mac"]: 0.0 for d in DEVICES}
    noop_attempts = 0

    for scan in range(SCANS):
        high_water = store._execute_read(
            "SELECT COALESCE(MAX(id), 0) AS m FROM device_events", ()
        )[0]["m"]
        # One real ip_changed per scan (a DHCP lease shuffle), so the fixture's
        # window spans the whole simulated period on BOTH paths. Without it the
        # arbitrated path converges after scan 0 and writes nothing further, so
        # resolve_window() would collapse to its 1-hour floor and report the
        # steadiest possible pipeline as the churniest. The churn numerator is
        # unaffected: class_change_totals() filters on event_type.
        store.record_device_change_event(
            mac=DEVICES[0]["mac"], event_type="ip_changed",
            old_value=f"192.168.68.{60 + scan}", new_value=f"192.168.68.{61 + scan}",
            source="ratchet",
        )
        for dev in DEVICES:
            mac = dev["mac"]
            writers = dev["writers"]
            if arbitrated:
                claims = [
                    ClassificationClaim(device_type=t, confidence=c, source=src,
                                        evidence=f"{src} match")
                    for src, (t, c) in writers.items()
                ]
                verdict = arbitrate(claims)
                proposals = [(verdict.device_type, verdict.confidence)]
            else:
                proposals = [
                    (writers[src][0], writers[src][1])
                    for src in WRITER_ORDER if src in writers
                ]
            for new_type, new_conf in proposals:
                if (current[mac] or "") == (new_type or ""):
                    noop_attempts += 1
                store.record_device_change_event(
                    mac=mac, event_type="class_changed",
                    old_value=current[mac], new_value=new_type,
                    source="ratchet",
                )
                current[mac] = new_type
                confidence[mac] = new_conf
        # record_device_change_event() stamps ts from the wall clock (correct
        # for production, useless for a fixture), so restamp exactly the rows
        # this scan wrote — by id, not by a ts pattern — onto the fixture's own
        # timeline. Everything above still goes through the real write path.
        store._execute_write(
            "UPDATE device_events SET ts = ? WHERE id > ?", (_ts(scan), high_water)
        )

    _seed_inventory(store, confidence, current)
    store.close()
    return {"noop_attempts": noop_attempts, "final_types": dict(current)}


@pytest.fixture(scope="module")
def legacy_run(tmp_path_factory):
    path = tmp_path_factory.mktemp("identity_legacy") / "NetSentinel.db"
    stats = _simulate(path, arbitrated=False)
    return path, stats


@pytest.fixture(scope="module")
def v2_run(tmp_path_factory):
    path = tmp_path_factory.mktemp("identity_v2") / "NetSentinel.db"
    stats = _simulate(path, arbitrated=True)
    return path, stats


def _summary(path: Path) -> dict:
    conn = identity_replay.open_db(path)
    try:
        since, span = identity_replay.resolve_window(conn, None)
        return identity_replay.build_summary(
            identity_replay.class_change_totals(conn, since),
            identity_replay.hotspots(conn, since),
            identity_replay.disagreement(conn),
            identity_replay.confidence_coverage(conn),
            identity_replay.identity_breakdown(conn),
            identity_replay.ip_collisions(conn),
            identity_replay.device_count(conn),
            span,
            identity_replay.max_distinct_types(conn, since),
        )
    finally:
        conn.close()


@pytest.fixture(scope="module")
def v2_summary(v2_run):
    return _summary(v2_run[0])


@pytest.fixture(scope="module")
def legacy_summary(legacy_run):
    return _summary(legacy_run[0])


# ── The ratchet ──────────────────────────────────────────────────────────────

def test_the_fixture_actually_attempts_no_op_writes(legacy_run, v2_run):
    """Non-vacuity guard. Every assertion about the no-op share below is
    meaningless if nothing in the fixture ever tries to write old == new — and
    the Deco gateway, whose five writers have always agreed, exists precisely to
    make sure something does. If this fails, the fixture stopped reproducing the
    defect and the guard is no longer under test."""
    assert legacy_run[1]["noop_attempts"] > 0
    assert v2_run[1]["noop_attempts"] > 0


def test_no_op_writes_never_reach_the_audit_trail(v2_summary, legacy_summary):
    """47.5% of every class_changed row on the reference network claimed a
    change that did not happen. The guard lives at the single write choke point
    (`record_device_change_event`), so this must hold for BOTH paths — a new
    writer that bypasses the choke point is exactly what this catches."""
    assert v2_summary["class_changed_noop_total"] == 0
    assert legacy_summary["class_changed_noop_total"] == 0


def test_arbitrated_churn_stays_under_the_ceiling(v2_summary):
    rate = v2_summary["class_changed_per_device_day"]
    assert rate <= V2_CLASS_CHANGED_PER_DEVICE_DAY_CEILING, (
        f"Identity churn ratchet breached: {rate:.3f} class_changed/device-day "
        f"> ceiling {V2_CLASS_CHANGED_PER_DEVICE_DAY_CEILING}. Something started "
        f"changing a device's type again after the arbiter settled it."
    )


def test_the_arbiter_writes_once_per_device_and_stops(v2_summary, legacy_summary):
    """The window-independent form of the ceiling above, and the sharper claim.

    Every device's evidence is identical on scan 1 and scan 10 — nothing about
    it changed — so a correct pipeline classifies each device once and then has
    nothing further to say. The arbiter writes exactly `len(DEVICES)` rows
    across the whole run; last-writer-wins writes on almost every scan because
    each writer overwrites the previous one's answer in turn."""
    assert v2_summary["class_changed_total"] == len(DEVICES), (
        "the arbiter changed a device's type after settling it, on evidence "
        "that never changed"
    )
    assert legacy_summary["class_changed_total"] > 10 * len(DEVICES), (
        "the legacy path stopped churning, so the comparison above no longer "
        "measures what the arbiter fixed — check the fixture still reproduces "
        "the defect"
    )


def test_the_arbiter_is_decisively_steadier_than_last_writer_wins(
    v2_summary, legacy_summary
):
    """Characterization + direction pin, mirroring
    test_legacy_gate_stays_the_loud_one. The arbiter's entire justification is
    that it is dramatically steadier than the unconditional writers it replaced;
    if that inverts, the replacement stopped being worth its risk."""
    legacy = legacy_summary["class_changed_per_device_day"]
    v2 = v2_summary["class_changed_per_device_day"]
    assert legacy <= LEGACY_CLASS_CHANGED_PER_DEVICE_DAY_CEILING
    assert v2 < legacy / 4, (
        f"The arbiter ({v2:.3f}/device-day) is no longer decisively steadier "
        f"than last-writer-wins ({legacy:.3f}/device-day)."
    )


def test_no_device_cycles_through_more_than_two_types(v2_summary, legacy_summary):
    """Acceptance criterion 3. The Sonos hit four distinct types on the real
    network and the fixture reproduces its four disagreeing sources, so this
    fails loudly if arbitration stops converging."""
    assert v2_summary["max_distinct_types_by_mac"] <= V2_MAX_DISTINCT_TYPES
    assert legacy_summary["max_distinct_types_by_mac"] > V2_MAX_DISTINCT_TYPES, (
        "the legacy path stopped churning, so this test no longer proves the "
        "arbiter is what fixed it — check the fixture still reproduces the defect"
    )


def test_confidence_is_persisted_for_every_nameable_device(v2_summary):
    """Acceptance criterion 4. `classify_with_evidence()` scored a confidence on
    every call from the start and nothing stored it — `known_device.confidence`
    read 0.0 on every row of every install until v2.2.4."""
    share = v2_summary["confidence_coverage_share"]
    assert share >= V2_MIN_CONFIDENCE_COVERAGE, (
        f"Confidence coverage {share:.1%} < {V2_MIN_CONFIDENCE_COVERAGE:.0%} — "
        f"a classification path stopped persisting the score it computed."
    )


def test_what_the_page_shows_agrees_with_the_audit_trail(v2_summary):
    """The baseline's sharpest finding: for 20 of 26 devices, what the Devices
    page showed was not what the app's own audit trail said happened most
    recently (23.1% agreement). A column with five writers and no arbiter does
    not average out to mostly-right — it converges on whoever wrote last."""
    assert v2_summary["device_type_agreement_share"] == 1.0, (
        f"known_device.device_type disagrees with the newest class_changed "
        f"event for {v2_summary['device_type_mismatches']}"
    )


# ── Structural half — a rate can hold flat while the answers go wrong ────────

def test_the_arbiter_picks_corroborated_evidence_over_a_confident_lone_source(v2_run):
    """The Nest Wifi case, expressed as a test. One writer says Video Doorbell
    at 0.70 and says it twice; two independent writers say Mesh Network Node.
    Under last-writer-wins the doorbell won — that is how the mesh AP, one of
    only two alert-eligible devices on the network, ended up misclassified."""
    final = v2_run[1]["final_types"]
    assert final["f0:72:ea:51:d3:b8"] == "Mesh Network Node"
    assert final["00:22:61:d8:ee:58"] == "Smart Speaker"


def test_a_randomised_mac_is_still_classified_from_its_hostname(v2_run):
    """RULE-T3 regression pin for the v2.2.5 vendor-gate fix. iOS and Android
    both default to randomised MACs, so vendor lookup returns nothing for
    exactly the devices whose hostname rules exist. The arbiter cannot rescue a
    device no writer can classify — this asserts the writers still can."""
    assert v2_run[1]["final_types"]["92:ac:4a:bf:8d:10"] == "iPhone / iPad"


def test_legacy_path_ends_on_whoever_wrote_last(legacy_run):
    """Characterization of the defect itself, so the comparison above cannot
    quietly become a comparison of two correct pipelines."""
    final = legacy_run[1]["final_types"]
    assert final["f0:72:ea:51:d3:b8"] == "Video Doorbell"
    assert final["00:22:61:d8:ee:58"] == "Smart TV"
