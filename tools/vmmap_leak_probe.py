"""
vmmap_leak_probe.py -- short chaos run + periodic VMMap snapshots to localize
WHEN (and, via monkey.log's own action log, roughly WHAT action) an RSS jump
happens -- without gflags/UMDH and without a multi-hour soak.

Rationale: the wild-soak RSS leak breaches its mem-limit within 6-15 minutes
in every prior run, and growth is step-function (bursty), not smooth with
wall-clock time -- so a short run sampled every few minutes gives far better
time-resolution on the first jumps than one early/late snapshot pair taken
hours apart. VMMap categorizes committed memory into Heap (RtlAllocateHeap-
routed, UMDH-visible), Private Data (raw VirtualAlloc, UMDH-blind), and Image
(one-time DLL load noise) -- narrowing where a later UMDH run should even
look, without needing gflags +ust at all.

Usage:
    python tools/vmmap_leak_probe.py --duration 2400 --interval 180

Requires Sysinternals VMMap (winget install Microsoft.Sysinternals.Suite).
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_PID_RE = re.compile(r"PID:\s*(\d+)")
_LOG_LINE_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.(\d+)\s+\[(\w+)\s*\]\s+(.*)$")
_ACTION_MSG_RE = re.compile(r"^\[\s*(\d+)\]\s+(\S+)\s+(\S+)\s+name=(.+?)\s+->\s*(.*)$")


def _find_vmmap(explicit: Optional[str]) -> Path:
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        raise SystemExit(f"--vmmap path not found: {explicit}")
    which = shutil.which("vmmap64.exe") or shutil.which("vmmap.exe")
    if which:
        return Path(which)
    import os
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        for cand in Path(local, "Microsoft", "WinGet", "Packages").glob(
            "Microsoft.Sysinternals.Suite_*/vmmap64.exe"
        ):
            return cand
    raise SystemExit(
        "vmmap64.exe not found. Install: winget install --id "
        "Microsoft.Sysinternals.Suite --accept-source-agreements "
        "--accept-package-agreements"
    )


def _tail_for_pid(log_path: Path, seen_pos: int) -> tuple[Optional[int], int]:
    """Read new bytes since seen_pos; return (latest PID found, new file pos)."""
    if not log_path.exists():
        return None, seen_pos
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(seen_pos)
        chunk = f.read()
        new_pos = f.tell()
    pid = None
    for m in _PID_RE.finditer(chunk):
        pid = int(m.group(1))
    return pid, new_pos


def _snapshot(vmmap: Path, pid: int, out_csv: Path) -> bool:
    try:
        subprocess.run(
            [str(vmmap), "-p", str(pid), str(out_csv)],
            capture_output=True, timeout=60, check=False,
        )
    except Exception as exc:
        print(f"  [warn] vmmap snapshot failed: {exc}", file=sys.stderr)
        return False
    return out_csv.is_file() and out_csv.stat().st_size > 0


def _parse_snapshot(csv_path: Path) -> dict[str, float]:
    """Sum 'Total WS' (KB) per 'Type' row, returned in MB. Raises on schema mismatch.

    VMMap's `-p pid outfile.csv` export has two encoding/format quirks:
    (1) NOT UTF-8 -- the 0xA0 (NBSP) thousands separator is a raw cp1252 byte,
    invalid UTF-8 on its own (mangled to U+FFFD under errors="replace", which then
    fails the float() parse). (2) every line is terminated "\r\r\n" (a doubled CR),
    which Python's universal-newline splitting (any of \r/\n/\r\n) treats as two
    lines -- a real line plus a spurious blank one -- silently doubling the line
    count and breaking any "next blank line" boundary search. Read as raw bytes,
    strip every \r before decoding, and split on \n only, to sidestep this instead
    of fighting Python's newline auto-detection.

    The file also opens with a 2-3 line "Process:"/"PID:"/blank preamble before
    the real header row -- the real header is the first line whose first field is
    exactly "Type". The "Total" row is itself the sum of every other row and must
    be excluded or it double-counts.
    """
    raw = csv_path.read_bytes().replace(b"\r", b"")
    lines = raw.decode("cp1252", errors="replace").split("\n")
    header_idx = next(
        (i for i, line in enumerate(lines) if line.split(",", 1)[0].strip().strip('"') == "Type"),
        None,
    )
    if header_idx is None:
        raise ValueError(f"{csv_path.name}: could not find a 'Type' header row (unexpected VMMap CSV format)")
    # The summary-by-type table ends at the first blank line after the header. A much
    # larger per-region detail table follows ("Address","Type","Size",... -- note the
    # extra leading Address column), and reading into it under the summary header's
    # column names shifts every value one column left (hex addresses land in "Type").
    end_idx = next(
        (i for i in range(header_idx + 1, len(lines)) if not lines[i].strip()),
        len(lines),
    )
    reader = csv.DictReader(lines[header_idx:end_idx])
    if not reader.fieldnames:
        raise ValueError(f"{csv_path.name}: empty data section after header")
    type_col = next((c for c in reader.fieldnames if c.strip().lower() == "type"), None)
    ws_col = next((c for c in reader.fieldnames if "total ws" in c.strip().lower()), None)
    if type_col is None or ws_col is None:
        raise ValueError(
            f"{csv_path.name}: expected 'Type' + 'Total WS' columns, found {reader.fieldnames!r}"
        )
    totals: dict[str, float] = {}
    for row in reader:
        t = (row.get(type_col) or "Unknown").strip()
        if t == "Total":
            continue  # this row already IS the sum of every other row below
        raw = (row.get(ws_col) or "0").replace("\xa0", "").replace(",", "").strip()
        try:
            kb = float(raw)
        except ValueError:
            continue
        totals[t] = totals.get(t, 0.0) + kb / 1024.0  # KB -> MB
    return totals


@dataclass
class Snapshot:
    idx: int
    t_wall: float
    elapsed_s: float
    pid: int
    csv_path: Path
    totals: dict = field(default_factory=dict)
    parse_error: str = ""


def _secs_since_midnight(t_wall: float) -> float:
    lt = time.localtime(t_wall)
    frac = t_wall - int(t_wall)
    return lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec + frac


def _actions_in_window(log_path: Path, start_wall: float, end_wall: float) -> Counter:
    """Best-effort: count (ctype, action) pairs from monkey.log DEBUG action lines
    whose HH:MM:SS timestamp falls within [start_wall, end_wall). Ignores date --
    fine for a run that stays within one calendar day."""
    counts: Counter = Counter()
    start_s, end_s = _secs_since_midnight(start_wall), _secs_since_midnight(end_wall)
    if not log_path.exists():
        return counts
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _LOG_LINE_RE.match(line)
            if not m:
                continue
            h, mi, s, frac, level, msg = m.groups()
            if level != "DEBUG":
                continue
            ts = int(h) * 3600 + int(mi) * 60 + int(s) + int(frac) / (10 ** len(frac))
            if not (start_s <= ts < end_s):
                continue
            am = _ACTION_MSG_RE.match(msg)
            if am:
                _, ctype, action, name, _result = am.groups()
                counts[(ctype, action, name.strip())] += 1
    return counts


def _run_probe(args: argparse.Namespace) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir or f"test_output/vmmap_probe_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    snap_dir = out_dir / "snapshots"
    snap_dir.mkdir(exist_ok=True)

    vmmap = _find_vmmap(args.vmmap)
    print(f"Using vmmap: {vmmap}")

    cmd = [
        sys.executable, "tools/monkey_test.py", "--source",
        "--chaos", args.chaos, "--seed", str(args.seed),
        "--duration", str(args.duration), "--mem-limit", str(args.mem_limit),
        "--procdump", "--output-dir", str(out_dir),
    ]
    if args.connect_timeout is not None:
        cmd += ["--connect-timeout", str(args.connect_timeout)]

    print("Launching:", " ".join(cmd))
    proc = subprocess.Popen(cmd)

    log_path = out_dir / "monkey.log"
    pid: Optional[int] = None
    log_pos = 0
    print("Waiting for app PID in monkey.log...")
    wait_deadline = time.time() + max(120.0, (args.connect_timeout or 60.0) + 30.0)
    while pid is None and time.time() < wait_deadline:
        if proc.poll() is not None:
            raise SystemExit(
                f"monkey_test.py exited early (code {proc.returncode}) "
                f"before a PID appeared -- check {log_path}"
            )
        pid, log_pos = _tail_for_pid(log_path, log_pos)
        if pid is None:
            time.sleep(1.0)
    if pid is None:
        raise SystemExit(f"Timed out waiting for app PID in {log_path}")
    print(f"Tracking PID {pid}")

    snapshots: list[Snapshot] = []
    start = time.time()
    next_tick = start
    idx = 0
    run_deadline = start + args.duration + 120  # margin past the chaos run's own duration

    while True:
        new_pid, log_pos = _tail_for_pid(log_path, log_pos)
        if new_pid is not None and new_pid != pid:
            print(f"  [note] app restarted -- new PID {new_pid} (was {pid})")
            pid = new_pid

        now = time.time()
        csv_path = snap_dir / f"snap_{idx:03d}_t{int(now - start):05d}s.csv"
        ok = _snapshot(vmmap, pid, csv_path)
        snap = Snapshot(idx, now, now - start, pid, csv_path)
        if ok:
            try:
                snap.totals = _parse_snapshot(csv_path)
                grand = sum(snap.totals.values())
                print(f"  snapshot {idx:03d}  t+{now - start:6.0f}s  pid={pid}  total={grand:7.1f}MB")
            except ValueError as exc:
                snap.parse_error = str(exc)
                print(f"  [warn] snapshot {idx:03d} parse failed: {exc}")
        else:
            snap.parse_error = "vmmap snapshot command failed (pid may have exited)"
            print(f"  [warn] snapshot {idx:03d} at t+{now - start:.0f}s failed (pid {pid})")
        snapshots.append(snap)
        idx += 1

        if proc.poll() is not None or now >= run_deadline:
            break
        next_tick += args.interval
        end_wait = max(time.time(), next_tick)
        while time.time() < end_wait:
            if proc.poll() is not None:
                break
            time.sleep(min(2.0, end_wait - time.time()))

    if proc.poll() is None:
        print("Run still finishing -- waiting for monkey_test.py to exit...")
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            print("  [warn] monkey_test.py did not exit within 120s of duration limit")
    print(f"monkey_test.py exited with code {proc.returncode}")

    _write_report(out_dir, log_path, snapshots)
    return out_dir


def _write_report(out_dir: Path, log_path: Path, snapshots: list) -> None:
    good = [s for s in snapshots if not s.parse_error]
    lines: list[str] = []
    lines.append("# VMMap leak-probe report")
    lines.append("")
    lines.append(f"Snapshots taken: {len(snapshots)}  (parsed OK: {len(good)})")
    lines.append("")

    all_types = sorted({t for s in good for t in s.totals})
    header = ["t(s)", "pid", *all_types, "TOTAL"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for s in good:
        row = [f"{s.elapsed_s:.0f}", str(s.pid)]
        row += [f"{s.totals.get(t, 0.0):.1f}" for t in all_types]
        row.append(f"{sum(s.totals.values()):.1f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Deltas between consecutive parsed snapshots, ranked by biggest total jump.
    deltas = []
    for prev, curr in zip(good, good[1:]):
        d_total = sum(curr.totals.values()) - sum(prev.totals.values())
        d_by_type = {t: curr.totals.get(t, 0.0) - prev.totals.get(t, 0.0) for t in all_types}
        deltas.append((prev, curr, d_total, d_by_type))
    deltas.sort(key=lambda d: d[2], reverse=True)

    lines.append("## Windows ranked by total growth (biggest first)")
    lines.append("")
    for prev, curr, d_total, d_by_type in deltas:
        biggest_cat = max(d_by_type, key=lambda t: d_by_type[t]) if d_by_type else "?"
        lines.append(
            f"- t+{prev.elapsed_s:.0f}s -> t+{curr.elapsed_s:.0f}s: "
            f"**{d_total:+.1f}MB** total (driven by {biggest_cat} {d_by_type.get(biggest_cat, 0):+.1f}MB)"
        )
    lines.append("")

    if deltas:
        prev, curr, d_total, d_by_type = deltas[0]
        lines.append(f"## Actions during the biggest window (t+{prev.elapsed_s:.0f}s -> t+{curr.elapsed_s:.0f}s)")
        lines.append("")
        counts = _actions_in_window(log_path, prev.t_wall, curr.t_wall)
        if counts:
            for (ctype, action, name), n in counts.most_common(15):
                lines.append(f"- x{n}  {ctype} {action}  name={name}")
        else:
            lines.append("_No action-log lines matched this window (check monkey.log DEBUG level)._")
        lines.append("")

    parse_failures = [s for s in snapshots if s.parse_error]
    if parse_failures:
        lines.append("## Snapshot parse failures")
        lines.append("")
        for s in parse_failures:
            lines.append(f"- snapshot {s.idx:03d} (t+{s.elapsed_s:.0f}s): {s.parse_error}")
        lines.append("")

    report_path = out_dir / "REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written: {report_path}")
    print("\n".join(lines[: min(40, len(lines))]))


_SNAP_NAME_RE = re.compile(r"snap_(\d+)_t(\d+)s\.csv$")


def _reprocess(out_dir: Path) -> None:
    """Regenerate REPORT.md from an existing probe run's snapshots/ + monkey.log --
    no re-run needed, e.g. after fixing a parser bug against already-collected data."""
    snap_dir = out_dir / "snapshots"
    log_path = out_dir / "monkey.log"
    csvs = sorted(snap_dir.glob("snap_*.csv"))
    if not csvs:
        raise SystemExit(f"No snapshot CSVs found in {snap_dir}")
    pid, _ = _tail_for_pid(log_path, 0)
    snapshots: list[Snapshot] = []
    for p in csvs:
        m = _SNAP_NAME_RE.search(p.name)
        idx = int(m.group(1)) if m else len(snapshots)
        elapsed = float(m.group(2)) if m else 0.0
        t_wall = p.stat().st_mtime  # original wall-clock time is not persisted; mtime is a close proxy
        snap = Snapshot(idx, t_wall, elapsed, pid or 0, p)
        try:
            snap.totals = _parse_snapshot(p)
        except ValueError as exc:
            snap.parse_error = str(exc)
        snapshots.append(snap)
    _write_report(out_dir, log_path, snapshots)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--duration", type=float, default=2400, metavar="SECS",
                   help="Chaos run duration (default 2400 = 40 min)")
    p.add_argument("--interval", type=float, default=180, metavar="SECS",
                   help="Seconds between VMMap snapshots (default 180 = 3 min)")
    p.add_argument("--chaos", choices=["mild", "moderate", "wild"], default="wild")
    p.add_argument("--seed", type=int, default=99)
    p.add_argument("--mem-limit", type=int, default=1500, metavar="MB")
    p.add_argument("--connect-timeout", type=float, default=None, metavar="SECS",
                   help="Passthrough to monkey_test.py --connect-timeout")
    p.add_argument("--output-dir", default=None,
                   help="Default: test_output/vmmap_probe_<timestamp>")
    p.add_argument("--vmmap", default=None, help="Explicit path to vmmap64.exe")
    p.add_argument("--reprocess", default=None, metavar="DIR",
                   help="Skip launching a new run; regenerate REPORT.md from an existing "
                        "probe output directory's snapshots/ + monkey.log")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    if args.reprocess:
        _reprocess(Path(args.reprocess))
        return
    _run_probe(args)


if __name__ == "__main__":
    main()
