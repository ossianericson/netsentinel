"""
tests/test_service_bandwidth_overlay.py — Unit tests for
modules/service_bandwidth_overlay.py (S6-6).
"""

from modules.service_bandwidth_overlay import build_overlay_note


def test_no_note_when_failure_layer_identified():
    assert build_overlay_note("Netflix", "isp", 3) is None


def test_no_note_when_no_active_devices():
    assert build_overlay_note("Netflix", "none", 0) is None


def test_note_when_healthy_and_devices_active():
    note = build_overlay_note("Netflix", "none", 3)
    assert note is not None
    assert "Netflix" in note
    assert "3 other active devices" in note


def test_note_uses_singular_device():
    note = build_overlay_note("Netflix", "none", 1)
    assert "1 other active device" in note
    assert "devices" not in note
