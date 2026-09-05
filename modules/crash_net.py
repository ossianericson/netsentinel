"""The shared crash net installed by every NetSentinel entry point (A3).

Sinks previously defined inside ``app.py::main()``, and therefore reaching only
``NetSentinel.exe``. ``cli.py`` and ``svc.py`` installed none of it and were entirely
silent in the field — ``svc.py`` unattended as a Windows service, where nobody is
present to notice.

**Encoding is load-bearing here, not incidental.** A traceback carries the source line
of every frame, exception ``str()`` values and file paths, so it routinely holds
characters the ANSI codepage cannot represent — this repo's own ``→``/``✅`` literals,
and ``%LOCALAPPDATA%`` on a machine whose username is not Latin. A handler of last
resort that raises while recording an error destroys the only evidence there was
(RULE-WIN19, RULE-WIN24).
"""
from __future__ import annotations

import datetime
import os
import sys
import threading
import traceback
from typing import Callable, Optional

#: Kept alive for the process lifetime — faulthandler writes to the raw fd.
_crash_log_fd = None

__all__ = [
    "crash_log_path",
    "exceptions_log_path",
    "record_exception",
    "install",
]


def _app_dir() -> str:
    """The app-data directory, or the temp dir if it cannot be resolved (RULE 23)."""
    try:
        from modules.utils import get_app_data_dir

        return str(get_app_data_dir())
    except Exception:
        import tempfile

        return tempfile.gettempdir()


def crash_log_path() -> str:
    """Native-fault log. Append-only and deliberately never rotated.

    ``tools/monkey_test.py::_check_crash_log()`` is the only detector for native SEH
    faults, and it works by baselining this file's **byte size** at run start and
    seeking to that offset. Truncating or rotating it makes a shrink read as "nothing
    new" while the stale baseline stays large, so every later fault in that run goes
    unseen. Bound the diagnostic *report* instead of the file.
    """
    return os.path.join(_app_dir(), "netsentinel_crash.log")


def exceptions_log_path() -> str:
    """Python-level unhandled-exception log, for the main thread and any other thread."""
    return os.path.join(_app_dir(), "netsentinel_exceptions.log")


def record_exception(header: str, text: str) -> None:
    """Append one entry. Must never raise — it is the recorder of last resort."""
    try:
        stamp = datetime.datetime.now().isoformat()
        with open(exceptions_log_path(), "a", encoding="utf-8", errors="replace") as f:
            f.write(f"\n--- {stamp} {header} ---\n{text}")
    except Exception:
        pass  # non-fatal — a log-write failure must not mask the original error


def _enable_faulthandler() -> None:
    """Route native SEH faults to the crash log. No Python hook can catch these.

    On Windows this installs a **vectored (first-chance)** handler, so a fault the
    process then survives is still recorded — which is why the chaos harness treats any
    new entry as a failed run even when nothing crashed (RULE-WIN10, RULE-CHAOS2).
    """
    global _crash_log_fd
    import faulthandler

    try:
        # No encoding= on purpose: faulthandler writes bytes to the raw fd and never
        # touches the text codec, so naming one would be wrong, not merely redundant.
        # Append mode is load-bearing — see crash_log_path().
        # Deliberately never closed, and held in a module global so it cannot be
        # garbage-collected: faulthandler writes to this fd for the life of the
        # process, and a native fault arrives with no chance to reopen anything.
        # Closing it would disable the only detector for the SEH class the chaos
        # harness gates on. CodeQL py/file-not-closed flags the shape, not the
        # intent (alert 1637, dismissed as won't-fix).
        _crash_log_fd = open(crash_log_path(), "a")  # noqa: SIM115  # lgtm[py/file-not-closed]
        faulthandler.enable(file=_crash_log_fd)
    except Exception:
        faulthandler.enable()  # fallback: write to stderr


def install(on_unhandled: Optional[Callable[[str, str], None]] = None) -> None:
    """Install every sink. Safe to call from any entry point; safe to call twice.

    ``on_unhandled(title, message)`` is invoked **after** the record is written, so the
    traceback survives even if the notifier raises or the process dies inside it.
    ``cli.py`` and ``svc.py`` pass nothing; ``app.py`` passes its dialog, which is
    itself responsible for the RULE-WIN20 thread-affinity check — ``modules/`` cannot
    import PyQt (ARCH RULE 1), which is why this is a callback rather than a direct call.
    """
    _enable_faulthandler()

    def _excepthook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        record_exception("main", text)
        if on_unhandled is not None:
            try:
                on_unhandled("Unhandled Error", text)
            except Exception:
                pass  # a failing notifier must not lose the already-written record

    def _thread_excepthook(args):
        # SystemExit is how a thread is asked to stop; it is not a failure, and logging
        # it would bury real tracebacks in routine shutdown noise.
        if args.exc_type is SystemExit:
            return
        text = "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        )
        name = getattr(args.thread, "name", "?")
        record_exception(f"thread {name}", text)

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
