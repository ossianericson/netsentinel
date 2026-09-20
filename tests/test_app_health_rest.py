"""S3.3 — a REST API that cannot serve is an app-health condition, and serving resolves it.

S1.5 made a bind failure *emit* on both server paths. Nothing listened: ``app.py``'s
handler was ``print()`` into a windowed build's ``StringIO``, and the page's hot-start
handler was another ``print()``. The REST API page's own probe cannot stand in for the
truth either — it only checks that *something* accepts connections on the port, which is
exactly what is true when another program took it.

The worker reports to the registry itself, because it is the only place that holds both
facts: the real exception (so ``modules.error_text`` can say why without reading the
localized message) and whether the server thread is still alive. There are two worker
owners — ``app.py`` at launch and ``RestApiPage._hot_start`` — and a condition raised by
the first must be resolvable by the second, or fixing the port leaves a stale warning.
"""
from __future__ import annotations

import errno
import socket
import sys
import threading
import time

import pytest

pytest.importorskip("PyQt6")

from modules.app_health import AppHealth  # noqa: E402
from modules.app_health_catalogue import REST_API  # noqa: E402
from modules.error_text import explain  # noqa: E402
from workers.rest_api_worker import RestApiWorker  # noqa: E402


@pytest.fixture
def occupied_port():
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    yield holder.getsockname()[1]
    holder.close()


def _worker(port: int, store=None) -> RestApiWorker:
    worker = RestApiWorker(store=store)
    worker.set_bind("127.0.0.1", port)
    worker._running = True  # as run() sets it before starting the server thread
    return worker


def _release(worker, qt_app) -> None:
    worker.deleteLater()
    for _ in range(3):
        qt_app.processEvents()


def test_the_real_server_on_an_occupied_port_raises_the_condition(qt_app, tmp_path, occupied_port):
    """RULE-DBG5: the real ``run_server`` — waitress or the dev server, whichever is installed."""
    from modules.metric_store import MetricStore

    store = MetricStore(str(tmp_path / "rest.db"))
    health = AppHealth()
    worker = _worker(occupied_port, store)
    worker.report_to(health)
    try:
        worker._serve_once()
    finally:
        _release(worker, qt_app)

    cond = health.get(REST_API.key)
    assert cond is not None and cond.resolved_at is None
    assert cond.cta_label == "REST API"


def test_a_classified_bind_error_says_why_without_reading_its_message(qt_app, monkeypatch, occupied_port):
    """The waitress path raises the OS's own ``OSError`` — Swedish on the dev machine."""
    import modules.rest_api as rest_api

    def _bind_like_waitress(_store, host, port):
        with socket.socket() as s:
            s.bind((host, port))

    monkeypatch.setattr(rest_api, "run_server", _bind_like_waitress)
    health = AppHealth()
    worker = _worker(occupied_port)
    worker.report_to(health)
    try:
        worker._serve_once()
    finally:
        _release(worker, qt_app)

    cond = health.get(REST_API.key)
    # errno, never the message: EADDRINUSE is 98 on Linux, 48 on macOS and 10048 on
    # Windows, so the reference exception has to name the constant, not a number.
    assert cond.why == explain(OSError(errno.EADDRINUSE, "")).why  # "Another program is already using this port."
    assert str(occupied_port) in cond.detail


def test_a_deliberate_stop_raises_nothing(qt_app, monkeypatch):
    import modules.rest_api as rest_api

    def _stopped(*_a, **_k):
        raise SystemExit(0)

    monkeypatch.setattr(rest_api, "run_server", _stopped)
    health = AppHealth()
    worker = _worker(8080)
    worker._running = False
    worker.report_to(health)
    try:
        worker._serve_once()
    finally:
        _release(worker, qt_app)

    assert health.active() == []


def test_a_server_that_stays_up_resolves_a_condition_raised_by_another_worker(qt_app, monkeypatch):
    """Launch worker failed on the old port; the page's hot-start on a new port works."""
    import modules.rest_api as rest_api

    release = threading.Event()
    monkeypatch.setattr(rest_api, "run_server", lambda *_a, **_k: release.wait(10))
    monkeypatch.setattr("workers.rest_api_worker._SERVING_AFTER_S", 0.2)

    health = AppHealth()
    health.report_failure(REST_API, detail="bind failed on the old port")

    worker = RestApiWorker(store=None)
    worker.set_bind("127.0.0.1", 18766)
    worker.report_to(health)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while health.active() and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.05)
        assert health.active() == [], "a server that stayed up never resolved the condition"
    finally:
        worker._running = False
        release.set()
        assert worker.wait(5000)
        _release(worker, qt_app)


def test_the_page_hands_its_hot_started_worker_over_before_starting_it(qt_app, monkeypatch):
    """The page's worker is the one that resolves a launch failure — if it is reported
    to nobody, the user fixes the port and the condition stays up."""
    import modules.rest_api as rest_api
    from ui.pages.rest_api_page import RestApiPage

    monkeypatch.setattr(rest_api, "get_or_create_api_key", lambda: "k")
    seen_at_start = []
    monkeypatch.setattr(RestApiWorker, "start", lambda self: seen_at_start.append(self._health))

    health = AppHealth()
    page = RestApiPage(store=object())
    page.worker_created.connect(lambda w: w.report_to(health))
    try:
        page._hot_start()
    finally:
        page.deleteLater()
        for _ in range(3):
            qt_app.processEvents()

    assert seen_at_start == [health]


def test_the_dashboard_passes_its_registry_to_every_page_worker():
    """Behaviour of the hand-over, plus a structural pin on the lazy factory that
    connects it — a Dashboard cannot be built in-process (RULE-TP4-DASH)."""
    import ast
    from pathlib import Path

    from ui.tabs import TabBuilderMixin

    class _Worker:
        health = "unset"

        def report_to(self, h):
            self.health = h

    class _Dash:
        _app_health = AppHealth()

    worker = _Worker()
    TabBuilderMixin._watch_rest_api_worker(_Dash(), worker)
    assert worker.health is _Dash._app_health

    tree = ast.parse(Path(__file__).resolve().parents[1].joinpath("ui", "tabs.py").read_text(encoding="utf-8"))
    factory = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_mk_rest_api_page")
    assert "worker_created.connect(self._watch_rest_api_worker)" in ast.unparse(factory)


def test_a_rest_api_that_cannot_even_import_raises_the_condition(qt_app, monkeypatch):
    """Every branch that ends with no server must say so — not only the bind failures."""
    monkeypatch.setitem(sys.modules, "modules.rest_api", None)  # import now raises ImportError
    health = AppHealth()
    worker = RestApiWorker(store=None)
    worker.report_to(health)
    try:
        worker.run()  # the QThread body, synchronously: it returns straight after the import
    finally:
        _release(worker, qt_app)

    assert health.get(REST_API.key) is not None


# ── S4.4c: turning the REST API off withdraws its launch failure ────────────────

class _FakeSettings:
    """Stands in for QSettings("NetSentinel", "NetSentinel"): the suite cannot sandbox the
    registry (tests/conftest.py), and a real write here would flip the developer's REST API."""

    store: dict = {}

    def __init__(self, *_a):
        pass

    def value(self, key, default=None, type=None):  # noqa: A002 — QSettings' own keyword
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value


def test_the_page_announces_the_rest_api_being_switched_off(qt_app, monkeypatch):
    from ui.pages.rest_api_page import RestApiPage

    monkeypatch.setattr("ui.pages.rest_api_page.QSettings", _FakeSettings)
    page = RestApiPage(store=object())
    monkeypatch.setattr(page, "_probe_status", lambda: None)
    seen: list = []
    page.enabled_changed.connect(seen.append)
    try:
        page._on_enable_changed(0)
        page._on_enable_changed(2)
    finally:
        page.deleteLater()
        for _ in range(3):
            qt_app.processEvents()

    assert seen == [False, True]


def test_switching_the_rest_api_off_resolves_a_launch_failure():
    """A REST API the user turned off is not a REST API that is failing — without this,
    Home keeps "The REST API could not start" for a feature that is meant to be off."""
    import ast
    from pathlib import Path

    from ui.tabs import TabBuilderMixin

    class _Dash:
        _app_health = AppHealth()

    _Dash._app_health.report_failure(REST_API, detail="WinError 10048")
    TabBuilderMixin._on_rest_api_enabled_changed(_Dash(), True)
    assert _Dash._app_health.get(REST_API.key).resolved_at is None, "switching ON must not clear it"

    TabBuilderMixin._on_rest_api_enabled_changed(_Dash(), False)
    assert _Dash._app_health.get(REST_API.key).resolved_at is not None

    tree = ast.parse(Path(__file__).resolve().parents[1].joinpath("ui", "tabs.py").read_text(encoding="utf-8"))
    factory = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_mk_rest_api_page")
    assert "enabled_changed.connect(self._on_rest_api_enabled_changed)" in ast.unparse(factory)


def test_switching_it_off_before_the_registry_is_attached_is_harmless():
    from ui.tabs import TabBuilderMixin

    TabBuilderMixin._on_rest_api_enabled_changed(object(), False)
