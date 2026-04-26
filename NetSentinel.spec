# -*- mode: python ; coding: utf-8 -*-
"""
NetSentinel — PyInstaller build specification.

This is the SINGLE SOURCE OF TRUTH for the packaged executable.
Edit this file when adding new modules or dependencies.
build.bat and .github/workflows/release.yml both reference it so
changes propagate to all platforms automatically.

Build (production, windowed):
    pyinstaller NetSentinel.spec

Debug build (keeps a console window so print/traceback output is visible):
    set NETSENTINEL_DEBUG=1 && pyinstaller NetSentinel.spec   (Windows)
    NETSENTINEL_DEBUG=1 pyinstaller NetSentinel.spec           (macOS/Linux)
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all

# ── Build mode ────────────────────────────────────────────────────────────────
# Set NETSENTINEL_DEBUG=1 to get a console window for troubleshooting.
_debug_build = os.environ.get("NETSENTINEL_DEBUG", "0") == "1"

# ── Data files ────────────────────────────────────────────────────────────────
datas = [("offenders.json", ".")]

# ── Collect whole packages (data + binaries + submodule tree) ─────────────────
# PyInstaller cannot auto-discover dynamically-loaded backends and lazy-loaded
# protocol layers, so we collect every file for these three packages.
binaries: list = []
hiddenimports: list = [
    # PyQt6 Qt modules that are loaded at runtime via dynamic dispatch
    "PyQt6.sip",
    "PyQt6.QtCore",
    "PyQt6.QtWidgets",
    "PyQt6.QtGui",
    "PyQt6.QtNetwork",
    "PyQt6.QtPrintSupport",
    "PyQt6.QtSvg",
    "PyQt6.QtOpenGL",
    "PyQt6.QtOpenGLWidgets",
    # Matplotlib backend used by ui/live_graph.py  ← was the original crash cause
    "matplotlib.backends.backend_qtagg",
    # Scapy loads all protocol layers lazily; collect them explicitly
    "scapy.layers.all",
    "scapy.arch.windows",
    # modules only referenced via __import__() strings in smoke test —
    # PyInstaller's static tracer cannot follow dynamic string imports
    "modules.tls_checker",
    "modules.arp_monitor",
    "modules.bandwidth_monitor",
    "modules.dhcp_detector",
    "modules.snmp_poller",
    "modules.scheduler",
    "modules.device_classifier",
    "modules.risk_scorer",
    "modules.syn_scanner",
    "modules.cve_lookup",
    "modules.internet_exposure",
    "modules.os_fingerprint",
    "modules.credentialed_scan",
    "modules.combined_discovery",
    "modules.smb_enumerator",
    "modules.nl_query",
    "modules.plugin_system",
    "modules.private_endpoint_checker",
    "ui.topology_widget",
    "ui.matrix_rain",
]

for _pkg in ("scapy", "PyQt6", "matplotlib"):
    _d, _b, _h = collect_all(_pkg)
    datas         += _d
    binaries      += _b
    hiddenimports += _h

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NetSentinel",
    debug=_debug_build,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=_debug_build,              # False in production, True for debug
    disable_windowed_traceback=False,  # Show crash tracebacks even in windowed mode
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# macOS: wrap the binary in a .app bundle (only relevant on macOS)
if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821 — PyInstaller injects this name at build time
        exe,
        name="NetSentinel.app",
        icon=None,
        bundle_identifier="com.netsentinel.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
