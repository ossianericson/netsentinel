"""
NetSentinel — Debug Launcher
=============================
Runs the full GUI with Qt message handler captured to a log file.
All Qt warnings, Python exceptions and tracebacks are written to
  netsentinel_debug.log  (in the repo root, symlinked to the latest run)

Log rotation: keeps the last 5 timestamped launch logs, plus a
  netsentinel_debug.log  symlink/copy pointing to the most recent one.

Usage:
    python tools/debug_launch.py
"""
import os
import sys
import traceback
import shutil
from datetime import datetime

# Ensure repo root is on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)

_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
_ROTATED_PATH = os.path.join(_ROOT, f"netsentinel_debug_{_TIMESTAMP}.log")
LOG_PATH = os.path.join(_ROOT, "netsentinel_debug.log")

# Rotate: delete ALL previous timestamped logs before creating a new one.
# Only netsentinel_debug.log (the symlink/copy) plus the current run's log are kept.
# This prevents agents from reading stale old logs during version-bump/commit sessions.
import atexit
import glob as _glob

_existing = sorted(_glob.glob(os.path.join(_ROOT, "netsentinel_debug_????????_??????.log")))
for _old in _existing:
    try:
        os.remove(_old)
    except OSError:
        pass  # log rotation errors are non-fatal

_log = open(_ROTATED_PATH, "w", encoding="utf-8")  # lgtm[py/file-not-closed] — log file kept open for process lifetime; atexit closes it  # noqa: WPS515
atexit.register(_log.close)

# Update the stable symlink/copy immediately so any process reading
# netsentinel_debug.log always gets the current run's content even if
# the event loop is killed before clean shutdown.
try:
    _log.flush()
    shutil.copy2(_ROTATED_PATH, LOG_PATH)
except OSError:
    pass  # best-effort initial log sync


def _w(msg: str) -> None:
    _log.write(msg + "\n")
    _log.flush()
    # Keep the main log in sync after every write
    try:
        shutil.copy2(_ROTATED_PATH, LOG_PATH)
    except OSError:
        pass  # best-effort sync
    print(msg)


_w("=== NetSentinel Debug Launch ===")
_w(f"Python {sys.version}")
_w(f"CWD: {os.getcwd()}")
_w(f"Log: {_ROTATED_PATH}")
_w("")

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, qInstallMessageHandler, QtMsgType

    _MSG_LEVELS = {
        QtMsgType.QtDebugMsg:    "DEBUG",
        QtMsgType.QtInfoMsg:     "INFO ",
        QtMsgType.QtWarningMsg:  "WARN ",
        QtMsgType.QtCriticalMsg: "CRIT ",
        QtMsgType.QtFatalMsg:    "FATAL",
    }

    def _qt_handler(mode, context, message):
        level = _MSG_LEVELS.get(mode, "?????")
        loc = f"{context.file}:{context.line}" if context.file else "<qt>"
        _w(f"[Qt {level}] {loc} — {message}")

    qInstallMessageHandler(_qt_handler)

    # Required for QtWebEngineWidgets — must be set before QApplication is created.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setApplicationName("NetSentinel")
    app.setApplicationVersion("2.1.23")
    app.setOrganizationName("netsentinel")

    _w("QApplication created OK")

    from ui.dashboard import Dashboard
    _w("Dashboard class imported OK")

    window = Dashboard()
    _w("Dashboard() instantiated OK")

    window.show()
    _w("window.show() called OK")
    _w("")
    _w("--- entering event loop ---")
    _log.flush()

    result = app.exec()
    _w(f"--- event loop exited: {result} ---")
    _log.close()

    # Update the stable symlink/copy
    try:
        shutil.copy2(_ROTATED_PATH, LOG_PATH)
    except OSError:
        pass  # non-fatal

    sys.exit(result)

except Exception:
    _w("\n=== UNHANDLED EXCEPTION ===")
    traceback.print_exc(file=_log)
    _log.flush()
    traceback.print_exc()
    _log.close()

    # Still update the stable copy so CI can read LOG_PATH
    try:
        shutil.copy2(_ROTATED_PATH, LOG_PATH)
    except OSError:
        pass  # non-fatal

    print(f"\nFull log: {_ROTATED_PATH}")
    sys.exit(1)
