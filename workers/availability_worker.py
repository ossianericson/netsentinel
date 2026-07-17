"""
AvailabilityWorker — QThread wrapper for the background availability monitor.

Creates one long-running thread that:
  1. Waits interval_s seconds between cycles (interruptible via stop()).
  2. Calls AvailabilityMonitor.run_cycle() and emits signals for the UI.

Signals
-------
cycle_done(dict)        — emitted after every cycle: {"ts": int, "states": {}, "rtts": {}}
state_changed(str, str, str)  — host, previous_state, current_state
error(str)              — human-readable error message

Usage (in app.py / dashboard.py)
---------------------------------
    worker = AvailabilityWorker(store=metric_store)
    worker.state_changed.connect(my_slot)
    worker.start()
    ...
    worker.stop()
    worker.wait()
"""

import time
from typing import List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from modules.availability_monitor import AvailabilityMonitor, CycleResult, TargetConfig
from modules.metric_store import MetricStore


class AvailabilityWorker(QThread):
    """Background QThread that runs the availability monitor on a fixed interval."""

    # Emitted after every completed cycle
    cycle_done    = pyqtSignal(dict)
    # Emitted for each state transition within a cycle
    state_changed = pyqtSignal(str, str, str)   # host, previous, current
    # Emitted on unexpected errors
    error         = pyqtSignal(str)

    def __init__(
        self,
        store: MetricStore,
        targets: Optional[List[TargetConfig]] = None,
        interval_s: int = 60,
        parent=None,
    ):
        super().__init__(parent)
        self._stop_requested = False
        self._monitor = AvailabilityMonitor(
            store=store,
            targets=targets,
            interval_s=interval_s,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def set_targets(self, targets: List[TargetConfig]) -> None:
        """Update targets; takes effect on the next cycle."""
        self._monitor.set_targets(targets)

    def stop(self) -> None:
        """Request graceful shutdown. Call wait() afterwards to join."""
        self._stop_requested = True

    # ── QThread entry point ───────────────────────────────────────────────────

    def run(self) -> None:
        interval = self._monitor.interval_s
        while not self._stop_requested:
            try:
                result: CycleResult = self._monitor.run_cycle()
                self.cycle_done.emit({
                    "ts":     result.ts,
                    "states": dict(result.states),
                    "rtts":   dict(result.rtts),
                })
                # F5: fetch the known-device map once per cycle rather than
                # once per state change (only needed at all when something
                # transitioned this cycle).
                _known = None
                if result.changes:
                    try:
                        _known = self._monitor._store.get_known_devices()
                    except Exception:
                        pass  # non-fatal — audit trail is best-effort
                for change in result.changes:
                    self.state_changed.emit(
                        change.host,
                        change.previous or "",
                        change.current,
                    )
                    # Record availability transitions in device audit trail
                    if _known is None:
                        continue
                    try:
                        from modules.device_tracker import record_event as _rec_ev
                        _mac = next(
                            (kd.mac for kd in _known.values()
                             if kd.ip == change.host),
                            None,
                        )
                        if _mac:
                            if change.current in ("DOWN", "DEGRADED"):
                                _rec_ev(_mac, "went_offline",
                                        change.previous or "", change.current,
                                        "availability", self._monitor._store)
                            elif change.current in ("UP", "RECOVERED"):
                                _rec_ev(_mac, "came_online",
                                        change.previous or "", change.current,
                                        "availability", self._monitor._store)
                    except Exception:
                        pass  # non-fatal — audit trail is best-effort
            except Exception as exc:  # noqa: BLE001
                self.error.emit(str(exc))

            # Interruptible sleep — check stop flag every second
            for _ in range(interval):
                if self._stop_requested:
                    return
                time.sleep(1)
