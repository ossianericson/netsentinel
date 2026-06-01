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
    _fetch_servers_python, _run_python_test,
)

# Re-export all public names so existing callers continue to work.
__all__ = [
    "SpeedServer", "SpeedTestResult",
    "fetch_servers", "run_test", "speed_to_fraction",
]


# ── Gauge helper ──────────────────────────────────────────────────────────────

def speed_to_fraction(speed_mbps: float, max_mbps: float = 1000.0) -> float:
    """Map a speed (Mbps) to a 0–1 gauge fill on a log₁₀ scale."""
    if speed_mbps <= 0 or max_mbps <= 0:
        return 0.0
    return min(math.log10(speed_mbps + 1) / math.log10(max_mbps + 1), 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_servers(limit: int = 20) -> List[SpeedServer]:
    """
    Fetch nearby Ookla-compatible servers sorted by latency.
    Raises RuntimeError on network failure.
    """
    try:
        import speedtest as _st  # noqa: F401
        _patch_ssl_for_312()
        import socket as _socket
        _prev = _socket.getdefaulttimeout()
        _socket.setdefaulttimeout(30)
        try:
            try:
                client = _st.Speedtest(secure=True)
            except AttributeError:
                client = _st.Speedtest(secure=False)
            client.get_servers()
            closest = client.get_closest_servers(limit=limit)
            try:
                client.get_best_server(closest)
            except Exception:
                pass
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
        except (_st.ConfigRetrievalError, AttributeError):
            raise
        finally:
            _socket.setdefaulttimeout(_prev)
    except ImportError:
        pass
    except Exception as exc:
        raise RuntimeError(f"Server fetch failed: {exc}") from exc

    return _fetch_servers_python(limit)


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
    cli = _find_ookla_cli()
    if cli:
        try:
            return _run_ookla_cli(cli, server_id=server_id,
                                  on_progress=on_progress, on_sample=on_sample)
        except Exception:
            pass

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
