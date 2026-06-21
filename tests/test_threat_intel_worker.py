"""Tests for workers/threat_intel_worker.py (RULE-T2)."""
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


# ── Import guard ──────────────────────────────────────────────────────────────

def test_import_feed_refresh():
    from workers.threat_intel_worker import ThreatFeedRefreshWorker  # noqa: F401


def test_import_abuse_ip():
    from workers.threat_intel_worker import AbuseIpDbWorker  # noqa: F401


# ── ThreatFeedRefreshWorker ───────────────────────────────────────────────────

def test_feed_refresh_instantiation():
    from workers.threat_intel_worker import ThreatFeedRefreshWorker
    w = ThreatFeedRefreshWorker()
    assert not w.isRunning()
    _cleanup(w)


def test_feed_refresh_signals_exist():
    from workers.threat_intel_worker import ThreatFeedRefreshWorker
    w = ThreatFeedRefreshWorker()
    assert hasattr(w, "progress")
    assert hasattr(w, "result_ready")
    assert hasattr(w, "error")
    _cleanup(w)


def test_feed_refresh_lifecycle():
    """One-shot worker; must complete within 10 s (or error out quickly in CI)."""
    from workers.threat_intel_worker import ThreatFeedRefreshWorker
    errors = []
    w = ThreatFeedRefreshWorker()
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(10000)
    assert finished, "ThreatFeedRefreshWorker did not finish within 10 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are expected in CI (no network for feed downloads).


# ── AbuseIpDbWorker ───────────────────────────────────────────────────────────

def test_abuse_ip_instantiation():
    from workers.threat_intel_worker import AbuseIpDbWorker
    w = AbuseIpDbWorker(ip="8.8.8.8", api_key="dummy")
    assert not w.isRunning()
    _cleanup(w)


def test_abuse_ip_lifecycle():
    """One-shot worker; must complete quickly (error with dummy key in CI)."""
    from workers.threat_intel_worker import AbuseIpDbWorker
    errors = []
    w = AbuseIpDbWorker(ip="8.8.8.8", api_key="dummy_key_for_test")
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(10000)
    assert finished, "AbuseIpDbWorker did not finish within 10 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are expected in CI (invalid key / no network).
