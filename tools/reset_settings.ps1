# reset_settings.ps1 - Wipe all NetSentinel user state for clean new-user testing
#
# What this removes:
#   1. QSettings registry hive  (HKCU:\Software\NetSentinel)
#   2. App data directory       (%LOCALAPPDATA%\NetSentinel\)  - DB, logs, cache
#   3. Windows Credential Manager entries matching "NetSentinel*"  (keyring secrets)
#   4. NetSentinel.ini (legacy, if present next to the repo root)
#
# Usage:
#   cd c:\Code\netsentinel\tools
#   powershell -ExecutionPolicy Bypass -File reset_settings.ps1
#
# The app will behave as a brand-new install on next launch.

$ErrorActionPreference = "Continue"
$changed = $false

Write-Host ""
Write-Host "NetSentinel - Settings Reset" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host ""

# 1. QSettings (registry)
$regPath = "HKCU:\Software\NetSentinel"
if (Test-Path $regPath) {
    Remove-Item $regPath -Recurse -Force -Confirm:$false
    Write-Host "[OK] Removed QSettings registry hive: $regPath" -ForegroundColor Green
    $changed = $true
} else {
    Write-Host "[--] QSettings hive not found (already clean)" -ForegroundColor DarkGray
}

# 2. App data directory
$appData = "$env:LOCALAPPDATA\NetSentinel"
if (Test-Path $appData) {
    Remove-Item $appData -Recurse -Force -Confirm:$false
    Write-Host "[OK] Removed app data directory: $appData" -ForegroundColor Green
    $changed = $true
} else {
    Write-Host "[--] App data directory not found: $appData" -ForegroundColor DarkGray
}

# 3. Windows Credential Manager (keyring secrets)
# keyring stores secrets as Generic credentials with target = "NetSentinel*"
$credOutput = cmdkey /list 2>$null
$targets = @()
foreach ($line in $credOutput) {
    if ($line -match "Target:\s+(.+)") {
        $target = $Matches[1].Trim()
        if ($target -like "NetSentinel*" -or $target -like "LegacyGeneric:target=NetSentinel*") {
            $targets += $target
        }
    }
}

if ($targets.Count -gt 0) {
    foreach ($t in $targets) {
        cmdkey /delete:$t 2>$null | Out-Null
        Write-Host "[OK] Removed credential: $t" -ForegroundColor Green
    }
    $changed = $true
} else {
    Write-Host "[--] No NetSentinel keyring credentials found" -ForegroundColor DarkGray
}

# 4. NetSentinel.ini (legacy, if present next to the repo root)
$iniPath = Join-Path (Split-Path $PSScriptRoot -Parent) "NetSentinel.ini"
if (Test-Path $iniPath) {
    Remove-Item $iniPath -Force -Confirm:$false
    Write-Host "[OK] Removed: $iniPath" -ForegroundColor Green
    $changed = $true
} else {
    Write-Host "[--] NetSentinel.ini not found" -ForegroundColor DarkGray
}

# Summary
Write-Host ""
if ($changed) {
    Write-Host "Done. NetSentinel will start as a new user on next launch." -ForegroundColor Cyan
} else {
    Write-Host "Nothing to reset - already a clean state." -ForegroundColor Yellow
}
Write-Host ""
