"""
scripts/vt_scan.py — Submit a GitHub Release download URL to VirusTotal and poll for a result.

Usage (called from release.yml):
    python scripts/vt_scan.py <url>

Writes to $GITHUB_OUTPUT on success:
    VT_PERMALINK   — link to the VT report
    VT_DETECTIONS  — "<malicious>/<total>" engine count
    VT_SUSPICIOUS  — suspicious engine count
    VT_STATUS      — "clean" | "flagged" | "blocked" | "timeout"
    VT_ENGINES     — up to 10 flagging engine names, "; "-joined (empty if none)

Exit code reflects `classify()`, not "any nonzero detection" (RULE-REL1): only a
"blocked" verdict (combined malicious+suspicious hits above VT_SOFT_FLAG_MAX) fails
the step. A "flagged" verdict (a small number of hits — the common single-engine
false-positive shape on a brand-new binary) exits 0 but is never silent: it prints
a `::warning::` Actions annotation and a $GITHUB_STEP_SUMMARY block, and the caller
(release.yml) still renders it in the release notes via update_release_body.py.

Requires:
    VT_API_KEY environment variable (VirusTotal free-tier API key)
"""

from __future__ import annotations

import os
import sys
import time
import base64
import urllib.error
import urllib.parse
import urllib.request
import json

VT_API = "https://www.virustotal.com/api/v3"
POLL_INTERVAL = 30   # seconds between status checks
MAX_POLLS     = 20   # 20 × 30s = 10 minutes max

# Combined malicious+suspicious hit count at/below which a result is "flagged"
# (visible, non-blocking) rather than "blocked" (fails the step). Tunable without
# a code change because reasonable people can disagree on where this line sits —
# see RULE-REL1 for the incident that set the default.
SOFT_FLAG_MAX = int(os.environ.get("VT_SOFT_FLAG_MAX", "2"))

MAX_ENGINES_REPORTED = 10


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


def flagging_engines(results: dict) -> list[str]:
    """Names of engines that reported "malicious" or "suspicious", sorted."""
    return sorted(
        name for name, r in results.items()
        if r.get("category") in ("malicious", "suspicious")
    )


def poll_analysis(analysis_id: str) -> tuple[dict, dict] | None:
    """Poll until analysis is complete. Returns (stats, results) or None on timeout."""
    for attempt in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL)
        resp = _get(f"/analyses/{analysis_id}")
        attrs = resp["data"]["attributes"]
        status = attrs["status"]
        print(f"VT poll {attempt + 1}/{MAX_POLLS}: {status}", flush=True)
        if status == "completed":
            return attrs["stats"], attrs.get("results", {})
    return None


def classify(stats: dict) -> str:
    """Returns "clean" | "flagged" | "blocked" from a VT stats dict.

    Combined malicious+suspicious hits of 0 is "clean". Above 0 but at/below
    SOFT_FLAG_MAX is "flagged" — visible but non-blocking. Above SOFT_FLAG_MAX is
    "blocked" — fails the step. See RULE-REL1.
    """
    hits = stats.get("malicious", 0) + stats.get("suspicious", 0)
    if hits == 0:
        return "clean"
    return "blocked" if hits > SOFT_FLAG_MAX else "flagged"


def write_output(key: str, value: str) -> None:
    gh_output = os.environ.get("GITHUB_OUTPUT", "")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write(f"{key}={value}\n")
    print(f"Output: {key}={value}", flush=True)


def write_step_summary(lines: list[str]) -> None:
    gh_summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if gh_summary:
        with open(gh_summary, "a") as f:
            f.write("\n".join(lines) + "\n")


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

    result = poll_analysis(analysis_id)

    # Build the permalink from the URL hash (VT's stable URL format)
    url_id = base64.b64encode(
        (download_url + "\n").encode()
    ).rstrip(b"=").decode()
    permalink = f"https://www.virustotal.com/gui/url/{url_id}"

    if result is None:
        print("VT analysis timed out — using submission permalink", flush=True)
        write_output("VT_PERMALINK", permalink)
        write_output("VT_STATUS", "timeout")
        sys.exit(0)

    stats, results = result
    malicious  = stats.get("malicious",  0)
    suspicious = stats.get("suspicious", 0)
    total      = sum(stats.values())
    status     = classify(stats)
    engines    = flagging_engines(results)
    print(f"VT result: {malicious} malicious, {suspicious} suspicious / {total} engines", flush=True)
    if engines:
        print(f"Flagging engines: {', '.join(engines)}", flush=True)

    write_output("VT_PERMALINK",  permalink)
    write_output("VT_DETECTIONS", f"{malicious}/{total}")
    write_output("VT_SUSPICIOUS", str(suspicious))
    write_output("VT_STATUS",     status)
    write_output("VT_ENGINES",    "; ".join(engines[:MAX_ENGINES_REPORTED]))

    if status == "clean":
        return

    if status == "flagged":
        print(
            f"::warning::VirusTotal flagged {malicious} malicious + {suspicious} suspicious "
            f"detections ({', '.join(engines) or 'engine names unavailable'}) — at or below the "
            f"VT_SOFT_FLAG_MAX={SOFT_FLAG_MAX} threshold, so this does not block the release. "
            f"Review {permalink} and see docs/internal/vt-false-positive-runbook.md if further action is needed.",
            flush=True,
        )
        write_step_summary([
            "### ⚠️ VirusTotal: flagged, non-blocking",
            "",
            f"**{malicious} malicious + {suspicious} suspicious / {total} engines** — "
            f"at or below the soft-flag threshold ({SOFT_FLAG_MAX}), so the release proceeds.",
            "",
            f"Flagging engines: {', '.join(engines) or '(unavailable)'}",
            "",
            f"[VirusTotal report]({permalink})",
            "",
            "See `docs/internal/vt-false-positive-runbook.md` for manual-review guidance.",
        ])
        return

    # status == "blocked"
    print(
        f"RELEASE BLOCKED: VirusTotal flagged {malicious} malicious + {suspicious} suspicious "
        f"detections ({', '.join(engines) or 'engine names unavailable'}), above the "
        f"VT_SOFT_FLAG_MAX={SOFT_FLAG_MAX} threshold. Investigate before shipping — "
        f"see {permalink} and docs/internal/vt-false-positive-runbook.md.",
        file=sys.stderr, flush=True,
    )
    write_step_summary([
        "### 🛑 VirusTotal: BLOCKED",
        "",
        f"**{malicious} malicious + {suspicious} suspicious / {total} engines** — "
        f"above the soft-flag threshold ({SOFT_FLAG_MAX}).",
        "",
        f"Flagging engines: {', '.join(engines) or '(unavailable)'}",
        "",
        f"[VirusTotal report]({permalink})",
        "",
        "See `docs/vt-false-positive-runbook.md` before overriding this.",
    ])
    sys.exit(1)


if __name__ == "__main__":
    main()
