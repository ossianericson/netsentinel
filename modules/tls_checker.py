"""
SSL/TLS certificate checker.

For each open HTTPS port found (443, 8443), fetches the certificate and
returns expiry date, issuer, subject, and whether it is self-signed.
No admin or raw sockets required — uses the standard ssl module.
"""

import ssl
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class CertInfo:
    host: str
    port: int
    subject: str = ""
    issuer: str = ""
    not_before: str = ""
    not_after: str = ""
    days_remaining: int = 0
    is_self_signed: bool = False
    is_expired: bool = False
    error: str = ""
    verdict: str = ""


def _parse_cert_field(cert_dict: dict, field_name: str) -> str:
    """Extract a human-readable string from a cert subject/issuer tuple-of-tuples."""
    for rdn in cert_dict.get(field_name, []):
        for key, value in rdn:
            if key == "commonName":
                return value
    return ""


def check_cert(host: str, port: int = 443, timeout: float = 5.0) -> CertInfo:
    """Retrieve and analyse the TLS certificate for host:port."""
    info = CertInfo(host=host, port=port)
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE   # we inspect manually
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()

        if not cert:
            info.error = "No certificate returned"
            return info

        subject = _parse_cert_field(cert, "subject")
        issuer  = _parse_cert_field(cert, "issuer")
        info.subject = subject
        info.issuer  = issuer

        not_after_str  = cert.get("notAfter", "")
        not_before_str = cert.get("notBefore", "")
        info.not_before = not_before_str
        info.not_after  = not_after_str

        if not_after_str:
            try:
                expiry = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z")
                expiry = expiry.replace(tzinfo=timezone.utc)
                now    = datetime.now(timezone.utc)
                delta  = (expiry - now).days
                info.days_remaining = delta
                info.is_expired     = delta < 0
            except Exception:
                pass  # non-fatal

        info.is_self_signed = (subject == issuer)

        # Build verdict
        if info.is_expired:
            info.verdict = f"🔴 EXPIRED cert on {host}:{port} (expired {not_after_str})"
        elif info.days_remaining < 14:
            info.verdict = f"🟡 Cert expiring soon: {info.days_remaining} days left on {host}:{port}"
        elif info.is_self_signed:
            info.verdict = f"🟡 Self-signed cert on {host}:{port} — not trusted by browsers"
        else:
            info.verdict = (
                f"✅ Valid cert on {host}:{port} — {info.days_remaining} days remaining, "
                f"issued by {issuer}"
            )
    except ssl.SSLError as exc:
        info.error   = str(exc)
        info.verdict = f"🟡 TLS error on {host}:{port}: {exc}"
    except (ConnectionRefusedError, OSError):
        info.error   = "Connection refused"
    except Exception as exc:
        info.error   = str(exc)
        info.verdict = f"Error checking {host}:{port}: {exc}"

    return info


def check_host_certs(
    host: str,
    ports: Optional[List[int]] = None,
    progress_cb=None,
) -> List[CertInfo]:
    """Check TLS certificates on all specified ports for a host."""
    _cb    = progress_cb or (lambda m: None)
    ports  = ports or [443, 8443]
    results: List[CertInfo] = []
    for port in ports:
        _cb(f"Checking TLS cert on {host}:{port}…")
        info = check_cert(host, port)
        if not info.error or info.verdict:
            results.append(info)
    return results
