@echo off
setlocal enabledelayedexpansion
REM tools\run_mouse_test.bat
REM =========================
REM STAGE ONE: validate the raw-mouse (SendInput) chaos tester IN ISOLATION.
REM
REM monkey_mouse_test.py is the only tester that clicks by real screen
REM coordinate (every other tester invokes controls by UIA identity and cannot
REM click outside the app). That makes it the one tool that can click off the
REM app window - so it gets validated on its own here, separate from the
REM overnight bracket, until it runs clean.
REM
REM Off-window clicks are now prevented three ways (see monkey_mouse_test.py):
REM   1. window maximised at startup (fills the work area)
REM   2. per-action _point_ok guard: re-checks foreground + live window rect
REM      immediately before EVERY SendInput
REM   3. zone-scan filtering: controls/headers outside the window are dropped
REM Watch off_window_skips in monkey_summary.json - it should stay low. A high
REM count means focus was being stolen repeatedly (the guard did its job, but
REM close whatever kept stealing focus for a cleaner run).
REM
REM Usage:
REM   tools\run_mouse_test.bat [duration_seconds] [chaos_level]
REM   tools\run_mouse_test.bat 600 wild
REM Defaults: 300 seconds, moderate chaos.

cd /d "%~dp0.."

set DURATION=%1
if "%DURATION%"=="" set DURATION=300
set CHAOS=%2
if "%CHAOS%"=="" set CHAOS=moderate

REM Locale-independent timestamp (avoids EU/Swedish date-format issues)
for /f "tokens=*" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%T
set OUT=%USERPROFILE%\Documents\NetSentinel\test_output\mouse_%STAMP%
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
echo  NetSentinel mouse-tester STAGE-ONE validation
echo  duration=%DURATION%s   chaos=%CHAOS%
echo  Output: %OUT%
echo  Started: %date% %time%
echo ============================================================

echo.
echo [1/2] monkey_mouse_test.py  (raw mouse: control centres + header + chaos)...
python "%~dp0monkey_mouse_test.py" --source --duration %DURATION% --chaos %CHAOS% ^
    --focus-interval 1.5 --output-dir "%OUT%\mouse"
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
echo   monkey_mouse_test.py   exit=%RC1%   log: %OUT%\mouse\monkey.log
echo   systematic_test.py     exit=%RC2%   log: %OUT%\sys_post\
echo ============================================================

set OVERALL=0
if not "%RC1%"=="0" set OVERALL=1
if not "%RC2%"=="0" set OVERALL=1
if "%OVERALL%"=="0" ( echo MOUSE TESTER PASSED ) else ( echo MOUSE TESTER FAILED - check the logs above )

echo.
echo ----------------------------------------------------------------------------
echo  PASTE THIS INTO A NEW CHAT TO ANALYSE RESULTS:
echo ----------------------------------------------------------------------------
echo.
echo I ran the NetSentinel mouse tester (monkey_mouse_test.py) in isolation.
echo Output is in %OUT%\ with:
echo   - mouse\      -- the raw-mouse chaos run (monkey.log, monkey_summary.json,
echo                    any *_crash*.txt / screenshot PNGs)
echo   - sys_post\   -- systematic sweep AFTER the chaos run, confirming every
echo                    page still opens and is functional
echo.
echo Please inspect the logs/crash reports/screenshots: summarise what happened,
echo list every crash or exception with the page/action that triggered it, report
echo the off_window_skips count from monkey_summary.json, and give me a prioritised
echo fix list. Ignore pywinauto focus warnings and QThreadStorage teardown noise.
echo.
pause
exit /b %OVERALL%
