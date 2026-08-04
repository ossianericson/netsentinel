r"""
umdh_leak_probe.py -- targeted UMDH snapshot pair around the STEADY-STATE
Heap growth window, automating the wait/snapshot timing that caused two
documented false starts in earlier manual attempts (ScheduleWakeup not firing
reliably for a long wait; a health-monitor restart silently invalidating a
snap1/snap2 pairing taken from two different process lifetimes).

Why this specific window: a prior VMMap probe (tools/vmmap_leak_probe.py) on
this same wild-chaos profile found the RSS growth has three distinct phases --
a startup ramp (0-3min, every category jumps at once), a clean steady
Heap-only climb (3min-36min, ~+220MB/hour, UMDH-visible), and a late one-time
Image-only jump (last ~3min, looked like a one-time DLL load, not a leak).
The default --settle/--window bracket exactly the steady-Heap phase, so the
UMDH diff isn't diluted by the startup ramp or a late one-off.

Prerequisite: +ust must be armed on python.exe. Two ways --

  (a) RECOMMENDED -- let this script own it. Run from an ELEVATED prompt with
      --manage-ust: it arms +ust at start and ALWAYS reverts on the way out,
      including on Ctrl+C, an aborted snapshot, or a diff timeout.
          python tools/umdh_leak_probe.py --manage-ust

  (b) Manual (default; the script only QUERIES in this mode). gflags.exe is
      usually not on PATH, so use the full path with PowerShell's & operator:
          & "C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\gflags.exe" /i python.exe +ust
      ...and revert it YOURSELF when done, from an elevated prompt:
          & "C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\gflags.exe" /i python.exe -ust

WHY THIS MATTERS ENOUGH TO AUTOMATE: +ust is process-wide, survives reboots,
and is invisible at runtime -- nothing looks wrong, the numbers are just false.
Left armed by accident on 2026-08-03 it took app startup from 5.8s to 99s and
the pytest suite from 9min to 68min, produced two "failures" that were pure
artifact, and invalidated a full day of RSS/perf conclusions before anyone
thought to check the flag. tools/monkey_test.py and tools/run_all_monkey_tests.ps1
now refuse to start while it is armed, so a leftover flag costs one aborted
command instead of an overnight chaos run.

Usage (defaults: settle=300s, window=1200s, duration auto-computed with a 300s
buffer past snap2 so it can never race the run's own duration-triggered quit):
    python tools/umdh_leak_probe.py
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from vmmap_leak_probe import _tail_for_pid  # noqa: E402 -- reuse the proven PID-tail logic

_DEBUGGERS_DIR = Path(r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64")


def _find_debugger_tool(name: str, explicit: Optional[str]) -> Path:
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        raise SystemExit(f"path not found: {explicit}")
    which = shutil.which(name)
    if which:
        return Path(which)
    default = _DEBUGGERS_DIR / name
    if default.is_file():
        return default
    raise SystemExit(
        f"{name} not found. Install the Windows SDK/WDK debugging tools "
        f"(https://developer.microsoft.com/windows/downloads/windows-sdk/), or pass its path explicitly."
    )


def _check_ust_enabled(gflags: Path) -> bool:
    """Query (never modify) whether +ust is active for python.exe. Returns True only on
    a confirmed positive match -- any query failure or ambiguous output is treated as
    NOT confirmed, since launching a 25+ minute run with tracing off wastes the run."""
    try:
        out = subprocess.run([str(gflags), "/i", "python.exe"], capture_output=True,
                              text=True, timeout=15, check=False)
        combined = (out.stdout or "") + (out.stderr or "")
    except Exception as exc:
        print(f"  [warn] could not query gflags state ({exc})")
        return False
    if "ust" in combined.lower():
        print("  gflags +ust confirmed active for python.exe.")
        return True
    print("  gflags does NOT report +ust active for python.exe.")
    return False


def _set_ust(gflags: Path, enable: bool) -> bool:
    """Arm (+ust) or clear (-ust) stack-trace tracing for python.exe. Needs elevation."""
    flag = "+ust" if enable else "-ust"
    try:
        r = subprocess.run([str(gflags), "/i", "python.exe", flag],
                            capture_output=True, text=True, timeout=30, check=False)
    except Exception as exc:
        print(f"  [ERROR] gflags {flag} failed to run ({exc})")
        return False
    if r.returncode != 0:
        print(f"  [ERROR] gflags {flag} exited {r.returncode}: {(r.stderr or r.stdout).strip()}")
        return False
    return True


def _restore_ust(gflags: Path, managed: bool) -> None:
    """Always runs, on every exit path. Reverts +ust when we own it; otherwise
    prints the exact command, because a flag left armed silently falsifies every
    later measurement on this machine (see module docstring)."""
    if managed:
        print("\n--manage-ust: reverting +ust for python.exe...")
        if _set_ust(gflags, False):
            print("  +ust cleared. GlobalFlag is back to normal.")
            return
        print("  [WARNING] automatic revert FAILED -- clear it by hand, elevated:")
    else:
        print("\n" + "=" * 70)
        print("IMPORTANT -- +ust is still armed. Revert it now (elevated prompt):")
    print(f'    & "{gflags}" /i python.exe -ust')
    print("Until you do, every RSS/timing number on this machine -- including any")
    print("chaos run -- is an artifact. tools/monkey_test.py will refuse to start.")
    print("=" * 70)


def _run_diff(umdh: Path, snap1: Path, snap2: Path, diff: Path, timeout: float) -> None:
    """Run `umdh snap1 snap2 -f:diff`. With _NT_SYMBOL_PATH pointed at Microsoft's
    internet symbol server, resolving symbols for every loaded DLL (Qt6, matplotlib,
    numpy, scipy, dozens of system DLLs -- 50+ modules is typical for this app) can
    take much longer than a short timeout on a first run before the local symbol
    cache is warm; a killed subprocess leaves a truncated, garbage diff.txt with no
    indication anything went wrong."""
    print(f"Diffing snapshots (timeout {timeout:.0f}s -- first-run symbol download can be slow)...")
    try:
        r = subprocess.run([str(umdh), str(snap1), str(snap2), f"-f:{diff}"],
                            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SystemExit(
            f"\numdh diff timed out after {timeout:.0f}s and was killed -- {diff} is truncated/"
            f"unusable. snap1/snap2 are still on disk and intact, so no need to re-run the "
            f"chaos soak. Retry just the diff with a longer --diff-timeout:\n\n"
            f"    python tools/umdh_leak_probe.py --redo-diff \"{diff.parent}\" --diff-timeout "
            f"{timeout * 3:.0f}\n\n"
            f"(A second attempt should be much faster once C:\\symbols has cached the PDBs "
            f"this run already downloaded.)"
        )
    combined = (r.stdout or "") + (r.stderr or "")
    if "didn't find any allocations" in combined.lower():
        print(f"  [WARNING] umdh reported no allocations with stacks collected -- {diff} will "
              f"be empty/useless. This means +ust tracing was not actually active on the "
              f"snapshotted PID (unrelated to the timeout fix above).")
    print(f"  diff written: {diff}")


def _wait_tracking_restarts(proc: subprocess.Popen, log_path: Path,
                             pid: int, log_pos: int, until: float) -> tuple[int, int]:
    """Sleep until `until`, but keep polling monkey.log for a PID change (a restart),
    which would silently invalidate a snap1/snap2 pairing taken across two lifetimes."""
    while time.time() < until:
        new_pid, log_pos = _tail_for_pid(log_path, log_pos)
        if new_pid is not None and new_pid != pid:
            print(f"  [WARNING] app restarted -- new PID {new_pid} (was {pid}). "
                  "snap1/snap2 must come from the SAME process lifetime -- "
                  "consider Ctrl+C and re-running.")
            pid = new_pid
        if proc.poll() is not None:
            print("  [warn] monkey_test.py exited early while waiting")
            break
        time.sleep(min(5.0, max(0.1, until - time.time())))
    return pid, log_pos


_DURATION_BUFFER_SECS = 300.0  # snap2 must land at least this long before the run's own quit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--duration", type=float, default=None, metavar="SECS",
                     help="Chaos run duration (default: settle + window + 300s buffer, so snap2 "
                          "never races the run's own duration-triggered quit sequence)")
    ap.add_argument("--settle", type=float, default=300, metavar="SECS",
                     help="Delay after connect before snap1 -- skips the startup ramp (default 300 = 5 min)")
    ap.add_argument("--window", type=float, default=1200, metavar="SECS",
                     help="Delay between snap1 and snap2 (default 1200 = 20 min)")
    ap.add_argument("--chaos", choices=["mild", "moderate", "wild"], default="wild")
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--mem-limit", type=int, default=1500, metavar="MB")
    ap.add_argument("--connect-timeout", type=float, default=240.0, metavar="SECS",
                     help="Passthrough to monkey_test.py (default 240 -- +ust slows startup)")
    ap.add_argument("--unresponsive-secs", type=float, default=90.0, metavar="SECS",
                     help="Passthrough to monkey_test.py (default 90 -- +ust's per-allocation "
                          "overhead can slow an ordinary action enough to false-trip the default "
                          "45s hang alarm mid-run)")
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--gflags", default=None, help="Explicit path to gflags.exe")
    ap.add_argument("--manage-ust", action="store_true",
                     help="Arm +ust at start and ALWAYS revert it on exit (including Ctrl+C, a "
                          "failed snapshot, or a diff timeout). Requires an elevated prompt. "
                          "Strongly preferred over arming it by hand -- a leftover +ust flag "
                          "silently falsifies every measurement taken afterwards.")
    ap.add_argument("--umdh", default=None, help="Explicit path to umdh.exe")
    ap.add_argument("--force", action="store_true",
                     help="Launch even if gflags does not report +ust active (skips the abort check)")
    ap.add_argument("--diff-timeout", type=float, default=900.0, metavar="SECS",
                     help="Timeout for the umdh diff step (default 900 = 15 min -- first-run "
                          "internet symbol resolution across 50+ DLLs can be slow; a killed "
                          "diff leaves a truncated, silently-unusable diff.txt)")
    ap.add_argument("--redo-diff", default=None, metavar="DIR",
                     help="Skip launching/snapshotting entirely -- just re-run the umdh diff "
                          "against an existing DIR/snap1.txt + DIR/snap2.txt (e.g. after a "
                          "previous --diff-timeout was too short; the raw snapshots don't need "
                          "to be retaken)")
    args = ap.parse_args()

    if args.redo_diff:
        out_dir = Path(args.redo_diff)
        snap1, snap2 = out_dir / "snap1.txt", out_dir / "snap2.txt"
        if not snap1.is_file() or not snap2.is_file():
            raise SystemExit(f"{snap1} and/or {snap2} not found in {out_dir}")
        umdh = _find_debugger_tool("umdh.exe", args.umdh)
        _run_diff(umdh, snap1, snap2, out_dir / "diff.txt", args.diff_timeout)
        return

    min_duration = args.settle + args.window + _DURATION_BUFFER_SECS
    if args.duration is None:
        args.duration = min_duration
    elif args.duration < min_duration:
        raise SystemExit(
            f"--duration {args.duration:.0f}s is too short for --settle {args.settle:.0f}s + "
            f"--window {args.window:.0f}s -- snap2 (fires at t+{args.settle + args.window:.0f}s) "
            f"would race the run's own duration-triggered quit sequence, exactly what produced "
            f"an empty UMDH snapshot last time (the process had already exited, or worse, its "
            f"PID had been reused, by the time the snapshot command ran). Need --duration >= "
            f"{min_duration:.0f}s (adds a {_DURATION_BUFFER_SECS:.0f}s safety margin), or lower "
            f"--settle/--window instead."
        )
    print(f"Duration: {args.duration:.0f}s (snap1 @ t+{args.settle:.0f}s, snap2 @ "
          f"t+{args.settle + args.window:.0f}s, {args.duration - args.settle - args.window:.0f}s "
          f"buffer before quit)")

    gflags = _find_debugger_tool("gflags.exe", args.gflags)
    umdh = _find_debugger_tool("umdh.exe", args.umdh)
    print(f"Using gflags: {gflags}")
    print(f"Using umdh:   {umdh}")
    ust_active = _check_ust_enabled(gflags)

    managed = False
    if args.manage_ust:
        managed = True   # we own the revert from here on, armed by us or not
        if ust_active:
            print("  --manage-ust: +ust was already armed; it will still be reverted on exit.")
        else:
            print("  --manage-ust: arming +ust for python.exe...")
            if not _set_ust(gflags, True):
                raise SystemExit(
                    "\nABORTING -- could not arm +ust. gflags needs an ELEVATED prompt; "
                    "re-run this from 'Run as administrator'. Nothing was changed."
                )
            ust_active = True

    if not ust_active and not args.force:
        raise SystemExit(
            "\nABORTING before launching -- +ust is not active for python.exe, so this run "
            "would produce empty/useless UMDH snapshots. Either re-run with --manage-ust from "
            "an ELEVATED prompt (recommended -- it reverts the flag automatically on every "
            "exit path), or arm it yourself first (note the '&' call operator, needed because "
            "the path contains spaces):\n\n"
            f'    & "{gflags}" /i python.exe +ust\n\n'
            "Then re-run this exact command. (Pass --force to proceed anyway, e.g. if you "
            "believe this check is wrong.)"
        )

    # Everything past this point runs under a finally that either reverts +ust
    # (--manage-ust) or, at minimum, prints the revert command. The old code
    # printed that reminder only on the success path, so an aborted snapshot, a
    # diff timeout, or a Ctrl+C left the flag armed with no warning at all --
    # which is exactly how it survived a session on 2026-08-03 and silently
    # corrupted a day of measurements.
    try:
        _probe(args, umdh)
    finally:
        _restore_ust(gflags, managed)


def _probe(args: argparse.Namespace, umdh: Path) -> None:
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir or f"test_output/umdh_probe_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "tools/monkey_test.py", "--source",
        "--chaos", args.chaos, "--seed", str(args.seed),
        "--duration", str(args.duration), "--mem-limit", str(args.mem_limit),
        "--procdump", "--output-dir", str(out_dir),
        "--connect-timeout", str(args.connect_timeout),
        "--unresponsive-secs", str(args.unresponsive_secs),
    ]
    print("Launching:", " ".join(cmd))
    proc = subprocess.Popen(cmd)

    log_path = out_dir / "monkey.log"
    pid: Optional[int] = None
    log_pos = 0
    wait_deadline = time.time() + args.connect_timeout + 60
    print("Waiting for app PID in monkey.log...")
    while pid is None and time.time() < wait_deadline:
        if proc.poll() is not None:
            raise SystemExit(f"monkey_test.py exited early (code {proc.returncode}) -- check {log_path}")
        pid, log_pos = _tail_for_pid(log_path, log_pos)
        if pid is None:
            time.sleep(1.0)
    if pid is None:
        raise SystemExit(f"Timed out waiting for app PID in {log_path}")
    connect_time = time.time()
    print(f"Tracking PID {pid} (connected {time.strftime('%H:%M:%S')})")

    print(f"Settling {args.settle:.0f}s past connect (skipping the startup ramp)...")
    pid, log_pos = _wait_tracking_restarts(proc, log_path, pid, log_pos, connect_time + args.settle)

    snap1 = out_dir / "snap1.txt"
    print(f"Taking snap1 at t+{time.time() - connect_time:.0f}s (PID {pid})...")
    r = subprocess.run([str(umdh), f"-p:{pid}", f"-f:{snap1}"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not snap1.is_file():
        raise SystemExit(f"umdh snap1 failed (code {r.returncode}): {r.stderr or r.stdout}")
    print(f"  snap1 written: {snap1}")

    print(f"Waiting {args.window:.0f}s (the steady-growth window)...")
    pid, log_pos = _wait_tracking_restarts(proc, log_path, pid, log_pos, time.time() + args.window)

    snap2 = out_dir / "snap2.txt"
    print(f"Taking snap2 at t+{time.time() - connect_time:.0f}s (PID {pid})...")
    r = subprocess.run([str(umdh), f"-p:{pid}", f"-f:{snap2}"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not snap2.is_file():
        raise SystemExit(f"umdh snap2 failed (code {r.returncode}): {r.stderr or r.stdout}")
    print(f"  snap2 written: {snap2}")

    diff = out_dir / "diff.txt"
    _run_diff(umdh, snap1, snap2, diff, args.diff_timeout)

    remaining = max(1.0, args.duration - (time.time() - connect_time)) + 60
    print(f"\nSnapshots done. Letting the chaos run finish naturally (up to {remaining:.0f}s more)...")
    if proc.poll() is None:
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            print("  [warn] monkey_test.py still running -- leaving it to finish/quit on its own")

    print(f"\nNext: read {diff} (ranked by byte growth), or run "
          f"'{umdh} {snap1} {snap2} -f:{diff}' again with _NT_SYMBOL_PATH set for better symbol names:")
    print(r"    $env:_NT_SYMBOL_PATH = 'srv*C:\symbols*https://msdl.microsoft.com/download/symbols'")


if __name__ == "__main__":
    main()
