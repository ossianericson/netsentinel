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

import platform
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest


# ── is_store_app() — the REAL detection, never mocked ──────────────────────
# RULE-T3 regression for the v2.1.33 Store-banner bug. Every other test in this
# file monkeypatches is_store_app(), so they verify the guard's behaviour GIVEN a
# correct answer and can never see a broken detection. That blind spot shipped a
# permanently-False is_store_app() to the Store, where the winget/GitHub update
# bar then rendered for real users.

@pytest.mark.skipif(platform.system() != "Windows", reason="MSIX packaging is Windows-only")
def test_package_family_name_syscall_receives_an_intact_process_handle():
    """The syscall must actually reach the API and report package identity.

    ctypes marshals an undeclared return value as a 32-bit C int, truncating
    GetCurrentProcess()'s (HANDLE)-1 pseudo-handle to 0x00000000FFFFFFFF. The API
    then rejects the handle with ERROR_INVALID_HANDLE (6) *before* it inspects
    package identity — so the call returns 6 on every machine, packaged or not,
    and `ret == 122` is never true.

    A handle that arrives intact yields exactly one of these two codes.
    """
    from modules.utils import (
        APPMODEL_ERROR_NO_PACKAGE,
        ERROR_INSUFFICIENT_BUFFER,
        package_family_name_status,
    )

    rc = package_family_name_status()

    assert rc in (ERROR_INSUFFICIENT_BUFFER, APPMODEL_ERROR_NO_PACKAGE), (
        f"GetPackageFamilyName returned {rc}; expected {ERROR_INSUFFICIENT_BUFFER} "
        f"(packaged) or {APPMODEL_ERROR_NO_PACKAGE} (not packaged). rc=6 means "
        f"ctypes truncated the process pseudo-handle — declare restype/argtypes "
        f"on both GetCurrentProcess and GetPackageFamilyName."
    )


def test_is_store_app_returns_a_bool_and_never_raises():
    from modules.utils import is_store_app
    assert isinstance(is_store_app(), bool)


# ── store_update_url() ─────────────────────────────────────────────────────

def test_store_update_url_targets_correct_product():
    from modules.utils import store_update_url
    parsed = urlparse(store_update_url())
    assert parsed.scheme == "ms-windows-store"
    assert parsed.hostname == "pdp"
    assert parse_qs(parsed.query).get("productid") == ["9NZ124C7HJWS"]


# ── AppHeaderMixin._start_update_check() guard ─────────────────────────────

@pytest.mark.parametrize("store_build", [True, False])
def test_start_update_check_spawns_thread_in_both_builds(monkeypatch, store_build):
    """GitHub releases is the version oracle for Store builds too.

    Patching Thread.start (rather than relying on urlopen raising inside the
    background thread's own `except Exception: pass`, which the main test thread
    can never observe) is what makes this assertion deterministic — a daemon
    thread's exception can't fail this test, but the thread starting at all can
    be asserted synchronously. Which remedy the resulting bar offers is the
    business of _on_update_available(), covered below.
    """
    from ui.header import AppHeaderMixin

    class _HeaderStub(AppHeaderMixin):
        pass

    monkeypatch.setattr("modules.utils.is_store_app", lambda: store_build)

    started = []
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.append(self))

    _HeaderStub()._start_update_check()

    assert len(started) == 1


# ── The update bar's remedy differs by build ───────────────────────────────

def _hrefs(html: str) -> list:
    import re
    return re.findall(r'href="([^"]+)"', html)


def _update_bar_html(monkeypatch, qt_app, store_build: bool) -> str:
    from PyQt6.QtWidgets import QLabel, QWidget
    from ui.header import AppHeaderMixin

    class _HeaderStub(AppHeaderMixin):
        pass

    stub = _HeaderStub()
    stub._update_bar_lbl = QLabel()
    stub._update_bar = QWidget()
    monkeypatch.setattr("modules.utils.is_store_app", lambda: store_build)
    try:
        stub._on_update_available("9.9.9")
        return stub._update_bar_lbl.text()
    finally:
        stub._update_bar_lbl.deleteLater()
        stub._update_bar.deleteLater()
        if qt_app:
            for _ in range(3):
                qt_app.processEvents()


def test_update_bar_offers_store_deep_link_in_store_build(qt_app, monkeypatch):
    """The regression the user hit: a Store install advertising GitHub/winget."""
    pytest.importorskip("PyQt6", reason="PyQt6 not installed")
    html = _update_bar_html(monkeypatch, qt_app, store_build=True)

    links = _hrefs(html)
    assert len(links) == 1, f"expected exactly one link, got {links}"
    parsed = urlparse(links[0])
    assert parsed.scheme == "ms-windows-store"
    assert parsed.hostname == "pdp"
    assert parse_qs(parsed.query).get("productid") == ["9NZ124C7HJWS"]

    assert "winget" not in html.lower(), "Store build must never advertise winget"
    assert all(
        urlparse(u).hostname != "github.com" for u in links
    ), "Store build must never link to the GitHub download"


def test_update_bar_offers_github_and_winget_outside_store_build(qt_app, monkeypatch):
    pytest.importorskip("PyQt6", reason="PyQt6 not installed")
    html = _update_bar_html(monkeypatch, qt_app, store_build=False)

    links = _hrefs(html)
    assert len(links) == 1, f"expected exactly one link, got {links}"
    assert urlparse(links[0]).hostname == "github.com"
    assert "winget upgrade NetSentinel.NetSentinel" in html


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
