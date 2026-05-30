"""
NetSentinel — Startup Profiler
================================
Times each stage of application startup to surface regressions.

Usage:
    python tools/startup_profile.py

Output (example):
    [0.000]  QApplication created
    [0.124]  MetricStore opened
    [0.480]  Dashboard.__init__ started
    [1.203]  _init_pages complete
    [2.100]  window.show() called

If any stage exceeds 3 seconds total the profiler prints a warning.

The profile is also written to  startup_profile.log  in the repo root.
"""
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)

_START = time.perf_counter()
_STAGES: list[tuple[float, str]] = []
_THRESHOLD_S = 3.0


def _mark(stage: str) -> None:
    elapsed = time.perf_counter() - _START
    _STAGES.append((elapsed, stage))
    print(f"[{elapsed:6.3f}]  {stage}")


# ── instrument module imports ────────────────────────────────────────────────

import importlib
import unittest.mock as _mock

_orig_init = None


def _patched_dashboard_init(self, *args, **kwargs):
    _mark("Dashboard.__init__ started")
    _orig_init(self, *args, **kwargs)


def _patched_init_pages(self):
    from ui.dashboard import Dashboard
    Dashboard._orig_init_pages(self)
    _mark("_init_pages complete")


# ── run startup ──────────────────────────────────────────────────────────────

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import qInstallMessageHandler, QtMsgType

    def _qt_handler(mode, context, message):
        if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            _mark(f"Qt {mode.name}: {message[:80]}")

    qInstallMessageHandler(_qt_handler)

    app = QApplication(sys.argv)
    app.setApplicationName("NetSentinel")
    app.setApplicationVersion("1.9.60")
    app.setOrganizationName("netsentinel")
    _mark("QApplication created")

    from modules.metric_store import MetricStore
    store = MetricStore()
    _mark("MetricStore opened")

    # Monkey-patch Dashboard to time _init_pages
    from ui import dashboard as _dash_mod
    _DashClass = _dash_mod.Dashboard

    _orig_init = _DashClass.__init__
    _DashClass._orig_init_pages = _DashClass._init_pages

    def _timed_init(self, *a, **kw):
        _mark("Dashboard.__init__ started")
        _orig_init(self, *a, **kw)

    def _timed_init_pages(self):
        _DashClass._orig_init_pages(self)
        _mark("_init_pages complete")

    _DashClass.__init__ = _timed_init
    _DashClass._init_pages = _timed_init_pages

    window = _DashClass(store)

    window.show()
    _mark("window.show() called")

    total = time.perf_counter() - _START

    print()
    print(f"Total startup: {total:.3f}s")
    if total > _THRESHOLD_S:
        print(f"  ⚠ WARNING: startup exceeded {_THRESHOLD_S}s threshold")

    # Write profile log
    log_path = os.path.join(_ROOT, "startup_profile.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"NetSentinel startup profile\n\n")
        for elapsed, stage in _STAGES:
            f.write(f"[{elapsed:6.3f}]  {stage}\n")
        f.write(f"\nTotal: {total:.3f}s\n")
    print(f"Profile written to: {log_path}")

    # Close immediately — this is a profiling run, not a full session
    window.close()
    sys.exit(0)

except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)
