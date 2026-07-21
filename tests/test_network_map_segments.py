"""Behavioural tests -- NetworkMapPage segment collapse (Part 1/D).

Covers: _effective_devices() applying collapse_to_segments() to the last
render() call's real devices, the segment-note toolbar label, and
_on_node_clicked() routing a synthetic segment id to expand/collapse instead
of the normal device-click passthrough (which still re-emits node_clicked
for a real device, unchanged).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not installed")

from ui.pages.network_map_page import NetworkMapPage


@pytest.fixture(autouse=True)
def _isolate_render_cache(tmp_path, monkeypatch):
    """render() persists its inputs via modules.network_map_cache by default
    -- redirect that to a temp dir so the test suite never overwrites a real
    user's network_map_render_cache.json under %LOCALAPPDATA%\\NetSentinel."""
    monkeypatch.setattr("modules.network_map_cache.get_app_data_dir", lambda: tmp_path)


@pytest.fixture
def page(qt_app):
    p = NetworkMapPage()
    # Simulate an available interactive view without a real QWebEngineView --
    # the production setHtml()/runJavaScript() calls are not under test here.
    p._web_available = True
    p._web_view = MagicMock()
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already destroyed -- safe to skip
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _many_devices(n: int, subnet: int = 0) -> list:
    return [
        {"ip": f"10.{subnet}.0.{i}", "mac": f"aa:bb:cc:{subnet:02x}:00:{i:02x}",
         "hostname": f"dev{i}", "risk_level": "CLEAN"}
        for i in range(1, n + 1)
    ]


def _few_devices() -> list:
    return [
        {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:01", "hostname": "PC", "risk_level": "CLEAN"},
        {"ip": "192.168.1.11", "mac": "aa:bb:cc:dd:ee:02", "hostname": "Phone", "risk_level": "CLEAN"},
    ]


class TestEffectiveDevices:
    def test_below_threshold_unchanged(self, page):
        page.render(devices=_few_devices(), gateway_ip="192.168.1.1")
        assert page._effective_devices() == _few_devices()

    def test_above_threshold_collapses(self, page):
        page.render(devices=_many_devices(200), gateway_ip="10.0.0.1")
        out = page._effective_devices()
        assert len(out) == 1
        assert out[0]["device_type"] == "segment"

    def test_expanding_a_segment_shows_real_devices_again(self, page):
        page.render(devices=_many_devices(200), gateway_ip="10.0.0.1")
        page._expanded_segments.add("10.0.0.0/24")
        out = page._effective_devices()
        assert len(out) == 200


class TestSegmentNoteLabel:
    def test_hidden_below_threshold(self, page):
        page.render(devices=_few_devices(), gateway_ip="192.168.1.1")
        assert page._segment_note_label.isVisibleTo(page) is False

    def test_visible_above_threshold_with_device_count(self, page):
        page.render(devices=_many_devices(200), gateway_ip="10.0.0.1")
        assert page._segment_note_label.isVisibleTo(page) is True
        assert "200" in page._segment_note_label.text()


class TestNodeClickRouting:
    def test_segment_click_toggles_expanded_and_does_not_emit_node_clicked(self, page):
        page.render(devices=_many_devices(200), gateway_ip="10.0.0.1")
        emitted = []
        page.node_clicked.connect(emitted.append)

        page._on_node_clicked("10.0.0.0/24")

        assert "10.0.0.0/24" in page._expanded_segments
        assert emitted == []

    def test_second_click_on_same_segment_collapses_again(self, page):
        page.render(devices=_many_devices(200), gateway_ip="10.0.0.1")
        page._on_node_clicked("10.0.0.0/24")
        page._on_node_clicked("10.0.0.0/24")
        assert "10.0.0.0/24" not in page._expanded_segments

    def test_real_device_click_emits_node_clicked(self, page):
        page.render(devices=_few_devices(), gateway_ip="192.168.1.1")
        emitted = []
        page.node_clicked.connect(emitted.append)

        page._on_node_clicked("192.168.1.10")

        assert emitted == ["192.168.1.10"]
        assert page._expanded_segments == set()


class TestOfficeVpnScenario:
    """Part 1 verification step 4: a 715-device fixture (the reported office/VPN
    scan result) must render as a small, readable set of segment nodes, not a
    715-node wall -- and expanding one segment must recover exactly its devices."""

    @staticmethod
    def _office_fixture() -> list:
        # Three /24s totalling 715 -- mirrors the reported "715 devices" scan.
        # Each count stays <= 254 (a /24's usable host range).
        devices = []
        for subnet, count in ((2, 250), (3, 250), (4, 215)):
            for i in range(1, count + 1):
                devices.append({
                    "ip": f"10.4.{subnet}.{i}",
                    "mac": f"aa:bb:cc:{subnet:02x}:00:{i:02x}",
                    "hostname": "", "risk_level": "UNKNOWN",
                })
        assert len(devices) == 715
        return devices

    def test_715_devices_collapse_to_a_handful_of_segment_nodes(self, page):
        page.render(devices=self._office_fixture(), gateway_ip="10.4.0.1")
        out = page._effective_devices()
        assert 1 <= len(out) <= 5, f"expected a small readable node set, got {len(out)}"
        assert all(d.get("device_type") == "segment" for d in out)
        assert sum(d["segment_count"] for d in out) == 715

    def test_expanding_one_segment_recovers_its_real_devices_only(self, page):
        page.render(devices=self._office_fixture(), gateway_ip="10.4.0.1")
        segment_ip = page._effective_devices()[0]["ip"]

        page._on_node_clicked(segment_ip)
        out = page._effective_devices()

        expanded_count = sum(1 for d in out if d.get("ip", "").startswith(segment_ip.rsplit(".", 1)[0]))
        placeholder_count = sum(1 for d in out if d.get("device_type") == "segment")
        assert placeholder_count == len(page._effective_devices()) - expanded_count
        # every device is still accounted for exactly once
        real = sum(1 for d in out if d.get("device_type") != "segment")
        placeholders = sum(d.get("segment_count", 0) for d in out if d.get("device_type") == "segment")
        assert real + placeholders == 715
