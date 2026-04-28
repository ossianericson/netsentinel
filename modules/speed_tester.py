"""
Speed Tester — fetches Ookla-compatible servers via speedtest-cli and runs
download / upload / ping measurements.

Public API
──────────
fetch_servers(limit)  → list[SpeedServer]
run_test(server_id, on_progress)  → SpeedTestResult
"""

from __future__ import annotations

import datetime
import io
import math
import ssl
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# ── Windowed-exe stdout/stderr guard ─────────────────────────────────────────
# In a PyInstaller windowed (no-console) exe, sys.stdout and sys.stderr are
# None.  speedtest-cli calls sys.stderr.fileno() internally which raises
# AttributeError: 'NoneType' object has no attribute 'fileno'.
# Replace None streams with a null sink so the library can initialise safely.
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

# ── Python 3.12+ compatibility patch for speedtest-cli ───────────────────────
# speedtest-cli 2.1.x calls ssl.wrap_socket() which was removed in Python 3.12.
# Restore it as a shim so the library can initialise without crashing.
if not hasattr(ssl, "wrap_socket"):
    def _wrap_socket_shim(sock, *args, **kwargs):  # type: ignore[override]
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        server_hostname = kwargs.pop("server_hostname", None)
        return ctx.wrap_socket(sock, server_hostname=server_hostname, **kwargs)
    ssl.wrap_socket = _wrap_socket_shim  # type: ignore[attr-defined]


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SpeedServer:
    id: str
    name: str           # sponsor / ISP name
    city: str           # location name
    country: str
    host: str
    latency_ms: float   # ping in ms; 0.0 if not yet measured


@dataclass
class SpeedTestResult:
    download_mbps: float
    upload_mbps: float
    ping_ms: float
    server_name: str
    server_city: str
    server_country: str
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds")
    )


# ── Logarithmic scale helper (matches Ookla's gauge) ─────────────────────────

def speed_to_fraction(speed_mbps: float, max_mbps: float = 1000.0) -> float:
    """Map a speed (Mbps) to a 0–1 gauge fill fraction using log₁₀ scale."""
    if speed_mbps <= 0 or max_mbps <= 0:
        return 0.0
    return min(
        math.log10(speed_mbps + 1) / math.log10(max_mbps + 1),
        1.0,
    )


# ── Server fetch ──────────────────────────────────────────────────────────────

def fetch_servers(limit: int = 20) -> List[SpeedServer]:
    """
    Fetch nearby Ookla-compatible servers.
    Pings each server to determine latency; returns list sorted by latency.
    Raises RuntimeError on network failure.
    """
    try:
        import speedtest as _st
    except ImportError:
        raise RuntimeError(
            "speedtest-cli is not installed. "
            "Run: pip install speedtest-cli"
        )

    import socket as _socket
    _prev_timeout = _socket.getdefaulttimeout()
    _socket.setdefaulttimeout(30)   # prevent hung sockets that cause fileno() errors
    try:
        try:
            client = _st.Speedtest(secure=True)
        except AttributeError:
            client = _st.Speedtest(secure=False)
        client.get_servers()
        closest = client.get_closest_servers(limit=limit)
        # Pings servers and populates .latency on each dict
        try:
            client.get_best_server(closest)
        except Exception:
            pass  # latency values may be partial; still usable

        servers: List[SpeedServer] = []
        for s in sorted(closest, key=lambda x: float(x.get("latency") or 9999)):
            servers.append(SpeedServer(
                id=str(s.get("id", "")),
                name=s.get("sponsor") or s.get("name") or "Unknown",
                city=s.get("name") or "",
                country=s.get("country") or "",
                host=s.get("host") or "",
                latency_ms=round(float(s.get("latency") or 0.0), 1),
            ))
        return servers

    except AttributeError as exc:
        # speedtest-cli can leave sockets in a None/_closed state on some
        # Windows/SSL configs; the resulting fileno() call raises AttributeError.
        raise RuntimeError(
            f"Speed test socket error (connection closed unexpectedly): {exc}"
        ) from exc
    except _st.ConfigRetrievalError as exc:
        raise RuntimeError(f"Cannot reach Speedtest servers: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Server fetch failed: {exc}") from exc
    finally:
        _socket.setdefaulttimeout(_prev_timeout)


# ── Test runner ───────────────────────────────────────────────────────────────

def run_test(
    server_id: Optional[str] = None,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> SpeedTestResult:
    """
    Run a full speed test against a selected server (or auto-select best).

    on_progress(phase, message) is called at key milestones:
        phase "connecting"  — establishing connection to server
        phase "ping"        — ping measured, message contains value
        phase "download"    — download phase starting
        phase "upload"      — upload phase starting
        phase "done"        — test complete
    """
    try:
        import speedtest as _st
    except ImportError:
        raise RuntimeError(
            "speedtest-cli is not installed. Run: pip install speedtest-cli"
        )

    def _cb(phase: str, msg: str) -> None:
        if on_progress:
            on_progress(phase, msg)

    import socket as _socket
    _prev_timeout = _socket.getdefaulttimeout()
    _socket.setdefaulttimeout(30)   # prevent hung sockets that cause fileno() errors
    try:
        _cb("connecting", "Connecting to Speedtest servers…")
        # secure=True can trigger the fileno() bug on some Windows/SSL configs;
        # fall back to plain HTTP if the SSL init fails.
        try:
            client = _st.Speedtest(secure=True)
        except AttributeError:
            client = _st.Speedtest(secure=False)

        if server_id:
            client.get_servers([int(server_id)])
        else:
            client.get_servers()

        best = client.get_best_server()
        _cb(
            "ping",
            f"Ping: {best.get('latency', 0):.0f} ms → "
            f"{best.get('sponsor', '')} ({best.get('name', '')})",
        )

        _cb("download", "Measuring download speed…")
        download_bps = client.download(threads=4)

        _cb("upload", "Measuring upload speed…")
        upload_bps = client.upload(threads=2)

        _cb("done", "Test complete")

        res = client.results
        return SpeedTestResult(
            download_mbps=round(download_bps / 1_000_000, 2),
            upload_mbps=round(upload_bps / 1_000_000, 2),
            ping_ms=round(float(res.ping), 1),
            server_name=best.get("sponsor") or "",
            server_city=best.get("name") or "",
            server_country=best.get("country") or "",
        )

    except AttributeError as exc:
        # speedtest-cli can leave sockets in a None/_closed state; the resulting
        # fileno() call raises AttributeError.  Map to a friendly RuntimeError.
        raise RuntimeError(
            f"Speed test socket error (connection closed unexpectedly): {exc}"
        ) from exc
    except _st.ConfigRetrievalError as exc:
        raise RuntimeError(f"Cannot reach Speedtest servers: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Speed test failed: {exc}") from exc
    finally:
        _socket.setdefaulttimeout(_prev_timeout)  # restore caller's socket timeout
