"""
maintenance_window — suppresses AlertEngine alerts during defined maintenance periods.

A MaintenanceWindow is a named, time-bounded suppression entry for one or more
hosts (or ALL hosts).  During an active window, alerts whose host matches the
window are silently dropped — they are logged in the suppression log but not
dispatched to notification channels.

Persistence
-----------
Windows are serialised to/from a plain JSON list and stored by the UI layer
via QSettings("NetSentinel", "NetSentinel") key "maintenance/windows_json".
This module is persistence-agnostic — it receives and returns plain dicts /
dataclass instances.

Architecture rules
------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • Thread-safe: all mutations go through a threading.Lock.
  • AlertEngine integration: inject via alert_engine.set_maintenance_checker(mw.is_suppressed).
"""
from __future__ import annotations

import json
import time
import threading
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class MaintenanceWindow:
    """
    Describes a suppression window for one or more hosts.

    Fields
    ------
    id          : unique UUID string (auto-generated)
    label       : human name, e.g. "Router firmware upgrade"
    hosts       : list of IP / hostname strings; empty list = ALL hosts
    start_ts    : Unix timestamp — window opens at this time
    end_ts      : Unix timestamp — window closes at this time
    created_ts  : when the window was created (for audit log)
    active      : True = enabled; False = manually disabled without deletion
    daily_start_hour : 0-23 local wall-clock hour — set together with
                       daily_end_hour to make this a RECURRING daily window
                       (e.g. nightly quiet hours) instead of a one-off absolute
                       start_ts/end_ts window.  None (default) = not recurring.
    daily_end_hour   : 0-23 local wall-clock hour, exclusive end of the daily
                       window.  None (default) = not recurring.
    """
    label:      str
    start_ts:   int   # UTC Unix epoch seconds — MUST be stored as UTC, not local time
    end_ts:     int   # UTC Unix epoch seconds — MUST be stored as UTC, not local time
    hosts:      List[str]  = field(default_factory=list)
    id:         str        = field(default_factory=lambda: str(uuid.uuid4()))
    created_ts: int        = field(default_factory=lambda: int(time.time()))
    active:     bool       = True
    daily_start_hour: Optional[int] = None  # local hour 0-23 — recurring mode only
    daily_end_hour:   Optional[int] = None  # local hour 0-23 — recurring mode only

    @property
    def is_currently_active(self) -> bool:
        """True if this window is enabled and right now falls inside the window.

        Two modes:

        1. Absolute (default) — comparison is UTC-vs-UTC: time.time() always
           returns UTC epoch seconds, and start_ts/end_ts must also be UTC
           epoch seconds.  The UI layer must convert local QDateTimeEdit
           values with:
               dt.replace(tzinfo=timezone.utc).timestamp()
           or equivalent — never with naive datetime.timestamp() which
           interprets the value in the local timezone and shifts by the UTC
           offset.

        2. Recurring daily (when daily_start_hour/daily_end_hour are both
           set) — deliberately checked against LOCAL wall-clock hour via
           time.localtime(), NOT UTC.  This is an intentional, isolated
           exception to the UTC rule above: quiet hours ("don't page me
           between 11pm and 7am") are inherently a local-time concept tied to
           when the user is asleep, not a fixed instant in UTC.  Do not
           "fix" this back to time.gmtime()/UTC — that would make quiet
           hours drift with DST and make the feature useless for its actual
           purpose.  start_ts/end_ts are ignored entirely in this mode.
        """
        if not self.active:
            return False
        if self.daily_start_hour is not None and self.daily_end_hour is not None:
            hour = time.localtime().tm_hour
            start, end = self.daily_start_hour, self.daily_end_hour
            if start <= end:
                # Same-day window, e.g. 09:00-17:00 -> [9, 17)
                return start <= hour < end
            # Overnight wraparound, e.g. 23:00-07:00 -> hours 23,0..6
            return hour >= start or hour < end
        now = int(time.time())
        return self.start_ts <= now <= self.end_ts

    @property
    def duration_minutes(self) -> int:
        return max(0, (self.end_ts - self.start_ts) // 60)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MaintenanceWindow":
        _daily_start = d.get("daily_start_hour")
        _daily_end = d.get("daily_end_hour")
        return cls(
            label=d.get("label", ""),
            start_ts=int(d.get("start_ts", 0)),
            end_ts=int(d.get("end_ts", 0)),
            hosts=list(d.get("hosts", [])),
            id=d.get("id", str(uuid.uuid4())),
            created_ts=int(d.get("created_ts", int(time.time()))),
            active=bool(d.get("active", True)),
            daily_start_hour=int(_daily_start) if _daily_start is not None else None,
            daily_end_hour=int(_daily_end) if _daily_end is not None else None,
        )


# ── Suppression log entry ─────────────────────────────────────────────────────

@dataclass
class SuppressionEntry:
    """Record of an alert that was suppressed by a maintenance window."""
    ts:           int
    window_id:    str
    window_label: str
    host:         str
    rule_name:    str
    severity:     str
    message:      str


# ── Manager ───────────────────────────────────────────────────────────────────

class MaintenanceWindowManager:
    """
    Manages maintenance windows and provides a suppression check callable.

    Usage::

        mw = MaintenanceWindowManager()
        mw.load_from_json(qs.value("maintenance/windows_json", "[]"))

        # Wire into AlertEngine (the engine calls this before dispatching)
        alert_engine.set_maintenance_checker(mw.is_suppressed)

        # Check manually:
        if mw.is_suppressed("192.168.1.1"):
            pass  # alert would be dropped
    """

    _LOG_MAX = 500

    def __init__(self) -> None:
        self._windows: List[MaintenanceWindow] = []
        self._lock = threading.Lock()
        self._suppression_log: List[SuppressionEntry] = []

    # ── Window CRUD ───────────────────────────────────────────────────────────

    def add_window(self, window: MaintenanceWindow) -> None:
        with self._lock:
            self._windows.append(window)

    def remove_window(self, window_id: str) -> bool:
        with self._lock:
            before = len(self._windows)
            self._windows = [w for w in self._windows if w.id != window_id]
            return len(self._windows) < before

    def update_window(self, window: MaintenanceWindow) -> None:
        with self._lock:
            self._windows = [window if w.id == window.id else w
                             for w in self._windows]

    def get_windows(self) -> List[MaintenanceWindow]:
        with self._lock:
            return list(self._windows)

    def get_active_windows(self) -> List[MaintenanceWindow]:
        with self._lock:
            return [w for w in self._windows if w.is_currently_active]

    # ── Suppression check ─────────────────────────────────────────────────────

    def is_suppressed(self, host: str) -> Optional[str]:
        """
        Return the window label if `host` is currently under maintenance,
        or None if not suppressed.

        Passing this method to AlertEngine::set_maintenance_checker means
        the engine can call is_suppressed(host) before firing an alert.
        """
        with self._lock:
            for w in self._windows:
                if not w.is_currently_active:
                    continue
                # Empty hosts list = all hosts
                if not w.hosts or host in w.hosts:
                    return w.label
        return None

    def record_suppression(
        self,
        window_id: str,
        window_label: str,
        host: str,
        rule_name: str,
        severity: str,
        message: str,
    ) -> None:
        entry = SuppressionEntry(
            ts=int(time.time()),
            window_id=window_id,
            window_label=window_label,
            host=host,
            rule_name=rule_name,
            severity=severity,
            message=message,
        )
        self._suppression_log.append(entry)
        if len(self._suppression_log) > self._LOG_MAX:
            self._suppression_log = self._suppression_log[-self._LOG_MAX:]

    def get_suppression_log(self) -> List[SuppressionEntry]:
        return list(self._suppression_log)

    def clear_suppression_log(self) -> None:
        self._suppression_log.clear()

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_json(self) -> str:
        with self._lock:
            return json.dumps([w.to_dict() for w in self._windows])

    def load_from_json(self, raw: str) -> None:
        try:
            items = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            items = []
        with self._lock:
            self._windows = [MaintenanceWindow.from_dict(d) for d in items if isinstance(d, dict)]

    # ── Convenience: expire old (past-end) windows ────────────────────────────

    def purge_expired(self, older_than_days: int = 7) -> int:
        """Remove windows that ended more than `older_than_days` days ago."""
        cutoff = int(time.time()) - older_than_days * 86400
        with self._lock:
            before = len(self._windows)
            self._windows = [w for w in self._windows if w.end_ts >= cutoff]
            return before - len(self._windows)
