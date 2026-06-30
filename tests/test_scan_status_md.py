"""Tests for modules/scan_status_md.py — Markdown rendering of the scan registry.

Behavioural coverage for the "Copy Scan Status as Markdown" feature (v2.1.20).
The module is pure Python (no PyQt) so these run headless in CI.
"""

import time

import pytest

from modules import scan_status_md


_LABELS = (
    "Port Scan (TCP)",
    "CVE Lookup",
    "Exposed to Internet",
)


def test_import_and_callable():
    assert callable(scan_status_md.render_scan_status_md)


def test_returns_markdown_with_title_and_table_header():
    out = scan_status_md.render_scan_status_md({}, _LABELS)
    assert isinstance(out, str)
    assert out.startswith("## ")
    # markdown table header + separator row present
    assert "| Tool | State | Last run | Finding |" in out
    assert "| --- |" in out


def test_one_data_row_per_label():
    out = scan_status_md.render_scan_status_md({}, _LABELS)
    # one row per label, each label appears as the leading cell of its row
    for label in _LABELS:
        assert f"| {label} |" in out
    data_rows = [ln for ln in out.splitlines() if ln.startswith("| ") and "---" not in ln]
    # header row + one row per label
    assert len(data_rows) == 1 + len(_LABELS)


def test_missing_label_shows_never_run_and_dash():
    out = scan_status_md.render_scan_status_md({}, _LABELS)
    row = next(ln for ln in out.splitlines() if ln.startswith("| CVE Lookup |"))
    assert "Never run" in row
    assert row.rstrip().endswith("— |")


def test_fresh_entry_shows_human_state_and_verdict():
    now = time.time()
    registry = {
        "Port Scan (TCP)": {
            "state": "fresh",
            "ts": now - 120,
            "verdict": "3 open ports",
            "error": None,
        }
    }
    out = scan_status_md.render_scan_status_md(registry, _LABELS, now=now)
    row = next(ln for ln in out.splitlines() if ln.startswith("| Port Scan (TCP) |"))
    assert "Fresh" in row
    assert "3 open ports" in row
    assert "ago" in row  # age rendered for a real timestamp


def test_error_state_uses_error_text_when_no_verdict():
    now = time.time()
    registry = {
        "CVE Lookup": {"state": "error", "ts": now - 30, "verdict": None,
                       "error": "network unreachable"},
    }
    out = scan_status_md.render_scan_status_md(registry, _LABELS, now=now)
    row = next(ln for ln in out.splitlines() if ln.startswith("| CVE Lookup |"))
    assert "Error" in row
    assert "network unreachable" in row


def test_pipe_in_verdict_is_escaped_to_not_break_table():
    registry = {
        "Port Scan (TCP)": {"state": "fresh", "ts": time.time(),
                            "verdict": "tcp|80|443 open", "error": None},
    }
    out = scan_status_md.render_scan_status_md(registry, _LABELS)
    row = next(ln for ln in out.splitlines() if ln.startswith("| Port Scan (TCP) |"))
    # a raw pipe would add phantom columns; it must be escaped
    assert "tcp\\|80\\|443 open" in row


def test_never_ts_renders_never_not_ago():
    out = scan_status_md.render_scan_status_md(
        {"OS Detection": {"state": "never", "ts": 0, "verdict": None, "error": None}},
        ("OS Detection",),
    )
    row = next(ln for ln in out.splitlines() if ln.startswith("| OS Detection |"))
    assert "Never" in row
    assert "ago" not in row


def test_custom_title_is_used():
    out = scan_status_md.render_scan_status_md({}, _LABELS, title="My Audit")
    assert out.startswith("## My Audit")


@pytest.mark.parametrize(
    "age_seconds,expected_substr",
    [
        (5, "just now"),
        (90, "m ago"),
        (3 * 3600, "h ago"),
        (2 * 86400, "d ago"),
    ],
)
def test_age_formatting_buckets(age_seconds, expected_substr):
    now = 1_000_000.0
    assert expected_substr in scan_status_md._format_age(now - age_seconds, now)
