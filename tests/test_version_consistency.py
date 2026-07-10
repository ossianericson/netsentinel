"""
test_version_consistency.py

Asserts that every file that embeds the application version string contains
the same version as the canonical source: app.py `setApplicationVersion(...)`.

This test is the automated enforcement of RULE 11 (version bump checklist).
A failure here means at least one file was missed during a version bump.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Resolve the repository root (one level above /tests/)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent


def _canonical_version() -> str:
    """Extract version from app.py — the single source of truth."""
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    m = re.search(r'setApplicationVersion\(\s*"([^"]+)"\s*\)', text)
    assert m, "Could not find setApplicationVersion(...) in app.py"
    return m.group(1)


# ---------------------------------------------------------------------------
# Individual file checks — each is its own test so failures are pinpointed
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def canonical():
    return _canonical_version()


def test_cli_version(canonical):
    text = (ROOT / "cli.py").read_text(encoding="utf-8")
    m = re.search(r'_VERSION\s*=\s*"([^"]+)"', text)
    assert m, "Could not find _VERSION in cli.py"
    assert m.group(1) == canonical, (
        f"cli.py _VERSION={m.group(1)!r} does not match app.py {canonical!r}"
    )


def test_debug_launch_version(canonical):
    text = (ROOT / "tools" / "debug_launch.py").read_text(encoding="utf-8")
    m = re.search(r'setApplicationVersion\(\s*"([^"]+)"\s*\)', text)
    assert m, "Could not find setApplicationVersion(...) in tools/debug_launch.py"
    assert m.group(1) == canonical, (
        f"debug_launch.py version={m.group(1)!r} does not match app.py {canonical!r}"
    )


def test_apm_yml_version(canonical):
    text = (ROOT / "apm.yml").read_text(encoding="utf-8")
    m = re.search(r'^version:\s*(\S+)', text, re.MULTILINE)
    assert m, "Could not find version: field in apm.yml"
    assert m.group(1) == canonical, (
        f"apm.yml version={m.group(1)!r} does not match app.py {canonical!r}"
    )


def test_installer_iss_version(canonical):
    text = (ROOT / "installer.iss").read_text(encoding="utf-8")
    m = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', text)
    assert m, "Could not find #define MyAppVersion in installer.iss"
    assert m.group(1) == canonical, (
        f"installer.iss version={m.group(1)!r} does not match app.py {canonical!r}"
    )


def test_build_bat_version(canonical):
    text = (ROOT / "build.bat").read_text(encoding="utf-8")
    m = re.search(r'NetSentinel v([0-9]+\.[0-9]+(\.[0-9]+)?)', text)
    assert m, "Could not find 'NetSentinel vX.Y[.Z]' in build.bat"
    assert m.group(1) == canonical, (
        f"build.bat version={m.group(1)!r} does not match app.py {canonical!r}"
    )


def test_build_sh_version(canonical):
    text = (ROOT / "build.sh").read_text(encoding="utf-8")
    m = re.search(r'NetSentinel v([0-9]+\.[0-9]+(\.[0-9]+)?)', text)
    assert m, "Could not find 'NetSentinel vX.Y[.Z]' in build.sh"
    assert m.group(1) == canonical, (
        f"build.sh version={m.group(1)!r} does not match app.py {canonical!r}"
    )


def test_project_vision_version(canonical):
    # CLAUDE.md is no longer generated/tracked; the canonical version-stamped doc
    # is the APM source that bump_version.py updates and `apm` compiles to
    # .claude/rules/ (claude is the only configured apm.yml target).
    src = ROOT / ".apm" / "instructions" / "project-vision.instructions.md"
    text = src.read_text(encoding="utf-8")
    m = re.search(r'Current version:\s*\*\*v([^*]+)\*\*', text)
    assert m, "Could not find 'Current version:' in project-vision.instructions.md"
    assert m.group(1) == canonical, (
        f"project-vision.instructions.md Current version={m.group(1)!r} "
        f"does not match app.py {canonical!r}"
    )


def test_appxmanifest_msix_version_format(canonical):
    """
    MSIX version MUST be exactly 4 parts: X.Y.Z.W format.
    bump_version.py generates {canonical}.0, which is correct.
    makeappx.exe rejects 5-part versions (e.g., X.Y.Z.0.0) — test that we never do this.
    """
    text = (ROOT / "packaging" / "AppxManifest.xml").read_text(encoding="utf-8")
    m = re.search(r'Version="([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)"', text)
    assert m, "Could not find Version=... in AppxManifest.xml"
    
    msix_version = m.group(1)
    parts = msix_version.split(".")
    
    # CRITICAL: Must be exactly 4 parts
    assert len(parts) == 4, (
        f"AppxManifest.xml Version has {len(parts)} parts ({msix_version!r}), "
        f"expected exactly 4 (e.g., {canonical}.0)"
    )
    
    # Fourth part must be 0 (the .0 suffix)
    assert parts[3] == "0", (
        f"AppxManifest.xml Version fourth part must be 0, got {parts[3]!r} "
        f"in {msix_version!r}"
    )
    
    # First three parts must match the canonical version
    expected_msix = f"{canonical}.0"
    assert msix_version == expected_msix, (
        f"AppxManifest.xml Version={msix_version!r} does not match "
        f"expected {expected_msix!r} (canonical={canonical!r})"
    )


def test_appxmanifest_target_device_family_minversion(canonical):
    """
    TargetDeviceFamily MinVersion must be a valid Windows build (10.0.x.x),
    NOT the app version. bump_version.py's Version= regex must not match MinVersion=.
    """
    text = (ROOT / "packaging" / "AppxManifest.xml").read_text(encoding="utf-8")
    m = re.search(r'MinVersion="([^"]+)"', text)
    assert m, "Could not find MinVersion= in AppxManifest.xml TargetDeviceFamily"
    minver = m.group(1)
    parts = minver.split(".")
    assert parts[0] == "10", (
        f"AppxManifest.xml TargetDeviceFamily MinVersion={minver!r} must start with '10' "
        f"(Windows 10/11 build). Got {parts[0]!r}. "
        f"This is likely bump_version.py overwriting MinVersion with the app version ({canonical})."
    )


def test_splash_screen_version(canonical):
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    m = re.search(r'AlignmentFlag\.AlignCenter,\s*"v([^"]+)"', text)
    assert m, "Could not find splash screen version drawText in app.py"
    assert m.group(1) == canonical, (
        f"Splash screen version={m.group(1)!r} does not match app.py {canonical!r}"
    )
