"""
Natural Language Query Engine

Parses plain-English questions about scan results and returns a filtered,
sorted subset of devices with an explanation.

Examples:
    "show me risky devices"
    "find exposed RDP"
    "which devices have telnet open"
    "show cameras"
    "what has SMB open"
    "list high risk"
    "find windows devices"
    "show devices with CVEs"
    "what is 192.168.1.1"
    "show printers"
    "find devices with open ports"
    "which devices are domain controllers"

No ML/NLP library required — uses a rule-based keyword matcher against
a small taxonomy.  Instant, offline, zero deps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


# ── Query result ──────────────────────────────────────────────────────────────

@dataclass
class QueryMatch:
    """A single device that matched a query."""
    device: Any           # DeviceInfo or any dict/object with ip, hostname, etc.
    score: float = 1.0    # higher = more relevant
    reason: str = ""      # human-readable explanation


@dataclass
class QueryResult:
    matches: List[QueryMatch] = field(default_factory=list)
    query: str = ""
    explanation: str = ""   # plain-English description of what the query did
    error: str = ""

    @property
    def count(self) -> int:
        return len(self.matches)

    @property
    def empty(self) -> bool:
        return len(self.matches) == 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", s.strip().lower())


def _attr(obj: Any, *keys: str, default: Any = "") -> Any:
    """Safely read an attribute or dict key."""
    for k in keys:
        if isinstance(obj, dict):
            v = obj.get(k, None)
        else:
            v = getattr(obj, k, None)
        if v is not None:
            return v
    return default


def _open_ports(device: Any) -> List[int]:
    """Return list of open port numbers from a device object."""
    ports = _attr(device, "open_ports", "ports", default=[])
    result: List[int] = []
    for p in ports:
        if isinstance(p, int):
            result.append(p)
        elif isinstance(p, dict):
            if p.get("open"):
                result.append(p.get("port", 0))
        elif hasattr(p, "port") and hasattr(p, "open"):
            if p.open:
                result.append(p.port)
    return result


def _risk_level(device: Any) -> str:
    return str(_attr(device, "risk_level", "risk", "severity", default="UNKNOWN")).upper()


def _device_type(device: Any) -> str:
    return str(_attr(device, "device_type", "type", default="")).lower()


def _vendor(device: Any) -> str:
    return str(_attr(device, "vendor", "manufacturer", default="")).lower()


def _hostname(device: Any) -> str:
    return str(_attr(device, "hostname", "name", default="")).lower()


def _ip(device: Any) -> str:
    return str(_attr(device, "ip", "address", default=""))


def _os_family(device: Any) -> str:
    return str(_attr(device, "os_family", "os", default="")).lower()


# ── Matchers — each returns (matched: bool, reason: str, score: float) ────────

def _match_risk(device: Any, level: str) -> tuple:
    lvl = _risk_level(device)
    order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0, "CLEAN": 0}
    if level == "any" and order.get(lvl, 0) >= 1:
        return True, f"Risk level: {lvl}", float(order.get(lvl, 1))
    if lvl == level.upper():
        return True, f"Risk level: {lvl}", float(order.get(lvl, 1))
    if level == "high_or_above" and order.get(lvl, 0) >= 3:
        return True, f"Risk level: {lvl}", float(order.get(lvl, 3))
    if level == "medium_or_above" and order.get(lvl, 0) >= 2:
        return True, f"Risk level: {lvl}", float(order.get(lvl, 2))
    return False, "", 0.0


def _match_port(device: Any, port: int) -> tuple:
    if port in _open_ports(device):
        return True, f"Port {port} open", 2.0
    return False, "", 0.0


def _match_any_ports(device: Any, ports: List[int]) -> tuple:
    found = [p for p in ports if p in _open_ports(device)]
    if found:
        return True, f"Open ports: {', '.join(map(str, found))}", float(len(found))
    return False, "", 0.0


def _match_has_open_ports(device: Any) -> tuple:
    ports = _open_ports(device)
    if ports:
        return True, f"{len(ports)} open port(s): {', '.join(map(str, ports[:5]))}", 1.0
    return False, "", 0.0


def _match_device_type(device: Any, dtype: str) -> tuple:
    dt = _device_type(device)
    if dtype in dt:
        return True, f"Device type: {_attr(device, 'device_type', 'type', default=dtype)}", 2.0
    return False, "", 0.0


def _match_vendor_keyword(device: Any, kw: str) -> tuple:
    v = _vendor(device)
    h = _hostname(device)
    if kw in v or kw in h:
        return True, f"Vendor/hostname contains '{kw}'", 1.5
    return False, "", 0.0


def _match_os(device: Any, os_kw: str) -> tuple:
    os_f = _os_family(device)
    if os_kw in os_f:
        return True, f"OS family: {os_f}", 2.0
    return False, "", 0.0


def _match_ip(device: Any, ip_fragment: str) -> tuple:
    if ip_fragment in _ip(device):
        return True, f"IP: {_ip(device)}", 3.0
    return False, "", 0.0


def _match_has_cves(device: Any) -> tuple:
    cves = _attr(device, "cves", "cve_list", "vulnerabilities", default=[])
    if cves:
        return True, f"{len(cves)} CVE(s) found", 3.0
    return False, "", 0.0


# ── Intent taxonomy ───────────────────────────────────────────────────────────
# Each intent maps a pattern to a (filter_fn, explanation) factory.

_PORT_KEYWORDS: Dict[str, List[int]] = {
    "rdp":           [3389],
    "remote desktop":[3389],
    "ssh":           [22],
    "telnet":        [23],
    "smb":           [445, 139],
    "file sharing":  [445, 548],
    "ftp":           [21],
    "http":          [80, 8080, 8888],
    "https":         [443, 8443],
    "vnc":           [5900],
    "mqtt":          [1883],
    "tr-069":        [7547],
    "cwmp":          [7547],
    "upnp":          [5000, 49152],
    "print":         [631, 9100],
    "dns":           [53],
    "snmp":          [161, 162],
    "ldap":          [389, 636],
    "kerberos":      [88],
    "ntp":           [123],
    "imap":          [143, 993],
    "pop3":          [110, 995],
    "smtp":          [25, 587, 465],
    "rtsp":          [554],
    "camera stream": [554, 8554],
    "jupyter":       [8888],
    "mysql":         [3306],
    "postgres":      [5432],
    "redis":         [6379],
    "elasticsearch": [9200, 9300],
}

_DTYPE_KEYWORDS: Dict[str, str] = {
    "camera":            "camera",
    "ip camera":         "camera",
    "cctv":              "camera",
    "nas":               "nas",
    "file server":       "nas",
    "printer":           "printer",
    "print server":      "printer",
    "router":            "router",
    "gateway":           "router",
    "firewall":          "firewall",
    "switch":            "switch",
    "access point":      "access point",
    "ap":                "access point",
    "smart tv":          "smart tv",
    "tv":                "smart tv",
    "domain controller": "domain controller",
    "dc":                "domain controller",
    "iot":               "iot",
    "smart home":        "smart home",
    "phone":             "phone",
    "iphone":            "phone",
    "android":           "android",
    "laptop":            "laptop",
    "desktop":           "desktop",
    "server":            "server",
    "pc":                "windows",
}

_OS_KEYWORDS: Dict[str, str] = {
    "windows":  "windows",
    "linux":    "linux",
    "macos":    "macos",
    "mac":      "macos",
    "android":  "android",
    "ios":      "ios",
}

_RISK_KEYWORDS: Dict[str, str] = {
    "risky":            "medium_or_above",
    "risk":             "medium_or_above",
    "dangerous":        "high_or_above",
    "critical":         "CRITICAL",
    "high risk":        "HIGH",
    "high":             "high_or_above",
    "medium":           "MEDIUM",
    "low risk":         "LOW",
    "vulnerable":       "medium_or_above",
    "any risk":         "any",
}


# ── Query parser ──────────────────────────────────────────────────────────────

@dataclass
class _Intent:
    filter_fn: Callable[[Any], tuple]   # (device) → (match, reason, score)
    explanation: str


def _parse_intents(query: str) -> List[_Intent]:
    q = _norm(query)
    intents: List[_Intent] = []

    # IP address lookup
    ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", q)
    if ip_match:
        ip_frag = ip_match.group(1)
        intents.append(_Intent(
            filter_fn=lambda d, f=ip_frag: _match_ip(d, f),
            explanation=f"Devices with IP containing {ip_frag}",
        ))

    # CVE / vulnerability check
    if any(kw in q for kw in ("cve", "vulnerabilit", "exploit")):
        intents.append(_Intent(
            filter_fn=lambda d: _match_has_cves(d),
            explanation="Devices with known CVEs",
        ))

    # Open ports check
    if re.search(r"\bopen port|\bhas port|\bany port", q):
        intents.append(_Intent(
            filter_fn=lambda d: _match_has_open_ports(d),
            explanation="Devices with any open port",
        ))

    # Port-specific keywords
    for kw, ports in _PORT_KEYWORDS.items():
        if kw in q:
            intents.append(_Intent(
                filter_fn=lambda d, p=ports: _match_any_ports(d, p),
                explanation=f"Devices with {kw.upper()} port(s) open ({', '.join(map(str, ports))})",
            ))

    # Device type keywords
    for kw, dtype in _DTYPE_KEYWORDS.items():
        if kw in q:
            intents.append(_Intent(
                filter_fn=lambda d, t=dtype: _match_device_type(d, t),
                explanation=f"Devices classified as {dtype}",
            ))
            break   # first match wins for device type

    # OS keywords
    for kw, os_kw in _OS_KEYWORDS.items():
        if re.search(rf"\b{kw}\b", q):
            intents.append(_Intent(
                filter_fn=lambda d, o=os_kw: _match_os(d, o),
                explanation=f"Devices running {os_kw}",
            ))
            break

    # Risk level keywords
    for kw, level in _RISK_KEYWORDS.items():
        if kw in q:
            intents.append(_Intent(
                filter_fn=lambda d, lv=level: _match_risk(d, lv),
                explanation=f"Devices with risk: {level.replace('_', ' ')}",
            ))
            break

    # Vendor/hostname free-text — pick up remaining nouns
    # Strip known keywords to find leftover vendor hints
    remainder = q
    for strip in list(_PORT_KEYWORDS) + list(_DTYPE_KEYWORDS) + list(_OS_KEYWORDS) + list(_RISK_KEYWORDS):
        remainder = remainder.replace(strip, " ")
    for noise in ("show", "find", "list", "which", "what", "devices", "device",
                  "me", "all", "are", "is", "have", "has", "with", "open", "the",
                  "a", "an", "on", "my", "network", "exposed", "port", "ports"):
        remainder = re.sub(rf"\b{noise}\b", " ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip()
    if len(remainder) >= 3:
        intents.append(_Intent(
            filter_fn=lambda d, kw=remainder: _match_vendor_keyword(d, kw),
            explanation=f"Devices with '{remainder}' in vendor or hostname",
        ))

    return intents


# ── Public API ────────────────────────────────────────────────────────────────

def query(
    devices: List[Any],
    question: str,
    *,
    max_results: int = 100,
) -> QueryResult:
    """
    Filter and rank a list of device objects by a plain-English question.

    devices: list of any objects with attributes like ip, hostname, vendor,
             device_type, risk_level, open_ports, os_family, cves.
             Works with DeviceInfo, RiskAssessment, dicts, etc.
    question: natural language query string
    """
    if not question.strip():
        return QueryResult(query=question, error="Empty query.")

    intents = _parse_intents(question)
    if not intents:
        return QueryResult(
            query=question,
            error="Could not understand the query. "
                  "Try: 'show risky devices', 'find RDP', 'list cameras', 'show windows', 'find CVEs'.",
        )

    explanations = " AND ".join(i.explanation for i in intents)

    # Score each device against all intents
    matches: List[QueryMatch] = []
    for device in devices:
        total_score = 0.0
        reasons: List[str] = []
        all_matched = True

        for intent in intents:
            matched, reason, score = intent.filter_fn(device)
            if not matched:
                all_matched = False
                break
            total_score += score
            if reason:
                reasons.append(reason)

        if all_matched:
            matches.append(QueryMatch(
                device=device,
                score=total_score,
                reason=" · ".join(reasons),
            ))

    # Sort by score descending
    matches.sort(key=lambda m: m.score, reverse=True)
    matches = matches[:max_results]

    return QueryResult(
        matches=matches,
        query=question,
        explanation=explanations,
    )


# ── Suggestion helper ─────────────────────────────────────────────────────────

EXAMPLE_QUERIES: List[str] = [
    "show risky devices",
    "find exposed RDP",
    "which devices have telnet open",
    "show cameras",
    "find SMB",
    "list high risk",
    "find Windows devices",
    "show devices with CVEs",
    "what is 192.168.1.1",
    "show printers",
    "find domain controllers",
    "list Linux servers",
    "find MQTT",
    "show IoT devices",
    "find devices with open ports",
]
