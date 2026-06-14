"""Tests for workers/bandwidth_worker.py (RULE-T2)."""
import time
import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ── Import guard ──────────────────────────────────────────────────────────────

def test_import():
    from workers.bandwidth_worker import BandwidthOverlayWorker  # noqa: F401


# ── Instantiation ─────────────────────────────────────────────────────────────

def test_instantiation():
    from workers.bandwidth_worker import BandwidthOverlayWorker
    app = QApplication.instance()
    w = BandwidthOverlayWorker(interval_s=5.0, parent=None)
    assert not w.isRunning()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already deleted
    if app:
        for _ in range(3):
            app.processEvents()


# ── Start / stop lifecycle ────────────────────────────────────────────────────

def test_start_stop_lifecycle():
    """Worker must start, then stop cleanly within a short timeout."""
    from workers.bandwidth_worker import BandwidthOverlayWorker
    app = QApplication.instance()
    errors = []
    w = BandwidthOverlayWorker(interval_s=60.0, parent=None)
    w.error.connect(errors.append)
    w.start()
    # Give the thread a moment to enter run() — either it starts or emits error
    time.sleep(0.3)
    w.stop()
    finished = w.wait(3000)  # ms
    assert finished, "BandwidthOverlayWorker did not stop within 3 s"
    assert not w.isRunning()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal
    if app:
        for _ in range(3):
            app.processEvents()
    # Worker is allowed to emit an error (Scapy/Npcap unavailable in CI),
    # but it must NOT still be running after stop().
    # Errors are informational only in this test.


# ── _bw_class helper ──────────────────────────────────────────────────────────

def test_bw_class_helpers():
    from modules.topology_cytoscape import _bw_class, _bw_label

    assert _bw_class(6_000_000) == "traffic-high"
    assert _bw_class(1_000_000) == "traffic-medium"
    assert _bw_class(100_000) == "traffic-low"
    assert _bw_class(0.0) == ""

    label = _bw_label(4_500_000)
    assert "Mbps" in label or "mbps" in label.lower()

    label_k = _bw_label(50_000)
    assert "Kbps" in label_k or "kbps" in label_k.lower()


# ── build_cytoscape_elements with bw_by_mac ───────────────────────────────────

def test_cytoscape_elements_traffic_overlay():
    from modules.topology_cytoscape import build_cytoscape_elements

    devices = [
        {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:01",
         "hostname": "laptop", "risk_level": "LOW", "vendor": "Apple"},
        {"ip": "192.168.1.11", "mac": "aa:bb:cc:dd:ee:02",
         "hostname": "nas", "risk_level": "MEDIUM", "vendor": "Synology"},
    ]
    bw = {
        "aa:bb:cc:dd:ee:01": 7_000_000,  # 7 Mbps → traffic-high
        "aa:bb:cc:dd:ee:02": 900_000,    # 0.9 Mbps → traffic-medium
    }
    result = build_cytoscape_elements(devices=devices, bw_by_mac=bw)
    nodes = [e for e in result["elements"] if e["group"] == "nodes"]

    laptop = next((n for n in nodes if n["data"].get("mac") == "aa:bb:cc:dd:ee:01"), None)
    nas    = next((n for n in nodes if n["data"].get("mac") == "aa:bb:cc:dd:ee:02"), None)

    assert laptop is not None, "laptop node not found"
    assert "traffic-high" in laptop["classes"], laptop["classes"]
    assert laptop["data"]["bw_mbps"] > 0

    assert nas is not None, "nas node not found"
    assert "traffic-medium" in nas["classes"], nas["classes"]

    # Without bw_by_mac, no traffic classes should appear
    result2 = build_cytoscape_elements(devices=devices)
    nodes2  = [e for e in result2["elements"] if e["group"] == "nodes"]
    for n in nodes2:
        assert "traffic-" not in n["classes"]


def test_cytoscape_html_accepts_bw_by_mac():
    from modules.topology_cytoscape import build_cytoscape_html

    devices = [{"ip": "10.0.0.1", "mac": "de:ad:be:ef:00:01",
                "hostname": "host1", "risk_level": "LOW", "vendor": ""}]
    html = build_cytoscape_html(
        devices=devices,
        bw_by_mac={"de:ad:be:ef:00:01": 2_500_000},
    )
    assert "<html>" in html
    assert "traffic-medium" in html
