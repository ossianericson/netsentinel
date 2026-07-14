"""
Automatic per-finding risk scorer.

Takes the combined output of Module 1 (device fingerprint), the port scanner,
OS fingerprint, and device-type classifier, and returns a structured
RiskAssessment for each device — with a numeric score, severity label,
plain-English impact statement, and prioritised remediation steps.

No network calls are made here; purely analytical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ── Score constants ────────────────────────────────────────────────────────────

# Severity bands  (score out of 100)
CRITICAL = "CRITICAL"   # 80–100  — immediate action required
HIGH     = "HIGH"       # 60–79   — action required
MEDIUM   = "MEDIUM"     # 35–59   — review recommended
LOW      = "LOW"        # 10–34   — informational
INFO     = "INFO"       # 0–9     — no concern


def _band(score: int) -> str:
    if score >= 80: return CRITICAL
    if score >= 60: return HIGH
    if score >= 35: return MEDIUM
    if score >= 10: return LOW
    return INFO


# Per-port risk contributions
_PORT_SCORES: dict[int, tuple[int, str, str]] = {
    # port: (score_contribution, short_label, impact)
    23:    (25, "Telnet",        "Credentials transmitted in plaintext — trivially interceptable on any LAN."),
    445:   (25, "SMB",          "Windows file sharing exposed — primary vector for ransomware lateral movement (EternalBlue, WannaCry)."),
    3389:  (25, "RDP",          "Remote Desktop exposed — brute-force and BlueKeep-class exploits actively used in the wild."),
    5900:  (20, "VNC",          "Remote control port open — often unauthenticated or weakly authenticated on IoT/embedded devices."),
    7547:  (30, "CWMP/TR-069",  "ISP remote management port exposed on LAN — allows ISP (or attacker) to reconfigure device remotely."),
    1883:  (15, "MQTT",         "IoT message broker without TLS — device commands and sensor data readable by anyone on the network."),
    21:    (10, "FTP",          "File transfer in plaintext — credentials and data visible on the network."),
    5000:  ( 8, "UPnP/DevSrv",  "UPnP or development server port open — may expose internal APIs without authentication."),
    8888:  ( 8, "Jupyter/Dev",  "Jupyter or developer service — often runs without authentication; full code execution risk."),
    49152: ( 5, "UPnP SSDP",    "UPnP service discovery port open — can be abused for port mapping or amplification attacks."),
}

# Device type risk modifiers
_DTYPE_SCORES: dict[str, tuple[int, str]] = {
    "IP Camera":             (15, "IP cameras frequently run outdated firmware with known CVEs and default credentials."),
    "Industrial / ICS Device": (20, "ICS/OT devices are high-value targets; many have no authentication or patching mechanism."),
    "Router / Firewall":      (5, "Gateway device — any misconfiguration affects all network traffic."),
    "Router / Gateway":       (5, "Gateway device — any misconfiguration affects all network traffic."),
    "Domain Controller":      (15, "Domain Controllers are prime targets; compromise grants control of all domain-joined systems."),
    "IoT Device":             (10, "IoT devices commonly ship with default credentials and receive infrequent security updates."),
    "Smart Home Hub":          (8, "Smart home hubs aggregate control of physical devices; compromise has real-world consequences."),
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RiskFinding:
    """A single scored risk finding for one device."""
    title: str
    score_contribution: int
    impact: str
    remediation: str


@dataclass
class RiskAssessment:
    """Complete risk profile for one device."""
    ip: str
    mac: str
    hostname: str
    vendor: str
    device_type: str
    os_family: str
    total_score: int                          # 0–100
    severity: str                             # CRITICAL / HIGH / MEDIUM / LOW / INFO
    findings: List[RiskFinding] = field(default_factory=list)
    plain_summary: str = ""
    top_remediation: str = ""


# ── Scorer ────────────────────────────────────────────────────────────────────

def score_device(
    ip: str,
    mac: str = "",
    hostname: str = "",
    vendor: str = "",
    device_type: str = "",
    os_family: str = "",
    open_ports: Optional[List[int]] = None,
    m1_risk_level: str = "",
    known_issues: Optional[List[str]] = None,
    credential_access: bool = False,
) -> RiskAssessment:
    """
    Produce a RiskAssessment for a single device.

    Parameters mirror the DeviceInfo fields from Module 1 plus the port scanner.
    credential_access: True when Login Test successfully authenticated to this
        host with the supplied credentials (modules/credentialed_scan.py) —
        proof the device is reachable and loggable-into over the network.
    """
    open_ports   = set(open_ports or [])
    known_issues = known_issues or []
    findings: List[RiskFinding] = []
    total = 0

    # ── 1. Dangerous open ports ───────────────────────────────────────────
    for port in open_ports:
        if port in _PORT_SCORES:
            pts, label, impact = _PORT_SCORES[port]
            findings.append(RiskFinding(
                title=f"Port {port} open ({label})",
                score_contribution=pts,
                impact=impact,
                remediation=_port_remediation(port),
            ))
            total += pts

    # ── 2. Device-type modifier ───────────────────────────────────────────
    if device_type in _DTYPE_SCORES:
        pts, impact = _DTYPE_SCORES[device_type]
        findings.append(RiskFinding(
            title=f"Device type: {device_type}",
            score_contribution=pts,
            impact=impact,
            remediation="Ensure firmware is current and default credentials are changed.",
        ))
        total += pts

    # ── 3. Module 1 OUI risk level ────────────────────────────────────────
    level_pts = {"HIGH": 20, "MEDIUM": 10, "LOW": 5, "CLEAN": 0, "UNKNOWN": 3}
    if m1_risk_level in level_pts and level_pts[m1_risk_level] > 0:
        pts = level_pts[m1_risk_level]
        issue_text = "; ".join(known_issues[:2]) if known_issues else "Vendor flagged in OUI risk database."
        findings.append(RiskFinding(
            title=f"Vendor risk ({m1_risk_level}): {vendor}",
            score_contribution=pts,
            impact=issue_text,
            remediation="Review known issues for this vendor and apply recommended network segmentation.",
        ))
        total += pts

    # ── 4. Link-local address ─────────────────────────────────────────────
    if ip.startswith("169.254."):
        findings.append(RiskFinding(
            title="Link-local address (DHCP failure or rogue host)",
            score_contribution=15,
            impact="Device has no valid DHCP lease. May indicate a rogue device or DHCP exhaustion attack.",
            remediation="Investigate device identity. Check DHCP server logs for exhaustion.",
        ))
        total += 15

    # ── 5. Confirmed working login credentials (Login Test) ──────────────
    if credential_access:
        findings.append(RiskFinding(
            title="Working login credentials confirmed (Login Test)",
            score_contribution=35,
            impact="A Login Test scan successfully authenticated to this device — it is reachable "
                   "and loggable-into over the network with the credentials that were tried.",
            remediation="Rotate this device's password immediately and restrict remote login access "
                        "to trusted management hosts.",
        ))
        total += 35

    # Cap at 100
    total = min(total, 100)
    severity = _band(total)

    # Plain summary
    if not findings:
        plain_summary = f"{ip} — No significant risks detected."
        top_remediation = "No action required."
    else:
        top = sorted(findings, key=lambda f: f.score_contribution, reverse=True)[0]
        plain_summary = (
            f"{ip} ({device_type or vendor}) — {severity} risk (score {total}/100). "
            f"Primary concern: {top.title}."
        )
        top_remediation = top.remediation

    return RiskAssessment(
        ip=ip, mac=mac, hostname=hostname, vendor=vendor,
        device_type=device_type, os_family=os_family,
        total_score=total, severity=severity,
        findings=findings,
        plain_summary=plain_summary,
        top_remediation=top_remediation,
    )


def score_devices(devices: list, credential_hosts: Optional[set] = None) -> List[RiskAssessment]:
    """
    Score a list of DeviceInfo objects (or dicts) from Module 1.

    credential_hosts: IPs where Login Test confirmed working credentials
        (see score_device's credential_access parameter).
    Returns assessments sorted by total_score descending.
    """
    credential_hosts = credential_hosts or set()
    assessments = []
    for d in devices:
        if isinstance(d, dict):
            ip = d.get("ip", "")
            assessments.append(score_device(
                ip=ip,
                mac=d.get("mac", ""),
                hostname=d.get("hostname", ""),
                vendor=d.get("vendor", ""),
                device_type=d.get("device_type", ""),
                os_family=d.get("os_family", ""),
                open_ports=d.get("open_ports", []),
                m1_risk_level=d.get("risk_level", ""),
                known_issues=d.get("known_issues", []),
                credential_access=ip in credential_hosts,
            ))
        else:
            ip = getattr(d, "ip", "")
            assessments.append(score_device(
                ip=ip,
                mac=getattr(d, "mac", ""),
                hostname=getattr(d, "hostname", ""),
                vendor=getattr(d, "vendor", ""),
                device_type=getattr(d, "device_type", ""),
                os_family=getattr(d, "os_family", ""),
                open_ports=getattr(d, "open_ports", []) or [],
                m1_risk_level=getattr(d, "risk_level", ""),
                known_issues=getattr(d, "known_issues", []) or [],
                credential_access=ip in credential_hosts,
            ))
    return sorted(assessments, key=lambda a: a.total_score, reverse=True)


# ── Per-port remediation text ─────────────────────────────────────────────────

def _port_remediation(port: int) -> str:
    _REM = {
        23:    "Disable Telnet on the device admin panel. Use SSH instead.",
        445:   "Block TCP 445 at the network perimeter. Disable SMBv1 on all Windows hosts. Ensure patching is current.",
        3389:  "Restrict RDP access using firewall rules or VPN. Enable Network Level Authentication. Apply all Windows updates.",
        5900:  "Disable VNC if not actively used. If required, set a strong password and restrict to trusted IPs.",
        7547:  "Contact your ISP to confirm TR-069 is needed. If not, disable CWMP in your router settings.",
        1883:  "Enable TLS on the MQTT broker (port 8883). Add client authentication. Restrict broker access by IP.",
        21:    "Replace FTP with SFTP or FTPS. Disable FTP if not required.",
        5000:  "Identify the service on port 5000. Disable UPnP if not required. Restrict development servers to loopback.",
        8888:  "Add authentication to any Jupyter/dev server. Never expose notebook servers on a shared network.",
        49152: "Disable UPnP on your router if not required. Monitor for unexpected port mappings.",
    }
    return _REM.get(port, "Review whether this service needs to be accessible on the LAN. Restrict with firewall rules if not.")
