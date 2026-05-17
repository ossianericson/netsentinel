"""
geo_locator.py — GeoLite2 IP geolocation (fully local, no external API calls).

Usage
─────
  from modules.geo_locator import GeoLocator, GeoResult, db_path, download_db

  loc = GeoLocator()          # auto-opens the .mmdb if present
  result = loc.lookup("1.1.1.1")

Database
────────
  The MaxMind GeoLite2-City.mmdb file is stored under:
      get_app_data_dir() / "GeoLite2-City.mmdb"

  NetSentinel does NOT bundle the .mmdb file (MaxMind licence requires
  separate attribution).  The user can:
    1. Download it manually from maxmind.com (free account required) and
       place it in the path returned by db_path().
    2. Use the in-app "Download DB" button, which calls download_db_permalink()
       with a permalink URL that the user pastes from their MaxMind account.

  The module works in degraded mode (country="" lon=0 lat=0) when no .mmdb
  is present, so the rest of the app is never blocked.

Privacy / Security
──────────────────
  - No IP addresses are ever sent to any external service by this module.
  - All lookups are purely in-process reads from the local .mmdb file.
  - The optional permalink download contacts maxmind.com over HTTPS only to
    fetch the database file itself; the URL is user-supplied.
"""

from __future__ import annotations

import ipaddress
import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import urllib.request

from modules.utils import get_app_data_dir

# Optional — guarded import; present after `pip install maxminddb`
try:
    import maxminddb
    _MAXMIND_OK = True
except ImportError:
    _MAXMIND_OK = False


# ── Paths ─────────────────────────────────────────────────────────────────────

def db_path() -> Path:
    """Return the expected path for GeoLite2-City.mmdb."""
    return get_app_data_dir() / "GeoLite2-City.mmdb"


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class GeoResult:
    ip: str
    country: str = ""          # ISO-3166 alpha-2, e.g. "US"
    country_name: str = ""     # e.g. "United States"
    city: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    asn: str = ""              # e.g. "AS13335"
    org: str = ""              # e.g. "Cloudflare, Inc."
    is_bogon: bool = False     # RFC 1918 / loopback / link-local / CGNAT


# ── Bogon check ───────────────────────────────────────────────────────────────

_BOGON_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_bogon(ip: str) -> bool:
    """Return True for RFC 1918 / loopback / link-local / CGNAT addresses."""
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _BOGON_NETS)
    except ValueError:
        return False


# ── GeoLocator ────────────────────────────────────────────────────────────────

class GeoLocator:
    """
    Thread-safe GeoLite2 lookup engine.

    Uses maxminddb (pure Python, no C extension required).
    Falls back gracefully when the .mmdb file is absent.
    """

    def __init__(self, mmdb_path: Optional[Path] = None) -> None:
        self._path = mmdb_path or db_path()
        self._db: Optional[object] = None   # maxminddb.Reader
        self._lock = threading.Lock()
        self._open()

    def _open(self) -> None:
        if not _MAXMIND_OK:
            return
        if not self._path.exists():
            return
        try:
            self._db = maxminddb.open_database(str(self._path))
        except Exception:
            self._db = None

    def reload(self) -> None:
        """Re-open the database (call after the user installs the .mmdb)."""
        with self._lock:
            if self._db is not None:
                try:
                    self._db.close()
                except Exception:
                    pass
            self._db = None
        self._open()

    @property
    def is_available(self) -> bool:
        return self._db is not None

    def lookup(self, ip: str) -> GeoResult:
        """
        Resolve an IP address to GeoResult.
        Returns a GeoResult with is_bogon=True for private/loopback addresses.
        Returns a zero-filled GeoResult if the .mmdb is not loaded.
        """
        bogon = is_bogon(ip)
        if bogon:
            return GeoResult(ip=ip, is_bogon=True)

        with self._lock:
            db = self._db

        if db is None:
            return GeoResult(ip=ip)

        try:
            record = db.get(ip)
        except Exception:
            return GeoResult(ip=ip)

        if record is None:
            return GeoResult(ip=ip)

        try:
            country = (record.get("country") or {}).get("iso_code") or ""
            country_name = _first_en(
                (record.get("country") or {}).get("names") or {})
            city = _first_en(
                (record.get("city") or {}).get("names") or {})
            loc = record.get("location") or {}
            lat = float(loc.get("latitude") or 0.0)
            lon = float(loc.get("longitude") or 0.0)
        except Exception:
            country = country_name = city = ""
            lat = lon = 0.0

        return GeoResult(
            ip=ip,
            country=country,
            country_name=country_name,
            city=city,
            latitude=lat,
            longitude=lon,
        )

    def lookup_many(self, ips: list[str]) -> list[GeoResult]:
        """Bulk lookup — returns a result for every IP in the input list."""
        return [self.lookup(ip) for ip in ips]

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                try:
                    self._db.close()
                except Exception:
                    pass
            self._db = None


def _first_en(names: dict) -> str:
    """Return the 'en' name from a MaxMind names dict, or the first value."""
    if not names:
        return ""
    return names.get("en") or next(iter(names.values()), "")


# ── Database download helper ──────────────────────────────────────────────────

def download_db_permalink(
    permalink_url: str,
    dest: Optional[Path] = None,
    on_progress: Optional[object] = None,
) -> Path:
    """
    Download GeoLite2-City.mmdb from a MaxMind permalink URL.

    Parameters
    ----------
    permalink_url : str
        The download URL from the user's MaxMind account dashboard.
        Must be an HTTPS URL to maxmind.com or download.maxmind.com.
    dest : Path, optional
        Destination path for the .mmdb file.  Defaults to db_path().
    on_progress : callable(int, int), optional
        Called with (bytes_received, total_bytes) during download.

    Returns
    -------
    Path to the written .mmdb file.

    Raises
    ------
    ValueError  — if the URL is not an HTTPS MaxMind URL
    OSError     — if the download or extraction fails
    """
    # Security: only allow HTTPS URLs from trusted hosts
    if not permalink_url.startswith("https://"):
        raise ValueError("GeoIP download URL must use HTTPS.")
    from urllib.parse import urlparse
    host = urlparse(permalink_url).netloc.lower()
    _trusted = (
        host == "maxmind.com"
        or host == "download.maxmind.com"
        or host.endswith(".maxmind.com")
        or host == "raw.githubusercontent.com"    # P3TERX/GeoLite.mmdb mirror
    )
    if not _trusted:
        raise ValueError(
            f"Untrusted download host '{host}'. "
            "Accepted: maxmind.com and raw.githubusercontent.com."
        )

    if dest is None:
        dest = db_path()
    dest.parent.mkdir(parents=True, exist_ok=True)

    tmp = dest.with_suffix(".mmdb.tmp")

    req = urllib.request.Request(
        permalink_url,
        headers={"User-Agent": "NetSentinel/GeoIP-Downloader"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (HTTPS only)
        total = int(resp.headers.get("Content-Length") or 0)
        received = 0
        chunk = 65536
        with open(tmp, "wb") as fh:
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                fh.write(block)
                received += len(block)
                if on_progress:
                    on_progress(received, total)

    # Handle .tar.gz archives from MaxMind (permalink format)
    if permalink_url.lower().endswith(".tar.gz") or _is_gzip(tmp):
        extracted = _extract_mmdb_from_tarball(tmp, dest)
        tmp.unlink(missing_ok=True)
        return extracted
    else:
        tmp.replace(dest)
        return dest


def _is_gzip(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"\x1f\x8b"
    except OSError:
        return False


def _extract_mmdb_from_tarball(tar_path: Path, dest: Path) -> Path:
    import tarfile
    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.name.endswith(".mmdb"):
                reader = tf.extractfile(member)
                if reader is None:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as out:
                    out.write(reader.read())
                return dest
    raise OSError("No .mmdb file found in the downloaded archive.")


# Public mirror maintained by P3TERX — updated automatically from MaxMind nightly.
# No MaxMind account required.  Source: https://github.com/P3TERX/GeoLite.mmdb
GEOLITE_MIRROR_URL = (
    "https://raw.githubusercontent.com/P3TERX/GeoLite.mmdb/download/GeoLite2-City.mmdb"
)

# ── Module-level singleton ────────────────────────────────────────────────────

_singleton: Optional[GeoLocator] = None
_singleton_lock = threading.Lock()


def get_locator() -> GeoLocator:
    """Return the shared GeoLocator instance (created on first call)."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = GeoLocator()
    return _singleton
