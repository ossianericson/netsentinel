"""
modules/root_cause_correlator_alerts.py — recent-alerts correlation pass for
root_cause_correlator.py (RULE-AH1: 780-line budget split).

V6 Sprint 5.1 — folds already-fired MESH_DEGRADED / MODEM_SIGNAL_DROP /
IOT_BEHAVIOR / BASELINE_DROP alerts (as recorded by AlertEngine via
store.get_recent_alerts()) into root-cause findings, so "What's Wrong?"
surfaces things the always-on background detectors already know even when
the live diagnostic pass doesn't re-detect them itself (e.g. a modem blip
that has since recovered).
"""
from __future__ import annotations

import time
from typing import List

from modules.root_cause_types import CorrelatedFinding, HIGH, MEDIUM


def correlate_recent_alerts(
    recent_alerts: List[dict],
    findings: List[CorrelatedFinding],
) -> None:
    """
    One finding per rule — newest alert wins — to avoid duplicate noise when
    a rule fired repeatedly.
    """
    if not recent_alerts:
        return

    latest_by_rule: dict = {}
    for a in recent_alerts:
        rule = a.get("rule_name", "")
        if rule not in latest_by_rule or a.get("ts", 0) > latest_by_rule[rule].get("ts", 0):
            latest_by_rule[rule] = a

    modem_alert = latest_by_rule.get("Modem Signal Drop")
    if modem_alert:
        findings.append(CorrelatedFinding(
            source="Modem Signal Monitor",
            category="Degraded Cellular/5G Modem Signal",
            severity=HIGH,
            headline=f"Radio signal issue: {modem_alert.get('message', 'your modem signal recently degraded')}",
            detail=(
                f"At {_fmt_ts(modem_alert.get('ts'))}, NetSentinel's background modem "
                "monitor detected your cellular signal drop well below its normal level "
                "(or a downgrade from 5G to LTE). Weak radio signal directly causes "
                "slower speeds and higher latency, independent of your ISP's network."
            ),
            remediation=(
                "Reposition the modem/antenna closer to a window and away from metal "
                "objects, thick walls, and other electronics. Check the manufacturer's "
                "site for a firmware update."
            ),
            verify_step=(
                "Go to Modem Signal Monitor in NetSentinel to confirm SINR/RSRP has "
                "returned to its normal range."
            ),
        ))

    mesh_alert = latest_by_rule.get("Mesh Degraded")
    if mesh_alert:
        findings.append(CorrelatedFinding(
            source="Mesh Router Monitor",
            category="Degraded Mesh Wi-Fi Node",
            severity=MEDIUM,
            headline=f"Mesh Wi-Fi issue: {mesh_alert.get('message', 'a mesh node recently degraded')}",
            detail=(
                f"At {_fmt_ts(mesh_alert.get('ts'))}, a mesh Wi-Fi node "
                f"({mesh_alert.get('host', 'unknown node')}) went offline or reported a "
                "weak backhaul signal. Devices connected to a degraded node see slower "
                "speeds even though the rest of your network is healthy."
            ),
            remediation=(
                "Check the affected mesh node is powered on and within range of its "
                "neighbouring node. Try relocating it closer to the main router."
            ),
            verify_step=(
                "Go to Mesh Router Monitor in NetSentinel to confirm the node shows "
                "a strong backhaul signal again."
            ),
        ))

    iot_alert = latest_by_rule.get("IoT Behavior Anomaly")
    if iot_alert:
        findings.append(CorrelatedFinding(
            source="IoT Behaviour Monitor",
            category="Unusual IoT Device Behavior",
            severity=MEDIUM,
            headline=f"IoT anomaly: {iot_alert.get('message', 'a device deviated from its learned baseline')}",
            detail=(
                f"At {_fmt_ts(iot_alert.get('ts'))}, "
                f"{iot_alert.get('host', 'a monitored device')} deviated from its "
                "learned traffic baseline (new destination, new port, or a rate spike). "
                "This can indicate a misbehaving device, a software update, or "
                "compromised firmware."
            ),
            remediation=(
                "Check IoT Behaviour in NetSentinel for the specific deviation. If it "
                "does not match a known update or new feature, isolate the device on a "
                "guest network and check the manufacturer's site for advisories."
            ),
            verify_step=(
                "Go to IoT Behaviour in NetSentinel — the device should return to its "
                "learned baseline pattern once the cause is addressed."
            ),
        ))

    speed_alert = latest_by_rule.get("Baseline Speed Drop")
    if speed_alert:
        message = speed_alert.get("message", "")
        is_radio = "radio" in message.lower()
        findings.append(CorrelatedFinding(
            source="Speed Test",
            category="Speed Drop — Radio Link" if is_radio else "Speed Drop — Possible ISP Issue",
            severity=HIGH,
            headline=(
                f"Radio signal issue: {message}" if is_radio
                else f"Speed drop: {message}"
            ),
            detail=(
                f"At {_fmt_ts(speed_alert.get('ts'))}, a scheduled speed test recorded a "
                "severe drop versus your recent typical speed."
                + (" Your modem's signal quality had also dropped at the same time, "
                   "pointing at the radio link rather than your ISP." if is_radio else "")
            ),
            remediation=(
                "Reposition the modem/antenna and check for physical obstructions; "
                "restart the modem if signal doesn't improve." if is_radio else
                "Restart your router and modem, re-run the speed test, and contact "
                "your ISP if the drop persists."
            ),
            verify_step=(
                "Go to Speed Test in NetSentinel and run a fresh test to confirm "
                "speeds have recovered."
            ),
        ))


def _fmt_ts(ts) -> str:
    try:
        return time.strftime("%H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError, OSError):
        return "the recorded time"
