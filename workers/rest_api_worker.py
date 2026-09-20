"""
RestApiWorker — QThread wrapper for the NetSentinel local REST API server.

Starts/stops the Flask server in a daemon thread.
Emits started(port), stopped(), error(str).

With ``report_to(health)`` it also keeps the ``rest_api:serve`` app-health condition
true (S3.3): raised on a failure, with the cause classified from the real exception by
``modules.error_text``; resolved once the server thread has stayed up. The worker is the
only place holding both facts — the page's probe cannot tell our server from another
program that took the port.
"""
from __future__ import annotations

import dataclasses
import threading
import time
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from modules.app_health import AppHealth
from modules.app_health_catalogue import REST_API
from modules.error_text import explain
from modules.metric_store import MetricStore

#: A bind failure ends the server thread within milliseconds on both server paths
#: (waitress raises, the dev server calls sys.exit). A thread still alive this long
#: after start is serving.
_SERVING_AFTER_S = 1.5


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
        self._health: Optional[AppHealth] = None

    def report_to(self, health: Optional[AppHealth]) -> None:
        """Keep the REST API app-health condition current. Call before start()."""
        self._health = health

    def set_bind(self, host: str, port: int) -> None:
        """Configure the bind address before starting. Must be called before start()."""
        self._host = host
        self._port = port

    def run(self) -> None:
        """QThread entry point — starts the Flask server in a daemon thread."""
        try:
            from modules.rest_api import FLASK_AVAILABLE
        except ImportError as exc:
            self.error.emit(str(exc))
            self._report_failure(
                str(exc),
                why="A component the REST API needs is missing from this installation.",
                next_step="Reinstall NetSentinel.",
            )
            return

        if not FLASK_AVAILABLE:
            self.error.emit(
                "Flask is not installed. Install it with:  pip install flask\n"
                "Then restart NetSentinel."
            )
            self._report_failure(
                "Flask is not installed",
                why="A component the REST API needs is missing from this installation.",
                next_step="Reinstall NetSentinel.",
            )
            return

        self._running = True

        self._thread = threading.Thread(target=self._serve_once, name="rest-api-server", daemon=True)
        self._thread.start()
        self.started_ok.emit(self._port)

        # Block the QThread until stop() is called (or the app exits)
        started = time.monotonic()
        serving_reported = False
        while self._running and self._thread.is_alive():
            self.msleep(500 if serving_reported else 100)
            if (not serving_reported and self._thread.is_alive()
                    and time.monotonic() - started >= _SERVING_AFTER_S):
                serving_reported = True
                if self._health is not None:
                    self._health.report_ok(REST_API.key)

        self.stopped.emit()

    def _serve_once(self) -> None:
        """Run the server until it returns or fails. Body of the server thread.

        A method rather than a closure so the failure paths can be driven
        directly in tests — the SystemExit branch below has no other reachable
        trigger on a machine where waitress is installed.
        """
        from modules.rest_api import run_server

        try:
            run_server(self._store, host=self._host, port=self._port)
        except OSError as exc:
            self.error.emit(
                f"REST API failed to bind on {self._host}:{self._port}: {exc}\n"
                "Check that no other process is using this port."
            )
            explanation = explain(exc)
            if explanation.kind == "unknown":
                self._report_failure(f"{self._host}:{self._port}: {exc}")
            else:
                self._report_failure(
                    f"{self._host}:{self._port}: {exc}",
                    why=explanation.why, next_step=explanation.next_step,
                )
        except SystemExit as exc:
            # RULE-SURF1 / finding F2-REST. Without waitress, Flask falls back to
            # the Werkzeug dev server, which answers a taken port with
            # sys.exit(1). SystemExit derives from BaseException, so it missed
            # both clauses above, escaped this thread, and crash_net's thread
            # hook ignores SystemExit by design (that is how a thread is asked to
            # stop) — no signal, no log, no crash record. The page showed
            # "Not running" with no reason.
            if self._running:
                self.error.emit(
                    f"REST API failed to start on {self._host}:{self._port} "
                    f"(server exited with code {exc.code}).\n"
                    "Check that no other process is using this port."
                )
                # The dev server exits for any bind failure and keeps the cause to
                # itself, so the catalogue's fallback text is the honest one here.
                self._report_failure(
                    f"{self._host}:{self._port}: server exited with code {exc.code}"
                )
        except Exception as exc:
            if self._running:
                self.error.emit(f"REST API error: {exc}")
                self._report_failure(f"{self._host}:{self._port}: {exc}")

    def _report_failure(self, detail: str, why: str = "", next_step: str = "") -> None:
        """Raise ``rest_api:serve``; ``why``/``next_step`` override the catalogue fallback."""
        if self._health is None:
            return
        spec = REST_API
        if why:
            spec = dataclasses.replace(spec, why=why, next_step=next_step or spec.next_step)
        self._health.report_failure(spec, detail=detail)

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
