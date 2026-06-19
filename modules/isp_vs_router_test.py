"""
modules/isp_vs_router_test.py — "Is this my ISP or my router?" quick test.

Runs a 5-hop ICMP ping chain to distinguish between a local network problem
and an ISP or external routing problem.

Hop sequence:
  1. Default gateway  — if unreachable, the router itself is at fault
  2. ISP DNS server   — if unreachable, the WAN link or ISP is at fault
  3. Google DNS       — 8.8.8.8; if unreachable, ISP is blocking external DNS
  4. Cloudflare DNS   — 1.1.1.1; confirms external internet reachability
  5. Public CDN       — 208.67.222.222 (OpenDNS); validates CDN-layer access

No PyQt imports.  Callable from workers/isp_vs_router_worker.py.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from typing import Optional

# ── Public hop targets ────────────────────────────────────────────────────────

_EXTERNAL_HOPS: list[tuple[str, str, str]] = [
    ("google_dns",    "8.8.8.8",         "Google DNS (8.8.8.8)"),
    ("cloudflare",    "1.1.1.1",         "Cloudflare (1.1.1.1)"),
    ("opendns",       "208.67.222.222",   "OpenDNS CDN (208.67.222.222)"),
]

_PING_TIMEOUT = 2.0  # seconds per hop

# ── Result dataclasses ────────────────────────────────────────────────────────


@dataclass
class HopResult:
    key: str
    label: str
    ip: str
    reachable: bool
    rtt_ms: Optional[float]


@dataclass
class IspVsRouterResult:
    hops: list[HopResult] = field(default_factory=list)
    verdict: str = ""
    plain_answer: str = ""
    category: str = "unknown"   # "local" | "isp" | "external" | "all_ok" | "unknown"
    elapsed_s: float = 0.0


# ── ICMP ping helper ──────────────────────────────────────────────────────────


def _ping_once(ip: str, timeout: float = _PING_TIMEOUT) -> Optional[float]:
    """Return round-trip time in ms, or None if unreachable / permission denied."""
    try:
        import platform
        import subprocess  # noqa: S404 — controlled invocation; no shell=True; no user input
        flag = "-n" if platform.system().lower() == "windows" else "-c"
        result = subprocess.run(  # noqa: S603 — no shell; fixed args only
            ["ping", flag, "1", "-W", "2", ip] if platform.system().lower() != "windows"
            else ["ping", flag, "1", "-w", "2000", ip],
            capture_output=True,
            text=True,
            timeout=timeout + 1,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            return None
        # Parse RTT from ping output (works on Windows and Linux/macOS)
        for token in output.split():
            t = token.strip("ms").replace("time=", "").replace("time<", "")
            try:
                return float(t)
            except ValueError:
                continue
        return None  # reachable but RTT not parseable
    except Exception:
        return None


def _tcp_probe(ip: str, port: int = 53, timeout: float = _PING_TIMEOUT) -> Optional[float]:
    """TCP connect probe as fallback when ICMP is blocked.  Returns RTT in ms."""
    try:
        t0 = time.monotonic()
        sock = socket.create_connection((ip, port), timeout=timeout)
        rtt = (time.monotonic() - t0) * 1000
        sock.close()
        return rtt
    except Exception:
        return None


def _check_hop(key: str, label: str, ip: str) -> HopResult:
    rtt = _ping_once(ip)
    if rtt is None:
        rtt = _tcp_probe(ip)
    reachable = rtt is not None
    return HopResult(key=key, label=label, ip=ip, reachable=reachable, rtt_ms=rtt)


# ── Verdict builder ───────────────────────────────────────────────────────────


def _build_verdict(hops: list[HopResult]) -> tuple[str, str, str]:
    """Return (category, verdict, plain_answer)."""
    by_key = {h.key: h for h in hops}

    router   = by_key.get("router")
    isp_dns  = by_key.get("isp_dns")
    ext1     = by_key.get("google_dns")
    ext2     = by_key.get("cloudflare")

    if router and not router.reachable:
        return (
            "local",
            "Local network — router unreachable",
            (
                "Your router is not responding. The problem is inside your home network. "
                "Try restarting your router and checking the cable between your device and the router."
            ),
        )

    if isp_dns and not isp_dns.reachable:
        if router and router.reachable:
            return (
                "isp",
                "WAN link — ISP connection fault",
                (
                    "Your router is fine, but the connection between your router and your ISP is down. "
                    "Your local network is working. Contact your ISP or power-cycle your modem."
                ),
            )

    if ext1 and not ext1.reachable and ext2 and not ext2.reachable:
        if (not isp_dns) or (isp_dns and isp_dns.reachable):
            return (
                "isp",
                "ISP connectivity — external internet unreachable",
                (
                    "Your ISP's server is reachable but you cannot reach external internet addresses. "
                    "Your ISP may be experiencing a routing problem. Power-cycle your modem "
                    "and contact your ISP if the problem persists."
                ),
            )

    if ext1 and ext1.reachable and ext2 and not ext2.reachable:
        return (
            "external",
            "Partial connectivity — some paths blocked",
            (
                "Most external internet is reachable but some destinations are not. "
                "This is typically a routing issue at your ISP or the remote server. "
                "Your local network is fine."
            ),
        )

    if all(h.reachable for h in hops if h is not None):
        best_rtt = min((h.rtt_ms for h in hops if h.rtt_ms is not None), default=None)
        rtt_note = f" (fastest hop: {best_rtt:.0f} ms)" if best_rtt else ""
        return (
            "all_ok",
            "All clear — internet connectivity healthy",
            (
                f"All network hops are responding{rtt_note}. "
                "Your internet connection appears healthy from this device. "
                "The problem is likely with the specific service or website you were trying to reach."
            ),
        )

    return (
        "unknown",
        "Inconclusive — mixed results",
        (
            "Some hops are not responding but the pattern is unclear. "
            "This can happen when intermediate routers block ICMP ping. "
            "Try running a speed test or Service Diagnostics for a clearer picture."
        ),
    )


# ── Public API ────────────────────────────────────────────────────────────────


def run_isp_vs_router_test(
    gateway_ip: Optional[str] = None,
    isp_dns_ip: Optional[str] = None,
    progress_cb=None,
) -> IspVsRouterResult:
    """
    Run the 5-hop ping chain.

    Parameters
    ----------
    gateway_ip  : default gateway IP; auto-detected via socket if None
    isp_dns_ip  : ISP DNS server IP from DHCP; skipped if None
    progress_cb : optional callable(step_label: str) for UI progress updates

    Returns
    -------
    IspVsRouterResult with hop detail and plain-English verdict
    """
    t0 = time.monotonic()
    hops: list[HopResult] = []

    def _emit(msg: str) -> None:
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass  # non-fatal — UI may have been closed

    # Hop 1: gateway
    gw = gateway_ip or _detect_gateway()
    if gw:
        _emit(f"Pinging your router ({gw})…")
        hops.append(_check_hop("router", f"Your router ({gw})", gw))
    else:
        hops.append(HopResult("router", "Your router (not detected)", "", False, None))

    # Hop 2: ISP DNS (optional)
    if isp_dns_ip:
        _emit(f"Pinging ISP DNS server ({isp_dns_ip})…")
        hops.append(_check_hop("isp_dns", f"ISP DNS ({isp_dns_ip})", isp_dns_ip))

    # Hops 3–5: external
    for key, ip, label in _EXTERNAL_HOPS:
        _emit(f"Pinging {label}…")
        hops.append(_check_hop(key, label, ip))

    category, verdict, plain_answer = _build_verdict(hops)
    return IspVsRouterResult(
        hops=hops,
        verdict=verdict,
        plain_answer=plain_answer,
        category=category,
        elapsed_s=time.monotonic() - t0,
    )


def _detect_gateway() -> Optional[str]:
    """Best-effort gateway detection via a UDP connect trick (no packets sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        # Assume gateway is .1 on the same /24
        parts = local_ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3]) + ".1"
    except Exception:
        pass  # non-fatal — caller may supply gateway_ip directly
    return None
