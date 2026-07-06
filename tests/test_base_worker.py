"""Behaviour tests for workers/base_worker.py (P3 BaseWorker).

Covers the templated run()->work() contract, the error safety-net, and the
cooperative-stop flag.  The architectural gate that every worker *subclasses*
BaseWorker lives separately in test_worker_base_class.py.
"""

from __future__ import annotations

import time

from workers.base_worker import BaseWorker


# ── Minimal concrete workers for exercising the base ────────────────────────────

class _OneShotWorker(BaseWorker):
    result = None

    def work(self) -> None:
        self.result = "did-work"


class _BoomWorker(BaseWorker):
    def work(self) -> None:
        raise ValueError("kaboom")


class _LoopWorker(BaseWorker):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.iterations = 0

    def work(self) -> None:
        while not self._should_stop():
            self.iterations += 1
            self.msleep(5)


def test_signals_exist(qt_app):
    w = _OneShotWorker()
    assert hasattr(w, "error")
    assert hasattr(w, "progress")


def test_stop_flag_defaults_false(qt_app):
    w = _OneShotWorker()
    assert w._should_stop() is False


def test_request_stop_sets_flag(qt_app):
    w = _OneShotWorker()
    w.request_stop()
    assert w._should_stop() is True


def test_stop_is_alias_for_request_stop(qt_app):
    w = _OneShotWorker()
    w.stop()
    assert w._should_stop() is True


def test_run_calls_work(qt_app):
    w = _OneShotWorker()
    w.run()   # synchronous — exercises the template without spawning a thread
    assert w.result == "did-work"


def test_run_resets_stop_flag_before_work(qt_app):
    """A stop requested before start() must not leak into the next run()."""
    w = _OneShotWorker()
    w.request_stop()
    w.run()
    assert w._should_stop() is False


def test_uncaught_exception_routes_to_error(qt_app):
    w = _BoomWorker()
    seen: list[str] = []
    w.error.connect(seen.append)
    w.run()
    assert seen == ["kaboom"]


def test_missing_work_override_emits_notimplemented(qt_app):
    w = BaseWorker()
    seen: list[str] = []
    w.error.connect(seen.append)
    w.run()
    assert len(seen) == 1
    assert "work()" in seen[0]


def test_loop_worker_start_stop(qt_app):
    """Long-lived work() loop stops cooperatively via stop()."""
    w = _LoopWorker()
    w.start()
    time.sleep(0.05)
    w.stop()
    assert w.wait(2000) is True
    assert not w.isRunning()
    assert w.iterations > 0
