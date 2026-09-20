"""S1.5 — a REST API bind failure must emit an error signal (finding F2-REST).

Two server paths, one defect each side of an inheritance boundary:

  * Shipped builds bundle waitress, which raises ``OSError`` on a taken port.
    ``_serve`` catches that and emits — that half already worked.
  * A source run without waitress falls back to the Werkzeug dev server, which
    calls ``sys.exit(1)``. ``SystemExit`` inherits from ``BaseException``, not
    ``Exception``, so it sailed through both ``except`` clauses, escaped the
    ``rest-api-server`` thread, and ``crash_net``'s thread hook deliberately
    ignores ``SystemExit`` (that is how a thread is asked to stop). Net result:
    no signal, no log, no crash record — the page just said "Not running" with
    no reason.

The S3/S4 work wires that signal to a visible surface. This test only pins that
the signal is emitted at all, which is the precondition for any of it.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from workers.rest_api_worker import RestApiWorker  # noqa: E402


class _Recorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def emit(self, msg: str) -> None:
        self.messages.append(msg)


def _make_worker(running: bool) -> RestApiWorker:
    worker = RestApiWorker(store=None)
    worker.set_bind("127.0.0.1", 8080)
    worker._running = running
    return worker


def _run_serve(monkeypatch, raiser, running: bool = True) -> _Recorder:
    """Drive the real ``_serve_once`` with a run_server that fails."""
    worker = _make_worker(running)
    rec = _Recorder()
    monkeypatch.setattr(worker, "error", rec, raising=False)

    import modules.rest_api as rest_api
    monkeypatch.setattr(rest_api, "run_server", raiser, raising=False)

    try:
        worker._serve_once()
    finally:
        worker.deleteLater()
    return rec


def test_bind_oserror_is_emitted(monkeypatch):
    """The waitress path — already worked; pinned so the refactor keeps it."""
    def _boom(*_a, **_k):
        raise OSError("address already in use")

    rec = _run_serve(monkeypatch, _boom)
    assert rec.messages, "an OSError bind failure emitted nothing"
    assert "8080" in rec.messages[0]


def test_dev_server_systemexit_is_emitted(monkeypatch):
    """The dev-server path — SystemExit is not an Exception and escaped."""
    def _boom(*_a, **_k):
        raise SystemExit(1)

    rec = _run_serve(monkeypatch, _boom)
    assert rec.messages, (
        "SystemExit from the Werkzeug dev server escaped _serve — no error "
        "signal, so nothing downstream can ever report the bind failure"
    )
    assert "8080" in rec.messages[0]


def test_stopping_worker_does_not_report_a_shutdown_as_an_error(monkeypatch):
    """stop() sets _running False; the resulting exit is not a failure."""
    def _boom(*_a, **_k):
        raise SystemExit(0)

    rec = _run_serve(monkeypatch, _boom, running=False)
    assert rec.messages == [], (
        "a deliberate shutdown was reported to the user as an error"
    )
