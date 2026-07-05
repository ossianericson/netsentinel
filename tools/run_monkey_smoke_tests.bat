@echo off
setlocal enabledelayedexpansion
REM tools\run_monkey_smoke_tests.bat
REM =================================
REM Quick smoke pass for all three monkey-test tools - NOT a full chaos run.
REM Runs each tool for a short duration (default 60s, mild chaos) against
REM the app launched from source, one after another, and reports exit codes.
REM Use this to confirm the tooling itself still works (launches, clicks,
REM navigates, exits cleanly) - not to find deep bugs. For that, run each
REM tool directly with a longer --duration (see each script's --help).
REM
REM Usage:
REM   tools\run_monkey_smoke_tests.bat [duration_seconds] [chaos_level]
REM   tools\run_monkey_smoke_tests.bat 90 moderate
REM
REM Logs are written under test_output\smoke_<tool>\ so each tool's run
REM does not overwrite another's monkey.log.

cd /d "%~dp0.."

set DURATION=%1
if "%DURATION%"=="" set DURATION=60
set CHAOS=%2
if "%CHAOS%"=="" set CHAOS=mild

echo ============================================================
echo NetSentinel monkey-test smoke pass
echo duration=%DURATION%s per tool   chaos=%CHAOS%
echo ============================================================

echo.
echo [1/3] monkey_test.py  (UIA control clicking)...
python tools\monkey_test.py --source --duration %DURATION% --chaos %CHAOS% --output-dir "test_output\smoke_monkey_test"
set RC1=%ERRORLEVEL%
echo     exit code: %RC1%

echo.
echo [2/3] monkey_mouse_test.py  (raw mouse: points/drags/scroll/header sort+resize)...
python tools\monkey_mouse_test.py --source --duration %DURATION% --chaos %CHAOS% --output-dir "test_output\smoke_monkey_mouse_test"
set RC2=%ERRORLEVEL%
echo     exit code: %RC2%

echo.
echo [3/3] scan_navigate_test.py  (start a real scan, navigate away, check for damage)...
python tools\scan_navigate_test.py --source --duration %DURATION% --output-dir "test_output\smoke_scan_navigate_test"
set RC3=%ERRORLEVEL%
echo     exit code: %RC3%

echo.
echo ============================================================
echo SUMMARY
echo   monkey_test.py          exit=%RC1%   log: test_output\smoke_monkey_test\monkey.log
echo   monkey_mouse_test.py    exit=%RC2%   log: test_output\smoke_monkey_mouse_test\monkey.log
echo   scan_navigate_test.py   exit=%RC3%   log: test_output\smoke_scan_navigate_test\monkey.log
echo ============================================================

set OVERALL=0
if not "%RC1%"=="0" set OVERALL=1
if not "%RC2%"=="0" set OVERALL=1
if not "%RC3%"=="0" set OVERALL=1

if "%OVERALL%"=="0" (
    echo ALL THREE PASSED
) else (
    echo ONE OR MORE TOOLS FAILED - check the logs above
)

echo.
pause
exit /b %OVERALL%
