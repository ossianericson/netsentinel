# tools/test_setup.ps1
# Called by test.ps1 / tools/run_all_monkey_tests.ps1 at the start and end of every long test run.
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\test_setup.ps1          # setup
#   powershell -ExecutionPolicy Bypass -File tools\test_setup.ps1 -Restore # teardown
#
# What it does (setup mode):
#   1. Disables Quick Edit mode on the calling console window so an accidental
#      mouse click can never freeze the CMD session mid-run.
#   2. Calls SetThreadExecutionState (no admin rights required) so THIS process
#      — the one that lives for the entire run and launches every phase as a
#      child process — holds Windows awake continuously from before the first
#      phase starts to after the last one ends. This is the primary guard: it
#      has no gaps between phases, unlike relying on each short-lived Python
#      phase process to suppress sleep only while it itself is running.
#   3. Also attempts powercfg (AC plan) as a second, belt-and-suspenders layer.
#      Requires admin rights; silently skipped otherwise — harmless since step 2
#      already covers the whole run without it.
#   4. Prints a confirmation banner.
#
# What it does (restore mode):
#   1. Re-enables Quick Edit mode.
#   2. Clears the SetThreadExecutionState hold.
#   3. Restores default power timeouts (30 min sleep / 15 min display).

param([switch]$Restore)

# ── Quick Edit mode ────────────────────────────────────────────────────────────
# Quick Edit lets users select text by clicking in CMD — but it PAUSES execution
# the moment the window is clicked, silently freezing a 24-hour test.

$consoleHelper = @'
using System;
using System.Runtime.InteropServices;
public class ConsoleMode {
    [DllImport("kernel32.dll")] static extern bool GetConsoleMode(IntPtr h, out uint m);
    [DllImport("kernel32.dll")] static extern bool SetConsoleMode(IntPtr h, uint m);
    [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int n);
    const uint ENABLE_QUICK_EDIT  = 0x0040u;
    const uint ENABLE_INSERT_MODE = 0x0020u;
    public static void Disable() {
        IntPtr h = GetStdHandle(-10);
        uint m;
        GetConsoleMode(h, out m);
        SetConsoleMode(h, m & ~ENABLE_QUICK_EDIT & ~ENABLE_INSERT_MODE);
    }
    public static void Enable() {
        IntPtr h = GetStdHandle(-10);
        uint m;
        GetConsoleMode(h, out m);
        SetConsoleMode(h, m | ENABLE_QUICK_EDIT | ENABLE_INSERT_MODE);
    }
}
public class PowerState {
    [DllImport("kernel32.dll")] static extern uint SetThreadExecutionState(uint esFlags);
    const uint ES_CONTINUOUS       = 0x80000000;
    const uint ES_SYSTEM_REQUIRED  = 0x00000001;
    const uint ES_DISPLAY_REQUIRED = 0x00000002;
    // Holds for as long as THIS process is alive, even while it is blocked
    // waiting on a child process (e.g. Start-Process -Wait) — no need to
    // renew it. Covers every phase and every gap between phases in one call.
    public static void Suppress() {
        SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED);
    }
    public static void Restore() {
        SetThreadExecutionState(ES_CONTINUOUS);
    }
}
'@

try {
    Add-Type -TypeDefinition $consoleHelper -ErrorAction Stop
} catch {
    # Already loaded in this session — ignore duplicate-type error
}

# ── Power management ───────────────────────────────────────────────────────────

function Set-SleepTimeouts([int]$SleepMin, [int]$DisplayMin) {
    try {
        powercfg /change standby-timeout-ac  $SleepMin   2>$null
        powercfg /change monitor-timeout-ac  $DisplayMin 2>$null
        return $true
    } catch {
        return $false
    }
}

# ── Main ───────────────────────────────────────────────────────────────────────

if ($Restore) {
    try { [ConsoleMode]::Enable()  } catch {}
    try { [PowerState]::Restore() } catch {}
    $ok = Set-SleepTimeouts -SleepMin 30 -DisplayMin 15
    Write-Host ""
    Write-Host "  [teardown] Quick Edit re-enabled." -ForegroundColor Gray
    Write-Host "  [teardown] SetThreadExecutionState hold released." -ForegroundColor Gray
    if ($ok) {
        Write-Host "  [teardown] Sleep timeouts restored (30 min sleep / 15 min display)." -ForegroundColor Gray
    }
    Write-Host ""
} else {
    try { [ConsoleMode]::Disable() } catch {}
    $stateOk = $true
    try { [PowerState]::Suppress() } catch { $stateOk = $false }
    $ok = Set-SleepTimeouts -SleepMin 0 -DisplayMin 0

    Write-Host ""
    Write-Host "  +----------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host "  |  NetSentinel test-run pre-flight                         |" -ForegroundColor Cyan
    Write-Host "  +----------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host "  |  Quick Edit mode : DISABLED (click won't freeze console) |" -ForegroundColor Cyan
    if ($stateOk) {
        Write-Host "  |  Sleep / display : SUPPRESSED (SetThreadExecutionState)  |" -ForegroundColor Cyan
    } else {
        Write-Host "  |  Sleep / display : SetThreadExecutionState call failed!  |" -ForegroundColor Red
    }
    if ($ok) {
        Write-Host "  |  powercfg AC plan: also zeroed (belt-and-suspenders)      |" -ForegroundColor Cyan
    } else {
        Write-Host "  |  powercfg AC plan: skipped (no admin rights - not needed) |" -ForegroundColor Yellow
    }
    Write-Host "  +----------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host ""

    Write-Host "  TIP: For best results, also:" -ForegroundColor Yellow
    Write-Host "    - Enable Windows Focus Assist / Do Not Disturb" -ForegroundColor Yellow
    Write-Host "    - Close Outlook, Teams, and other notification apps" -ForegroundColor Yellow
    Write-Host "    - Disconnect external monitors that could trigger DPI changes" -ForegroundColor Yellow
    Write-Host ""
}
