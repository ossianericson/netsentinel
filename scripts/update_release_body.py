"""
scripts/update_release_body.py — Prepend a security section to an existing GitHub Release body.

Usage (called from release.yml):
    python scripts/update_release_body.py <release_id> <version> <sha256sums_url> \\
        [--vt-permalink <url>] [--bundle-name <filename>] [--msix-bundle-name <filename>]

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


def build_security_section(
    version: str,
    sha256sums_url: str,
    vt_permalink: str | None,
    bundle_name: str | None,
    msix_bundle_name: str | None = None,
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
            f"| VirusTotal scan | [{vt_permalink.split('/')[-1][:12]}…]({vt_permalink}) |",
            f"| SHA256 checksums | [SHA256SUMS.txt]({sha256sums_url}) |",
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
    )

    new_body = security_section + existing_body

    print("Updating release body…", flush=True)
    _api(f"/releases/{args.release_id}", method="PATCH", body={"body": new_body})
    print("Release body updated.", flush=True)


if __name__ == "__main__":
    main()
