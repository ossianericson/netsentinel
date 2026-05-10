"""
NetSentinel — Debug Launcher
=============================
Runs the full GUI with Qt message handler captured to a log file.
All Qt warnings, Python exceptions and tracebacks are written to
  netsentinel_debug.log  (in the repo root)

Usage:
    python tools/debug_launch.py

The log is always overwritten so it is fresh each run.
"""
import os
import sys
import traceback

# Ensure repo root is on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)

LOG_PATH = os.path.join(_ROOT, "netsentinel_debug.log")

_log = open(LOG_PATH, "w", encoding="utf-8")


def _w(msg: str) -> None:
    _log.write(msg + "\n")
    _log.flush()
    print(msg)


_w("=== NetSentinel Debug Launch ===")
_w(f"Python {sys.version}")
_w(f"CWD: {os.getcwd()}")
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
    app.setApplicationVersion("1.9.0")
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
    sys.exit(result)

except Exception:
    _w("\n=== UNHANDLED EXCEPTION ===")
    traceback.print_exc(file=_log)
    _log.flush()
    traceback.print_exc()
    _log.close()
    print(f"\nFull log: {LOG_PATH}")
    sys.exit(1)
