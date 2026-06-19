"""
Private Endpoint Checker
========================
Verifies that named service endpoints (hostname:port) are:
  1. Resolving to a private (RFC-1918 / RFC-4193) address — not leaking to public
  2. TCP reachable on the declared port
  3. TLS certificate valid, not expired, and hostname matches (HTTPS/TLS ports)
  4. Classified by cloud provider (Azure, AWS, GCP) when recognisable

Zero extra dependencies — uses stdlib ssl, socket, ipaddress only.

Usage:
    from modules.private_endpoint_checker import check_endpoints, EndpointSpec
    results = check_endpoints([
        EndpointSpec("myblob.privatelink.blob.core.windows.net", 443),
        EndpointSpec("my-rds.cluster-xxxx.us-east-1.rds.amazonaws.com", 5432),
        EndpointSpec("10.0.1.55", 22),
    ])
"""

from __future__ import annotations

import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


# ── Cloud provider patterns ───────────────────────────────────────────────────

_CLOUD_PATTERNS: List[tuple] = [
    ("Azure",      (".privatelink.", ".azure.com", ".windows.net", ".azure.net",
                    ".microsoft.com", ".azurewebsites.net", ".scm.azurewebsites.net")),
    ("AWS",        (".amazonaws.com", ".aws.com", ".elasticbeanstalk.com", ".awsapprunner.com")),
    ("GCP",        (".googleapis.com", ".google.com", ".appspot.com",
                    ".cloudfunctions.net", ".run.app")),
    ("Cloudflare", (".cloudflare.com", ".workers.dev", ".pages.dev")),
]

_PRIVATE_RANGES = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT
    ipaddress.ip_network("fd00::/8"),         # IPv6 ULA
    ipaddress.ip_network("fc00::/7"),
)

_TLS_PORTS = {443, 8443, 4443, 636, 993, 995, 465, 5671, 5986}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class EndpointSpec:
    """Input: a hostname (or bare IP) + TCP port to check."""
    host: str
    port: int
    label: str = ""          # optional friendly name shown in UI

    def __post_init__(self):
        if not self.label:
            self.label = f"{self.host}:{self.port}"


@dataclass
class CertInfo:
    subject_cn:  str = ""
    sans:        List[str] = field(default_factory=list)
    issuer:      str = ""
    not_before:  str = ""
    not_after:   str = ""
    days_left:   int = -1
    hostname_ok: bool = False
    expired:     bool = False
    error:       str = ""


@dataclass
class EndpointResult:
    spec:         EndpointSpec = field(default_factory=lambda: EndpointSpec("", 0))

    # DNS
    resolved_ips: List[str] = field(default_factory=list)
    dns_ok:       bool = False          # resolved at least one address
    is_private:   bool = False          # all resolved IPs are private
    dns_leak:     bool = False          # resolved to public IP (bad for private endpoint)
    dns_latency:  float = -1.0          # ms
    dns_server:   str = ""              # which system resolver was used

    # PaaS hint (non-empty when hostname matches a known managed platform suffix)
    paas_hint:    str = ""

    # TCP
    tcp_open:     bool = False
    tcp_latency:  float = -1.0          # ms

    # TLS
    tls_checked:  bool = False
    cert:         Optional[CertInfo] = None

    # Classification
    cloud:        str = ""              # "Azure" / "AWS" / "GCP" / ""

    # Overall
    status:       str = "UNKNOWN"       # PASS / WARN / FAIL
    findings:     List[str] = field(default_factory=list)

    @property
    def plain_verdict(self) -> str:
        if not self.findings:
            return f"{self.spec.label} — all checks passed."
        return f"{self.spec.label} — {self.findings[0]}"


# ── Helpers ───────────────────────────────────────────────────────────────────

# Maps hostname suffix → (service_label, guidance_message)
# Add more entries here to support additional cloud PaaS platforms.
_PAAS_HINTS: dict[str, tuple[str, str]] = {
    # ── Azure ────────────────────────────────────────────────────────────────
    ".azurewebsites.net": (
        "Azure App Service",
        "DNS resolution from this machine may differ from what the app sees inside Azure. "
        "Verify with the Kudu console: open https://<app>.scm.azurewebsites.net/DebugConsole "
        "and run 'nameresolver <hostname>'.",
    ),
    ".azurewebsites.windows.net": (
        "Azure App Service",
        "DNS resolution from this machine may differ from what the app sees inside Azure. "
        "Verify with the Kudu console: open https://<app>.scm.azurewebsites.net/DebugConsole "
        "and run 'nameresolver <hostname>'.",
    ),
    ".scm.azurewebsites.net": (
        "Azure App Service (Kudu)",
        "This is the Kudu management endpoint of an Azure App Service. "
        "DNS resolution from this machine may differ from what the app sees inside Azure.",
    ),
    # ── AWS ──────────────────────────────────────────────────────────────────
    ".elasticbeanstalk.com": (
        "AWS Elastic Beanstalk",
        "DNS resolution from this machine may differ from what the app sees inside your VPC. "
        "Test from an EC2 instance or Lambda in the same subnet to verify private DNS.",
    ),
    ".awsapprunner.com": (
        "AWS App Runner",
        "DNS resolution from this machine may differ from what the app sees inside your VPC. "
        "Test from an EC2 instance or Lambda in the same subnet to verify private DNS.",
    ),
    # ── GCP ──────────────────────────────────────────────────────────────────
    ".run.app": (
        "GCP Cloud Run",
        "DNS resolution from this machine may differ from what the service sees inside your VPC. "
        "Test from Cloud Shell or a VM in the same VPC to verify private DNS.",
    ),
    ".appspot.com": (
        "GCP App Engine",
        "DNS resolution from this machine may differ from what the app sees inside your VPC. "
        "Test from Cloud Shell or a VM in the same VPC to verify private DNS.",
    ),
}


def _detect_paas_hint(host: str) -> tuple[str, str]:
    """Return (service_label, hint) if host matches a known PaaS suffix, else ('', '')."""
    hl = host.lower()
    for suffix, (label, hint) in _PAAS_HINTS.items():
        if hl.endswith(suffix):
            return label, hint
    return "", ""


def _get_system_dns_server() -> str:
    """Return the first DNS server the OS is configured to use, or empty string."""
    import platform
    import subprocess
    system = platform.system()
    try:
        if system == "Windows":
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-DnsClientServerAddress -AddressFamily IPv4 | "
                 "Where-Object { $_.ServerAddresses } | "
                 "Select-Object -First 1).ServerAddresses[0]"],
                capture_output=True, text=True, timeout=5,
            )
            ip = r.stdout.strip()
            return ip if ip else ""
        elif system == "Darwin":
            r = subprocess.run(
                ["scutil", "--dns"], capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.startswith("nameserver["):
                    parts = line.split()
                    if len(parts) >= 3:
                        return parts[2]
        else:  # Linux
            with open("/etc/resolv.conf") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("nameserver"):
                        parts = line.split()
                        if len(parts) >= 2:
                            return parts[1]
    except Exception:
        pass  # non-fatal
    return ""


def _is_private(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _PRIVATE_RANGES) or addr.is_loopback
    except ValueError:
        return False


def _detect_cloud(host: str) -> str:
    hl = host.lower()
    for provider, patterns in _CLOUD_PATTERNS:
        if any(p in hl for p in patterns):
            return provider
    return ""


def _resolve(host: str) -> tuple[List[str], float]:
    """Return (list_of_ips, latency_ms). Falls back gracefully."""
    try:
        t0 = time.monotonic()
        infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        latency = (time.monotonic() - t0) * 1000
        ips = list(dict.fromkeys(i[4][0] for i in infos))  # deduplicated, order preserved
        return ips, latency
    except Exception:
        return [], -1.0


def _tcp_probe(host: str, port: int, timeout: float = 4.0) -> tuple[bool, float]:
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, (time.monotonic() - t0) * 1000
    except Exception:
        return False, (time.monotonic() - t0) * 1000


def _tls_inspect(host: str, port: int, timeout: float = 6.0) -> CertInfo:
    info = CertInfo()
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(
            socket.create_connection((host, port), timeout=timeout),
            server_hostname=host,
            do_handshake_on_connect=True,
        ) as ssock:
            der = ssock.getpeercert()
            if not der:
                info.error = "No certificate returned"
                return info

            # Subject CN
            for rdn in der.get("subject", ()):
                for k, v in rdn:
                    if k == "commonName":
                        info.subject_cn = v

            # SANs
            for san_type, san_val in der.get("subjectAltName", ()):
                if san_type in ("DNS", "IP Address"):
                    info.sans.append(san_val)

            # Issuer
            for rdn in der.get("issuer", ()):
                for k, v in rdn:
                    if k == "organizationName":
                        info.issuer = v
                        break

            # Validity
            fmt = "%b %d %H:%M:%S %Y %Z"
            nb = der.get("notBefore", "")
            na = der.get("notAfter", "")
            info.not_before = nb
            info.not_after  = na
            try:
                exp = datetime.strptime(na, fmt).replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                info.days_left = (exp - now).days
                info.expired   = info.days_left < 0
            except Exception:
                pass  # non-fatal

            # Hostname match — check CN + SANs
            host_lower = host.lower()
            candidates = [info.subject_cn.lower()] + [s.lower() for s in info.sans]
            for cand in candidates:
                if cand == host_lower:
                    info.hostname_ok = True
                    break
                if cand.startswith("*."):
                    # wildcard: *.example.com matches sub.example.com but not sub.sub.example.com
                    suffix = cand[2:]
                    parts  = host_lower.split(".")
                    if len(parts) >= 2 and ".".join(parts[1:]) == suffix:
                        info.hostname_ok = True
                        break

    except ssl.CertificateError as e:
        info.hostname_ok = False
        info.error = f"Certificate error: {e}"
    except Exception as e:
        info.error = str(e)
    return info


# ── Main entry point ──────────────────────────────────────────────────────────

def check_endpoint(spec: EndpointSpec) -> EndpointResult:
    """Run all checks for a single endpoint."""
    res = EndpointResult(spec=spec)
    res.cloud = _detect_cloud(spec.host)

    # ── PaaS platform hint ───────────────────────────────────────────────────
    paas_label, paas_guidance = _detect_paas_hint(spec.host)
    if paas_label:
        res.paas_hint = paas_guidance
        res.findings.append(f"ℹ  {paas_label} detected — {paas_guidance}")

    # ── Capture system DNS server for informational output ───────────────────
    res.dns_server = _get_system_dns_server()
    # Try to resolve the host; if it's already a bare IP, skip resolution
    try:
        ipaddress.ip_address(spec.host)
        # It's a bare IP — treat as pre-resolved
        res.resolved_ips  = [spec.host]
        res.dns_ok        = True
        res.dns_latency   = 0.0
    except ValueError:
        ips, latency = _resolve(spec.host)
        res.resolved_ips = ips
        res.dns_latency  = latency
        res.dns_ok       = len(ips) > 0

    if res.dns_ok:
        private_flags = [_is_private(ip) for ip in res.resolved_ips]
        res.is_private = all(private_flags)
        res.dns_leak   = any(not f for f in private_flags)

        if res.dns_leak:
            public_ips = [ip for ip, priv in zip(res.resolved_ips, private_flags) if not priv]
            res.findings.append(
                f"DNS LEAK — resolves to public IP(s): {', '.join(public_ips)}. "
                "Private endpoint traffic may egress over the internet."
            )
    else:
        res.findings.append(f"DNS resolution failed for '{spec.host}'.")

    # ── TCP ──────────────────────────────────────────────────────────────────
    connect_host = res.resolved_ips[0] if res.resolved_ips else spec.host
    res.tcp_open, res.tcp_latency = _tcp_probe(connect_host, spec.port)
    if not res.tcp_open:
        res.findings.append(
            f"TCP port {spec.port} unreachable on {connect_host}. "
            "Firewall / NSG may be blocking, or service is down."
        )

    # ── TLS ──────────────────────────────────────────────────────────────────
    if spec.port in _TLS_PORTS or spec.port == 443:
        res.tls_checked = True
        cert = _tls_inspect(spec.host, spec.port)
        res.cert = cert
        if cert.error:
            res.findings.append(f"TLS error: {cert.error}")
        else:
            if cert.expired:
                res.findings.append(
                    f"TLS certificate EXPIRED {abs(cert.days_left)} day(s) ago "
                    f"(expiry: {cert.not_after})."
                )
            elif cert.days_left >= 0 and cert.days_left < 30:
                res.findings.append(
                    f"TLS certificate expires in {cert.days_left} day(s) — renew soon."
                )
            if not cert.hostname_ok:
                res.findings.append(
                    f"TLS hostname mismatch — cert CN/SAN does not match '{spec.host}'. "
                    "Possible misconfiguration or MITM."
                )

    # ── Overall status ────────────────────────────────────────────────────────
    critical = any(
        any(kw in f for kw in ("LEAK", "EXPIRED", "mismatch", "unreachable", "failed"))
        for f in res.findings
    )
    warn = any("expires in" in f for f in res.findings)

    if critical:
        res.status = "FAIL"
    elif warn or (res.tls_checked and res.cert and res.cert.days_left < 30):
        res.status = "WARN"
    elif res.dns_ok and res.tcp_open:
        res.status = "PASS"
    else:
        res.status = "FAIL"

    return res


def check_endpoints(specs: List[EndpointSpec]) -> List[EndpointResult]:
    """Check multiple endpoints sequentially. Returns results in same order."""
    return [check_endpoint(s) for s in specs]
