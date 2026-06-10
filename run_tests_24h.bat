@echo off
setlocal enabledelayedexpansion

:: ─── 24-hour chaos suite ─────────────────────────────────────────────────────
:: mild 3000  ≈ 175 min
:: moderate 9000  ≈ 450 min
:: wild 18000  ≈ 750 min
:: systematic ×2  ≈ 10 min
:: total  ≈ 23.2 h  (buffer ~50 min)
:: ─────────────────────────────────────────────────────────────────────────────

:: Locale-independent timestamp via PowerShell (avoids Swedish / EU date format issues)
for /f "tokens=*" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%T

set FULLOUT=%USERPROFILE%\Documents\NetSentinel\test_output\24h_%STAMP%
set OUT=%FULLOUT%

:: Create output directory now so the test can write to it even if a step exits early
mkdir "%OUT%" >nul 2>&1

:: ── Pre-flight: disable Quick Edit + suppress sleep ───────────────────────────
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\test_setup.ps1"

echo.
echo ════════════════════════════════════════
echo  NetSentinel 24-hour test suite
echo  Output: %FULLOUT%
echo  Started: %date% %time%
echo ════════════════════════════════════════
echo.

:: ─── Step 1/5 ─────────────────────────────────────────────────────────────────
echo [1/5] Systematic pre-run...
set STEP_START=%time%
python tools\systematic_test.py --source --pause 0.4 --output-dir "%OUT%\sys_pre"
if errorlevel 1 (
    echo WARNING: systematic pre-run reported errors  [started %STEP_START%  ended %time%]
) else (
    echo OK: systematic pre-run complete              [started %STEP_START%  ended %time%]
)

:: ─── Step 2/5 ─────────────────────────────────────────────────────────────────
echo.
echo [2/5] Monkey mild  (3000 iter)...
set STEP_START=%time%
python tools\monkey_test.py --source -n 3000 --chaos mild --seed 1 --mem-limit 1000 --output-dir "%OUT%\monkey_mild"
if errorlevel 1 (
    echo WARNING: mild run reported errors            [started %STEP_START%  ended %time%]
) else (
    echo OK: mild run complete                        [started %STEP_START%  ended %time%]
)

:: ─── Step 3/5 ─────────────────────────────────────────────────────────────────
echo.
echo [3/5] Monkey moderate  (9000 iter)...
set STEP_START=%time%
python tools\monkey_test.py --source -n 9000 --chaos moderate --seed 42 --mem-limit 1200 --output-dir "%OUT%\monkey_moderate"
if errorlevel 1 (
    echo WARNING: moderate run reported errors        [started %STEP_START%  ended %time%]
) else (
    echo OK: moderate run complete                    [started %STEP_START%  ended %time%]
)

:: ─── Step 4/5 ─────────────────────────────────────────────────────────────────
echo.
echo [4/5] Monkey wild  (18000 iter)...
set STEP_START=%time%
python tools\monkey_test.py --source -n 18000 --chaos wild --seed 99 --mem-limit 1500 --output-dir "%OUT%\monkey_wild"
if errorlevel 1 (
    echo WARNING: wild run reported errors            [started %STEP_START%  ended %time%]
) else (
    echo OK: wild run complete                        [started %STEP_START%  ended %time%]
)

:: ─── Step 5/5 ─────────────────────────────────────────────────────────────────
echo.
echo [5/5] Systematic post-run...
set STEP_START=%time%
python tools\systematic_test.py --source --pause 0.4 --output-dir "%OUT%\sys_post"
if errorlevel 1 (
    echo WARNING: systematic post-run reported errors [started %STEP_START%  ended %time%]
) else (
    echo OK: systematic post-run complete             [started %STEP_START%  ended %time%]
)

:: ── Restore system settings ───────────────────────────────────────────────────
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\test_setup.ps1" -Restore

echo.
echo ════════════════════════════════════════
echo  Done: %date% %time%
echo  Results in: %FULLOUT%
echo ════════════════════════════════════════
echo.
echo.
echo ┌──────────────────────────────────────────────────────────────────────────┐
echo │  PASTE THIS INTO A NEW CHAT TO ANALYSE RESULTS:                         │
echo └──────────────────────────────────────────────────────────────────────────┘
echo.
echo I ran overnight chaos and systematic tests on the NetSentinel app.
echo The output is in %FULLOUT%\ with these folders:
echo   - sys_pre\         -- systematic coverage run before chaos
echo   - monkey_mild\     -- 3000 iterations mild chaos   (seed 1)
echo   - monkey_moderate\ -- 9000 iterations moderate chaos  (seed 42)
echo   - monkey_wild\     -- 18000 iterations wild chaos   (seed 99)
echo   - sys_post\        -- systematic coverage run after chaos
echo.
echo Please inspect all output files (logs, screenshots, crash reports) in
echo those folders. For each folder: summarise what happened, list any crashes
echo or errors found, identify which pages or actions caused problems, and give
echo me a prioritised fix list. Focus on actionable bugs -- ignore pywinauto
echo focus warnings and QThreadStorage teardown warnings as those are known noise.
echo.
pause
