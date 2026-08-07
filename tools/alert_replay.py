"""
alert_replay.py — measure how much NetSentinel *claims* versus how much is real.

Phase 0 of the Signal Quality Program. This tool changes no behaviour; it exists
so every later threshold change is measurable instead of guessed, and so a
regression in signal quality is detectable.

It reports three things from a real NetSentinel.db, read-only:

  OBSERVED    what the app actually surfaced — device_event and alert_fired
              counts, normalised to claims/day. This is the number the user
              experiences as noise.

  HOTSPOTS    which devices produce it. A single MAC emitting 37 LEFT events, or
              one IP producing 306 state transitions, is a defect signature, not
              a busy network.

  REPLAY      what the alert engine *would* fire if the rules were enabled,
              reconstructed from the real device_state history and run through
              the real AlertEngine. Reported through three gates side by side —
              ungated, the legacy `inferred_role` boolean
              (MetricStore.is_device_alert_in_scope), and the "v2 path" the
              experimental/signal_quality_v2 flag selects — so the difference
              isolates exactly how much volume each admits.

              The v2 column is everything the flag turns on, not the tier gate
              alone: from Phase 3 that is the Phase 2 device_importance tier
              floor **plus** edge-triggered HOST_DOWN and duplicate-outage
              suppression. Its JSON keys keep their `replay_tier_*` names so
              recorded baselines stay comparable across phases.

Usage
─────
    python tools/alert_replay.py                    # default DB, full history
    python tools/alert_replay.py --days 13          # last 13 days only
    python tools/alert_replay.py --db path\\to.db    # explicit database
    python tools/alert_replay.py --json out.json    # machine-readable summary
    python tools/alert_replay.py --gateway 10.0.0.1 # real evidence for the tier gate

The database is opened with mode=ro and is never written to, so this is safe to
run against a live database while the app is running (WAL allows concurrent
readers).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.alert_engine import AlertEngine  # noqa: E402
from modules.evidence import DEFAULT_MIN_CONSECUTIVE  # noqa: E402
from modules.utils import get_app_data_dir  # noqa: E402

# Event types that represent a per-device availability transition. These are the
# ones that flood: a device that sleeps nightly emits DOWN + RECOVERED forever.
_STATE_EVENT_TYPES = ("DOWN", "DEGRADED", "RECOVERED", "UP")

# Roles that MetricStore.is_device_alert_in_scope() treats as always-in-scope.
_IN_SCOPE_ROLES = ("gateway", "infrastructure")


# ── Database access ──────────────────────────────────────────────────────────

def default_db_path() -> Path:
    """The installed app's database location (RULE 23 app-data dir)."""
    return get_app_data_dir() / "NetSentinel.db"


def open_db(path: Path) -> sqlite3.Connection:
    """Open `path` strictly read-only. Raises FileNotFoundError if absent."""
    if not path.exists():
        raise FileNotFoundError(f"No database at {path}")
    uri = "file:" + str(path).replace("\\", "/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def resolve_window(conn: sqlite3.Connection, days: Optional[float]) -> Tuple[int, float]:
    """Return (since_ts, span_days) for the requested window.

    `days=None` means the full recorded history. span_days is the actual span
    covered by the data, which is what claim rates must be divided by — using
    the requested window instead would understate the rate whenever the database
    holds less history than asked for.
    """
    bounds = conn.execute(
        "SELECT MIN(ts), MAX(ts) FROM device_event"
    ).fetchone()
    lo, hi = (bounds[0], bounds[1]) if bounds else (None, None)
    if lo is None or hi is None:
        return 0, 0.0
    since = lo if days is None else max(lo, int(hi - days * 86400))
    span_days = max((hi - since) / 86400.0, 1.0 / 24)  # floor at 1 h
    return since, span_days


# ── Observed claims ──────────────────────────────────────────────────────────

def observed_claims(conn: sqlite3.Connection, since_ts: int) -> Dict[str, Counter]:
    """Count what the app actually surfaced, by source and type."""
    out: Dict[str, Counter] = {"device_event": Counter(), "alert_fired": Counter()}

    for row in conn.execute(
        "SELECT event_type, COUNT(*) AS n FROM device_event WHERE ts >= ? GROUP BY 1",
        (since_ts,),
    ):
        out["device_event"][row["event_type"]] = row["n"]

    if _table_exists(conn, "alert_fired"):
        for row in conn.execute(
            "SELECT rule_type, severity, COUNT(*) AS n FROM alert_fired "
            "WHERE ts >= ? GROUP BY 1, 2",
            (since_ts,),
        ):
            label = f"{row['rule_type'] or '(none)'}/{row['severity']}"
            out["alert_fired"][label] = row["n"]

    return out


def noise_hotspots(
    conn: sqlite3.Connection, since_ts: int, limit: int = 8
) -> Dict[str, List[Tuple[str, int, str]]]:
    """Identify the devices responsible for the bulk of the event volume.

    Returns {section: [(identifier, count, description), ...]}.
    """
    identities = _identity_map(conn)

    def describe(key: str) -> str:
        info = identities.get(key)
        if not info:
            return "(no known_device row)"
        bits = [b for b in (info["hostname"], info["vendor"], info["device_type"]) if b]
        role = info["inferred_role"]
        if role:
            bits.append(f"role={role}")
        return " / ".join(bits) if bits else "(unnamed)"

    left = [
        (r["mac"] or "(no mac)", r["n"], describe(r["mac"] or ""))
        for r in conn.execute(
            "SELECT mac, COUNT(*) AS n FROM device_event "
            "WHERE ts >= ? AND event_type = 'LEFT' GROUP BY 1 ORDER BY n DESC LIMIT ?",
            (since_ts, limit),
        )
    ]

    placeholders = ",".join("?" * len(_STATE_EVENT_TYPES))
    churn = [
        (r["ip"], r["n"], describe(r["ip"]))
        for r in conn.execute(
            f"SELECT ip, COUNT(*) AS n FROM device_event "
            f"WHERE ts >= ? AND event_type IN ({placeholders}) "
            f"GROUP BY 1 ORDER BY n DESC LIMIT ?",
            (since_ts, *_STATE_EVENT_TYPES, limit),
        )
    ]

    return {"left_repeats": left, "state_churn": churn}


def _identity_map(conn: sqlite3.Connection) -> Dict[str, sqlite3.Row]:
    """known_device rows keyed by BOTH mac and ip, mirroring how the scope
    checker looks devices up (`WHERE ip = ? OR mac = ?`)."""
    out: Dict[str, sqlite3.Row] = {}
    if not _table_exists(conn, "known_device"):
        return out
    for row in conn.execute(
        "SELECT mac, ip, hostname, vendor, device_type, inferred_role, alert_opt_in "
        "FROM known_device"
    ):
        if row["mac"]:
            out[row["mac"]] = row
        if row["ip"]:
            out[row["ip"]] = row
    return out


def scope_admits(conn: sqlite3.Connection) -> Dict[str, bool]:
    """Simulate MetricStore.is_device_alert_in_scope() for every known identifier.

    Mirrors metric_store_writes_device.py: in scope iff the inferred role is
    gateway/infrastructure, or the user explicitly opted the device in. A device
    with no row is out of scope.

    Like the real gate, the IP key answers across every MAC at that address —
    several devices routinely share one IP, and alerts are keyed by IP.

    This is the LEGACY gate — the one measured at ~52 % admission. See
    tier_admits() for its Phase 2 replacement.
    """
    out: Dict[str, bool] = {}
    for row in conn.execute(
        "SELECT mac, ip, inferred_role, alert_opt_in FROM known_device"
    ):
        admitted = row["inferred_role"] in _IN_SCOPE_ROLES or bool(row["alert_opt_in"])
        if row["mac"]:
            out[row["mac"]] = admitted
        if row["ip"]:
            out[row["ip"]] = out.get(row["ip"], False) or admitted
    return out


def tier_admits(
    conn: sqlite3.Connection, gateway_ip: Optional[str] = None
) -> Dict[str, bool]:
    """Simulate the Signal Quality Phase 2 tier gate for every known identifier.

    In scope iff the device's `device_importance.Tier` reaches INFRASTRUCTURE —
    the tier equivalent of the legacy gateway/infrastructure role check.

    **`inferred_role` is recomputed here, not read.** The stored column is
    precisely what Phase 2 replaces (wrong for 8 of 13 assignments on the
    reference network), and the app's own one-time migration rewrites it at
    startup. Reading it back would measure the old defect and report it as the
    new gate's volume.

    `gateway_ip` supplies the corroborating evidence `ui/scan_wiring.py` passes
    at runtime. Without it, inference falls back to the .1/.254 heuristic — so a
    replay of a network whose gateway sits elsewhere understates coverage.
    """
    from modules.device_importance import Tier, classify_importance
    from modules.device_stability import RoleEvidence, infer_role

    evidence = RoleEvidence.from_network({"gateway": gateway_ip} if gateway_ip else None)
    # mac_randomized (schema v21) and friends arrive by migration, not in the
    # base DDL, so a database predating them must still replay rather than
    # crash — the harness is for diagnosing old installs as much as new ones.
    wanted = (
        "mac", "ip", "hostname", "vendor", "device_type", "custom_name",
        "is_pinned", "mac_randomized", "scan_count", "ip_stability", "alert_opt_in",
    )
    present = {r[1] for r in conn.execute("PRAGMA table_info(known_device)")}
    cols = [c for c in wanted if c in present]
    out: Dict[str, bool] = {}
    for raw in conn.execute(f"SELECT {', '.join(cols)} FROM known_device"):
        row = dict(raw)
        scan_count = int(row.get("scan_count") or 0)
        stability = float(row.get("ip_stability") or 0.0)
        role = infer_role(
            ip=row.get("ip"),
            device_type=row.get("device_type"),
            custom_name=row.get("custom_name"),
            scan_count=scan_count,
            ip_stability=stability,
            mac=row.get("mac"),
            hostname=row.get("hostname"),
            vendor=row.get("vendor"),
            evidence=evidence,
        )
        tier = classify_importance(
            mac=row.get("mac"), ip=row.get("ip"), hostname=row.get("hostname"),
            vendor=row.get("vendor"), device_type=row.get("device_type"),
            inferred_role=role,
            scan_count=scan_count,
            ip_stability=stability,
            custom_name=row.get("custom_name"),
            is_pinned=bool(row.get("is_pinned")),
            mac_randomized=bool(row.get("mac_randomized")),
            alert_opt_in=bool(row.get("alert_opt_in")),
        ).tier
        admitted = tier >= Tier.INFRASTRUCTURE
        if row.get("mac"):
            out[row["mac"]] = admitted
        # OR-merge on the IP key: several MACs routinely share one address (the
        # reference network has three at 192.168.68.64, one of them the mesh
        # AP), and alerts are keyed by IP. Last-write-wins would let row order
        # decide whether that address is alertable.
        if row.get("ip"):
            out[row["ip"]] = out.get(row["ip"], False) or admitted
    return out


# ── Replay ───────────────────────────────────────────────────────────────────

def reconstruct_cycles(
    conn: sqlite3.Connection, since_ts: int
) -> Iterator[Dict[str, Any]]:
    """Rebuild AvailabilityMonitor cycle results from recorded device_state rows.

    record_availability_cycle() writes one row per device per cycle sharing a
    single `ts`, so grouping by exact timestamp reproduces the original cycle
    boundaries without needing to guess an interval.

    Yields dicts in the shape AlertEngine.evaluate_cycle() expects:
        {"ts": int, "states": {host: state}, "rtts": {host: rtt_ms}}
    """
    current_ts: Optional[int] = None
    states: Dict[str, str] = {}
    rtts: Dict[str, float] = {}

    for row in conn.execute(
        "SELECT ts, ip, state, rtt_ms FROM device_state WHERE ts >= ? ORDER BY ts",
        (since_ts,),
    ):
        if current_ts is not None and row["ts"] != current_ts:
            yield {"ts": current_ts, "states": states, "rtts": rtts}
            states, rtts = {}, {}
        current_ts = row["ts"]
        host = row["ip"]
        states[host] = row["state"]
        rtts[host] = row["rtt_ms"] if row["rtt_ms"] is not None else -1.0

    if current_ts is not None:
        yield {"ts": current_ts, "states": states, "rtts": rtts}


def _all_rules_enabled_engine(
    scope_checker: Optional[Dict[str, bool]] = None,
    signal_quality_v2: bool = False,
) -> AlertEngine:
    """An AlertEngine carrying the shipped default rules, all force-enabled.

    The defaults ship enabled=False, so a faithful replay of the app as-shipped
    fires nothing. Enabling them all measures the ceiling: what a user who turned
    on everything they believe they want would actually receive.

    `signal_quality_v2` turns on the Phase 3 behaviour the experimental flag
    selects — edge-triggered HOST_DOWN and duplicate-outage suppression — so the
    v2 column measures the whole path a user would actually get, not the tier
    gate in isolation.
    """
    engine = AlertEngine(store=None)
    rules = engine.get_rules()
    for rule in rules:
        rule.enabled = True
    engine.set_rules(rules)
    if scope_checker is not None:
        engine.set_alert_scope_checker(lambda host: scope_checker.get(host, False))
    if signal_quality_v2:
        engine.set_availability_edge_trigger(DEFAULT_MIN_CONSECUTIVE)
        engine.set_duplicate_outage_suppression(True)
    return engine


def replay(
    conn: sqlite3.Connection,
    since_ts: int,
    scope_checker: Optional[Dict[str, bool]] = None,
    signal_quality_v2: bool = False,
) -> Tuple[Counter, Counter]:
    """Run the real AlertEngine over reconstructed history.

    Returns (by_rule_type, by_host) counters of alerts that would have fired.
    Resolution alerts (severity HEALTHY) are counted separately under a
    "<TYPE>/resolved" key — they are claims too, and a rule that resolves as
    often as it fires is a flapping rule, not a working one.

    **This measures the alert layer only.** Phase 3b's monitor-side changes
    (per-device DEGRADED thresholds, DOWN confirmation) act when `device_state`
    is *written*, and replay reads rows that were already written under the old
    classification — so their effect shows up in the OBSERVED table of a future
    run, never in this one. A replay is a lower bound on Phase 3's total effect.
    """
    engine = _all_rules_enabled_engine(scope_checker, signal_quality_v2)
    by_type: Counter = Counter()
    by_host: Counter = Counter()

    for cycle in reconstruct_cycles(conn, since_ts):
        for alert in engine.evaluate_cycle(cycle):
            key = alert.rule_type + ("/resolved" if alert.is_resolution else "")
            by_type[key] += 1
            by_host[alert.host] += 1

    return by_type, by_host


# ── Reporting ────────────────────────────────────────────────────────────────

def _rate(n: int, span_days: float) -> str:
    return f"{n / span_days:>8.1f}"


def _section(title: str) -> None:
    # ASCII only: this prints to a Windows console, which defaults to cp1252 and
    # raises UnicodeEncodeError on box-drawing characters and em dashes.
    print()
    print(title)
    print("-" * max(len(title), 62))


def format_report(
    observed: Dict[str, Counter],
    hotspots: Dict[str, List[Tuple[str, int, str]]],
    ungated: Counter,
    gated: Counter,
    tiered: Counter,
    span_days: float,
) -> None:
    _section("OBSERVED CLAIMS - what the app actually surfaced")
    print(f"{'source / type':<38}{'total':>8}{'per day':>10}")
    total_observed = 0
    for source, counts in observed.items():
        if not counts:
            continue
        for name, n in counts.most_common():
            total_observed += n
            print(f"  {source}: {name:<26}{n:>8}{_rate(n, span_days)}")
    print(f"{'  TOTAL':<38}{total_observed:>8}{_rate(total_observed, span_days)}")

    _section("HOTSPOTS - which devices produce the volume")
    print("Repeated LEFT events per MAC (one absence should emit exactly one):")
    for ident, n, desc in hotspots["left_repeats"]:
        print(f"  {ident:<20}{n:>5}   {desc}")
    print()
    print("Availability state churn per IP:")
    for ident, n, desc in hotspots["state_churn"]:
        print(f"  {ident:<20}{n:>5}   {desc}")

    _section("REPLAY - what the alert engine would fire if rules were enabled")
    print(
        f"{'rule_type':<32}{'ungated':>10}{'role gate':>12}"
        f"{'v2 path':>12}{'per day':>10}"
    )
    all_keys = sorted(
        set(ungated) | set(gated) | set(tiered), key=lambda k: -ungated.get(k, 0)
    )
    for key in all_keys:
        u, g, t = ungated.get(key, 0), gated.get(key, 0), tiered.get(key, 0)
        print(f"  {key:<30}{u:>10}{g:>12}{t:>12}{_rate(t, span_days)}")
    tu, tg, tt = sum(ungated.values()), sum(gated.values()), sum(tiered.values())
    print(f"  {'TOTAL':<30}{tu:>10}{tg:>12}{tt:>12}{_rate(tt, span_days)}")

    _section("SUMMARY")
    print(f"  History span                       {span_days:>8.1f} days")
    print(f"  Observed claims/day                {total_observed / span_days:>8.1f}")
    print(f"  Replayed alerts/day (ungated)      {tu / span_days:>8.1f}")
    print(f"  Replayed alerts/day (role gate)    {tg / span_days:>8.1f}")
    print(f"  Replayed alerts/day (v2 path)      {tt / span_days:>8.1f}")
    if tu:
        print(
            f"  Role gate admits                   {100.0 * tg / tu:>8.1f}% "
            f"of candidate alerts"
        )
        print(
            f"  v2 path admits                     {100.0 * tt / tu:>8.1f}% "
            f"of candidate alerts"
        )


def build_summary(
    observed: Dict[str, Counter],
    ungated: Counter,
    gated: Counter,
    tiered: Counter,
    span_days: float,
) -> Dict[str, Any]:
    """Machine-readable summary — the shape the noise ratchet test consumes."""
    total_observed = sum(sum(c.values()) for c in observed.values())
    return {
        "span_days": round(span_days, 3),
        "observed_total": total_observed,
        "observed_per_day": round(total_observed / span_days, 3),
        "observed_by_type": {
            f"{src}.{name}": n
            for src, counts in observed.items()
            for name, n in counts.items()
        },
        "replay_gated_total": sum(gated.values()),
        "replay_ungated_total": sum(ungated.values()),
        "replay_gated_per_day": round(sum(gated.values()) / span_days, 3),
        "replay_by_rule_type": dict(gated),
        "replay_tier_gated_total": sum(tiered.values()),
        "replay_tier_gated_per_day": round(sum(tiered.values()) / span_days, 3),
        "replay_tier_by_rule_type": dict(tiered),
    }


# ── Entry point ──────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure NetSentinel's claim volume against a real database."
    )
    parser.add_argument("--db", type=Path, default=None, help="path to NetSentinel.db")
    parser.add_argument(
        "--days", type=float, default=None, help="only replay the last N days"
    )
    parser.add_argument(
        "--json", type=Path, default=None, help="write a machine-readable summary here"
    )
    parser.add_argument(
        "--gateway",
        default=None,
        help="the network's real gateway IP — corroborating evidence for the "
             "tier gate, matching what ui/scan_wiring.py supplies at runtime",
    )
    args = parser.parse_args(argv)

    db_path = args.db or default_db_path()
    try:
        conn = open_db(db_path)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        since_ts, span_days = resolve_window(conn, args.days)
        if span_days <= 0:
            print("error: database contains no device_event history", file=sys.stderr)
            return 2

        print(f"database : {db_path}")
        print(f"window   : {span_days:.1f} days of history")

        observed = observed_claims(conn, since_ts)
        hotspots = noise_hotspots(conn, since_ts)
        ungated, _ = replay(conn, since_ts, scope_checker=None)
        gated, _ = replay(conn, since_ts, scope_checker=scope_admits(conn))
        tiered, _ = replay(
            conn, since_ts, scope_checker=tier_admits(conn, args.gateway),
            signal_quality_v2=True,
        )

        format_report(observed, hotspots, ungated, gated, tiered, span_days)

        if args.json:
            summary = build_summary(observed, ungated, gated, tiered, span_days)
            args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(f"\nwrote {args.json}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
