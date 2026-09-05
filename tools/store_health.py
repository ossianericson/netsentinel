"""tools/store_health.py — pull Microsoft Store failure data and diff it release-over-release.

**Why this exists.** v2.2.8's regional hardening was driven by 13 Store failures across
en-AU, en-US, sv-SE, es-BO and hi-IN, and its own commit message says the honest thing:
attribution to those specific events is *unproven*. Every fix was a hypothesis fitted to
a market code and a count, because that is all Partner Center gives. This tool turns
"we think we fixed it" into a before/after measurement.

**What it can and cannot tell you.** Partner Center will never give a usable stack for
this app: it is a PyInstaller onefile of a Python program, there are no PDBs, and even
with them WER would resolve ``python3xx.dll`` / ``Qt6Core.dll`` frames rather than
``scan_enrichment.py:412``. CAB downloads are additionally restricted to failures on
Windows Insider builds. So this tier answers *where, how many, which version, which OS*
and nothing else. The Python-level cause has to come from the app's own crash net.

**The 30-day window is the point.** ``failurehits`` only serves the last 30 days, so data
not captured is gone permanently. Run this on a schedule, not when you happen to wonder.

Usage
-----
    # From the API (needs the one-time Entra setup below)
    python tools/store_health.py --days 30

    # From a Failures CSV downloaded from Partner Center (no cloud setup at all)
    python tools/store_health.py --csv ~/Downloads/failures.csv

    # Compare against the previous snapshot rather than the newest one
    python tools/store_health.py --days 30 --baseline docs/internal/store-health-2026-08.json

One-time Partner Center setup (only a human can do this)
--------------------------------------------------------
1. Associate a Microsoft Entra directory with the Partner Center account.
2. Account settings -> Users -> add an Entra application, role **Manager**.
3. Generate a key; note the tenant ID, client ID and key.
4. Store them (RULE 22-A — never QSettings, never a file)::

       python -c "import keyring; keyring.set_password('NetSentinel','store/tenant_id','...')"
       python -c "import keyring; keyring.set_password('NetSentinel','store/client_id','...')"
       python -c "import keyring; keyring.set_password('NetSentinel','store/client_secret','...')"

   ``NETSENTINEL_STORE_TENANT_ID`` / ``_CLIENT_ID`` / ``_CLIENT_SECRET`` override the
   keychain, for CI where no keychain exists.
"""
from __future__ import annotations

import dataclasses
from typing import Any, List

#: Store ID for NetSentinel — the same product id used by store_update_url().
DEFAULT_APPLICATION_ID = "9NZ124C7HJWS"


@dataclasses.dataclass(frozen=True)
class FailureRow:
    """One aggregated failure bucket, as returned by ``failurehits``.

    ``device_count``/``event_count`` are floats, not ints: the API returns
    already-averaged values for the chosen aggregation level, so a bucket can legitimately
    read 1.05 events. Rounding on ingest would quietly misreport small numbers, which is
    the whole signal at these volumes.
    """

    date: str
    market: str
    package_version: str
    event_type: str
    failure_name: str
    os_version: str
    device_count: float
    event_count: float


def parse_failure_hits(payload: dict) -> List[FailureRow]:
    """Turn a ``failurehits`` response body into rows."""
    rows: List[FailureRow] = []
    for item in payload.get("Value") or []:
        rows.append(_row_from_api(item))
    return rows


def _row_from_api(item: dict) -> FailureRow:
    def _num(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    return FailureRow(
        date=str(item.get("date") or ""),
        market=str(item.get("market") or ""),
        package_version=str(item.get("packageVersion") or ""),
        event_type=str(item.get("eventType") or ""),
        failure_name=str(item.get("failureName") or ""),
        os_version=str(item.get("osVersion") or ""),
        device_count=_num(item.get("deviceCount")),
        event_count=_num(item.get("eventCount")),
    )


@dataclasses.dataclass
class Bucket:
    """Aggregated totals for one (market, package_version, event_type) key."""

    events: float = 0.0
    devices: float = 0.0
    failure_names: set = dataclasses.field(default_factory=set)


def summarize(rows: List[FailureRow]) -> "dict[tuple, Bucket]":
    """Group rows by (market, package_version, event_type).

    Package version is part of the key on purpose: collapsing versions would hide
    exactly the signal this tool exists to show — whether a release actually removed a
    market's failures, or merely coincided with fewer installs.
    """
    out: dict[tuple, Bucket] = {}
    for r in rows:
        key = (r.market, r.package_version, r.event_type)
        bucket = out.setdefault(key, Bucket())
        bucket.events += r.event_count
        bucket.devices += r.device_count
        if r.failure_name:
            bucket.failure_names.add(r.failure_name)
    return out


def _norm_header(name: str) -> str:
    """Normalise a CSV column name: lowercase, no spaces/underscores."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


#: CSV column -> FailureRow field. Partner Center has renamed these before, so matching
#: is case- and space-insensitive rather than exact.
_CSV_FIELDS = {
    "date": "date",
    "market": "market",
    "packageversion": "package_version",
    "eventtype": "event_type",
    "failurename": "failure_name",
    "osversion": "os_version",
    "devicecount": "device_count",
    "eventcount": "event_count",
}


def parse_failures_csv(text: str) -> List[FailureRow]:
    """Parse a Failures CSV exported from Partner Center.

    The manual path: Partner Center -> Health -> Failures -> download icon. It needs no
    Entra application, no tenant association and no secret, so the analysis half of this
    tool works even if the API setup is never done.
    """
    import csv
    import io

    reader = csv.DictReader(io.StringIO(text))
    rows: List[FailureRow] = []
    for raw in reader:
        item = {}
        for key, value in raw.items():
            if key is None:
                continue
            field = _CSV_FIELDS.get(_norm_header(key))
            if field:
                item[field] = value
        rows.append(
            FailureRow(
                date=str(item.get("date") or ""),
                market=str(item.get("market") or ""),
                package_version=str(item.get("package_version") or ""),
                event_type=str(item.get("event_type") or ""),
                failure_name=str(item.get("failure_name") or ""),
                os_version=str(item.get("os_version") or ""),
                device_count=_to_float(item.get("device_count")),
                event_count=_to_float(item.get("event_count")),
            )
        )
    return rows


def _to_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


@dataclasses.dataclass
class Diff:
    """What changed between two snapshots.

    ``resolved`` is the answer to "did the release fix it"; ``new`` is the answer to
    "did it break something else" — a release that trades one market's crashes for
    another's is not a win, and only showing ``resolved`` would call it one.
    """

    resolved: "dict[tuple, float]" = dataclasses.field(default_factory=dict)
    new: "dict[tuple, float]" = dataclasses.field(default_factory=dict)
    changed: "dict[tuple, float]" = dataclasses.field(default_factory=dict)


def diff(before: "dict[tuple, Bucket]", after: "dict[tuple, Bucket]") -> Diff:
    """Compare two summaries. ``changed`` values are after-minus-before event deltas."""
    out = Diff()
    for key, bucket in before.items():
        if key not in after:
            out.resolved[key] = bucket.events
        elif after[key].events != bucket.events:
            out.changed[key] = after[key].events - bucket.events
    for key, bucket in after.items():
        if key not in before:
            out.new[key] = bucket.events
    return out


def snapshot_from_rows(rows: List[FailureRow]) -> dict:
    """A JSON-serialisable snapshot, to be the baseline for the next run.

    Rows, not the summary: the 30-day window means a snapshot is the only durable copy
    of that data, and re-grouping later is free while un-grouping is impossible.
    """
    return {
        "schema": 1,
        "rows": [dataclasses.asdict(r) for r in rows],
    }


def rows_from_snapshot(snapshot: dict) -> List[FailureRow]:
    return [FailureRow(**r) for r in snapshot.get("rows") or []]


def snapshot_filename(now) -> str:
    """Snapshot name for ``now``. Second-resolution, and lexically sortable.

    Date alone collides when the tool is run twice in a day, and the second run would
    overwrite the very baseline it had just compared against. The API window is 30 days,
    so a snapshot is the only durable copy of data that expires — losing one is exactly
    the failure this tool exists to prevent.

    **Microseconds, not seconds.** Two CLI runs were observed completing inside the same
    wall-clock second on a warm interpreter with small inputs, which collided at second
    resolution and destroyed the baseline. Fixed-width ISO basic format keeps lexical
    order equal to chronological order, which the baseline picker relies on when it
    sorts by name — so no zero-padding may be dropped.
    """
    return "store-health-" + now.strftime("%Y-%m-%dT%H%M%S.%f") + ".json"


def _fmt(value: float) -> str:
    """Trim the API's float counts without hiding a genuine fraction."""
    return f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.2f}"


def render_markdown(
    summary: "dict[tuple, Bucket]",
    generated: str,
    delta: "Diff | None" = None,
) -> str:
    """Render the report written under docs/internal/."""
    lines = [
        "# Microsoft Store — failure report",
        "",
        f"Generated {generated}. Source: Partner Center `failurehits` (30-day window).",
        "",
        "Counts are Partner Center's own aggregates and can be fractional. This tier",
        "answers *where / how many / which version*; it cannot give a Python traceback",
        "for a PyInstaller build — that has to come from the app's own crash net.",
        "",
    ]

    if not summary:
        lines += [
            "**No failures reported in this window.**",
            "",
            "Treat that as good news only if installs were non-zero — an empty report and",
            "an unused app look identical here.",
            "",
        ]
    else:
        lines += [
            "## Failures by market × version",
            "",
            "| Market | Package version | Type | Events | Devices |",
            "|---|---|---|---:|---:|",
        ]
        for (market, version, event_type), bucket in sorted(
            summary.items(), key=lambda kv: (-kv[1].events, kv[0])
        ):
            lines.append(
                f"| {market} | {version} | {event_type} | "
                f"{_fmt(bucket.events)} | {_fmt(bucket.devices)} |"
            )
        lines.append("")

    if delta is not None:
        lines += ["## Change since the baseline", ""]
        for title, mapping in (
            ("Resolved (present before, gone now)", delta.resolved),
            ("New (absent before)", delta.new),
            ("Changed", delta.changed),
        ):
            lines.append(f"**{title}**")
            lines.append("")
            if not mapping:
                lines += ["_none_", ""]
                continue
            for key, value in sorted(mapping.items(), key=lambda kv: kv[0]):
                market, version, event_type = key
                lines.append(
                    f"- `{market}` {version} {event_type} — {_fmt(value)} "
                    f"event{'' if abs(value) == 1 else 's'}"
                )
            lines.append("")

    return "\n".join(lines)


# ── Live API ─────────────────────────────────────────────────────────────────
# Deliberately thin. Everything above is pure and tested; this half is a urllib
# wrapper against a live authenticated endpoint, where a fake would assert the shape
# of the fake rather than anything about Partner Center.

_TOKEN_HOST = "https://login.microsoftonline.com"
_ANALYTICS = "https://manage.devcenter.microsoft.com/v1.0/my/analytics"
_RESOURCE = "https://manage.devcenter.microsoft.com"

_SECRET_KEYS = {
    "tenant_id": "store/tenant_id",
    "client_id": "store/client_id",
    "client_secret": "store/client_secret",
}


def _credential(name: str) -> str:
    """Read one credential: env var first (for CI), then the OS keychain (RULE 22-A)."""
    import os

    env = os.environ.get("NETSENTINEL_STORE_" + name.upper())
    if env:
        return env
    try:
        import keyring

        return keyring.get_password("NetSentinel", _SECRET_KEYS[name]) or ""
    except Exception:
        return ""


def get_access_token() -> str:
    """Client-credentials grant. The token is valid for 60 minutes."""
    import urllib.parse
    import urllib.request

    tenant = _credential("tenant_id")
    client = _credential("client_id")
    secret = _credential("client_secret")
    missing = [n for n, v in (("tenant_id", tenant), ("client_id", client),
                              ("client_secret", secret)) if not v]
    if missing:
        raise SystemExit(
            "Missing Store API credentials: " + ", ".join(missing) + ".\n"
            "Complete the one-time Partner Center setup in this file's docstring, or "
            "use --csv to analyse a downloaded Failures export instead."
        )

    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client,
        "client_secret": secret,
        "resource": _RESOURCE,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{_TOKEN_HOST}/{urllib.parse.quote(tenant)}/oauth2/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed https host
        import json

        return json.loads(resp.read().decode("utf-8"))["access_token"]


def fetch_failure_hits(token: str, application_id: str, days: int) -> List[FailureRow]:
    """Page through ``failurehits`` for the last ``days`` days.

    ``groupby`` is what makes the response answer the market question at all — without
    it the API returns totals with no dimensions to slice by.
    """
    import datetime as _dt
    import json
    import urllib.parse
    import urllib.request

    end = _dt.date.today()
    start = end - _dt.timedelta(days=max(1, min(days, 30)))

    query = urllib.parse.urlencode({
        "applicationId": application_id,
        "startDate": start.strftime("%m/%d/%Y"),
        "endDate": end.strftime("%m/%d/%Y"),
        "top": 10000,
        "skip": 0,
        "aggregationLevel": "day",
        "groupby": ",".join([
            "failureName", "failureHash", "symbol", "osVersion",
            "eventType", "market", "packageName", "packageVersion",
        ]),
    })

    url = f"{_ANALYTICS}/failurehits?{query}"
    rows: List[FailureRow] = []
    seen_pages = 0
    while url and seen_pages < 50:      # bounded: a paging bug must not loop forever
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https host
            payload = json.loads(resp.read().decode("utf-8"))
        rows.extend(parse_failure_hits(payload))
        nxt = payload.get("@nextLink")
        url = f"{_ANALYTICS}/{nxt}" if nxt else ""
        seen_pages += 1
    return rows


def main(argv: "list[str] | None" = None) -> int:
    import argparse
    import datetime as _dt
    import json
    import pathlib as _pl

    ap = argparse.ArgumentParser(
        description="Pull Microsoft Store failure data and diff it against a baseline.",
    )
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--days", type=int, default=30,
                     help="days to fetch from the API (max 30 — the API's own window)")
    src.add_argument("--csv", type=_pl.Path,
                     help="analyse a Failures CSV exported from Partner Center instead")
    ap.add_argument("--application-id", default=DEFAULT_APPLICATION_ID)
    ap.add_argument("--baseline", type=_pl.Path,
                    help="snapshot JSON to diff against (default: the newest one found)")
    ap.add_argument("--out-dir", type=_pl.Path,
                    default=_pl.Path(__file__).resolve().parents[1] / "docs" / "internal")
    args = ap.parse_args(argv)

    if args.csv:
        rows = parse_failures_csv(args.csv.read_text(encoding="utf-8", errors="replace"))
    else:
        rows = fetch_failure_hits(get_access_token(), args.application_id, args.days)

    summary = summarize(rows)

    baseline_path = args.baseline
    if baseline_path is None:
        snaps = sorted(args.out_dir.glob("store-health-*.json"))
        baseline_path = snaps[-1] if snaps else None

    delta = None
    if baseline_path and baseline_path.exists():
        previous = rows_from_snapshot(
            json.loads(baseline_path.read_text(encoding="utf-8"))
        )
        delta = diff(summarize(previous), summary)

    now = _dt.datetime.now()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    snap_name = snapshot_filename(now)
    (args.out_dir / snap_name).write_text(
        json.dumps(snapshot_from_rows(rows), indent=2), encoding="utf-8"
    )
    report = render_markdown(summary, generated=now.date().isoformat(), delta=delta)
    report_path = args.out_dir / snap_name.replace(".json", ".md")
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nWritten: {report_path}")
    if baseline_path:
        print(f"Compared against: {baseline_path}")
    else:
        print("No baseline found — this run becomes the baseline for the next one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
