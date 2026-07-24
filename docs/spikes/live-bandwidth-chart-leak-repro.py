"""
Live repro (RULE-DBG3): does LiveBandwidthPage's background poller + matplotlib
redraw loop keep running forever after the user navigates away, and does
pumping it drive main-process RSS growth visible to tools/monkey_test.py?

Follow-up to the wild-soak RSS-growth thread
([[project_wild_soak_rss_regression_20260723]],
[[project_network_map_webengine_leak_ruled_out_as_driver_20260724]]). Four prior
candidates were checked: the dialog `.exec()` leak (fixed v2.1.39), the
nav-rail flyout toggle (bounded ~25MB warm-up), the HistoryPage worker leak
(fixed, ~1.5KB/nav), and Network Map's QWebEngineView bandwidth-sniffer leak
(fixed, RULE-WIN15 — but lives entirely in the QtWebEngineProcess.exe CHILD
process, so it does not explain the tracked main-PID-only wild-soak metric).
The flagged-but-untested lead left on record: matplotlib canvas/figure
retention across the many chart-bearing pages wild chaos visits.

Reading `ui/pages/live_bandwidth_page.py` end to end found a more specific
mechanism than generic "matplotlib retention" — the SAME RULE-WIN15 shape bug
as Network Map, but this time entirely IN-PROCESS (matches the tracked metric
exactly, unlike the WebEngine case):

  `__init__()` calls `_start_worker()` UNCONDITIONALLY (not deferred to
  `showEvent()` like Network Map) — `IfaceBwPoller` (workers/iface_bw_worker.py)
  is a QThread that polls `psutil.net_io_counters()` every 1s FOREVER. Every
  tick's `stats_ready` signal drives `_on_stats()` -> `_redraw_chart()`, which
  does a full matplotlib repaint: `ax.clear()`, 2x `fill_between()`, 2x
  `plot()`, `ax.legend()` rebuild, per-spine styling loop, tick label/xlabel
  recreation, and up to `_HISTORY_LEN` (60) `axvline()`/`text()` calls for
  event annotations -- then `self._canvas.draw_idle()`. This file has NO
  `hideEvent()` override at all (grep-confirmed) — unlike
  `history_page.py`/`speed_test_page.py`/`geo_map_page.py`, which all stop
  their own workers on hide. The ONLY place `_worker.stop()` is called is
  `closeEvent()`, which never fires for a page living inside the permanent
  `QStackedWidget` until the whole app closes.

  So once a user visits Live Bandwidth even once, this 1Hz poll+redraw loop
  keeps running for the rest of the app session no matter what page is
  showing — the identical shape as the already-fixed Network Map bug, but at
  5x the tick rate (1s vs 5s) and doing much heavier per-tick work (a real
  matplotlib Axes rebuild with legend/annotations vs a single runJavaScript
  call), and critically ALL of it happens in the main process, which is
  exactly what tools/monkey_test.py measures.

Part A confirms the worker survives a simulated navigate-away.
Part B pumps simulated `_on_stats()` calls (bypassing the real QThread/psutil
polling — same technique as the WebEngine repro's direct `_on_bw_snapshot()`
calls) while the page is hidden, sampling total RSS (main + children, RULE-DBG4)
at checkpoints across ~1 simulated hour (3,600 ticks @ 1s) to see whether the
growth plateaus (like the three ruled-out mechanisms) or not (like the
WebEngine mechanism).

Run manually: `python docs/spikes/live-bandwidth-chart-leak-repro.py`
"""
import gc
import os
import random
import sys

import psutil
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QStackedWidget, QWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])
proc = psutil.Process(os.getpid())

import ui.pages.live_bandwidth_page as lb_mod  # noqa: E402
import workers.iface_bw_worker as iface_mod  # noqa: E402

_RealWorker = iface_mod.IfaceBwPoller
_started_count = [0]
_stopped_count = [0]


class _CountingWorker(_RealWorker):
    """Real worker class, unmodified behavior — override run() to a no-op gate
    (never actually touching psutil.net_io_counters()) so the lifecycle bug can
    be tested without depending on real NIC counters, mirroring the
    Network Map repro's _CountingWorker technique."""

    def run(self) -> None:  # noqa: D401 — intentionally does nothing
        self._running = True
        while self._running:
            self._sleep_interruptible(0.05)

    def start(self, *a, **kw):  # type: ignore[override]
        _started_count[0] += 1
        super().start(*a, **kw)

    def stop(self) -> None:
        _stopped_count[0] += 1
        super().stop()


iface_mod.IfaceBwPoller = _CountingWorker  # live_bandwidth_page.py imports it locally
                                            # inside _start_worker(), so patching the
                                            # source module (read at call time) is required


def rss_mb(pid=None) -> float:
    p = proc if pid is None else psutil.Process(pid)
    return p.memory_info().rss / (1024 * 1024)


def total_rss_mb() -> float:
    """Main process + every child (RULE-DBG4)."""
    total = rss_mb()
    for c in proc.children(recursive=True):
        try:
            total += rss_mb(c.pid)
        except psutil.NoSuchProcess:
            pass  # child exited between children() and memory_info()
    return total


def settle(n=5):
    for _ in range(n):
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    gc.collect()


_IFACES = ["Ethernet", "Wi-Fi", "Loopback Pseudo-Interface 1", "vEthernet (WSL)"]


def _fake_stats(tick: int) -> dict:
    return {
        iface: {
            "up_mbps":    max(0.0, random.gauss(2.0, 1.5)),
            "down_mbps":  max(0.0, random.gauss(8.0, 4.0)),
            "up_bytes":   random.randint(1000, 500_000),
            "down_bytes": random.randint(1000, 2_000_000),
        }
        for iface in _IFACES
    }


# ── Part A: mechanism confirmation — does the worker survive a hide? ──────────

def part_a():
    print("=" * 78)
    print("PART A — does hiding the page stop the background bandwidth poller?")
    print("=" * 78)

    other = QWidget()
    stack = QStackedWidget()
    page = lb_mod.LiveBandwidthPage()
    stack.addWidget(other)
    stack.addWidget(page)
    stack.resize(1200, 800)
    stack.show()

    stack.setCurrentWidget(page)  # showEvent() fires (no-op here — worker already started in __init__)
    settle()

    worker = page._worker
    print(f"After first show: _worker={'set' if worker else 'None'}  "
          f"isRunning={worker.isRunning() if worker else None}  "
          f"started_count={_started_count[0]}")

    stack.setCurrentWidget(other)  # hideEvent() fires on `page` (no override exists)
    settle()

    worker_after_hide = page._worker
    print(f"After navigating away (hideEvent fired, or no-op if absent): _worker="
          f"{'set' if worker_after_hide else 'None'}  "
          f"isRunning={worker_after_hide.isRunning() if worker_after_hide else None}  "
          f"stopped_count={_stopped_count[0]}")

    if worker_after_hide is not None and worker_after_hide.isRunning():
        print("BUG REPRODUCED: worker is still running after the page was hidden — "
              "no hideEvent() stops it (same shape as the fixed RULE-WIN15 Network Map bug).")
    else:
        print(f"NOT reproduced: worker was stopped — stopped_count={_stopped_count[0]}.")

    # Clean up regardless of outcome, for Part B's isolation
    if worker_after_hide is not None:
        worker_after_hide.stop()
        worker_after_hide.wait(500)
    page.deleteLater()
    other.deleteLater()
    stack.deleteLater()
    settle()
    return worker_after_hide is not None and False  # never used; keep stack alive via return below


# ── Part B: magnitude — does the redraw loop grow RSS while hidden? ───────────

def part_b():
    print()
    print("=" * 78)
    print("PART B — magnitude: repeated background _on_stats() calls while the")
    print("          page is HIDDEN (simulating the poller's 1s loop continuing")
    print("          after the user navigated away)")
    print("=" * 78)

    other = QWidget()
    stack = QStackedWidget()
    page = lb_mod.LiveBandwidthPage()
    stack.addWidget(other)
    stack.addWidget(page)
    stack.resize(1200, 800)
    stack.show()

    stack.setCurrentWidget(page)
    settle()

    # Stop the real (no-op) poller thread — we drive _on_stats() directly so the
    # tick rate is deterministic and the run isn't wall-clock bound at 1 tick/s.
    if page._worker is not None:
        page._worker.stop()
        page._worker.wait(500)

    stack.setCurrentWidget(other)  # hide the page — the real-world condition we're testing
    settle()
    print(f"Page hidden (isVisible={page.isVisible()}).")

    def pump(n: int, tick_start: int) -> None:
        for i in range(n):
            tick = tick_start + i
            page._on_stats(_fake_stats(tick))
            if tick % 7 == 0:
                page.annotate_event("device joined", "#4CAF50")
            app.processEvents()

    warm = 200
    pump(warm, 0)
    settle()
    main0 = rss_mb()
    total0 = total_rss_mb()
    print(f"After {warm}-tick warm-up (discarded): main={main0:.2f} MB  total={total0:.2f} MB")

    CHECKPOINT = 300
    CHECKPOINTS = 12  # 3,600 simulated ticks total — 1 real hour at the actual 1s poll interval
    prev_main = main0
    prev_total = total0
    for cp in range(1, CHECKPOINTS + 1):
        pump(CHECKPOINT, warm + cp * CHECKPOINT)
        settle()
        now_main = rss_mb()
        now_total = total_rss_mb()
        n = cp * CHECKPOINT
        print(
            f"  [tick] after {n:>5} bg ticks (~{n/60:5.1f} sim-min): main={now_main:7.2f} MB "
            f"(d={now_main - prev_main:+6.2f})  total={now_total:7.2f} MB "
            f"(d={now_total - prev_total:+6.2f})"
        )
        prev_main, prev_total = now_main, now_total

    print()
    print(f"main-process RSS:  {main0:.2f} -> {prev_main:.2f} MB "
          f"({prev_main - main0:+.2f} MB over {CHECKPOINT * CHECKPOINTS} bg ticks "
          f"= ~{(CHECKPOINT * CHECKPOINTS) / 60:.0f} sim-minutes at the real 1s poll rate)")
    # Scale to the wild-soak reporting window (450MB/20min baseline) for direct comparison.
    sim_minutes = (CHECKPOINT * CHECKPOINTS) / 60
    per_20min = (prev_main - main0) / sim_minutes * 20
    print(f"extrapolated main-process growth per 20 sim-minutes: {per_20min:+.2f} MB "
          f"(wild-soak baseline to compare against: ~+450 MB/20min)")

    page.deleteLater()
    other.deleteLater()
    stack.deleteLater()
    settle()


if __name__ == "__main__":
    part_a()
    part_b()
