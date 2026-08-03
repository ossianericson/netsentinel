"""
Live repro (RULE-DBG3): does InventoryPage._refresh()'s per-row PulsingDot()
(ui/widgets/pulsing_dot.py) + its animate=True QPropertyAnimation pulse leak
memory that the table's setRowCount(0) teardown (ui/pages/inventory_page.py:1467)
should have freed?

Follow-up to the wild-soak RSS investigation
([[project_wild_soak_run_20260730_2314_v220_stepfunction]]). A short -Soak
verification run (2026-07-31, run_20260731_082104) already showed this pair
jump 0 -> 589 KiB / 240 KiB / 284 KiB in ONE tracemalloc diff step across just
~2 minutes of wild chaos:

    ui/widgets/pulsing_dot.py:23    (the QPropertyAnimation itself)  +286 KiB
    ui/pages/inventory_page.py:1533 (the PulsingDot() construction)  +138 KiB
    ui/pages/inventory_page.py:1536 (the set_status() call)          +117 KiB

That alone doesn't prove a leak vs. legitimate row growth — Inventory's table
is rebuilt from scratch (setRowCount(0)) every 15s refresh and can legitimately
hold more rows over time as more device events accumulate within the 24h
window. This repro isolates the animation-specific mechanism from that
baseline by running TWO arms that grow their table identically:

  control: every cycle inserts one "DOWN" event -> _refresh()'s dot-creation
           branch takes animate=False (no QPropertyAnimation started;
           ui/pages/inventory_page.py:1535-1538's condition requires
           event_type in ("JOINED", "UP", "RECOVERED")).
  test:    every cycle inserts one "JOINED" event -> animate=True, so every
           new PulsingDot's QPropertyAnimation(self, b"dot_radius", self)
           actually runs (400ms pulse, pulsing_dot.py:23-24).

Both arms insert exactly one new device_event per cycle and never delete any,
so query_device_events(hours=24) legitimately returns MORE rows every cycle in
BOTH arms — table growth is identical between arms by construction. If nothing
leaks, live PulsingDot count after N cycles should be ~N in BOTH arms (exactly
the current row count, since setRowCount(0) destroys everything from the
previous cycle before rebuilding). If the animate=True path leaks, the test
arm's live PulsingDot count will exceed the control arm's for the same N —
that excess is code specifically tied to animate=True, i.e. the running
QPropertyAnimation, not "the table legitimately has more rows now."

Run manually: python docs/spikes/inventory-pulsing-dot-leak-repro.py [--cycles N]
"""
import argparse
import gc
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import psutil  # noqa: E402
from PyQt6.QtCore import QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from modules.metric_store import MetricStore  # noqa: E402
from ui.pages.inventory_page import InventoryPage  # noqa: E402
from ui.widgets.pulsing_dot import PulsingDot  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])
proc = psutil.Process(os.getpid())


def rss_mb() -> float:
    return proc.memory_info().rss / (1024 * 1024)


def live_pulsingdot_count() -> int:
    gc.collect()
    return sum(1 for o in gc.get_objects() if isinstance(o, PulsingDot))


def settle(n: int = 5) -> None:
    for _ in range(n):
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    gc.collect()


def run_arm(name: str, event_type: str, cycles: int, checkpoint: int, db_path: Path) -> dict:
    print("=" * 78)
    print(f"ARM: {name}  (event_type={event_type}, animate="
          f"{event_type in ('JOINED', 'UP', 'RECOVERED')})")
    print("=" * 78)

    store = MetricStore(db_path=db_path)
    page = InventoryPage(store=store)
    page.show()
    settle()
    assert page.isVisible(), "page must be visible for _refresh() to do its table rebuild"

    rss0 = rss_mb()
    dots0 = live_pulsingdot_count()
    print(f"before: rss={rss0:.2f} MB  live PulsingDot={dots0}")

    base_ts = int(time.time())
    t0 = time.time()
    for i in range(cycles):
        store.record_device_event(
            ip=f"10.{(i // 250) % 256}.{(i % 250) + 1}.1",
            event_type=event_type,
            mac=f"aa:bb:cc:dd:{(i // 256) % 256:02x}:{i % 256:02x}",
            ts=base_ts + i,
        )
        page._refresh()
        app.processEvents()   # let deleteLater()'s DeferredDelete queue drain every cycle,
                               # matching the real app's continuously-running event loop —
                               # without this, unprocessed deletions back up identically in
                               # BOTH arms and look like a leak that isn't one (see repro notes)
        if (i + 1) % checkpoint == 0:
            now = rss_mb()
            dots = live_pulsingdot_count()
            rows = page._table.rowCount()
            print(f"  [{i + 1:>5}/{cycles}] rows={rows:>5}  "
                  f"rss={now:7.2f} MB (d={now - rss0:+7.2f})  "
                  f"live PulsingDot={dots:>5} (excess-over-rows={dots - rows:+d})  "
                  f"elapsed={time.time() - t0:5.1f}s")

    settle(10)
    time.sleep(0.5)   # let any in-flight 400ms pulse animations finish
    settle(10)

    rss1 = rss_mb()
    dots1 = live_pulsingdot_count()
    rows1 = page._table.rowCount()   # ground truth: dots1 should equal rows1 if nothing leaks
    print(f"after:  rss={rss1:.2f} MB (d={rss1 - rss0:+.2f})  "
          f"live PulsingDot={dots1}  rows={rows1}  excess-over-rows={dots1 - rows1:+d}")

    page.deleteLater()
    settle()
    store.close()

    return {
        "name": name, "cycles": cycles, "rows": rows1,
        "rss_delta": rss1 - rss0, "dots_before": dots0, "dots_after": dots1,
        "dots_excess": dots1 - rows1,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=int, default=800)
    p.add_argument("--checkpoint", type=int, default=100)
    args = p.parse_args()

    import tempfile
    # Fresh dir every invocation -- a reused fixed path left stale events from a
    # prior run's db file on disk, silently inflating "before" row/dot counts.
    tmp_dir = Path(tempfile.mkdtemp(prefix="inventory_pulsing_dot_repro_"))

    control = run_arm("control (animate=False)", "DOWN", args.cycles, args.checkpoint,
                       tmp_dir / "control.db")
    print()
    test = run_arm("test (animate=True)", "JOINED", args.cycles, args.checkpoint,
                    tmp_dir / "test.db")

    print()
    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    for r in (control, test):
        print(f"{r['name']:<28} cycles={r['cycles']:<6} rows={r['rows']:<6} "
              f"rss_delta={r['rss_delta']:+8.2f} MB  "
              f"live PulsingDot={r['dots_after']:<6} excess-over-rowcount={r['dots_excess']:+d}")

    excess_gap = test["dots_excess"] - control["dots_excess"]
    print()
    print(f"excess-PulsingDot gap (test - control): {excess_gap:+d}")
    if excess_gap > max(5, 0.05 * args.cycles):
        print("LEAK CONFIRMED: the animate=True arm retains meaningfully more live "
              "PulsingDot instances than the control, for identical table growth — "
              "the running QPropertyAnimation (or something set_status(animate=True) "
              "does) is preventing setCellWidget()/setRowCount(0)'s teardown from "
              "freeing the previous cycle's dot.")
    else:
        print("NOT reproduced: both arms retain roughly the expected (~row-count) "
              "number of live PulsingDot instances -- no differential leak detected "
              "from this mechanism.")


if __name__ == "__main__":
    main()
