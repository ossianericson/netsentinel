"""The one formatted application log, configured by every entry point (D4).

Nothing in this tree configured root logging before this module existed. The
consequence is not "we log a bit less than we could" — it is that the diagnostic
record has **no shape at all**:

* ``log.warning`` fell through to ``logging.lastResort``, a ``StreamHandler`` on
  ``sys.stderr`` whose format is bare ``%(message)s``. Every warning the app has ever
  written landed in ``netsentinel_stderr.log`` with no timestamp, no level and no
  logger name. Two identical lines from two different builds are indistinguishable,
  and the file is append-only across installs, so nothing in it can be dated.
* ``debug`` and ``info`` were dropped outright at the default ``WARNING`` root level.
  That is why seven sites — five inside ``app.py`` plus ``ui/shutdown.py`` and
  ``ui/styles.py`` — each grew a private logger and ``FileHandler``, seven separate
  answers to "a bare ``log.info()`` goes nowhere", each re-solving formatting and
  rotation. Those stay as they are: they own dedicated files that are read on their
  own (the chaos harness reads the shutdown log by timestamp), and they all set
  ``propagate = False``, so none of them double-writes into this one.

What this buys, concretely: ``netsentinel_stderr.log``'s newest 2,000 lines hold 785
``Tight layout not applied`` warnings, and the fix for that flood is already in HEAD
(``bfe1dd1``). Nobody can tell whether current code still writes them. With a timestamp
and a logger name, that question is a one-line ``grep``.

Three design choices carry the risk, and each is deliberate.

**Additive, never a reset.** ``configure()`` adds one handler and never removes another.
``logging.basicConfig()`` is not used: it is a no-op when root already has handlers, and
its ``force=True`` form would tear out pytest's capture handler and the one
``tools/debug_launch.py`` installs — silently blinding the project's own commit gate.

**Root stays at WARNING; only NetSentinel's own package loggers drop to INFO.** Turning
root down to INFO recruits matplotlib's font manager, urllib3's connection pool and
PIL's plugin probing into the file at thousands of lines an hour, burying the record
this log exists to carry. Third-party *warnings* still land, because those are
diagnostic. ``NETSENTINEL_LOG_LEVEL=DEBUG`` opts the app's own loggers into debug — the
switch that makes RULE-SURF2's "log at debug with ``exc_info``" a real outcome rather
than a polite fiction. It is an environment variable, not a setting, because
``modules/`` cannot read QSettings (ARCH RULE 1) and the service has no UI.

**A plain ``FileHandler``, bounded at startup by ``modules/log_rotation.py``.** Not a
``RotatingFileHandler``: ``NetSentinel.exe``, ``NetSentinelCLI.exe`` and the service can
hold this file at the same time, and a mid-session rollover renames a file another
process still has open — which on Windows raises inside ``emit()``, on the error path,
where a logging failure is least affordable. ``rotate_logs()`` runs before any handle is
opened and has no such race, so it is the single owner of this file's size.

Encoding is load-bearing for the same reason it is in ``modules/crash_net.py``: these
records carry hostnames, SSIDs, vendor names and ``%LOCALAPPDATA%`` paths, so a
Devanagari username makes an unencoded write fail deterministically (RULE-WIN19 /
RULE-WIN24). UTF-8 with ``errors="replace"``, named explicitly.
"""
from __future__ import annotations

import logging
import os
import platform
import sys
import threading
import time
from typing import Optional

__all__ = [
    "LOG_NAME",
    "FORMAT",
    "AppLogHandler",
    "RepeatLimiter",
    "log_path",
    "configure",
]

#: The file, under ``get_app_data_dir()`` (RULE 23). Deliberately NOT in
#: ``log_rotation.EXEMPT_LOGS`` — see the module docstring on rotation ownership.
LOG_NAME = "netsentinel_app.log"

#: Timestamp, level, logger, message — the four fields F4 is about.
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

#: Loggers whose level ``configure()`` owns. These are the top-level package names the
#: tree's ``getLogger(__name__)`` calls resolve under, plus ``__main__`` (an entry point
#: run as a script) and ``py.warnings`` (``logging.captureWarnings``).
APP_LOGGERS = (
    "app", "cli", "svc", "__main__",
    "modules", "ui", "workers",
    "netsentinel", "py.warnings",
)

_log = logging.getLogger(__name__)

_LEVEL_ENV = "NETSENTINEL_LOG_LEVEL"
_DEFAULT_LEVEL = logging.INFO

#: Limiter defaults. Sized so the Deco per-node warning kept by the 2026-07-16 decision
#: still arrives — three times, then a count — instead of once per poll for the life of
#: the session.
_MAX_PER_WINDOW = 3
_WINDOW_S = 300.0


class AppLogHandler(logging.FileHandler):
    """Marker subclass so ``configure()`` can recognise its own handler on root.

    Idempotency is derived from the handler list itself rather than a module-level
    "already configured" flag: there is then no second copy of that fact to get out of
    step with reality when a test, or ``app.py --audit``, tears the handler back off.
    """


class RepeatLimiter(logging.Filter):
    """Collapse a repeating (logger, message template) pair to a few per window.

    Keyed on the **template**, not the rendered message: six mesh nodes timing out is
    one shape worth one report, while a genuinely different warning from the same
    logger must not be muted by the first one's flood.

    A suppressed run is never silent — the first record admitted after the window
    closes carries the count of what was dropped. A flood that vanishes without trace
    is the failure this audit is about, so the limiter must not become an instance of
    it (RULE-SURF2).
    """

    def __init__(self, max_per_window: int = _MAX_PER_WINDOW,
                 window_s: float = _WINDOW_S) -> None:
        super().__init__()
        self.max_per_window = max_per_window
        self.window_s = window_s
        # Filters run in Handler.handle() BEFORE the handler's I/O lock is acquired, so
        # two worker threads reach this dict concurrently. Cheap lock, held for a few
        # dict operations only.
        self._lock = threading.Lock()
        self._state: dict = {}

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging's API
        key = (record.name, str(record.msg))
        now = time.monotonic()
        with self._lock:
            entry = self._state.get(key)
            if entry is None or (now - entry[0]) >= self.window_s:
                suppressed = entry[2] if entry else 0
                self._prune(now)
                self._state[key] = [now, 1, 0]
            elif entry[1] < self.max_per_window:
                entry[1] += 1
                return True
            else:
                entry[2] += 1
                return False
        if suppressed:
            # Fold the count into the rendered text. Rendering here (rather than
            # appending to the template) keeps the key stable and leaves nothing for a
            # later handler to re-format with the wrong args.
            record.msg = (
                f"{record.getMessage()} [+{suppressed} identical messages suppressed "
                f"in the previous {int(self.window_s)}s]"
            )
            record.args = ()
        return True

    def _prune(self, now: float) -> None:
        """Drop entries whose window has long closed. Caller holds the lock.

        Unbounded growth is a real risk rather than a theoretical one: a template
        carrying a device IP in the *logger name* would mint a key per host. Only runs
        when a new key appears, and only above a size worth the walk.
        """
        if len(self._state) <= 512:
            return
        stale = [k for k, v in self._state.items() if (now - v[0]) >= self.window_s * 4]
        for k in stale:
            del self._state[k]


def _app_dir() -> str:
    """The app-data directory, or the temp dir if it cannot be resolved (RULE 23).

    Imported inside the function, as ``crash_net`` does, so a test can redirect
    ``modules.utils.get_app_data_dir`` and actually be followed.
    """
    try:
        from modules.utils import get_app_data_dir

        return str(get_app_data_dir())
    except Exception:
        import tempfile

        return tempfile.gettempdir()


def log_path() -> str:
    """Where the formatted log lives. Safe to call before ``configure()``."""
    return os.path.join(_app_dir(), LOG_NAME)


def _level_from_env() -> int:
    raw = os.environ.get(_LEVEL_ENV, "").strip().upper()
    if raw:
        named = logging.getLevelName(raw)
        if isinstance(named, int):
            return named
    return _DEFAULT_LEVEL


def _write_session_header(app_version: str) -> None:
    """One line saying which build wrote everything below it.

    The version is passed in rather than discovered: ``modules/`` cannot import
    ``app.py``, and ``configure()`` runs long before a ``QApplication`` exists to ask.
    Same contract as ``diagnostic_report.build_report(app_version=...)``.
    """
    try:
        from modules.diagnostic_report import install_channel

        channel = install_channel()
    except Exception:
        # A header missing one field beats no header at all — but say why, at debug,
        # rather than leaving "unknown" to look like a fact about the build (RULE-SURF2).
        _log.debug("install channel probe failed", exc_info=True)
        channel = "unknown"
    logging.getLogger("netsentinel").info(
        "session start: version=%s channel=%s frozen=%s python=%s platform=%s pid=%d",
        app_version or "unknown",
        channel,
        bool(getattr(sys, "frozen", False)),
        platform.python_version(),
        sys.platform,
        os.getpid(),
    )


def configure(app_version: str = "", *, level: Optional[int] = None) -> Optional[str]:
    """Install the formatted app log on the root logger. Idempotent; never raises.

    Call it at every entry point, immediately **after** ``rotate_logs()`` — Windows
    cannot rename an open file, so a handler opened first would exempt this log from
    rotation for the life of the install.

    Returns the path written to, or ``None`` if the log could not be opened. A failure
    here is not fatal and must never be: housekeeping is not a reason an app fails to
    launch, and the crash net (``modules/crash_net.py``) is a separate, independent
    sink that does not depend on this one.
    """
    root = logging.getLogger()
    for existing in root.handlers:
        if isinstance(existing, AppLogHandler):
            return existing.baseFilename

    try:
        handler = AppLogHandler(
            log_path(), mode="a", encoding="utf-8", errors="replace",
        )
    except Exception as exc:
        # The one failure that cannot be reported into the log being configured. Root
        # has no handler yet, so this goes through logging.lastResort to stderr — the
        # pre-S2 path, which is exactly the right fallback for "there is no app log".
        _log.warning("could not open %s: %s", log_path(), exc)
        return None

    handler.setFormatter(logging.Formatter(FORMAT))
    handler.setLevel(logging.DEBUG)  # the loggers decide what is emitted, not the sink
    handler.addFilter(RepeatLimiter())
    root.addHandler(handler)

    # Lower-bound only. Root at NOTSET passes everything (getEffectiveLevel returns 0),
    # which is the flood; root already at DEBUG means somebody opted in deliberately and
    # raising it here would silently overrule them.
    if root.level == logging.NOTSET or root.level > logging.WARNING:
        root.setLevel(logging.WARNING)

    resolved = level if level is not None else _level_from_env()
    for name in APP_LOGGERS:
        logging.getLogger(name).setLevel(resolved)

    # Python warnings become records too. matplotlib's "Tight layout not applied" and
    # "No artists with labels" reach stderr through warnings.warn, not logging, and are
    # exactly the undatable shapes that motivated this sprint.
    logging.captureWarnings(True)

    _write_session_header(app_version)
    return handler.baseFilename
