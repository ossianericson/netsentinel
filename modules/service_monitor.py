"""
ServiceMonitor — scheduled TCP service/port heartbeat checker (T2#7).

Periodically checks whether specific host:port pairs accept a TCP connection
and persists results to MetricStore. No admin privileges required.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected as constructor parameter.
  • All I/O in run_check(); callers decide scheduling.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from modules.metric_store import MetricStore


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ServiceTarget:
    """A single service to monitor."""
    host:    str
    port:    int
    label:   str = ""           # human name, e.g. "HTTP", "SSH", "Plex"
    timeout: float = 3.0        # TCP connect timeout in seconds

    def __post_init__(self):
        if not self.label:
            self.label = f"{self.host}:{self.port}"


@dataclass
class ServiceResult:
    """Outcome of one TCP check."""
    host:   str
    port:   int
    label:  str
    up:     bool
    rtt_ms: Optional[float]    # connect latency; None when unreachable
    error:  str                # empty string on success
    ts:     int = field(default_factory=lambda: int(time.time()))


# ── TCP check ─────────────────────────────────────────────────────────────────

def check_tcp(host: str, port: int, timeout: float = 3.0) -> tuple[bool, Optional[float], str]:
    """
    Attempt a TCP connection to host:port.

    Returns
    -------
    (up, rtt_ms, error)
        up      — True if the connection succeeded
        rtt_ms  — connect latency in ms; None if unreachable
        error   — empty string on success; error message otherwise
    """
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            rtt = (time.monotonic() - t0) * 1000.0
            return True, round(rtt, 2), ""
    except (ConnectionRefusedError, socket.timeout, OSError) as exc:
        return False, None, str(exc)


# ── ServiceMonitor ────────────────────────────────────────────────────────────

class ServiceMonitor:
    """
    Runs TCP checks for a list of ServiceTarget hosts and persists
    results to the MetricStore.

    Parameters
    ----------
    store : MetricStore
        Injected MetricStore singleton.
    targets : list[ServiceTarget]
        Services to check.
    on_result : callable | None
        Called synchronously with the full list of ServiceResult after each run.
    """

    def __init__(
        self,
        store: MetricStore,
        targets: Optional[List[ServiceTarget]] = None,
        on_result: Optional[Callable[[List[ServiceResult]], None]] = None,
    ):
        self._store     = store
        self._targets   = list(targets or [])
        self._on_result = on_result

    # ── Public API ────────────────────────────────────────────────────────────

    def set_targets(self, targets: List[ServiceTarget]) -> None:
        self._targets = list(targets)

    def get_targets(self) -> List[ServiceTarget]:
        return list(self._targets)

    def run_check(self) -> List[ServiceResult]:
        """
        Check all configured targets. Persists each result to MetricStore.
        Returns the full list of ServiceResult objects.
        """
        results: List[ServiceResult] = []
        now = int(time.time())
        for target in self._targets:
            up, rtt_ms, error = check_tcp(target.host, target.port, target.timeout)
            result = ServiceResult(
                host=target.host,
                port=target.port,
                label=target.label,
                up=up,
                rtt_ms=rtt_ms,
                error=error,
                ts=now,
            )
            self._store.record_service_check(
                host=target.host,
                port=target.port,
                up=up,
                rtt_ms=rtt_ms,
                label=target.label,
                error=error or None,
                ts=now,
            )
            results.append(result)

        if self._on_result:
            self._on_result(results)

        return results
