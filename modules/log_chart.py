"""
Logger RTT Chart — renders a NetSentinel CSV log as a publication-quality
matplotlib figure without opening the GUI.

Layout:
  Top subplot  — RTT (ms) per target, line per host.
                 Outages (FAIL periods) shaded red.
                 Slow periods (SLOW status) shaded amber.
                 DNS latency on a secondary y-axis if dns_ms column present.
  Bottom subplot — Per-target uptime % bar chart.

Usage:
    from modules.log_chart import render_chart
    from modules.network_logger import load_log_file

    summary = load_log_file(Path("netlog_20260426_120000.csv"))
    out_path = render_chart(summary)                   # saves PNG next to CSV
    render_chart(summary, show=True)                   # interactive window
    render_chart(summary, output_path=Path("out.png")) # explicit path
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Optional, List

# matplotlib is imported lazily so this module can be imported without a display
# (the actual render will fail gracefully if matplotlib is missing).


def render_chart(
    summary,
    output_path: Optional[Path] = None,
    show: bool = False,
) -> Path:
    """
    Render a log summary to a PNG chart (and optionally display it).

    Args:
        summary:     A LogSummary returned by load_log_file() or get_summary().
        output_path: Explicit PNG output path.  If None, saves to the same
                     directory as the log file with .png extension.
        show:        If True, also calls plt.show() for an interactive window.

    Returns:
        Path of the saved PNG file.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")   # non-interactive backend; reset to TkAgg etc. if show=True
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import matplotlib.patches as mpatches
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required for chart rendering: pip install matplotlib"
        ) from exc

    entries   = summary.entries
    outages   = summary.outages
    log_path  = Path(summary.log_path) if summary.log_path else Path("netlog.csv")

    if not entries:
        raise ValueError("No log entries to chart — load a non-empty log file first.")

    # ── Parse timestamps ──────────────────────────────────────────────────────
    _FMT = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f")

    def _parse_ts(s: str) -> Optional[_dt.datetime]:
        for fmt in _FMT:
            try:
                return _dt.datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    # Build per-host time-series
    hosts = sorted(set(e.host for e in entries))
    host_series: dict = {h: {"ts": [], "rtt": [], "dns": []} for h in hosts}

    for e in entries:
        ts = _parse_ts(e.timestamp)
        if ts is None:
            continue
        rtt = e.rtt_ms if e.rtt_ms >= 0 else float("nan")
        dns = e.dns_ms  if e.dns_ms  >= 0 else float("nan")
        host_series[e.host]["ts"].append(ts)
        host_series[e.host]["rtt"].append(rtt)
        host_series[e.host]["dns"].append(dns)

    # Check whether we have any DNS data worth plotting
    has_dns = any(
        any(not _is_nan(v) for v in host_series[h]["dns"])
        for h in hosts
    )

    # ── Outage / slow time-window boundaries ──────────────────────────────────
    # Build per-host fail/slow spans from entries
    fail_spans: List[tuple] = []   # (start_dt, end_dt)
    slow_spans: List[tuple] = []

    for h in hosts:
        ts_list  = host_series[h]["ts"]
        if not ts_list:
            continue
        host_entries = [e for e in entries if e.host == h]
        # Estimate the interval between consecutive entries for duration calc
        if len(ts_list) > 1:
            gaps = [(ts_list[i+1] - ts_list[i]).total_seconds()
                    for i in range(len(ts_list) - 1)]
            interval = max(1.0, sum(gaps) / len(gaps))
        else:
            interval = 60.0
        half = _dt.timedelta(seconds=interval / 2)

        for e, ts in zip(host_entries, ts_list):
            if e.status == "FAIL":
                fail_spans.append((ts - half, ts + half))
            elif e.status == "SLOW":
                slow_spans.append((ts - half, ts + half))

    # ── Uptime per host ───────────────────────────────────────────────────────
    host_uptime: dict = {}
    for h in hosts:
        h_entries = [e for e in entries if e.host == h]
        n = len(h_entries)
        ok = sum(1 for e in h_entries if e.status != "FAIL")
        host_uptime[h] = (ok / n * 100) if n else 100.0

    # ── Figure layout ─────────────────────────────────────────────────────────
    if show:
        matplotlib.use("TkAgg" if _backend_available("TkAgg") else "Qt5Agg")
        import matplotlib.pyplot as plt  # re-import after backend change

    DARK_BG   = "#0d0d1a"
    CARD_BG   = "#13132a"
    TEXT_CLR  = "#e0e0ff"
    GRID_CLR  = "#2a2a4a"
    RED_CLR   = "#ff3366"
    AMBER_CLR = "#ffaa00"
    ACCENT    = "#00c8ff"

    COLORS = [ACCENT, "#a78bfa", "#34d399", "#fb923c",
              "#f472b6", "#facc15", "#60a5fa", "#4ade80"]

    fig, (ax_rtt, ax_bar) = plt.subplots(
        2, 1,
        figsize=(14, 8),
        gridspec_kw={"height_ratios": [3, 1]},
        facecolor=DARK_BG,
    )
    fig.subplots_adjust(hspace=0.35, left=0.08, right=0.95, top=0.92, bottom=0.08)

    for ax in (ax_rtt, ax_bar):
        ax.set_facecolor(CARD_BG)
        ax.tick_params(colors=TEXT_CLR, labelsize=9)
        for spine in ax.spines.values():
            spine.set_edgecolor(GRID_CLR)

    # ── Top subplot: RTT lines ────────────────────────────────────────────────
    ax_rtt.set_title("Network Logger — RTT Chart", color=TEXT_CLR, fontsize=13, pad=12)
    ax_rtt.set_ylabel("RTT (ms)", color=TEXT_CLR, fontsize=10)
    ax_rtt.grid(True, color=GRID_CLR, linewidth=0.5, alpha=0.7)

    legend_handles = []
    for i, h in enumerate(hosts):
        color = COLORS[i % len(COLORS)]
        ts_list  = host_series[h]["ts"]
        rtt_list = host_series[h]["rtt"]
        if not ts_list:
            continue
        line, = ax_rtt.plot(ts_list, rtt_list, linewidth=1.2, color=color,
                            label=h, alpha=0.9)
        legend_handles.append(line)

    # Shade outages (red) and slow periods (amber)
    for start, end in fail_spans:
        ax_rtt.axvspan(start, end, alpha=0.25, color=RED_CLR, linewidth=0)
    for start, end in slow_spans:
        ax_rtt.axvspan(start, end, alpha=0.18, color=AMBER_CLR, linewidth=0)

    # Legend patches for shading
    legend_handles.append(mpatches.Patch(color=RED_CLR,   alpha=0.5, label="Outage (FAIL)"))
    legend_handles.append(mpatches.Patch(color=AMBER_CLR, alpha=0.5, label="Slow"))
    ax_rtt.legend(handles=legend_handles, loc="upper right",
                  facecolor=CARD_BG, edgecolor=GRID_CLR,
                  labelcolor=TEXT_CLR, fontsize=8)

    # Optional DNS latency on second y-axis
    if has_dns:
        ax_dns = ax_rtt.twinx()
        ax_dns.set_facecolor(CARD_BG)
        ax_dns.tick_params(colors=TEXT_CLR, labelsize=9)
        ax_dns.set_ylabel("DNS latency (ms)", color=TEXT_CLR, fontsize=9)
        for spine in ax_dns.spines.values():
            spine.set_edgecolor(GRID_CLR)
        # Aggregate DNS across all hosts (usually one value per cycle)
        all_ts_dns: list = []
        all_dns: list    = []
        for h in hosts:
            for ts, dns in zip(host_series[h]["ts"], host_series[h]["dns"]):
                if not _is_nan(dns):
                    all_ts_dns.append(ts)
                    all_dns.append(dns)
        if all_ts_dns:
            paired = sorted(zip(all_ts_dns, all_dns))
            all_ts_dns, all_dns = zip(*paired)
            ax_dns.plot(all_ts_dns, all_dns, linewidth=1.0, color="#f472b6",
                        alpha=0.7, linestyle="--", label="DNS latency")
            ax_dns.legend(loc="upper left", facecolor=CARD_BG,
                          edgecolor=GRID_CLR, labelcolor=TEXT_CLR, fontsize=8)

    # X-axis date formatting — auto-scale
    ax_rtt.xaxis.set_major_formatter(mdates.AutoDateFormatter(mdates.AutoDateLocator()))
    fig.autofmt_xdate(rotation=25, ha="right")

    # ── Bottom subplot: uptime bar chart ──────────────────────────────────────
    ax_bar.set_title("Per-target uptime %", color=TEXT_CLR, fontsize=10, pad=8)
    ax_bar.set_ylabel("Uptime %", color=TEXT_CLR, fontsize=9)
    ax_bar.set_ylim(0, 105)
    ax_bar.grid(axis="y", color=GRID_CLR, linewidth=0.5, alpha=0.7)

    bar_colors = [
        (RED_CLR if host_uptime[h] < 95 else (AMBER_CLR if host_uptime[h] < 99 else ACCENT))
        for h in hosts
    ]
    bars = ax_bar.bar(hosts, [host_uptime[h] for h in hosts],
                      color=bar_colors, alpha=0.85, zorder=3)
    ax_bar.axhline(100, color=GRID_CLR, linewidth=0.8, linestyle="--")
    for bar, h in zip(bars, hosts):
        ax_bar.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.8,
                    f"{host_uptime[h]:.1f}%",
                    ha="center", va="bottom", color=TEXT_CLR, fontsize=8)
    ax_bar.tick_params(axis="x", labelrotation=15, labelsize=8)

    # ── Stats annotation on figure ────────────────────────────────────────────
    stats_parts = [
        f"Total pings: {summary.total_pings}",
        f"Outages: {len(outages)}",
        f"Avg RTT: {summary.avg_rtt_ms:.0f} ms" if summary.avg_rtt_ms else None,
    ]
    if summary.avg_dns_ms > 0:
        stats_parts.append(f"Avg DNS: {summary.avg_dns_ms:.0f} ms")
    stats_text = "  |  ".join(p for p in stats_parts if p)
    fig.text(0.5, 0.96, stats_text, ha="center", va="top",
             color=TEXT_CLR, fontsize=9, alpha=0.8)

    # ── Save ──────────────────────────────────────────────────────────────────
    if output_path is None:
        output_path = log_path.with_suffix(".png")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=DARK_BG)

    if show:
        plt.show()

    plt.close(fig)
    return output_path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_nan(v) -> bool:
    try:
        import math
        return math.isnan(v)
    except (TypeError, ValueError):
        return True


def _backend_available(backend: str) -> bool:
    try:
        import matplotlib
        matplotlib.use(backend)
        return True
    except Exception:
        return False
