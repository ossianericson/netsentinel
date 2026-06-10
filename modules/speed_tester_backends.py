"""
Speed test data types and backend implementations (Ookla CLI, speedtest-cli, pure-Python HTTP).

Extracted from modules/speed_tester.py (S20-7 sprint split).
All public names remain importable from modules.speed_tester for
backwards compatibility via re-exports in that module.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import json
import logging
import os
import platform
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

_log = logging.getLogger(__name__)
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional


# ── Data classes (public) ─────────────────────────────────────────────────────

@dataclass
class SpeedServer:
    id: str
    name: str
    city: str
    country: str
    host: str
    latency_ms: float


@dataclass
class SpeedTestResult:
    download_mbps: float
    upload_mbps: float
    ping_ms: float
    server_name: str
    server_city: str
    server_country: str
    backend: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds")
    )
    modem_signal: Optional[dict] = None


# ─────────────────────────────────────────────────────────────────────────────
# BACKEND 1 — Ookla CLI binary
# ─────────────────────────────────────────────────────────────────────────────

def _find_ookla_cli() -> Optional[Path]:
    """
    Locate the Ookla CLI binary (speedtest.exe / speedtest).

    Search order:
      1. Directory of the running executable (portable / PyInstaller)
      2. %LOCALAPPDATA%\\NetSentinel\\           (manual drop-in)
      3. %LOCALAPPDATA%\\Microsoft\\WinGet\\Links\\ (winget per-user symlink dir)
      4. %LOCALAPPDATA%\\Microsoft\\WinGet\\Packages\\Ookla.*\\ (version-suffixed)
      5. C:\\Program Files\\Ookla\\Speedtest CLI\\  (MSI machine-wide)
      6. C:\\Program Files (x86)\\Ookla\\Speedtest CLI\\ (MSI 32-bit)
      7. /usr/local/bin, /opt/homebrew/bin, /usr/bin (macOS / Linux)
      8. shutil.which() (anything else on PATH)
    """
    is_windows = platform.system() == "Windows"
    exe_name = "speedtest.exe" if is_windows else "speedtest"

    candidates: List[Path] = []

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / exe_name)
    else:
        candidates.append(Path(__file__).resolve().parent.parent / exe_name)

    if is_windows:
        localappdata = os.environ.get("LOCALAPPDATA", "")
        if localappdata:
            la = Path(localappdata)
            candidates.append(la / "NetSentinel" / exe_name)
            candidates.append(la / "Microsoft" / "WinGet" / "Links" / exe_name)
            winget_pkg_base = la / "Microsoft" / "WinGet" / "Packages"
            if winget_pkg_base.is_dir():
                for pkg_dir in winget_pkg_base.glob("Ookla.*"):
                    candidates.append(pkg_dir / exe_name)
        candidates.append(Path("C:/Program Files/Ookla/Speedtest CLI") / exe_name)
        candidates.append(Path("C:/Program Files (x86)/Ookla/Speedtest CLI") / exe_name)
    else:
        for unix_dir in ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin"):
            candidates.append(Path(unix_dir) / exe_name)

    found = shutil.which(exe_name)
    if found:
        candidates.append(Path(found))

    for p in candidates:
        try:
            if p.exists() and p.is_file():
                return p
        except OSError as exc:
            _log.debug("CLI path check failed for %s: %s", p, exc)
    return None


def _run_ookla_cli(
    binary: Path,
    server_id: Optional[str],
    on_progress: Optional[Callable[[str, str], None]],
    on_sample: Optional[Callable[[float, str], None]] = None,
) -> SpeedTestResult:
    """Execute the Ookla CLI and parse its streaming JSON-Lines output."""
    import queue as _queue

    def _cb(phase: str, msg: str) -> None:
        if on_progress:
            on_progress(phase, msg)

    cmd = [str(binary), "--format=jsonl", "--accept-license", "--accept-gdpr"]
    if server_id:
        cmd += ["--server-id", str(server_id)]

    _cb("connecting", "Connecting via Ookla CLI…")

    popen_kwargs: dict = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if platform.system() == "Windows":
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(cmd, text=True, **popen_kwargs)
    except FileNotFoundError:
        raise RuntimeError(f"Ookla CLI binary not found: {binary}")

    line_q: _queue.Queue = _queue.Queue()

    def _reader(pipe: object, q: _queue.Queue) -> None:
        for ln in pipe:  # type: ignore[union-attr]
            q.put(ln)
        q.put(None)

    reader = threading.Thread(target=_reader, args=(proc.stdout, line_q), daemon=True)
    reader.start()

    result_data: dict = {}
    current_phase = "connecting"
    deadline = time.monotonic() + 130

    try:
        while True:
            try:
                raw = line_q.get(timeout=1.0)
            except _queue.Empty:
                if time.monotonic() > deadline:
                    proc.kill()
                    raise RuntimeError("Ookla CLI timed out (>120 s)")
                continue

            if raw is None:
                break

            line = raw.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = obj.get("type", "")

            if event_type == "testStart":
                srv = obj.get("server") or {}
                _cb("ping", f"Server: {srv.get('name', '')} ({srv.get('location', '')})")
            elif event_type == "ping":
                ping_ms = float((obj.get("ping") or {}).get("latency") or 0)
                _cb("ping", f"Ping: {ping_ms:.0f} ms")
            elif event_type == "download":
                if current_phase != "download":
                    current_phase = "download"
                    _cb("download", "Measuring download speed…")
                bw = float((obj.get("download") or {}).get("bandwidth") or 0)
                mbps = bw * 8 / 1_000_000
                if mbps > 0 and on_sample:
                    on_sample(mbps, "download")
            elif event_type == "upload":
                if current_phase != "upload":
                    current_phase = "upload"
                    _cb("upload", "Measuring upload speed…")
                bw = float((obj.get("upload") or {}).get("bandwidth") or 0)
                mbps = bw * 8 / 1_000_000
                if mbps > 0 and on_sample:
                    on_sample(mbps, "upload")
            elif event_type == "result":
                result_data = obj
                _cb("done", "Test complete")
            elif event_type == "error":
                raise RuntimeError(f"Ookla CLI error: {obj.get('message') or line}")

        proc.wait(timeout=5)

    finally:
        reader.join(timeout=2)

    if not result_data:
        stderr_text = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"Ookla CLI returned no result. stderr: {stderr_text[:300]}")

    ping_ms = float((result_data.get("ping") or {}).get("latency") or 0)
    dl_bps  = float((result_data.get("download") or {}).get("bandwidth") or 0)
    ul_bps  = float((result_data.get("upload")   or {}).get("bandwidth") or 0)
    srv     = result_data.get("server") or {}

    return SpeedTestResult(
        download_mbps=round(dl_bps * 8 / 1_000_000, 2),
        upload_mbps=round(ul_bps * 8 / 1_000_000, 2),
        ping_ms=round(ping_ms, 1),
        server_name=srv.get("name") or "",
        server_city=srv.get("location") or srv.get("name") or "",
        server_country=srv.get("country") or "",
        backend="Ookla CLI",
    )


# ─────────────────────────────────────────────────────────────────────────────
# BACKEND 2 — speedtest-cli library
# ─────────────────────────────────────────────────────────────────────────────

def _patch_ssl_for_312() -> None:
    """Restore ssl.wrap_socket() removed in Python 3.12 for speedtest-cli 2.1.x."""
    if not hasattr(ssl, "wrap_socket"):
        def _wrap_shim(sock, *args, **kwargs):  # type: ignore[override]
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            server_hostname = kwargs.pop("server_hostname", None)
            return ctx.wrap_socket(sock, server_hostname=server_hostname, **kwargs)
        ssl.wrap_socket = _wrap_shim  # type: ignore[attr-defined]


def _run_speedtest_cli(
    server_id: Optional[str],
    on_progress: Optional[Callable[[str, str], None]],
    on_sample: Optional[Callable[[float, str], None]] = None,
) -> SpeedTestResult:
    """Run speedtest-cli with 8 download / 4 upload threads."""
    try:
        import speedtest as _st
    except ImportError:
        raise RuntimeError("speedtest-cli is not installed (pip install speedtest-cli)")

    _patch_ssl_for_312()

    def _cb(phase: str, msg: str) -> None:
        if on_progress:
            on_progress(phase, msg)

    import socket as _socket
    _prev = _socket.getdefaulttimeout()
    _socket.setdefaulttimeout(30)
    try:
        _cb("connecting", "Connecting to Speedtest servers…")
        try:
            client = _st.Speedtest(secure=True)
        except AttributeError:
            client = _st.Speedtest(secure=False)

        if server_id:
            client.get_servers([int(server_id)])
        else:
            client.get_servers()

        best = client.get_best_server()
        _cb("ping", f"Ping: {best.get('latency', 0):.0f} ms → {best.get('sponsor', '')} ({best.get('name', '')})")

        _cb("download", "Measuring download speed (8 streams)…")
        dl_bps = client.download(threads=8)

        _cb("upload", "Measuring upload speed (4 streams)…")
        ul_bps = client.upload(threads=4, pre_allocate=False)

        _cb("done", "Test complete")

        res = client.results
        return SpeedTestResult(
            download_mbps=round(dl_bps / 1_000_000, 2),
            upload_mbps=round(ul_bps / 1_000_000, 2),
            ping_ms=round(float(res.ping), 1),
            server_name=best.get("sponsor") or "",
            server_city=best.get("name") or "",
            server_country=best.get("country") or "",
            backend="speedtest-cli",
        )
    except AttributeError as exc:
        raise RuntimeError(f"Speed test socket error: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"speedtest-cli failed: {exc}") from exc
    finally:
        _socket.setdefaulttimeout(_prev)


# ─────────────────────────────────────────────────────────────────────────────
# BACKEND 3 — Pure-Python multithreaded HTTP streams
# ─────────────────────────────────────────────────────────────────────────────

_HTTP_UA    = "speedtest-cli/2.1.3"
_HTTP_TIMEOUT = 20
_SSL_CTX: Optional[ssl.SSLContext] = None


def _get_ssl_ctx() -> ssl.SSLContext:
    global _SSL_CTX
    if _SSL_CTX is None:
        _SSL_CTX = ssl.create_default_context()
        _SSL_CTX.check_hostname = False
        _SSL_CTX.verify_mode = ssl.CERT_NONE
    return _SSL_CTX


def _http_get(url: str, timeout: int = _HTTP_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _HTTP_UA})
    with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=timeout) as r:
        return r.read()


def _fetch_client_coords() -> tuple:
    """Return (lat, lon) strings from speedtest.net config, or (None, None) on failure."""
    try:
        import xml.etree.ElementTree as _ET
        xml_bytes = _http_get(
            "https://www.speedtest.net/speedtest-config.php", timeout=8
        )
        root = _ET.fromstring(xml_bytes)
        client = root.find("client")
        if client is not None:
            lat = client.get("lat")
            lon = client.get("lon")
            if lat and lon:
                return lat, lon
    except Exception:
        pass  # non-fatal — server list will fall back to IP-based geo
    return None, None


def _fetch_servers_python(limit: int = 10) -> List[SpeedServer]:
    """Fetch Ookla servers via their JSON API, geo-filtered by client coordinates."""
    lat, lon = _fetch_client_coords()
    if lat and lon:
        url = (
            f"https://www.speedtest.net/api/js/servers"
            f"?engine=js&https_functional=true&limit={limit}&lat={lat}&lon={lon}"
        )
    else:
        url = (
            f"https://www.speedtest.net/api/js/servers"
            f"?engine=js&https_functional=true&limit={limit}"
        )
    try:
        data = json.loads(_http_get(url, timeout=15))
    except Exception as exc:
        raise RuntimeError(f"Cannot reach Speedtest server list: {exc}") from exc

    servers: List[SpeedServer] = []
    for s in data[:limit]:
        servers.append(SpeedServer(
            id=str(s.get("id", "")),
            name=s.get("sponsor") or s.get("name") or "Unknown",
            city=s.get("name") or "",
            country=s.get("country") or "",
            host=s.get("host") or "",
            latency_ms=0.0,
        ))

    def _ping(server: SpeedServer) -> None:
        try:
            import socket as _sock
            hostname = server.host.split(":")[0]
            port = int(server.host.split(":")[1]) if ":" in server.host else 8080
            times: list = []
            for _ in range(3):
                t0 = time.perf_counter()
                s = _sock.create_connection((hostname, port), timeout=5)
                s.close()
                times.append((time.perf_counter() - t0) * 1000)
                time.sleep(0.02)
            server.latency_ms = round(sum(times) / len(times), 1)
        except Exception:
            server.latency_ms = 9999.0

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(_ping, servers))

    return sorted(servers, key=lambda s: s.latency_ms)


def _download_worker(url: str, stop_event: threading.Event, deadline: float, counter: list) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _HTTP_UA})
    while not stop_event.is_set() and time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=15) as resp:
                while not stop_event.is_set() and time.monotonic() < deadline:
                    chunk = resp.read(131_072)
                    if not chunk:
                        break
                    counter[0] += len(chunk)
        except Exception:
            if not stop_event.is_set():
                time.sleep(0.1)


def _upload_worker(url: str, stop_event: threading.Event, deadline: float, counter: list) -> None:
    payload = os.urandom(1_048_576)
    while not stop_event.is_set() and time.monotonic() < deadline:
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/octet-stream", "User-Agent": _HTTP_UA},
                method="POST",
            )
            with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=15):
                counter[0] += len(payload)
        except Exception:
            if not stop_event.is_set():
                time.sleep(0.1)


def _measure_download_python(
    server_host: str,
    num_threads: int = 16,
    duration_s: float = 10.0,
    on_sample: Optional[Callable[[float], None]] = None,
) -> float:
    """Download with `num_threads` parallel TCP streams. Returns Mbps."""
    hostname = server_host.split(":")[0]
    port     = server_host.split(":")[1] if ":" in server_host else "8080"
    base_url = f"https://{hostname}:{port}"

    urls = [
        f"{base_url}/download?nocache={int(time.time())+i}&size={350 * (1 + i % 8) * 1024}"
        for i in range(num_threads)
    ]

    stop     = threading.Event()
    total    = [0]
    t0       = time.monotonic()
    deadline = t0 + duration_s

    def _sampler() -> None:
        last_bytes = 0
        last_t     = time.monotonic()
        while not stop.is_set() and time.monotonic() < deadline:
            time.sleep(0.3)
            now   = time.monotonic()
            cur   = total[0]
            dt    = now - last_t
            if dt > 0:
                mbps = max(0.0, ((cur - last_bytes) * 8) / dt / 1_000_000)
                on_sample(mbps)
            last_bytes = cur
            last_t     = now

    if on_sample:
        threading.Thread(target=_sampler, daemon=True).start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as ex:
        futs = [ex.submit(_download_worker, urls[i], stop, deadline, total)
                for i in range(num_threads)]
        concurrent.futures.wait(futs, timeout=duration_s + 5)
        stop.set()

    elapsed = max(time.monotonic() - t0, 0.001)
    return round((total[0] * 8) / elapsed / 1_000_000, 2)


def _measure_upload_python(
    server_host: str,
    num_threads: int = 8,
    duration_s: float = 8.0,
    on_sample: Optional[Callable[[float], None]] = None,
) -> float:
    """Upload with `num_threads` parallel TCP streams. Returns Mbps."""
    hostname = server_host.split(":")[0]
    port     = server_host.split(":")[1] if ":" in server_host else "8080"
    url      = f"https://{hostname}:{port}/upload"

    stop     = threading.Event()
    total    = [0]
    t0       = time.monotonic()
    deadline = t0 + duration_s

    def _sampler() -> None:
        last_bytes = 0
        last_t     = time.monotonic()
        while not stop.is_set() and time.monotonic() < deadline:
            time.sleep(0.3)
            now   = time.monotonic()
            cur   = total[0]
            dt    = now - last_t
            if dt > 0:
                mbps = max(0.0, ((cur - last_bytes) * 8) / dt / 1_000_000)
                on_sample(mbps)
            last_bytes = cur
            last_t     = now

    if on_sample:
        threading.Thread(target=_sampler, daemon=True).start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as ex:
        futs = [ex.submit(_upload_worker, url, stop, deadline, total)
                for _ in range(num_threads)]
        concurrent.futures.wait(futs, timeout=duration_s + 5)
        stop.set()

    elapsed = max(time.monotonic() - t0, 0.001)
    return round((total[0] * 8) / elapsed / 1_000_000, 2)


def _run_python_test(
    server_id: Optional[str],
    on_progress: Optional[Callable[[str, str], None]],
    on_sample: Optional[Callable[[float, str], None]] = None,
) -> SpeedTestResult:
    """Pure-Python 16-stream speed test — no binary dependencies."""
    def _cb(phase: str, msg: str) -> None:
        if on_progress:
            on_progress(phase, msg)

    _cb("connecting", "Fetching nearest Ookla servers…")

    servers = _fetch_servers_python(limit=10)
    if not servers:
        raise RuntimeError("No speed test servers available")

    server = None
    if server_id:
        server = next((s for s in servers if s.id == server_id), None)
    server = server or servers[0]

    ping_ms = server.latency_ms if server.latency_ms < 9999 else 0.0
    _cb("ping", f"Ping: {ping_ms:.0f} ms → {server.name} ({server.city})")

    dl_sample = (lambda mbps: on_sample(mbps, "download")) if on_sample else None
    ul_sample = (lambda mbps: on_sample(mbps, "upload"))   if on_sample else None

    _cb("download", "Measuring download speed (16 streams)…")
    dl = _measure_download_python(server.host, num_threads=16, duration_s=10.0, on_sample=dl_sample)

    _cb("upload", "Measuring upload speed (8 streams)…")
    ul = _measure_upload_python(server.host, num_threads=8, duration_s=8.0, on_sample=ul_sample)

    _cb("done", "Test complete")

    return SpeedTestResult(
        download_mbps=dl,
        upload_mbps=ul,
        ping_ms=round(ping_ms, 1),
        server_name=server.name,
        server_city=server.city,
        server_country=server.country,
        backend="Pure-Python",
    )
