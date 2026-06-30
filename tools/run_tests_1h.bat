@echo off
setlocal enabledelayedexpansion

:: ─── 1-hour chaos suite ──────────────────────────────────────────────────────
:: systematic pre     ~5 min   (62 pages x ~5 controls x 0.4 s)
:: mild    150 iter   ~9 min   (150 x 3.5 s avg)
:: moderate 350 iter  ~18 min  (350 x 3.0 s avg)
:: wild    250 iter   ~10 min  (250 x 2.5 s avg)
:: systematic post    ~5 min
:: total              ~47 min  (buffer ~13 min)
::
:: Focus-lock improvements vs overnight suites:
::   --focus-interval 1.5  (heartbeat every 1.5 s instead of 5 s)
::   _assert_focus() verifies foreground before EVERY click (monkey_test v1.3.0)
::   Screenshots saved when focus is stolen (up to 5 per run)
:: ─────────────────────────────────────────────────────────────────────────────

:: Locale-independent timestamp via PowerShell (avoids Swedish / EU date format issues)
for /f "tokens=*" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%T

set FULLOUT=%USERPROFILE%\Documents\NetSentinel\test_output\1h_%STAMP%
set OUT=%FULLOUT%

:: Create output directory so steps can write even if an earlier step exits early
mkdir "%OUT%" >nul 2>&1

:: ── Venv activation (ensures correct Python on fresh boot) ─────────────────
set "REPO=%~dp0.."
if exist "%REPO%\.venv\Scripts\activate.bat" (
    call "%REPO%\.venv\Scripts\activate.bat"
    echo [setup] Activated .venv
) else if exist "%REPO%\venv\Scripts\activate.bat" (
    call "%REPO%\venv\Scripts\activate.bat"
    echo [setup] Activated venv
) else (
    echo [setup] No venv found - using system Python
)

:: ── Pre-flight: disable Quick Edit mode + suppress sleep ───────────────────────
:: test_setup.ps1 is optional (may not exist in all checkouts)
if exist "%~dp0test_setup.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_setup.ps1"
)

echo.
echo ════════════════════════════════════════
echo  NetSentinel 1-hour chaos suite
echo  Output: %FULLOUT%
echo  Started: %date% %time%
echo ════════════════════════════════════════
echo.

:: ─── Step 1/5 — Systematic pre-run ────────────────────────────────────────────
echo [1/5] Systematic pre-run...
set STEP_START=%time%
python "%~dp0systematic_test.py" --source --pause 0.4 --output-dir "%OUT%\sys_pre" --focus-interval 1.5
if errorlevel 1 (
    echo WARNING: systematic pre-run reported errors  [started %STEP_START%  ended %time%]
) else (
    echo OK: systematic pre-run complete              [started %STEP_START%  ended %time%]
)

:: ─── Step 2/5 — Mild chaos ─────────────────────────────────────────────────────
echo.
echo [2/5] Monkey mild  (150 iter)...
set STEP_START=%time%
python "%~dp0monkey_test.py" --source -n 150 --chaos mild --seed 1 --mem-limit 1000 ^
    --focus-interval 1.5 --output-dir "%OUT%\monkey_mild"
if errorlevel 1 (
    echo WARNING: mild run reported errors            [started %STEP_START%  ended %time%]
) else (
    echo OK: mild run complete                        [started %STEP_START%  ended %time%]
)

:: ─── Step 3/5 — Moderate chaos ─────────────────────────────────────────────────
echo.
echo [3/5] Monkey moderate  (350 iter)...
set STEP_START=%time%
python "%~dp0monkey_test.py" --source -n 350 --chaos moderate --seed 42 --mem-limit 1200 ^
    --focus-interval 1.5 --output-dir "%OUT%\monkey_moderate"
if errorlevel 1 (
    echo WARNING: moderate run reported errors        [started %STEP_START%  ended %time%]
) else (
    echo OK: moderate run complete                    [started %STEP_START%  ended %time%]
)

:: ─── Step 4/5 — Wild chaos ─────────────────────────────────────────────────────
echo.
echo [4/5] Monkey wild  (250 iter)...
set STEP_START=%time%
python "%~dp0monkey_test.py" --source -n 250 --chaos wild --seed 99 --mem-limit 1500 ^
    --focus-interval 1.5 --output-dir "%OUT%\monkey_wild"
if errorlevel 1 (
    echo WARNING: wild run reported errors            [started %STEP_START%  ended %time%]
) else (
    echo OK: wild run complete                        [started %STEP_START%  ended %time%]
)

:: ─── Step 5/5 — Systematic post-run ────────────────────────────────────────────
echo.
echo [5/5] Systematic post-run...
set STEP_START=%time%
python "%~dp0systematic_test.py" --source --pause 0.4 --output-dir "%OUT%\sys_post" --focus-interval 1.5
if errorlevel 1 (
    echo WARNING: systematic post-run reported errors [started %STEP_START%  ended %time%]
) else (
    echo OK: systematic post-run complete             [started %STEP_START%  ended %time%]
)

:: ── Restore system settings ────────────────────────────────────────────────────
if exist "%~dp0test_setup.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_setup.ps1" -Restore
)

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
echo I ran a 1-hour chaos and systematic test on the NetSentinel app.
echo The output is in %FULLOUT%\ with these folders:
echo   - sys_pre\         -- systematic coverage run before chaos
echo   - monkey_mild\     -- 150 iterations mild chaos    (seed 1)
echo   - monkey_moderate\ -- 350 iterations moderate chaos (seed 42)
echo   - monkey_wild\     -- 250 iterations wild chaos    (seed 99)
echo   - sys_post\        -- systematic coverage run after chaos
echo.
echo Each monkey run used --focus-interval 1.5 and per-click _assert_focus()
echo checks (monkey_test.py v1.3.0). Look for focus_stolen_count in the
echo monkey_summary.json files to see how many times another window stole focus.
echo Screenshots named focus_stolen_NN.png capture what window was in the way.
echo.
echo Please inspect all output files (logs, screenshots, crash reports) in
echo those folders. For each folder: summarise what happened, list any crashes
echo or errors found, identify which pages or actions caused problems, and give
echo me a prioritised fix list. Focus on actionable bugs -- ignore pywinauto
echo focus warnings and QThreadStorage teardown warnings as those are known noise.
echo.
pause
