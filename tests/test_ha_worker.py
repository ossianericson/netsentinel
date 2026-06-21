"""Tests for workers/ha_worker.py (RULE-T2)."""
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

def test_import():
    from workers.ha_worker import HaScanWorker  # noqa: F401


def test_import_mac_lookup():
    from workers.ha_worker import MacLookupWorker  # noqa: F401


# ── HaScanWorker ──────────────────────────────────────────────────────────────

def test_ha_scan_instantiation():
    from workers.ha_worker import HaScanWorker
    w = HaScanWorker(hosts=[])
    assert not w.isRunning()
    _cleanup(w)


def test_ha_scan_lifecycle_empty():
    """HaScanWorker with empty host list is one-shot and must complete quickly."""
    from workers.ha_worker import HaScanWorker
    errors = []
    results = []
    w = HaScanWorker(hosts=[])
    w.error.connect(errors.append)
    w.results_ready.connect(results.append)
    w.start()
    finished = w.wait(5000)
    assert finished, "HaScanWorker did not finish within 5 s"
    assert not w.isRunning()
    _cleanup(w)


def test_ha_scan_signals_exist():
    from workers.ha_worker import HaScanWorker
    w = HaScanWorker(hosts=[])
    assert hasattr(w, "results_ready")
    assert hasattr(w, "error")
    assert hasattr(w, "status")
    _cleanup(w)


# ── MacLookupWorker ───────────────────────────────────────────────────────────

def test_mac_lookup_instantiation():
    from workers.ha_worker import MacLookupWorker
    w = MacLookupWorker(mac="aa:bb:cc:dd:ee:ff")
    assert not w.isRunning()
    _cleanup(w)


def test_mac_lookup_lifecycle():
    """MacLookupWorker is one-shot; must complete within 5 s."""
    from workers.ha_worker import MacLookupWorker
    errors = []
    w = MacLookupWorker(mac="00:00:00:00:00:00")
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(5000)
    assert finished, "MacLookupWorker did not finish within 5 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors allowed (no network in CI).
