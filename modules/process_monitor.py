"""
modules/process_monitor.py — Process-to-Socket Mapping
========================================================
Maps every active TCP/UDP connection on the local machine to the owning
Windows process (exe name + path) and optionally geo-locates the remote IP.

Key function
------------
    snapshot() -> List[Connection]

No admin privileges are required for own-user connections.
Remote-process connections (SYSTEM, other users) return the PID only when
the process object cannot be opened; this is expected and handled gracefully.

Geo-lookup uses ip-api.com (free, no key required, rate-limited to ~45 req/min).
Results are cached in-process per IP for the session lifetime.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import psutil
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Connection:
    pid:          int
    exe_name:     str          # e.g. "chrome.exe"  or  "<unknown>"
    exe_path:     str          # full path or ""
    proto:        str          # "TCP" | "UDP"
    local_addr:   str          # "127.0.0.1:54321"
    remote_addr:  str          # "142.250.74.46:443" or ""
    remote_ip:    str          # bare IP or ""
    remote_port:  int          # 0 if unavailable
    status:       str          # "ESTABLISHED" | "LISTEN" | "TIME_WAIT" | …
    country:      str = ""     # filled by geo-lookup, "" until enriched
    city:         str = ""
    flag:         str = ""     # 2-char country code, e.g. "US"
    is_local:     bool = False # True if remote is RFC-1918 / loopback


# ── Geo-lookup cache ──────────────────────────────────────────────────────────

_GEO_CACHE:   dict[str, dict] = {}
_GEO_LOCK     = threading.Lock()
_GEO_LAST_REQ = 0.0
_GEO_MIN_GAP  = 1.4           # seconds between requests (≤45/min)


def _is_private(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def geo_lookup(ip: str, timeout: float = 3.0) -> dict:
    """
    Return geo dict with keys: country, countryCode, city, org.
    Returns {} on failure or for private IPs.
    """
    if not ip or _is_private(ip):
        return {}
    with _GEO_LOCK:
        if ip in _GEO_CACHE:
            return _GEO_CACHE[ip]
        global _GEO_LAST_REQ
        gap = time.monotonic() - _GEO_LAST_REQ
        if gap < _GEO_MIN_GAP:
            time.sleep(_GEO_MIN_GAP - gap)
        try:
            import urllib.request, json
            url = f"http://ip-api.com/json/{ip}?fields=country,countryCode,city,org,status"
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            _GEO_LAST_REQ = time.monotonic()
            if data.get("status") == "success":
                _GEO_CACHE[ip] = data
                return data
        except Exception:
            pass
        _GEO_CACHE[ip] = {}
        return {}


# ── Core snapshot function ────────────────────────────────────────────────────

def snapshot(
    include_listen: bool = False,
    geo_enrich: bool = False,
    geo_timeout: float = 2.0,
) -> list[Connection]:
    """
    Return a list of active connections from the local machine.

    Parameters
    ----------
    include_listen  : include LISTEN/BOUND sockets (default False)
    geo_enrich      : call ip-api for each distinct public remote IP (slow)
    geo_timeout     : per-request timeout for geo calls
    """
    if not _PSUTIL_OK:
        return []

    # Build PID → process info map upfront (one pass, much faster than
    # calling psutil.Process() per connection)
    pid_info: dict[int, tuple[str, str]] = {}   # pid -> (name, exe)
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            info = proc.info
            pid_info[info["pid"]] = (
                info.get("name") or "<unknown>",
                info.get("exe")  or "",
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    results: list[Connection] = []

    try:
        conns = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        # On Windows, non-admin cannot enumerate all-user connections;
        # fall back to per-process iteration which only gives own-user
        conns = []
        for proc in psutil.process_iter(["pid"]):
            try:
                conns.extend(proc.connections(kind="inet"))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    seen: set[tuple] = set()

    for c in conns:
        status = (c.status or "").upper()

        # Filter out LISTEN sockets unless requested
        if not include_listen and status in ("LISTEN", "NONE", ""):
            continue

        # Build address strings
        local  = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
        remote_ip   = c.raddr.ip   if c.raddr else ""
        remote_port = c.raddr.port if c.raddr else 0
        remote = f"{remote_ip}:{remote_port}" if remote_ip else ""

        # Dedup by (proto, local, remote, pid)
        proto = "UDP" if c.type == socket.SOCK_DGRAM else "TCP"
        key   = (proto, local, remote, c.pid or 0)
        if key in seen:
            continue
        seen.add(key)

        pid = c.pid or 0
        exe_name, exe_path = pid_info.get(pid, ("<unknown>", ""))

        conn = Connection(
            pid=pid,
            exe_name=exe_name,
            exe_path=exe_path,
            proto=proto,
            local_addr=local,
            remote_addr=remote,
            remote_ip=remote_ip,
            remote_port=remote_port,
            status=status,
            is_local=_is_private(remote_ip) if remote_ip else False,
        )
        results.append(conn)

    # Geo enrichment (optional, slow — runs sequentially to respect rate limit)
    if geo_enrich:
        public_ips = {c.remote_ip for c in results
                      if c.remote_ip and not c.is_local}
        geo_map: dict[str, dict] = {}
        for ip in public_ips:
            geo_map[ip] = geo_lookup(ip, timeout=geo_timeout)
        for conn in results:
            g = geo_map.get(conn.remote_ip, {})
            if g:
                conn.country = g.get("country", "")
                conn.city    = g.get("city", "")
                conn.flag    = g.get("countryCode", "")

    # Sort: established first, then by exe name
    results.sort(key=lambda c: (0 if c.status == "ESTABLISHED" else 1,
                                c.exe_name.lower()))
    return results


def is_available() -> bool:
    return _PSUTIL_OK
