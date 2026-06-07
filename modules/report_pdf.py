"""
PDF report generation for NetSentinel — save_pdf_report().

Tries backends in order: weasyprint → headless Edge → headless Chrome.
Extracted from modules/report_exporter.py (S2-2 sprint split).
save_pdf_report() is re-exported from modules/report_exporter for backwards compatibility.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from modules.report_html import generate_html


def save_pdf_report(
    output_path: Path,
    module1_data=None,
    module2_data=None,
    module3_data=None,
    module4_data=None,
    module5_data=None,
    diagnostics_data=None,
    network_info_data=None,
    overall_verdict: str = "",
    overall_level: str = "CLEAN",
) -> Path:
    """
    Generate a PDF report from the same HTML template as save_report().

    Strategy (tries in order):
      1. weasyprint — pure Python, best fidelity (pip install weasyprint)
      2. headless Microsoft Edge (Windows) — msedge.exe --headless --print-to-pdf
      3. headless Google Chrome / Chromium — chrome --headless --print-to-pdf
      4. Fallback — saves HTML and raises RuntimeError listing install options

    Returns the Path to the saved PDF on success.
    Raises RuntimeError if no PDF backend is available.
    """
    html_content = generate_html(
        module1_data, module2_data, module3_data, module4_data, module5_data,
        diagnostics_data, network_info_data,
        overall_verdict, overall_level,
    )

    # ── Backend 1: weasyprint ───────────────────────────────────────────────
    try:
        import weasyprint  # type: ignore
        weasyprint.HTML(string=html_content).write_pdf(str(output_path))
        return output_path
    except ImportError:
        pass  # non-fatal
    except Exception as exc:
        raise RuntimeError(f"weasyprint failed: {exc}") from exc

    # ── Backends 2 & 3: headless browser ───────────────────────────────────
    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as tmp:
        tmp.write(html_content)
        tmp_html = tmp.name

    browser_candidates: list = []
    if sys.platform == "win32":
        import os
        browser_candidates += [
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LocalAppData", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]
    elif sys.platform == "darwin":
        browser_candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "chromium-browser",
            "chromium",
        ]
    else:
        browser_candidates += ["google-chrome", "chromium-browser", "chromium", "microsoft-edge"]

    import os
    pdf_out = str(output_path)
    for browser in browser_candidates:
        if not os.path.isabs(browser) or os.path.isfile(browser):
            try:
                result = subprocess.run(
                    [
                        browser,
                        "--headless",
                        "--disable-gpu",
                        "--no-sandbox",
                        f"--print-to-pdf={pdf_out}",
                        f"file:///{tmp_html}",
                    ],
                    capture_output=True,
                    timeout=30,
                )
                if result.returncode == 0 and Path(pdf_out).exists():
                    return output_path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            except Exception:
                continue

    try:
        Path(tmp_html).unlink(missing_ok=True)
    except Exception:
        pass  # non-fatal

    raise RuntimeError(
        "No PDF backend available.\n"
        "Install one of:\n"
        "  pip install weasyprint\n"
        "  OR install Google Chrome or Microsoft Edge"
    )
