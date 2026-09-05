"""Bound the app-data logs that otherwise grow forever (A4).

Nothing in shipped code rotated anything — no ``RotatingFileHandler``, no ``maxBytes``,
no age pruning — so every diagnostic sink grew for the life of the install. Measured on
a real one: a 6.78 MB crash log, a 4.08 MB theme-switch log still growing that day, and
roughly a megabyte each of stderr, shutdown and scan-timing history.

Two design choices carry all the risk here, and both are deliberate.
"""
from __future__ import annotations

import os

__all__ = ["MAX_LOG_BYTES", "EXEMPT_LOGS", "rotate_logs"]

#: Rotate a log only once it passes this. The threshold is the safety mechanism, not a
#: tuning knob: `netsentinel_exceptions.log` sits at ~58 KB and chaos-run verification
#: reads its mtime, so a bound well above normal size means rotation cannot fire during
#: a run and behaviour there stays byte-identical to before this module existed.
MAX_LOG_BYTES = 2 * 1024 * 1024

#: Never rotated, for reasons specific to each.
EXEMPT_LOGS = frozenset({
    # The only detector for native SEH faults is monkey_test.py::_check_crash_log(),
    # which baselines this file's BYTE SIZE at run start and seeks to that offset. A
    # rotation makes the shrink read as "nothing new" and leaves a stale, too-large
    # baseline, so every later fault in that run is invisible. The harness restarts the
    # app mid-run, so rotate-on-start would fire mid-run and disarm the project's
    # primary stability gate. Bound the diagnostic *report* instead (B2 tails it).
    "netsentinel_crash.log",
    # app.py truncates this fresh on every launch (RULE-TM1) and the harness salvages it
    # across restarts; a second lifecycle owner would fight both.
    "tracemalloc_snapshots.log",
    # User-authored content, not a log — the feedback dialog's saved text.
    "feedback.log",
})


def rotate_logs(directory: str | None = None) -> list:
    """Move every oversized, non-exempt log aside, keeping one generation.

    Returns the names rotated. Best-effort throughout: this runs on the startup path of
    every entry point, and housekeeping must never be the reason an app fails to launch.
    """
    try:
        if directory is None:
            from modules.utils import get_app_data_dir

            directory = str(get_app_data_dir())
        names = os.listdir(directory)
    except OSError:
        return []  # no app-data dir yet: nothing to bound, and nothing to fail over

    rotated = []
    for name in names:
        if not name.endswith(".log") or name in EXEMPT_LOGS:
            continue
        path = os.path.join(directory, name)
        try:
            if os.path.getsize(path) <= MAX_LOG_BYTES:
                continue
            # os.replace overwrites any existing generation atomically, which is what
            # keeps exactly one and never leaves a half-rotated pair behind.
            os.replace(path, path + ".1")
            rotated.append(name)
        except OSError:
            continue  # in use by another process, or gone since listdir — skip it
    return rotated
