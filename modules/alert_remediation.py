"""
alert_remediation.py — canonical per-rule-type remediation text.

Moves ui/widgets/alert_drawer.py's _RULE_FIX table out of Qt so it is
unit-testable and reusable outside the drawer. REMEDIATION is keyed by the
25 canonical RULE_TYPES (modules.alert_types); _LEGACY_SUBSTRING_FIX
preserves the OLD substring-on-rule_name table verbatim so alert_fired rows
written before rule_type was persisted still resolve.

Design principles the text below follows (unchanged from the original
ui/widgets/alert_drawer.py table):
  1. No CLI commands
  2. Fix at the router, not the device
  3. Use app-measured data
  4. Close the loop with a rescan

Architecture rules observed: pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
"""
from __future__ import annotations

from typing import Dict

from modules.alert_types import RULE_TYPES

# ── Legacy substring-on-rule_name table ───────────────────────────────────────
# Moved verbatim from ui/widgets/alert_drawer.py::_RULE_FIX. THREAT_INTEL and
# BANDWIDTH have no RULE_TYPES counterpart — they were written by a code path
# outside AlertEngine and only ever matched by this substring lookup — so
# they stay legacy-only rather than moving into REMEDIATION.
_LEGACY_SUBSTRING_FIX: Dict[str, str] = {
    "PORT_SCAN": (
        "An unexpected port is open on this device. Open Port Scan to see the full results.\n"
        "To close it: log in to your router's admin page and disable any services you do not "
        "recognise. On the device itself, disable the service from its settings.\n"
        "After making changes, run a new Port Scan in NetSentinel to confirm the port is closed."
    ),
    "ARP": (
        "NetSentinel detected possible MAC address impersonation — a device may be "
        "intercepting traffic on your network.\n"
        "Open ARP Spoof Watch to see the full ARP table and identify the suspicious device.\n"
        "Once identified, block the unknown device from your router's client list, then "
        "click Rescan in NetSentinel to confirm the alert clears."
    ),
    "DHCP": (
        "A device is responding to DHCP requests from an IP that is not your router. "
        "This rogue DHCP server could redirect your traffic.\n"
        "Open DHCP Rogue Monitor to identify it. Then locate and disconnect the device from "
        "your network, or block it in your router's client list.\n"
        "Run a new scan in NetSentinel to confirm the rogue server is gone."
    ),
    "DEVICE": (
        "An unknown device joined your network. Open the Devices page to identify it.\n"
        "If you do not recognise it: block it in your router's wireless client list. "
        "Look for a setting called 'Block' or 'Deny' next to the device's MAC address.\n"
        "After blocking, run a new scan in NetSentinel to verify it no longer appears."
    ),
    "HOST_DOWN": (
        "NetSentinel cannot reach this device. Check the Availability page for the full "
        "outage timeline and when it went offline.\n"
        "Try restarting the device or checking its network cable. For Wi-Fi devices, "
        "check whether the device is still connected to your router's client list.\n"
        "NetSentinel will automatically detect when the device comes back online."
    ),
    "SERVICE_DOWN": (
        "A monitored service is not responding. Open Service Heartbeat to see its history.\n"
        "Restart the device or service. If the service requires a specific port, verify "
        "the port has not been blocked by your router's firewall settings.\n"
        "NetSentinel will automatically show the service as recovered when it responds."
    ),
    "RTT_THRESHOLD": (
        "NetSentinel measured high latency to this device. Open the Network Logger to see "
        "the full latency timeline and when the problem started.\n"
        "High latency for all devices usually means the router or ISP link is congested. "
        "Try changing the DNS server on your router to 1.1.1.1 to rule out DNS delays.\n"
        "After making changes, run a new DNS test in NetSentinel to confirm improvement."
    ),
    "THREAT_INTEL": (
        "This IP address has been reported for malicious activity in threat intelligence feeds.\n"
        "Open Threat Intel to see the full report and abuse score.\n"
        "Block traffic to/from this IP on your router's firewall, then run a new Threat "
        "Intel scan in NetSentinel to confirm the device is no longer contacting it."
    ),
    "CVE": (
        "A known vulnerability was found on this device. Open CVE Lookup to see full details "
        "and the CVSS severity score.\n"
        "Apply the latest firmware or software update for the affected device. Check the "
        "manufacturer's website for a security advisory.\n"
        "After updating, run a new scan in NetSentinel to verify the CVE is resolved."
    ),
    "CERT": (
        "A TLS certificate on this host is expired or about to expire. Open TLS & Exposure "
        "to see the certificate details.\n"
        "Renew the certificate through the hosting provider or certificate authority. "
        "If the service is hosted on your network, update the certificate on the server.\n"
        "After renewal, run a new TLS scan in NetSentinel to confirm the certificate is valid."
    ),
    "BANDWIDTH": (
        "Unusually high bandwidth was detected on this interface. Open Live Bandwidth to "
        "see a real-time chart of which device is consuming the most traffic.\n"
        "If a single device is using excessive bandwidth, check for software updates running "
        "in the background, video streaming, or potential malware.\n"
        "After investigating, monitor the Live Bandwidth page to confirm usage returns to normal."
    ),
}


def _legacy_fix(rule_name: str) -> str:
    rule_upper = rule_name.upper()
    for key, fix in _LEGACY_SUBSTRING_FIX.items():
        if key in rule_upper:
            return fix
    return ""


# ── Canonical rule_type table ─────────────────────────────────────────────────

REMEDIATION: Dict[str, str] = {
    # -- moved verbatim from _LEGACY_SUBSTRING_FIX --
    "RTT_THRESHOLD":  _LEGACY_SUBSTRING_FIX["RTT_THRESHOLD"],
    "HOST_DOWN":      _LEGACY_SUBSTRING_FIX["HOST_DOWN"],
    "NEW_DEVICE":     _LEGACY_SUBSTRING_FIX["DEVICE"],
    "CERT_EXPIRY":    _LEGACY_SUBSTRING_FIX["CERT"],
    "CERT_EXPIRED":   _LEGACY_SUBSTRING_FIX["CERT"],
    "SERVICE_DOWN":   _LEGACY_SUBSTRING_FIX["SERVICE_DOWN"],
    "NEW_OPEN_PORT":  _LEGACY_SUBSTRING_FIX["PORT_SCAN"],
    "NEW_CVE":        _LEGACY_SUBSTRING_FIX["CVE"],
    "ARP_SPOOF":      _LEGACY_SUBSTRING_FIX["ARP"],
    "ROGUE_DHCP":     _LEGACY_SUBSTRING_FIX["DHCP"],
    # -- freshly authored, no legacy counterpart --
    "LOSS_THRESHOLD": (
        "NetSentinel is seeing packet loss to this device. Open the Network Logger to see "
        "the full loss history and when it started.\n"
        "Packet loss usually means a weak Wi-Fi signal or a failing cable — try moving the "
        "device closer to the router or swapping the cable.\n"
        "After making changes, watch the Network Logger to confirm loss drops back to zero."
    ),
    "HOST_DEGRADED": (
        "This device is responding, but more slowly or inconsistently than usual. Open the "
        "Network Logger to see its recent response-time pattern.\n"
        "Degraded performance is often caused by Wi-Fi interference or too many devices "
        "competing for bandwidth — try moving the device closer to the router.\n"
        "After making changes, run a new scan in NetSentinel to confirm the device is "
        "responding normally again."
    ),
    "DEVICE_GONE": (
        "A previously known device has not been seen on your network recently. Open Devices "
        "to see when it was last active.\n"
        "If you expected this device to still be connected, check that it is powered on and "
        "within Wi-Fi range, or that its cable is still plugged in.\n"
        "NetSentinel will automatically clear this alert once the device is seen again."
    ),
    "FLAP": (
        "This device keeps going online and offline repeatedly. Open the Network Logger to "
        "see the pattern of drops.\n"
        "Flapping usually points to a loose cable, a failing Wi-Fi adapter, or a power-saving "
        "setting on the device — check the physical connection first.\n"
        "After making changes, watch the Network Logger to confirm the device stays connected."
    ),
    "BASELINE_DROP": (
        "Your measured internet speed has dropped well below your recent typical speed. Open "
        "Speed Test to see the full history and compare against your baseline.\n"
        "Restart your modem and router, and check whether other devices on the network are "
        "using heavy bandwidth at the same time.\n"
        "After restarting, run a new speed test in NetSentinel to confirm your speed has recovered."
    ),
    "JITTER_HIGH": (
        "This device's connection has become unstable — packets are arriving at uneven "
        "intervals, which can cause choppy calls or stuttering video. Open the Network Logger "
        "to see the jitter trend.\n"
        "Move the device closer to the router or connect it with a cable, and check whether "
        "another device on the network is saturating the link.\n"
        "After making changes, watch the Network Logger to confirm jitter returns to normal."
    ),
    "DNS_LATENCY": (
        "DNS is the phone book of the internet — every website you open needs a lookup "
        "first. Yours is answering much slower than it normally does, which makes pages "
        "feel sluggish to start even when your connection speed is perfectly fine.\n"
        "Open DNS & Stability and run a DNS speed test to see how your current resolver "
        "compares to the public ones.\n"
        "If your router is the resolver, reboot it first — a router that has been up for "
        "months is the usual cause. If it stays slow, set your router or PC to use a "
        "public resolver such as 1.1.1.1 or 8.8.8.8 and re-test."
    ),
    "INFRA_UNREACHABLE": (
        "A piece of your network hardware — a modem, router, access point or switch — has "
        "stopped answering NetSentinel. Anything connected through it is offline too, so fix "
        "this before chasing individual devices. Open Hardware to see which one it is.\n"
        "Check it has power and that its cables are seated at both ends, then power-cycle it "
        "and wait a full minute for it to come back.\n"
        "If it stays unreachable, check whether it moved to a different IP address — a device "
        "that took a new DHCP lease looks identical to one that died."
    ),
    "MESH_DEGRADED": (
        "One or more nodes in your mesh network are offline or have a weak signal. Open "
        "Hardware to see the status of each node.\n"
        "Check that the affected node is powered on, then try moving it closer to the main "
        "router or to a location with fewer walls in between.\n"
        "After repositioning, re-run a scan in NetSentinel to confirm the mesh network is "
        "back to full health."
    ),
    "MODEM_SIGNAL_DROP": (
        "Your modem's signal quality has dropped, or it downgraded from 5G to a slower "
        "network type. Open Hardware to see the current signal details.\n"
        "Reposition the modem near a window or a higher shelf, and check that the antennas "
        "are firmly connected.\n"
        "After repositioning, run a new speed test in NetSentinel to confirm the signal and "
        "speed have recovered."
    ),
    "GRADE_REGRESSION": (
        "Your overall network health grade has dropped compared to the previous run. Open "
        "Network Grade to see exactly which check declined.\n"
        "Address the specific check that dropped — the Network Grade page links each factor "
        "to the page that can fix it.\n"
        "After making changes, re-run the scan in NetSentinel to confirm your grade has improved."
    ),
    "IP_CHURN": (
        "This device has used several different IP addresses in a short time, which usually "
        "means it has no fixed DHCP reservation. Open Devices to see its IP history.\n"
        "Log in to your router's admin page and add a DHCP reservation (a fixed IP) for this "
        "device's MAC address.\n"
        "After making the change, run a new scan in NetSentinel to confirm the device keeps "
        "the same IP."
    ),
    "RTT_ANOMALY": (
        "This device is responding slower than its own usual pattern, even though it may "
        "still be under your general RTT threshold. Open DNS & Stability to compare against "
        "its learned baseline.\n"
        "Check for new background traffic on the link, or Wi-Fi interference specific to this "
        "device's location.\n"
        "After investigating, NetSentinel will automatically clear this alert once the "
        "device's response time returns to its normal pattern."
    ),
    "IOT_BEHAVIOR": (
        "A device's network behaviour has deviated from what it normally does — a new "
        "destination, a new port, or an unusual traffic spike. Open IoT Behaviour to see "
        "exactly what changed.\n"
        "If you do not recognise the destination or activity, block the device in your "
        "router's client list until you can confirm it's safe.\n"
        "After investigating, keep an eye on IoT Behaviour to confirm the device's traffic "
        "returns to its normal pattern."
    ),
    "TREND_FORECAST": (
        "NetSentinel has projected that a metric is on track to cross its alert threshold "
        "soon, based on its recent trend. Open Trend Forecasts to see the projection and "
        "estimated time.\n"
        "Address the underlying cause now, before the threshold is actually crossed — the "
        "Trend Forecasts page links to the page that measures the metric.\n"
        "After making changes, check Trend Forecasts again to confirm the trend has "
        "flattened or reversed."
    ),
    "NEW_EXPOSURE": (
        "A port on your network has become newly reachable from the internet. Open Exposed "
        "to Internet to see which port and device.\n"
        "Log in to your router's admin page and remove the port-forwarding rule if you did "
        "not intend to expose it.\n"
        "After removing the forward, run a new scan in NetSentinel to confirm the port is "
        "no longer exposed."
    ),
    "CONFIG_DRIFT": (
        "A device was added, removed, or changed role compared to your blessed baseline "
        "snapshot. Open Config Snapshots to review exactly what changed.\n"
        "If the change was expected, re-bless the current snapshot as the new baseline. If "
        "not, investigate the device that changed.\n"
        "After reviewing, NetSentinel will compare future scans against the updated baseline."
    ),
}

assert RULE_TYPES <= set(REMEDIATION), (
    "REMEDIATION must cover every canonical rule type"
)


def remediation_for(rule_type: str, rule_name: str = "") -> str:
    """Prefers the canonical rule_type. Falls back to a legacy substring match on
    rule_name so alert_fired rows written before rule_type was persisted still
    resolve. Returns "" when nothing matches."""
    fix = REMEDIATION.get(rule_type, "")
    if fix:
        return fix
    if rule_name:
        return _legacy_fix(rule_name)
    return ""
