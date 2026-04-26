#!/usr/bin/env bash
set -e

echo "================================================"
echo " NetSentinel v1.0.0 — macOS / Linux Build"
echo "================================================"
echo ""
echo "Usage:"
echo "  ./build.sh           — production build (GUI + CLI)"
echo "  ./build.sh --debug   — debug GUI build (console window)"
echo "  ./build.sh --gui     — GUI only"
echo "  ./build.sh --cli     — CLI only"
echo ""

PLATFORM=$(uname -s)
BUILD_GUI=1
BUILD_CLI=1

if [ "$1" = "--gui" ]; then BUILD_CLI=0; fi
if [ "$1" = "--cli" ]; then BUILD_GUI=0; fi

# Install dependencies
echo "[1/4] Installing dependencies..."
pip install -r requirements.txt

# Pre-build smoke test — catches missing imports before wasting time on PyInstaller
echo ""
echo "[2/4] Pre-build import check..."
python app.py --smoke

echo ""
# --------------------------------------------------------------------------
# GUI build
# --------------------------------------------------------------------------
if [ "$BUILD_GUI" = "1" ]; then
    if [ "$1" = "--debug" ]; then
        echo "[3/4] Building DEBUG GUI executable (console window enabled)..."
        export NETSENTINEL_DEBUG=1
    else
        echo "[3/4] Building production GUI executable..."
        export NETSENTINEL_DEBUG=0
    fi
    pyinstaller NetSentinel.spec
else
    echo "[3/4] Skipping GUI build."
fi

# --------------------------------------------------------------------------
# CLI build
# --------------------------------------------------------------------------
echo ""
if [ "$BUILD_CLI" = "1" ]; then
    echo "[4/4] Building CLI executable..."
    pyinstaller NetSentinelCLI.spec
else
    echo "[4/4] Skipping CLI build."
fi

# Note: Windows service (NetSentinelSvc.spec) is Windows-only — not built here.

# Post-build smoke test (GUI only)
if [ "$BUILD_GUI" = "1" ]; then
    echo ""
    echo "[*] Post-build GUI smoke test..."
    if [ "$PLATFORM" = "Darwin" ]; then
        BINARY="dist/NetSentinel.app/Contents/MacOS/NetSentinel"
        [ -f "$BINARY" ] || BINARY="dist/NetSentinel"
    else
        BINARY="dist/NetSentinel"
    fi
    "$BINARY" --smoke
fi

echo ""
echo "================================================"
echo " Build complete!"
if [ "$BUILD_GUI" = "1" ]; then
    if [ "$PLATFORM" = "Darwin" ]; then
        echo "  GUI:  dist/NetSentinel.app"
    else
        echo "  GUI:  dist/NetSentinel"
    fi
fi
if [ "$BUILD_CLI" = "1" ]; then
    echo "  CLI:  dist/NetSentinel-cli"
fi
echo ""
echo "  Windows service: run build.bat on Windows"
echo "================================================"
