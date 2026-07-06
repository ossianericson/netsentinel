"""
Ratchet test for P4 — shared network primitives consolidation.

Guards against new hand-rolled subprocess ping invocations or raw TCP connect
probes creeping back into modules/ outside modules/utils_net.py. New code that
needs an ICMP RTT should call utils_net.icmp_ping(); new code that needs a bare
TCP reachability check should call utils_net.tcp_probe(). New code that needs
the OS ARP cache should call utils_net.get_arp_snapshot(). New code fanning a
function out across many items on a thread pool should call
utils_net.parallel_map() unless it needs incremental per-item progress
reporting or early-cancellation (as_completed), which parallel_map does not
provide.

Both baselines below are ratchets: counts may only stay the same or shrink.
Do not raise a count to make a new violation pass — either route the new call
through utils_net, or (if there is a genuine, documented reason utils_net
can't serve it) add a one-line comment explaining why and keep the count
accurate.
"""
from __future__ import annotations

import re
from pathlib import Path

_MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"

_PING_SUBPROCESS_RE = re.compile(r'\[\s*["\']ping["\']')
_CREATE_CONNECTION_RE = re.compile(r"create_connection\(")

# Files with a legitimate reason to invoke ping via subprocess directly instead
# of calling utils_net.icmp_ping() — each needs something icmp_ping does not
# provide (icmp_ping is single-ping RTT only).
_PING_SUBPROCESS_BASELINE = {
    "os_fingerprint.py":              2,  # _ping_ttl — needs TTL from the reply, not RTT
    "service_diagnostics_probes.py":  2,  # icmp_probe — multi-ping min/avg/max/jitter/loss stats
    "utils.py":                       4,  # ping_sweep_subnet + ping_sweep_cidr — bulk liveness-only sweeps, no RTT needed
    "utils_platform.py":              1,  # ping_sweep_ipv6 — ping6/-6, fire-and-forget neighbour-cache populate
}

# Files that legitimately open a raw TCP socket via create_connection() for
# further protocol I/O (TLS handshake, banner grab) rather than a simple
# up/down + RTT probe — utils_net.tcp_probe() closes the socket immediately
# and can't serve these.
_CREATE_CONNECTION_BASELINE = {
    "os_fingerprint.py":             1,  # _grab_banner — reads a banner off the live socket
    "port_scanner.py":               1,  # _check — banner grab (probe_service) reuses the live socket
    "private_endpoint_checker.py":   1,  # _tls_inspect — needs the raw socket for ctx.wrap_socket()
    "syn_scanner.py":                1,  # banner grab after SYN-ACK reuses the live socket
    "tls_checker.py":                1,  # needs the raw socket to wrap in ctx.wrap_socket()
}


def _count(text: str, pattern: re.Pattern) -> int:
    return len(pattern.findall(text))


def test_no_new_subprocess_ping_outside_baseline():
    offenders = []
    for path in sorted(_MODULES_DIR.glob("*.py")):
        if path.name == "utils_net.py":
            continue  # the canonical implementation
        n = _count(path.read_text(encoding="utf-8"), _PING_SUBPROCESS_RE)
        baseline = _PING_SUBPROCESS_BASELINE.get(path.name, 0)
        if n > baseline:
            offenders.append(f"{path.name}: found {n}, baseline {baseline}")
        elif n == 0 and path.name in _PING_SUBPROCESS_BASELINE:
            offenders.append(
                f"{path.name}: baseline says {baseline} but found 0 — "
                "lower _PING_SUBPROCESS_BASELINE, don't leave it stale"
            )
    assert not offenders, (
        "New direct subprocess ping invocation(s) outside modules/utils_net.py: "
        f"{offenders}. Call modules.utils_net.icmp_ping() instead of shelling out "
        "to ping directly, or add a baseline entry with a comment if icmp_ping "
        "genuinely can't serve this call site."
    )


def test_no_new_raw_create_connection_outside_baseline():
    offenders = []
    for path in sorted(_MODULES_DIR.glob("*.py")):
        if path.name == "utils_net.py":
            continue  # the canonical implementation
        n = _count(path.read_text(encoding="utf-8"), _CREATE_CONNECTION_RE)
        baseline = _CREATE_CONNECTION_BASELINE.get(path.name, 0)
        if n > baseline:
            offenders.append(f"{path.name}: found {n}, baseline {baseline}")
        elif n == 0 and path.name in _CREATE_CONNECTION_BASELINE:
            offenders.append(
                f"{path.name}: baseline says {baseline} but found 0 — "
                "lower _CREATE_CONNECTION_BASELINE, don't leave it stale"
            )
    assert not offenders, (
        "New raw socket.create_connection() outside modules/utils_net.py: "
        f"{offenders}. Use modules.utils_net.tcp_probe() for TCP reachability "
        "checks, or add a baseline entry with a comment explaining why this "
        "call site needs the live connected socket."
    )
