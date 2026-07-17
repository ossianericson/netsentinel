"""Tests for workers/live_protocol_worker.py (RULE-T2, Phase A5).

Pattern-matches tests/test_lldp_worker.py: the worker's own is_admin()/
is_npcap_available() gate must translate to a progress() message and a
clean, fast exit -- never a raw exception -- when the capability is missing.
"""
import time

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _cleanup(w):
    app = QApplication.instance()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already deleted
    if app:
        for _ in range(3):
            app.processEvents()


def _pump():
    """Drain queued cross-thread signal deliveries to plain-callable slots.

    A signal emitted from a QThread and connected to a plain Python callable
    (not a QObject slot) auto-resolves to a queued connection against the
    main thread's event loop -- the callable only actually runs once
    processEvents() pumps that queue, even though w.wait() has already
    returned (the *thread* finished; the *delivery* is still pending)."""
    app = QApplication.instance()
    if app:
        for _ in range(5):
            app.processEvents()


def test_import():
    from workers.live_protocol_worker import LiveProtocolWorker  # noqa: F401


def test_subclasses_base_worker():
    from workers.base_worker import BaseWorker
    from workers.live_protocol_worker import LiveProtocolWorker
    assert issubclass(LiveProtocolWorker, BaseWorker)


def test_instantiation():
    from workers.live_protocol_worker import LiveProtocolWorker
    w = LiveProtocolWorker(protocol="ARP")
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist():
    from workers.live_protocol_worker import LiveProtocolWorker
    w = LiveProtocolWorker(protocol="ARP")
    assert hasattr(w, "frame_event")
    assert hasattr(w, "error")       # inherited from BaseWorker
    assert hasattr(w, "progress")    # inherited from BaseWorker
    _cleanup(w)


def test_exits_quickly_without_admin(monkeypatch):
    """Without admin, work() must emit a translated progress message and return
    immediately -- never attempt the capture, never raise."""
    monkeypatch.setattr("modules.utils.is_admin", lambda: False)
    from workers.live_protocol_worker import LiveProtocolWorker
    progress_msgs = []
    errors = []
    w = LiveProtocolWorker(protocol="ARP")
    w.progress.connect(progress_msgs.append)
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(5000)
    _pump()
    assert finished, "worker did not finish within 5 s without admin"
    assert not w.isRunning()
    assert not errors, "non-admin path must never emit a raw error"
    assert any("admin" in m.lower() for m in progress_msgs)
    _cleanup(w)


def test_exits_quickly_without_npcap(monkeypatch):
    monkeypatch.setattr("modules.utils.is_admin", lambda: True)
    monkeypatch.setattr("modules.utils.is_npcap_available", lambda: False)
    from workers.live_protocol_worker import LiveProtocolWorker
    progress_msgs = []
    errors = []
    w = LiveProtocolWorker(protocol="ARP")
    w.progress.connect(progress_msgs.append)
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(5000)
    _pump()
    assert finished, "worker did not finish within 5 s without Npcap"
    assert not w.isRunning()
    assert not errors
    assert any("npcap" in m.lower() or "libpcap" in m.lower() for m in progress_msgs)
    _cleanup(w)


class _FakeFeed:
    """Stands in for LiveProtocolFeed so the loop test doesn't need real capture."""

    def __init__(self, protocol, on_event, on_error):
        self.protocol = protocol
        self.event_count = 0
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def test_start_stop_lifecycle_with_capability(monkeypatch):
    """RULE-T2: with admin+Npcap simulated, start() -> brief run -> stop() ->
    isRunning() False, and the underlying feed is stopped before thread exit."""
    monkeypatch.setattr("modules.utils.is_admin", lambda: True)
    monkeypatch.setattr("modules.utils.is_npcap_available", lambda: True)

    fake_feeds: list = []

    def _make_fake_feed(protocol, on_event, on_error):
        f = _FakeFeed(protocol, on_event, on_error)
        fake_feeds.append(f)
        return f

    monkeypatch.setattr("modules.live_protocol_feed.LiveProtocolFeed", _make_fake_feed)

    from workers.live_protocol_worker import LiveProtocolWorker
    w = LiveProtocolWorker(protocol="ARP")
    w.start()
    time.sleep(0.5)
    assert w.isRunning()
    w.stop()
    finished = w.wait(5000)
    assert finished, "worker did not stop within 5 s"
    assert not w.isRunning()
    assert len(fake_feeds) == 1
    assert fake_feeds[0].started is True
    assert fake_feeds[0].stopped is True
    _cleanup(w)
