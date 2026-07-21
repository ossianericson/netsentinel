"""
threat_intel.py — Threat Intelligence Feed integration (item 7).

Provides:
  • ThreatEntry  — data class for a threat indicator record
  • ThreatIntelDB — in-memory database; load from local cache files and check IPs/domains
  • refresh_from_feeds(cache_dir, progress_cb) — download public OSINT blocklists
  • lookup_abuseipdb(ip, api_key) — query AbuseIPDB (only with explicit user consent)

Security rules observed
-----------------------
  • Only OUI prefix (first 3 octets) or full public IPs are sent to external APIs,
    never private/RFC1918 addresses (checked before any HTTP call).
  • AbuseIPDB API key stored in OS keychain by the UI layer (RULE 22-A).
  • All external HTTP calls: per-request timeout, 1-second rate-limit between
    calls to the same host (ARCH security requirement).
  • Never sends hostnames or full MACs to external services.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

_UA = "NetSentinel/1.9 (github.com/ossianericson/netsentinel)"

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ThreatEntry:
    indicator: str          # IP address or domain name
    itype:     str          # "ip" or "domain"
    categories: List[str]  # e.g. ["botnet_c2", "malware", "phishing"]
    source:    str          # feed name, e.g. "Feodo Tracker", "URLhaus", "custom"
    confidence: int         # 0–100
    last_seen:  str         # ISO-8601 date or empty string
    comment:   str = ""


class AbuseIpDbUnreachableError(Exception):
    """The AbuseIPDB API itself could not be reached (network error, timeout,
    rate-limit, malformed response) — distinct from a missing API key or a
    private IP, both of which are expected, by-design "nothing to check"
    outcomes that lookup_abuseipdb() still returns as a plain None."""


@dataclass
class AbuseIpDbResult:
    ip:             str
    abuse_score:    int      # 0–100
    country:        str
    isp:            str
    categories:     List[str] = field(default_factory=list)
    last_reported:  str = ""
    total_reports:  int = 0
    is_public:      bool = True


# ── Rate limiter ──────────────────────────────────────────────────────────────

_rate_locks: Dict[str, float] = {}
_rate_mutex = threading.Lock()
_MIN_INTERVAL = 1.0   # seconds between calls to the same host


def _rate_wait(host: str) -> None:
    """Enforce minimum 1-second gap between calls to the same host."""
    with _rate_mutex:
        last = _rate_locks.get(host, 0.0)
        now  = time.monotonic()
        wait = max(0.0, _MIN_INTERVAL - (now - last))
        _rate_locks[host] = now + wait
    if wait > 0:
        time.sleep(wait)


# ── Public IP guard ───────────────────────────────────────────────────────────

def _is_public_ip(ip: str) -> bool:
    """Return True only for globally-routable public IP addresses."""
    try:
        obj = ipaddress.ip_address(ip)
        return (
            obj.is_global
            and not obj.is_private
            and not obj.is_loopback
            and not obj.is_link_local
            and not obj.is_multicast
            and not obj.is_reserved
        )
    except ValueError:
        return False


# ── Feed parsers ──────────────────────────────────────────────────────────────

def _parse_feodo_json(data: bytes) -> List[ThreatEntry]:
    """
    Parse Abuse.ch Feodo Tracker botnet C2 JSON feed.
    Format: list of objects with "ip_address", "status", "malware", "first_seen", "last_online"
    """
    entries: List[ThreatEntry] = []
    try:
        records = json.loads(data)
        if isinstance(records, list):
            for r in records:
                ip = r.get("ip_address", "").strip()
                if not ip:
                    continue
                entries.append(ThreatEntry(
                    indicator=ip,
                    itype="ip",
                    categories=["botnet_c2"],
                    source="Feodo Tracker",
                    confidence=90,
                    last_seen=r.get("last_online", ""),
                    comment=r.get("malware", ""),
                ))
    except Exception:
        pass  # non-fatal
    return entries


def _parse_urlhaus_text(data: bytes) -> List[ThreatEntry]:
    """
    Parse URLhaus online hosts text file (one domain/IP per line, # comments).
    """
    entries: List[ThreatEntry] = []
    try:
        for raw_line in data.decode(errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip scheme if present
            line = re.sub(r"^https?://", "", line).split("/")[0].split(":")[0]
            if not line:
                continue
            try:
                ipaddress.ip_address(line)
                itype = "ip"
            except ValueError:
                itype = "domain"
            entries.append(ThreatEntry(
                indicator=line,
                itype=itype,
                categories=["malware"],
                source="URLhaus",
                confidence=75,
                last_seen="",
            ))
    except Exception:
        pass  # non-fatal
    return entries


def _parse_plain_ip_list(data: bytes, source: str, categories: List[str],
                         confidence: int) -> List[ThreatEntry]:
    """Generic parser for newline-delimited IP address files (# comments ignored)."""
    entries: List[ThreatEntry] = []
    try:
        for raw_line in data.decode(errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # May contain CIDR or trailing text — extract the IP/CIDR
            ip_part = line.split()[0].split(",")[0]
            try:
                ipaddress.ip_network(ip_part, strict=False)
                entries.append(ThreatEntry(
                    indicator=ip_part,
                    itype="ip",
                    categories=categories,
                    source=source,
                    confidence=confidence,
                    last_seen="",
                ))
            except ValueError:
                pass  # non-fatal
    except Exception:
        pass  # non-fatal
    return entries


# ── Feed definitions ──────────────────────────────────────────────────────────

FEEDS = [
    {
        "name":       "Feodo Tracker (Botnet C2)",
        "url":        "https://feodotracker.abuse.ch/downloads/ipblocklist.json",
        "filename":   "feodo.json",
        "parser":     _parse_feodo_json,
    },
    {
        "name":       "Emerging Threats Compromised IPs",
        "url":        "https://rules.emergingthreats.net/blockrules/compromised-ips.txt",
        "filename":   "et_compromised.txt",
        "parser":     lambda d: _parse_plain_ip_list(d, "Emerging Threats", ["compromised"], 70),
    },
]

_DEFAULT_TIMEOUT = 15   # seconds per HTTP request


# ── Cache management ──────────────────────────────────────────────────────────

def _cache_dir() -> Path:
    """Return the local cache directory for threat feed files."""
    base = Path(os.environ.get("APPDATA", Path.home())) / "NetSentinel" / "threat_feeds"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _fetch_one_feed(
    feed: dict,
    cache_dir: Path,
    progress_cb: Optional[Callable[[str], None]],
) -> List[ThreatEntry]:
    """Download, cache, and parse a single feed. Falls back to the local
    cache file on any download failure. Runs inside the shared ThreadPoolExecutor
    in refresh_from_feeds() — one thread per feed, so a slow/unreachable host
    doesn't add its full timeout to every other feed's wait."""
    if progress_cb:
        progress_cb(f"Downloading {feed['name']}…")
    host = urllib.parse.urlparse(feed["url"]).hostname or feed["name"]
    cache_path = cache_dir / feed["filename"]
    try:
        _rate_wait(host)
        req = urllib.request.Request(feed["url"], headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
            data = resp.read()
        cache_path.write_bytes(data)
        entries = feed["parser"](data)
        if progress_cb:
            progress_cb(f"  {feed['name']}: {len(entries)} indicators loaded.")
        return entries
    except Exception as exc:
        if progress_cb:
            progress_cb(f"  {feed['name']}: failed ({exc})")
        if cache_path.exists():
            try:
                data = cache_path.read_bytes()
                entries = feed["parser"](data)
                if progress_cb:
                    progress_cb(f"  {feed['name']}: loaded from cache ({len(entries)} indicators).")
                return entries
            except Exception:
                pass  # non-fatal — cache file unreadable/corrupt; treat as empty
        return []


def refresh_from_feeds(
    cache_dir: Optional[Path] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> List[ThreatEntry]:
    """
    Download all configured threat feeds, cache them locally, and return
    the combined list of ThreatEntry records.

    Feeds are fetched concurrently (one thread per feed) so total wall time
    is bounded by the slowest single feed rather than their sum — with 2+
    feeds each carrying a 15 s timeout, sequential fetching held the calling
    thread busy long enough (and the UI-visible "Update Feeds" wait long
    enough) to widen the window for unrelated main-thread contention.

    Safe to call in a background thread.  Returns an empty list on complete failure.
    """
    if cache_dir is None:
        cache_dir = _cache_dir()

    from concurrent.futures import ThreadPoolExecutor

    all_entries: List[ThreatEntry] = []
    with ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
        futures = [pool.submit(_fetch_one_feed, feed, cache_dir, progress_cb) for feed in FEEDS]
        for future in futures:
            all_entries.extend(future.result())

    if progress_cb:
        progress_cb(f"Done. {len(all_entries)} threat indicators loaded.")
    return all_entries


def load_from_cache(cache_dir: Optional[Path] = None) -> List[ThreatEntry]:
    """Load threat entries from local cache files without downloading."""
    if cache_dir is None:
        cache_dir = _cache_dir()
    all_entries: List[ThreatEntry] = []
    for feed in FEEDS:
        cache_path = cache_dir / feed["filename"]
        if cache_path.exists():
            try:
                data = cache_path.read_bytes()
                all_entries.extend(feed["parser"](data))
            except Exception:
                pass  # non-fatal
    return all_entries


# ── ThreatIntelDB ─────────────────────────────────────────────────────────────

class ThreatIntelDB:
    """
    In-memory threat indicator database.

    Build with ThreatIntelDB.from_entries() or ThreatIntelDB.from_cache().
    Use check_ip() / check_domain() to look up indicators.
    """

    def __init__(self) -> None:
        self._ip_index: Dict[str, ThreatEntry]     = {}
        self._cidr_list: List[tuple]                = []   # (network, ThreatEntry)
        self._domain_index: Dict[str, ThreatEntry]  = {}
        self._entries: List[ThreatEntry]            = []

    @classmethod
    def from_entries(cls, entries: List[ThreatEntry]) -> "ThreatIntelDB":
        db = cls()
        db.load(entries)
        return db

    @classmethod
    def from_cache(cls, cache_dir: Optional[Path] = None) -> "ThreatIntelDB":
        return cls.from_entries(load_from_cache(cache_dir))

    def load(self, entries: List[ThreatEntry]) -> None:
        """Load (or replace) the database with a list of ThreatEntry records."""
        self._ip_index.clear()
        self._cidr_list.clear()
        self._domain_index.clear()
        self._entries = list(entries)
        for entry in entries:
            if entry.itype == "ip":
                ind = entry.indicator
                if "/" in ind:
                    # CIDR block
                    try:
                        net = ipaddress.ip_network(ind, strict=False)
                        self._cidr_list.append((net, entry))
                    except ValueError:
                        pass  # non-fatal
                else:
                    self._ip_index[ind] = entry
            elif entry.itype == "domain":
                self._domain_index[entry.indicator.lower()] = entry

    def check_ip(self, ip: str) -> Optional[ThreatEntry]:
        """Return a ThreatEntry if the IP is in the database, else None."""
        entry = self._ip_index.get(ip)
        if entry:
            return entry
        try:
            addr = ipaddress.ip_address(ip)
            for net, e in self._cidr_list:
                if addr in net:
                    return e
        except ValueError:
            pass  # non-fatal
        return None

    def check_domain(self, domain: str) -> Optional[ThreatEntry]:
        """Return a ThreatEntry if the domain (or a parent) is in the database."""
        domain = domain.lower().rstrip(".")
        entry = self._domain_index.get(domain)
        if entry:
            return entry
        # Check parent domains
        parts = domain.split(".")
        for i in range(1, len(parts) - 1):
            parent = ".".join(parts[i:])
            entry = self._domain_index.get(parent)
            if entry:
                return entry
        return None

    def all_entries(self) -> List[ThreatEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# ── AbuseIPDB integration (consent-gated, public IPs only) ───────────────────

_ABUSEIPDB_BASE = "https://api.abuseipdb.com/api/v2/check"
_ABUSE_CATEGORY_MAP = {
    3:  "Fraud Orders",     4:  "DDoS Attack",    5:  "FTP Brute-Force",
    6:  "Ping of Death",    7:  "Phishing",        8:  "Fraud VoIP",
    9:  "Open Proxy",       10: "Web Spam",        11: "Email Spam",
    12: "Blog Spam",        13: "VPN IP",          14: "Port Scan",
    15: "Hacking",          16: "SQL Injection",   17: "Spoofing",
    18: "Brute-Force",      19: "Bad Web Bot",     20: "Exploited Host",
    21: "Web App Attack",   22: "SSH",             23: "IoT Targeted",
}


def lookup_abuseipdb(
    ip: str,
    api_key: str,
    max_age_days: int = 30,
    timeout_s: int = 8,
) -> Optional[AbuseIpDbResult]:
    """
    Query AbuseIPDB for an IP reputation score.

    SECURITY: Only public IPs are queried (RFC1918/loopback/link-local blocked).
    PRIVACY:  Caller must obtain explicit user consent before calling this function.
    RATE:     1-second minimum gap enforced via _rate_wait().
    API KEY:  Must be loaded from OS keychain (RULE 22-A); never stored in QSettings.

    Returns None on failure or if the IP is private.
    """
    if not api_key:
        return None
    if not _is_public_ip(ip):
        return None

    _rate_wait("api.abuseipdb.com")
    params = f"ipAddress={urllib.parse.quote(ip)}&maxAgeInDays={max_age_days}&verbose"
    url = f"{_ABUSEIPDB_BASE}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "Key":        api_key,
            "Accept":     "application/json",
            "User-Agent": _UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read())
        data = body.get("data", {})
        raw_cats = data.get("reports", [{}])
        cats_flat = []
        for report in raw_cats:
            for cat_id in report.get("categories", []):
                label = _ABUSE_CATEGORY_MAP.get(cat_id, str(cat_id))
                if label not in cats_flat:
                    cats_flat.append(label)
        # Fallback: top-level categories field (older API response format)
        if not cats_flat:
            for cat_id in data.get("categories", []):
                label = _ABUSE_CATEGORY_MAP.get(cat_id, str(cat_id))
                if label not in cats_flat:
                    cats_flat.append(label)
        return AbuseIpDbResult(
            ip=ip,
            abuse_score=data.get("abuseConfidenceScore", 0),
            country=data.get("countryCode", ""),
            isp=data.get("isp", ""),
            categories=cats_flat,
            last_reported=data.get("lastReportedAt", "") or "",
            total_reports=data.get("totalReports", 0),
            is_public=data.get("isPublic", True),
        )
    except Exception as exc:
        raise AbuseIpDbUnreachableError(str(exc)) from exc

