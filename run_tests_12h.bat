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

echo.
echo ════════════════════════════════════════
echo  NetSentinel 12-hour test suite
echo  Output: %OUT%
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
echo  Results in: %OUT%
echo ════════════════════════════════════════
pause
