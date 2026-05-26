#!/usr/bin/env python3
"""
bump_version.py — update version string across all tracked files in one shot.

Usage:
    python bump_version.py 1.60
    python bump_version.py 2.0.0

Covers every entry in RULE-R1.  After running, verify with:
    python -m pytest tests/test_version_consistency.py -v
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# Matches any X.Y or X.Y.Z version string (current value, whatever it is)
_VER = r"[0-9]+\.[0-9]+(?:\.[0-9]+)?"
# Matches a 4-part MSIX version X.Y.Z.W
_VER4 = r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"


def _sub(path: Path, pattern: str, replacement: str, flags: int = 0, count: int = 0) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, n = re.subn(pattern, replacement, text, count=count, flags=flags)
    if n == 0:
        print(f"  WARN  no match: {path.relative_to(ROOT)}")
        return
    path.write_text(new_text, encoding="utf-8")
    print(f"  ok    {path.relative_to(ROOT)}")


def bump(ver: str) -> None:
    print(f"\nBumping to {ver}\n")

    # app.py  ── canonical source of truth
    _sub(ROOT / "app.py",
         rf'(setApplicationVersion\("){_VER}("\))',
         rf'\g<1>{ver}\g<2>')

    # cli.py
    _sub(ROOT / "cli.py",
         rf'(_VERSION\s*=\s*"){_VER}(")',
         rf'\g<1>{ver}\g<2>')

    # installer.iss
    _sub(ROOT / "installer.iss",
         rf'(#define\s+MyAppVersion\s+"){_VER}(")',
         rf'\g<1>{ver}\g<2>')

    # apm.yml  ── top-level field only; changelog history is left intact
    _sub(ROOT / "apm.yml",
         rf'^(version:\s*){_VER}',
         rf'\g<1>{ver}',
         re.MULTILINE)

    # build scripts (banner line)
    _sub(ROOT / "build.bat",
         rf'(NetSentinel v){_VER}',
         rf'\g<1>{ver}')
    _sub(ROOT / "build.sh",
         rf'(NetSentinel v){_VER}',
         rf'\g<1>{ver}')

    # modules/rest_api.py  /health endpoint
    _sub(ROOT / "modules" / "rest_api.py",
         rf'("version":\s+"){_VER}(")',
         rf'\g<1>{ver}\g<2>')

    # tools/debug_launch.py
    _sub(ROOT / "tools" / "debug_launch.py",
         rf'(setApplicationVersion\("){_VER}("\))',
         rf'\g<1>{ver}\g<2>')

    # app.py  ── splash screen version label (drawText "vX.Y.Z")
    _sub(ROOT / "app.py",
         rf'(AlignmentFlag\.AlignCenter,\s*"v){_VER}(")',
         rf'\g<1>{ver}\g<2>')

    # packaging/AppxManifest.xml  — 4-part MSIX version (Major.Minor.Patch.0)
    # CRITICAL: Must be exactly 4 parts. makeappx.exe rejects 5-part versions.
    _sub(ROOT / "packaging" / "AppxManifest.xml",
         rf'(Version="){_VER4}(")',
         rf'\g<1>{ver}.0\g<2>')

    # WinGet manifests
    winget = ROOT / ".github" / "winget"
    for name in (
        "NetSentinel.NetSentinel.yaml",
        "NetSentinel.NetSentinel.installer.yaml",
        "NetSentinel.NetSentinel.locale.en-US.yaml",
    ):
        _sub(winget / name,
             rf'(PackageVersion:\s*){_VER}',
             rf'\g<1>{ver}')

    # Installer URL inside installer manifest  (vX.Y.Z/NetSentinel-Setup-X.Y.Z.exe)
    _sub(winget / "NetSentinel.NetSentinel.installer.yaml",
         rf'(releases/download/v){_VER}(/NetSentinel-Setup-){_VER}(\.exe)',
         rf'\g<1>{ver}\g<2>{ver}\g<3>')

    # README.md  ── only the first changelog header (current version); count=1 prevents
    # the wildcard _VER from also replacing older version headers below it
    _sub(ROOT / "README.md",
         rf'(###\s+v){_VER}',
         rf'\g<1>{ver}',
         count=1)

    # CLAUDE.md  ── "Current version" marker and version history chain
    _sub(ROOT / "CLAUDE.md",
         rf'(Current version:\s*\*\*v){_VER}(\*\*)',
         rf'\g<1>{ver}\g<2>')
    # Appends new version to end of the history line: "... → vX.Y.Z" → "... → vX.Y.Z → vNEW"
    _sub(ROOT / "CLAUDE.md",
         rf'(Version history \(condensed\):.*→ v)({_VER})$',
         rf'\g<1>\g<2> → v{ver}',
         re.MULTILINE)

    # .apm/instructions/project-vision.instructions.md  ── "Current version:" line
    _sub(ROOT / ".apm" / "instructions" / "project-vision.instructions.md",
         rf'(Current version:\s*\*\*v){_VER}(\*\*)',
         rf'\g<1>{ver}\g<2>')

    # ── redeploy APM rules to all targets (RULE-APM1) ─────────────────────────
    import shutil
    _apm = shutil.which("apm") or shutil.which("apm.cmd")
    if _apm:
        print("\nDeploying APM rules…")
        subprocess.run([_apm, "install", "--target", "all"], cwd=ROOT, check=False)
        subprocess.run([_apm, "compile", "--all"], cwd=ROOT, check=False)
    else:
        print("\n  WARN  apm CLI not found — run 'apm install --target all && apm compile --all' manually")

    # ── verify ────────────────────────────────────────────────────────────────
    print("\nRunning version consistency tests…")
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_version_consistency.py", "-v", "--tb=short"],
        cwd=ROOT,
    )
    if result.returncode == 0:
        print(f"\nAll good — version is now {ver}")
    else:
        print("\nConsistency tests failed — check warnings above.")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {Path(__file__).name} <version>")
        print("Example: python bump_version.py 1.60")
        sys.exit(1)
    bump(sys.argv[1])
