@echo off
echo ================================================
echo  NetSentinel v1.3.1 — Windows Build Script
echo ================================================
echo.
echo Usage:
echo   build.bat           — production build (all three executables)
echo   build.bat --debug   — debug build of the GUI (console window)
echo   build.bat --gui     — GUI only (skip CLI and service)
echo   build.bat --cli     — CLI only
echo   build.bat --svc     — Windows service only
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Determine what to build
set BUILD_GUI=1
set BUILD_CLI=1
set BUILD_SVC=1
if "%1"=="--gui" ( set BUILD_CLI=0 & set BUILD_SVC=0 )
if "%1"=="--cli" ( set BUILD_GUI=0 & set BUILD_SVC=0 )
if "%1"=="--svc" ( set BUILD_GUI=0 & set BUILD_CLI=0 )

:: Install / upgrade dependencies
echo [1/5] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

:: If building the service, check pywin32 is present
if "%BUILD_SVC%"=="1" (
    python -c "import win32serviceutil" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo NOTE: pywin32 not installed — skipping Windows service build.
        echo       To build the service:
        echo         pip install pywin32
        echo         python -m pywin32_postinstall -install   (as Administrator)
        echo.
        set BUILD_SVC=0
    )
)

:: Pre-build smoke test
echo.
echo [2/5] Pre-build import check...
python app.py --smoke
if errorlevel 1 (
    echo ERROR: Import check failed. Fix the errors above before building.
    pause
    exit /b 1
)

echo.
:: --------------------------------------------------------------------------
:: GUI build
:: --------------------------------------------------------------------------
if "%BUILD_GUI%"=="1" (
    if "%1"=="--debug" (
        echo [3/5] Building DEBUG GUI executable ^(console window enabled^)...
        set NETSENTINEL_DEBUG=1
    ) else (
        echo [3/5] Building production GUI executable...
        set NETSENTINEL_DEBUG=0
    )
    python -m PyInstaller NetSentinel.spec
    if errorlevel 1 (
        echo ERROR: GUI build failed.
        pause
        exit /b 1
    )
) else (
    echo [3/5] Skipping GUI build.
)

:: --------------------------------------------------------------------------
:: CLI build
:: --------------------------------------------------------------------------
echo.
if "%BUILD_CLI%"=="1" (
    echo [4/5] Building CLI executable...
    python -m PyInstaller NetSentinelCLI.spec
    if errorlevel 1 (
        echo ERROR: CLI build failed.
        pause
        exit /b 1
    )
) else (
    echo [4/5] Skipping CLI build.
)

:: --------------------------------------------------------------------------
:: Windows Service build
:: --------------------------------------------------------------------------
echo.
if "%BUILD_SVC%"=="1" (
    echo [5/5] Building Windows service executable...
    python -m PyInstaller NetSentinelSvc.spec
    if errorlevel 1 (
        echo ERROR: Service build failed.
        pause
        exit /b 1
    )
) else (
    echo [5/5] Skipping service build.
)

:: Post-build smoke test (GUI only — CLI and service have no --smoke)
echo.
if "%BUILD_GUI%"=="1" (
    echo [*] Post-build GUI smoke test...
    dist\NetSentinel.exe --smoke
    if errorlevel 1 (
        echo ERROR: Bundled executable failed the smoke test.
        echo        Run with --debug flag for a console build to diagnose.
        pause
        exit /b 1
    )
)

echo.
echo ================================================
echo  Build complete!
if "%BUILD_GUI%"=="1" echo   GUI:     dist\NetSentinel.exe
if "%BUILD_CLI%"=="1" echo   CLI:     dist\NetSentinel-cli.exe
if "%BUILD_SVC%"=="1" echo   Service: dist\NetSentinel-svc.exe
echo.
echo To install the service (run as Administrator):
echo   dist\NetSentinel-svc.exe install
echo   dist\NetSentinel-svc.exe start
echo ================================================
echo.
pause
