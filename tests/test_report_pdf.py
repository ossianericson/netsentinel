"""Tests for modules/report_pdf.py (RULE-T1)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Import ─────────────────────────────────────────────────────────────────────

def test_import():
    import modules.report_pdf as rp
    assert hasattr(rp, "save_pdf_report")
    assert callable(rp.save_pdf_report)


# ── weasyprint backend ─────────────────────────────────────────────────────────

def test_save_pdf_weasyprint_success(tmp_path):
    """save_pdf_report returns the output path when weasyprint succeeds."""
    import modules.report_pdf as rp

    output = tmp_path / "report.pdf"
    mock_html = MagicMock()
    mock_wp = MagicMock()
    mock_wp.HTML.return_value = mock_html

    with patch("modules.report_pdf.generate_html", return_value="<html></html>"):
        with patch.dict("sys.modules", {"weasyprint": mock_wp}):
            result = rp.save_pdf_report(output)

    assert result == output
    mock_html.write_pdf.assert_called_once_with(str(output))


def test_save_pdf_weasyprint_not_installed(tmp_path):
    """save_pdf_report falls through to browser backends when weasyprint is absent."""
    import modules.report_pdf as rp

    output = tmp_path / "report.pdf"

    def _raise_import(*a, **kw):
        raise ImportError("weasyprint not installed")

    with patch("modules.report_pdf.generate_html", return_value="<html></html>"):
        with patch.dict("sys.modules", {"weasyprint": None}):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                with pytest.raises((RuntimeError, FileNotFoundError, OSError)):
                    rp.save_pdf_report(output)


def test_save_pdf_weasyprint_runtime_error_propagates(tmp_path):
    """A weasyprint exception that is NOT ImportError propagates as RuntimeError."""
    import modules.report_pdf as rp

    output = tmp_path / "report.pdf"
    mock_html = MagicMock()
    mock_html.write_pdf.side_effect = Exception("renderer crash")
    mock_wp = MagicMock()
    mock_wp.HTML.return_value = mock_html

    with patch("modules.report_pdf.generate_html", return_value="<html></html>"):
        with patch.dict("sys.modules", {"weasyprint": mock_wp}):
            with pytest.raises(RuntimeError, match="weasyprint failed"):
                rp.save_pdf_report(output)


# ── generate_html integration ──────────────────────────────────────────────────

def test_generate_html_called_with_data(tmp_path):
    """save_pdf_report passes all data kwargs to generate_html."""
    import modules.report_pdf as rp

    output = tmp_path / "report.pdf"
    mock_html_obj = MagicMock()
    mock_wp = MagicMock()
    mock_wp.HTML.return_value = mock_html_obj

    with patch("modules.report_pdf.generate_html", return_value="<html>data</html>") as mock_gen:
        with patch.dict("sys.modules", {"weasyprint": mock_wp}):
            rp.save_pdf_report(
                output,
                overall_verdict="All clear",
                overall_level="CLEAN",
            )

    mock_gen.assert_called_once()
    _kw = mock_gen.call_args
    assert _kw is not None


# ── fallback: RuntimeError when no backend ────────────────────────────────────

def test_save_pdf_raises_when_no_backend(tmp_path):
    """save_pdf_report raises RuntimeError when weasyprint absent and no browser found."""
    import modules.report_pdf as rp

    output = tmp_path / "report.pdf"

    with patch("modules.report_pdf.generate_html", return_value="<html></html>"):
        with patch.dict("sys.modules", {"weasyprint": None}):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                with pytest.raises((RuntimeError, FileNotFoundError, OSError)):
                    rp.save_pdf_report(output)
