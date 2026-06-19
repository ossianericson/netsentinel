"""
scripts/extract_changelog.py — Build a GitHub Release body from README.md changelog.

Extracts the ### vX.Y.Z block for the given version and writes release_body.md
containing the changelog entry followed by the static install instructions.

Usage (called from release.yml):
    python scripts/extract_changelog.py <version>

Writes:
    release_body.md  (passed to softprops/action-gh-release as body_path)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_STATIC_TAIL = """\
### Recommended install

```powershell
winget install NetSentinel.NetSentinel
```

Or download manually:

| Platform | File | Notes |
|---|---|---|
| **Windows** | `NetSentinel-Setup-*.exe` | Installer — adds to Start Menu + PATH. Use winget (above) instead if possible. |
| **Windows** | `NetSentinel-svc.exe` | Background Windows service (not in winget). |
| **macOS** | `NetSentinel-macOS.zip` | GUI — unzip, right-click → Open. |
| **macOS** | `NetSentinel-cli-macOS` | Headless CLI. |
| **Linux** | `NetSentinel` | GUI — `chmod +x NetSentinel && sudo ./NetSentinel` |
| **Linux** | `NetSentinel-cli-linux` | Headless CLI. |

### What it does
One tool that replaces a drawer full of network utilities:
- Rogue device fingerprinting with curated OUI registry (Google, TP-Link, Apple, Amazon, Samsung, LG, PlayStation, Nintendo, Xbox, Roku, Netgear, Asus)
- STP/BPDU rogue Root Bridge detection
- Broadcast & multicast storm analysis
- IoT Behavioral Baseline — learns normal device traffic, alerts on deviations
- Root Cause Correlator — distinguishes ISP fault from local network fault
- Network Grade (A–F) across 8 dimensions — uptime, latency, jitter, DNS, speed, safety, STP, storm
- ISP Accountability Report — HTML export with MTR hop table and outage log for support tickets
- How-to-Fix context menus on every scan result
- Hidden SSID and co-channel WiFi interference detection
- Live ping + DNS latency correlation
- On-demand diagnostics: speed test, DNS leak, traceroute, public IP
- Long-term background connectivity logger with stability scoring
- TCP port scanner, OS fingerprinter, CVE lookup, MTR, and more
- HTML, JSON, CSV, Nmap XML report export
"""


def extract_changelog(readme: str, version: str) -> str:
    """Return the ### vVERSION block from readme, or a fallback string."""
    pattern = rf"(### v{re.escape(version)}\b.*?)(?=\n### v|\Z)"
    m = re.search(pattern, readme, re.DOTALL)
    if m:
        return m.group(1).strip()
    return f"### v{version}\n\n_No changelog entry found._"


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <version>", file=sys.stderr)
        sys.exit(1)

    version = sys.argv[1]
    readme = Path("README.md").read_text(encoding="utf-8")
    changelog = extract_changelog(readme, version)

    body = (
        f"## NetSentinel v{version}\n\n"
        f"{changelog}\n\n"
        f"---\n\n"
        f"{_STATIC_TAIL}"
    )

    Path("release_body.md").write_text(body, encoding="utf-8")
    print(f"release_body.md written ({len(body)} chars)", flush=True)
    print(f"Changelog entry preview:\n{changelog[:300]}", flush=True)


if __name__ == "__main__":
    main()
