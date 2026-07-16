"""Tests for workers/wifi_monitor_worker.py (RULE-T2)."""
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


def test_import():
    from workers.wifi_monitor_worker import WiFiMonitorWorker  # noqa: F401


def test_instantiation():
    from workers.wifi_monitor_worker import WiFiMonitorWorker
    w = WiFiMonitorWorker(iface="")
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist():
    from workers.wifi_monitor_worker import WiFiMonitorWorker
    w = WiFiMonitorWorker()
    assert hasattr(w, "frame_captured")
    assert hasattr(w, "error")
    assert hasattr(w, "status")
    assert hasattr(w, "unsupported")
    _cleanup(w)


def test_start_stop_lifecycle():
    """Worker must stop within 5 s after stop() is called."""
    from workers.wifi_monitor_worker import WiFiMonitorWorker
    errors = []
    w = WiFiMonitorWorker(iface="")
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.5)
    w.stop()
    finished = w.wait(5000)
    assert finished, "WiFiMonitorWorker did not stop within 5 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are allowed (scapy/Npcap missing in CI); thread must stop.


def test_classify_beacon():
    pytest.importorskip("scapy.all")
    from scapy.layers.dot11 import Dot11, Dot11Beacon
    from workers.wifi_monitor_worker import _classify
    pkt = Dot11(type=0, subtype=8) / Dot11Beacon()
    assert _classify(pkt) == "Beacon"


def test_classify_eapol():
    pytest.importorskip("scapy.all")
    from scapy.layers.dot11 import Dot11
    from scapy.layers.eap import EAPOL
    from workers.wifi_monitor_worker import _classify
    pkt = Dot11(type=2, subtype=0) / EAPOL()
    assert _classify(pkt) == "EAPOL"


def test_classify_unknown_falls_back_to_type_subtype():
    pytest.importorskip("scapy.all")
    from scapy.layers.dot11 import Dot11
    from workers.wifi_monitor_worker import _classify
    pkt = Dot11(type=1, subtype=11)  # RTS control frame, not separately handled
    assert _classify(pkt) == "Type 1/11"
