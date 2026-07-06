@echo off
setlocal enabledelayedexpansion
REM tools\run_scan_navigate_test.bat
REM =================================
REM Validate scan_navigate_test.py IN ISOLATION (not the 60s smoke-pass slice
REM inside run_monkey_smoke_tests.bat). scan_navigate_test.py is the only
REM tester that deliberately starts a real background scan worker and then
REM navigates away before it finishes - the bug class it hunts (a
REM result_ready slot firing against a torn-down/hidden page, a stale
REM _nav_set_scan_state racing a page switch) needs many iterations across
REM all 8 whitelisted scan targets to surface, not a quick smoke check.
REM
REM Usage:
REM   tools\run_scan_navigate_test.bat [duration_seconds] [chaos_level]
REM   tools\run_scan_navigate_test.bat 900 wild
REM Defaults: 600 seconds, moderate chaos.

cd /d "%~dp0.."

set DURATION=%1
if "%DURATION%"=="" set DURATION=600
set CHAOS=%2
if "%CHAOS%"=="" set CHAOS=moderate

REM Locale-independent timestamp (avoids EU/Swedish date-format issues)
for /f "tokens=*" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%T
set OUT=%USERPROFILE%\Documents\NetSentinel\test_output\scannav_%STAMP%
mkdir "%OUT%" >nul 2>&1

REM ── Venv activation (ensures correct Python on fresh boot) ─────────────────
if exist "%~dp0..\.venv\Scripts\activate.bat" (
    call "%~dp0..\.venv\Scripts\activate.bat"
    echo [setup] Activated .venv
) else if exist "%~dp0..\venv\Scripts\activate.bat" (
    call "%~dp0..\venv\Scripts\activate.bat"
    echo [setup] Activated venv
) else (
    echo [setup] No venv found - using system Python
)

REM ── Pre-flight: disable Quick Edit + suppress sleep ────────────────────────
if exist "%~dp0test_setup.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_setup.ps1"
)

echo.
echo ============================================================
echo  NetSentinel scan_navigate_test.py STAGE-ONE validation
echo  duration=%DURATION%s   chaos=%CHAOS%
echo  Output: %OUT%
echo  Started: %date% %time%
echo ============================================================

echo.
echo [1/2] scan_navigate_test.py  (real scan-trigger + navigate-away churn)...
python "%~dp0scan_navigate_test.py" --source --duration %DURATION% --chaos %CHAOS% ^
    --focus-interval 1.5 --output-dir "%OUT%\scannav"
set RC1=%ERRORLEVEL%
echo     exit code: %RC1%

echo.
echo [2/2] systematic_test.py  (post-check: confirm all pages still functional)...
python "%~dp0systematic_test.py" --source --pause 0.4 --focus-interval 1.5 ^
    --output-dir "%OUT%\sys_post"
set RC2=%ERRORLEVEL%
echo     exit code: %RC2%

REM ── Restore system settings ────────────────────────────────────────────────
if exist "%~dp0test_setup.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_setup.ps1" -Restore
)

echo.
echo ============================================================
echo SUMMARY
echo   scan_navigate_test.py   exit=%RC1%   log: %OUT%\scannav\monkey.log
echo   systematic_test.py      exit=%RC2%   log: %OUT%\sys_post\
echo ============================================================

set OVERALL=0
if not "%RC1%"=="0" set OVERALL=1
if not "%RC2%"=="0" set OVERALL=1
if "%OVERALL%"=="0" ( echo SCAN-NAVIGATE TESTER PASSED ) else ( echo SCAN-NAVIGATE TESTER FAILED - check the logs above )

echo.
echo ----------------------------------------------------------------------------
echo  PASTE THIS INTO A NEW CHAT TO ANALYSE RESULTS:
echo ----------------------------------------------------------------------------
echo.
echo I ran the NetSentinel scan-navigate tester (scan_navigate_test.py) in isolation.
echo Output is in %OUT%\ with:
echo   - scannav\    -- the scan-trigger + navigate-away run (monkey.log,
echo                    monkey_summary.json, any *_crash*.txt / screenshot PNGs)
echo   - sys_post\   -- systematic sweep AFTER the run, confirming every page
echo                    still opens and is functional
echo.
echo Please inspect the logs/crash reports/screenshots: summarise what happened,
echo list every crash, exception, or stray error dialog with the scan target and
echo away-page that triggered it, and give me a prioritised fix list. Ignore
echo pywinauto focus warnings and QThreadStorage teardown noise.
echo.
pause
exit /b %OVERALL%
