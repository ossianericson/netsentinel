"""
identity_replay.py -- measure how often NetSentinel changes its mind about what
a device IS, versus how confidently it can say so.

Phase 0 of the Device Identity & Classification Program (the successor to the
Signal Quality Program -- see tools/alert_replay.py, same method). This tool
changes no behaviour; it exists so every later phase's fix is measured against
a real "before" number instead of a hunch.

It reports, read-only, from a real NetSentinel.db:

  CLASS-CHANGE CHURN   device_events rows where event_type='class_changed' --
                       total, the share that are pure no-ops (old_value ==
                       new_value), and the rate per day / per device-day.

  HOTSPOTS             which MACs produce the churn, and how many distinct
                       device_type values each has cycled through.

  DISAGREEMENT         devices where known_device.device_type (what the
                       Devices page renders) does not match the newest
                       class_changed event for that MAC (what the audit trail
                       says actually happened last).

  CONFIDENCE COVERAGE  known_device rows with confidence > 0, out of every row
                       that has a vendor or hostname to be confident about.

  IDENTITY             classify_identity() breakdown of the known_device table
                       -- how many rows are a nameable device, an unnameable
                       one, or not a device at all (multicast/malformed MAC).

  IP COLLISIONS        IP addresses currently claimed by more than one MAC in
                       known_device -- the confound that breaks IP-keyed
                       enrichment matching.

Usage
-----
    python tools/identity_replay.py                    # default DB, full history
    python tools/identity_replay.py --days 30          # last 30 days only
    python tools/identity_replay.py --db path\\to.db    # explicit database
    python tools/identity_replay.py --json out.json    # machine-readable summary

The database is opened with mode=ro and is never written to, so this is safe to
run against a live database while the app is running (WAL allows concurrent
readers).
"""
from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.device_identity import IdentityClass, classify_identity  # noqa: E402
from modules.utils import get_app_data_dir  # noqa: E402

_TS_FMT = "%Y-%m-%d %H:%M:%S"


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


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _parse_ts(s: str) -> datetime.datetime:
    return datetime.datetime.strptime(s, _TS_FMT)


def _fmt_ts(dt: datetime.datetime) -> str:
    return dt.strftime(_TS_FMT)


def resolve_window(conn: sqlite3.Connection, days: Optional[float]) -> Tuple[str, float]:
    """Return (since_ts_string, span_days) for the requested window.

    device_events.ts is a TEXT datetime (`datetime('now')` default), not an
    epoch int like alert_replay's device_event table -- so the window bound is
    a formatted string, comparable lexicographically because the format is
    fixed-width and zero-padded. `days=None` means the full recorded history.
    span_days is the actual span covered by the data: using the requested
    window instead would understate the rate whenever the database holds less
    history than asked for.
    """
    bounds = conn.execute("SELECT MIN(ts), MAX(ts) FROM device_events").fetchone()
    lo, hi = (bounds[0], bounds[1]) if bounds else (None, None)
    if lo is None or hi is None:
        return "", 0.0
    lo_dt, hi_dt = _parse_ts(lo), _parse_ts(hi)
    since_dt = lo_dt if days is None else max(lo_dt, hi_dt - datetime.timedelta(days=days))
    span_days = max((hi_dt - since_dt).total_seconds() / 86400.0, 1.0 / 24)  # floor at 1h
    return _fmt_ts(since_dt), span_days


# ── known_device inventory ───────────────────────────────────────────────────

def _known_device_rows(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    cols = _columns(conn, "known_device")
    wanted = ["mac", "ip", "hostname", "vendor", "device_type"]
    if "confidence" in cols:
        wanted.append("confidence")
    return list(conn.execute(f"SELECT {', '.join(wanted)} FROM known_device"))


def device_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM known_device").fetchone()[0]


def identity_breakdown(conn: sqlite3.Connection) -> Dict[str, int]:
    """classify_identity() verdict counts across the known_device inventory."""
    out = {c.value: 0 for c in IdentityClass}
    for row in _known_device_rows(conn):
        ident = classify_identity(row["mac"], row["hostname"], row["vendor"], row["ip"])
        out[ident.identity_class.value] += 1
    return out


def confidence_coverage(conn: sqlite3.Connection) -> Dict[str, int]:
    """known_device rows with confidence > 0, out of rows with a vendor or
    hostname to be confident about (matches acceptance criterion 4's
    denominator -- a row with neither has nothing for a classifier to score)."""
    if "confidence" not in _columns(conn, "known_device"):
        return {"eligible": 0, "covered": 0}
    eligible = 0
    covered = 0
    for row in _known_device_rows(conn):
        if not ((row["vendor"] or "").strip() or (row["hostname"] or "").strip()):
            continue
        eligible += 1
        if (row["confidence"] or 0.0) > 0.0:
            covered += 1
    return {"eligible": eligible, "covered": covered}


def ip_collisions(conn: sqlite3.Connection, limit: int = 8) -> List[Tuple[str, int]]:
    """IPs currently claimed by more than one MAC in known_device, worst first."""
    rows = conn.execute(
        "SELECT ip, COUNT(DISTINCT mac) AS n FROM known_device "
        "WHERE ip IS NOT NULL AND ip != '' GROUP BY ip HAVING n > 1 "
        "ORDER BY n DESC LIMIT ?",
        (limit,),
    )
    return [(r["ip"], r["n"]) for r in rows]


# ── class_changed churn ──────────────────────────────────────────────────────

def class_change_totals(conn: sqlite3.Connection, since_ts: str) -> Dict[str, int]:
    total = conn.execute(
        "SELECT COUNT(*) FROM device_events WHERE event_type='class_changed' AND ts >= ?",
        (since_ts,),
    ).fetchone()[0]
    noop = conn.execute(
        "SELECT COUNT(*) FROM device_events WHERE event_type='class_changed' "
        "AND ts >= ? AND old_value = new_value",
        (since_ts,),
    ).fetchone()[0]
    return {"total": total, "noop": noop}


def hotspots(conn: sqlite3.Connection, since_ts: str, limit: int = 8) -> List[sqlite3.Row]:
    """Which MACs produce class_changed churn, and how many distinct
    device_type values each has cycled through -- worst churn first."""
    return list(conn.execute(
        "SELECT mac, COUNT(*) AS n, COUNT(DISTINCT new_value) AS distinct_types "
        "FROM device_events WHERE event_type='class_changed' AND ts >= ? "
        "GROUP BY mac ORDER BY n DESC LIMIT ?",
        (since_ts, limit),
    ))


def max_distinct_types(conn: sqlite3.Connection, since_ts: str) -> int:
    """The worst distinct-device_type count for any single MAC -- acceptance
    criterion 3 ("no device assigned more than 2 distinct types in 30 days")."""
    row = conn.execute(
        "SELECT MAX(n) FROM (SELECT COUNT(DISTINCT new_value) AS n FROM device_events "
        "WHERE event_type='class_changed' AND ts >= ? GROUP BY mac)",
        (since_ts,),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _describe(row: sqlite3.Row) -> str:
    bits = [b for b in (row["hostname"], row["vendor"], row["device_type"]) if b]
    return " / ".join(bits) if bits else "(unnamed)"


def disagreement(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Devices where known_device.device_type disagrees with the newest
    class_changed event recorded for that MAC -- the "Lexmark is Print Server
    in the audit trail but Unknown Device on the Devices page" defect.

    Newest is by rowid (id), not ts: two events can share a timestamp (TEXT
    datetime has 1-second resolution), and id is strictly insertion-ordered.
    """
    newest = {
        r["mac"]: r["new_value"]
        for r in conn.execute(
            "SELECT de.mac, de.new_value FROM device_events de "
            "JOIN (SELECT mac, MAX(id) AS max_id FROM device_events "
            "      WHERE event_type='class_changed' GROUP BY mac) latest "
            "ON de.mac = latest.mac AND de.id = latest.max_id"
        )
    }
    mismatches: List[Dict[str, str]] = []
    compared = 0
    for row in _known_device_rows(conn):
        mac = row["mac"]
        if mac not in newest:
            continue
        compared += 1
        newest_type = newest[mac] or ""
        current_type = row["device_type"] or ""
        if newest_type != current_type:
            mismatches.append({
                "mac": mac,
                "known_device.device_type": current_type or "(blank)",
                "newest_class_changed": newest_type or "(blank)",
                "description": _describe(row),
            })
    return {"compared": compared, "mismatches": mismatches}


# ── Reporting ────────────────────────────────────────────────────────────────

def _section(title: str) -> None:
    # ASCII only: this prints to a Windows console, which defaults to cp1252
    # and raises UnicodeEncodeError on box-drawing characters and em dashes.
    print()
    print(title)
    print("-" * max(len(title), 62))


def format_report(
    class_totals: Dict[str, int],
    hot: List[sqlite3.Row],
    disagree: Dict[str, Any],
    confidence: Dict[str, int],
    identity: Dict[str, int],
    collisions: List[Tuple[str, int]],
    n_devices: int,
    span_days: float,
) -> None:
    total, noop = class_totals["total"], class_totals["noop"]
    noop_share = (noop / total * 100.0) if total else 0.0
    per_day = total / span_days
    per_device_day = per_day / n_devices if n_devices else 0.0

    _section("CLASS-CHANGE CHURN")
    print(f"  device_events 'class_changed' rows       {total:>8}")
    print(f"  ...of which old_value == new_value (no-op){noop:>7}  ({noop_share:.1f}%)")
    print(f"  per day                                   {per_day:>8.1f}")
    print(f"  per device-day (/{n_devices} devices)          {per_device_day:>8.3f}")

    _section("HOTSPOTS - which MACs produce the churn")
    print(f"{'mac':<20}{'events':>8}{'distinct types':>16}")
    for row in hot:
        print(f"  {row['mac']:<18}{row['n']:>8}{row['distinct_types']:>16}")

    _section("DISAGREEMENT - known_device.device_type vs newest class_changed")
    compared, mismatches = disagree["compared"], disagree["mismatches"]
    agree = compared - len(mismatches)
    agree_pct = (agree / compared * 100.0) if compared else 100.0
    print(f"  Agree: {agree}/{compared} ({agree_pct:.1f}%)")
    for m in mismatches[:10]:
        print(
            f"    {m['mac']:<18} known_device={m['known_device.device_type']!r:<22} "
            f"newest_event={m['newest_class_changed']!r:<22} {m['description']}"
        )

    _section("CONFIDENCE COVERAGE")
    eligible, covered = confidence["eligible"], confidence["covered"]
    cov_pct = (covered / eligible * 100.0) if eligible else 0.0
    print(f"  confidence > 0: {covered}/{eligible} rows with a vendor or hostname ({cov_pct:.1f}%)")

    _section("IDENTITY - classify_identity() breakdown")
    for cls in IdentityClass:
        print(f"  {cls.value:<16}{identity.get(cls.value, 0):>6}")

    _section("IP COLLISIONS - IPs claimed by more than one MAC")
    if not collisions:
        print("  none")
    for ip, n in collisions:
        print(f"  {ip:<18}{n} MACs")

    _section("SUMMARY")
    print(f"  History span                       {span_days:>8.1f} days")
    print(f"  known_device rows                  {n_devices:>8}")
    print(f"  class_changed / device-day          {per_device_day:>8.3f}")
    print(f"  class_changed no-op share           {noop_share:>7.1f}%")
    print(f"  confidence coverage                 {cov_pct:>7.1f}%")
    print(f"  device_type agreement               {agree_pct:>7.1f}%")
    print(f"  IP collisions                       {len(collisions):>8}")


def build_summary(
    class_totals: Dict[str, int],
    hot: List[sqlite3.Row],
    disagree: Dict[str, Any],
    confidence: Dict[str, int],
    identity: Dict[str, int],
    collisions: List[Tuple[str, int]],
    n_devices: int,
    span_days: float,
    max_types: int,
) -> Dict[str, Any]:
    """Machine-readable summary -- the shape a future ratchet test consumes."""
    total, noop = class_totals["total"], class_totals["noop"]
    noop_share = (noop / total) if total else 0.0
    per_day = total / span_days
    per_device_day = per_day / n_devices if n_devices else 0.0
    eligible, covered = confidence["eligible"], confidence["covered"]
    compared = disagree["compared"]
    agree = compared - len(disagree["mismatches"])
    return {
        "span_days": round(span_days, 3),
        "device_count": n_devices,
        "class_changed_total": total,
        "class_changed_noop_total": noop,
        "class_changed_noop_share": round(noop_share, 4),
        "class_changed_per_day": round(per_day, 3),
        "class_changed_per_device_day": round(per_device_day, 4),
        "max_distinct_types_by_mac": max_types,
        "hotspots": [
            {"mac": r["mac"], "events": r["n"], "distinct_types": r["distinct_types"]}
            for r in hot
        ],
        "device_type_agreement_total": compared,
        "device_type_agreement_count": agree,
        "device_type_agreement_share": round(agree / compared, 4) if compared else 1.0,
        "device_type_mismatches": disagree["mismatches"],
        "confidence_eligible": eligible,
        "confidence_covered": covered,
        "confidence_coverage_share": round(covered / eligible, 4) if eligible else 0.0,
        "identity_breakdown": identity,
        "ip_collision_count": len(collisions),
        "ip_collisions": [{"ip": ip, "mac_count": n} for ip, n in collisions],
    }


# ── Entry point ──────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure NetSentinel's device-identity churn against a real database."
    )
    parser.add_argument("--db", type=Path, default=None, help="path to NetSentinel.db")
    parser.add_argument(
        "--days", type=float, default=None, help="only measure the last N days"
    )
    parser.add_argument(
        "--json", type=Path, default=None, help="write a machine-readable summary here"
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
            print("error: database contains no device_events history", file=sys.stderr)
            return 2

        print(f"database : {db_path}")
        print(f"window   : {span_days:.1f} days of history")

        class_totals = class_change_totals(conn, since_ts)
        hot = hotspots(conn, since_ts)
        max_types = max_distinct_types(conn, since_ts)
        disagree = disagreement(conn)
        confidence = confidence_coverage(conn)
        identity = identity_breakdown(conn)
        collisions = ip_collisions(conn)
        n_devices = device_count(conn)

        format_report(
            class_totals, hot, disagree, confidence, identity, collisions,
            n_devices, span_days,
        )

        if args.json:
            summary = build_summary(
                class_totals, hot, disagree, confidence, identity, collisions,
                n_devices, span_days, max_types,
            )
            args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(f"\nwrote {args.json}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
