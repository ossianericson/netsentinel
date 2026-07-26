"""
Phase 3.2 -- delete the orphan Settings -> Active Integrations notification
rows (user decision 2).

_NotifTestWorker read notifications/* QSettings keys and notifications/*
keyring names that nothing else in the app ever wrote (defect 5) -- its
"Send test" buttons could never succeed. The three rows (Email/Webhook/
Pushover) duplicated NotificationsPage's real, working channel config.
Replaced with a single link row pointing at the Notifications page.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QLabel, QPushButton  # noqa: E402

from ui.pages.settings_page import SettingsPage  # noqa: E402


def _find_row_button(card, label_text):
    body = card.layout().itemAt(1).widget()
    bl = body.layout()
    for i in range(bl.count()):
        item = bl.itemAt(i)
        lay = item.layout()
        if lay is None:
            continue
        lbl_item = lay.itemAt(0)
        if lbl_item and isinstance(lbl_item.widget(), QLabel) and lbl_item.widget().text() == label_text:
            btn_item = lay.itemAt(lay.count() - 1)
            return btn_item.widget()
    return None


def test_notif_test_worker_class_removed():
    import ui.pages.settings_cards as sc
    assert not hasattr(sc, "_NotifTestWorker")


def test_settings_page_has_no_notif_test_workers_list():
    page = SettingsPage()
    assert not hasattr(page, "_notif_test_workers")


def test_integrations_card_has_no_per_channel_send_test_buttons():
    page = SettingsPage()
    card = page._build_integrations_card()
    labels = [w.text() for w in card.findChildren(QLabel)]
    assert "Email notifications" not in labels
    assert "Webhook" not in labels
    assert "Pushover" not in labels
    buttons = [w.text() for w in card.findChildren(QPushButton)]
    assert "Send test" not in buttons


def test_integrations_card_has_one_notification_channels_link_row():
    page = SettingsPage()
    card = page._build_integrations_card()
    labels = [w.text() for w in card.findChildren(QLabel)]
    assert "Notification channels" in labels

    btn = _find_row_button(card, "Notification channels")
    assert isinstance(btn, QPushButton)
    assert btn.text() == "Configure →"

    seen = []
    page.navigate_to.connect(seen.append)
    btn.click()
    assert seen == ["Notifications"]
