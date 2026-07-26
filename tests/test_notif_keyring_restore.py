"""
Phase 5 -- keychain secrets reaching the live router after a restart.

_kr_restore_field() deliberately leaves the QLineEdit EMPTY and shows only a
masked placeholder for a secret already stored in the OS keychain, so
field.text() is "" on every restart after the first save. _apply_to_router()
read .text() directly, so after every restart Pushover/Telegram silently
disabled themselves (their enabled= expression requires a truthy token) and
Email's SMTP auth failed with an empty password -- even though the real
secret was sitting right there in the keychain the whole time.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from unittest.mock import MagicMock  # noqa: E402

from PyQt6.QtCore import QSettings  # noqa: E402


_QS_KEYS = (
    "notif/pushover_enabled", "notif/telegram_enabled",
    "notif/email_enabled", "notif/email_host", "notif/email_to",
    "notif/ntfy_enabled", "notif/ntfy_url",
    "notif/telegram_chat",
)


def _clear_settings():
    qs = QSettings("NetSentinel", "NetSentinel")
    for k in _QS_KEYS:
        qs.remove(k)
    qs.sync()
    return qs


def _make_page_with_secrets(monkeypatch, **settings):
    """Construct a NotificationsPage where every keychain-backed field
    restores to 'SECRET' (simulating a real post-restart keychain hit), and
    the given QSettings values are pre-set before construction."""
    qs = _clear_settings()
    for key, value in settings.items():
        qs.setValue(key, value)
    monkeypatch.setattr(
        "ui.pages.notif_channel_panels._load_secret", lambda kr_key: "SECRET"
    )
    from ui.pages.notifications_page import NotificationsPage
    return NotificationsPage()


class TestPushoverKeyringRestore:
    def test_pushover_channel_enabled_and_carries_secret_after_restart(self, monkeypatch):
        try:
            page = _make_page_with_secrets(monkeypatch, **{"notif/pushover_enabled": True})
            router = MagicMock()
            page.set_router(router)

            from modules.notification_router import PushoverChannel
            channels = router.set_channels.call_args[0][0]
            po = next(c for c in channels if isinstance(c, PushoverChannel))
            assert po.enabled is True
            assert po.api_token == "SECRET"
            assert po.user_key == "SECRET"
        finally:
            _clear_settings()


class TestTelegramKeyringRestore:
    def test_telegram_channel_enabled_and_carries_secret_after_restart(self, monkeypatch):
        try:
            page = _make_page_with_secrets(
                monkeypatch,
                **{"notif/telegram_enabled": True, "notif/telegram_chat": "-100123"},
            )
            router = MagicMock()
            page.set_router(router)

            from modules.notification_router import TelegramChannel
            channels = router.set_channels.call_args[0][0]
            tg = next(c for c in channels if isinstance(c, TelegramChannel))
            assert tg.enabled is True
            assert tg.bot_token == "SECRET"
        finally:
            _clear_settings()


class TestEmailKeyringRestore:
    def test_email_password_carries_through_after_restart(self, monkeypatch):
        try:
            page = _make_page_with_secrets(
                monkeypatch,
                **{
                    "notif/email_enabled": True,
                    "notif/email_host": "smtp.example.com",
                    "notif/email_to": "a@b.com",
                },
            )
            router = MagicMock()
            page.set_router(router)

            from modules.notification_router import EmailChannel
            channels = router.set_channels.call_args[0][0]
            em = next(c for c in channels if isinstance(c, EmailChannel))
            assert em.enabled is True
            assert em.password == "SECRET"
        finally:
            _clear_settings()


class TestNtfyKeyringRestore:
    def test_ntfy_access_token_carries_through_after_restart(self, monkeypatch):
        try:
            page = _make_page_with_secrets(
                monkeypatch,
                **{"notif/ntfy_enabled": True, "notif/ntfy_url": "https://ntfy.sh/x"},
            )
            router = MagicMock()
            page.set_router(router)

            from modules.notification_router import NtfyChannel
            channels = router.set_channels.call_args[0][0]
            nt = next(c for c in channels if isinstance(c, NtfyChannel))
            assert nt.enabled is True
            assert nt.access_token == "SECRET"
        finally:
            _clear_settings()


class TestTypedValueTakesPrecedence:
    def test_freshly_typed_secret_is_used_over_the_keychain_placeholder(self, monkeypatch):
        """A user typing a NEW token must not be shadowed by the old keychain
        value until _save() actually persists it."""
        try:
            page = _make_page_with_secrets(monkeypatch, **{"notif/pushover_enabled": True})
            page._pushover_token.setText("freshly-typed")
            router = MagicMock()
            page.set_router(router)

            from modules.notification_router import PushoverChannel
            channels = router.set_channels.call_args[0][0]
            po = next(c for c in channels if isinstance(c, PushoverChannel))
            assert po.api_token == "freshly-typed"
        finally:
            _clear_settings()


class TestNoSecretMeansDisabled:
    def test_pushover_stays_disabled_with_no_keychain_secret(self, monkeypatch):
        qs = _clear_settings()
        try:
            qs.setValue("notif/pushover_enabled", True)
            monkeypatch.setattr(
                "ui.pages.notif_channel_panels._load_secret", lambda kr_key: ""
            )
            from ui.pages.notifications_page import NotificationsPage
            page = NotificationsPage()
            router = MagicMock()
            page.set_router(router)

            from modules.notification_router import PushoverChannel
            channels = router.set_channels.call_args[0][0]
            po = next(c for c in channels if isinstance(c, PushoverChannel))
            assert po.enabled is False
        finally:
            _clear_settings()
