"""
ISP Accountability Report builder.

Extracted from modules/report_exporter.py (S20-5 sprint split).
All public names remain importable from modules.report_exporter for
backwards compatibility via re-exports in that module.
"""

import datetime
import html
from pathlib import Path
from string import Template as _Template

from modules.report_html import _CSS
from modules.colours import (
    EXPORT_TEXT, EXPORT_HEADING_FG, EXPORT_META,
    EXPORT_RED_FG,
    EXPORT_BORDER, EXPORT_ACCENT_FG,
    EXPORT_TH_BG, EXPORT_ISP_HEADER, EXPORT_NOTE_BG,
    GRADE_A_BG, GRADE_A_FG, GRADE_A_BORDER,
    GRADE_B_BG, GRADE_B_FG, GRADE_B_BORDER,
    GRADE_C_BG, GRADE_C_FG, GRADE_C_BORDER,
    GRADE_D_BG, GRADE_D_FG, GRADE_D_BORDER,
    GRADE_F_BG, GRADE_F_FG, GRADE_F_BORDER,
)


_ISP_CSS = _CSS + _Template("""
.isp-header { background: $EXPORT_ISP_HEADER; border-bottom: 3px solid $EXPORT_HEADING_FG; padding: 24px 32px 16px; }
.isp-header h1 { color: $EXPORT_TEXT; font-size: 1.6rem; }
.isp-header .sub { color: $EXPORT_META; font-size: 0.85rem; margin-top: 4px; }
.grade-box { display:inline-block; width:90px; height:90px; border-radius:50%;
  line-height:90px; text-align:center; font-size:3rem; font-weight:bold; margin-right:24px;
  vertical-align:middle; }
.grade-A { background:$GRADE_A_BG; color:$GRADE_A_FG; border:3px solid $GRADE_A_BORDER; }
.grade-B { background:$GRADE_B_BG; color:$GRADE_B_FG; border:3px solid $GRADE_B_BORDER; }
.grade-C { background:$GRADE_C_BG; color:$GRADE_C_FG; border:3px solid $GRADE_C_BORDER; }
.grade-D { background:$GRADE_D_BG; color:$GRADE_D_FG; border:3px solid $GRADE_D_BORDER; }
.grade-F { background:$GRADE_F_BG; color:$GRADE_F_FG; border:3px solid $GRADE_F_BORDER; }
.dim-row { display:flex; align-items:center; padding:10px 0; border-bottom:1px solid $EXPORT_TH_BG; }
.dim-name { flex:0 0 200px; color:$EXPORT_ACCENT_FG; font-size:0.9rem; }
.dim-bar-wrap { flex:1; background:$EXPORT_TH_BG; border-radius:6px; height:12px; margin:0 16px; }
.dim-bar { height:12px; border-radius:6px; }
.dim-grade { flex:0 0 30px; font-weight:bold; font-size:1.1rem; text-align:center; }
.dim-val { flex:0 0 100px; color:$EXPORT_META; font-size:0.8rem; text-align:right; }
.hop-table { font-size:0.82rem; }
.hop-table .loss-high { color:$EXPORT_RED_FG; font-weight:bold; }
.section-title { color:$EXPORT_HEADING_FG; font-size:1rem; font-weight:bold;
  margin:20px 0 8px; padding-bottom:4px; border-bottom:1px solid $EXPORT_BORDER; }
.evidence-note { background:$EXPORT_NOTE_BG; border-left:3px solid $EXPORT_HEADING_FG;
  padding:10px 14px; font-size:0.85rem; color:$EXPORT_META; margin:12px 0; border-radius:0 8px 8px 0; }
""").substitute(
    EXPORT_ISP_HEADER=EXPORT_ISP_HEADER, EXPORT_HEADING_FG=EXPORT_HEADING_FG,
    EXPORT_TEXT=EXPORT_TEXT, EXPORT_META=EXPORT_META, EXPORT_TH_BG=EXPORT_TH_BG,
    EXPORT_ACCENT_FG=EXPORT_ACCENT_FG, EXPORT_BORDER=EXPORT_BORDER,
    EXPORT_NOTE_BG=EXPORT_NOTE_BG, EXPORT_RED_FG=EXPORT_RED_FG,
    GRADE_A_BG=GRADE_A_BG, GRADE_A_FG=GRADE_A_FG, GRADE_A_BORDER=GRADE_A_BORDER,
    GRADE_B_BG=GRADE_B_BG, GRADE_B_FG=GRADE_B_FG, GRADE_B_BORDER=GRADE_B_BORDER,
    GRADE_C_BG=GRADE_C_BG, GRADE_C_FG=GRADE_C_FG, GRADE_C_BORDER=GRADE_C_BORDER,
    GRADE_D_BG=GRADE_D_BG, GRADE_D_FG=GRADE_D_FG, GRADE_D_BORDER=GRADE_D_BORDER,
    GRADE_F_BG=GRADE_F_BG, GRADE_F_FG=GRADE_F_FG, GRADE_F_BORDER=GRADE_F_BORDER,
)


def generate_isp_report(
    log_summary=None,
    diag_result=None,
    mtr_result=None,
    benchmark_result=None,
    m1_result=None,
    public_ip: str = "",
    isp_name: str = "",
    account_ref: str = "",
) -> str:
    """
    Generate a self-contained HTML ISP Accountability Report.

    Bundles: network grade, traceroute hop table with loss %, ping stats,
    DNS latency, outage log, and a plain-English summary paragraph.
    """
    ts  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.datetime.now().strftime("%A %d %B %Y, %H:%M")

    if benchmark_result:
        grade_letter = benchmark_result.overall_grade
        grade_color  = benchmark_result.overall_color
        overall_txt  = html.escape(benchmark_result.overall_verdict)
        grade_css    = f"grade-{grade_letter}"
        score        = f"{benchmark_result.overall_score:.0f}/100"
    else:
        grade_letter = "N/A"
        grade_css    = "grade-F"
        grade_color  = "#888"
        overall_txt  = "No benchmark data available."
        score        = "—"

    dim_html = ""
    if benchmark_result and benchmark_result.dimensions:
        for d in benchmark_result.dimensions:
            bar_color = d.color
            dim_html += (
                f'<div class="dim-row">'
                f'<div class="dim-name">{html.escape(d.name)}</div>'
                f'<div class="dim-bar-wrap">'
                f'<div class="dim-bar" style="width:{d.score:.0f}%;background:{bar_color}"></div>'
                f'</div>'
                f'<div class="dim-grade" style="color:{bar_color}">{d.grade}</div>'
                f'<div class="dim-val">{html.escape(d.value_label)}</div>'
                f'</div>'
            )

    trace_hops = getattr(diag_result, "trace_hops", []) if diag_result else []
    mtr_rows_html = ""
    if mtr_result:
        for hop in mtr_result:
            loss = hop.get("loss_pct", 0.0)
            cls  = 'loss-high' if loss > 10 else ''
            mtr_rows_html += (
                f"<tr><td>{hop.get('hop','?')}</td>"
                f"<td>{html.escape(hop.get('ip','*'))}</td>"
                f"<td class='{cls}'>{loss:.1f}%</td>"
                f"<td>{hop.get('avg_rtt',-1):.1f} ms</td>"
                f"<td>{hop.get('last_rtt',-1):.1f} ms</td></tr>"
            )
    elif trace_hops:
        for h in trace_hops:
            rtt  = getattr(h, "rtt_ms", -1)
            mtr_rows_html += (
                f"<tr><td>{getattr(h,'hop','?')}</td>"
                f"<td>{html.escape(getattr(h,'ip','*'))}</td>"
                f"<td>—</td>"
                f"<td>{'—' if rtt < 0 else f'{rtt:.1f} ms'}</td>"
                f"<td>—</td></tr>"
            )
    hop_section = ""
    if mtr_rows_html:
        hop_section = f"""
<div class="section-title">Network Path (Traceroute / MTR)</div>
<table class="hop-table">
<thead><tr><th>Hop</th><th>IP Address</th><th>Packet Loss</th>
<th>Avg RTT</th><th>Last RTT</th></tr></thead>
<tbody>{mtr_rows_html}</tbody>
</table>
<div class="evidence-note">
Packet loss at hop 1 (your router) = local fault.<br>
Packet loss first appearing at hop 2+ = ISP infrastructure issue.
</div>"""

    outages = getattr(log_summary, "outages", []) if log_summary else []
    outage_rows = ""
    for o in outages:
        outage_rows += (
            f"<tr><td>{html.escape(o.host)}</td>"
            f"<td>{html.escape(o.start)}</td>"
            f"<td>{html.escape(o.end)}</td>"
            f"<td>{o.duration_s:.0f} s</td>"
            f"<td>{o.consecutive_fails}</td></tr>"
        )
    outage_section = ""
    if outage_rows:
        outage_section = f"""
<div class="section-title">Recorded Outages</div>
<table>
<thead><tr><th>Target</th><th>Start</th><th>End</th>
<th>Duration</th><th>Consecutive Fails</th></tr></thead>
<tbody>{outage_rows}</tbody>
</table>"""
    elif log_summary:
        outage_section = (
            '<div class="section-title">Recorded Outages</div>'
            '<p style="color:#22c55e">No outages recorded during the monitoring period.</p>'
        )

    uptime  = getattr(log_summary, "uptime_pct",   100.0) if log_summary else None
    avg_rtt = getattr(log_summary, "avg_rtt_ms",   -1.0)  if log_summary else -1.0
    jitter  = getattr(log_summary, "avg_jitter_ms",-1.0)  if log_summary else -1.0
    dl_mbps = getattr(diag_result, "download_mbps",-1.0)  if diag_result else -1.0

    def _fmt(val, suffix, default="Not measured"):
        return f"{val:.1f}{suffix}" if val and val > 0 else default

    metrics_rows = f"""
<tr><td>Uptime</td><td>{_fmt(uptime,'%') if uptime is not None else 'Not measured'}</td></tr>
<tr><td>Average Latency</td><td>{_fmt(avg_rtt,' ms')}</td></tr>
<tr><td>Average Jitter</td><td>{_fmt(jitter,' ms')}</td></tr>
<tr><td>Download Speed</td><td>{_fmt(dl_mbps,' Mbps')}</td></tr>
<tr><td>Public IP</td><td>{html.escape(public_ip or 'Not detected')}</td></tr>
<tr><td>ISP</td><td>{html.escape(isp_name or 'Not specified')}</td></tr>
<tr><td>Account Reference</td><td>{html.escape(account_ref or '—')}</td></tr>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NetSentinel — ISP Report {ts}</title>
<style>{_ISP_CSS}</style>
</head>
<body>
<div class="isp-header">
  <h1>NetSentinel — ISP Accountability Report</h1>
  <div class="sub">Generated: {now} &nbsp;|&nbsp; This report was produced entirely offline. No data was sent to any server.</div>
</div>

<div class="module" style="margin-top:20px;display:flex;align-items:center">
  <div class="grade-box {grade_css}">{grade_letter}</div>
  <div>
    <div style="font-size:1.1rem;font-weight:bold;color:{grade_color}">
      Network Health Score: {score}
    </div>
    <div style="color:#ccc;margin-top:6px;max-width:600px">{overall_txt}</div>
  </div>
</div>

<div class="module">
  <div class="section-title">Performance Breakdown</div>
  {dim_html or '<p>No benchmark data — run scans first.</p>'}
</div>

<div class="module">
  <div class="section-title">Key Metrics Summary</div>
  <table><tbody>{metrics_rows}</tbody></table>
</div>

{f'<div class="module">{hop_section}</div>' if hop_section else ''}
{f'<div class="module">{outage_section}</div>' if outage_section else ''}

<div class="module">
  <div class="section-title">How to Use This Report</div>
  <ul style="padding-left:18px;line-height:1.9;color:#ccc;font-size:0.9rem">
    <li>Share this HTML file or print it to PDF (Ctrl+P → Save as PDF) and attach to your ISP support ticket.</li>
    <li>Point the technician to the <strong>Network Path</strong> table — packet loss first appearing at hop 2 or later is in the ISP's network.</li>
    <li>The <strong>Recorded Outages</strong> section provides timestamped evidence of every disconnection.</li>
    <li>The <strong>Network Health Score</strong> gives an at-a-glance summary of your connection quality.</li>
  </ul>
</div>

<p class="meta">
  NetSentinel &bull; Privacy-First Network Diagnostics &bull;
  All measurements taken locally &bull; {ts}
</p>
</body>
</html>"""


def generate_isp_complaint_text(
    log_summary=None,
    diag_result=None,
    benchmark_result=None,
    isp_name: str = "",
    account_ref: str = "",
    include_legal: bool = False,
) -> str:
    """
    Return a plain-text ISP complaint script the user can paste into an email.

    All measurements come from NetSentinel — no "run speedtest.net" (Principle 3).
    """
    import datetime as _dt
    now = _dt.datetime.now().strftime("%d %B %Y, %H:%M")

    uptime  = getattr(log_summary, "uptime_pct",   None) if log_summary else None
    avg_rtt = getattr(log_summary, "avg_rtt_ms",   -1.0) if log_summary else -1.0
    jitter  = getattr(log_summary, "avg_jitter_ms",-1.0) if log_summary else -1.0
    dl_mbps = getattr(diag_result, "download_mbps",-1.0) if diag_result else -1.0
    outages = getattr(log_summary, "outages",      [])   if log_summary else []

    grade_note = ""
    if benchmark_result:
        grade_note = (
            f" (NetSentinel network health score: "
            f"{benchmark_result.overall_score:.0f}/100, grade {benchmark_result.overall_grade})"
        )

    isp_line  = f"To: {isp_name} Support" if isp_name else "To: [Your ISP] Support"
    ref_line  = f"Account / Ticket Ref: {account_ref}" if account_ref else ""

    def _fmt(val, suffix):
        return f"{val:.1f}{suffix}" if val and val > 0 else "not measured"

    uptime_line = f"{uptime:.1f}% uptime" if uptime is not None else "uptime not measured"
    rtt_line    = _fmt(avg_rtt, " ms average latency")
    jitter_line = _fmt(jitter, " ms average jitter")
    dl_line     = _fmt(dl_mbps, " Mbps download speed")
    outage_line = (
        f"{len(outages)} recorded outage(s)" if outages else "no outages recorded"
    )

    legal_block = (
        "\n"
        "Under the Consumer Rights Act 2015 and Ofcom's General Conditions (UK),\n"
        "and / or the EU Electronic Communications Code, I am entitled to a service\n"
        "that meets the agreed performance characteristics. I formally request that\n"
        "you investigate and resolve the issues above within a reasonable timeframe\n"
        "and provide a written response with a reference number.\n"
    ) if include_legal else ""

    lines = [now, "", isp_line]
    if ref_line:
        lines.append(ref_line)
    lines += [
        "",
        f"Subject: Service Quality Issue — Measured Evidence{grade_note}",
        "",
        "Dear Support Team,",
        "",
        "I am experiencing persistent performance issues with my broadband connection. "
        "I have monitored my connection using NetSentinel (a local network diagnostics tool) "
        "and recorded the following measurements:",
        "",
        f"  • {uptime_line}",
        f"  • {rtt_line}",
        f"  • {jitter_line}",
        f"  • {dl_line}",
        f"  • {outage_line}",
        "",
        "Please investigate the cause of these issues and advise on the expected resolution timeline.",
        "After any changes on your side, I will re-run NetSentinel diagnostics to confirm improvement.",
    ]
    if legal_block:
        lines += ["", legal_block.rstrip()]
    lines += ["", "Yours faithfully,", "[Your name]", "[Your address / account number]"]

    return "\n".join(lines)


def save_isp_report(
    output_path: Path,
    log_summary=None,
    diag_result=None,
    mtr_result=None,
    benchmark_result=None,
    m1_result=None,
    public_ip: str = "",
    isp_name: str = "",
    account_ref: str = "",
) -> Path:
    """Save an ISP Accountability Report as HTML. Returns the output path."""
    content = generate_isp_report(
        log_summary=log_summary,
        diag_result=diag_result,
        mtr_result=mtr_result,
        benchmark_result=benchmark_result,
        m1_result=m1_result,
        public_ip=public_ip,
        isp_name=isp_name,
        account_ref=account_ref,
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path
