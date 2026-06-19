"""Tests for ui/perf_audit.py (UX Sprint 10, S10-1).

Pure stdlib module — no QApplication needed.
"""
import logging

from ui.perf_audit import (
    NAV_SLOW_THRESHOLD_MS,
    _slowest_page_inits,
    profile_page_init,
    warn_if_nav_slow,
)


def test_warn_if_nav_slow_logs_warning_above_threshold(caplog):
    with caplog.at_level(logging.WARNING, logger="netsentinel.perf"):
        warn_if_nav_slow("Devices", NAV_SLOW_THRESHOLD_MS + 50)
    assert any("Devices" in r.message for r in caplog.records)
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_warn_if_nav_slow_silent_below_threshold(caplog):
    with caplog.at_level(logging.WARNING, logger="netsentinel.perf"):
        warn_if_nav_slow("Devices", NAV_SLOW_THRESHOLD_MS - 50)
    assert not caplog.records


def test_warn_if_nav_slow_silent_at_exact_threshold(caplog):
    with caplog.at_level(logging.WARNING, logger="netsentinel.perf"):
        warn_if_nav_slow("Devices", NAV_SLOW_THRESHOLD_MS)
    assert not caplog.records


def test_profile_page_init_disabled_by_default_returns_build_result(monkeypatch):
    monkeypatch.delenv("NETSENTINEL_PROFILE_PAGES", raising=False)
    calls = []

    def _build():
        calls.append(1)
        return "main-widget"

    result = profile_page_init(_build)
    assert result == "main-widget"
    assert calls == [1]


def test_profile_page_init_enabled_still_returns_build_result(monkeypatch):
    monkeypatch.setenv("NETSENTINEL_PROFILE_PAGES", "1")

    def _build():
        return "main-widget"

    result = profile_page_init(_build)
    assert result == "main-widget"


def test_slowest_page_inits_filters_to_pages_init_and_sorts_descending():
    stats = {
        ("ui/pages/foo_page.py", 10, "__init__"): (1, 1, 0.01, 0.05, {}),
        ("ui/pages/bar_page.py", 20, "__init__"): (1, 1, 0.01, 0.20, {}),
        ("ui/pages/foo_page.py", 30, "_build_ui"): (1, 1, 0.01, 99.0, {}),
        ("modules/utils.py", 5, "__init__"): (1, 1, 0.01, 50.0, {}),
    }
    slowest = _slowest_page_inits(stats, n=10)
    assert [label for _, label in slowest] == ["bar_page.__init__", "foo_page.__init__"]
    assert slowest[0][0] == 0.20


def test_slowest_page_inits_respects_n_limit():
    stats = {
        (f"ui/pages/p{i}_page.py", 1, "__init__"): (1, 1, 0.0, float(i), {})
        for i in range(15)
    }
    slowest = _slowest_page_inits(stats, n=10)
    assert len(slowest) == 10
    assert slowest[0][0] == 14.0
