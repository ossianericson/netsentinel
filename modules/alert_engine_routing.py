"""
alert_engine_routing.py — CTA page routing + action-step text for AlertEngine.

Extracted from alert_engine.py (RULE-AH1: 780-line budget) — this is a
self-contained lookup-table module with no evaluate_* logic, so it splits
cleanly away from the rule-evaluation mixins in alert_engine_checks*.py.
"""
from __future__ import annotations

from typing import Dict, Optional

from modules.speed_drop_detector import RESTART_CHECKLIST
from ui.nav.labels import NavLabel

# ── CTA routing — maps rule_type → nav_label ──────────────────────────────────
#
# Values are NavLabel members, not bare strings (S3 fix): a typo'd or renamed
# label used to silently no-op the "Fix this" button with no error (RULE-NAV3)
# -- HOST_DOWN/HOST_DEGRADED/DEVICE_GONE pointed at the dead label "Inventory"
# (real: "Inventory Changes"), CERT_EXPIRY/CERT_EXPIRED at "TLS & Cert Monitor"
# (real: "TLS & Exposure"), and NEW_CVE at "CVE Lookup" -- but NEW_CVE fires
# from evaluate_cve_recheck_checks() for a CVE gained by an already-*tracked*
# (host, service) pair, so "CVE Tracker" (the lifecycle page) is where that
# finding actually lives, not the on-demand Lookup scan. NavLabel members ARE
# str instances, so every existing str-typed consumer keeps working unchanged.

RULE_CTA: Dict[str, str] = {
    "RTT_THRESHOLD":  NavLabel.DNS_STABILITY,
    "LOSS_THRESHOLD": NavLabel.DNS_STABILITY,
    "HOST_DOWN":      NavLabel.INVENTORY_CHANGES,
    "HOST_DEGRADED":  NavLabel.INVENTORY_CHANGES,
    "NEW_DEVICE":     NavLabel.DEVICES,
    "DEVICE_GONE":    NavLabel.INVENTORY_CHANGES,
    "CERT_EXPIRY":    NavLabel.TLS_EXPOSURE,
    "CERT_EXPIRED":   NavLabel.TLS_EXPOSURE,
    "FLAP":           NavLabel.TREND_FORECASTS,
    "SERVICE_DOWN":   NavLabel.SERVICE_HEARTBEAT,
    "BASELINE_DROP":  NavLabel.SPEED_TEST,
    "JITTER_HIGH":        NavLabel.NETWORK_LOGGER,
    "MESH_DEGRADED":      NavLabel.HARDWARE,
    "MODEM_SIGNAL_DROP":  NavLabel.HARDWARE,
    "GRADE_REGRESSION":   NavLabel.NETWORK_GRADE,
    "IP_CHURN":           NavLabel.DEVICES,
    "RTT_ANOMALY":        NavLabel.DNS_STABILITY,
    "IOT_BEHAVIOR":       NavLabel.IOT_BEHAVIOUR,
    "TREND_FORECAST":     NavLabel.TREND_FORECASTS,
    "NEW_OPEN_PORT":      NavLabel.DEVICES,
    "NEW_CVE":            NavLabel.CVE_TRACKER,
    "NEW_EXPOSURE":       NavLabel.EXPOSED_TO_INTERNET,
    "ARP_SPOOF":          NavLabel.ARP_SPOOF_WATCH,
    "ROGUE_DHCP":         NavLabel.DHCP_ROGUE_MONITOR,
    "CONFIG_DRIFT":       NavLabel.CONFIG_SNAPSHOTS,
    "INFRA_UNREACHABLE":  NavLabel.HARDWARE,
    "DNS_LATENCY":        NavLabel.DNS_STABILITY,
}


def cta_for_rule(rule_type: str, host: str) -> tuple[Optional[str], Optional[str]]:
    """Return (cta_page, cta_filter) for an alert so the UI can deep-link to the right page."""
    page = RULE_CTA.get(rule_type)
    if not page:
        return None, None
    return page, host


# ── S4-4: action steps appended to every alert message ────────────────────────

ACTION_STEPS: Dict[str, str] = {
    "RTT_THRESHOLD":  "→ Run a speed test  → Check if other devices are also slow",
    "LOSS_THRESHOLD": "→ Restart your router  → Check all cable connections",
    "HOST_DOWN":      "→ Check the device is powered on  → Check network cable or Wi-Fi",
    "HOST_DEGRADED":  "→ Check for congestion  → Run a speed test to confirm",
    "NEW_DEVICE":     "→ Open Devices to identify it  → Block in your router if unexpected",
    "DEVICE_GONE":    "→ Check if the device was intentionally disconnected",
    "CERT_EXPIRY":    "→ Renew the certificate  → Check auto-renewal is enabled",
    "CERT_EXPIRED":   "→ Renew the certificate now  → Visitors will see security warnings",
    "FLAP":           "→ Check the cable or Wi-Fi signal  → Look for interference",
    "SERVICE_DOWN":   "→ Restart the service  → Check firewall rules for this port",
    "BASELINE_DROP":  "  ".join(f"→ {step}" for step in RESTART_CHECKLIST),
    "NEW_OPEN_PORT":  "→ Confirm this was intentional  → If not, check the device for malware or a misconfigured service",
    "NEW_CVE":        "→ Check for a firmware/software update for this service  → Restrict access if no patch exists yet",
    "NEW_EXPOSURE":   "→ Check your router's port-forwarding rules  → Remove the forward if unintentional",
    "ARP_SPOOF":      "→ Run as Administrator, check the Devices list immediately  → Isolate the attacking device from the network",
    "ROGUE_DHCP":     "→ Identify and disconnect the unauthorised DHCP server  → Check your router for a compromised second router or IoT device",
    "CONFIG_DRIFT":   "→ Open Config Snapshots to review the change  → Re-bless the baseline if the change was expected",
    "JITTER_HIGH":       "→ Move the device closer to the router or use a cable  → Check for other devices saturating the link",
    "MESH_DEGRADED":     "→ Check the offline node's power  → Move it closer to the main router and re-run the scan",
    "MODEM_SIGNAL_DROP": "→ Reposition the modem near a window  → Check the antenna connections  → Re-run a speed test to confirm",
    "GRADE_REGRESSION":  "→ Open Network Grade to see which check dropped  → Re-run the scan after fixing it",
    "IP_CHURN":          "→ Reserve a fixed DHCP lease for this device in your router  → Check its Wi-Fi signal",
    "RTT_ANOMALY":       "→ Compare against the host's own history in Network Logger  → Check for new traffic on the link",
    "IOT_BEHAVIOR":      "→ Open IoT Behaviour to see what changed  → Block the device in your router if you do not recognise the destination",
    "TREND_FORECAST":    "→ Open Trend Forecasts to see the projection  → Act before the threshold is crossed",
    "INFRA_UNREACHABLE": "→ Check the device has power and its cables are seated  → Power-cycle it and wait 60 seconds  → Open Hardware to confirm it reconnects",
    "DNS_LATENCY":       "→ Open DNS & Stability and run a DNS speed test  → Try a public resolver (1.1.1.1 or 8.8.8.8) in your router  → Reboot your router if it is acting as the resolver",
}


def append_action(message: str, rule_type: str) -> str:
    step = ACTION_STEPS.get(rule_type, "")
    if step and step not in message:
        return f"{message}  {step}"
    return message
