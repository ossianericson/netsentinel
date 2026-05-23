"""
NetSentinel CLI — headless command-line interface.

Run as Administrator (Windows) or with sudo (Linux/macOS) for full functionality.

Commands:
    scan              Device fingerprint scan → HTML / JSON / CSV report
    diagnose          Full connectivity diagnostics
    log               Background ping logger — runs until Ctrl+C, writes CSV
    ports HOST        TCP port scan on a single host
    check-endpoints   DNS / TCP / TLS reachability for private endpoints
    cloud-metadata    Detect if this machine is inside a cloud VM (AWS/Azure/GCP)
    log-chart FILE    Render a log CSV as a PNG RTT chart

Examples:
    python cli.py scan --format html --output report.html
    python cli.py scan --cidr 10.0.0.0/24 --format json
    python cli.py scan --ipv6
    python cli.py diagnose --output diag.html
    python cli.py log --interval 30 --targets 8.8.8.8 1.1.1.1 --dns --arp
    python cli.py ports 192.168.1.1 --mode fast
    python cli.py check-endpoints api.myapp.azurewebsites.net:443 db.internal:5432:MyDB
    python cli.py cloud-metadata
    python cli.py log-chart netlog.csv --show
"""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

# Allow running from the project root without installation.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_VERSION = "1.9.21"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_devices(devices, verbose: bool = False) -> None:
    """Pretty-print DeviceInfo objects to stdout."""
    if not devices:
        print("  (no devices found)")
        return
    print(f"\n  {'IP':<16}  {'MAC':<17}  {'RISK':<8}  {'HOSTNAME / TYPE / VENDOR'}")
    print("  " + "-" * 76)
    for d in devices:
        ip       = getattr(d, "ip",          "")
        mac      = getattr(d, "mac",         "")
        risk     = getattr(d, "risk_level",  "UNKNOWN")
        hostname = getattr(d, "hostname",    "")
        dev_type = getattr(d, "device_type", "")
        vendor   = getattr(d, "vendor",      "")
        name = hostname or (f"[{dev_type}]" if dev_type else vendor)
        print(f"  {ip:<16}  {mac:<17}  {risk:<8}  {name}")
        if verbose:
            verdict = getattr(d, "verdict", "")
            if verdict:
                print(f"  {'':<16}  {'':<17}  {'':<8}  ↳ {verdict}")


# ── scan ──────────────────────────────────────────────────────────────────────

def cmd_scan(args) -> None:
    """Device fingerprint scan."""
    from modules.utils import (
        get_offenders_path, flush_network_caches, get_local_ip,
        ping_sweep_subnet, ping_sweep_cidr,
    )
    from modules.rogue_device import scan as m1_scan
    from modules.report_exporter import (
        generate_html, generate_json, generate_csv_devices,
    )

    def _log(msg: str) -> None:
        if not args.quiet:
            print(msg)

    _log("[1/4] Flushing network caches…")
    flush_network_caches()

    if args.cidr:
        _log(f"[2/4] CIDR sweep: {args.cidr}…")
        ping_sweep_cidr(args.cidr, progress_cb=_log if args.verbose else None)
    else:
        _log("[2/4] Subnet sweep…")
        local_ip = get_local_ip()
        ping_sweep_subnet(local_ip, progress_cb=_log if args.verbose else None)

    _log("[3/4] Fingerprinting devices…")
    path = get_offenders_path()
    data = m1_scan(path)
    devices      = data.get("devices", [])
    high_risk    = data.get("high_risk_count", 0)
    plain_verdict = data.get("plain_verdict", "")
    _log(f"      {len(devices)} device(s) found, {high_risk} HIGH RISK")

    fmt = args.format.lower()
    out = os.path.abspath(args.output or f"netsentinel_scan.{fmt}")

    _log(f"[4/4] Writing {fmt.upper()} report…")
    if fmt == "html":
        content = generate_html(module1_data=data, overall_verdict=plain_verdict)
        Path(out).write_text(content, encoding="utf-8")
    elif fmt == "json":
        content = generate_json(module1_data=data, overall_verdict=plain_verdict)
        Path(out).write_text(content, encoding="utf-8")
    elif fmt == "csv":
        content = generate_csv_devices(data)
        Path(out).write_text(content, encoding="utf-8")
    else:
        print(f"Unknown format: {fmt}", file=sys.stderr)
        sys.exit(1)

    _log(f"Report: {out}")

    if not args.quiet:
        print(f"\nVerdict: {plain_verdict}")
        _print_devices(devices, verbose=args.verbose)
        print()

    # Exit 2 if any HIGH-RISK devices found — useful in CI pipelines.
    if args.ipv6:
        _log("[IPv6] Scanning link-local segment…")
        from modules.utils import ping_sweep_ipv6
        ipv6_devices = ping_sweep_ipv6(progress_cb=_log if args.verbose else None)
        if not args.quiet:
            print(f"\n  IPv6 devices ({len(ipv6_devices)} found):")
            if ipv6_devices:
                print(f"  {'IPv6 Address':<42}  {'MAC':<17}  {'State':<12}  Source")
                print("  " + "-" * 82)
                for d in ipv6_devices:
                    print(f"  {d['ip6']:<42}  {d.get('mac',''):<17}  {d.get('state',''):<12}  {d.get('source','')}")
            else:
                print("  (no IPv6 devices found)")
            print()

    sys.exit(2 if high_risk > 0 else 0)


# ── diagnose ──────────────────────────────────────────────────────────────────

def cmd_diagnose(args) -> None:
    """Run full network diagnostics."""
    from modules.network_diagnostics import scan as diag_scan

    def _log(msg: str) -> None:
        if not args.quiet:
            print(msg)

    _log("Running diagnostics…")
    result = diag_scan(progress_cb=_log if args.verbose else None)

    if not args.quiet:
        print(f"\nVerdict:   {result.plain_verdict}")
        print(f"Public IP: {result.public_ip or '—'}")
        if result.download_mbps > 0:
            print(f"Download:  {result.download_mbps:.1f} Mbps")

        print("\nPing:")
        for p in result.ping_results:
            rtt = f"{p.rtt_ms:.1f} ms" if p.rtt_ms >= 0 else "FAIL"
            print(f"  {p.host:<22} {rtt:<12} {p.status}")

        print("\nDNS servers:")
        for d in result.dns_results:
            lat = f"{d.latency_ms:.1f} ms" if d.latency_ms >= 0 else "FAIL"
            print(f"  {d.server:<22} {lat:<12} {d.status}")

        if result.dns_leak:
            leak = "⚠ LEAK DETECTED" if result.dns_leak.leak_detected else "✔ No leak"
            print(f"\nDNS leak: {leak}")

    if args.output:
        fmt = args.format.lower()
        out = os.path.abspath(args.output)
        if fmt == "html":
            from modules.report_exporter import generate_html
            content = generate_html(diagnostics_data=result)
            Path(out).write_text(content, encoding="utf-8")
        elif fmt == "json":
            from modules.report_exporter import generate_json
            content = generate_json(diagnostics_data=result)
            Path(out).write_text(content, encoding="utf-8")
        else:
            print(f"Unsupported format for diagnose: {fmt}", file=sys.stderr)
            sys.exit(1)
        _log(f"Report: {out}")


# ── log ───────────────────────────────────────────────────────────────────────

def cmd_log(args) -> None:
    """Start the background ping logger. Runs until Ctrl+C, writes CSV."""
    from modules.network_logger import NetworkLogger

    targets = args.targets or ["8.8.8.8", "1.1.1.1", "google.com"]
    log_path = Path(args.output).expanduser() if args.output else None

    logger = NetworkLogger(
        interval_s=args.interval,
        targets=targets,
        log_path=log_path,
        enable_jitter=args.jitter,
        enable_dns=args.dns,
        enable_http=args.http,
        enable_arp=args.arp,
    )

    def _on_entry(entry) -> None:
        if not args.quiet:
            rtt = f"{entry.rtt_ms:.1f} ms" if entry.rtt_ms >= 0 else "FAIL"
            print(f"  [{entry.timestamp}]  {entry.host:<20}  {rtt:<12}  {entry.status}")

    print(f"Logging to: {logger.log_file}")
    print(f"Targets:    {', '.join(targets)}")
    print(f"Interval:   {args.interval}s")
    extras = [n for n, f in [("jitter", args.jitter), ("dns", args.dns),
                              ("http", args.http), ("arp", args.arp)] if f]
    if extras:
        print(f"Extras:     {', '.join(extras)}")
    print("Press Ctrl+C to stop.\n")

    logger.start(on_entry=_on_entry)

    def _stop(sig, frame) -> None:
        print("\nStopping logger…")
        logger.stop()
        print(f"Log saved: {logger.log_file}")
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while logger.is_running():
        time.sleep(1)


# ── ports ─────────────────────────────────────────────────────────────────────

def cmd_ports(args) -> None:
    """TCP port scan on a single host."""
    from modules.port_scanner import scan as ps_scan

    print(f"Scanning {args.host} ({args.mode} mode)…")
    result = ps_scan(
        host=args.host,
        mode=args.mode,
        progress_cb=print if args.verbose else None,
    )

    if args.format == "json":
        payload = {
            "host":         result.host,
            "ip":           result.ip,
            "scanned":      result.scanned,
            "plain_verdict": result.plain_verdict,
            "open_ports": [
                {
                    "port":    p.port,
                    "service": p.service,
                    "banner":  p.banner,
                    "risk":    p.risk,
                }
                for p in result.open_ports
            ],
        }
        text = json.dumps(payload, indent=2)
        print(text)
        if args.output:
            Path(os.path.abspath(args.output)).write_text(text, encoding="utf-8")
    else:
        print(f"\nVerdict: {result.plain_verdict}")
        print(f"Scanned: {result.scanned} ports  |  {len(result.open_ports)} open\n")
        if result.open_ports:
            print(f"  {'Port':<8} {'Service':<30} {'Risk':<8} Banner")
            print("  " + "-" * 70)
            for p in result.open_ports:
                print(f"  {p.port:<8} {p.service:<30} {p.risk:<8} {p.banner or '—'}")
        else:
            print("  No open ports found.")
        if args.output:
            print(f"\nNote: use --format json to save output to a file.", file=sys.stderr)


# ── check-endpoints ───────────────────────────────────────────────────────────

def cmd_check_endpoints(args) -> None:
    """DNS / TCP / TLS reachability checker for private endpoints."""
    from modules.private_endpoint_checker import EndpointSpec, check_endpoints

    specs = []
    for spec_str in args.endpoints:
        parts = spec_str.split(":")
        if len(parts) < 2:
            print(f"Bad endpoint spec (need host:port[:label]): {spec_str}", file=sys.stderr)
            sys.exit(1)
        host = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            print(f"Bad port in: {spec_str}", file=sys.stderr)
            sys.exit(1)
        label = parts[2] if len(parts) >= 3 else f"{host}:{port}"
        specs.append(EndpointSpec(host=host, port=port, label=label))

    print(f"Checking {len(specs)} endpoint(s)…\n")
    results = check_endpoints(specs)

    if args.format == "json":
        payload = []
        for r in results:
            payload.append({
                "label":        r.spec.label,
                "host":         r.spec.host,
                "port":         r.spec.port,
                "status":       r.status,
                "cloud":        r.cloud,
                "resolved_ips": r.resolved_ips,
                "is_private":   r.is_private,
                "dns_leak":     r.dns_leak,
                "tcp_open":     r.tcp_open,
                "dns_server":   r.dns_server,
                "paas_hint":    r.paas_hint,
                "findings":     r.findings,
            })
        text = json.dumps(payload, indent=2)
        print(text)
        if args.output:
            Path(os.path.abspath(args.output)).write_text(text, encoding="utf-8")
    else:
        for r in results:
            status_icon = "✔" if r.status == "PASS" else ("⚠" if r.status == "WARN" else "✘")
            priv  = "PRIVATE" if r.is_private else ("LEAK!" if r.dns_leak else "public")
            tcp   = "✔ open" if r.tcp_open else "✘ closed"
            ips   = ", ".join(r.resolved_ips[:3]) + ("…" if len(r.resolved_ips) > 3 else "")
            cert  = ""
            if r.cert and not r.cert.error and r.cert.days_left >= 0:
                cert = f"  cert: {r.cert.days_left}d"
            print(f"  {status_icon} [{r.status:<4}]  {r.spec.label}")
            print(f"           {r.spec.host}:{r.spec.port}  →  {ips or '(unresolved)'}")
            print(f"           DNS: {priv}  |  TCP: {tcp}{cert}")
            if r.cloud:
                print(f"           Cloud: {r.cloud}")
            if r.dns_server:
                print(f"           Resolver: {r.dns_server}")
            for finding in r.findings:
                print(f"           ⚠ {finding}")
            print()

        if args.output:
            print("Note: use --format json to save output to a file.", file=sys.stderr)

    sys.exit(1 if any(r.status == "FAIL" for r in results) else 0)


# ── cloud-metadata ────────────────────────────────────────────────────────────

def cmd_cloud_metadata(args) -> None:
    """Detect cloud VM environment and network IMDS exposure."""
    from modules.cloud_metadata import check_local_imds

    def _log(msg: str) -> None:
        if not args.quiet:
            print(msg)

    _log("Probing cloud metadata endpoints…")
    result = check_local_imds()

    if args.format == "json":
        import dataclasses
        payload = {
            "provider":        result.provider,
            "instance_id":     result.instance_id,
            "region":          result.region,
            "account_id":      result.account_id,
            "public_ip":       result.public_ip,
            "ami_id":          result.ami_id,
            "project_id":      result.project_id,
            "imdsv2_enforced": result.imdsv2_enforced,
            "risk_level":      result.risk_level,
            "plain_verdict":   result.plain_verdict,
            "findings":        result.findings,
        }
        text = json.dumps(payload, indent=2)
        print(text)
        if args.output:
            Path(os.path.abspath(args.output)).write_text(text, encoding="utf-8")
    else:
        risk_icon = {"NONE": "✔", "INFO": "ℹ", "HIGH": "⚠"}.get(result.risk_level, "?")
        print(f"\n{risk_icon} [{result.risk_level}]  {result.plain_verdict}")
        if result.provider:
            print(f"\n  Provider:    {result.provider}")
            if result.instance_id:
                print(f"  Instance:    {result.instance_id}")
            if result.region:
                print(f"  Region:      {result.region}")
            if result.account_id:
                print(f"  Account:     {result.account_id}")
            if result.public_ip:
                print(f"  Public IP:   {result.public_ip}")
            if result.ami_id:
                print(f"  AMI:         {result.ami_id}")
            if result.project_id:
                print(f"  Project:     {result.project_id}")
            if result.imdsv2_enforced is not None:
                status = "enforced (secure)" if result.imdsv2_enforced else "NOT enforced (HIGH RISK)"
                print(f"  IMDSv2:      {status}")
        for finding in result.findings:
            print(f"\n  ⚠ {finding}")
        print()
        if args.output:
            print("Note: use --format json to save output to a file.", file=sys.stderr)


# ── log-chart ─────────────────────────────────────────────────────────────────

def cmd_log_chart(args) -> None:
    """Render a NetSentinel log CSV as a PNG RTT chart."""
    from modules.network_logger import load_log_file
    from modules.log_chart import render_chart

    log_path = Path(args.logfile).expanduser()
    if not log_path.exists():
        print(f"Log file not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"Loading: {log_path}")

    summary = load_log_file(log_path)
    if not summary.entries:
        print("No log entries found in the file.", file=sys.stderr)
        sys.exit(1)

    out_path = Path(os.path.abspath(args.output)) if args.output else None

    if not args.quiet:
        print(f"Entries: {summary.total_pings}  |  "
              f"Outages: {len(summary.outages)}  |  "
              f"Uptime: {summary.uptime_pct:.1f}%")
        print("Rendering chart…")

    saved = render_chart(summary, output_path=out_path, show=args.show)
    if not args.quiet:
        print(f"Chart saved: {saved}")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="netsentinel",
        description="NetSentinel — Network Security Scanner & Connectivity Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--version", action="version", version=f"NetSentinel {_VERSION}")
    parser.add_argument("-q", "--quiet",   action="store_true",
                        help="Suppress progress output (errors still shown)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show verbose / per-device output")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── scan ─────────────────────────────────────────────────────────────────
    p_scan = sub.add_parser("scan", help="Scan network for devices and fingerprint them")
    p_scan.add_argument("--cidr",   default=None,
                        help="CIDR range to scan (e.g. 192.168.1.0/24). Default: local /24")
    p_scan.add_argument("--format", default="html", choices=["html", "json", "csv"],
                        help="Output format (default: html)")
    p_scan.add_argument("--output", default=None,
                        help="Output file path (default: netsentinel_scan.<format>)")
    p_scan.add_argument("--ipv6",   action="store_true",
                        help="Also run IPv6 link-local sweep (cache + active ping6)")
    p_scan.set_defaults(func=cmd_scan)

    # ── diagnose ─────────────────────────────────────────────────────────────
    p_diag = sub.add_parser("diagnose", help="Run full network diagnostics")
    p_diag.add_argument("--format", default="html", choices=["html", "json"],
                        help="Output format when --output is given (default: html)")
    p_diag.add_argument("--output", default=None,
                        help="Write report to this file (optional; results also print to stdout)")
    p_diag.set_defaults(func=cmd_diagnose)

    # ── log ──────────────────────────────────────────────────────────────────
    p_log = sub.add_parser("log",
                           help="Background ping logger — runs until Ctrl+C, writes CSV")
    p_log.add_argument("--targets",  nargs="+", metavar="HOST",
                       help="Hosts to ping (default: 8.8.8.8 1.1.1.1 google.com)")
    p_log.add_argument("--interval", type=int, default=60, metavar="SECONDS",
                       help="Ping interval in seconds (default: 60)")
    p_log.add_argument("--output",   default=None, metavar="FILE",
                       help="CSV log path (default: auto-named in ~/Documents/NetSentinel/logs/)")
    p_log.add_argument("--jitter",   action="store_true",
                       help="Measure jitter (3× pings per host per cycle)")
    p_log.add_argument("--dns",      action="store_true",
                       help="Measure DNS latency each cycle")
    p_log.add_argument("--http",     action="store_true",
                       help="HTTP connectivity check each cycle (captive portal detection)")
    p_log.add_argument("--arp",      action="store_true",
                       help="ARP table watch — alert on new/changed MACs")
    p_log.set_defaults(func=cmd_log)

    # ── ports ─────────────────────────────────────────────────────────────────
    p_ports = sub.add_parser("ports", help="TCP port scan on a single host")
    p_ports.add_argument("host",
                         help="Target IP address or hostname")
    p_ports.add_argument("--mode",   default="normal", choices=["fast", "normal", "stealth"],
                         help="Scan mode (default: normal)")
    p_ports.add_argument("--format", default="text", choices=["text", "json"],
                         help="Output format (default: text)")
    p_ports.add_argument("--output", default=None, metavar="FILE",
                         help="Save JSON result to file (requires --format json)")
    p_ports.set_defaults(func=cmd_ports)

    # ── check-endpoints ───────────────────────────────────────────────────────
    p_ep = sub.add_parser("check-endpoints",
                          help="Check private endpoint DNS / TCP / TLS reachability")
    p_ep.add_argument("endpoints", nargs="+", metavar="HOST:PORT[:LABEL]",
                      help="Endpoint(s) to check, e.g. api.foo.azurewebsites.net:443:MyAPI")
    p_ep.add_argument("--format", default="text", choices=["text", "json"],
                      help="Output format (default: text)")
    p_ep.add_argument("--output", default=None, metavar="FILE",
                      help="Save JSON results to file (requires --format json)")
    p_ep.set_defaults(func=cmd_check_endpoints)

    # ── cloud-metadata ────────────────────────────────────────────────────────
    p_cloud = sub.add_parser(
        "cloud-metadata",
        help="Detect if this machine is inside a cloud VM (AWS/Azure/GCP); "
             "scan network for metadata proxy exposure",
    )
    p_cloud.add_argument("--format", default="text", choices=["text", "json"],
                         help="Output format (default: text)")
    p_cloud.add_argument("--output", default=None, metavar="FILE",
                         help="Save JSON result to file (requires --format json)")
    p_cloud.set_defaults(func=cmd_cloud_metadata)

    # ── log-chart ─────────────────────────────────────────────────────────────
    p_chart = sub.add_parser(
        "log-chart",
        help="Render a NetSentinel log CSV as a PNG RTT chart",
    )
    p_chart.add_argument("logfile", metavar="LOGFILE.csv",
                         help="Path to a NetSentinel log CSV file")
    p_chart.add_argument("--output", default=None, metavar="chart.png",
                         help="Output PNG path (default: same dir as log file, .png extension)")
    p_chart.add_argument("--show",   action="store_true",
                         help="Also open an interactive matplotlib window")
    p_chart.set_defaults(func=cmd_log_chart)

    args = parser.parse_args()

    # Ensure global flags always exist on the namespace even for sub-commands
    # that were registered before the flags were defined.
    if not hasattr(args, "verbose"):
        args.verbose = False
    if not hasattr(args, "quiet"):
        args.quiet = False

    args.func(args)


if __name__ == "__main__":
    main()
