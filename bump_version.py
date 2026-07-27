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
# Matches a comma-grouped or bare integer (existing figures use either style)
_NUM = r"[0-9][0-9,]*"


def _test_stats() -> tuple[int, int]:
    """Collect the current total test count and test-file count.

    Uses `-m ""` to override the default marker deselection (live/benchmark/monkey
    in pyproject.toml addopts) so the figure reflects every test in the suite, not
    just the ones a default `pytest tests/` run selects.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q", "-m", ""],
        cwd=ROOT, capture_output=True, text=True,
    )
    match = re.search(r"^(\d+) tests? collected", result.stdout, re.MULTILINE)
    if not match:
        print("  WARN  could not determine test count — skipping test-count refresh")
        print(result.stdout[-500:])
        return 0, 0
    n_tests = int(match.group(1))
    n_files = len(list((ROOT / "tests").rglob("test_*.py")))
    return n_tests, n_files


def _preflight_whats_new(ver: str) -> None:
    """Abort before ANY file is written if the in-app "What's New" is stale.

    `ui/help_tab.py` carries hand-written release prose that this script
    deliberately never rewrites — auto-bumping it would relabel the previous
    release's bullets as the new version, which is the defect the check exists
    to catch (v2.1.47 shipped showing v2.1.46's bullets).

    tests/test_version_consistency.py::test_whats_new_version catches the same
    thing at the end of this run, but by then ~20 files have already been
    rewritten, leaving a half-bumped tree to unpick by hand.  Fail here instead,
    while the tree is still clean.
    """
    path = ROOT / "ui" / "help_tab.py"
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^_WHATS_NEW_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match is None:
        print("error: could not find _WHATS_NEW_VERSION in ui/help_tab.py")
        print("       (expected a module-level assignment — has the file been restructured?)")
        sys.exit(1)
    if match.group(1) != ver:
        print(f"error: ui/help_tab.py still describes v{match.group(1)}, not v{ver}.\n")
        print("The in-app \"What's New\" section is hand-written and is NOT bumped")
        print("automatically. Nothing has been modified — fix this first:\n")
        print("  1. Rewrite _WHATS_NEW_ENTRIES in ui/help_tab.py to describe this")
        print("     release's changes (match the top CHANGELOG.md entry).")
        print(f'  2. Set _WHATS_NEW_VERSION = "{ver}".')
        print(f"  3. Re-run: python bump_version.py {ver}")
        sys.exit(1)


def _sub(path: Path, pattern: str, replacement: str, flags: int = 0, count: int = 0) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, n = re.subn(pattern, replacement, text, count=count, flags=flags)
    if n == 0:
        print(f"  WARN  no match: {path.relative_to(ROOT)}")
        return
    path.write_text(new_text, encoding="utf-8")
    print(f"  ok    {path.relative_to(ROOT)}")


def bump(ver: str) -> None:
    # Runs before the first _sub() so a stale "What's New" leaves a clean tree.
    _preflight_whats_new(ver)

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

    # packaging/AppxManifest.xml  — 4-part MSIX version in <Identity> only.
    # CRITICAL: Must be exactly 4 parts. makeappx.exe rejects 5-part versions.
    # Use a line-start anchor (^\s+Version=") so we ONLY match the Identity element's
    # Version attribute, which sits on its own indented line.  MinVersion= and
    # MaxVersionTested= live on the <TargetDeviceFamily ...> line which begins with
    # "<", not whitespace-then-Version, so they are never touched.
    _sub(ROOT / "packaging" / "AppxManifest.xml",
         rf'(^\s+Version="){_VER4}(")',
         rf'\g<1>{ver}.0\g<2>',
         flags=re.MULTILINE)

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

    # CHANGELOG.md  ── promote the topmost header to the new version
    _sub(ROOT / "CHANGELOG.md",
         rf'(###\s+v){_VER}',
         rf'\g<1>{ver}',
         count=1)

    # ── test-count figures ─────────────────────────────────────────────────────
    # README.md and docs/architecture.md each carry a hand-written "N tests across
    # M files" figure that nobody remembers to refresh — recompute it every bump
    # instead of relying on a human noticing the drift.
    print("\nRecomputing test-count figures…")
    n_tests, n_files = _test_stats()
    if n_tests and n_files:
        n_tests_str = f"{n_tests:,}"
        n_files_str = f"{n_files:,}"

        _sub(ROOT / "README.md",
             rf'(badge/tests-){_NUM}(%2B)',
             rf'\g<1>{n_tests}\g<2>')
        _sub(ROOT / "README.md",
             rf'(\*\*){_NUM}(\+ tests)',
             rf'\g<1>{n_tests_str}\g<2>')
        _sub(ROOT / "README.md",
             rf'(\*\*){_NUM}( automated tests\*\* across ){_NUM}( test files)',
             rf'\g<1>{n_tests_str}\g<2>{n_files_str}\g<3>')
        _sub(ROOT / "docs" / "architecture.md",
             rf'(The test suite has ){_NUM}( tests across ){_NUM}( files\.)',
             rf'\g<1>{n_tests_str}\g<2>{n_files_str}\g<3>')
        print(f"  {n_tests_str} tests across {n_files_str} files")

    # .apm/instructions/project-vision.instructions.md  ── "Current version:" line
    # (This is the canonical version-stamped doc. CLAUDE.md is no longer generated
    #  or tracked — Claude Code reads .claude/rules/ directly via `apm install`.)
    _sub(ROOT / ".apm" / "instructions" / "project-vision.instructions.md",
         rf'(Current version:\s*\*\*v){_VER}(\*\*)',
         rf'\g<1>{ver}\g<2>')

    # ── redeploy APM rules to the claude target (RULE-APM1) ───────────────────
    import shutil
    _apm = shutil.which("apm") or shutil.which("apm.cmd")
    if _apm:
        print("\nDeploying APM rules…")
        subprocess.run([_apm, "install", "--target", "claude"], cwd=ROOT, check=False)
        subprocess.run([_apm, "compile", "--target", "claude", "--clean"], cwd=ROOT, check=False)
    else:
        print("\n  WARN  apm CLI not found — run 'apm install --target claude && apm compile --target claude --clean' manually")

    # ── verify ────────────────────────────────────────────────────────────────
    print("\nRunning version consistency tests…")
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_version_consistency.py", "-v", "--tb=short"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("\nConsistency tests failed — check warnings above.")
        sys.exit(1)

    print(f"\nAll good — version is now {ver}")

    # ── auto-commit all version-touched files ─────────────────────────────────
    _VERSION_FILES = [
        "app.py", "cli.py", "apm.yml", "apm.lock.yaml", "installer.iss",
        "build.bat", "build.sh", "modules/rest_api.py", "tools/debug_launch.py",
        "packaging/AppxManifest.xml",
        "bump_version.py",
        ".github/winget/NetSentinel.NetSentinel.yaml",
        ".github/winget/NetSentinel.NetSentinel.installer.yaml",
        ".github/winget/NetSentinel.NetSentinel.locale.en-US.yaml",
        "README.md", "CHANGELOG.md", "ui/dashboard.py",
        # Hand-edited (see _preflight_whats_new) — staged here so the What's New
        # rewrite lands in the release commit instead of being left behind.
        "ui/help_tab.py",
        "docs/architecture.md",
        ".apm/instructions/project-vision.instructions.md",
        ".claude/rules/project-vision.md",
    ]
    print("\nStaging version files…")
    existing = [f for f in _VERSION_FILES if (ROOT / f).exists()]
    add_result = subprocess.run(
        ["git", "add", "--"] + existing,
        cwd=ROOT, capture_output=True, text=True,
    )
    if add_result.returncode != 0:
        print(f"  WARN  git add failed: {add_result.stderr.strip()}")
        print(f"  Run manually: git add -A && git commit -m 'chore: bump version to v{ver}'")
    else:
        commit_result = subprocess.run(
            ["git", "commit", "-m", f"chore: bump version to v{ver}"],
            cwd=ROOT, capture_output=True, text=True,
        )
        out = commit_result.stdout + commit_result.stderr
        if commit_result.returncode == 0:
            print(f"  ok    committed — chore: bump version to v{ver}")
        elif "nothing to commit" in out:
            print("  ok    nothing to commit (already up to date)")
        else:
            print(f"  WARN  git commit failed: {out.strip()}")
            print(f"  Run manually: git commit -m 'chore: bump version to v{ver}'")

    print(f"\nNext steps:")
    print(f"  git push origin main")
    print(f"  git tag v{ver}")
    print(f"  git push origin v{ver}")


_USAGE = f"""\
{Path(__file__).name} — bump the NetSentinel version string across all tracked files.

Usage:
    python {Path(__file__).name} <version>

Arguments:
    <version>   New version, plain semver: X.Y or X.Y.Z (digits and dots only).
                Examples: 1.60, 2.0.0, 2.1.24

Options:
    -h, --help  Show this message and exit.

After running, verify with:
    python -m pytest tests/test_version_consistency.py -v
"""

# Plain semver only — guards against an option string (e.g. "--help") being
# mistaken for a version and rewritten into every file. See RULE-R1.
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(_USAGE)
        # Exit 0 for an explicit help request; exit 2 when no version was given.
        sys.exit(0 if args else 2)
    if len(args) != 1 or not _SEMVER.match(args[0]):
        print(f"error: invalid version {args[0]!r} — expected plain semver X.Y or X.Y.Z\n")
        print(_USAGE)
        sys.exit(2)
    bump(args[0])
