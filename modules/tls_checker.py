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
    not_testable:        bool = False
    not_testable_reason: str  = ""


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
        ctx.verify_mode    = ssl.CERT_NONE   # we inspect manually — cert is evaluated in code below
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2  # lgtm[py/insecure-protocol] — TLS 1.2+ enforced; CERT_NONE is intentional for manual inspection  # still require TLS 1.2+
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()

        if not cert:
            info.not_testable = True
            info.not_testable_reason = (
                f"{host}:{port} completed a TLS handshake but presented no certificate to "
                "inspect, so this scan cannot confirm anything about its certificate."
            )
            info.error   = "No certificate returned"
            info.verdict = f"⚠ Could not test {host}:{port} — {info.not_testable_reason}"
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
    except (ConnectionRefusedError, OSError) as exc:
        # The host was never reached (refused, unreachable, timed out, or
        # unresolvable) -- distinct from ssl.SSLError above, which means the
        # host WAS reached and responded with a genuine TLS-level problem.
        info.error   = "Connection refused"
        info.not_testable = True
        info.not_testable_reason = (
            f"Could not connect to {host}:{port} — {exc}. The host may be offline, "
            "blocking this port, or unreachable from this network, so this scan "
            "cannot confirm anything about its TLS certificate."
        )
        info.verdict = f"⚠ Could not test {host}:{port} — {info.not_testable_reason}"
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
        # CertInfo-drop bug (Sprint 5b C): a not_testable result must never be
        # silently discarded, even on the rare path where verdict wasn't set.
        if not info.error or info.verdict or info.not_testable:
            results.append(info)
    return results
