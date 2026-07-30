"""Page-pair memory isolation harness.

Unlike monkey_test.py's random chaos clicking, this cycles through a fixed,
user-specified list of nav pages via Ctrl+K only -- no control interaction,
no random actions. The point is to isolate RSS growth by exclusion: run one
suspect page against a known-quiet anchor page, and compare the resulting
RSS slope across pairs to find which page(s) actually drive the growth
documented in docs/spikes/wild-soak-rss-leak-investigation.md.

Reuses MonkeyTester's launch/connect/overlay-dismiss/quit machinery from
monkey_test.py (already battle-tested against real focus-steal and startup
timing quirks) -- only the interaction loop differs: navigate, settle, sample
RSS, repeat.

Usage:
    python tools/page_isolation_soak.py Home "Network Map" --duration 1200
    python tools/page_isolation_soak.py Home "Protocol Visualizer" "Lab Mode" --duration 1200
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from monkey_test import Config, MonkeyTester, _force_foreground  # noqa: E402


def _slug(label: str) -> str:
    return label.lower().replace(" ", "").replace("/", "").replace("&", "")


def _navigate_to(tester: MonkeyTester, label: str) -> bool:
    """Ctrl+K -> type label -> Enter.

    Mirrors monkey_test._nav_command_palette()'s exact keystroke pattern
    (including set_foreground=False -- see that function's comment for why
    re-asserting focus on `win` mid-sequence steals the palette's own focus
    back and makes navigation silently no-op) but targets one fixed label
    instead of a random pick from _SAFE_PAGES.
    """
    win = tester._win
    try:
        win.type_keys("^k")
        time.sleep(0.45)
        win.type_keys(label[:6], with_spaces=True, pause=0.04, set_foreground=False)
        time.sleep(0.30)
        win.type_keys("{ENTER}", set_foreground=False)
        time.sleep(0.50)
        return True
    except Exception as exc:
        tester.log.warning("[nav] navigate to %r failed: %s", label, exc)
        try:
            win.type_keys("{ESC}")
        except Exception:
            pass  # non-fatal -- best-effort recovery, next iteration retries
        return False


def run_isolation(pages: list[str], duration_secs: float, seed: int, output_dir: str) -> int:
    slug = "_".join(_slug(p) for p in pages)
    cfg = Config(
        use_source=True,
        duration_secs=duration_secs,
        seed=seed,
        screenshots=False,
        output_dir=output_dir,
        log_file=str(Path(output_dir) / f"isolation_{slug}.log"),
    )
    tester = MonkeyTester(cfg)

    if not tester._launch_source():
        return 2
    if not tester._connect():
        return 2
    tester._dismiss_startup_overlays()
    time.sleep(cfg.warmup_secs)
    try:
        _force_foreground(tester._win.handle)
        tester.log.info("[startup] Foreground claimed (hwnd=0x%x)", tester._win.handle)
    except Exception as exc:
        tester.log.warning("[startup] Could not claim foreground: %s", exc)

    import threading
    stop = threading.Event()
    tester._stop = stop  # _focus_heartbeat reads this to know when to exit
    fthread = threading.Thread(target=tester._focus_heartbeat, daemon=True, name="focus")
    fthread.start()

    csv_path = Path(output_dir) / f"page_isolation_{slug}_{int(time.time())}.csv"
    rows: list[tuple[int, float, str, bool, float]] = []
    start = time.time()
    iteration = 0

    tester.log.info("=" * 70)
    tester.log.info("PAGE ISOLATION SOAK  pages=%s  duration=%.0fs", pages, duration_secs)
    tester.log.info("=" * 70)

    while time.time() - start < duration_secs:
        if not tester._alive():
            tester.log.error("[iso] process died at iter %d -- aborting run", iteration)
            break
        for label in pages:
            if time.time() - start >= duration_secs:
                break
            iteration += 1
            ok = _navigate_to(tester, label)
            time.sleep(1.5)  # let showEvent()/paint settle before sampling
            try:
                rss = tester._total_rss_mb()  # main + children, RULE-DBG4
            except Exception:
                rss = 0.0
            elapsed = time.time() - start
            rows.append((iteration, elapsed, label, ok, rss))
            if iteration % 10 == 0 or not ok:
                tester.log.info(
                    "[iso] iter=%d t=%.0fs/%.0fs page=%r nav_ok=%s rss=%.1fMB",
                    iteration, elapsed, duration_secs, label, ok, rss,
                )

    stop.set()

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["iteration", "elapsed_s", "page", "nav_ok", "total_rss_mb"])
        w.writerows(rows)

    if len(rows) >= 2:
        t0, r0 = rows[0][1], rows[0][4]
        t1, r1 = rows[-1][1], rows[-1][4]
        slope_mb_per_hr = (r1 - r0) / max(t1 - t0, 1) * 3600
        peak_rss = max(r[4] for r in rows)
    else:
        slope_mb_per_hr = 0.0
        peak_rss = rows[0][4] if rows else 0.0

    tester.log.info("=" * 70)
    tester.log.info("ISOLATION RUN COMPLETE  pages=%s", pages)
    tester.log.info("  iterations       %d", iteration)
    tester.log.info("  start_rss_mb     %.1f", rows[0][4] if rows else 0.0)
    tester.log.info("  end_rss_mb       %.1f", rows[-1][4] if rows else 0.0)
    tester.log.info("  peak_rss_mb      %.1f", peak_rss)
    tester.log.info("  slope_mb_per_hr  %.1f", slope_mb_per_hr)
    tester.log.info("  csv              %s", csv_path)
    tester.log.info("=" * 70)

    crash_log_grew = False
    if tester._crash_log is not None:
        try:
            size1 = tester._crash_log.stat().st_size
            crash_log_grew = size1 > tester._crash_log_size0
        except OSError:
            pass  # non-fatal -- crash log check is best-effort diagnostics
    if crash_log_grew:
        tester.log.error("[iso] crash-log grew during this run (RULE-CHAOS2)")

    crashed = tester._real_quit_phase()
    return 1 if (crashed or crash_log_grew) else 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pages", nargs="+",
                   help='Nav labels to cycle through, e.g. Home "Network Map"')
    p.add_argument("--duration", type=float, default=1200.0, metavar="SECS",
                   help="wall-clock run length (default 1200 = 20min)")
    p.add_argument("--seed", type=int, default=99)
    p.add_argument("--output-dir", default="test_output")
    args = p.parse_args()
    if len(args.pages) < 2:
        p.error("need at least 2 pages to alternate between")
    sys.exit(run_isolation(args.pages, args.duration, args.seed, args.output_dir))


if __name__ == "__main__":
    main()
