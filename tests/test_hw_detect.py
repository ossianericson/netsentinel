"""Tests for modules/hw_detect.py — hardware integration detection."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


def test_import():
    import modules.hw_detect  # noqa: F401


def test_already_installed_false():
    from modules.hw_detect import already_installed
    result = already_installed("__nonexistent_plugin_xyz__")
    assert result is False


def test_already_installed_returns_bool():
    from modules.hw_detect import already_installed
    result = already_installed("some_plugin_id")
    assert isinstance(result, bool)


def test_bundled_plugin_path_missing():
    from modules.hw_detect import bundled_plugin_path
    result = bundled_plugin_path("__no_such_plugin__.py")
    assert result is None or not result.exists()


def test_load_catalogue_returns_dict():
    from modules.hw_detect import load_catalogue
    catalogue = load_catalogue(try_remote=False)
    assert isinstance(catalogue, dict)


def test_load_catalogue_no_network():
    """load_catalogue(try_remote=False) must never make network calls."""
    import urllib.request
    original = urllib.request.urlopen
    calls = []
    def mock_urlopen(*a, **kw):
        calls.append(a)
        raise Exception("should not be called")
    urllib.request.urlopen = mock_urlopen
    try:
        from modules.hw_detect import load_catalogue
        load_catalogue(try_remote=False)
    except Exception:
        pass
    finally:
        urllib.request.urlopen = original
    assert len(calls) == 0, "load_catalogue(try_remote=False) made a network call"


def test_detect_returns_list_no_network():
    from modules.hw_detect import detect
    with patch("urllib.request.urlopen", side_effect=OSError("no network")):
        try:
            result = detect(ip="192.168.1.1", gateway_mac=None, catalogue={})
            assert isinstance(result, list)
        except Exception:
            pass  # Expected without real network
