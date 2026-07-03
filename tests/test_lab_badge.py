"""Tests for modules/lab_badge.py (TDD — written before implementation)."""

import inspect


def test_import():
    from modules.lab_badge import render_lab_badge_png  # noqa: F401


def test_render_lab_badge_png_writes_file(tmp_path):
    from modules.lab_badge import render_lab_badge_png

    out = tmp_path / "badge.png"
    result = render_lab_badge_png("ARP Cache Poisoning Detective", "2026-07-03 14:22:00", out)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0


def test_render_lab_badge_png_no_fake_certification_wording():
    """Hard exclusion: no fake certification wording, no mock IDs anywhere in the module."""
    from modules import lab_badge

    src = inspect.getsource(lab_badge)
    for banned in ("certified", "certificate", "certification", "license"):
        assert banned not in src.lower()
