"""
PassiveObserverWorker — QThread wrapper for modules/passive_observer.py.

Starts the SSDP + mDNS background listeners and emits observation_ready()
whenever a new or upgraded device-type hint arrives.

Signals
-------
observation_ready(object)  — PassiveObservation instance
error(str)                 — human-readable startup failure message
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from modules.passive_observer import (
    PassiveObservation,
    start_passive_observation,
    stop_passive_observation,
)


class PassiveObserverWorker(QThread):
    """Manages the passive SSDP / mDNS listeners and bridges them to Qt signals."""

    observation_ready = pyqtSignal(object)   # PassiveObservation
    error             = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    def run(self) -> None:
        self._running = True
        try:
            start_passive_observation(self._on_observation)
        except Exception as exc:
            self.error.emit(
                f"Passive observer could not start: {exc}. "
                "Device classification hints from SSDP/mDNS will be unavailable."
            )
            return

        # Park here until stop() is called — the real work happens in daemon threads.
        while self._running:
            self.msleep(500)

        stop_passive_observation()

    def stop(self) -> None:
        self._running = False
        stop_passive_observation()

    def _on_observation(self, obs: PassiveObservation) -> None:
        """Bridge from daemon thread → Qt signal (thread-safe via queued connection)."""
        if self._running:
            self.observation_ready.emit(obs)
