"""
Speed Tester — high-performance multithreaded internet speed test.

Backend strategy (tried in order):
  1. Ookla CLI binary  — speedtest.exe / speedtest found next to the exe
                          or in %LOCALAPPDATA%\\NetSentinel\\   (1 Gbps+)
  2. speedtest-cli lib — bumped to 8 download / 4 upload threads;
                          SSL-shimmed for Python 3.12                (~400 Mbps)
  3. Pure-Python HTTP  — 16 parallel TCP streams via ThreadPoolExecutor
                          (no extra deps; ~1 Gbps limited by HTTP overhead)

Backend implementations live in modules/speed_tester_backends.py (S20-7 split).
Server discovery and geo-filtering live in modules/speed_tester_servers.py (S20-7b split).

Public API (unchanged):
────────────────────────────────────
    fetch_servers(limit)             → list[SpeedServer]
    run_test(server_id, on_progress) → SpeedTestResult
    speed_to_fraction(mbps)          → float   (0–1 log-scale gauge helper)
"""

from __future__ import annotations

import io
import math
import sys
import time
from typing import Callable, List, Optional

# ── Windowed-exe stdout/stderr guard ─────────────────────────────────────────
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

from modules.speed_tester_backends import (
    SpeedServer, SpeedTestResult,
    _find_ookla_cli, _run_ookla_cli,
    _patch_ssl_for_312, _run_speedtest_cli,
    _run_python_test,
)
from modules.speed_tester_servers import (
    _fetch_servers_python, _fetch_servers_by_query, _load_servers_cache, _save_servers_cache,
)

# Re-export all public names so existing callers continue to work.
__all__ = [
    "SpeedServer", "SpeedTestResult",
    "fetch_servers", "run_test", "resolve_server_id", "speed_to_fraction",
]

# Retry policy for fetch_servers(): both backends in the cascade are transient
# network calls, so a single blip (DNS hiccup, slow API, rate-limit) shouldn't
# surface as a hard failure to the user.
_FETCH_MAX_ATTEMPTS = 3
_FETCH_BACKOFF_SECONDS = (0.5, 1.0, 2.0)


# ── Gauge helper ──────────────────────────────────────────────────────────────

def speed_to_fraction(speed_mbps: float, max_mbps: float = 1000.0) -> float:
    """Map a speed (Mbps) to a 0–1 gauge fill on a log₁₀ scale."""
    if speed_mbps <= 0 or max_mbps <= 0:
        return 0.0
    return min(math.log10(speed_mbps + 1) / math.log10(max_mbps + 1), 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_servers(
    limit: int = 20,
    on_status: Optional[Callable[[str], None]] = None,
    preferred_location: Optional[str] = None,
) -> List[SpeedServer]:
    """
    Fetch nearby Ookla-compatible servers sorted by latency.
    Tries speedtest-cli first (5 s timeout), then pure-Python HTTP fallback.
    The whole cascade is retried up to _FETCH_MAX_ATTEMPTS times with backoff
    before falling back to the last-known-good cached list. Raises RuntimeError
    only if every attempt fails and no cache exists.
    on_status: optional callback(msg) for progress messages.
    preferred_location: optional free-text city/country (e.g. "Stockholm, Sweden").
        When given, this replaces IP-geolocation entirely as the source of the
        candidate list — a text search against Ookla's server list, so servers in
        the user's actual country are found even when IP geolocation resolves to
        the wrong country (see modules/speed_tester_servers.py:_fetch_servers_by_query).
    """
    from modules.firewall_rules import ensure_app_rules
    ensure_app_rules()

    def _status(msg: str) -> None:
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass  # non-fatal — UI callback may have been destroyed

    last_exc: Optional[Exception] = None
    for attempt in range(1, _FETCH_MAX_ATTEMPTS + 1):
        if attempt > 1:
            _status(f"Retrying server list (attempt {attempt}/{_FETCH_MAX_ATTEMPTS})…")
            time.sleep(_FETCH_BACKOFF_SECONDS[attempt - 2])
        try:
            servers = _fetch_servers_cascade(limit, _status, preferred_location=preferred_location)
        except Exception as exc:
            last_exc = exc
            continue
        _save_servers_cache(servers)
        return servers

    cached = _load_servers_cache()
    if cached:
        _status("Network unreachable — showing last known server list")
        return cached

    raise RuntimeError(f"Cannot fetch server list: {last_exc}") from last_exc


def _fetch_servers_cascade(
    limit: int,
    _status: Callable[[str], None],
    preferred_location: Optional[str] = None,
) -> List[SpeedServer]:
    """One attempt through the CLI-then-Python backend cascade (RULE 24 order)."""
    if preferred_location:
        return _fetch_servers_by_query(preferred_location, limit=limit, on_status=_status)

    try:
        import speedtest as _st  # noqa: F401
        _patch_ssl_for_312()
        import socket as _socket
        _prev = _socket.getdefaulttimeout()
        _socket.setdefaulttimeout(5)  # reduced from 8 — fall through faster on slow API
        try:
            _status("Connecting to Speedtest network…")
            try:
                client = _st.Speedtest(secure=True)
            except AttributeError:
                client = _st.Speedtest(secure=False)
            _status("Finding nearby servers…")
            client.get_servers()
            closest = client.get_closest_servers(limit=limit)
            try:
                client.get_best_server(closest)
            except Exception:
                pass  # non-fatal
            return [
                SpeedServer(
                    id=str(s.get("id", "")),
                    name=s.get("sponsor") or s.get("name") or "Unknown",
                    city=s.get("name") or "",
                    country=s.get("country") or "",
                    host=s.get("host") or "",
                    latency_ms=round(float(s.get("latency") or 0.0), 1),
                )
                for s in sorted(closest, key=lambda x: float(x.get("latency") or 9999))
            ]
        finally:
            _socket.setdefaulttimeout(_prev)
    except ImportError:
        pass  # speedtest-cli not installed — fall through to pure-Python
    except Exception:
        pass  # speedtest-cli failed — fall through to pure-Python fallback

    return _fetch_servers_python(limit, on_status=_status)


def run_test(
    server_id: Optional[str] = None,
    on_progress: Optional[Callable[[str, str], None]] = None,
    on_sample: Optional[Callable[[float, str], None]] = None,
) -> SpeedTestResult:
    """
    Run a full speed test.

    Backend selected automatically (highest accuracy first):
      1. Ookla CLI binary   — if speedtest.exe/speedtest found on disk
      2. speedtest-cli lib  — if installed (pip install speedtest-cli)
      3. Pure-Python HTTP   — always available, 16 parallel streams

    on_progress(phase, message) callbacks:
        phase ∈ {"connecting", "ping", "download", "upload", "done"}

    on_sample(mbps, phase) callbacks:
        Fired with live throughput samples during download and upload.
    """
    # Ensure Windows Firewall outbound rules exist for speedtest ports.
    # No-op on non-Windows, silent fallback when not elevated.
    from modules.firewall_rules import ensure_app_rules, ensure_ookla_rules
    ensure_app_rules()

    cli = _find_ookla_cli()
    if cli:
        ensure_ookla_rules(cli)
        try:
            return _run_ookla_cli(cli, server_id=server_id,
                                  on_progress=on_progress, on_sample=on_sample)
        except Exception:
            pass  # non-fatal

    try:
        return _run_speedtest_cli(server_id=server_id, on_progress=on_progress,
                                  on_sample=on_sample)
    except RuntimeError as exc:
        if "not installed" in str(exc):
            pass
        else:
            raise

    return _run_python_test(server_id=server_id, on_progress=on_progress,
                            on_sample=on_sample)


def resolve_server_id(
    preferred_server_id: Optional[str] = None,
    preferred_location: Optional[str] = None,
) -> Optional[str]:
    """
    Resolve which Ookla server ID a manual or scheduled/background test should
    target, so both paths apply the same location-correction logic instead of
    scheduled tests silently falling back to auto-best (see RULE-DW / the
    Speed Test wrong-country server bug fix).

    Priority:
      1. An explicit pinned server ID — trusted as-is. If it has since gone stale
         (Ookla retired/renumbered it), each backend's own "not found in candidate
         list" fallback handles that; this function doesn't re-validate it.
      2. A saved preferred_location — resolved to the fastest server from a fresh
         location-text search (bypasses IP geolocation entirely).
      3. Neither set → None, today's fully-automatic behavior.
    """
    if preferred_server_id:
        return preferred_server_id
    if preferred_location:
        try:
            servers = fetch_servers(limit=10, preferred_location=preferred_location)
        except Exception:
            return None  # non-fatal — caller falls back to auto-best
        if servers:
            return servers[0].id
    return None
