"""
tests/test_store_update_flow.py — Part B: Store-aware update flow.

The GitHub-releases-based update check ("Download" link / winget upgrade
instructions) is wrong for a Microsoft Store install — Store apps auto-update
and external download/winget is disallowed there. These tests cover:

1. store_update_url() — the Store deep link is well-formed.
2. AppHeaderMixin._start_update_check() — the background GitHub check must
   never run in the Store build (no bar can appear if the check never runs).
3. The Help tab's Updates card swaps to a "Open Microsoft Store" button
   instead of "Check for Updates" when running in the Store build.

RULE-TP4-DASH: none of these construct a real Dashboard — the mixin method is
exercised on a minimal stub, and build_help_tab() takes a plain window stub.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest


# ── store_update_url() ─────────────────────────────────────────────────────

def test_store_update_url_targets_correct_product():
    from modules.utils import store_update_url
    parsed = urlparse(store_update_url())
    assert parsed.scheme == "ms-windows-store"
    assert parsed.hostname == "pdp"
    assert parse_qs(parsed.query).get("productid") == ["9NZ124C7HJWS"]


# ── AppHeaderMixin._start_update_check() guard ─────────────────────────────

def test_start_update_check_never_spawns_thread_for_store_build(monkeypatch):
    """Patching Thread.start (rather than relying on urlopen raising inside
    the background thread's own `except Exception: pass`, which the main
    test thread can never observe) is what makes this assertion deterministic
    — a daemon thread's exception can't fail this test, but never starting
    the thread at all can be asserted synchronously."""
    from ui.header import AppHeaderMixin

    class _HeaderStub(AppHeaderMixin):
        pass

    monkeypatch.setattr("modules.utils.is_store_app", lambda: True)

    def _urlopen_must_not_be_reached(*a, **kw):
        raise AssertionError("urlopen must not be reached in the Store build")
    monkeypatch.setattr("urllib.request.urlopen", _urlopen_must_not_be_reached)

    started = []
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.append(self))

    _HeaderStub()._start_update_check()

    assert started == [], "Store build must never spawn the GitHub/winget update-check thread"


def test_start_update_check_spawns_thread_for_non_store_build(monkeypatch):
    """Sanity check for the guard's other branch — the existing GitHub check
    behaviour must be untouched outside the Store build."""
    from ui.header import AppHeaderMixin

    class _HeaderStub(AppHeaderMixin):
        pass

    monkeypatch.setattr("modules.utils.is_store_app", lambda: False)

    started = []
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.append(self))

    _HeaderStub()._start_update_check()

    assert len(started) == 1, "Non-Store build must still start the background update check"


# ── Help tab Updates card — Store variant ──────────────────────────────────

@pytest.fixture
def _help_window_stub():
    return SimpleNamespace(
        _open_settings_dialog=lambda: None,
        _check_for_updates=lambda: None,
    )


def _button_texts(page):
    from PyQt6.QtWidgets import QPushButton
    return {b.text() for b in page.findChildren(QPushButton)}


def test_update_card_shows_store_button_in_store_build(qt_app, monkeypatch, _help_window_stub):
    pytest.importorskip("PyQt6", reason="PyQt6 not installed")
    from ui.help_tab import build_help_tab

    monkeypatch.setattr("modules.utils.is_store_app", lambda: True)
    page = build_help_tab(_help_window_stub)
    try:
        texts = _button_texts(page)
        assert "Open Microsoft Store" in texts
        assert "Check for Updates" not in texts
    finally:
        page.deleteLater()
        if qt_app:
            for _ in range(3):
                qt_app.processEvents()


# ── Belt-and-suspenders: _HelpTabsMixin._check_for_updates() ──────────────
# Covers any other caller of the manual "Check for Updates" flow (the Help
# tab button wires to this, not directly to urllib) — must also show the
# Store message and never touch the network.

def test_manual_check_for_updates_shows_store_message(qt_app, monkeypatch):
    pytest.importorskip("PyQt6", reason="PyQt6 not installed")
    from PyQt6.QtWidgets import QLabel
    from ui.tabs_help import _HelpTabsMixin

    class _Stub(_HelpTabsMixin):
        pass

    stub = _Stub()
    stub._update_lbl = QLabel()

    monkeypatch.setattr("modules.utils.is_store_app", lambda: True)

    def _urlopen_must_not_be_reached(*a, **kw):
        raise AssertionError("urlopen must not be reached in the Store build")
    monkeypatch.setattr("urllib.request.urlopen", _urlopen_must_not_be_reached)

    stub._check_for_updates()

    assert "Microsoft Store" in stub._update_lbl.text()
    stub._update_lbl.deleteLater()
    if qt_app:
        for _ in range(3):
            qt_app.processEvents()


def test_update_card_shows_check_button_outside_store_build(qt_app, monkeypatch, _help_window_stub):
    pytest.importorskip("PyQt6", reason="PyQt6 not installed")
    from ui.help_tab import build_help_tab

    monkeypatch.setattr("modules.utils.is_store_app", lambda: False)
    page = build_help_tab(_help_window_stub)
    try:
        texts = _button_texts(page)
        assert "Check for Updates" in texts
        assert "Open Microsoft Store" not in texts
    finally:
        page.deleteLater()
        if qt_app:
            for _ in range(3):
                qt_app.processEvents()
