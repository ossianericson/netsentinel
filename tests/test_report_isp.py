"""Tests for modules/report_isp.py — see also test_sprint20_splits.py."""


def test_import():
    from modules import report_isp as m
    assert hasattr(m, "generate_isp_report")
    assert hasattr(m, "save_isp_report")
    assert hasattr(m, "_ISP_CSS")


def test_generate_isp_report_returns_html():
    from modules.report_isp import generate_isp_report
    html = generate_isp_report()
    assert "<!DOCTYPE html>" in html
    assert "ISP Accountability Report" in html
    assert "NetSentinel" in html


def test_generate_isp_report_no_data_grade():
    from modules.report_isp import generate_isp_report
    html = generate_isp_report()
    assert "N/A" in html or "grade-F" in html


def test_isp_css_non_empty():
    from modules.report_isp import _ISP_CSS
    assert len(_ISP_CSS) > 100
    assert "isp-header" in _ISP_CSS


# ── generate_isp_complaint_text ───────────────────────────────────────────────

def test_complaint_text_import():
    from modules.report_isp import generate_isp_complaint_text
    assert callable(generate_isp_complaint_text)


def test_complaint_text_no_data():
    from modules.report_isp import generate_isp_complaint_text
    text = generate_isp_complaint_text()
    assert "ISP" in text or "broadband" in text
    assert "NetSentinel" in text


def test_complaint_text_isp_name():
    from modules.report_isp import generate_isp_complaint_text
    text = generate_isp_complaint_text(isp_name="Acme Broadband")
    assert "Acme Broadband" in text


def test_complaint_text_account_ref():
    from modules.report_isp import generate_isp_complaint_text
    text = generate_isp_complaint_text(account_ref="REF-9999")
    assert "REF-9999" in text


def test_complaint_text_legal_block():
    from modules.report_isp import generate_isp_complaint_text
    text_no_legal = generate_isp_complaint_text(include_legal=False)
    text_legal    = generate_isp_complaint_text(include_legal=True)
    assert "Consumer Rights Act" in text_legal
    assert "Consumer Rights Act" not in text_no_legal


def test_complaint_text_with_measurements():
    from modules.report_isp import generate_isp_complaint_text

    class _FakeLog:
        uptime_pct   = 97.5
        avg_rtt_ms   = 42.0
        avg_jitter_ms = 8.3
        outages      = ["o1", "o2"]

    class _FakeDiag:
        download_mbps = 78.4

    text = generate_isp_complaint_text(log_summary=_FakeLog(), diag_result=_FakeDiag())
    assert "97.5%" in text
    assert "42.0 ms" in text
    assert "78.4 Mbps" in text
    assert "2 recorded outage" in text
