"""App-health conditions: "NetSentinel can't see X" held as state (D1, D3).

A network alert says something about the network. An app-health condition says the
app has lost the ability to look: a monitor whose checks fail, a listener that could
not bind, a notification channel that stopped delivering, a credential store that
refuses writes. D1 keeps the two apart — ``INFRA_UNREACHABLE`` stays an alert.

Before this registry each of those producers already *detected* its failure and then
had nowhere to put it. The status bar is a single line the next progress update
overwrites (matrix row F2-G6); a log record is history, not state; the delivery log is
capped and in-memory. None of them can answer "what is broken *right now*".

The registry answers exactly that, and nothing more:

* **One condition per key**, however often it fires — a count and a ``last_seen``, never
  a row per retry.
* **Resolved by the first success.** A failure after that opens a new episode, so
  ``first_seen`` describes the current outage, not the first one ever recorded.
* **Subscribers hear transitions only** — raised and resolved, never a repeat. A
  surface that repaints per retry is the noise D2 exists to avoid. They are called on
  the reporting thread and outside the lock, so a subscriber may read the registry;
  a Qt surface must marshal to the GUI thread itself.
* **In memory only** (D3). A condition is about this process's ability to see; the
  next launch re-derives it from the producers within one interval.

Producers live in ``app.py`` and the notification router. This module has no PyQt
import (ARCH RULE 1); the surface that reads it arrives in S4.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Optional

__all__ = ["SEVERITIES", "ConditionSpec", "Condition", "AppHealth"]

_log = logging.getLogger(__name__)

#: RULE-A3's canonical UI set, most severe first. Not the internal risk levels
#: (``HIGH``/``STORM``/``CLEAN``…) — those never reach a user as a severity label.
SEVERITIES = ("Critical", "High", "Warning", "Info")


@dataclass(frozen=True)
class ConditionSpec:
    """The fixed, reviewable text of one condition — everything except the raw error."""

    key: str
    source: str
    severity: str
    what: str
    why: str
    next_step: str
    cta_label: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(
                f"{self.key}: severity {self.severity!r} is not one of {SEVERITIES} (RULE-A3)"
            )


@dataclass(frozen=True)
class Condition:
    """An immutable snapshot of one condition. Safe to hand across threads."""

    key: str
    source: str
    severity: str
    what: str
    why: str
    next_step: str
    cta_label: str
    detail: str
    first_seen: float
    last_seen: float
    count: int
    resolved_at: Optional[float] = None


class AppHealth:
    """Registry of app-health conditions. Instantiate once in the entry point and inject."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._conditions: Dict[str, Condition] = {}
        self._subscribers: List[Callable[[Condition], None]] = []

    def subscribe(self, callback: Callable[[Condition], None]) -> None:
        """Call ``callback(condition)`` whenever a condition is raised or resolved."""
        with self._lock:
            self._subscribers.append(callback)

    def report_failure(self, spec: ConditionSpec, detail: str = "") -> Condition:
        now = self._clock()
        with self._lock:
            prev = self._conditions.get(spec.key)
            raised = prev is None or prev.resolved_at is not None
            if raised:
                cond = Condition(
                    key=spec.key, source=spec.source, severity=spec.severity,
                    what=spec.what, why=spec.why, next_step=spec.next_step,
                    cta_label=spec.cta_label, detail=detail,
                    first_seen=now, last_seen=now, count=1,
                )
            else:
                # Same episode, newest text: a condition whose cause changed mid-outage
                # should describe the cause that is true now.
                cond = replace(
                    prev, source=spec.source, severity=spec.severity, what=spec.what,
                    why=spec.why, next_step=spec.next_step, cta_label=spec.cta_label,
                    detail=detail, last_seen=now, count=prev.count + 1,
                )
            self._conditions[spec.key] = cond
        if raised:
            self._notify(cond)
        return cond

    def report_ok(self, key: str) -> Optional[Condition]:
        now = self._clock()
        with self._lock:
            prev = self._conditions.get(key)
            if prev is None or prev.resolved_at is not None:
                return None
            cond = replace(prev, resolved_at=now)
            self._conditions[key] = cond
        self._notify(cond)
        return cond

    def get(self, key: str) -> Optional[Condition]:
        with self._lock:
            return self._conditions.get(key)

    def active(self) -> List[Condition]:
        """Unresolved conditions, most severe first, then longest-standing first."""
        with self._lock:
            live = [c for c in self._conditions.values() if c.resolved_at is None]
        return sorted(live, key=lambda c: (SEVERITIES.index(c.severity), c.first_seen))

    def _notify(self, cond: Condition) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(cond)
            except Exception:
                # A broken surface must not take the registry — or the other
                # subscribers — down with it. Logged with the traceback (RULE-SURF2).
                _log.exception("app-health subscriber failed on %s", cond.key)
