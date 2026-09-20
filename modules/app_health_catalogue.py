"""The fixed text of every app-health condition (S3.3, D1).

One place for what each "NetSentinel can't see X" condition says, because its producers
span three layers — ``app.py`` wiring, ``workers/rest_api_worker.py`` and
``modules/notification_router.py`` — and none of them can import the others. Keeping the
text together is also what lets ``tests/test_app_health_catalogue.py`` check every CTA a
condition will ever offer against the real nav labels before any surface draws a button.

What goes here is only what is true of the condition in general. The raw error text is
passed separately as ``detail`` (a tooltip or diagnostic report, never the message —
RULE-A2), and a producer that still holds the exception may swap in a sharper ``why`` /
``next_step`` from ``modules.error_text`` with ``dataclasses.replace``.

Severity follows who asked for the feature. A monitor the app runs for everyone is
``Warning``; a listener that binds at every launch whether or not anyone sends to it
(syslog on UDP 514, SNMP traps on UDP 162) is ``Info``, because warning a user about a
port they have never heard of is noise; alert delivery that silently stopped is
``High``, because it is the one failure that hides every other failure.
"""
from __future__ import annotations

from typing import Dict

from modules.app_health import ConditionSpec

__all__ = [
    "MONITORS",
    "SCHEDULED_SPEED_TEST",
    "REST_API",
    "SYSLOG_RECEIVER",
    "SYSLOG_RANDOM_PORT",
    "SNMP_TRAP_RECEIVER",
    "REPORT_SCHEDULER",
    "MQTT_PASSWORD",
    "ALL_STATIC",
    "CHANNEL_TYPES",
    "notification_channel",
]

_RETRIES = "It retries automatically on its next interval."

#: Keyed by the display names ``app.py::_wire_monitor_error_surface`` already uses.
MONITORS: Dict[str, ConditionSpec] = {
    "Availability": ConditionSpec(
        key="monitor:availability",
        source="Availability monitor",
        severity="Warning",
        what="Availability monitoring is failing",
        why="Its last check failed, so device up/down history is not being updated.",
        next_step=f"{_RETRIES} If this stays, open Availability History and check the monitored devices.",
        cta_label="Availability History",
    ),
    "Certificate": ConditionSpec(
        key="monitor:certificate",
        source="Certificate monitor",
        severity="Warning",
        what="Certificate monitoring is failing",
        why="Its last check failed, so an expiring certificate may go unnoticed.",
        next_step=f"{_RETRIES} If this stays, open TLS & Exposure and check the monitored hosts.",
        cta_label="TLS & Exposure",
    ),
    "Service": ConditionSpec(
        key="monitor:service",
        source="Service monitor",
        severity="Warning",
        what="Service monitoring is failing",
        why="Its last check failed, so a service going down may go unnoticed.",
        next_step=f"{_RETRIES} If this stays, open Service Heartbeat and check the monitored services.",
        cta_label="Service Heartbeat",
    ),
    "Health": ConditionSpec(
        key="monitor:health",
        source="Network health monitor",
        severity="Warning",
        what="Network health checks are failing",
        why="Its last check failed, so the health summary on Home is not being refreshed.",
        next_step=f"{_RETRIES} If this stays, save a diagnostic report and include it when reporting the problem.",
    ),
    "Passive Observer": ConditionSpec(
        key="monitor:passive_observer",
        source="Passive observer",
        severity="Info",
        what="Passive device discovery is not running",
        why="Listening for mDNS and SSDP announcements failed, so device type hints from them are unavailable.",
        next_step="Device scans still work. Restart NetSentinel to try again.",
        cta_label="Devices",
    ),
    "Trend Forecast": ConditionSpec(
        key="monitor:trend_forecast",
        source="Trend forecaster",
        severity="Info",
        what="Trend forecasting is failing",
        why="Its last hourly analysis failed, so forecasts may be out of date.",
        next_step=_RETRIES,
        cta_label="Trend Forecasts",
    ),
}

SCHEDULED_SPEED_TEST = ConditionSpec(
    key="speedtest:scheduled",
    source="Scheduled speed test",
    severity="Warning",
    what="Scheduled speed tests are failing",
    why="The last scheduled test could not complete, so speed history has a gap.",
    next_step="Run a speed test manually to see what is going wrong.",
    cta_label="Speed Test",
)

#: The schedule advances to its next window whether or not the scan started — otherwise a
#: scan that always fails would be retried on every timer tick. That makes this condition
#: the only trace a missed run leaves (S8 B14).
SCHEDULED_SCAN = ConditionSpec(
    key="scan:scheduled",
    source="Scheduled scan",
    severity="Warning",
    what="Scheduled scans are not running",
    why="The last scheduled scan could not be started, so your device list has not been refreshed.",
    next_step="Run a scan manually to see what is going wrong.",
    cta_label="Devices",
)

#: ``why`` / ``next_step`` here are the fallback for a failure with no classifiable
#: cause; ``RestApiWorker`` swaps in the ``modules.error_text`` explanation when it has one.
REST_API = ConditionSpec(
    key="rest_api:serve",
    source="REST API",
    severity="Warning",
    what="The REST API could not start",
    why="The server stopped immediately after starting. Another program may be using its port.",
    next_step="Choose a different port on the REST API page, then start it again.",
    cta_label="REST API",
)

#: Worded for a socket that failed, not a port that was taken: SyslogReceiver.open() falls
#: back 514 → FALLBACK_PORT → port 0, and port 0 always binds, so a taken 514 never
#: reaches this condition (it is a degraded listener — see the plan's §3, found in S3).
SYSLOG_RECEIVER = ConditionSpec(
    key="listener:syslog",
    source="Syslog receiver",
    severity="Info",
    what="The syslog receiver stopped",
    why="Its UDP socket failed, so syslog messages from devices are not being received.",
    next_step="Only matters if devices send syslog to this computer. If they do, restart NetSentinel.",
    cta_label="Syslog Viewer",
)

#: S4.4e — the degraded case SYSLOG_RECEIVER cannot see. When 514 and FALLBACK_PORT (5140)
#: are both taken, open() binds port 0: it "works", on a random port no device is set up to
#: send to. 5140 alone is not raised — it is the designed fallback, and the normal one
#: without root on Linux/macOS, so a condition for it would fire on every such launch.
SYSLOG_RANDOM_PORT = ConditionSpec(
    key="listener:syslog_port",
    source="Syslog receiver",
    severity="Info",
    what="The syslog receiver is on a temporary port",
    why="UDP ports 514 and 5140 were both in use, so it is listening on a random port "
        "that no device is set up to send to.",
    next_step="Only matters if devices send syslog to this computer. If they do, close the "
              "program using UDP 514, then restart NetSentinel.",
    cta_label="Syslog Viewer",
)

#: SnmpTrapReceiver.open() tries 162 then FALLBACK_PORT and raises if both are taken.
SNMP_TRAP_RECEIVER = ConditionSpec(
    key="listener:snmp_trap",
    source="SNMP trap receiver",
    severity="Info",
    what="The SNMP trap receiver is not listening",
    why="It could not open UDP port 162 or its fallback port, or its socket failed. "
        "Another SNMP manager may be using them.",
    next_step="Only matters if devices send SNMP traps to this computer. If they do, stop the "
              "other SNMP manager and restart NetSentinel.",
    cta_label="SNMP Trap Receiver",
)

REPORT_SCHEDULER = ConditionSpec(
    key="scheduler:reports",
    source="Report scheduler",
    severity="Warning",
    what="Scheduled reports are failing",
    why="The last scheduled report could not be generated or saved.",
    next_step="Check the report schedule and the output folder.",
    cta_label="Network Health Report",
)

MQTT_PASSWORD = ConditionSpec(
    key="keyring:mqtt",
    source="Credential store",
    severity="Warning",
    what="The MQTT password could not be saved",
    why="The secure credential store refused to save it.",
    next_step="MQTT works for this session, but you will be asked for the password again next launch. "
              "Check that Windows Credential Manager is working, then save again.",
    cta_label="MQTT / Home Assistant",
)

ALL_STATIC = (
    *MONITORS.values(),
    SCHEDULED_SPEED_TEST,
    SCHEDULED_SCAN,
    REST_API,
    SYSLOG_RECEIVER,
    SYSLOG_RANDOM_PORT,
    SNMP_TRAP_RECEIVER,
    REPORT_SCHEDULER,
    MQTT_PASSWORD,
)

#: ``NotificationRouter`` channel types → the word a user knows.
_CHANNEL_NAMES = {
    "TOAST": "Desktop",
    "WEBHOOK": "Webhook",
    "EMAIL": "Email",
    "PUSHOVER": "Pushover",
    "NTFY": "ntfy",
    "TELEGRAM": "Telegram",
}

#: Every channel type a ``notify:`` condition can be built for — lets ``--audit`` check
#: each one's CTA without a configured channel of that type.
CHANNEL_TYPES = tuple(_CHANNEL_NAMES)


def notification_channel(channel_type: str, channel_name: str) -> ConditionSpec:
    """The condition for one delivery channel that keeps failing. Keyed per channel."""
    kind = _CHANNEL_NAMES.get(channel_type, channel_type.title())
    return ConditionSpec(
        key=f"notify:{channel_name}",
        source=f"{kind} notifications",
        severity="High",
        what=f"{kind} alerts are not being delivered",
        why=f"Several deliveries in a row through “{channel_name}” have failed.",
        next_step="Open Notifications, check the channel settings, and send a test.",
        cta_label="Notifications",
    )
