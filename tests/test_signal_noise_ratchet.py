"""
Noise ratchet for the Signal Quality Program — claims/day may only go DOWN.

The program's whole premise is that "is the app too noisy?" must be a number,
not an opinion. `tools/alert_replay.py` produces that number; this file pins it
so a later change cannot quietly give it back. Ceilings only ever move
downward, following the ratchet convention already in this codebase
(`test_item_tooltip_wrap.py`, `test_qss_scoping.py`).

**Why a synthetic fixture rather than captured real history.** The program plan
asked for "a committed fixture of the real history", and that turns out not to
be pinnable: the live database *prunes*, so its window shrank 25.4 -> 23.7 days
between Phase 0 and Phase 2 and totals stopped being comparable across runs. A
ratchet needs a fixed denominator or it measures pruning instead of noise. So
the fixture below is generated deterministically from the real schema (`_DDL`)
and reproduces the *defect shapes* measured on the reference network — a
level-triggered HOST_DOWN flood from devices that legitimately sleep, a device
sitting exactly on the DEGRADED boundary, wrong `inferred_role` on almost
everything, and an SSDP multicast group answering like a host.

The real number stays measurable — `python tools/alert_replay.py --gateway
192.168.68.1` against the live database, recorded in
`docs/spikes/signal-quality-baseline.md`. This ratchet pins regression; that
document pins reality. Neither substitutes for the other.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.metric_store_schema import _DDL  # noqa: E402
from tools import alert_replay  # noqa: E402

# ── Ratchet baselines — LOWER THESE when a change makes the app quieter, ─────
# ── never raise them. A rise means a regression re-admitted noise. ──────────
#
# Measured against the fixture below on 2026-08-05.
#   Phase 2 (tier gate only):     5.577/day
#   Phase 3 (+ edge trigger,      0.858/day   <- current
#            + outage dedup)
#   legacy role gate:           508.647/day  (unchanged by either phase)
#
# Phase 3 cut the survivors by 85%: the fixture holds exactly 3 outage episodes
# spanning 18 DOWN cycles, and the v2 path now emits one alert and one
# resolution per episode instead of one of each per cycle.
TIER_GATED_PER_DAY_CEILING = 0.86
LEGACY_GATED_PER_DAY_CEILING = 510.0

# Per-rule ceilings under the v2 path. Only HOST_DOWN and its resolution remain,
# and they are necessarily equal: every episode that opens also closes, so a
# divergence between these two means an outage was reported and never resolved
# (or vice versa) — worth a failure either way.
#
# **A rule type absent from this dict is a failure, not a pass.** RTT_THRESHOLD,
# HOST_DEGRADED, FLAP and — since Phase 3 — LOSS_THRESHOLD all fire zero times
# through the v2 path; if one reappears, the ratchet must notice rather than
# silently accept it. LOSS_THRESHOLD in particular was 2.574/day at Phase 2 and
# is now fully absorbed by the duplicate-outage suppression, so its return would
# mean that suppression stopped working.
TIER_PER_RULE_CEILING = {
    "HOST_DOWN": 0.44,
    "HOST_DOWN/resolved": 0.44,
}

# The fixture's own shape. Changing these changes every number above.
BASE_TS = 1_780_000_000
CYCLE_S = 600
SPAN_DAYS = 7
CYCLES = SPAN_DAYS * 86400 // CYCLE_S

GATEWAY_IP = "192.168.68.1"


# ── Fixture devices ──────────────────────────────────────────────────────────
# Every one carries inferred_role='infrastructure' — the pre-Phase-2 state the
# always-on catch-all wrote for 9 of 30 real rows. The legacy gate therefore
# admits nearly all of them; the tier gate has to reject them on identity and
# corroboration instead. That contrast is the thing being measured.
#
# mac, ip, hostname, vendor, device_type, stored_role
_DEVICES = [
    ("3c:64:cf:e0:27:02", GATEWAY_IP, "deco", "TP-Link (Deco mesh / RE series extenders)",
     "Mesh Network Node", "gateway"),
    ("f0:72:ea:51:d3:b8", "192.168.68.64", None, "Google Nest / Nest Wifi / Google Wifi Router",
     "Video Doorbell", None),                       # real mesh AP, misclassified, no role
    ("88:3d:24:21:77:66", "192.168.68.54", None, "Google", "Streaming Stick", "infrastructure"),
    ("5c:93:a2:5c:47:19", "192.168.68.69", "PS4-C8208A", "Liteon Technology Corporation",
     "Games Console", "infrastructure"),
    ("d8:3a:dd:de:11:a7", "192.168.68.67", "PINAS", "Microsoft", "Games Console", "infrastructure"),
    ("00:21:b7:a3:09:1a", "192.168.68.57", None, "Lexmark", "Unknown Device", "infrastructure"),
    ("02:a8:f1:3b:93:40", "192.168.68.61", None, "Unknown", "Unknown Device", "infrastructure"),
    ("6a:34:64:72:f8:f0", "192.168.68.56", None, "Unknown", "Unknown Device", "infrastructure"),
    ("01:00:5e:7f:ff:fa", "239.255.255.250", None, None, None, "infrastructure"),  # SSDP group
    ("3c:22:fb:8a:11:04", "192.168.68.72", "macbook", "Apple, Inc.", "Laptop", None),
]

# Hosts the tier gate must never admit, whatever a stored role claims:
# a multicast group is not an endpoint, and an unnameable privacy MAC is a real
# device the app cannot speak about (device_identity.IdentityClass).
_MUST_STAY_OUT_OF_SCOPE = {"239.255.255.250", "192.168.68.61", "192.168.68.56"}


def _state_for(ip: str, i: int):
    """(state, rtt_ms) for one device on cycle `i`. Pure and deterministic."""
    hour = (i * CYCLE_S) // 3600
    if ip == GATEWAY_IP:
        # Two real outages, ~1 h each — the signal that must survive.
        return ("DOWN", -1.0) if hour in (40, 100) else ("UP", 3.0)
    if ip == "192.168.68.64":                       # mesh AP, one outage
        return ("DOWN", -1.0) if hour == 70 else ("UP", 8.0)
    if ip == "192.168.68.54":
        # The Chromecast shape: mean RTT above the 150 ms DEGRADED threshold, so
        # it sits permanently on the boundary and churns state every few cycles.
        rtt = 140.0 + (i % 7) * 12.0
        return ("DEGRADED" if rtt > 150.0 else "UP", rtt)
    if ip in ("192.168.68.69", "192.168.68.67", "192.168.68.57"):
        # Devices that legitimately sleep — the level-triggered HOST_DOWN source.
        return ("DOWN", -1.0) if (hour // 8) % 3 == 0 else ("UP", 12.0)
    if ip in ("192.168.68.61", "192.168.68.56"):
        return ("DOWN", -1.0) if (hour // 12) % 5 == 0 else ("UP", 20.0)
    if ip == "239.255.255.250":
        return ("UP", 1.0)                          # answered like a host, as it did
    return ("DOWN", -1.0) if (hour // 6) % 7 == 0 else ("UP", 6.0)


@pytest.fixture(scope="module")
def noise_db(tmp_path_factory):
    """A deterministic NetSentinel.db carrying the reference network's defects."""
    path = tmp_path_factory.mktemp("noise") / "NetSentinel.db"
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)

    for mac, ip, hostname, vendor, dtype, role in _DEVICES:
        conn.execute(
            "INSERT INTO known_device (mac, ip, hostname, vendor, device_type, "
            "first_seen, last_seen, scan_count, ip_stability, inferred_role, alert_opt_in) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (mac, ip, hostname, vendor, dtype, BASE_TS,
             BASE_TS + CYCLES * CYCLE_S, 600, 0.98, role),
        )

    rows = []
    for i in range(CYCLES):
        ts = BASE_TS + i * CYCLE_S
        for mac, ip, *_ in _DEVICES:
            state, rtt = _state_for(ip, i)
            rows.append((ts, ip, mac, None, state, rtt))
    conn.executemany(
        "INSERT INTO device_state (ts, ip, mac, hostname, state, rtt_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)", rows,
    )

    # resolve_window() derives the span from device_event, so the window has to
    # be anchored there or every per-day rate is divided by the wrong number.
    conn.execute(
        "INSERT INTO device_event (ts, ip, mac, event_type, detail) VALUES (?, ?, ?, ?, ?)",
        (BASE_TS, GATEWAY_IP, "3c:64:cf:e0:27:02", "JOINED", None),
    )
    conn.execute(
        "INSERT INTO device_event (ts, ip, mac, event_type, detail) VALUES (?, ?, ?, ?, ?)",
        (BASE_TS + (CYCLES - 1) * CYCLE_S, GATEWAY_IP, "3c:64:cf:e0:27:02", "LEFT", None),
    )
    conn.commit()
    conn.close()

    ro = alert_replay.open_db(path)
    yield ro
    ro.close()


@pytest.fixture(scope="module")
def summary(noise_db):
    """The `build_summary()` dict for the fixture — one replay for every test."""
    since, span = alert_replay.resolve_window(noise_db, None)
    observed = alert_replay.observed_claims(noise_db, since)
    ungated, _ = alert_replay.replay(noise_db, since, None)
    gated, _ = alert_replay.replay(noise_db, since, alert_replay.scope_admits(noise_db))
    tiered, _ = alert_replay.replay(
        noise_db, since, alert_replay.tier_admits(noise_db, GATEWAY_IP),
        signal_quality_v2=True,
    )
    return alert_replay.build_summary(observed, ungated, gated, tiered, span)


# ── The ratchet ──────────────────────────────────────────────────────────────

def test_span_is_what_the_fixture_declares(summary):
    """Guards every rate below: a fixture whose window drifted would move all
    of them without any behaviour changing."""
    assert abs(summary["span_days"] - (SPAN_DAYS - CYCLE_S / 86400)) < 0.01


def test_tier_gated_claims_per_day_ratchet(summary):
    actual = summary["replay_tier_gated_per_day"]
    assert actual <= TIER_GATED_PER_DAY_CEILING, (
        f"Signal-quality ratchet — tier-gated claims rose to {actual}/day "
        f"(ceiling {TIER_GATED_PER_DAY_CEILING}).\n"
        f"Something re-admitted noise the tier gate was suppressing. Find it; "
        f"do not raise the ceiling.\n"
        f"Per rule: {summary['replay_tier_by_rule_type']}"
    )
    # Two-sided, per the test_qss_scoping.py convention: a large drop means the
    # ceiling has slack a future regression could hide in.
    assert actual > TIER_GATED_PER_DAY_CEILING * 0.75, (
        f"Tier-gated claims dropped to {actual}/day, well under the "
        f"{TIER_GATED_PER_DAY_CEILING} ceiling. Good — now lower "
        f"TIER_GATED_PER_DAY_CEILING to {actual} so the slack cannot hide a "
        f"later regression."
    )


def test_per_rule_claims_per_day_ratchet(summary):
    span = summary["span_days"]
    offenders = []
    for rule_type, count in summary["replay_tier_by_rule_type"].items():
        per_day = count / span
        ceiling = TIER_PER_RULE_CEILING.get(rule_type)
        if ceiling is None:
            offenders.append(
                f"{rule_type}: {per_day:.3f}/day — this rule type fired ZERO times "
                f"through the tier gate at baseline. Something re-admitted it."
            )
        elif per_day > ceiling:
            offenders.append(f"{rule_type}: {per_day:.3f}/day > ceiling {ceiling}")
    assert not offenders, (
        "Signal-quality per-rule ratchet breached:\n  " + "\n  ".join(offenders)
    )


def test_legacy_gate_stays_the_loud_one(summary):
    """Characterization + direction pin. The tier gate's entire justification is
    that it is dramatically quieter than the `inferred_role` boolean it
    replaces; if that inverts, the replacement stopped being worth its risk."""
    legacy = summary["replay_gated_per_day"]
    tiered = summary["replay_tier_gated_per_day"]
    assert legacy <= LEGACY_GATED_PER_DAY_CEILING
    assert tiered < legacy / 4, (
        f"The tier gate ({tiered}/day) is no longer decisively quieter than the "
        f"legacy role gate ({legacy}/day)."
    )


def test_tier_gate_never_admits_a_non_device_or_an_anonymous_one(noise_db):
    """The structural half of the ratchet. A rate can stay flat while the gate
    starts speaking about the wrong hosts, so identity is asserted directly —
    this is acceptance criterion 4 ("no ANONYMOUS-identity device holds
    gateway/infrastructure") expressed as a test."""
    admits = alert_replay.tier_admits(noise_db, GATEWAY_IP)
    wrongly_admitted = {h for h in _MUST_STAY_OUT_OF_SCOPE if admits.get(h)}
    assert not wrongly_admitted, (
        f"The tier gate admitted {sorted(wrongly_admitted)} — a multicast group "
        f"and/or an unnameable privacy MAC. Both carry a stale "
        f"inferred_role='infrastructure' in the fixture; the gate must reject "
        f"them on identity regardless."
    )


def test_the_gateway_and_the_mesh_ap_stay_in_scope(noise_db):
    """Over-suppression is the failure mode the program plan calls out. A gate
    that admits nothing would pass every ceiling above."""
    admits = alert_replay.tier_admits(noise_db, GATEWAY_IP)
    assert admits.get(GATEWAY_IP), "the gateway fell out of alert scope"
    assert admits.get("192.168.68.64"), (
        "the mesh AP fell out of alert scope — it is OUI-registered as Google "
        "Nest / Nest Wifi despite the classifier calling it a Video Doorbell"
    )
