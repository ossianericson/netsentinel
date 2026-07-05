<#
.SYNOPSIS
    Run NetSentinel's chaos/monkey testers back-to-back for a given time.

.DESCRIPTION
    One command, one time argument. Two modes:

    DEFAULT (quick pass) - launches the app from source and runs, in order:
        1. monkey_test.py        - UIA control clicking (invokes controls via accessibility API)
        2. monkey_mouse_test.py  - real mouse: clicks real control centres + header sort/resize + chaos
        3. scan_navigate_test.py - start a real scan, navigate away before it finishes, check for damage

    -Nightly (full overnight suite) - the bracketed, multi-tier run for finding
    deep bugs. Everything the run_tests_*.bat overnight suites do, PLUS the two
    newer testers they never ran:
        1. systematic_test.py    - coverage sweep of every page (pre)
        2. monkey_test.py        - mild chaos   (seed 1)
        3. monkey_test.py        - moderate     (seed 42)
        4. monkey_test.py        - wild         (seed 99)
        5. monkey_mouse_test.py  - wild real-mouse (seed 99)   [NEW coverage]
        6. scan_navigate_test.py - scan/navigate-away churn     [NEW coverage]
        7. systematic_test.py    - coverage sweep of every page (post)

    Each phase gets its own app launch and its own log dir. At the end the
    script prints an aggregated summary (exit code + crashes + exceptions per
    phase) and, in -Nightly mode, a paste-ready block: run this on your PC,
    paste the summary into a fresh chat, and the crashes/exceptions get triaged
    into a prioritized fix list. Full logs + screenshots stay on disk.

    DurationSeconds is PER duration-based phase (the monkey/mouse/scan phases).
    systematic_test.py is pause-based and ignores it.

.PARAMETER DurationSeconds
    Seconds to run each duration-based phase. Positional: .\run_all_monkey_tests.ps1 300

.PARAMETER Chaos
    Chaos level for the DEFAULT (quick) mode: mild | moderate | wild. Default moderate.
    Ignored by -Nightly, which sweeps all three tiers itself.

.PARAMETER Seed
    Optional RNG seed for the DEFAULT mode. 0 (default) means no fixed seed.
    Ignored by -Nightly, which uses fixed seeds 1/42/99 per tier.

.PARAMETER Nightly
    Run the full bracketed overnight suite instead of the quick 3-tool pass.

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1 300
    Quick pass: each of the three testers for 5 minutes at moderate chaos.

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1 3600 -Nightly
    Overnight suite: each duration-based phase runs 1 hour (~5h + 2 coverage
    sweeps total). Paste the final summary into a chat for a fix list.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [int]$DurationSeconds = 120,

    [Parameter(Position = 1)]
    [ValidateSet("mild", "moderate", "wild")]
    [string]$Chaos = "moderate",

    [Parameter(Position = 2)]
    [int]$Seed = 0,

    [switch]$Nightly
)

# Repo root is the parent of tools\ (this script's dir).
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# Activate a local virtualenv if one exists, so the right Python/deps are used
# on a fresh shell (mirrors the old run_tests_*.bat behaviour).
$venvActivate = $null
foreach ($cand in @(".venv\Scripts\Activate.ps1", "venv\Scripts\Activate.ps1")) {
    if (Test-Path (Join-Path $repoRoot $cand)) { $venvActivate = Join-Path $repoRoot $cand; break }
}
if ($venvActivate) {
    & $venvActivate
    Write-Host "[setup] Activated venv: $venvActivate" -ForegroundColor Gray
} else {
    Write-Host "[setup] No venv found - using system Python" -ForegroundColor Gray
}

# Pre-flight: disable console Quick Edit (a stray click won't freeze the run)
# and suppress sleep/screensaver. Restored in the finally block at the end.
$setupScript = Join-Path $PSScriptRoot "test_setup.ps1"
if (Test-Path $setupScript) { & $setupScript }

# ── Build the phase list for the selected mode ──────────────────────────────
# Each phase: Name, Script, Args (WITHOUT --output-dir; the loop appends it),
# OutSub (its subfolder), Desc, and DurationBased (whether it emits a summary).

$seedArgs = @()
if ($Seed -ne 0) { $seedArgs = @("--seed", "$Seed") }
$d = "$DurationSeconds"

if ($Nightly) {
    # Persistent, timestamped root outside the repo so big overnight artifacts
    # (screenshots, crash dumps) don't clutter the working tree.
    $stamp   = Get-Date -Format "yyyyMMdd_HHmmss"
    $outRoot = Join-Path $env:USERPROFILE ("Documents\NetSentinel\test_output\nightly_" + $stamp)
    $sysArgs = @("--source", "--pause", "0.4", "--focus-interval", "1.5")
    $phases = @(
        @{ Name = "systematic_test.py (pre)";  Script = "tools\systematic_test.py";    Args = $sysArgs; OutSub = "sys_pre";       Desc = "coverage sweep of every page";      DurationBased = $false },
        @{ Name = "monkey_test.py mild";        Script = "tools\monkey_test.py";        Args = @("--source","--duration",$d,"--chaos","mild","--seed","1","--mem-limit","1000","--focus-interval","1.5");     OutSub = "monkey_mild";     Desc = "UIA control clicking, mild";       DurationBased = $true },
        @{ Name = "monkey_test.py moderate";    Script = "tools\monkey_test.py";        Args = @("--source","--duration",$d,"--chaos","moderate","--seed","42","--mem-limit","1200","--focus-interval","1.5"); OutSub = "monkey_moderate"; Desc = "UIA control clicking, moderate";   DurationBased = $true },
        @{ Name = "monkey_test.py wild";        Script = "tools\monkey_test.py";        Args = @("--source","--duration",$d,"--chaos","wild","--seed","99","--mem-limit","1500","--focus-interval","1.5");     OutSub = "monkey_wild";     Desc = "UIA control clicking, wild";       DurationBased = $true },
        @{ Name = "monkey_mouse_test.py wild";  Script = "tools\monkey_mouse_test.py";  Args = @("--source","--duration",$d,"--chaos","wild","--seed","99","--mem-limit","1500","--focus-interval","1.5");     OutSub = "mouse_wild";      Desc = "real mouse: control centres + chaos"; DurationBased = $true },
        @{ Name = "scan_navigate_test.py";      Script = "tools\scan_navigate_test.py"; Args = @("--source","--duration",$d,"--focus-interval","1.5");                                                              OutSub = "scan_navigate";   Desc = "scan, navigate away, check damage"; DurationBased = $true },
        @{ Name = "systematic_test.py (post)"; Script = "tools\systematic_test.py";    Args = $sysArgs; OutSub = "sys_post";      Desc = "coverage sweep of every page";      DurationBased = $false }
    )
    $durationPhases = @($phases | Where-Object { $_.DurationBased }).Count
    $estTotal = ($DurationSeconds * $durationPhases) + (600) + (15 * $phases.Count)
    $modeLabel = "NIGHTLY (full bracketed suite)"
} else {
    $outRoot = Join-Path $repoRoot "test_output"
    $commonArgs = @("--source", "--duration", $d, "--chaos", $Chaos) + $seedArgs
    $phases = @(
        @{ Name = "monkey_test.py";        Script = "tools\monkey_test.py";        Args = $commonArgs; OutSub = "run_monkey_test";        Desc = "UIA control clicking";                        DurationBased = $true },
        @{ Name = "monkey_mouse_test.py";  Script = "tools\monkey_mouse_test.py";  Args = $commonArgs; OutSub = "run_monkey_mouse_test";  Desc = "real mouse: control centres + header + chaos"; DurationBased = $true },
        @{ Name = "scan_navigate_test.py"; Script = "tools\scan_navigate_test.py"; Args = $commonArgs; OutSub = "run_scan_navigate_test"; Desc = "scan, navigate away, check for damage";        DurationBased = $true }
    )
    $estTotal = ($DurationSeconds * $phases.Count) + (15 * $phases.Count)
    $modeLabel = "QUICK (3-tool pass)"
}

$seedLabel = if ($Seed -ne 0) { "$Seed" } else { "none" }
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "NetSentinel - run monkey/chaos testers" -ForegroundColor Cyan
Write-Host ("  mode     : {0}" -f $modeLabel)
Write-Host ("  duration : {0}s per duration-phase   chaos: {1}   seed: {2}" -f $DurationSeconds, $(if ($Nightly) { "mild/moderate/wild" } else { $Chaos }), $(if ($Nightly) { "1/42/99" } else { $seedLabel }))
Write-Host ("  phases   : {0}   estimated total: ~{1}s (~{2} min)" -f $phases.Count, $estTotal, [math]::Round($estTotal / 60, 1))
Write-Host ("  output   : {0}" -f $outRoot)
Write-Host "============================================================" -ForegroundColor Cyan

$results = @()
try {
    $i = 0
    foreach ($phase in $phases) {
        $i++
        Write-Host ""
        Write-Host ("[{0}/{1}] {2}  ({3})..." -f $i, $phases.Count, $phase.Name, $phase.Desc) -ForegroundColor Yellow

        $outDir   = Join-Path $outRoot $phase.OutSub
        $phaseArgs = $phase.Args + @("--output-dir", $outDir)
        # Call the native python exe with the assembled argument array. Do NOT
        # redirect stderr (2>&1) - in Windows PowerShell that wraps native
        # stderr lines as error records and falsely flips $? even on exit 0.
        & python $phase.Script @phaseArgs
        $rc = $LASTEXITCODE
        Write-Host ("    exit code: {0}" -f $rc)

        # Pull crash/exception counts from the tester's summary JSON when present
        # (systematic_test.py has no summary - it reports via its own log).
        $crashes = "-"; $exc = "-"; $iters = "-"
        $summaryPath = Join-Path $outDir "monkey_summary.json"
        if (Test-Path $summaryPath) {
            try {
                $s = Get-Content $summaryPath -Raw | ConvertFrom-Json
                $crashes = $s.crashes
                $exc     = $s.exceptions_caught
                $iters   = $s.iterations_completed
            } catch {
                # malformed/partial JSON - leave placeholders
            }
        }

        $results += [pscustomobject]@{
            Phase      = $phase.Name
            ExitCode   = $rc
            Status     = $(if ($rc -eq 0) { "PASS" } else { "FAIL" })
            Crashes    = $crashes
            Exceptions = $exc
            Iters      = $iters
            Log        = Join-Path $outDir "monkey.log"
        }
    }
} finally {
    # Always restore Quick Edit + sleep timeouts, even on Ctrl+C mid-run.
    if (Test-Path $setupScript) { & $setupScript -Restore }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Cyan
foreach ($r in $results) {
    $color = if ($r.ExitCode -eq 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-26} {1}  exit={2}  crashes={3}  exceptions={4}  iters={5}" -f `
        $r.Phase, $r.Status, $r.ExitCode, $r.Crashes, $r.Exceptions, $r.Iters) -ForegroundColor $color
    Write-Host ("      log: {0}" -f $r.Log) -ForegroundColor DarkGray
}
Write-Host "============================================================" -ForegroundColor Cyan

$failed = @($results | Where-Object { $_.ExitCode -ne 0 })
$crashed = @($results | Where-Object { $_.Crashes -ne "-" -and $_.Crashes -ne 0 })
if ($failed.Count -eq 0) {
    Write-Host ("ALL {0} PHASES PASSED" -f $phases.Count) -ForegroundColor Green
} else {
    Write-Host ("{0} of {1} PHASE(S) FAILED - check the logs above" -f $failed.Count, $phases.Count) -ForegroundColor Red
}

# ── Paste-ready analysis block (nightly only) ───────────────────────────────
if ($Nightly) {
    Write-Host ""
    Write-Host "+--------------------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host "|  PASTE THE BLOCK BELOW INTO A NEW CHAT TO GET A FIX LIST            |" -ForegroundColor Cyan
    Write-Host "+--------------------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "I ran the NetSentinel nightly chaos + systematic suite on my PC."
    Write-Host ("Output root: {0}" -f $outRoot)
    Write-Host "Per-phase results (exit / crashes / exceptions / iterations):"
    foreach ($r in $results) {
        Write-Host ("  - {0,-26} exit={1} crashes={2} exceptions={3} iters={4}" -f `
            $r.Phase, $r.ExitCode, $r.Crashes, $r.Exceptions, $r.Iters)
    }
    Write-Host ""
    Write-Host "Phase folders under the output root: sys_pre, monkey_mild, monkey_moderate,"
    Write-Host "monkey_wild, mouse_wild, scan_navigate, sys_post (each has monkey.log,"
    Write-Host "monkey_summary.json, and any *_crash*.txt / screenshot PNGs)."
    Write-Host ""
    Write-Host "Please inspect the logs/crash reports/screenshots, summarise what happened"
    Write-Host "per phase, list every crash or exception with the page/action that triggered"
    Write-Host "it, and give me a prioritised fix list. Ignore pywinauto focus warnings and"
    Write-Host "QThreadStorage teardown warnings - those are known harmless noise."
    Write-Host ""
}

if ($failed.Count -eq 0) { exit 0 } else { exit 1 }
