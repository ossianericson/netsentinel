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

# Rotate: remove oldest logs, keep last 4 (the new one will be 5th)
import glob as _glob

_existing = sorted(_glob.glob(os.path.join(_ROOT, "netsentinel_debug_????????_??????.log")))
for _old in _existing[:-4]:
    try:
        os.remove(_old)
    except OSError:
        pass

_log = open(_ROTATED_PATH, "w", encoding="utf-8")


def _w(msg: str) -> None:
    _log.write(msg + "\n")
    _log.flush()
    print(msg)


_w("=== NetSentinel Debug Launch ===")
_w(f"Python {sys.version}")
_w(f"CWD: {os.getcwd()}")
_w(f"Log: {_ROTATED_PATH}")
_w("")

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import qInstallMessageHandler, QtMsgType

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

    app = QApplication(sys.argv)
    app.setApplicationName("NetSentinel")
    app.setApplicationVersion("1.9.82")
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
        pass

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
        pass

    print(f"\nFull log: {_ROTATED_PATH}")
    sys.exit(1)
