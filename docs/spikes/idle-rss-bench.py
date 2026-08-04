"""Idle-Dashboard RSS bench — before/after arm for the timer/render fixes.

Reproduces the measurement methodology from
docs/spikes/idle-rss-leak-lazy-page-timers.md:

  * real MetricStore (a COPY of the real DB — never the live one)
  * Dashboard shown, sitting idle on Home, never navigated
  * every other page constructed by the lazy chunk-builder but NEVER shown
    (that is the scenario RULE-WIN18 is about, and the one today's fixes target)
  * main-process and child-process RSS sampled SEPARATELY — the spike found
    QtWebEngineProcess oscillates in a ~25 MB bounded sawtooth (Chromium GC),
    which swamps the real signal if you sum them (RULE-DBG4 says include
    children; this says report them apart, not merged)

Run one arm on the working tree and one on stashed HEAD, same duration, same
machine state, nothing else running.

    python idle_rss_bench.py --label after  --duration 900
    git stash push -- ui/ && python idle_rss_bench.py --label before --duration 900 ; git stash pop

Offscreen QPA on purpose: a real window steals focus and makes noise, and a
prior session established that unattended live-GUI repros are disruptive.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_REPO = Path(r"c:\Code\netsentinel")
sys.path.insert(0, str(_REPO))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import psutil  # noqa: E402

# Redirect settings_path() BEFORE importing/constructing anything that reads it.
# Dashboard.closeEvent() unconditionally calls save_settings(); left pointed at
# the real NetSentinel.ini it overwrites the developer's actual window geometry
# with an offscreen Dashboard's degenerate geometry (see tests/_lazy_pages_child.py).
import tempfile as _tf  # noqa: E402
from ui import app_settings as _app_settings  # noqa: E402

_BENCH_INI = Path(_tf.mkdtemp()) / "NetSentinel_bench.ini"
_app_settings.settings_path = lambda: _BENCH_INI

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP: QApplication | None = None      # module-level: keeps the C++ app alive
_DASH = None


def _real_db() -> Path | None:
    from modules.utils import get_app_data_dir
    db = Path(get_app_data_dir()) / "NetSentinel.db"
    return db if db.exists() else None


def _make_store():
    """Real MetricStore over a COPY of the real DB (never the live file)."""
    from modules.metric_store import MetricStore

    src = _real_db()
    dst = Path(tempfile.mkdtemp()) / "NetSentinel_bench.db"
    if src is not None:
        shutil.copy2(src, dst)
        print(f"[bench] DB copy: {src} -> {dst} ({dst.stat().st_size / 1e6:.1f} MB)")
    else:
        print("[bench] WARNING: no real DB found — running against an empty store, "
              "which under-represents per-tick rebuild cost")
    return MetricStore(db_path=dst)


def _rss_split(proc: psutil.Process) -> tuple[float, float]:
    """(main_mb, children_mb) — reported apart, never summed."""
    main = proc.memory_info().rss
    child = 0
    for c in proc.children(recursive=True):
        try:
            child += c.memory_info().rss
        except psutil.Error:
            pass  # child exited between children() and memory_info() — skip
    return main / (1024 * 1024), child / (1024 * 1024)


def _fit_mb_per_hr(samples: list[tuple[float, float]]) -> float:
    """Least-squares slope over (t_seconds, mb), scaled to MB/hour."""
    n = len(samples)
    if n < 2:
        return 0.0
    mean_t = sum(t for t, _ in samples) / n
    mean_v = sum(v for _, v in samples) / n
    num = sum((t - mean_t) * (v - mean_v) for t, v in samples)
    den = sum((t - mean_t) ** 2 for t, _ in samples)
    return 0.0 if den == 0 else (num / den) * 3600.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="arm name, e.g. before / after")
    ap.add_argument("--duration", type=int, default=900, help="seconds (default 900)")
    ap.add_argument("--interval", type=int, default=30, help="sample period (default 30)")
    ap.add_argument("--settle", type=int, default=120,
                    help="seconds to ignore before the trend window starts "
                         "(default 120 — skips the lazy-build ramp)")
    args = ap.parse_args()

    global _APP, _DASH
    _APP = QApplication.instance() or QApplication(["netsentinel-bench", "-platform", "offscreen"])

    store = _make_store()
    from ui.dashboard import Dashboard

    t_start = time.time()
    _DASH = Dashboard(store=store)
    _DASH.show()                     # Home visible; every other page stays unshown
    print(f"[bench] Dashboard constructed+shown in {time.time() - t_start:.1f}s")
    print(f"[bench] arm={args.label} duration={args.duration}s "
          f"interval={args.interval}s settle={args.settle}s")
    print(f"[bench] current page: {getattr(_DASH, '_nav_current_label', '?')}")

    proc = psutil.Process()
    samples: list[tuple[float, float]] = []
    t0 = time.time()
    print(f"{'t':>6} | {'main MB':>9} | {'child MB':>9} | {'d_main':>8}")

    def sample() -> None:
        t = time.time() - t0
        main_mb, child_mb = _rss_split(proc)
        d = f"{main_mb - samples[-1][1]:+.2f}" if samples else "   —"
        print(f"{t:6.0f} | {main_mb:9.1f} | {child_mb:9.1f} | {d:>8}", flush=True)
        samples.append((t, main_mb))
        if t >= args.duration:
            finish(samples, args)

    timer = QTimer()
    timer.timeout.connect(sample)
    timer.start(args.interval * 1000)
    _APP.exec()


def finish(samples: list[tuple[float, float]], args) -> None:
    windowed = [(t, v) for t, v in samples if t >= args.settle]
    print("\n" + "=" * 62)
    print(f"ARM: {args.label}")
    if len(samples) >= 2:
        print(f"  full run   : {samples[0][1]:.1f} -> {samples[-1][1]:.1f} MB "
              f"({_fit_mb_per_hr(samples):+.1f} MB/hr)")
    if len(windowed) >= 2:
        print(f"  post-settle: {windowed[0][1]:.1f} -> {windowed[-1][1]:.1f} MB "
              f"({_fit_mb_per_hr(windowed):+.1f} MB/hr)   <-- compare THIS across arms")
    else:
        print("  post-settle: not enough samples after --settle; raise --duration")
    print("=" * 62, flush=True)
    sys.stdout.flush()
    os._exit(0)     # skip Qt teardown entirely (RULE-WIN4 / os._exit convention)


if __name__ == "__main__":
    main()
