"""
scripts/verify_release.py — End-user release verification tool.

Usage:
    python verify_release.py NetSentinel-Setup-X.Y.Z.exe

What it checks:
  1. SHA256 against SHA256SUMS.txt (downloaded from the GitHub release)
  2. Cosign signature bundle (if .bundle file exists alongside the exe)
  3. Prints the VirusTotal permalink from the release notes (informational)

Requirements:
  - Python 3.9+
  - cosign in PATH (for signature verification)
  - Internet access (to fetch SHA256SUMS.txt from the release)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "ossianericson/netsentinel"
API  = f"https://api.github.com/repos/{REPO}"


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "*/*", "User-Agent": "verify_release.py/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def find_release_for_file(filename: str) -> dict | None:
    """Search recent releases for one that contains the given filename."""
    data = json.loads(_fetch(f"{API}/releases?per_page=10"))
    version_hint = ""
    # Try to extract version from filename like NetSentinel-Setup-1.9.7.exe
    parts = Path(filename).stem.split("-")
    for part in reversed(parts):
        if part.replace(".", "").isdigit():
            version_hint = part
            break

    for release in data:
        if version_hint and version_hint in release.get("tag_name", ""):
            return release
        for asset in release.get("assets", []):
            if asset["name"] == filename:
                return release
    return data[0] if data else None   # fall back to latest


def fetch_sha256sums(release: dict) -> dict[str, str]:
    """Download SHA256SUMS.txt and parse into {filename: hash}."""
    for asset in release.get("assets", []):
        if asset["name"] == "SHA256SUMS.txt":
            content = _fetch(asset["browser_download_url"]).decode()
            result = {}
            for line in content.splitlines():
                line = line.strip()
                if "  " in line:
                    h, fname = line.split("  ", 1)
                    result[fname.strip()] = h.strip().lower()
                elif " " in line:
                    h, fname = line.split(" ", 1)
                    result[fname.strip()] = h.strip().lower()
            return result
    return {}


def verify_cosign(exe_path: Path, bundle_path: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "cosign", "verify-blob",
                "--bundle", str(bundle_path),
                "--certificate-identity-regexp",
                f"https://github.com/{REPO}/.*",
                "--certificate-oidc-issuer",
                "https://token.actions.githubusercontent.com",
                str(exe_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return None   # type: ignore[return-value]  # cosign not installed


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python {Path(sys.argv[0]).name} <path-to-installer.exe>")
        sys.exit(1)

    exe = Path(sys.argv[1]).resolve()
    if not exe.exists():
        print(f"Error: file not found: {exe}", file=sys.stderr)
        sys.exit(1)

    print(f"\nVerifying: {exe.name}")
    print("=" * 60)

    # ── SHA256 ────────────────────────────────────────────────────────────────
    print("\n[1/3] SHA256 checksum")
    actual_hash = sha256_file(exe)
    print(f"  Computed : {actual_hash}")

    try:
        release = find_release_for_file(exe.name)
        if release is None:
            print("  Warning  : could not find GitHub release — manual check required")
            checksums = {}
        else:
            checksums = fetch_sha256sums(release)
    except Exception as e:
        print(f"  Warning  : could not fetch SHA256SUMS.txt ({e})")
        checksums = {}
        release = None

    if checksums:
        expected_hash = checksums.get(exe.name, "")
        if expected_hash:
            print(f"  Expected : {expected_hash}")
            if actual_hash == expected_hash:
                print("  Result   : ✅ MATCH — file is intact")
            else:
                print("  Result   : ❌ MISMATCH — DO NOT RUN THIS FILE")
                sys.exit(2)
        else:
            print(f"  Result   : ⚠️  {exe.name} not found in SHA256SUMS.txt")
    else:
        print(f"  SHA256SUMS.txt not available — computed hash: {actual_hash}")
        print("  Compare manually against the hash published in the GitHub release.")

    # ── Cosign ───────────────────────────────────────────────────────────────
    print("\n[2/3] Cosign signature")
    bundle = exe.with_suffix(exe.suffix + ".bundle")
    if not bundle.exists():
        print(f"  ⚠️  Bundle not found: {bundle.name}")
        print("  Download it from the GitHub release alongside the installer.")
    else:
        ok = verify_cosign(exe, bundle)
        if ok is None:
            print("  ⚠️  cosign not installed. Install from: https://docs.sigstore.dev/cosign/system_config/installation/")
        elif ok:
            print("  ✅ Signature valid — built by GitHub Actions from ossianericson/netsentinel")
        else:
            print("  ❌ Signature INVALID — file may have been tampered with")
            sys.exit(2)

    # ── VirusTotal ────────────────────────────────────────────────────────────
    print("\n[3/3] VirusTotal")
    if release:
        body = release.get("body", "") or ""
        vt_line = next((l for l in body.splitlines() if "virustotal.com" in l.lower()), None)
        if vt_line:
            import re
            match = re.search(r"https://www\.virustotal\.com/\S+", vt_line)
            if match:
                print(f"  VT link  : {match.group()}")
            else:
                print("  VT link  : see release notes on GitHub")
        else:
            print("  VirusTotal link not found in release notes")
    else:
        print("  Visit the GitHub release page to find the VirusTotal link")

    print("\n" + "=" * 60)
    print("Verification complete.\n")


if __name__ == "__main__":
    main()
