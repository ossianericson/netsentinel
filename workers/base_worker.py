"""
base_worker.py — shared QThread base for all NetSentinel background workers (P3).

Every worker under ``workers/`` runs network / disk / subprocess work off the
main thread and reports back to the UI via Qt signals (RULE 4).  Historically
each worker re-declared the same ``error(str)`` signal, re-implemented the same
try/except-around-run() boilerplate, and reinvented its own stop flag (or had
none).  ``BaseWorker`` collapses that shared surface into one place.

What the base provides
----------------------
- ``error(str)``    — universal failure channel (every worker had this).
- ``progress(str)`` — human-readable status channel (RULE-AH2: workers should
  emit progress at least every 5 s during long work).  Free for all workers;
  a worker that never emits it simply leaves it unconnected.
- ``request_stop()`` / ``stop()`` — cooperative cancellation.  ``stop()`` is a
  back-compat alias so existing call sites (and the lifecycle-test helper that
  calls ``worker.stop()`` if present) keep working unchanged.
- ``_should_stop()`` — the flag read inside loop bodies.
- a templated ``run()`` that resets the stop flag, calls the subclass's
  ``work()``, and routes any *uncaught* exception to ``error``.

What the base deliberately does NOT do
--------------------------------------
It does **not** impose a single ``result_ready`` signal.  Workers emit results
under many names and signatures that every ``.connect()`` site depends on
(``result_ready``, ``snapshot_ready``, ``check_done``, ``results_ready``,
``phase_changed``, ``trap_received``, ...).  Forcing one name would break dozens
of call sites for no benefit, so each subclass declares its own result
signal(s).  The base is a convenience mixin, not a straitjacket.

Two work() shapes are supported
-------------------------------
1. **One-shot** — ``work()`` does the job once and emits a result.  The base's
   try/except is the error path; the subclass needs no try/except of its own
   (unless it wants to *translate* the error message — then it keeps its own).
2. **Long-lived loop** — ``work()`` runs ``while not self._should_stop():`` with
   its own per-iteration try/except so a single failure doesn't tear down the
   loop.  The base's outer try/except is then only a last-resort safety net.

A subclass with a genuinely custom threading shape (e.g. a blocking receive
loop that must be interrupted by closing a socket rather than by a flag) may
override ``run()`` directly and still inherit ``error`` / ``progress`` /
``request_stop`` — subclassing ``BaseWorker`` is all the ratchet
(``tests/test_worker_base_class.py``) requires.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


class BaseWorker(QThread):
    """Common QThread base: ``error``/``progress`` signals + stop flag + run() template."""

    error:    pyqtSignal = pyqtSignal(str)
    progress: pyqtSignal = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop_requested = False

    # ── Cooperative cancellation ────────────────────────────────────────────────

    def request_stop(self) -> None:
        """Ask the worker to stop at the next ``_should_stop()`` check."""
        self._stop_requested = True

    def stop(self) -> None:
        """Back-compat alias for :meth:`request_stop`.

        Existing call sites and the lifecycle-test helper call ``stop()``.
        Subclasses that need extra teardown (close a socket, shut a server)
        override this, do their teardown, then call ``super().stop()``.
        """
        self.request_stop()

    def _should_stop(self) -> bool:
        """True once :meth:`request_stop`/:meth:`stop` has been called."""
        return self._stop_requested

    # ── QThread entry point ─────────────────────────────────────────────────────

    def run(self) -> None:
        """Reset the stop flag, run :meth:`work`, funnel uncaught errors to ``error``."""
        self._stop_requested = False
        try:
            self.work()
        except Exception as exc:  # noqa: BLE001 — last-resort net; translated errors stay in work()
            self.error.emit(str(exc))

    def work(self) -> None:
        """Override with the actual background job (one-shot or a stop-aware loop)."""
        raise NotImplementedError(
            f"{type(self).__name__} must override work() (or run())"
        )
