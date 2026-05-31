"""Tests for modules/web_dashboard.py — self-contained HTML dashboard builder."""
import pytest
from urllib.parse import urlparse


def test_web_dashboard_import():
    from modules import web_dashboard
    assert web_dashboard is not None


def test_build_html_returns_string():
    from modules.web_dashboard import build_html
    html = build_html("test-api-key")
    assert isinstance(html, str)
    assert len(html) > 100


def test_build_html_contains_doctype():
    from modules.web_dashboard import build_html
    html = build_html("test-api-key")
    assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()


def test_build_html_embeds_api_key():
    from modules.web_dashboard import build_html
    api_key = "my-secret-key-1234"
    html = build_html(api_key)
    assert api_key in html


def test_build_html_escapes_special_characters():
    from modules.web_dashboard import build_html
    dangerous_key = '<script>alert("xss")</script>'
    html = build_html(dangerous_key)
    assert "<script>alert(" not in html


def test_build_html_contains_auto_refresh():
    from modules.web_dashboard import build_html
    html = build_html("key")
    assert "refresh" in html.lower() or "interval" in html.lower()


def test_build_html_no_external_urls():
    from modules.web_dashboard import build_html
    html = build_html("key")
    lines = html.splitlines()
    for line in lines:
        for tok in line.split():
            if "://" in tok:
                parsed = urlparse(tok.strip('"\'<>'))
                if parsed.scheme in ("http", "https"):
                    assert parsed.hostname in (
                        "localhost", "127.0.0.1", None
                    ), f"Unexpected external URL in dashboard HTML: {tok}"
