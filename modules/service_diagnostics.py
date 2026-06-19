"""
Service Connectivity Diagnostics — Sprint 3.

Determines whether a connectivity problem originates from:
  device | local_network | dns | isp | routing | remote_outage

Usage:
    from modules.service_diagnostics import DiagnosticEngine, SERVICE_CATALOG

    engine = DiagnosticEngine()
    result = engine.run("netflix")          # single service
    batch  = engine.run_batch(["steam", "psn"])  # multiple in parallel
"""
from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from modules.service_diagnostics_probes import (
    DnsProbeResult,
    HttpsProbeResult,
    IcmpProbeResult,
    TcpProbeResult,
    TracerouteResult,
    dns_probe,
    https_probe,
    icmp_probe,
    tcp_probe,
    traceroute_probe,
)


# ── Service catalog ───────────────────────────────────────────────────────────

@dataclass
class ServiceEntry:
    id: str
    name: str
    category: str           # "streaming" | "gaming"
    probe_hosts: List[str]  # hostnames for DNS + latency probes
    tcp_ports: List[int]    # ports for TCP connectivity check (primary host)
    https_urls: List[str]   # full HTTPS URLs for reachability check


_STREAMING: List[ServiceEntry] = [
    ServiceEntry(
        id="netflix", name="Netflix", category="streaming",
        probe_hosts=["www.netflix.com", "api.netflix.com"],
        tcp_ports=[443],
        https_urls=["https://www.netflix.com"],
    ),
    ServiceEntry(
        id="hbomax", name="Max (HBO Max)", category="streaming",
        probe_hosts=["www.max.com"],
        tcp_ports=[443],
        https_urls=["https://www.max.com"],
    ),
    ServiceEntry(
        id="disneyplus", name="Disney+", category="streaming",
        probe_hosts=["www.disneyplus.com"],
        tcp_ports=[443],
        https_urls=["https://www.disneyplus.com"],
    ),
    ServiceEntry(
        id="appletv", name="Apple TV+", category="streaming",
        probe_hosts=["tv.apple.com"],
        tcp_ports=[443],
        https_urls=["https://tv.apple.com"],
    ),
    ServiceEntry(
        id="primevideo", name="Prime Video", category="streaming",
        probe_hosts=["www.primevideo.com"],
        tcp_ports=[443],
        https_urls=["https://www.primevideo.com"],
    ),
    ServiceEntry(
        id="youtube", name="YouTube", category="streaming",
        probe_hosts=["www.youtube.com"],
        tcp_ports=[443, 80],
        https_urls=["https://www.youtube.com"],
    ),
    ServiceEntry(
        id="spotify", name="Spotify", category="streaming",
        probe_hosts=["open.spotify.com"],
        tcp_ports=[443],
        https_urls=["https://open.spotify.com"],
    ),
    ServiceEntry(
        id="twitch", name="Twitch", category="streaming",
        probe_hosts=["www.twitch.tv"],
        tcp_ports=[443],
        https_urls=["https://www.twitch.tv"],
    ),
]

_GAMING: List[ServiceEntry] = [
    ServiceEntry(
        id="steam", name="Steam", category="gaming",
        probe_hosts=["store.steampowered.com", "api.steampowered.com"],
        tcp_ports=[443],
        https_urls=["https://store.steampowered.com"],
    ),
    ServiceEntry(
        id="epicgames", name="Epic Games", category="gaming",
        probe_hosts=["www.epicgames.com"],
        tcp_ports=[443],
        https_urls=["https://www.epicgames.com"],
    ),
    ServiceEntry(
        id="fortnite", name="Fortnite", category="gaming",
        probe_hosts=["www.epicgames.com"],
        tcp_ports=[443],
        https_urls=["https://www.epicgames.com/fortnite/en-US/home"],
    ),
    ServiceEntry(
        id="xboxlive", name="Xbox Live", category="gaming",
        probe_hosts=["login.live.com", "xsts.auth.xboxlive.com"],
        tcp_ports=[443],
        https_urls=["https://login.live.com"],
    ),
    ServiceEntry(
        id="psn", name="PlayStation Network", category="gaming",
        probe_hosts=["status.playstation.com", "auth.api.sonyentertainmentnetwork.com"],
        tcp_ports=[443, 80],
        https_urls=["https://status.playstation.com"],
    ),
    ServiceEntry(
        id="nintendo", name="Nintendo Online", category="gaming",
        probe_hosts=["eshop.nintendo.net", "accounts.nintendo.com"],
        tcp_ports=[443],
        https_urls=["https://accounts.nintendo.com"],
    ),
    ServiceEntry(
        id="riot", name="Riot Games", category="gaming",
        probe_hosts=["auth.riotgames.com"],
        tcp_ports=[443],
        https_urls=["https://auth.riotgames.com"],
    ),
    ServiceEntry(
        id="ea", name="EA", category="gaming",
        probe_hosts=["www.ea.com", "api.ea.com"],
        tcp_ports=[443],
        https_urls=["https://www.ea.com"],
    ),
    ServiceEntry(
        id="ubisoft", name="Ubisoft", category="gaming",
        probe_hosts=["www.ubisoft.com"],
        tcp_ports=[443],
        https_urls=["https://www.ubisoft.com"],
    ),
    ServiceEntry(
        id="battlenet", name="Battle.net", category="gaming",
        probe_hosts=["battle.net", "us.battle.net"],
        tcp_ports=[443, 1119],
        https_urls=["https://us.battle.net"],
    ),
]

SERVICE_CATALOG: Dict[str, ServiceEntry] = {
    s.id: s for s in _STREAMING + _GAMING
}


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class LayerResult:
    passed: bool = True
    detail: str = ""


@dataclass
class ServiceDiagnosticResult:
    service_id: str
    service_name: str
    ts: int = field(default_factory=lambda: int(time.time()))

    dns: LayerResult = field(default_factory=LayerResult)
    reachability: LayerResult = field(default_factory=LayerResult)
    latency: LayerResult = field(default_factory=LayerResult)
    path: LayerResult = field(default_factory=LayerResult)

    dns_probes: List[DnsProbeResult] = field(default_factory=list)
    tcp_probes: List[TcpProbeResult] = field(default_factory=list)
    https_probes: List[HttpsProbeResult] = field(default_factory=list)
    icmp_result: Optional[IcmpProbeResult] = None
    trace: Optional[TracerouteResult] = None

    # device | local_network | dns | isp | routing | remote_outage | none
    failure_layer: str = "none"
    summary: str = ""
    confidence: int = 0    # 0–100


@dataclass
class BatchDiagnosticResult:
    results: List[ServiceDiagnosticResult] = field(default_factory=list)
    cross_summary: str = ""
    dns_failure_count: int = 0
    reachability_failure_count: int = 0
    total: int = 0


# ── Latency thresholds ────────────────────────────────────────────────────────

_RTT_WARN_MS = 200.0      # avg RTT above this → latency warning
_LOSS_WARN_PCT = 5.0      # packet loss above this → loss warning
_DNS_SLOW_MS = 500.0      # DNS RTT above this → DNS warning

# Reference hosts used to separate service-specific failures from systemic ones
_REFERENCE_HOSTS = ["1.1.1.1", "8.8.8.8"]


# ── Diagnostic engine ─────────────────────────────────────────────────────────

class DiagnosticEngine:
    """
    Orchestrates multi-layer probes for a service and classifies the failure layer.
    Thread-safe: each run() call creates independent probe objects.
    """

    def run(
        self, service_id: str, *, traceroute: bool = False
    ) -> ServiceDiagnosticResult:
        """
        Run full diagnostics for a single service.
        traceroute=True adds path analysis (adds ~30 s to runtime).
        """
        entry = SERVICE_CATALOG.get(service_id)
        if not entry:
            result = ServiceDiagnosticResult(
                service_id=service_id,
                service_name=service_id,
            )
            result.failure_layer = "none"
            result.summary = f"Unknown service ID '{service_id}'."
            result.confidence = 100
            return result

        result = ServiceDiagnosticResult(
            service_id=service_id,
            service_name=entry.name,
        )

        # 1 — DNS probes for all probe hosts
        for host in entry.probe_hosts:
            result.dns_probes.append(dns_probe(host))

        # 2 — TCP probes on primary host
        primary = entry.probe_hosts[0]
        for port in entry.tcp_ports:
            result.tcp_probes.append(tcp_probe(primary, port))

        # 3 — HTTPS reachability probes
        for url in entry.https_urls:
            result.https_probes.append(https_probe(url))

        # 4 — ICMP latency / packet-loss
        result.icmp_result = icmp_probe(primary, count=4)

        # 5 — Reference connectivity (distinguishes service outage from local failure)
        ref_results = [tcp_probe(h, 80) for h in _REFERENCE_HOSTS]
        ref_reachable = any(r.up for r in ref_results)

        # 6 — Optional path analysis
        if traceroute:
            result.trace = traceroute_probe(primary)

        _classify(result, ref_reachable)
        return result

    def run_batch(
        self,
        service_ids: List[str],
        *,
        traceroute: bool = False,
        max_workers: int = 4,
    ) -> BatchDiagnosticResult:
        """Run diagnostics for multiple services concurrently."""
        batch = BatchDiagnosticResult(total=len(service_ids))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self.run, sid, traceroute=traceroute): sid
                for sid in service_ids
            }
            for fut in concurrent.futures.as_completed(futures):
                try:
                    batch.results.append(fut.result())
                except Exception as exc:
                    sid = futures[fut]
                    entry = SERVICE_CATALOG.get(sid)
                    name = entry.name if entry else sid
                    err_result = ServiceDiagnosticResult(
                        service_id=sid,
                        service_name=name,
                        failure_layer="none",
                        summary=f"Diagnostic failed: {exc}",
                        confidence=0,
                    )
                    batch.results.append(err_result)

        batch.dns_failure_count = sum(
            1 for r in batch.results if not r.dns.passed
        )
        batch.reachability_failure_count = sum(
            1 for r in batch.results if not r.reachability.passed
        )
        batch.cross_summary = _cross_diagnose(batch)
        return batch


# ── Per-service classification ────────────────────────────────────────────────

def _classify(result: ServiceDiagnosticResult, ref_reachable: bool) -> None:
    """Populate layer results, failure_layer, summary, and confidence."""
    dns_ok = any(p.ipv4 for p in result.dns_probes)
    tcp_ok = any(p.up for p in result.tcp_probes)
    https_ok = any(p.up for p in result.https_probes)
    reachable = tcp_ok or https_ok
    icmp = result.icmp_result

    # DNS layer
    if not dns_ok:
        result.dns = LayerResult(passed=False, detail="DNS resolution failed for all probe hosts")
    else:
        rtts = [p.rtt_ms for p in result.dns_probes if p.rtt_ms > 0]
        avg_dns = sum(rtts) / len(rtts) if rtts else -1.0
        if avg_dns > _DNS_SLOW_MS:
            result.dns = LayerResult(
                passed=False, detail=f"DNS slow ({avg_dns:.0f} ms)"
            )
        else:
            detail = f"DNS OK ({avg_dns:.0f} ms)" if avg_dns > 0 else "DNS resolved"
            result.dns = LayerResult(passed=True, detail=detail)

    # Reachability layer
    result.reachability = LayerResult(
        passed=reachable,
        detail="TCP/HTTPS connectivity confirmed" if reachable
        else "No TCP or HTTPS connections succeeded",
    )

    # Latency layer
    if icmp and icmp.avg_ms > 0:
        if icmp.loss_pct >= _LOSS_WARN_PCT:
            result.latency = LayerResult(
                passed=False,
                detail=f"{icmp.loss_pct:.0f}% packet loss, avg {icmp.avg_ms:.0f} ms",
            )
        elif icmp.avg_ms > _RTT_WARN_MS:
            result.latency = LayerResult(
                passed=False,
                detail=f"High latency: avg {icmp.avg_ms:.0f} ms",
            )
        else:
            result.latency = LayerResult(
                passed=True,
                detail=f"Latency OK: {icmp.avg_ms:.0f} ms avg, {icmp.loss_pct:.0f}% loss",
            )
    else:
        result.latency = LayerResult(
            passed=False,
            detail="ICMP unreachable (host may block ping)",
        )

    # Path layer
    if result.trace:
        if result.trace.anomalies:
            result.path = LayerResult(
                passed=False, detail="; ".join(result.trace.anomalies)
            )
        else:
            result.path = LayerResult(
                passed=True,
                detail=f"{result.trace.hop_count} hops, reached={result.trace.reached}",
            )

    _assign_layer(result, ref_reachable)


def _assign_layer(result: ServiceDiagnosticResult, ref_reachable: bool) -> None:
    """Determine root cause layer and write the plain-English diagnosis summary."""
    name = result.service_name
    icmp = result.icmp_result

    # All layers healthy
    if result.dns.passed and result.reachability.passed and result.latency.passed:
        result.failure_layer = "none"
        result.summary = f"{name} is reachable and responding normally."
        result.confidence = 90
        return

    # DNS failure
    if not result.dns.passed:
        if ref_reachable:
            result.failure_layer = "dns"
            result.summary = (
                f"DNS resolution failed for {name}. "
                "Reference hosts are reachable, suggesting a DNS issue specific to this "
                "service or a partial DNS outage. "
                "Try flushing your DNS cache or switching to 8.8.8.8."
            )
            result.confidence = 75
        else:
            result.failure_layer = "dns"
            result.summary = (
                f"DNS resolution failed for {name} and reference hosts. "
                "Local DNS configuration issue likely — check your router's DNS settings."
            )
            result.confidence = 85
        return

    # DNS resolved but service unreachable
    if not result.reachability.passed:
        if not ref_reachable:
            if icmp and icmp.loss_pct >= 99.0:
                result.failure_layer = "local_network"
                result.summary = (
                    f"{name} is unreachable and reference hosts do not respond. "
                    "Complete packet loss suggests a local network or device problem — "
                    "check your router and network adapter."
                )
                result.confidence = 80
            else:
                result.failure_layer = "isp"
                result.summary = (
                    f"{name} is unreachable and reference hosts also fail. "
                    "ISP-level outage or upstream routing problem likely."
                )
                result.confidence = 70
        elif result.trace and not result.path.passed:
            result.failure_layer = "routing"
            result.summary = (
                f"DNS resolution succeeded but {name} connectivity failed. "
                f"Path analysis found anomalies: {result.path.detail}. "
                "Likely a routing issue between your ISP and the service."
            )
            result.confidence = 70
        else:
            result.failure_layer = "remote_outage"
            result.summary = (
                f"DNS resolution succeeded but {name} connectivity failed. "
                "Other services remain reachable. "
                f"Likely a {name} outage or regional routing issue."
            )
            result.confidence = 75
        return

    # Reachable but degraded latency
    if not result.latency.passed and icmp:
        if icmp.avg_ms > 0 and icmp.loss_pct >= _LOSS_WARN_PCT:
            result.failure_layer = "isp"
            result.summary = (
                f"{name} is reachable but experiencing {icmp.loss_pct:.0f}% packet loss. "
                "ISP congestion or degraded uplink likely."
            )
            result.confidence = 65
        elif icmp.avg_ms > _RTT_WARN_MS:
            result.failure_layer = "routing"
            result.summary = (
                f"{name} is reachable but latency is high ({icmp.avg_ms:.0f} ms). "
                "A congested or suboptimal routing path is likely."
            )
            result.confidence = 60
        else:
            result.failure_layer = "none"
            result.summary = f"{name}: ICMP unreachable (host may block ping); TCP/HTTPS OK."
            result.confidence = 50
        return

    result.failure_layer = "none"
    result.summary = f"{name}: diagnostics complete with no critical failures detected."
    result.confidence = 50


# ── Cross-service analysis ────────────────────────────────────────────────────

def _cross_diagnose(batch: BatchDiagnosticResult) -> str:
    """Generate a plain-English summary across all services in a batch run."""
    results = batch.results
    total = len(results)
    if total == 0:
        return "No services tested."

    failed = [r for r in results if r.failure_layer != "none"]
    if not failed:
        return f"All {total} services are reachable and responding normally."

    dns_failed = [r for r in results if not r.dns.passed]
    local_failed = [r for r in results if r.failure_layer == "local_network"]
    isp_failed = [r for r in results if r.failure_layer == "isp"]
    remote_failed = [r for r in results if r.failure_layer == "remote_outage"]

    if len(dns_failed) == total:
        return (
            "Multiple services fail DNS resolution. "
            "Local DNS configuration issue likely — check router DNS settings."
        )

    if len(local_failed) >= total // 2 + 1:
        return (
            f"{len(local_failed)} of {total} services unreachable with complete packet loss. "
            "Local network or device problem likely."
        )

    if len(isp_failed) >= total // 2 + 1:
        return (
            f"{len(isp_failed)} of {total} services show ISP-level degradation. "
            "Contact your ISP or check for a known outage."
        )

    if len(remote_failed) == 1:
        svc = remote_failed[0].service_name
        return (
            f"DNS resolution succeeded but {svc} connectivity failed. "
            f"Other services remain reachable. Likely {svc} outage or regional routing issue."
        )

    names = ", ".join(r.service_name for r in failed[:3])
    suffix = f" and {len(failed) - 3} more" if len(failed) > 3 else ""
    return (
        f"{len(failed)} of {total} services report problems ({names}{suffix}). "
        "See individual diagnostics for details."
    )
