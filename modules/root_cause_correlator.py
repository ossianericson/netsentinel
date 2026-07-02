"""
Root Cause Correlator — links Storm Analyser, Diagnostics (MTR/trace),
STP Detector, and the Risk Scorer to produce a single prioritised list of
root causes with plain-English remediations.

Logic
─────
  ISP vs Local split
    If traceroute shows loss at hop 2+ but the first hop (gateway) is
    reachable → suppress local alerts and flag "External ISP Issue."
    If hop 1 itself fails → flag "Local Network / Router Problem."

  IoT traffic anomaly
    If a device classified as IoT in the fingerprinter appears in the
    Storm Analyser's top_sources above threshold → mark it "Degraded"
    in the risk assessment and emit a finding.

  STP rogue bridge
    Any rogue BPDU finding elevates to CRITICAL and produces a specific
    cable-disconnect remediation.

  Per-finding Plain English remediation
    Every correlated finding includes a one-sentence user-facing fix
    written for a non-technical audience.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ── Score constants (re-used from risk_scorer semantics) ─────────────────────
CRITICAL = "CRITICAL"
HIGH     = "HIGH"
MEDIUM   = "MEDIUM"
LOW      = "LOW"
INFO     = "INFO"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CorrelatedFinding:
    source: str          # e.g. "ISP Check", "Storm Analyser", "STP Detector"
    category: str        # e.g. "External ISP Issue", "Rogue IoT Broadcaster", …
    severity: str        # CRITICAL / HIGH / MEDIUM / LOW / INFO
    headline: str        # one-line plain-English summary
    detail: str          # longer explanation
    remediation: str     # plain-English fix — written for a home user
    verify_step: str = ""  # "To confirm this is fixed: [step]" — shown below remediation


@dataclass
class CorrelationResult:
    findings: List[CorrelatedFinding] = field(default_factory=list)
    global_severity: str = INFO
    plain_summary: str = ""          # 1-2 sentences for the verdict panel
    isp_issue_detected: bool = False
    local_issue_detected: bool = False
    suppress_local_alerts: bool = False  # True when ISP is clearly to blame

    @property
    def finding_count(self) -> int:
        return len(self.findings)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _severity_rank(s: str) -> int:
    return {CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, INFO: 0}.get(s, 0)


def _highest(severities: List[str]) -> str:
    if not severities:
        return INFO
    return max(severities, key=_severity_rank)


# ── ISP vs Local split ────────────────────────────────────────────────────────

def _correlate_isp(
    trace_hops: list,
    ping_results: list,
    findings: List[CorrelatedFinding],
) -> bool:
    """
    Examine traceroute hops and ping results.
    Returns True if the issue is clearly external (ISP-side).
    """
    if not trace_hops:
        return False

    # hop.rtt_ms == -1 means that hop timed out / dropped
    hop1 = trace_hops[0] if trace_hops else None
    hop1_ok = hop1 is not None and hop1.rtt_ms > 0

    # Count how many hops beyond the first have failures
    outer_failures = sum(1 for h in trace_hops[1:] if h.rtt_ms < 0)
    total_outer    = max(len(trace_hops) - 1, 1)
    outer_fail_pct = outer_failures / total_outer

    if not hop1_ok:
        findings.append(CorrelatedFinding(
            source="Path Tracer (MTR)",
            category="Local Network / Router Unreachable",
            severity=CRITICAL,
            headline="Your router is not responding",
            detail=(
                "The very first network hop (your home router / gateway) is "
                "not responding to probes. All internet traffic must pass through "
                "it, so this is the most likely cause of your connectivity problems."
            ),
            remediation=(
                "Restart your router by unplugging it for 30 seconds. "
                "If that does not help, connect directly to it with an Ethernet "
                "cable and check its admin page."
            ),
            verify_step=(
                "After restarting your router, run What's Wrong? again in "
                "NetSentinel to confirm the gateway is responding."
            ),
        ))
        return False  # local problem, do not suppress other local alerts

    if outer_fail_pct >= 0.5:
        findings.append(CorrelatedFinding(
            source="Path Tracer (MTR)",
            category="External ISP Issue",
            severity=HIGH,
            headline="Problem is outside your home — likely your ISP",
            detail=(
                f"Your router (hop 1) responded fine, but "
                f"{outer_failures}/{total_outer} of the onward hops are "
                "dropping packets. This pattern means the fault is beyond "
                "your home network, somewhere in your ISP's infrastructure."
            ),
            remediation=(
                "Contact your ISP and quote this trace result. "
                "While waiting, try restarting your modem (the box that "
                "connects to the street, not the Wi-Fi router)."
            ),
            verify_step=(
                "NetSentinel's Connection Monitor will automatically detect "
                "when the ISP issue is resolved."
            ),
        ))
        return True  # suppress unrelated local noise

    return False


# ── Storm + IoT correlation ───────────────────────────────────────────────────

def _correlate_storm(
    storm_result,
    fingerprint_devices: list,
    findings: List[CorrelatedFinding],
) -> None:
    """
    If a device typed as IoT is in the storm top_sources, emit a Degraded-IoT
    finding and suggest network isolation.
    """
    if storm_result is None:
        return

    iot_types = {
        "IoT Device", "IP Camera", "Smart Speaker", "Smart Speaker / Display",
        "Smart Display", "Smart Home Hub", "Smart TV", "Streaming Stick",
        "Video Doorbell", "Smart Thermostat",
    }

    # Build mac→device_type map from fingerprint results
    mac_to_type: dict = {}
    mac_to_label: dict = {}
    for dev in fingerprint_devices:
        mac = getattr(dev, "mac", "")
        dtype = getattr(dev, "device_type", "")
        vendor = getattr(dev, "vendor", "")
        ip = getattr(dev, "ip", "")
        if mac:
            mac_to_type[mac] = dtype
            mac_to_label[mac] = f"{vendor or dtype} ({ip})" if ip else mac

    storm_level = getattr(storm_result, "storm_level", "CLEAN")
    top_sources = getattr(storm_result, "top_sources", [])    # [(mac, count)]
    bcast_pps   = getattr(storm_result, "bcast_per_sec", 0.0)

    if storm_level in ("WARNING", "STORM"):
        for mac, count in top_sources[:5]:
            dtype = mac_to_type.get(mac, "")
            label = mac_to_label.get(mac, mac)
            if dtype in iot_types:
                sev = HIGH if storm_level == "STORM" else MEDIUM
                findings.append(CorrelatedFinding(
                    source="Broadcast Storm Analyser",
                    category="Degraded IoT Device — Excessive Broadcasting",
                    severity=sev,
                    headline=f"IoT device {label} is flooding the network",
                    detail=(
                        f"{label} (type: {dtype}) sent {count} broadcast packets "
                        f"during the scan window ({bcast_pps:.0f} pkt/s total). "
                        "Excessive broadcasting from IoT devices slows down every "
                        "other device on the same network segment and is often a sign "
                        "of a software bug or compromised firmware."
                    ),
                    remediation=(
                        f"Restart {label}. If the flooding continues, move it to a "
                        "separate guest Wi-Fi network so it cannot affect your main "
                        "devices. Check the manufacturer's website for a firmware update."
                    ),
                    verify_step=(
                        "Go to Broadcast Storm in NetSentinel — the storm level "
                        "should return to CLEAN after isolating or restarting the device."
                    ),
                ))

        if not any(f.category.startswith("Degraded IoT") for f in findings):
            # Storm from non-IoT sources
            findings.append(CorrelatedFinding(
                source="Broadcast Storm Analyser",
                category="Broadcast Storm",
                severity=HIGH if storm_level == "STORM" else MEDIUM,
                headline=f"Broadcast storm detected ({bcast_pps:.0f} pkt/s)",
                detail=(
                    "An abnormally high rate of broadcast/multicast packets is "
                    "saturating your local network. This causes slowdowns for all "
                    "connected devices and is often caused by a misconfigured device "
                    "or a network loop."
                ),
                remediation=(
                    "Check which device is sending the most broadcasts (see Storm "
                    "Analyser tab). Disconnect it temporarily to confirm. Look for "
                    "any Ethernet cables plugged into two ports on the same switch "
                    "(network loop)."
                ),
                verify_step=(
                    "Go to Broadcast Storm in NetSentinel — the storm level "
                    "should return to CLEAN after disconnecting the culprit device."
                ),
            ))


# ── STP rogue bridge ──────────────────────────────────────────────────────────

def _correlate_stp(
    stp_bpdus: list,
    gateway_mac: Optional[str],
    findings: List[CorrelatedFinding],
) -> None:
    """Promote any rogue BPDU finding to a root-cause entry."""
    for bpdu in stp_bpdus:
        is_rogue = getattr(bpdu, "is_rogue", False)
        src_mac  = getattr(bpdu, "src_mac", "")
        verdict  = getattr(bpdu, "verdict", "")
        if is_rogue:
            findings.append(CorrelatedFinding(
                source="Rogue Bridge Detector (STP)",
                category="Rogue Network Bridge",
                severity=CRITICAL,
                headline=f"Rogue bridge detected: {src_mac}",
                detail=(
                    verdict or
                    f"Device {src_mac} is injecting Spanning Tree Protocol (STP) "
                    "frames and may have taken over as the Root Bridge. This forces "
                    "your real router into a backup role and causes 15–45 second "
                    "internet outage cycles."
                ),
                remediation=(
                    f"Unplug the Ethernet cable from {src_mac}. "
                    "If it is a mesh Wi-Fi node, switch it to wireless backhaul mode "
                    "only. If it is a switch or hub, enable Rapid STP (RSTP) and "
                    "set a lower bridge priority on your main router."
                ),
                verify_step=(
                    "Go to Rogue Bridge (STP) in NetSentinel — the device "
                    "should no longer appear in the list after disconnecting it."
                ),
            ))


# ── Logger stability ──────────────────────────────────────────────────────────

def _correlate_logger(
    log_summary,
    findings: List[CorrelatedFinding],
) -> None:
    """Translate long-term logger metrics into root-cause findings."""
    if log_summary is None:
        return

    uptime = getattr(log_summary, "uptime_pct", 100.0)
    jitter = getattr(log_summary, "avg_jitter_ms", 0.0)
    outages = getattr(log_summary, "outages", [])
    total_pings = getattr(log_summary, "total_pings", 0)

    if total_pings == 0:
        return

    if uptime < 95.0:
        sev = CRITICAL if uptime < 80 else HIGH
        findings.append(CorrelatedFinding(
            source="Connection Stability Monitor",
            category="Chronic Connectivity Loss",
            severity=sev,
            headline=f"Network uptime only {uptime:.1f}% — frequent drops detected",
            detail=(
                f"Over the monitored period, {100 - uptime:.1f}% of pings failed "
                f"({len(outages)} outage(s) recorded). "
                "This level of packet loss causes video calls to freeze, buffering "
                "on streaming services, and VPN disconnections."
            ),
            remediation=(
                "Check all Ethernet cables for damage (bend them gently — a cracked "
                "cable will drop packets intermittently). Restart your router and "
                "modem. If the drops happen on Wi-Fi, try a wired connection to "
                "confirm whether the fault is in your router or ISP line."
            ),
            verify_step=(
                "NetSentinel's Connection Monitor will automatically detect "
                "when the drops stop. Check Availability for an updated timeline."
            ),
        ))

    if jitter > 20.0:
        sev = HIGH if jitter > 50 else MEDIUM
        findings.append(CorrelatedFinding(
            source="Connection Stability Monitor",
            category="High Jitter — Unstable Latency",
            severity=sev,
            headline=f"High jitter detected ({jitter:.0f} ms) — video calls will suffer",
            detail=(
                f"Average response-time variation (jitter) is {jitter:.0f} ms. "
                "Jitter above 20 ms causes poor voice and video call quality even "
                "when average speed seems fine. Common causes: Wi-Fi interference, "
                "ISP congestion, or a router that cannot handle your traffic load."
            ),
            remediation=(
                "Switch to a 5 GHz Wi-Fi channel or use a wired Ethernet cable. "
                "On your router admin page, enable QoS (Quality of Service) to "
                "prioritise video-call traffic. If jitter is only high at peak "
                "times, your ISP line may be congested — contact them."
            ),
            verify_step=(
                "Go to DNS & Stability in NetSentinel to see if jitter has "
                "improved after making changes. After the fix, click Rescan."
            ),
        ))


# ── Diagnostics: per-check plain-English ──────────────────────────────────────

def _correlate_diagnostics(
    diag_result,
    findings: List[CorrelatedFinding],
    gateway_ip: Optional[str] = None,
) -> None:
    """Translate raw DiagnosticsResult checks into plain-English findings."""
    if diag_result is None:
        return

    # DNS failures
    dns_results = getattr(diag_result, "dns_results", [])
    dns_fails = [d for d in dns_results if getattr(d, "status", "") == "FAIL"]
    if dns_fails:
        servers = ", ".join(getattr(d, "server", "?") for d in dns_fails[:3])
        findings.append(CorrelatedFinding(
            source="Network Diagnostics",
            category="DNS Resolution Failure",
            severity=HIGH,
            headline=f"DNS lookup failed on: {servers}",
            detail=(
                "Your device cannot resolve domain names (e.g. google.com → IP "
                "address). This means websites appear broken even if raw internet "
                "connectivity works. Affected resolvers: " + servers
            ),
            remediation=(
                "Open your router settings"
                + (f" at http://{gateway_ip}" if gateway_ip else "")
                + " and change the DNS server to 1.1.1.1 (Cloudflare) or 8.8.8.8 "
                "(Google). This fixes every device on your network at once."
            ),
            verify_step=(
                "Go to DNS & Stability in NetSentinel and run a fresh DNS test. "
                "After making this change, click Rescan to confirm the problem is gone."
            ),
        ))

    # Download speed very low
    dl = getattr(diag_result, "download_mbps", -1.0)
    if 0 < dl < 5.0:
        findings.append(CorrelatedFinding(
            source="Network Diagnostics",
            category="Very Low Download Speed",
            severity=HIGH,
            headline=f"Download speed only {dl:.1f} Mbps — severely degraded",
            detail=(
                f"Measured download speed is {dl:.1f} Mbps. Streaming HD video "
                "requires at least 5 Mbps; video calls need 3–8 Mbps. "
                "This will cause severe buffering and call quality issues."
            ),
            remediation=(
                f"NetSentinel measured {dl:.1f} Mbps download on this device. "
                "Open the Bandwidth Monitor in NetSentinel to check if other "
                "devices are using all the bandwidth. If the problem persists "
                "after a router restart, call your ISP and quote this measurement."
            ),
            verify_step=(
                "Go to Speed Test in NetSentinel and run a new test to confirm "
                "speed has improved. After the fix, click Rescan."
            ),
        ))

    # DNS leak
    leak = getattr(diag_result, "dns_leak", None)
    if leak and getattr(leak, "leak_detected", False):
        findings.append(CorrelatedFinding(
            source="Network Diagnostics",
            category="DNS Leak Detected",
            severity=MEDIUM,
            headline="DNS requests are leaking outside your VPN",
            detail=(
                "Your DNS queries are being sent to servers outside your VPN "
                "tunnel. This means your ISP (and potentially others) can see "
                "every website you visit even while connected to a VPN."
            ),
            remediation=(
                "In your VPN client settings, enable 'DNS Leak Protection' or "
                "'Block DNS outside VPN'. Alternatively, configure your router"
                + (f" at http://{gateway_ip}" if gateway_ip else "")
                + " to use only your VPN provider's DNS servers."
            ),
            verify_step=(
                "Go to DNS & Stability in NetSentinel and run a fresh DNS leak "
                "test to confirm the leak is gone."
            ),
        ))


# ── Public API ────────────────────────────────────────────────────────────────

def correlate(
    diag_result=None,
    storm_result=None,
    stp_bpdus: Optional[list] = None,
    fingerprint_devices: Optional[list] = None,
    log_summary=None,
    gateway_mac: Optional[str] = None,
    gateway_ip: Optional[str] = None,
    recent_alerts: Optional[List[dict]] = None,
) -> CorrelationResult:
    """
    Run all correlation passes and return a CorrelationResult.

    Parameters (all optional — pass whatever is available)
    ──────────────────────────────────────────────────────
    diag_result         : DiagnosticsResult from network_diagnostics.run_all()
    storm_result        : StormResult from storm_analyser.scan()
    stp_bpdus           : List[BPDUInfo] from stp_detector.scan()
    fingerprint_devices : List[DeviceInfo] from rogue_device.scan()
    log_summary         : LogSummary from network_logger
    gateway_mac         : MAC of the default gateway (str)
    recent_alerts       : List[dict] from store.get_recent_alerts() — folds in
                           already-fired MESH_DEGRADED / MODEM_SIGNAL_DROP /
                           IOT_BEHAVIOR / BASELINE_DROP alerts (V6 Sprint 5.1)

    Returns
    ──────
    CorrelationResult with prioritised findings and a plain-text summary.
    """
    findings: List[CorrelatedFinding] = []

    trace_hops   = getattr(diag_result, "trace_hops",   []) if diag_result else []
    ping_results = getattr(diag_result, "ping_results", []) if diag_result else []

    # Run each correlator pass
    isp_to_blame = _correlate_isp(trace_hops, ping_results, findings)
    _correlate_storm(storm_result, fingerprint_devices or [], findings)
    _correlate_stp(stp_bpdus or [], gateway_mac, findings)
    _correlate_logger(log_summary, findings)
    if not isp_to_blame:
        _correlate_diagnostics(diag_result, findings, gateway_ip)

    from modules.root_cause_correlator_alerts import correlate_recent_alerts
    correlate_recent_alerts(recent_alerts or [], findings)

    # Sort by severity (highest first)
    findings.sort(key=lambda f: _severity_rank(f.severity), reverse=True)

    global_sev = _highest([f.severity for f in findings]) if findings else INFO

    # Build plain summary
    if not findings:
        summary = "No correlated issues found. Network appears healthy."
    elif isp_to_blame:
        summary = (
            "Root cause analysis points to your ISP — local network hardware "
            "is working correctly. Contact your ISP with the traceroute results."
        )
    else:
        top = findings[0]
        summary = (
            f"{top.headline}. "
            + (f"Plus {len(findings)-1} additional issue(s)." if len(findings) > 1 else "")
        )

    return CorrelationResult(
        findings=findings,
        global_severity=global_sev,
        plain_summary=summary,
        isp_issue_detected=isp_to_blame,
        local_issue_detected=not isp_to_blame and bool(findings),
        suppress_local_alerts=isp_to_blame,
    )
