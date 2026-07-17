"""
NetSentinel — MetricStore Write Profiler
=========================================
Counts MetricStore write primitives (calls, transactions/commits, wall time)
grouped by SQL verb + table, across the three write paths the July 2026
data-wiring audit flagged as commit-heavy:

  (a) scan cycle      — DeviceTracker.process_scan() with 25 synthetic devices
  (b) availability    — AvailabilityMonitor.run_cycle() x10 over 5 targets
  (c) app traffic     — 25 per-flow record_app_traffic_sample() calls

Usage:
    python tools/write_profile.py

Output (example):
    ── (c) app traffic snapshot — 25 flows ────────────────
      INSERT app_traffic_sample      25 rows   25 commits    18.4 ms
      TOTAL                          25 rows   25 commits    18.4 ms

Dev-only — not shipped, not referenced by NetSentinel.spec. Every scenario runs
against a throwaway temp DB and a stubbed ping; no real network I/O happens.

Why this exists: it is the *baseline*. Phase B1 replaces the per-row commits in
paths (b) and (c) with batched transactions; the before/after commit counts from
this script go in that commit message. Numbers are only comparable when produced
by the same script on the same machine — re-run both sides, never compare against
a number pasted from an older session.

Instrumentation point: this patches MetricStore's private write primitives
(_execute_write and friends) at the class level, NOT the public record_*
methods. That is deliberate — a batch method added later routes through the same
primitive, so it shows up here as 1 commit for N rows with no edit to this file.
_PRIMITIVES lists every primitive by name and skips the ones that don't exist
yet, so B1's batch primitives are picked up automatically.

Three primitive shapes exist (Phase B1 added the last two, in
modules/metric_store_writes_batch.py):
  "single" — _execute_write(sql, params): 1 row, 1 commit.
  "many"   — _execute_write_many(sql, params_seq): N rows, ONE table, 1 commit.
  "multi"  — _execute_writes_many(statements): N rows across MULTIPLE tables,
             but still just ONE real transaction/commit (record_availability_cycle
             writes rtt_sample + device_state together). The commit is credited
             to the first statement's bucket only, so `commits` totals across all
             buckets still equal the real transaction count — crediting every
             bucket would double-count the same commit once per table.
"""
import os
import shutil
import sys
import tempfile
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.metric_store import MetricStore  # noqa: E402


# ── Write primitives to instrument ────────────────────────────────────────────
# (attribute name, shape). A primitive absent from the class is skipped, so
# this list may name primitives that do not exist yet. Shape is one of
# "single" / "many" / "multi" — see the module docstring.
_PRIMITIVES: Tuple[Tuple[str, str], ...] = (
    ("_execute_write", "single"),
    ("_execute_write_counted", "single"),
    ("_execute_write_many", "many"),      # Phase B1
    ("_execute_writes_many", "multi"),    # Phase B1
)


def _parse_sql(sql: str) -> Tuple[str, str]:
    """Return (VERB, table) for an INSERT/UPDATE/DELETE statement.

    Handles the forms MetricStore actually emits, including
    'INSERT OR REPLACE INTO x' and 'INSERT INTO x(a,b)' (no space before the
    paren). Anything unrecognised is reported verbatim rather than guessed at —
    a '?' table in the output means this parser needs a new case, not that the
    write vanished.
    """
    toks = sql.replace("(", " ( ").split()
    if not toks:
        return ("?", "?")
    verb = toks[0].upper()
    upper = [t.upper() for t in toks]
    if verb == "INSERT" and "INTO" in upper:
        i = upper.index("INTO")
        if i + 1 < len(toks):
            return (verb, toks[i + 1])
    elif verb == "UPDATE" and len(toks) > 1:
        return (verb, toks[1])
    elif verb == "DELETE" and "FROM" in upper:
        i = upper.index("FROM")
        if i + 1 < len(toks):
            return (verb, toks[i + 1])
    return (verb, "?")


class WriteProfiler:
    """Counts calls/rows/wall-time through MetricStore's write primitives.

    One commit == one primitive call: every primitive wraps its statement in its
    own transaction (that is finding F1 — the thing being measured). So
    `commits` is simply the call count, and `rows` diverges from it only once a
    batch primitive lands.
    """

    def __init__(self) -> None:
        # (verb, table) -> [rows, commits, total_seconds]
        self.stats: Dict[Tuple[str, str], List[float]] = {}
        self._originals: Dict[str, Callable] = {}

    def _record(self, sql: str, seconds: float, rows: int, count_commit: bool = True) -> None:
        entry = self.stats.setdefault(_parse_sql(sql), [0, 0, 0.0])
        entry[0] += rows
        if count_commit:
            entry[1] += 1
        entry[2] += seconds

    def install(self) -> None:
        for name, shape in _PRIMITIVES:
            orig = getattr(MetricStore, name, None)
            if orig is None:
                continue  # primitive not present in this revision — see _PRIMITIVES
            self._originals[name] = orig
            setattr(MetricStore, name, self._wrap(orig, shape))

    def uninstall(self) -> None:
        for name, orig in self._originals.items():
            setattr(MetricStore, name, orig)
        self._originals.clear()

    def _wrap(self, orig: Callable, shape: str) -> Callable:
        profiler = self

        if shape == "multi":
            def _patched_multi(store_self, statements: List[Tuple[str, Sequence[tuple]]]):
                t0 = time.perf_counter()
                try:
                    return orig(store_self, statements)
                finally:
                    elapsed = time.perf_counter() - t0
                    non_empty = [(sql, rows) for sql, rows in statements if rows]
                    if non_empty:
                        share = elapsed / len(non_empty)
                        for i, (sql, rows) in enumerate(non_empty):
                            # ONE real transaction covers every statement in
                            # this call — credit the commit to the first
                            # bucket only, so `commits` totals across all
                            # buckets still equal the real transaction count.
                            profiler._record(sql, share, len(rows), count_commit=(i == 0))

            return _patched_multi

        def _patched(store_self, sql, params):
            t0 = time.perf_counter()
            try:
                return orig(store_self, sql, params)
            finally:
                # Timed/counted even when the write raises: a failed write still
                # spent the wall time and still opened a transaction.
                rows = len(params) if (shape == "many" and params is not None) else 1
                profiler._record(sql, time.perf_counter() - t0, rows)

        return _patched

    # ── Reporting ─────────────────────────────────────────────────────────────

    def totals(self) -> Tuple[int, int, float]:
        rows = sum(int(v[0]) for v in self.stats.values())
        commits = sum(int(v[1]) for v in self.stats.values())
        seconds = sum(v[2] for v in self.stats.values())
        return rows, commits, seconds

    def report(self, title: str) -> None:
        print(f"\n-- {title} " + "-" * max(0, 58 - len(title)))
        if not self.stats:
            print("  (no writes)")
            return
        for (verb, table), (rows, commits, seconds) in sorted(
            self.stats.items(), key=lambda kv: -kv[1][1]
        ):
            print(
                f"  {verb:<7} {table:<24} {int(rows):>5} rows "
                f"{int(commits):>5} commits {seconds * 1000:>8.1f} ms"
            )
        rows, commits, seconds = self.totals()
        print(
            f"  {'TOTAL':<32} {rows:>5} rows "
            f"{commits:>5} commits {seconds * 1000:>8.1f} ms"
        )


# ── Synthetic inputs ──────────────────────────────────────────────────────────

def fake_devices(n: int = 25) -> List[dict]:
    """N scan-shaped device dicts, as DeviceTracker._normalise() consumes them.

    Vendor/device_type are real-looking strings (never 'Unknown'), so the
    service-mapper branch inside process_scan() runs — the placeholder values
    are dropped by _normalise and would silently skip that work.
    """
    vendors = ["Cisco", "Apple", "Samsung", "TP-Link", "HP"]
    types = ["Router", "Laptop", "Phone", "Smart TV", "Printer"]
    return [
        {
            "mac": f"aa:bb:cc:00:{i // 256:02x}:{i % 256:02x}",
            "ip": f"192.168.1.{i + 2}",
            "hostname": f"device-{i:02d}.local",
            "vendor": vendors[i % len(vendors)],
            "device_type": types[i % len(types)],
        }
        for i in range(n)
    ]


def fake_samples(n: int = 25) -> List[dict]:
    """N app-traffic flow dicts, shaped as ui/tabs.py::_on_app_traffic_sample
    receives them from AppTrafficPage.traffic_sample_ready."""
    categories = ["Streaming", "Web", "Gaming", "Cloud Sync", "Social"]
    return [
        {
            "mac": f"aa:bb:cc:00:00:{i % 256:02x}",
            "label": f"device-{i:02d}",
            "category": categories[i % len(categories)],
            "app": "",
            "bytes_total": 1_000_000 + i * 4_096,
            "window_s": 10.0,
            "cdn": None,
        }
        for i in range(n)
    ]


# ── Scenarios ─────────────────────────────────────────────────────────────────

def profile_scan_cycle(store: MetricStore, n_devices: int = 25) -> WriteProfiler:
    """(a) One DeviceTracker.process_scan() over n synthetic devices."""
    from modules.device_tracker import DeviceTracker

    tracker = DeviceTracker(store)
    devices = fake_devices(n_devices)
    prof = WriteProfiler()
    prof.install()
    try:
        tracker.process_scan(devices)
    finally:
        prof.uninstall()
    return prof


def profile_availability(
    store: MetricStore, n_targets: int = 5, rounds: int = 10
) -> WriteProfiler:
    """(b) `rounds` AvailabilityMonitor cycles over n stubbed targets.

    The ping is stubbed deterministically (no ICMP, no network, no root): every
    host is a steady ~12 ms UP, except host index 0, which goes DOWN for rounds
    5-6 and recovers on 7. That flip is what exercises the record_device_event
    write — a fully steady run costs 2 commits/host/cycle and would under-report
    the real path, which the audit measured at 2-3.
    """
    from modules import availability_monitor as _am
    from modules.availability_monitor import AvailabilityMonitor, TargetConfig

    targets = [
        TargetConfig(
            host=f"192.168.1.{i + 1}",
            label=f"target-{i}",
            mac=f"aa:bb:cc:00:00:{i:02x}",
            hostname=f"target-{i}.local",
        )
        for i in range(n_targets)
    ]

    state = {"round": 0}

    def _stub_ping(host: str) -> float:
        if host == targets[0].host and state["round"] in (5, 6):
            return -1.0     # DOWN
        return 12.5         # UP

    _orig_ping = _am._ping
    _am._ping = _stub_ping
    try:
        monitor = AvailabilityMonitor(store, targets=targets, interval_s=60)
        prof = WriteProfiler()
        prof.install()
        try:
            for r in range(rounds):
                state["round"] = r
                monitor.run_cycle()
        finally:
            prof.uninstall()
    finally:
        _am._ping = _orig_ping
    return prof


def profile_app_traffic(store: MetricStore, n_flows: int = 25) -> WriteProfiler:
    """(c) One app-traffic snapshot — mirrors ui/tabs.py::_on_app_traffic_sample
    (runs on the GUI thread), which since Phase B1 batches the whole snapshot
    into one record_app_traffic_samples() call instead of a per-sample loop (F2)."""
    samples = fake_samples(n_flows)
    prof = WriteProfiler()
    prof.install()
    try:
        store.record_app_traffic_samples(samples)
    finally:
        prof.uninstall()
    return prof


# ── Entry point ───────────────────────────────────────────────────────────────

def run_all(db_dir: Optional[str] = None) -> Dict[str, WriteProfiler]:
    """Run all three scenarios against throwaway stores. Returns name -> profiler."""
    tmp = db_dir or tempfile.mkdtemp(prefix="ns_write_profile_")
    results: Dict[str, WriteProfiler] = {}
    try:
        for name, fn in (
            ("(a) scan cycle - 25 devices, DeviceTracker.process_scan", profile_scan_cycle),
            ("(b) availability - 5 targets x 10 cycles", profile_availability),
            ("(c) app traffic snapshot - 25 flows", profile_app_traffic),
        ):
            store = MetricStore(db_path=os.path.join(tmp, f"{len(results)}.db"))
            try:
                results[name] = fn(store)
            finally:
                store.close()
    finally:
        if db_dir is None:
            shutil.rmtree(tmp, ignore_errors=True)
    return results


def main() -> int:
    print("NetSentinel -- MetricStore write profile (baseline, Phase B0)")
    print(f"python {sys.version.split()[0]}  |  sqlite3 write primitives instrumented")
    results = run_all()
    for name, prof in results.items():
        prof.report(name)
    print("\n-- summary " + "-" * 48)
    for name, prof in results.items():
        rows, commits, seconds = prof.totals()
        print(f"  {name:<52} {commits:>4} commits  {seconds * 1000:>7.1f} ms")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
