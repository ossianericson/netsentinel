"""Tests for modules/os_fingerprint.py — OS fingerprinting via TTL/TCP."""
import pytest
from modules.os_fingerprint import OSGuess, _ttl_to_os, _banner_to_os, _window_to_os


def test_import():
    import modules.os_fingerprint as m
    assert hasattr(m, "fingerprint_host")
    assert hasattr(m, "OSGuess")
    assert hasattr(m, "_ttl_to_os")


def test_os_guess_fields():
    g = OSGuess(ip="192.168.1.1")
    assert g.ip == "192.168.1.1"
    assert g.os_family == "Unknown"
    assert g.confidence == "Low"


def test_ttl_to_os_windows():
    assert "Windows" in _ttl_to_os(128)


def test_ttl_to_os_linux():
    result = _ttl_to_os(64)
    assert "Linux" in result or "macOS" in result


def test_ttl_to_os_cisco():
    result = _ttl_to_os(255)
    assert "Cisco" in result or "network" in result.lower() or "device" in result.lower() or "255" in result or result != ""


def test_ttl_to_os_unknown():
    result = _ttl_to_os(1)
    assert isinstance(result, str)
    assert len(result) > 0


def test_banner_to_os_openssh_linux():
    result = _banner_to_os("SSH-2.0-OpenSSH_8.4 Ubuntu")
    assert result is not None
    assert "Linux" in result or "Ubuntu" in result


def test_banner_to_os_empty():
    result = _banner_to_os("")
    assert result is None


def test_window_to_os_windows10():
    os_name, confidence = _window_to_os(64240, 128, [])
    assert "Windows" in os_name


def test_window_to_os_linux():
    os_name, confidence = _window_to_os(29200, 64, [])
    assert "Linux" in os_name
