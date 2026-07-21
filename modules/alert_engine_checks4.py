"""
alert_engine_checks4.py — _AlertChecksMixin4: ARP_SPOOF / ROGUE_DHCP /
CONFIG_DRIFT rule evaluation (V6 Sprint 4 — "passive always-on guards").

New file rather than growing alert_engine_checks3.py further — keeps every
alert_engine_checks*.py file under the RULE-AH1 780-line budget (see
tests/test_module_loc.py).

Provides:
  evaluate_arp_watch_checks()   — ARP_SPOOF: one alert per SpoofEvent from
                                   modules.arp_watch.ArpWatchReport (reuses
                                   arp_monitor.py's own IP_TAKEOVER /
                                   GATEWAY_HIJACK / GRAT_FLOOD / MAC_CLONE
                                   classification — no new detection logic).
  evaluate_dhcp_watch_checks()  — ROGUE_DHCP: one alert per rogue DHCPOffer
                                   from modules.dhcp_watch.DhcpWatchReport.
  evaluate_config_drift_checks() — CONFIG_DRIFT: one alert per added/removed
                                   device or role (device_type) change found
                                   in a modules.config_baseline.SnapshotDiff
                                   between the latest scheduled-discovery
                                   snapshot and the user-blessed baseline.

None of these three fire a resolution alert — same reasoning as
NEW_OPEN_PORT/NEW_CVE/NEW_EXPOSURE in alert_engine_checks3.py: the event
itself is the notable moment, there is no persistent "still spoofing" state
to track a recovery from.
"""
from __future__ import annotations

import time
from typing import List

from modules.alert_types import AlertFired


class _AlertChecksMixin4:
    """Mixin for AlertEngine providing ARP_SPOOF/ROGUE_DHCP/CONFIG_DRIFT checks."""

    def evaluate_arp_watch_checks(self, report) -> List[AlertFired]:
        """ARP_SPOOF — a background ARP watch cycle detected spoofing."""
        fired: List[AlertFired] = []
        now = int(time.time())

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "ARP_SPOOF":
                continue
            for evt in report.events:
                if evt.event_type == "GRAT_FLOOD":
                    continue  # flood detection is noisy — takeover/hijack/clone only
                host = evt.victim_ip or evt.attacker_ip
                if rule.host and rule.host != host:
                    continue
                severity = "CRITICAL" if evt.event_type == "GATEWAY_HIJACK" else "WARNING"
                alert = self._fire_if_cooled(
                    rule, f"{host}::{evt.event_type}::{evt.attacker_mac}", now,
                    message=self._append_action(evt.verdict, "ARP_SPOOF"),
                    severity=severity,
                    value=None,
                )
                if alert:
                    alert.host = host
                    alert.cta_filter = host
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

        return fired

    def evaluate_dhcp_watch_checks(self, report) -> List[AlertFired]:
        """ROGUE_DHCP — a background DHCP watch cycle saw an offer from an
        unexpected server."""
        fired: List[AlertFired] = []
        now = int(time.time())

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "ROGUE_DHCP":
                continue
            for offer in report.rogue_offers:
                host = offer.server_ip
                if rule.host and rule.host != host:
                    continue
                alert = self._fire_if_cooled(
                    rule, f"{host}::{offer.server_mac}", now,
                    message=self._append_action(offer.verdict, "ROGUE_DHCP"),
                    severity="CRITICAL",
                    value=None,
                )
                if alert:
                    alert.host = host
                    alert.cta_filter = host
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

        return fired

    def evaluate_config_drift_checks(self, diff) -> List[AlertFired]:
        """CONFIG_DRIFT — a device was added/removed, or a device's role
        (device_type) changed, versus the user-blessed baseline snapshot."""
        fired: List[AlertFired] = []
        now = int(time.time())

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "CONFIG_DRIFT":
                continue

            for ip in diff.added_devices:
                if rule.host and rule.host != ip:
                    continue
                alert = self._fire_if_cooled(
                    rule, f"{ip}::added", now,
                    message=self._append_action(
                        f"{ip} is not in your blessed baseline — this device joined "
                        "the network since the last approved snapshot.",
                        "CONFIG_DRIFT",
                    ),
                    severity="WARNING",
                    value=None,
                )
                if alert:
                    alert.host = ip
                    alert.cta_filter = ip
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

            for ip in diff.removed_devices:
                if rule.host and rule.host != ip:
                    continue
                alert = self._fire_if_cooled(
                    rule, f"{ip}::removed", now,
                    message=self._append_action(
                        f"{ip} was in your blessed baseline but is no longer on the "
                        "network.",
                        "CONFIG_DRIFT",
                    ),
                    severity="WARNING",
                    value=None,
                )
                if alert:
                    alert.host = ip
                    alert.cta_filter = ip
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

            for ip, fields in diff.changed_fields.items():
                role_change = fields.get("device_type")
                if not role_change:
                    continue
                if rule.host and rule.host != ip:
                    continue
                alert = self._fire_if_cooled(
                    rule, f"{ip}::role", now,
                    message=self._append_action(
                        f"{ip}'s role changed from {role_change.get('old') or 'unknown'} "
                        f"to {role_change.get('new') or 'unknown'} versus your blessed "
                        "baseline.",
                        "CONFIG_DRIFT",
                    ),
                    severity="WARNING",
                    value=None,
                )
                if alert:
                    alert.host = ip
                    alert.cta_filter = ip
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

        return fired
