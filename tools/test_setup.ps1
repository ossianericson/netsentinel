# tools/test_setup.ps1
# Called by run_tests_*.bat at the start and end of every long test run.
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\test_setup.ps1          # setup
#   powershell -ExecutionPolicy Bypass -File tools\test_setup.ps1 -Restore # teardown
#
# What it does (setup mode):
#   1. Disables Quick Edit mode on the calling console window so an accidental
#      mouse click can never freeze the CMD session mid-run.
#   2. Attempts to suppress Windows sleep/screensaver via powercfg (AC plan).
#      Silently ignored if the current user lacks admin rights — the Python test
#      processes call SetThreadExecutionState themselves as a backup.
#   3. Prints a confirmation banner.
#
# What it does (restore mode):
#   1. Re-enables Quick Edit mode.
#   2. Restores default power timeouts (30 min sleep / 15 min display).

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
    $ok = Set-SleepTimeouts -SleepMin 30 -DisplayMin 15
    Write-Host ""
    Write-Host "  [teardown] Quick Edit re-enabled." -ForegroundColor Gray
    if ($ok) {
        Write-Host "  [teardown] Sleep timeouts restored (30 min sleep / 15 min display)." -ForegroundColor Gray
    }
    Write-Host ""
} else {
    try { [ConsoleMode]::Disable() } catch {}
    $ok = Set-SleepTimeouts -SleepMin 0 -DisplayMin 0

    Write-Host ""
    Write-Host "  +----------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host "  |  NetSentinel test-run pre-flight                         |" -ForegroundColor Cyan
    Write-Host "  +----------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host "  |  Quick Edit mode : DISABLED (click won't freeze console) |" -ForegroundColor Cyan
    if ($ok) {
        Write-Host "  |  Sleep / display : SUPPRESSED (powercfg AC timeouts = 0) |" -ForegroundColor Cyan
    } else {
        Write-Host "  |  Sleep / display : powercfg skipped (Python will handle)  |" -ForegroundColor Yellow
    }
    Write-Host "  |  Python processes: will call SetThreadExecutionState      |" -ForegroundColor Cyan
    Write-Host "  +----------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host ""

    Write-Host "  TIP: For best results, also:" -ForegroundColor Yellow
    Write-Host "    - Enable Windows Focus Assist / Do Not Disturb" -ForegroundColor Yellow
    Write-Host "    - Close Outlook, Teams, and other notification apps" -ForegroundColor Yellow
    Write-Host "    - Disconnect external monitors that could trigger DPI changes" -ForegroundColor Yellow
    Write-Host ""
}
