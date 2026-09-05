"""Per-session lifecycle records, so a silent death leaves evidence (A1).

The app could not tell "the user quit" from "Windows killed us for memory" from a native
FailFast — exactly the classes Partner Center labels `Unknown`, and exactly the classes
that produce no traceback and no `faulthandler` entry. The recorded Store baseline was 8
memory failures and 5 hangs, none of which left a single byte anywhere on disk.

A record is written `clean_exit: false` at start and only ever flipped by an explicit
shutdown, so *not* being marked clean is the signal. `heartbeat()` then carries the last
page the user was on, which is the only thing that will ever say *where* they were when
the process was taken.

Pure Python by requirement, not by preference: `modules/` cannot import PyQt (ARCH
RULE 1), and the clean-exit write must happen inside `ui/shutdown.py`'s drain because
`Dashboard.closeEvent()` ends in `os._exit(0)`, which skips `atexit`.
"""
from __future__ import annotations

import json
import os
import time
import uuid

__all__ = [
    "sessions_dir",
    "begin_session",
    "heartbeat",
    "end_session_clean",
    "find_unclean_sessions",
]

#: How many records to keep. Ten is well past what anything reads — B1 names the most
#: recent one and B2 tails a handful — and one file per launch with no bound is how the
#: other eight logs reached ~6.78 MB.
MAX_SESSIONS = 10

#: Path of the record for the session in progress. None until begin_session() runs.
_current_path: str | None = None


def sessions_dir() -> str:
    """The directory holding session records (RULE 23: under get_app_data_dir())."""
    from modules.utils import get_app_data_dir

    path = os.path.join(str(get_app_data_dir()), "sessions")
    os.makedirs(path, exist_ok=True)
    return path


def _write(path: str, record: dict) -> None:
    """Write one record. utf-8 named explicitly — the path itself may be non-Latin."""
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        json.dump(record, f)


def _read(path: str) -> dict | None:
    """One record, or None if it is missing, unreadable or not valid JSON."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _update(**fields) -> None:
    """Merge *fields* into the in-progress record. Silent when there is nothing to update.

    Read-modify-write rather than append: the record is a handful of keys and is read
    only by the next launch, so the cost is one small file write and there is no partial
    state to reconcile. A process killed inside this call leaves a truncated file, which
    ``find_unclean_sessions()`` is required to tolerate.
    """
    if _current_path is None:
        return
    record = _read(_current_path)
    if record is None:
        return
    record.update(fields)
    try:
        _write(_current_path, record)
    except OSError:
        pass  # instrumentation must never break the path it is instrumenting


def begin_session(app_version: str = "") -> str | None:
    """Open a record for this run, marked unclean until something says otherwise.

    Call it **after** the single-instance mutex gate (RULE-WIN16), never before: a
    losing duplicate launch exits without ever building a GUI, and a record written
    ahead of that gate would be left behind as a phantom unclean exit on every impatient
    double-click — turning the very case the mutex exists to handle into a false crash
    report.
    """
    global _current_path
    from modules.environment_fingerprint import fingerprint

    record = {
        "started_at": time.time(),
        "app_version": app_version,
        "clean_exit": False,
        "environment": fingerprint(),
    }
    try:
        path = os.path.join(sessions_dir(), f"{uuid.uuid4().hex}.json")
        _write(path, record)
    except OSError:
        return None  # no app-data dir: record nothing rather than fail the launch
    _current_path = path
    _prune()
    return path


def _prune() -> None:
    """Drop all but the newest MAX_SESSIONS records. Best-effort, never fatal.

    Ordered by mtime rather than the record's own ``started_at``: a record truncated by
    the kill this module exists to catch has no parseable start time, and the pruner
    must not be the one thing that cannot read it.
    """
    try:
        directory = sessions_dir()
        paths = [os.path.join(directory, n) for n in os.listdir(directory)]
        paths.sort(key=os.path.getmtime, reverse=True)
        for stale in paths[MAX_SESSIONS:]:
            if stale != _current_path:
                os.remove(stale)
    except OSError:
        pass  # housekeeping only — a failure here must not disturb the launch


def heartbeat(page_label: str) -> None:
    """Record the page the user just navigated to, and when.

    Wired to `ui/nav/builder.py::_nav_rail_go_to`, so this runs on the GUI thread on
    every navigation — it stays one small file rewrite for that reason.
    """
    _update(last_page=page_label, last_beat=time.time())


def end_session_clean() -> None:
    """Mark the in-progress record as a real shutdown. The only writer of the flag.

    Called from ``ui/shutdown.py``, not from ``atexit``: ``Dashboard.closeEvent()`` ends
    in ``os._exit(0)``, which skips ``atexit`` handlers entirely.
    """
    _update(clean_exit=True, ended_at=time.time())


def find_unclean_sessions() -> list:
    """Records from previous runs that were never marked clean, newest first.

    The session in progress is excluded: it is unclean by construction until shutdown,
    and reporting it would make every launch look like a crash.
    """
    try:
        directory = sessions_dir()
        names = os.listdir(directory)
    except OSError:
        return []  # no app-data dir: nothing to report, and nothing to fail over
    found = []
    for name in names:
        path = os.path.join(directory, name)
        if path == _current_path:
            continue
        record = _read(path)
        # A record killed mid-write is the expected artefact of the very failure this
        # module exists to catch — skip it, never let it abort the scan.
        if record is not None and not record.get("clean_exit"):
            found.append(record)
    # uuid4 filenames sort randomly, so directory order carries no chronology at all.
    found.sort(key=lambda r: r.get("started_at") or 0, reverse=True)
    return found
