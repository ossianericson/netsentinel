"""
scripts/update_release_body.py — Prepend a security section to an existing GitHub Release body.

Usage (called from release.yml):
    python scripts/update_release_body.py <release_id> <version> <sha256sums_url> \\
        [--vt-permalink <url>] [--vt-status clean|flagged|blocked|timeout] \\
        [--vt-detections <malicious>/<total>] [--vt-engines "<name>; <name>"] \\
        [--human-override <note>] [--bundle-name <filename>] [--msix-bundle-name <filename>]

Manual-override usage (docs/internal/vt-false-positive-runbook.md): after a human has reviewed
a "blocked" VT verdict and judged it a false positive, re-run this script locally with
--human-override "reviewed <date> by <name>: <verdict>" to patch the release notes with
a visible reviewer note — never silently drop the VT status.

Requires:
    GITHUB_TOKEN environment variable (automatically provided by GitHub Actions)
    GITHUB_REPOSITORY environment variable (automatically provided by GitHub Actions)
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request


def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    token = os.environ["GITHUB_TOKEN"]
    repo  = os.environ["GITHUB_REPOSITORY"]
    url   = f"https://api.github.com/repos/{repo}{path}"
    data  = json.dumps(body).encode() if body else None
    req   = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _vt_row(
    vt_permalink: str,
    vt_status: str | None,
    vt_detections: str | None,
    vt_engines: str | None,
) -> str:
    """One markdown table row summarizing the VT verdict — status-aware (RULE-REL1).

    A bare "here's a link" row lets a flagged or blocked build look identical to a
    clean one in the release notes; every non-clean status must say so plainly
    rather than making the reader click through to find out.
    """
    label = vt_permalink.rstrip("/").split("/")[-1][:12] + "…"
    detail = ""
    if vt_detections:
        detail = f" ({vt_detections} engines" + (f": {vt_engines}" if vt_engines else "") + ")"

    if vt_status == "flagged":
        return f"| VirusTotal scan | ⚠️ Flagged, reviewed non-blocking{detail} — [report]({vt_permalink}) |"
    if vt_status == "blocked":
        return f"| VirusTotal scan | 🛑 Blocked{detail} — [report]({vt_permalink}) |"
    if vt_status == "timeout":
        return f"| VirusTotal scan | ⏱️ Scan did not complete — not confirmed clean — [report]({vt_permalink}) |"
    return f"| VirusTotal scan | [{label}]({vt_permalink}) |"


def build_security_section(
    version: str,
    sha256sums_url: str,
    vt_permalink: str | None,
    bundle_name: str | None,
    msix_bundle_name: str | None = None,
    vt_status: str | None = None,
    vt_detections: str | None = None,
    vt_engines: str | None = None,
    human_override: str | None = None,
) -> str:
    lines = [
        "## Security & Verification",
        "",
        "Every release is signed and checksummed. **Verify before running.**",
        "",
    ]

    if vt_permalink:
        lines += [
            f"| Check | Result |",
            f"|---|---|",
            _vt_row(vt_permalink, vt_status, vt_detections, vt_engines),
            f"| SHA256 checksums | [SHA256SUMS.txt]({sha256sums_url}) |",
            "",
        ]
        if vt_status == "blocked" and human_override:
            lines += [
                f"> **Manually reviewed:** {human_override}",
                "",
            ]
    else:
        lines += [
            f"- SHA256 checksums: [SHA256SUMS.txt]({sha256sums_url})",
            "",
        ]

    lines += [
        "**Verify the SHA256 checksum (Windows):**",
        "```powershell",
        f"$expected = (Get-Content SHA256SUMS.txt | Select-String 'NetSentinel-Setup').ToString().Split(' ')[0]",
        f"$actual   = (Get-FileHash 'NetSentinel-Setup-{version}.exe' -Algorithm SHA256).Hash.ToLower()",
        "if ($expected -eq $actual) { '✅ OK' } else { '❌ MISMATCH' }",
        "```",
        "",
    ]

    if bundle_name:
        lines += [
            "**Verify the cosign signature (Windows installer):**",
            "```bash",
            f"cosign verify-blob \\",
            f"  --bundle {bundle_name} \\",
            f'  --certificate-identity-regexp "https://github.com/ossianericson/netsentinel/.*" \\',
            f'  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \\',
            f"  NetSentinel-Setup-{version}.exe",
            "```",
            "",
        ]

    if msix_bundle_name:
        lines += [
            "**Verify the cosign signature (MSIX):**",
            "```bash",
            f"cosign verify-blob \\",
            f"  --bundle {msix_bundle_name} \\",
            f'  --certificate-identity-regexp "https://github.com/ossianericson/netsentinel/.*" \\',
            f'  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \\',
            f"  NetSentinel-{version}.msix",
            "```",
            "",
        ]

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("release_id")
    p.add_argument("version")
    p.add_argument("sha256sums_url")
    p.add_argument("--vt-permalink", default=None)
    p.add_argument("--vt-status", default=None, choices=["clean", "flagged", "blocked", "timeout"])
    p.add_argument("--vt-detections", default=None)
    p.add_argument("--vt-engines", default=None)
    p.add_argument("--human-override", default=None)
    p.add_argument("--bundle-name", default=None)
    p.add_argument("--msix-bundle-name", default=None)
    args = p.parse_args()

    print(f"Fetching release {args.release_id}…", flush=True)
    release = _api(f"/releases/{args.release_id}")
    existing_body = release.get("body") or ""

    security_section = build_security_section(
        version=args.version,
        sha256sums_url=args.sha256sums_url,
        vt_permalink=args.vt_permalink,
        bundle_name=args.bundle_name,
        msix_bundle_name=args.msix_bundle_name,
        vt_status=args.vt_status,
        vt_detections=args.vt_detections,
        vt_engines=args.vt_engines,
        human_override=args.human_override,
    )

    new_body = security_section + existing_body

    print("Updating release body…", flush=True)
    _api(f"/releases/{args.release_id}", method="PATCH", body={"body": new_body})
    print("Release body updated.", flush=True)


if __name__ == "__main__":
    main()
