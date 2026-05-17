"""
scripts/vt_scan.py — Submit a GitHub Release download URL to VirusTotal and poll for a result.

Usage (called from release.yml):
    python scripts/vt_scan.py <url>

Writes VT_PERMALINK=<url> to $GITHUB_OUTPUT on success.
Exits 0 on success or if VT times out (non-fatal: release continues regardless).

Requires:
    VT_API_KEY environment variable (VirusTotal free-tier API key)
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import json

VT_API = "https://www.virustotal.com/api/v3"
POLL_INTERVAL = 30   # seconds between status checks
MAX_POLLS     = 20   # 20 × 30s = 10 minutes max


def _headers() -> dict:
    key = os.environ.get("VT_API_KEY", "")
    if not key:
        print("VT_API_KEY not set — skipping VirusTotal scan", flush=True)
        sys.exit(0)
    return {"x-apikey": key, "Accept": "application/json"}


def _post(path: str, data: bytes, content_type: str) -> dict:
    req = urllib.request.Request(
        f"{VT_API}{path}",
        data=data,
        headers={**_headers(), "Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _get(path: str) -> dict:
    req = urllib.request.Request(
        f"{VT_API}{path}",
        headers=_headers(),
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def submit_url(download_url: str) -> str:
    """Submit URL for scanning. Returns the analysis ID."""
    encoded = urllib.parse.urlencode({"url": download_url}).encode()
    resp = _post("/urls", encoded, "application/x-www-form-urlencoded")
    analysis_id = resp["data"]["id"]
    print(f"VT analysis ID: {analysis_id}", flush=True)
    return analysis_id


def poll_analysis(analysis_id: str) -> dict | None:
    """Poll until analysis is complete. Returns stats dict or None on timeout."""
    for attempt in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL)
        resp = _get(f"/analyses/{analysis_id}")
        status = resp["data"]["attributes"]["status"]
        print(f"VT poll {attempt + 1}/{MAX_POLLS}: {status}", flush=True)
        if status == "completed":
            return resp["data"]["attributes"]["stats"]
    return None


def write_output(key: str, value: str) -> None:
    gh_output = os.environ.get("GITHUB_OUTPUT", "")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write(f"{key}={value}\n")
    print(f"Output: {key}={value}", flush=True)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: vt_scan.py <download_url>", file=sys.stderr)
        sys.exit(1)

    download_url = sys.argv[1]
    print(f"Submitting to VirusTotal: {download_url}", flush=True)

    try:
        analysis_id = submit_url(download_url)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"VT submission failed: HTTP {e.code} — {body}", flush=True)
        sys.exit(0)   # non-fatal

    stats = poll_analysis(analysis_id)

    # Build the permalink from the URL hash (VT's stable URL format)
    url_id = urllib.parse.b64encode(
        (download_url + "\n").encode()
    ).rstrip(b"=").decode()
    permalink = f"https://www.virustotal.com/gui/url/{url_id}"

    if stats is None:
        print("VT analysis timed out — using submission permalink", flush=True)
        write_output("VT_PERMALINK", permalink)
        sys.exit(0)

    malicious  = stats.get("malicious",  0)
    suspicious = stats.get("suspicious", 0)
    total      = sum(stats.values())
    print(f"VT result: {malicious} malicious, {suspicious} suspicious / {total} engines", flush=True)

    write_output("VT_PERMALINK",   permalink)
    write_output("VT_DETECTIONS",  f"{malicious}/{total}")

    if malicious > 0 or suspicious > 0:
        print(
            f"RELEASE BLOCKED: VirusTotal flagged {malicious} malicious + "
            f"{suspicious} suspicious detections. Investigate before shipping.",
            file=sys.stderr, flush=True,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
