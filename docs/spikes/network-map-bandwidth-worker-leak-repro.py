"""
Live repro (RULE-DBG3): Network Map's background bandwidth sniffer never stops
on hide, and quantify whether pumping it drives RSS growth visible to
tools/monkey_test.py's measurement.

Follow-up to the 2026-07-23/24 wild-soak RSS-growth thread
([[project_wild_soak_rss_regression_20260723]],
[[project_history_page_worker_leak_ruled_out_20260723]]). Three prior candidates
were checked and ruled out/fixed-but-insufficient: the dialog `.exec()` leak
(fixed v2.1.39), the nav-rail flyout toggle (bounded ~25MB warm-up), and the
HistoryPage worker leak (fixed, ~1.5KB/nav). The flagged-but-untested lead left
on record: Network Map's QWebEngineView.

Reading `ui/pages/network_map_page.py` end to end (not just the WebEngine
angle) found a more specific mechanism than "heavy embedded Chromium":

  `showEvent()` defaults Traffic Overlay to CHECKED the first time the page is
  ever shown (`_traffic_overlay_defaulted`), which starts a
  `BandwidthOverlayWorker` (workers/bandwidth_worker.py) — a QThread that runs
  a Scapy AsyncSniffer forever, emitting `snapshot_ready` every 5s. Every
  snapshot calls `_on_bw_snapshot()` -> `_refresh_web_view()`, which rebuilds
  the element list and pushes it into the live QWebEngineView via
  `runJavaScript()`.

  Unlike every other page with a background worker/timer (history_page.py,
  speed_test_page.py, geo_map_page.py, overview_tile.py, page_header.py all
  implement `hideEvent()` to stop their own workers), `network_map_page.py`
  has NO `hideEvent()` override at all. Nothing stops `_bw_worker` when the
  user navigates away — only the explicit "Traffic Overlay" checkbox does.
  So after a SINGLE visit to Network Map, a Scapy sniffer thread keeps running
  and keeps pushing JS updates into a hidden QWebEngineView every 5 seconds
  for the rest of the app session (confirmed by code reading; Part A below
  confirms it live).

  Separately — and this matters for whether this mechanism can even explain
  the wild-soak numbers — a live check
  (`python -c "... QWebEngineView() ..."`, see session notes) confirmed
  QWebEngineView spawns a genuinely separate OS process
  (`QtWebEngineProcess.exe`), even headless/offscreen. `tools/monkey_test.py`
  samples RSS via `self._proc.memory_info().rss` on the SINGLE main PID only
  (no `.children()` anywhere in the sampling code, grep-verified) — so any
  growth purely inside the renderer process's own heap is structurally
  invisible to every number in the wild-soak memory trail. Part B below
  measures BOTH the main-process RSS and the combined (main + children) RSS
  to see whether the main process ALSO grows (e.g. via IPC/shared-memory
  buffers for compositor frames), which is the only way this mechanism could
  explain the measured metric.

Run manually: `python docs/spikes/network-map-bandwidth-worker-leak-repro.py`
"""
import gc
import os
import sys

import psutil
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QApplication, QStackedWidget, QWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Must be set before QApplication() is constructed — see app.py:959.
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])
proc = psutil.Process(os.getpid())

import ui.pages.network_map_page as nm_mod  # noqa: E402
from modules.bandwidth_monitor import BandwidthEntry, BandwidthSnapshot  # noqa: E402

_RealWorker = nm_mod.BandwidthOverlayWorker
_started_count = [0]
_stopped_count = [0]


class _CountingWorker(_RealWorker):
    """Real worker class, unmodified behavior — .start()/.stop() are QThread
    methods we can't easily intercept without overriding run(), so instead we
    override start()/stop() to count calls AND still invoke the real QThread
    machinery via a no-op run() (never actually sniffing — no admin/Npcap
    dependency needed to test the lifecycle bug)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)

    def run(self) -> None:  # noqa: D401 — intentionally does nothing
        self._stop_event.clear()
        self._stop_event.wait()  # blocks until stop() is called, like the real loop's gate

    def start(self, *a, **kw):  # type: ignore[override]
        _started_count[0] += 1
        super().start(*a, **kw)

    def stop(self) -> None:
        _stopped_count[0] += 1
        super().stop()


nm_mod.BandwidthOverlayWorker = _CountingWorker


def rss_mb(pid=None) -> float:
    p = proc if pid is None else psutil.Process(pid)
    return p.memory_info().rss / (1024 * 1024)


def total_rss_mb() -> float:
    """Main process + every child (e.g. QtWebEngineProcess.exe) — the metric
    tools/monkey_test.py does NOT compute (it samples the main PID only)."""
    total = rss_mb()
    for c in proc.children(recursive=True):
        try:
            total += rss_mb(c.pid)
        except psutil.NoSuchProcess:
            pass  # child exited between children() and memory_info()
    return total


def child_names() -> list:
    try:
        return [c.name() for c in proc.children(recursive=True)]
    except psutil.Error:
        return []


def settle(n=5):
    for _ in range(n):
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    gc.collect()


def _devices():
    return [
        {"ip": f"192.168.68.{i}", "mac": f"aa:bb:cc:dd:ee:{i:02x}",
         "hostname": f"device-{i}", "risk_level": "CLEAN"}
        for i in range(2, 14)
    ]


def _fake_snapshot(seed: int) -> BandwidthSnapshot:
    entries = [
        BandwidthEntry(mac=f"aa:bb:cc:dd:ee:{i:02x}", ip=f"192.168.68.{i}",
                        label=f"device-{i}", rx_bytes=1000 + seed, tx_bytes=500 + seed,
                        rx_bps=(1000 + seed) / 5.0, tx_bps=(500 + seed) / 5.0)
        for i in range(2, 14)
    ]
    return BandwidthSnapshot(entries=entries, window_s=5.0)


# ── Part A: mechanism confirmation — does the worker survive a hide? ──────────

def part_a():
    print("=" * 78)
    print("PART A — does hiding the page stop the background bandwidth worker?")
    print("=" * 78)

    other = QWidget()
    stack = QStackedWidget()
    page = nm_mod.NetworkMapPage()
    stack.addWidget(other)
    stack.addWidget(page)
    stack.resize(1200, 800)
    stack.show()

    stack.setCurrentWidget(page)  # showEvent() fires -> Traffic Overlay auto-defaults ON
    settle()

    worker = page._bw_worker
    print(f"After first show: _traffic_overlay={page._traffic_overlay}  "
          f"_bw_worker={'set' if worker else 'None'}  "
          f"isRunning={worker.isRunning() if worker else None}  "
          f"started_count={_started_count[0]}")

    stack.setCurrentWidget(other)  # hideEvent() fires on `page`
    settle()

    worker_after_hide = page._bw_worker
    print(f"After navigating away (hideEvent fired): _bw_worker="
          f"{'set' if worker_after_hide else 'None'}  "
          f"isRunning={worker_after_hide.isRunning() if worker_after_hide else None}  "
          f"stopped_count={_stopped_count[0]}")

    if worker_after_hide is not None and worker_after_hide.isRunning():
        print("BUG REPRODUCED: worker is still running after the page was hidden — "
              "no hideEvent() stops it.")
    else:
        print("FIXED: worker was stopped by hideEvent() (RULE-WIN15) — "
              f"stopped_count={_stopped_count[0]}.")

    # Clean up regardless of outcome, for Part B's isolation
    if worker_after_hide is not None:
        worker_after_hide.stop()
        worker_after_hide.wait(500)
    page.deleteLater()
    other.deleteLater()
    stack.deleteLater()
    settle()
    return stack  # kept alive only long enough to print; GC'd after return


# ── Part B: magnitude — does pumping updates into a hidden WebEngineView grow RSS? ──

def part_b():
    print()
    print("=" * 78)
    print("PART B — magnitude: repeated background _on_bw_snapshot() calls")
    print("          while the page is HIDDEN (simulating the worker's 5s loop")
    print("          continuing after the user navigated away)")
    print("=" * 78)

    other = QWidget()
    stack = QStackedWidget()
    page = nm_mod.NetworkMapPage()
    stack.addWidget(other)
    stack.addWidget(page)
    stack.resize(1200, 800)
    stack.show()

    stack.setCurrentWidget(page)  # triggers _try_init_webengine()
    settle()
    print(f"_web_available={page._web_available}  web_view={'set' if page._web_view else 'None'}")
    if not page._web_available:
        print("QWebEngineView failed to initialize in this environment — Part B cannot "
              "measure the real native path. Stopping here.")
        return

    page.render(devices=_devices(), gateway_ip="192.168.68.1", gateway_mac="aa:bb:cc:dd:ee:00")
    for _ in range(30):
        app.processEvents()
    settle()
    print(f"_topology_loaded={page._topology_loaded}  children={child_names()}")

    page._traffic_overlay = True  # matches the real auto-defaulted state
    stack.setCurrentWidget(other)  # hide the page — the real-world condition we're testing
    settle()
    print(f"Page hidden (isVisible={page.isVisible()}). Beginning background-push simulation.")

    def pump(n: int, seed_start: int) -> None:
        for i in range(n):
            page._on_bw_snapshot(_fake_snapshot(seed_start + i))
            app.processEvents()  # let the runJavaScript() call actually reach the renderer

    warm = 100
    pump(warm, 0)
    settle()
    main0 = rss_mb()
    total0 = total_rss_mb()
    print(f"After {warm}-call warm-up (discarded): main={main0:.2f} MB  total={total0:.2f} MB  "
          f"children={child_names()}")

    CHECKPOINT = 300
    CHECKPOINTS = 8  # 2,400 background pushes total — roughly 3.3 real hours at 5s/push
    prev_main = main0
    prev_total = total0
    for cp in range(1, CHECKPOINTS + 1):
        pump(CHECKPOINT, cp * CHECKPOINT)
        settle()
        now_main = rss_mb()
        now_total = total_rss_mb()
        n = cp * CHECKPOINT
        print(
            f"  [push] after {n:>5} bg refreshes: main={now_main:7.2f} MB "
            f"(d={now_main - prev_main:+6.2f})  total={now_total:7.2f} MB "
            f"(d={now_total - prev_total:+6.2f})  children={child_names()}"
        )
        prev_main, prev_total = now_main, now_total

    print()
    print(f"main-process RSS:  {main0:.2f} -> {prev_main:.2f} MB "
          f"({prev_main - main0:+.2f} MB over {CHECKPOINT * CHECKPOINTS} bg refreshes)")
    print(f"total (main+children) RSS: {total0:.2f} -> {prev_total:.2f} MB "
          f"({prev_total - total0:+.2f} MB over {CHECKPOINT * CHECKPOINTS} bg refreshes)")

    page.deleteLater()
    other.deleteLater()
    stack.deleteLater()
    settle()


if __name__ == "__main__":
    part_a()
    part_b()
