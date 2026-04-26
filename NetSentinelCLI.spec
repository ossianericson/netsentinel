# -*- mode: python ; coding: utf-8 -*-
"""
NetSentinel CLI — PyInstaller build specification.

Produces a single-file console executable: dist/NetSentinel-cli[.exe]

The CLI binary is intentionally lightweight:
  - No PyQt6 / GUI stack
  - No matplotlib
  - No Scapy (all CLI commands use standard-library networking only)

Build:
    pyinstaller NetSentinelCLI.spec
"""

import os

# ── Data files ────────────────────────────────────────────────────────────────
datas = [("offenders.json", ".")]

# ── Hidden imports ────────────────────────────────────────────────────────────
# cli.py imports all modules inside function bodies (lazy), so PyInstaller's
# static tracer may not follow every path.  List them explicitly here.
hiddenimports: list = [
    "modules.rogue_device",
    "modules.port_scanner",
    "modules.network_diagnostics",
    "modules.network_logger",
    "modules.private_endpoint_checker",
    "modules.report_exporter",
    "modules.utils",
    "modules.nl_query",
    "modules.cloud_metadata",
    "modules.log_chart",
    # xml.etree used by report_exporter for Nmap XML output
    "xml.etree.ElementTree",
]

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ["cli.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Explicitly exclude the heavy GUI/ML stacks to keep the binary small.
        "PyQt6",
        "matplotlib",
        "scapy",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NetSentinel-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,   # CLI is always a console application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
