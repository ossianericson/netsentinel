"""
CVE Lookup — queries the NVD REST API v2 for known vulnerabilities matching
a service name + version string detected by the port scanner.

Rate limits (NVD):
  - Without API key: 5 requests / 30 seconds
  - With API key  : 50 requests / 30 seconds  (set NVD_API_KEY env var)

Results are cached in memory for the lifetime of the process to avoid
hammering the API when the same service appears on multiple devices.

Offline fallback: if the API is unreachable, returns an empty list with
no error raised — scan results are still usable without CVE data.
"""

from __future__ import annotations

import os
import re
import time
import threading
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import URLError
import json

# ── Configuration ─────────────────────────────────────────────────────────────

NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_API_KEY  = os.environ.get("NVD_API_KEY", "")

# Delay between requests (seconds) — stay inside rate limit
_DELAY_NO_KEY  = 6.5   # ~4.6/30s safe margin without key
_DELAY_WITH_KEY = 0.7  # ~42/30s safe margin with key
_REQUEST_DELAY  = _DELAY_WITH_KEY if _API_KEY else _DELAY_NO_KEY

# In-memory cache: keyword → List[CVEResult]
_cache: dict[str, list] = {}
_cache_lock = threading.Lock()
_last_request_time: float = 0.0
_rate_lock = threading.Lock()


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CVEResult:
    cve_id:      str
    description: str
    cvss_score:  float       # V3 base score, 0.0 if unavailable
    severity:    str         # CRITICAL / HIGH / MEDIUM / LOW / NONE
    published:   str         # ISO date string
    references:  List[str] = field(default_factory=list)

    @property
    def nvd_url(self) -> str:
        return f"https://nvd.nist.gov/vuln/detail/{self.cve_id}"


@dataclass
class CVELookupResult:
    keyword:    str
    cves:       List[CVEResult] = field(default_factory=list)
    from_cache: bool = False
    error:      str  = ""

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.cves if c.severity == "CRITICAL")

    @property
    def high_count(self) -> int:
        return sum(1 for c in self.cves if c.severity == "HIGH")

    @property
    def top_score(self) -> float:
        return max((c.cvss_score for c in self.cves), default=0.0)


# ── Version normalisation ─────────────────────────────────────────────────────

def _normalise_service_version(service_version: str) -> Optional[str]:
    """
    Convert a raw banner version string into a useful NVD keyword.

    Examples:
      "OpenSSH 8.9p1 Ubuntu"   → "OpenSSH 8.9"
      "Apache/2.4.54"           → "Apache httpd 2.4.54"
      "Microsoft-IIS/10.0"      → "Microsoft IIS 10.0"
      "nginx/1.22.1"            → "nginx 1.22.1"
      "vsftpd 3.0.5"            → "vsftpd 3.0.5"
    """
    if not service_version:
        return None
    sv = service_version.strip()

    # Map common banner patterns to NVD-friendly keywords
    _maps = [
        (r"OpenSSH[_ ]?([\d.p]+)",          r"OpenSSH \1"),
        (r"Apache/([\d.]+)",                 r"Apache httpd \1"),
        (r"Microsoft-IIS/([\d.]+)",          r"Microsoft IIS \1"),
        (r"nginx/([\d.]+)",                  r"nginx \1"),
        (r"vsftpd ([\d.]+)",                 r"vsftpd \1"),
        (r"ProFTPD ([\d.]+)",                r"ProFTPD \1"),
        (r"Exim ([\d.]+)",                   r"Exim \1"),
        (r"Postfix",                         r"Postfix"),
        (r"OpenVPN ([\d.]+)",                r"OpenVPN \1"),
        (r"MySQL\s+([\d.]+)",                r"MySQL \1"),
        (r"MariaDB\s+([\d.]+)",              r"MariaDB \1"),
        (r"PostgreSQL\s+([\d.]+)",           r"PostgreSQL \1"),
        (r"redis\s+([\d.]+)",                r"Redis \1"),
        (r"Samba\s+([\d.]+)",                r"Samba \1"),
        (r"lighttpd/([\d.]+)",               r"lighttpd \1"),
        (r"Tomcat/([\d.]+)",                 r"Apache Tomcat \1"),
        (r"IceWarp\s+([\d.]+)",              r"IceWarp \1"),
        (r"Dovecot",                         r"Dovecot"),
    ]

    for pattern, replacement in _maps:
        m = re.search(pattern, sv, re.IGNORECASE)
        if m:
            return re.sub(pattern, replacement, sv, flags=re.IGNORECASE).split("\n")[0][:60].strip()

    # Fallback: strip trailing metadata, keep first 60 chars
    sv_clean = sv.split(" (")[0].split("\n")[0][:60].strip()
    if any(c.isdigit() for c in sv_clean):
        return sv_clean
    return None


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _nvd_request(keyword: str, results_per_page: int = 10) -> list:
    """
    Query NVD API v2.  Returns a list of CVEResult objects.
    Raises on network/API errors.
    """
    global _last_request_time

    params = {
        "keywordSearch": keyword,
        "resultsPerPage": results_per_page,
        "startIndex": 0,
    }
    url = f"{NVD_BASE}?{urlencode(params)}"
    headers = {"Accept": "application/json", "User-Agent": "NetSentinel-CVELookup/3.0"}
    if _API_KEY:
        headers["apiKey"] = _API_KEY

    # Rate-limit enforcement
    with _rate_lock:
        now = time.monotonic()
        wait = _REQUEST_DELAY - (now - _last_request_time)
        if wait > 0:
            time.sleep(wait)
        _last_request_time = time.monotonic()

    req = Request(url, headers=headers)
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("vulnerabilities", []):
        cve   = item.get("cve", {})
        cve_id = cve.get("id", "")

        # Description (English preferred)
        descs = cve.get("descriptions", [])
        desc  = next((d["value"] for d in descs if d.get("lang") == "en"), "No description")

        # CVSS v3 score
        metrics = cve.get("metrics", {})
        cvss_score = 0.0
        severity   = "NONE"
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            m_list = metrics.get(key, [])
            if m_list:
                cvss_data = m_list[0].get("cvssData", {})
                cvss_score = float(cvss_data.get("baseScore", 0.0))
                severity   = cvss_data.get("baseSeverity",
                             m_list[0].get("baseSeverity", "NONE")).upper()
                break

        # Published date (just the date part)
        published = cve.get("published", "")[:10]

        # References (top 3)
        refs = [r["url"] for r in cve.get("references", [])[:3]]

        results.append(CVEResult(
            cve_id=cve_id,
            description=desc[:200],
            cvss_score=cvss_score,
            severity=severity,
            published=published,
            references=refs,
        ))

    # Sort by CVSS score descending
    results.sort(key=lambda c: c.cvss_score, reverse=True)
    return results


# ── Public API ────────────────────────────────────────────────────────────────

def lookup(service_version: str, max_results: int = 8) -> CVELookupResult:
    """
    Look up CVEs for a given service version string.

    Parameters
    ----------
    service_version   Raw version string from banner (e.g. "OpenSSH 8.9p1 Ubuntu").
    max_results       Maximum CVEs to return (default 8).

    Returns a CVELookupResult (empty .cves list if offline or no results).
    """
    keyword = _normalise_service_version(service_version)
    if not keyword:
        return CVELookupResult(keyword=service_version or "", error="No parseable version in banner.")

    with _cache_lock:
        if keyword in _cache:
            return CVELookupResult(keyword=keyword, cves=_cache[keyword], from_cache=True)

    try:
        cves = _nvd_request(keyword, results_per_page=max_results)
        with _cache_lock:
            _cache[keyword] = cves
        return CVELookupResult(keyword=keyword, cves=cves)
    except URLError as exc:
        return CVELookupResult(keyword=keyword, error=f"Network error: {exc.reason}")
    except Exception as exc:
        return CVELookupResult(keyword=keyword, error=str(exc))


def lookup_many(
    service_versions: List[str],
    progress_cb=None,
    max_results: int = 5,
) -> dict[str, CVELookupResult]:
    """
    Look up CVEs for multiple service versions sequentially (rate-limited).
    Returns {original_service_version: CVELookupResult}.
    """
    results: dict[str, CVELookupResult] = {}
    total = len(service_versions)
    _cb = progress_cb or (lambda m: None)
    _cb(f"CVE lookup: checking {total} service version(s)…")

    # Deduplicate: only look up each normalised keyword once
    seen_keywords: dict[str, str] = {}  # keyword → first sv
    for sv in service_versions:
        kw = _normalise_service_version(sv)
        if kw and kw not in seen_keywords:
            seen_keywords[kw] = sv

    done = 0
    for kw, sv in seen_keywords.items():
        res = lookup(sv, max_results=max_results)
        # Map back to all service versions that share this keyword
        for orig_sv in service_versions:
            if _normalise_service_version(orig_sv) == kw:
                results[orig_sv] = res
        done += 1
        _cb(f"CVE lookup: {done}/{len(seen_keywords)} — {kw} → {len(res.cves)} CVE(s)")

    # Fill in any SV that had no parseable version
    for sv in service_versions:
        if sv not in results:
            results[sv] = CVELookupResult(keyword=sv, error="No parseable version.")

    _cb(f"CVE lookup complete — {sum(len(r.cves) for r in results.values())} CVE(s) found.")
    return results
