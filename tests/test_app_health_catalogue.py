"""The fixed text of every app-health condition, in one reviewable place (S3.3).

Producers span three layers — ``app.py`` wiring, ``workers/rest_api_worker.py`` and
``modules/notification_router.py`` — so the text cannot live next to any one of them.
Keeping it here is what lets these tests check every button a condition will ever
offer *before* S4 draws one: a CTA naming a label that routes nowhere is a button that
silently does nothing (RULE-NAV3), and nothing at runtime would say so.
"""
from __future__ import annotations

import dataclasses

import pytest


def _all_specs():
    from modules import app_health_catalogue as cat

    return list(cat.ALL_STATIC) + [cat.notification_channel("EMAIL", "Ops mail")]


def test_the_six_background_monitors_are_covered():
    """The same six ``_wire_monitor_error_surface`` has carried since G6."""
    from modules.app_health_catalogue import MONITORS

    assert set(MONITORS) == {
        "Availability", "Certificate", "Service", "Health", "Passive Observer", "Trend Forecast",
    }


def test_keys_are_unique():
    keys = [s.key for s in _all_specs()]
    assert len(keys) == len(set(keys)), keys


def test_every_cta_routes_to_a_real_page():
    from ui.nav.labels import KNOWN_LABELS

    dead = [(s.key, s.cta_label) for s in _all_specs() if s.cta_label and s.cta_label not in KNOWN_LABELS]
    assert not dead, f"CTA labels that route nowhere (RULE-NAV3): {dead}"


def test_every_condition_says_what_why_and_next():
    """RULE-A2's three questions, answered in the catalogue rather than at the call site."""
    for spec in _all_specs():
        for field in ("source", "what", "why", "next_step"):
            assert getattr(spec, field).strip(), f"{spec.key}: empty {field}"


def test_a_notification_channel_condition_names_the_channel_and_is_high():
    """Alerting that silently stopped is the failure most worth hearing about."""
    from modules.app_health_catalogue import notification_channel

    spec = notification_channel("EMAIL", "Ops mail")

    assert spec.key == "notify:Ops mail"
    assert spec.severity == "High"
    assert "Email" in spec.what
    assert "Ops mail" in spec.why
    assert spec.cta_label == "Notifications"


def test_listeners_nobody_asked_for_are_info_not_warning():
    """Syslog (UDP 514) and SNMP traps (UDP 162) bind at every launch, enabled or not.

    A user who never sends either should not be warned that a port they have never
    heard of is taken.
    """
    from modules.app_health_catalogue import SNMP_TRAP_RECEIVER, SYSLOG_RECEIVER

    assert SYSLOG_RECEIVER.severity == SNMP_TRAP_RECEIVER.severity == "Info"


def test_specs_are_immutable():
    from modules.app_health_catalogue import REST_API

    with pytest.raises(dataclasses.FrozenInstanceError):
        REST_API.why = "changed"  # type: ignore[misc]


def test_a_syslog_receiver_on_a_random_port_is_an_info_condition():
    """S4.4e — port 0 always binds, so a taken 514 and 5140 is not a failure but a
    listener no device is configured to reach. Info: most users never send syslog."""
    from modules import app_health_catalogue as cat

    spec = cat.SYSLOG_RANDOM_PORT
    assert spec in cat.ALL_STATIC
    assert spec.severity == "Info"
    assert spec.key == "listener:syslog_port"
    assert spec.cta_label == "Syslog Viewer"
