"""
AvailabilityMonitor — continuous background device availability tracker.

Pings a list of targets on a configurable interval. For each cycle it:
  1. Pings each target.
  2. Computes state: UP / DEGRADED / DOWN.
  3. Writes an rtt_sample and device_state row to MetricStore.
  4. When state *changes*, writes a device_event row.
  5. Returns a list of StateChange objects so callers can react (alerts, UI).

State machine per device:
  • UP         — last ping succeeded, RTT ≤ degraded_threshold_ms
  • DEGRADED   — last ping succeeded but RTT > degraded_threshold_ms
  • DOWN       — last ping failed

State transitions that emit events:
  UP   → DEGRADED  : event DEGRADED
  UP   → DOWN      : event DOWN
  DEGRADED → DOWN  : event DOWN
  DEGRADED → UP    : event RECOVERED
  DOWN → UP        : event RECOVERED
  DOWN → DEGRADED  : event RECOVERED  (note: still emits RECOVERED to clear the down)
  None → *         : no event (first seen)

This module is pure Python — no PyQt imports.
The QThread wrapper lives in workers/availability_worker.py.

Architecture note (ARCH RULE 1 + 2):
  This module does NOT import PyQt6 or ui/.
  The MetricStore instance is injected — never created here.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from modules.network_logger import _ping_once as _ping   # reuse existing ping helper
from modules.metric_store import MetricStore


# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_INTERVAL_S        = 60      # seconds between scan cycles
DEFAULT_DEGRADED_THRESHOLD = 150.0  # ms above which a host is DEGRADED not UP
DEFAULT_TARGETS = ["8.8.8.8", "1.1.1.1"]


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class TargetConfig:
    host: str
    label: str = ""           # friendly name shown in UI; falls back to host
    degraded_threshold_ms: float = DEFAULT_DEGRADED_THRESHOLD
    mac: Optional[str] = None
    hostname: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.label or self.host


@dataclass
class StateChange:
    """Emitted when a target's state changes."""
    host: str
    previous: Optional[str]   # None on first seen
    current: str
    event_type: str            # JOINED / DOWN / DEGRADED / RECOVERED
    rtt_ms: float
    ts: int


@dataclass
class CycleResult:
    """Result of one full monitoring cycle across all targets."""
    ts: int
    changes: List[StateChange] = field(default_factory=list)
    states: Dict[str, str]    = field(default_factory=dict)  # host → state
    rtts:   Dict[str, float]  = field(default_factory=dict)  # host → rtt_ms


# ── Core monitoring logic ─────────────────────────────────────────────────────

class AvailabilityMonitor:
    """
    Stateful availability monitor. Call run_cycle() periodically (from a thread).

    Parameters
    ----------
    store : MetricStore
        Injected MetricStore singleton.
    targets : list[TargetConfig]
        Hosts to monitor.
    interval_s : int
        Seconds between cycles (used by callers to schedule; not enforced here).
    on_cycle : callable | None
        Optional callback(CycleResult) invoked after each cycle completes.
        Called synchronously — keep it fast (queue work, don't block).
    """

    def __init__(
        self,
        store: MetricStore,
        targets: Optional[List[TargetConfig]] = None,
        interval_s: int = DEFAULT_INTERVAL_S,
        on_cycle: Optional[Callable[[CycleResult], None]] = None,
    ):
        self._store     = store
        self._targets   = targets or [TargetConfig(h) for h in DEFAULT_TARGETS]
        self.interval_s = interval_s
        self._on_cycle  = on_cycle
        # host → current state string (UP / DEGRADED / DOWN / None)
        self._current_state: Dict[str, Optional[str]] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def set_targets(self, targets: List[TargetConfig]) -> None:
        """Replace the target list. Thread-safe if called between cycles."""
        self._targets = list(targets)

    def get_current_states(self) -> Dict[str, Optional[str]]:
        """Return a snapshot of the last known state per host."""
        return dict(self._current_state)

    def run_cycle(self) -> CycleResult:
        """
        Ping all targets once, update MetricStore, return a CycleResult.
        Designed to be called in a loop from a background thread.
        """
        now    = int(time.time())
        result = CycleResult(ts=now)

        for cfg in list(self._targets):
            rtt_ms = _ping(cfg.host)
            new_state = self._classify(rtt_ms, cfg.degraded_threshold_ms)

            # Record raw sample + state snapshot
            self._store.record_rtt(cfg.host, rtt_ms)
            self._store.record_device_state(
                ip=cfg.host,
                mac=cfg.mac,
                hostname=cfg.hostname or cfg.label or None,
                state=new_state,
                rtt_ms=rtt_ms if rtt_ms >= 0 else None,
                ts=now,
            )

            result.states[cfg.host] = new_state
            result.rtts[cfg.host]   = rtt_ms

            # State change detection
            prev = self._current_state.get(cfg.host)
            if prev is not None and prev != new_state:
                event_type = self._event_for_transition(prev, new_state)
                self._store.record_device_event(
                    ip=cfg.host,
                    event_type=event_type,
                    mac=cfg.mac,
                    detail=f"RTT={rtt_ms:.1f}ms  prev={prev}",
                    ts=now,
                )
                change = StateChange(
                    host=cfg.host,
                    previous=prev,
                    current=new_state,
                    event_type=event_type,
                    rtt_ms=rtt_ms,
                    ts=now,
                )
                result.changes.append(change)

            self._current_state[cfg.host] = new_state

        if self._on_cycle:
            self._on_cycle(result)

        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _classify(rtt_ms: float, degraded_threshold: float) -> str:
        if rtt_ms < 0:
            return "DOWN"
        if rtt_ms > degraded_threshold:
            return "DEGRADED"
        return "UP"

    @staticmethod
    def _event_for_transition(prev: str, curr: str) -> str:
        if curr == "DOWN":
            return "DOWN"
        if curr in ("UP", "DEGRADED") and prev == "DOWN":
            return "RECOVERED"
        if curr == "DEGRADED" and prev == "UP":
            return "DEGRADED"
        if curr == "UP" and prev == "DEGRADED":
            return "RECOVERED"
        return "UP"
