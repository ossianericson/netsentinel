@echo off
setlocal

:: ─── 12-hour chaos suite ─────────────────────────────────────────────────────
:: mild 1500  ≈ 87 min
:: moderate 4500  ≈ 225 min
:: wild 9000  ≈ 375 min
:: systematic ×2  ≈ 10 min
:: total  ≈ 11.6 h  (buffer ~25 min)
:: ─────────────────────────────────────────────────────────────────────────────

set STAMP=%date:~10,4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set STAMP=%STAMP: =0%
set OUT=test_output\12h_%STAMP%
set FULLOUT=c:\Code\netsentinel\%OUT%

echo.
echo ════════════════════════════════════════
echo  NetSentinel 12-hour test suite
echo  Output: %FULLOUT%
echo  Started: %date% %time%
echo ════════════════════════════════════════
echo.

echo [1/5] Systematic pre-run...
python tools\systematic_test.py --source --pause 0.4 --output-dir %OUT%\sys_pre
if errorlevel 1 echo WARNING: systematic pre-run reported errors

echo.
echo [2/5] Monkey mild  (1500 iter)...
python tools\monkey_test.py --source -n 1500 --chaos mild --seed 1 --mem-limit 1000 --output-dir %OUT%\monkey_mild
if errorlevel 1 echo WARNING: mild run reported errors

echo.
echo [3/5] Monkey moderate  (4500 iter)...
python tools\monkey_test.py --source -n 4500 --chaos moderate --seed 42 --mem-limit 1200 --output-dir %OUT%\monkey_moderate
if errorlevel 1 echo WARNING: moderate run reported errors

echo.
echo [4/5] Monkey wild  (9000 iter)...
python tools\monkey_test.py --source -n 9000 --chaos wild --seed 99 --mem-limit 1500 --output-dir %OUT%\monkey_wild
if errorlevel 1 echo WARNING: wild run reported errors

echo.
echo [5/5] Systematic post-run...
python tools\systematic_test.py --source --pause 0.4 --output-dir %OUT%\sys_post
if errorlevel 1 echo WARNING: systematic post-run reported errors

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
echo   - sys_pre\        -- systematic coverage run before chaos
echo   - monkey_mild\    -- 1500 iterations mild chaos   (seed 1)
echo   - monkey_moderate\ -- 4500 iterations moderate chaos  (seed 42)
echo   - monkey_wild\    -- 9000 iterations wild chaos   (seed 99)
echo   - sys_post\       -- systematic coverage run after chaos
echo.
echo Please inspect all output files (logs, screenshots, crash reports) in
echo those folders. For each folder: summarise what happened, list any crashes
echo or errors found, identify which pages or actions caused problems, and give
echo me a prioritised fix list. Focus on actionable bugs -- ignore pywinauto
echo focus warnings and QThreadStorage teardown warnings as those are known noise.
echo.
pause
