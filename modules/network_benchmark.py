"""
Network Benchmark — grades your home or small-office network against a
"Perfect Home Network" baseline and returns a letter grade (A–F) with
a plain-English explanation for each graded dimension.

Dimensions graded
─────────────────
  Uptime        — % of pings that succeeded (from LogSummary)
  Latency       — average RTT to gateway and public DNS
  Jitter        — response-time variability (video-call quality proxy)
  DNS Speed     — resolver round-trip time
  Download      — measured download throughput
  Rogue Devices — any HIGH-risk devices on the LAN
  STP Health    — presence of rogue Root Bridge BPDUs
  Storm Level   — broadcast/multicast flood rate

Each dimension is scored 0–100.  The overall grade is the weighted mean.

Thresholds are calibrated to what a well-configured home broadband
connection should achieve — NOT enterprise datacenter standards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ── Grade bands ────────────────────────────────────────────────────────────────

def _letter(score: float) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 65: return "C"
    if score >= 50: return "D"
    return "F"


def _score_to_color(score: float) -> str:
    """Return a hex colour string matching the score."""
    if score >= 80: return "#22c55e"   # green
    if score >= 60: return "#f59e0b"   # amber
    return "#ef4444"                   # red


# ── Dimension result ──────────────────────────────────────────────────────────

@dataclass
class DimensionResult:
    name: str
    score: float          # 0–100
    grade: str            # A–F
    color: str
    value_label: str      # e.g. "99.2 %" or "14 ms"
    ideal_label: str      # e.g. "≥ 99.5 %"
    verdict: str          # 1-sentence plain English
    tip: str              # actionable fix if grade < B


@dataclass
class BenchmarkResult:
    overall_score: float
    overall_grade: str
    overall_color: str
    overall_verdict: str
    dimensions: List[DimensionResult] = field(default_factory=list)


# ── Dimension scorers ─────────────────────────────────────────────────────────

def _score_uptime(uptime_pct: float) -> DimensionResult:
    # Perfect ≥ 99.5 %; failing below 95 %
    if uptime_pct >= 99.5:
        score = 100.0
    elif uptime_pct >= 98.0:
        score = 85.0
    elif uptime_pct >= 95.0:
        score = 65.0
    elif uptime_pct >= 90.0:
        score = 40.0
    else:
        score = 15.0
    grade = _letter(score)
    color = _score_to_color(score)
    return DimensionResult(
        name="Connection Uptime",
        score=score, grade=grade, color=color,
        value_label=f"{uptime_pct:.1f} %",
        ideal_label="≥ 99.5 %",
        verdict=(
            "Excellent — no meaningful packet loss." if score >= 90 else
            f"Acceptable — {100 - uptime_pct:.1f} % packet loss; occasional drops." if score >= 65 else
            f"Poor — {100 - uptime_pct:.1f} % packet loss is causing regular disconnections."
        ),
        tip=(
            "" if score >= 80 else
            "Check all Ethernet cables for damage. Restart your modem and router. "
            "If drops happen only on Wi-Fi, test with a wired connection to isolate the fault."
        ),
    )


def _score_latency(avg_rtt_ms: float) -> DimensionResult:
    # Ideal ≤ 20 ms for local; ≤ 50 ms for broadband
    if avg_rtt_ms <= 0:
        score = 0.0
        val = "No data"
    elif avg_rtt_ms <= 20:
        score = 100.0
        val = f"{avg_rtt_ms:.0f} ms"
    elif avg_rtt_ms <= 50:
        score = 85.0
        val = f"{avg_rtt_ms:.0f} ms"
    elif avg_rtt_ms <= 100:
        score = 65.0
        val = f"{avg_rtt_ms:.0f} ms"
    elif avg_rtt_ms <= 200:
        score = 40.0
        val = f"{avg_rtt_ms:.0f} ms"
    else:
        score = 15.0
        val = f"{avg_rtt_ms:.0f} ms"
    grade = _letter(score)
    return DimensionResult(
        name="Average Latency",
        score=score, grade=grade, color=_score_to_color(score),
        value_label=val,
        ideal_label="≤ 20 ms",
        verdict=(
            "Excellent latency — well within real-time application requirements." if score >= 90 else
            "Good latency for web browsing and streaming." if score >= 80 else
            "Moderate latency — may affect gaming and video calls." if score >= 50 else
            "High latency — likely to cause noticeable delays and poor call quality."
        ),
        tip=(
            "" if score >= 80 else
            "Connect via Ethernet instead of Wi-Fi. On Wi-Fi, move closer to the router "
            "or switch to the 5 GHz band. High latency to 8.8.8.8 at off-peak hours may indicate ISP congestion."
        ),
    )


def _score_jitter(jitter_ms: float) -> DimensionResult:
    # Perfect ≤ 5 ms; failing > 30 ms
    if jitter_ms <= 0:
        score = 0.0
        val = "No data"
    elif jitter_ms <= 5:
        score = 100.0
        val = f"{jitter_ms:.1f} ms"
    elif jitter_ms <= 15:
        score = 85.0
        val = f"{jitter_ms:.1f} ms"
    elif jitter_ms <= 30:
        score = 60.0
        val = f"{jitter_ms:.1f} ms"
    else:
        score = 25.0
        val = f"{jitter_ms:.1f} ms"
    grade = _letter(score)
    return DimensionResult(
        name="Jitter (Call Quality)",
        score=score, grade=grade, color=_score_to_color(score),
        value_label=val,
        ideal_label="≤ 5 ms",
        verdict=(
            "Rock-solid — video and voice calls will be clear." if score >= 90 else
            "Acceptable — minor instability; most calls will be fine." if score >= 70 else
            "Noticeable — video calls may stutter or freeze occasionally." if score >= 40 else
            "Severe — jitter this high will cause consistent call quality problems."
        ),
        tip=(
            "" if score >= 80 else
            "Enable QoS (Quality of Service) in your router settings to prioritise call traffic. "
            "Use a wired connection for video calls. Check for other devices running heavy downloads."
        ),
    )


def _score_dns(avg_dns_ms: float) -> DimensionResult:
    # Perfect ≤ 30 ms; failing > 200 ms
    if avg_dns_ms <= 0:
        return DimensionResult(
            name="DNS Response Speed", score=0, grade="F",
            color="#ef4444", value_label="Failed",
            ideal_label="≤ 30 ms",
            verdict="DNS resolution failed — websites will not load even if connectivity works.",
            tip="Set DNS to 1.1.1.1 (Cloudflare) or 8.8.8.8 (Google) in your router or adapter settings.",
        )
    if avg_dns_ms <= 30:
        score = 100.0
    elif avg_dns_ms <= 80:
        score = 85.0
    elif avg_dns_ms <= 150:
        score = 65.0
    else:
        score = 30.0
    grade = _letter(score)
    return DimensionResult(
        name="DNS Response Speed",
        score=score, grade=grade, color=_score_to_color(score),
        value_label=f"{avg_dns_ms:.0f} ms",
        ideal_label="≤ 30 ms",
        verdict=(
            "Fast DNS — websites will load quickly." if score >= 90 else
            "Acceptable DNS speed." if score >= 65 else
            f"Slow DNS ({avg_dns_ms:.0f} ms) — every website visit is delayed waiting for name resolution."
        ),
        tip=(
            "" if score >= 80 else
            "Switch to a faster DNS resolver: 1.1.1.1 (Cloudflare) for speed, "
            "9.9.9.9 (Quad9) for privacy. Set it on your router so all devices benefit."
        ),
    )


def _score_download(mbps: float) -> DimensionResult:
    # Graded relative to what streaming/calls need, not ISP plan speed
    if mbps <= 0:
        return DimensionResult(
            name="Download Speed", score=0, grade="F",
            color="#ef4444", value_label="Not measured",
            ideal_label="≥ 25 Mbps",
            verdict="Download speed not measured this session.",
            tip="Run the Health Check to measure download speed.",
        )
    if mbps >= 100:
        score = 100.0
    elif mbps >= 50:
        score = 92.0
    elif mbps >= 25:
        score = 80.0
    elif mbps >= 10:
        score = 65.0
    elif mbps >= 5:
        score = 40.0
    else:
        score = 15.0
    grade = _letter(score)
    return DimensionResult(
        name="Download Speed",
        score=score, grade=grade, color=_score_to_color(score),
        value_label=f"{mbps:.1f} Mbps",
        ideal_label="≥ 25 Mbps",
        verdict=(
            "Excellent — plenty of headroom for 4K streaming and multiple users." if score >= 90 else
            "Good — supports HD streaming and video calls." if score >= 70 else
            f"Limited at {mbps:.1f} Mbps — HD streaming and calls may buffer." if score >= 40 else
            f"Very slow at {mbps:.1f} Mbps — barely sufficient for basic browsing."
        ),
        tip=(
            "" if score >= 70 else
            "Test with a wired connection to separate Wi-Fi from broadband speed. "
            "Run a speed test at speedtest.net to compare. If wired is also slow, contact your ISP."
        ),
    )


def _score_rogue_devices(high_risk_count: int) -> DimensionResult:
    score = 100.0 if high_risk_count == 0 else max(0.0, 100.0 - high_risk_count * 25)
    grade = _letter(score)
    return DimensionResult(
        name="Network Device Safety",
        score=score, grade=grade, color=_score_to_color(score),
        value_label=f"{high_risk_count} high-risk device(s)",
        ideal_label="0 high-risk devices",
        verdict=(
            "No high-risk devices detected on your network." if high_risk_count == 0 else
            f"{high_risk_count} device(s) with known network-disruption issues found. "
            "See Devices on Network tab for details."
        ),
        tip=(
            "" if high_risk_count == 0 else
            "Review the flagged devices in the 'Devices on Network' tab. "
            "Disconnect any device you do not recognise or do not need connected via Ethernet."
        ),
    )


def _score_stp(rogue_bpdus: int) -> DimensionResult:
    score = 100.0 if rogue_bpdus == 0 else 20.0
    grade = _letter(score)
    return DimensionResult(
        name="Spanning Tree (STP) Health",
        score=score, grade=grade, color=_score_to_color(score),
        value_label=f"{rogue_bpdus} rogue BPDU source(s)",
        ideal_label="0 rogue bridges",
        verdict=(
            "STP topology is healthy — no rogue Root Bridges detected." if rogue_bpdus == 0 else
            f"{rogue_bpdus} device(s) injecting rogue STP BPDUs. This causes periodic 15–45 s outage cycles."
        ),
        tip=(
            "" if rogue_bpdus == 0 else
            "Disconnect the Ethernet cable from the flagged device (see Rogue Bridge tab). "
            "Mesh nodes should use Wi-Fi backhaul only."
        ),
    )


def _score_storm(storm_level: str, bcast_pps: float) -> DimensionResult:
    if storm_level == "CLEAN":
        score = 100.0
    elif storm_level == "WARNING":
        score = 55.0
    else:  # STORM
        score = 10.0
    grade = _letter(score)
    return DimensionResult(
        name="Broadcast Storm Level",
        score=score, grade=grade, color=_score_to_color(score),
        value_label=f"{bcast_pps:.0f} broadcast pkt/s" if bcast_pps > 0 else storm_level,
        ideal_label="< 50 pkt/s (CLEAN)",
        verdict=(
            "Broadcast traffic is at a healthy level." if score >= 90 else
            f"Elevated broadcast rate ({bcast_pps:.0f} pkt/s) — performance may be affected." if score >= 40 else
            f"Broadcast storm detected ({bcast_pps:.0f} pkt/s) — network is severely congested."
        ),
        tip=(
            "" if score >= 80 else
            "Find the top broadcast source in the Storm Analyser tab. "
            "Restart it, check for firmware updates, or move it to a separate network segment."
        ),
    )


# ── Weights ────────────────────────────────────────────────────────────────────
# Higher weight = more impact on the overall grade
_WEIGHTS = {
    "Connection Uptime":        0.25,
    "Average Latency":          0.15,
    "Jitter (Call Quality)":    0.15,
    "DNS Response Speed":        0.10,
    "Download Speed":            0.10,
    "Network Device Safety":    0.10,
    "Spanning Tree (STP) Health": 0.10,
    "Broadcast Storm Level":    0.05,
}


# ── Public API ─────────────────────────────────────────────────────────────────

def grade(
    log_summary=None,
    diag_result=None,
    m1_result: Optional[dict] = None,
    m2_result: Optional[dict] = None,
    m3_result=None,
) -> BenchmarkResult:
    """
    Grade the network across all available dimensions.

    Parameters (all optional — dimensions with no data score 0 and are noted)
    ─────────────────────────────────────────────────────────────────────────
    log_summary  : LogSummary from network_logger
    diag_result  : DiagnosticsResult from network_diagnostics
    m1_result    : dict from rogue_device.scan()   {"high_risk_count": int, ...}
    m2_result    : dict from stp_detector.scan()   {"bpdus": [...], ...}
    m3_result    : StormResult from storm_analyser.scan()
    """
    dims: List[DimensionResult] = []

    # ── Uptime / latency / jitter / DNS from logger ───────────────────────────
    uptime   = getattr(log_summary, "uptime_pct",   -1.0) if log_summary else -1.0
    avg_rtt  = getattr(log_summary, "avg_rtt_ms",   -1.0) if log_summary else -1.0
    avg_jit  = getattr(log_summary, "avg_jitter_ms",-1.0) if log_summary else -1.0
    avg_dns  = getattr(log_summary, "avg_dns_ms",   -1.0) if log_summary else -1.0

    # Fallback: latency/dns from diagnostics if logger hasn't run long enough
    if avg_rtt <= 0 and diag_result:
        pings = getattr(diag_result, "ping_results", [])
        good = [getattr(p, "rtt_ms", -1) for p in pings if getattr(p, "rtt_ms", -1) > 0]
        avg_rtt = sum(good) / len(good) if good else -1.0
    if avg_dns <= 0 and diag_result:
        dns_res = getattr(diag_result, "dns_results", [])
        good_dns = [getattr(d, "latency_ms", -1) for d in dns_res if getattr(d, "latency_ms", -1) > 0]
        avg_dns = sum(good_dns) / len(good_dns) if good_dns else -1.0

    dl_mbps = getattr(diag_result, "download_mbps", -1.0) if diag_result else -1.0

    if uptime >= 0:
        dims.append(_score_uptime(uptime))
    if avg_rtt > 0:
        dims.append(_score_latency(avg_rtt))
    if avg_jit > 0:
        dims.append(_score_jitter(avg_jit))
    if avg_dns > 0:
        dims.append(_score_dns(avg_dns))
    if dl_mbps > 0:
        dims.append(_score_download(dl_mbps))

    # ── Device safety from M1 ─────────────────────────────────────────────────
    if m1_result is not None:
        high_risk = m1_result.get("high_risk_count", 0)
        dims.append(_score_rogue_devices(high_risk))

    # ── STP health from M2 ────────────────────────────────────────────────────
    if m2_result is not None:
        bpdus = m2_result.get("bpdus", [])
        rogue = sum(1 for b in bpdus if getattr(b, "is_rogue", False))
        dims.append(_score_stp(rogue))

    # ── Storm from M3 ─────────────────────────────────────────────────────────
    if m3_result is not None:
        storm_level = getattr(m3_result, "storm_level", "CLEAN")
        bcast_pps   = getattr(m3_result, "bcast_per_sec", 0.0)
        dims.append(_score_storm(storm_level, bcast_pps))

    if not dims:
        return BenchmarkResult(
            overall_score=0, overall_grade="N/A",
            overall_color="#888",
            overall_verdict="No scan data available — run at least one scan first.",
        )

    # ── Weighted overall score ────────────────────────────────────────────────
    total_weight  = sum(_WEIGHTS.get(d.name, 0.05) for d in dims)
    weighted_sum  = sum(d.score * _WEIGHTS.get(d.name, 0.05) for d in dims)
    overall_score = weighted_sum / total_weight if total_weight > 0 else 0

    grade_letter = _letter(overall_score)
    color        = _score_to_color(overall_score)

    if grade_letter == "A":
        verdict = (
            "Your network is performing excellently across all measured dimensions. "
            "No action required."
        )
    elif grade_letter == "B":
        worst = min(dims, key=lambda d: d.score)
        verdict = (
            f"Good network health. Minor improvement possible: {worst.name} "
            f"scored {worst.grade} — {worst.verdict}"
        )
    elif grade_letter == "C":
        worst = min(dims, key=lambda d: d.score)
        verdict = (
            f"Average performance. Your {worst.name} is the weakest point "
            f"({worst.value_label}). {worst.tip}"
        )
    else:
        failing = [d for d in dims if d.grade in ("D", "F")]
        names   = ", ".join(d.name for d in failing[:3])
        verdict = (
            f"Network needs attention. Critical issues: {names}. "
            "See individual grades below for fix steps."
        )

    return BenchmarkResult(
        overall_score=round(overall_score, 1),
        overall_grade=grade_letter,
        overall_color=color,
        overall_verdict=verdict,
        dimensions=dims,
    )
