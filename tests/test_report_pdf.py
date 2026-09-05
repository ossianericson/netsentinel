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


# ── The file: URL handed to the headless browser ──────────────────────────────

def _drive_browser_backend(rp, monkeypatch, tmp_path, temp_dir):
    """Run save_pdf_report far enough to record the browser argv, and return it.

    weasyprint is absent in this environment (and forced absent here anyway), so
    the headless-browser backend is the one that runs. The fake `subprocess.run`
    writes no PDF, so every candidate is tried and the function ends in its
    "no backend" RuntimeError — which is fine: the argv is what is under test.
    """
    import subprocess
    import sys

    calls: list = []
    live: set = set()

    class _Result:
        returncode = 0

    def _fake_run(cmd, **kw):
        calls.append(list(cmd))
        # Snapshot the temp dir while the browser would still be reading it —
        # save_pdf_report unlinks the file before it raises.
        live.update(str(f.resolve()) for f in temp_dir.iterdir())
        return _Result()

    monkeypatch.setattr(rp.tempfile, "tempdir", str(temp_dir))
    monkeypatch.setattr(rp, "generate_html", lambda *a, **k: "<html><body>x</body></html>")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    if sys.platform == "win32":
        # The Windows candidate list is absolute paths, so give it a real file to find.
        app = tmp_path / "prog" / "Microsoft" / "Edge" / "Application"
        app.mkdir(parents=True)
        (app / "msedge.exe").write_bytes(b"")
        monkeypatch.setenv("ProgramFiles", str(tmp_path / "prog"))
        monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "prog"))

    with pytest.raises(RuntimeError):
        rp.save_pdf_report(tmp_path / "report.pdf")

    assert calls, "no browser candidate was invoked"
    return calls[0], live


def _url_arg(argv: list) -> str:
    return next(a for a in argv if a.startswith("file:"))


def test_the_browser_url_resolves_back_to_the_temp_file(tmp_path, monkeypatch):
    """A `#` anywhere in the temp path silently truncates the URL at the fragment.

    `#` is legal in a Windows account name, and `%TEMP%` is under the profile, so
    `C:\\Users\\C#dev\\AppData\\Local\\Temp\\tmpX.html` is an ordinary path. Built by
    string interpolation it becomes `file:///C:\\Users\\C` plus a fragment, and the
    browser is asked for a file that does not exist.

    Measured against real headless Edge (msedge 2026-09-05): rc **0**, and a
    **83,902-byte PDF of the browser's own "file not found" page**, against 58,141
    bytes of real content from the same document via `Path.as_uri()`. So the
    failure does not raise, does not reach the "No PDF backend available" branch,
    and does not produce an empty file — `save_pdf_report()` returns success and the
    user opens a report containing a browser error. `Path.as_uri()` percent-encodes
    the `#`, which is the whole fix.

    Asserted as a round-trip rather than a string shape: whatever URL form is used,
    resolving it back must name the file that was written.
    """
    from urllib.parse import urlparse
    from urllib.request import url2pathname

    import modules.report_pdf as rp

    temp_dir = tmp_path / "C#dev"
    temp_dir.mkdir()

    argv, live = _drive_browser_backend(rp, monkeypatch, tmp_path, temp_dir)
    url = _url_arg(argv)
    parsed = urlparse(url)

    assert parsed.fragment == "", "the path was cut at the '#': %r" % url
    resolved = str(Path(url2pathname(parsed.path)).resolve())
    assert resolved in live, "the URL does not name the file that was written: %r" % url


@pytest.mark.parametrize("dirname", ["plain", "with space", "नमस्ते", "Иван"])
def test_ordinary_temp_paths_keep_resolving(tmp_path, monkeypatch, dirname):
    """The shapes that already worked must keep working.

    Measured on real headless Edge, the interpolated form handled spaces,
    Devanagari and Cyrillic paths correctly — byte-identical PDFs to `as_uri()`.
    Those are pinned here so the fix is a widening, not a swap.
    """
    from urllib.parse import urlparse
    from urllib.request import url2pathname

    import modules.report_pdf as rp

    temp_dir = tmp_path / dirname
    temp_dir.mkdir()

    argv, live = _drive_browser_backend(rp, monkeypatch, tmp_path, temp_dir)
    url = _url_arg(argv)
    resolved = str(Path(url2pathname(urlparse(url).path)).resolve())

    assert resolved in live, url
