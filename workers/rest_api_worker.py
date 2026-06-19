"""
RestApiWorker — QThread wrapper for the NetSentinel local REST API server.

Starts/stops the Flask server in a daemon thread.
Emits started(port), stopped(), error(str).
"""
from __future__ import annotations

import threading
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from modules.metric_store import MetricStore


class RestApiWorker(QThread):
    """
    Manages the lifecycle of the local REST API Flask server.

    The Flask server runs in a plain Python daemon thread (not in the QThread
    event loop itself) because werkzeug's run() is a blocking call that we
    cannot easily interrupt.  The QThread is used to:
      • Provide a Qt-compatible started/stopped/error signal interface
      • Keep the server reference alive as long as the worker is alive
    """

    started_ok  = pyqtSignal(int)   # port number
    stopped     = pyqtSignal()
    error       = pyqtSignal(str)

    def __init__(self, store: MetricStore, parent=None):
        super().__init__(parent)
        self._store   = store
        self._host    = "127.0.0.1"
        self._port    = 8765
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def set_bind(self, host: str, port: int) -> None:
        """Configure the bind address before starting. Must be called before start()."""
        self._host = host
        self._port = port

    def run(self) -> None:
        """QThread entry point — starts the Flask server in a daemon thread."""
        try:
            from modules.rest_api import FLASK_AVAILABLE, run_server
        except ImportError as exc:
            self.error.emit(str(exc))
            return

        if not FLASK_AVAILABLE:
            self.error.emit(
                "Flask is not installed. Install it with:  pip install flask\n"
                "Then restart NetSentinel."
            )
            return

        self._running = True

        def _serve():
            try:
                run_server(self._store, host=self._host, port=self._port)
            except OSError as exc:
                self.error.emit(
                    f"REST API failed to bind on {self._host}:{self._port}: {exc}\n"
                    "Check that no other process is using this port."
                )
            except Exception as exc:
                if self._running:
                    self.error.emit(f"REST API error: {exc}")

        self._thread = threading.Thread(target=_serve, name="rest-api-server", daemon=True)
        self._thread.start()
        self.started_ok.emit(self._port)

        # Block the QThread until stop() is called (or the app exits)
        while self._running and self._thread.is_alive():
            self.msleep(500)

        self.stopped.emit()

    def stop(self) -> None:
        """Signal the worker to stop. The daemon thread will die when the process exits."""
        self._running = False
        # Werkzeug has no clean shutdown API for the dev server without
        # using the reloader.  Since the thread is daemon=True it will
        # terminate when the process exits.  For a graceful in-process
        # stop we send a dummy request to wake any blocking accept() call.
        try:
            import urllib.request
            host = "127.0.0.1" if self._host == "0.0.0.0" else self._host
            urllib.request.urlopen(
                f"http://{host}:{self._port}/health", timeout=1
            )
        except Exception:
            pass  # non-fatal
