"""Tests for plugin health tracking (RULE-T1).

Covers: _record_success, _record_error, _reset_health, _path_hash,
circuit-breaker auto-disable, degraded-hour constant.

Patches _load_health / _save_health so no QSettings / QApplication needed.
"""
from __future__ import annotations

from unittest.mock import patch



# ── storage stub ──────────────────────────────────────────────────────────────


def _fresh() -> dict:
    return {
        "success": 0, "errors": 0, "consecutive": 0,
        "last_ok": 0.0, "last_err": "", "disabled": False,
    }


def _make_store(initial: dict | None = None):
    """Return (store_dict, fake_load, fake_save) for monkeypatching."""
    store: dict = {}
    if initial is not None:
        store["/fake/plugin.py"] = dict(initial)

    def _load(path: str) -> dict:
        return dict(store.get(path, _fresh()))

    def _save(path: str, h: dict) -> None:
        store[path] = dict(h)

    return store, _load, _save


# ── _record_success ───────────────────────────────────────────────────────────


def test_record_success_increments_counter():
    store, _load, _save = _make_store()
    with patch("ui.pages.hardware_integration_page._load_health", side_effect=_load), \
         patch("ui.pages.hardware_integration_page._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_success
        h = _record_success("/fake/plugin.py")

    assert h["success"] == 1
    assert h["errors"] == 0
    assert h["consecutive"] == 0
    assert h["disabled"] is False
    assert h["last_ok"] > 0


def test_record_success_resets_consecutive_errors():
    store, _load, _save = _make_store({**_fresh(), "errors": 3, "consecutive": 3})
    with patch("ui.pages.hardware_integration_page._load_health", side_effect=_load), \
         patch("ui.pages.hardware_integration_page._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_success
        h = _record_success("/fake/plugin.py")

    assert h["consecutive"] == 0
    assert h["errors"] == 3   # total error count unchanged
    assert h["success"] == 1


def test_record_success_clears_disabled():
    store, _load, _save = _make_store({**_fresh(), "disabled": True, "consecutive": 10})
    with patch("ui.pages.hardware_integration_page._load_health", side_effect=_load), \
         patch("ui.pages.hardware_integration_page._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_success
        h = _record_success("/fake/plugin.py")

    assert h["disabled"] is False


# ── _record_error ─────────────────────────────────────────────────────────────


def test_record_error_increments_counters():
    store, _load, _save = _make_store()
    with patch("ui.pages.hardware_integration_page._load_health", side_effect=_load), \
         patch("ui.pages.hardware_integration_page._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_error
        h = _record_error("/fake/plugin.py", "connection timeout")

    assert h["errors"] == 1
    assert h["consecutive"] == 1
    assert h["last_err"] == "connection timeout"
    assert h["disabled"] is False


def test_record_error_accumulates_consecutive():
    store, _load, _save = _make_store({**_fresh(), "errors": 5, "consecutive": 5})
    with patch("ui.pages.hardware_integration_page._load_health", side_effect=_load), \
         patch("ui.pages.hardware_integration_page._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_error
        h = _record_error("/fake/plugin.py", "again")

    assert h["errors"] == 6
    assert h["consecutive"] == 6


def test_circuit_breaker_fires_at_threshold():
    """10 consecutive errors must set disabled=True."""
    store, _load, _save = _make_store({**_fresh(), "errors": 9, "consecutive": 9})
    with patch("ui.pages.hardware_integration_page._load_health", side_effect=_load), \
         patch("ui.pages.hardware_integration_page._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_error, _CIRCUIT_BREAK_THRESHOLD
        h = _record_error("/fake/plugin.py", "tenth failure")

    assert h["consecutive"] == _CIRCUIT_BREAK_THRESHOLD
    assert h["disabled"] is True


def test_circuit_breaker_threshold_is_10():
    from ui.pages.hardware_integration_page import _CIRCUIT_BREAK_THRESHOLD
    assert _CIRCUIT_BREAK_THRESHOLD == 10


def test_circuit_breaker_does_not_fire_below_threshold():
    store, _load, _save = _make_store({**_fresh(), "consecutive": 8})
    with patch("ui.pages.hardware_integration_page._load_health", side_effect=_load), \
         patch("ui.pages.hardware_integration_page._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_error
        h = _record_error("/fake/plugin.py", "error")

    assert h["disabled"] is False


# ── _reset_health ─────────────────────────────────────────────────────────────


def test_reset_health_clears_disabled_and_consecutive():
    store, _load, _save = _make_store(
        {**_fresh(), "consecutive": 10, "disabled": True, "errors": 10}
    )
    with patch("ui.pages.hardware_integration_page._load_health", side_effect=_load), \
         patch("ui.pages.hardware_integration_page._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _reset_health
        _reset_health("/fake/plugin.py")

    saved = store["/fake/plugin.py"]
    assert saved["disabled"] is False
    assert saved["consecutive"] == 0
    assert saved["errors"] == 10   # total error count preserved


# ── _load_health defaults ─────────────────────────────────────────────────────


def test_load_health_fresh_path_returns_defaults():
    with patch("ui.pages.hardware_integration_page.QSettings") as mock_qs:
        mock_qs.return_value.value.return_value = None
        from ui.pages.hardware_integration_page import _load_health
        h = _load_health("/fresh/path.py")

    assert h["success"] == 0
    assert h["errors"] == 0
    assert h["consecutive"] == 0
    assert h["disabled"] is False


# ── constants ─────────────────────────────────────────────────────────────────


def test_degraded_hours_constant():
    from ui.pages.hardware_integration_page import _DEGRADED_HOURS
    assert _DEGRADED_HOURS == 24


# ── _path_hash ────────────────────────────────────────────────────────────────


def test_path_hash_is_12_chars():
    from ui.pages.hardware_integration_page import _path_hash
    assert len(_path_hash("/some/path/plugin.py")) == 12


def test_path_hash_deterministic():
    from ui.pages.hardware_integration_page import _path_hash
    assert _path_hash("/a/b.py") == _path_hash("/a/b.py")


def test_path_hash_unique_per_path():
    from ui.pages.hardware_integration_page import _path_hash
    assert _path_hash("/a/b.py") != _path_hash("/a/c.py")


# ── consecutive-error isolation across paths ──────────────────────────────────


def test_separate_paths_have_independent_health():
    """Errors on path A must not affect path B's consecutive counter."""
    store: dict = {}

    def _load(path):
        return dict(store.get(path, _fresh()))

    def _save(path, h):
        store[path] = dict(h)

    with patch("ui.pages.hardware_integration_page._load_health", side_effect=_load), \
         patch("ui.pages.hardware_integration_page._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_error, _record_success
        for _ in range(9):
            _record_error("/path/a.py", "err")
        _record_success("/path/b.py")

    assert store["/path/a.py"]["consecutive"] == 9
    assert store["/path/b.py"]["consecutive"] == 0
