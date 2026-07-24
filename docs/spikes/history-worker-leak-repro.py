"""
Live repro (RULE-DBG3): quantify RSS growth from real navigation into HistoryPage.

Follow-up to the 2026-07-23 wild-soak RSS-growth thread
([[project_wild_soak_rss_regression_20260723]]). Two prior candidates were
checked and ruled out/fixed-but-insufficient: the dialog `.exec()` leak
(RULE-WIN8, fixed v2.1.39) and the nav-rail flyout toggle (quantified as a
bounded ~25MB one-time cache warm-up in flyout-toggle-leak-repro*.py). The next
candidate per that memory trail: real page navigation into a page that spins up
a worker QThread on every show, rather than on a user-initiated button click.

`ui/pages/history_page.py::showEvent()` -> `_refresh()` -> `_start_refresh_worker()`
runs `self._refresh_worker = _HistoryRefreshWorker(..., parent=self)` on EVERY
navigation into the page (no button click required, no TTL/throttle — unlike
speed_test_page.py's 30-minute-gated fetch). The previous `_refresh_worker`
reference is silently overwritten with no `deleteLater()` anywhere in the file —
the exact RULE-WIN8 general-case shape (a parented QObject whose only Python
handle is reassigned is not freed; the C++ QThread stays alive as a child of the
long-lived HistoryPage for the life of the app) applied to a worker thread
instead of a QDialog.

A sweep of the other 19 pages with a `showEvent` (network_map_page.py,
trend_page.py, speed_test_page.py, monitor_overview_page.py, connections_page.py,
dns_zone_page.py, timeline_page.py, dhcp_lease_page.py, cve_page.py, etc.) found
no other case of a worker QThread created unconditionally on every show — this
looks like an isolated instance, not a systemic sweep-worthy pattern like the
47-site dialog leak.

Method: build the REAL HistoryPage inside a REAL QStackedWidget and drive real
`setCurrentWidget()` transitions — the same primitive `_nav_crossfade_to()`
(ui/nav/builder.py) uses — in and out of the page many times. Each transition
fires a real `showEvent()`/`hideEvent()` pair against a MagicMock MetricStore
(fast, deterministic — isolates the QThread-lifecycle mechanism from real
SQLite I/O cost, matching the existing test suite's own convention in
tests/test_history_page.py). Sandwiched like dialog-exec-leak-repro.py (fixed /
leak / fixed) with an extended checkpointed leak phase like
flyout-toggle-leak-repro-final.py, to see whether growth is linear/unbounded
(a real leak) or decays to a plateau (a bounded cache warm-up, like the
ruled-out toggle case).

The REAL `_HistoryRefreshWorker` class is used unmodified (subclassed only to
add an instrumentation counter — behavior is untouched) so the "fixed" arm's
cleanup is the literal RULE-WIN8 remedy: `deleteLater()` the stale worker
before the reference is overwritten.

Run manually: `python docs/spikes/history-worker-leak-repro.py`
"""
import gc
import os
import sys

import psutil
from PyQt6.QtCore import QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QStackedWidget, QWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])
proc = psutil.Process(os.getpid())

import ui.pages.history_page as hp_mod  # noqa: E402

hp_mod.HistoryPage.REFRESH_MS = 10**9  # disable the 30s auto-timer for this repro's duration

_RealWorker = hp_mod._HistoryRefreshWorker
_created_count = [0]


class _CountingWorker(_RealWorker):
    """Real worker, unmodified — just counts instantiations for confirmation."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        _created_count[0] += 1


hp_mod._HistoryRefreshWorker = _CountingWorker


class _StubStore:
    """Plain stand-in for MetricStore's read surface used by _HistoryRefreshWorker.

    Deliberately NOT unittest.mock.MagicMock: a Mock records every call forever
    (mock_calls/call_args_list), which by itself grows unboundedly across
    thousands of calls and would swamp the much smaller per-navigation signal
    this repro is trying to measure (confirmed live: a MagicMock-backed first
    draft of this script showed ~28-30 KB/nav growth in BOTH the "fixed" and
    "leak" arms purely from call-history bookkeeping, not from the app).
    """

    _hosts = [f"192.168.1.{i}" for i in range(6)]

    def query_all_rtt_hosts(self, hours=None):
        return list(self._hosts)

    def query_rollup_hosts(self, metric):
        return []

    def query_rtt_history(self, host, hours=None):
        return []

    def query_device_state_history(self, host, hours=None):
        return []

    def query_uptime_pct(self, host, hours=None):
        return 99.0

    def query_daily_rollup(self, metric, host=None):
        return []


def _mock_store():
    return _StubStore()


def rss_mb() -> float:
    return proc.memory_info().rss / (1024 * 1024)


def live_worker_count() -> int:
    """Python-side proxy for leaked C++ QThread children: PyQt keeps a worker's
    Python wrapper alive as long as its C++ twin is alive (owned by its parent),
    so this counts real leaked instances, not just Python references."""
    return sum(1 for o in gc.get_objects() if isinstance(o, _RealWorker))


def settle():
    for _ in range(5):
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    gc.collect()


def navigate_cycle(stack: QStackedWidget, other: QWidget, page, cleanup: bool) -> None:
    """One in-then-out navigation transition, mirroring _nav_rail_go_to()."""
    if cleanup:
        stale = page._refresh_worker
        if stale is not None:
            try:
                stale.deleteLater()
            except RuntimeError:
                pass  # already gone
    stack.setCurrentWidget(page)  # showEvent() fires -> spawns a worker
    for _ in range(50):
        QTest.qWait(1)
        w = page._refresh_worker
        if w is None or not w.isRunning():
            break
    stack.setCurrentWidget(other)  # hideEvent() fires
    QTest.qWait(1)


def run(n: int, cleanup: bool, stack, other, page) -> float:
    settle()
    start = rss_mb()
    for _ in range(n):
        navigate_cycle(stack, other, page, cleanup)
    settle()
    return rss_mb() - start


if __name__ == "__main__":
    store = _mock_store()
    page = hp_mod.HistoryPage(store=store)
    other = QWidget()
    stack = QStackedWidget()
    stack.addWidget(other)
    stack.addWidget(page)
    stack.show()
    app.processEvents()
    settle()

    N = 300
    print(f"Navigations per sandwich phase: {N}")
    print(f"live worker instances before warm-up: {live_worker_count()}")

    warm = run(50, cleanup=True, stack=stack, other=other, page=page)
    print(f"warm-up (discarded): {warm:+.2f} MB  (workers created so far: {_created_count[0]}, "
          f"live: {live_worker_count()})")

    fixed1 = run(N, cleanup=True, stack=stack, other=other, page=page)
    print(f"WITH deleteLater() [1st]: RSS delta = {fixed1:+.2f} MB ({fixed1 * 1024 / N:.2f} KB/nav)  "
          f"live worker instances: {live_worker_count()}")

    # ---- checkpointed leak phase: current (unmodified) code ----
    CHECKPOINT = 500
    CHECKPOINTS = 12  # 6,000 navigations total for the leak phase
    settle()
    leak_start = rss_mb()
    prev = leak_start
    for cp in range(1, CHECKPOINTS + 1):
        for _ in range(CHECKPOINT):
            navigate_cycle(stack, other, page, cleanup=False)
        settle()
        now = rss_mb()
        total = cp * CHECKPOINT
        print(
            f"  [leak] after {total:>5} navigations: RSS={now:7.2f} MB  "
            f"delta-this-checkpoint={now - prev:+7.2f} MB "
            f"({(now - prev) * 1024 / CHECKPOINT:7.2f} KB/nav)  "
            f"cumulative={now - leak_start:+7.2f} MB  "
            f"live worker instances={live_worker_count()}"
        )
        prev = now
    leak_total = prev - leak_start
    leak_n = CHECKPOINT * CHECKPOINTS
    print(f"WITHOUT deleteLater(): RSS delta = {leak_total:+.2f} MB over {leak_n} navs "
          f"({leak_total * 1024 / leak_n:.2f} KB/nav)")

    fixed2 = run(N, cleanup=True, stack=stack, other=other, page=page)
    print(f"WITH deleteLater() [2nd]: RSS delta = {fixed2:+.2f} MB ({fixed2 * 1024 / N:.2f} KB/nav)  "
          f"live worker instances: {live_worker_count()}")

    fixed_avg = (fixed1 + fixed2) / 2
    print(f"\ntotal workers created: {_created_count[0]}")
    print(f"fixed baseline (avg of sandwiching runs): {fixed_avg:+.2f} MB over {N} navs "
          f"({fixed_avg * 1024 / N:.2f} KB/nav)")
    print(f"leak run:                                  {leak_total:+.2f} MB over {leak_n} navs "
          f"({leak_total * 1024 / leak_n:.2f} KB/nav)")
    leak_per_nav_extra = (leak_total / leak_n) - (fixed_avg / N)
    print(f"Difference attributable to the leak: {leak_per_nav_extra * 1024:.2f} KB/nav extra")
