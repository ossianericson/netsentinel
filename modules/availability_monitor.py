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
from typing import Callable, Dict, List, Optional, Sequence

from modules.network_logger import _ping_once as _ping   # reuse existing ping helper
from modules.network_logger import _ping_jitter          # 3-sample stddev, JITTER_HIGH
from modules.metric_store import MetricStore
from modules.device_baseline import DOWN_CONFIRMATION_CYCLES
from modules.evidence import EvidenceGate


# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_INTERVAL_S        = 60      # seconds between scan cycles
DEFAULT_DEGRADED_THRESHOLD = 150.0  # ms above which a host is DEGRADED not UP
DEFAULT_TARGETS = ["8.8.8.8", "1.1.1.1"]

# States meaning "the host answered". Used by the Phase 3b DOWN confirmation to
# decide whether there is a reachable prior state worth holding.
_REACHABLE_STATES = ("UP", "DEGRADED")


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
    threshold_provider : callable | None
        Signal Quality Phase 3b. callable(host) -> DEGRADED threshold in ms,
        normally `DeviceBaselines.degraded_threshold`. None (the default) uses
        each target's own `degraded_threshold_ms`, i.e. the global 150 ms
        constant — the behaviour every release up to now has shipped.
    confirm_down : bool
        Signal Quality Phase 3b. When True, a host must fail
        `DOWN_CONFIRMATION_CYCLES` consecutive checks before it is *classified*
        DOWN. One dropped ping is a dropped ping, not an outage. The raw RTT is
        never altered — only the classification waits.
    """

    def __init__(
        self,
        store: MetricStore,
        targets: Optional[List[TargetConfig]] = None,
        interval_s: int = DEFAULT_INTERVAL_S,
        on_cycle: Optional[Callable[[CycleResult], None]] = None,
        threshold_provider: Optional[Callable[[str], float]] = None,
        confirm_down: bool = False,
        jitter_hosts: Optional[Sequence[str]] = None,
    ):
        self._store     = store
        self._targets   = targets or [TargetConfig(h) for h in DEFAULT_TARGETS]
        self.interval_s = interval_s
        self._on_cycle  = on_cycle
        # Hosts to measure jitter for. Bounded on purpose — see run_cycle().
        self._jitter_hosts = frozenset(jitter_hosts or ())
        # host → current state string (UP / DEGRADED / DOWN / None)
        self._current_state: Dict[str, Optional[str]] = {}
        # ── Signal Quality Phase 3b (both off by default — RULE-EXP1) ─────────
        self._threshold_provider = threshold_provider
        self._down_gate: Optional[EvidenceGate] = (
            EvidenceGate(min_consecutive=DOWN_CONFIRMATION_CYCLES)
            if confirm_down else None
        )

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

        rtt_sample/device_state writes for the whole cycle are flushed once,
        in a single transaction, via record_availability_cycle() (Phase B1 —
        was 2 commits/target/cycle). record_device_event stays per-transition:
        it is rare and event ordering matters.
        """
        now    = int(time.time())
        result = CycleResult(ts=now)
        rtt_rows:   list = []
        state_rows: list = []

        for cfg in list(self._targets):
            # Jitter costs three ping.exe invocations instead of one, and this
            # loop is sequential with a 2 s timeout per probe — so it is
            # collected only for the nominated hosts (gateway + internet
            # targets). Measuring every LAN device would put worst-case cycle
            # time past the 60 s interval whenever several hosts are down.
            if cfg.host in self._jitter_hosts:
                rtt_ms, jitter_ms = _ping_jitter(cfg.host)
            else:
                rtt_ms, jitter_ms = _ping(cfg.host), -1.0
            new_state = self._classify_confirmed(cfg, rtt_ms, now)

            rtt_rows.append({"host": cfg.host, "rtt_ms": rtt_ms,
                             "jitter_ms": jitter_ms, "ts": now})
            state_rows.append({
                "ip": cfg.host,
                "mac": cfg.mac,
                "hostname": cfg.hostname or cfg.label or None,
                "state": new_state,
                "rtt_ms": rtt_ms if rtt_ms >= 0 else None,
                "ts": now,
            })

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

        self._store.record_availability_cycle(rtt_rows, state_rows)

        if self._on_cycle:
            self._on_cycle(result)

        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _threshold_for(self, cfg: TargetConfig) -> float:
        """The DEGRADED threshold to apply to `cfg` this cycle.

        Phase 3b: a learned per-device threshold when a provider is injected,
        otherwise the target's own (global 150 ms) value. A provider that raises
        must never take the monitoring loop down — it is an optimisation, and
        falling back to the global constant is exactly the old behaviour.
        """
        if self._threshold_provider is not None:
            try:
                return float(self._threshold_provider(cfg.host))
            except Exception:
                pass  # no baseline available — fall back to the fixed threshold
        return cfg.degraded_threshold_ms

    def _classify_confirmed(
        self, cfg: TargetConfig, rtt_ms: float, now: int
    ) -> str:
        """Classify `rtt_ms`, holding an unconfirmed DOWN at the prior state.

        Phase 3b. A device is not offline until it has failed to answer
        `DOWN_CONFIRMATION_CYCLES` times running; until then the monitor keeps
        reporting the last reachable state, so a single dropped ping produces no
        DOWN event and no matching RECOVERED. That pair, repeated, is most of
        the 1,226 DOWN/RECOVERED events measured on the reference network.

        Only a transition *into* DOWN from a reachable state is debounced. A
        host that is already DOWN stays DOWN, and a first-ever observation is
        reported as it is measured — there is no prior reachability to hold, and
        claiming UP would invent one.

        The `rtt_sample` row keeps the raw `-1` either way: this changes the
        classification, never the measurement.
        """
        raw_state = self._classify(rtt_ms, self._threshold_for(cfg))
        if self._down_gate is None:
            return raw_state

        evidence = self._down_gate.observe(cfg.host, raw_state == "DOWN", now)
        if raw_state != "DOWN":
            return raw_state

        previous = self._current_state.get(cfg.host)
        if (
            previous in _REACHABLE_STATES
            and evidence.consecutive < DOWN_CONFIRMATION_CYCLES
        ):
            return previous
        return raw_state

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
