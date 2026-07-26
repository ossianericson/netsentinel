"""Tests for scripts/update_release_body.py — RULE-REL1 status-aware release-notes rendering.

Only `build_security_section()` / `_vt_row()` are exercised — pure string formatting,
no GitHub API calls (those live behind `_api()`, untouched by these tests).
"""

from __future__ import annotations

from scripts.update_release_body import build_security_section, _vt_row


PERMALINK = "https://www.virustotal.com/gui/url/abc123def456"


def test_vt_row_clean_is_unchanged_link_style():
    row = _vt_row(PERMALINK, None, None, None)
    assert "VirusTotal scan" in row
    assert PERMALINK in row
    assert "⚠️" not in row and "🛑" not in row


def test_vt_row_flagged_shows_warning_and_detail():
    row = _vt_row(PERMALINK, "flagged", "1/92", "EngineA")
    assert "⚠️" in row
    assert "1/92" in row
    assert "EngineA" in row
    assert PERMALINK in row


def test_vt_row_blocked_shows_block_marker():
    row = _vt_row(PERMALINK, "blocked", "5/92", "EngineA, EngineB")
    assert "🛑" in row
    assert "5/92" in row
    assert "EngineA, EngineB" in row


def test_vt_row_timeout_says_not_confirmed_clean():
    row = _vt_row(PERMALINK, "timeout", None, None)
    assert "not confirmed clean" in row


def test_build_security_section_flagged_does_not_look_clean():
    body = build_security_section(
        version="2.1.45",
        sha256sums_url="https://example.com/SHA256SUMS.txt",
        vt_permalink=PERMALINK,
        bundle_name=None,
        vt_status="flagged",
        vt_detections="1/92",
        vt_engines="EngineA",
    )
    assert "⚠️" in body
    assert "1/92" in body
    assert "EngineA" in body


def test_build_security_section_blocked_includes_human_override_note():
    note = "reviewed 2026-07-26 by Ossian: single heuristic engine, judged non-blocking"
    body = build_security_section(
        version="2.1.45",
        sha256sums_url="https://example.com/SHA256SUMS.txt",
        vt_permalink=PERMALINK,
        bundle_name=None,
        vt_status="blocked",
        vt_detections="5/92",
        vt_engines="EngineA, EngineB",
        human_override=note,
    )
    assert "🛑" in body
    assert note in body
    assert "Manually reviewed" in body


def test_build_security_section_blocked_without_override_has_no_reviewer_note():
    body = build_security_section(
        version="2.1.45",
        sha256sums_url="https://example.com/SHA256SUMS.txt",
        vt_permalink=PERMALINK,
        bundle_name=None,
        vt_status="blocked",
        vt_detections="5/92",
        vt_engines="EngineA",
    )
    assert "Manually reviewed" not in body


def test_build_security_section_clean_preserves_existing_shape():
    body = build_security_section(
        version="2.1.45",
        sha256sums_url="https://example.com/SHA256SUMS.txt",
        vt_permalink=PERMALINK,
        bundle_name="NetSentinel-Setup-2.1.45.exe.bundle",
        msix_bundle_name="NetSentinel-2.1.45.msix.bundle",
    )
    assert "## Security & Verification" in body
    assert "cosign verify-blob" in body
    assert "SHA256SUMS.txt" in body


def test_build_security_section_no_permalink_falls_back_to_bullet():
    body = build_security_section(
        version="2.1.45",
        sha256sums_url="https://example.com/SHA256SUMS.txt",
        vt_permalink=None,
        bundle_name=None,
    )
    assert "VirusTotal" not in body
    assert "SHA256SUMS.txt" in body
