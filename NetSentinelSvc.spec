# -*- mode: python ; coding: utf-8 -*-
"""
NetSentinel Logger Service — PyInstaller build specification (Windows only).

Produces a single-file console executable: dist/NetSentinel-svc.exe

The service binary is intentionally minimal — it only runs NetworkLogger.
No GUI, no Scapy, no matplotlib required.

Pre-requisites:
    pip install pywin32
    python -m pywin32_postinstall -install   (run as Administrator, once only)

Build:
    pyinstaller NetSentinelSvc.spec

Install the built service (run as Administrator):
    dist\\NetSentinel-svc.exe install
    dist\\NetSentinel-svc.exe start
"""

import sys

if sys.platform != "win32":
    raise SystemExit(
        "NetSentinelSvc.spec is for Windows only.\n"
        "On macOS/Linux use a systemd service or launchd plist instead."
    )

# ── Data files ────────────────────────────────────────────────────────────────
datas = [("offenders.json", ".")]

# ── Hidden imports ────────────────────────────────────────────────────────────
# svc.py imports pywin32 inside a try/except block so PyInstaller cannot
# trace them statically.  The modules/network_logger dependencies are
# imported inside function bodies and also need to be listed explicitly.
hiddenimports: list = [
    # pywin32 — service framework
    "win32serviceutil",
    "win32service",
    "win32event",
    "win32con",
    "servicemanager",
    "pywintypes",
    "win32api",
    # RULE-WIN21 console codec — imported at svc.py module scope
    "modules.console_codec",
    "modules.crash_net",
    "modules.log_rotation",
    # NetworkLogger and its dependencies
    "modules.network_logger",
    "modules.utils",
    "csv",
    "threading",
    "configparser",
]

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ["svc.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Keep the service binary small — no GUI or packet-capture stack needed.
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
    name="NetSentinel-svc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Service executables must be console=True.
    # win32serviceutil.HandleCommandLine() relies on being able to write to
    # stdout/stderr; a windowed exe will silently fail to install.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icons/NetSentinel.ico" if sys.platform == "win32" else None,
)
