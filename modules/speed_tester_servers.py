"""
Speed test server discovery and latency probing (S20-7b split from speed_tester_backends.py).

Responsibilities:
  - GeoLite2 offline coordinate lookup (_geolite2_coords)
  - Client coordinate resolution with multi-source cascade + session cache (_fetch_client_coords)
  - Ookla server list fetch + parallel TCP latency probe (_fetch_servers_python)

Imported by modules/speed_tester.py via the public fetch_servers() function.
Download/upload/ping test backends stay in speed_tester_backends.py.
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
import json
import time
from typing import List

from modules.speed_tester_backends import SpeedServer, _http_get, _HTTP_UA
from modules.utils import get_app_data_dir

_SERVERS_CACHE_FILENAME = "speedtest_servers_cache.json"


# Session-level cache: public IP rarely changes; avoid repeated network lookups.
_coords_cache: tuple = (None, None)


def _geolite2_coords(ip: str) -> tuple:
    """Return (lat_str, lon_str) from the local GeoLite2-City database, or (None, None).

    Uses the shared GeoLocator singleton (same instance as the Geolocation Map page).
    Falls back gracefully when the .mmdb file is absent or maxminddb is not installed.
    """
    if not ip:
        return None, None
    try:
        from modules.geo_locator import get_locator
        locator = get_locator()
        if not locator.is_available:
            return None, None
        result = locator.lookup(ip)
        if result.latitude and result.longitude and not result.is_bogon:
            return str(result.latitude), str(result.longitude)
    except Exception:
        pass  # non-fatal — GeoLite2 db absent or maxminddb not installed
    return None, None


def _fetch_client_coords() -> tuple:
    """Return (lat, lon) strings, or (None, None) on failure.

    Source priority (best accuracy first):
      1. GeoLite2 offline db lookup of our public IP  — city-level, instant, no extra network
      2. speedtest.net config endpoint                — HTTPS, 3 s timeout; also gives our IP
      3. ip-api.com free JSON endpoint                — HTTP, 3 s timeout; also gives our IP

    For steps 1 and 2, the public IP is obtained from speedtest.net (already parsed from XML).
    For step 3, ip-api.com returns both the IP and coordinates in one call.

    Results are cached for the process lifetime — the public IP never changes mid-session.
    """
    global _coords_cache
    if _coords_cache[0]:
        return _coords_cache

    stn_ip: str = ""
    stn_lat: str = ""
    stn_lon: str = ""

    # ── Steps 1+2: speedtest.net config gives us IP + their lat/lon ─────────────
    try:
        import xml.etree.ElementTree as _ET
        xml_bytes = _http_get(
            "https://www.speedtest.net/speedtest-config.php", timeout=3
        )
        root = _ET.fromstring(xml_bytes)
        client = root.find("client")
        if client is not None:
            stn_ip = client.get("ip") or ""
            stn_lat = client.get("lat") or ""
            stn_lon = client.get("lon") or ""
    except Exception:
        pass  # try fallbacks below

    if stn_ip:
        geo = _geolite2_coords(stn_ip)
        if geo[0]:
            _coords_cache = geo
            return _coords_cache

    if stn_lat and stn_lon:
        _coords_cache = (stn_lat, stn_lon)
        return _coords_cache

    # ── Step 3: ip-api.com (HTTP, no SSL needed) ─────────────────────────────
    try:
        import urllib.request as _ureq
        req = _ureq.Request(
            "http://ip-api.com/json?fields=status,lat,lon,query",
            headers={"User-Agent": _HTTP_UA},
        )
        with _ureq.urlopen(req, timeout=3) as r:
            data = json.loads(r.read())
        if data.get("status") == "success":
            api_ip = data.get("query") or ""
            lat = str(data.get("lat") or "")
            lon = str(data.get("lon") or "")
            if lat and lon and float(lat) != 0.0:
                geo = _geolite2_coords(api_ip) if api_ip else (None, None)
                result = geo if geo[0] else (lat, lon)
                _coords_cache = result
                return _coords_cache
    except Exception:
        pass  # non-fatal — server list will fall back to IP-based geo on Ookla's side

    return None, None


def _fetch_servers_python(
    limit: int = 10,
    on_status: object = None,
) -> List[SpeedServer]:
    """Fetch Ookla servers via their JSON API, geo-filtered by client coordinates."""
    _s = on_status if callable(on_status) else (lambda _: None)

    _s("Looking up your location…")
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

    _s("Finding nearby servers…")
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

    _s("Measuring server latency…")

    def _ping(server: SpeedServer) -> None:
        try:
            import socket as _sock
            hostname = server.host.split(":")[0]
            port = int(server.host.split(":")[1]) if ":" in server.host else 8080
            times: list = []
            for _ in range(2):  # 2 attempts at 2 s each; parallel across servers
                t0 = time.perf_counter()
                s = _sock.create_connection((hostname, port), timeout=2)
                s.close()
                times.append((time.perf_counter() - t0) * 1000)
                time.sleep(0.02)
            server.latency_ms = round(sum(times) / len(times), 1)
        except Exception:
            server.latency_ms = 9999.0

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(_ping, servers))

    return sorted(servers, key=lambda s: s.latency_ms)


def _save_servers_cache(servers: List[SpeedServer]) -> None:
    """Persist the last-good server list so a future fetch outage can fall back to it."""
    try:
        path = get_app_data_dir() / _SERVERS_CACHE_FILENAME
        data = [dataclasses.asdict(s) for s in servers]
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass  # non-fatal — cache is a best-effort convenience


def _load_servers_cache() -> List[SpeedServer]:
    """Return the last cached server list, or [] if none exists or it is unreadable."""
    try:
        path = get_app_data_dir() / _SERVERS_CACHE_FILENAME
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [SpeedServer(**d) for d in data]
    except Exception:
        return []  # non-fatal — corrupt or missing cache treated as no cache
