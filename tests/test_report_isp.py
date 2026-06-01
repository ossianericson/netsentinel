"""Tests for modules/report_isp.py — see also test_sprint20_splits.py."""


def test_import():
    import modules.report_isp as m
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
