@echo off
echo ================================================
echo  NetSentinel v1.7.2 — Windows Build Script
echo ================================================
echo.
echo Usage:
echo   build.bat           — production build (all three executables)
echo   build.bat --debug   — debug build of the GUI (console window)
echo   build.bat --gui     — GUI only (skip CLI and service)
echo   build.bat --cli     — CLI only
echo   build.bat --svc     — Windows service only
echo.

:: ── Python: prefer .venv311 (Python 3.11, matches GitHub Actions) ──────────
:: If the venv does not exist yet, create it and install deps.
if exist .venv311\Scripts\python.exe (
    set PYTHON=.venv311\Scripts\python.exe
) else (
    echo [0/5] .venv311 not found — creating Python 3.11 build environment...
    py -3.11 -m venv .venv311
    if errorlevel 1 (
        echo ERROR: py -3.11 not found. Install Python 3.11 from https://python.org
        pause
        exit /b 1
    )
    .venv311\Scripts\pip install -r requirements.txt pyinstaller
    if errorlevel 1 (
        echo ERROR: pip install failed in .venv311
        pause
        exit /b 1
    )
    set PYTHON=.venv311\Scripts\python.exe
)

echo Using: %PYTHON%
%PYTHON% --version

:: Verify the venv is actually Python 3.11 — if py -3.11 was not found and
:: another Python was used instead, the speed test will fail in the exe.
for /f "tokens=2" %%v in ('%PYTHON% --version 2^>^&1') do set PYVER=%%v
echo Python version in venv: %PYVER%
echo %PYVER% | findstr /b "3.11" >nul
if errorlevel 1 (
    echo.
    echo ERROR: .venv311 is not Python 3.11 ^(got %PYVER%^).
    echo        Speed test requires Python 3.11. Delete .venv311 and re-run.
    echo        Install Python 3.11 first: winget install Python.Python.3.11
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
.venv311\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

:: Verify speedtest-cli is present — required for speed test feature.
:: It must be installed in the build venv or PyInstaller will not bundle it.
%PYTHON% -c "import speedtest" >nul 2>&1
if errorlevel 1 (
    echo [1/5] speedtest-cli not found in venv — installing...
    .venv311\Scripts\pip install speedtest-cli
    if errorlevel 1 (
        echo ERROR: Failed to install speedtest-cli. Speed test will not work in the exe.
        pause
        exit /b 1
    )
)

:: If building the service, check pywin32 is present
if "%BUILD_SVC%"=="1" (
    %PYTHON% -c "import win32serviceutil" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo NOTE: pywin32 not installed — skipping Windows service build.
        echo       To build the service:
        echo         .venv311\Scripts\pip install pywin32
        echo         %PYTHON% -m pywin32_postinstall -install   (as Administrator)
        echo.
        set BUILD_SVC=0
    )
)

:: Pre-build smoke test
echo.
echo [2/5] Pre-build import check...
%PYTHON% app.py --smoke
if errorlevel 1 (
    echo ERROR: Import check failed. Fix the errors above before building.
    pause
    exit /b 1
)
echo   OK: pre-build import check passed.

echo.
:: --------------------------------------------------------------------------
:: Clean dist and build directories for a guaranteed fresh output
:: --------------------------------------------------------------------------
echo [2b/5] Cleaning previous build output...
taskkill /F /IM NetSentinel.exe >nul 2>&1
timeout /t 1 /nobreak >nul
if exist dist\NetSentinel        rmdir /s /q dist\NetSentinel
if exist dist\NetSentinel.exe    del /f /q dist\NetSentinel.exe
if exist dist\NetSentinel-cli.exe del /f /q dist\NetSentinel-cli.exe
if exist dist\NetSentinel-svc.exe del /f /q dist\NetSentinel-svc.exe
if exist build\NetSentinel       rmdir /s /q build\NetSentinel
if exist build\NetSentinelCLI    rmdir /s /q build\NetSentinelCLI
if exist build\NetSentinelSvc    rmdir /s /q build\NetSentinelSvc

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
    %PYTHON% -m PyInstaller --clean -y NetSentinel.spec
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
    %PYTHON% -m PyInstaller --clean -y NetSentinelCLI.spec
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
    %PYTHON% -m PyInstaller --clean -y NetSentinelSvc.spec
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
    echo   OK: post-build smoke test passed.
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
