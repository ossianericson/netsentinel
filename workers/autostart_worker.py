"""
workers/autostart_worker.py — QThread wrapper around modules.autostart
=========================================================================
RULE 4: WinRT calls block on RPC (RequestEnableAsync may show a consent
dialog), so every query/set goes through this worker for a uniform async UX
(RULE-UX2), regardless of backend.

RoInitialize/RoUninitialize are scoped to this thread's single work() call.
Confirmed live (docs/spikes/startup-task-winrt.md section 1) that a plain
background thread gets a clean MTA even while a QApplication is alive in the
same process — this thread's apartment state is independent of the GUI
thread's STA.
"""
from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import pyqtSignal

from modules import autostart
from workers.base_worker import BaseWorker


class AutostartWorker(BaseWorker):
    """
    One-shot: query the current autostart state, or set it and report what
    actually resulted — never the requested value (modules.autostart's
    return-actual-state contract).
    """

    result_ready = pyqtSignal(object)  # modules.autostart.AutostartState

    def __init__(self, enable: Optional[bool] = None, parent=None) -> None:
        """enable=None -> query only. enable=True/False -> set, then report the actual state."""
        super().__init__(parent)
        self._enable = enable

    def work(self) -> None:
        backend = autostart.autostart_backend()
        ro_inited = False
        try:
            # sys.platform guard is required in addition to the backend check:
            # tests force backend == "startup_task" on every OS to exercise the
            # WinRT state-mapping logic without a real Store build, but
            # ro_initialize()/_combase() call ctypes.WinDLL, which does not
            # exist off Windows -- an unguarded call here raised AttributeError
            # on the mac/Linux CI runners (routed to the error signal, leaving
            # the checkbox in the wrong state instead of the mocked result).
            if backend == "startup_task" and sys.platform == "win32":
                from modules import startup_task
                hr = startup_task.ro_initialize()
                ro_inited = hr in (startup_task.S_OK, startup_task.S_FALSE)

            if self._enable is None:
                state = autostart.autostart_state()
            else:
                state = autostart.set_autostart(self._enable)
            self.result_ready.emit(state)
        finally:
            if ro_inited:
                from modules import startup_task
                startup_task.ro_uninitialize()
