<#
.SYNOPSIS
    One-command NetSentinel chaos/monkey test runner.

.DESCRIPTION
    Runs ONE coverage cycle (~1h), then - if enough budget remains - switches
    to a long-haul memory-soak tail for the rest of the run. Two phases:

    Coverage cycle (always runs once, first): bracketed by a systematic
    coverage sweep (every page, pre and post), five chaos phases in between,
    time-weighted like the old overnight .bat suites (wild gets ~3x mild's
    share):

        sweep (coverage)   - every page, every control, once
        monkey mild        - UIA control clicking, weight 1
        monkey moderate    - UIA control clicking, weight 2
        monkey wild        - UIA control clicking, weight 3
        monkey wild (mouse)- real mouse: control centres + header + chaos, weight 2
        scan/navigate      - start a scan, navigate away, check for damage, weight 1
        sweep (coverage)   - every page, every control, once  [closing / soak's opening]

    Soak tail (runs once budget/indefinite-run permitting, after the coverage
    cycle): mild -> moderate -> wild ONLY (no mouse/scan - those are one-time
    coverage extras), each a single LONG uninterrupted process with
    --tracemalloc on, split ~12%/33%/55% of the remaining budget (matching the
    old 9h/24h .bat time split) - or fixed 1h/2.5h/4.5h laps, repeating until
    Ctrl+C, when the budget is blank. Restarting the app every few minutes (the
    coverage cycle's model) caps how much a slow leak can ever compound before
    it's visible; one process running for hours does not. Skipped (falls back
    to more short cycles instead) when under an hour of budget remains after
    the coverage cycle - not worth it for that little time.

    Seeds rotate each cycle/lap (cycle 1 = 1/42/99, soak lap 2 = 101/142/199,
    ...) so a long budget still produces different random walks per phase.

    Writes AI_REPORT.md to the output root, REWRITTEN AFTER EVERY PHASE (not
    just at the end) so a hang, a closed window, or Ctrl+C still leaves a
    complete, paste-ready report of everything that finished. It embeds the
    actual crash-file contents and extracted tracebacks, not just pass/fail
    counts, plus a Peak RSS (MB) column and first/last tracemalloc top-allocator
    snapshots for soak phases, so a slow leak is visible without extra digging.

.PARAMETER Duration
    Total wall-clock time budget for the whole run. Accepts "1h", "45m",
    "300s", or a bare number (interpreted as minutes). Omit to run cycles
    forever until Ctrl+C.

    Very small budgets (under ~15 minutes) may only get through the coverage
    sweep, since the sweep itself isn't time-sliced.

.PARAMETER Soak
    Skip the ~1h coverage cycle and go STRAIGHT into the long-haul soak tail
    (opening sweep -> continuous mild/moderate/wild with --tracemalloc ->
    closing sweep). Use this when you specifically want the memory-leak hunt
    and don't want to wait an hour for the coverage cycle to finish first. The
    whole budget is spent on the soak (minus the two bracketing sweeps).

.PARAMETER PlanOnly
    Print the resolved cycle/phase plan and exit. Launches nothing, does not
    touch console Quick Edit / sleep settings.

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1
    Run cycles until you press Ctrl+C.

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1 1h
    One coverage cycle (~1h), then stop and finalize AI_REPORT.md - too short
    for a soak tail.

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1 20h
    Overnight run: one coverage cycle (~1h), then ~19h of continuous
    mild/moderate/wild soak (no app restarts) to surface slow memory leaks.

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1 8h -Soak
    Skip the coverage cycle - spend all 8h on the continuous memory soak from
    the start.

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1 20h -PlanOnly
    Preview the cycle/phase plan for a 20-hour run without launching anything.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Duration = "",

    [switch]$Soak,
    [switch]$PlanOnly
)

# Repo root is the parent of tools\ (this script's dir).
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# ── Tunables ─────────────────────────────────────────────────────────────────
# One "unit" of weight; wild/mouse get multiples of it. Nominal (uncapped by a
# tight budget) unit is ~5.5 min, so a full cycle's phases run ~49.5 min.
$NominalUnitSecs = 330
$MinUnitSecs     = 30
# Estimated cost of one systematic_test.py sweep (62 pages). Used only for
# budget math - the sweep itself is not duration-limited.
$SweepEstSecs    = 300
$MaxCyclesGuard  = 500   # safety cap so a bug can't spin the planner forever

# Soak-mode tunables. After the first coverage cycle (~1h), a long budget stops
# doing short restart-every-phase cycles and instead runs mild/moderate/wild as
# a small number of LONG, CONTINUOUS invocations - like the old overnight .bat
# suites did - so a slow leak has hours in ONE process to compound instead of
# being wiped out by an app restart every ~5-16 minutes.
$SoakMinRemainingSecs       = 3600    # skip soak mode if <1h remains after cycle 1 - not worth it
$SoakMildFrac               = 0.12
$SoakModerateFrac           = 0.33
$SoakWildFrac               = 0.55    # ~= old 9h/24h .bat mild:moderate:wild time split
$SoakIndefiniteMildSecs     = 3600    # 1h   ) fixed lap lengths when the budget is blank -
$SoakIndefiniteModerateSecs = 9000    # 2.5h ) there's no total to split proportionally
$SoakIndefiniteWildSecs     = 16200   # 4.5h ) against. 8h/lap, repeats until Ctrl+C.

$PhaseDefs = @(
    [pscustomobject]@{ Key = "mild";     Label = "Monkey mild (UIA)";        Script = "tools\monkey_test.py";        Weight = 1; SeedBase = 1;   MemLimit = 1000; Chaos = "mild" },
    [pscustomobject]@{ Key = "moderate"; Label = "Monkey moderate (UIA)";    Script = "tools\monkey_test.py";        Weight = 2; SeedBase = 42;  MemLimit = 1200; Chaos = "moderate" },
    [pscustomobject]@{ Key = "wild";     Label = "Monkey wild (UIA)";        Script = "tools\monkey_test.py";        Weight = 3; SeedBase = 99;  MemLimit = 1500; Chaos = "wild" },
    [pscustomobject]@{ Key = "mouse";    Label = "Monkey wild (real mouse)"; Script = "tools\monkey_mouse_test.py";  Weight = 2; SeedBase = 99;  MemLimit = 1500; Chaos = "wild" },
    [pscustomobject]@{ Key = "scan";     Label = "Scan/navigate churn";      Script = "tools\scan_navigate_test.py"; Weight = 1; SeedBase = $null; MemLimit = $null; Chaos = $null }
)
$WeightSum = ($PhaseDefs | Measure-Object -Property Weight -Sum).Sum

# Soak-mode phase list: mild/moderate/wild only - no mouse/scan. Those two are
# one-time coverage additions (real-mouse movement, scan/navigate churn) and
# don't belong in a multi-hour unattended soak. Reuses each phase's Script/
# SeedBase/MemLimit from $PhaseDefs so seed math and mem-limit behaviour match
# the coverage cycle exactly.
$SoakPhaseDefs = $PhaseDefs | Where-Object { $_.Key -in @("mild", "moderate", "wild") } | ForEach-Object {
    [pscustomobject]@{
        Key      = $_.Key
        Label    = "$($_.Label) (soak)"
        Script   = $_.Script
        SeedBase = $_.SeedBase
        MemLimit = $_.MemLimit
        Chaos    = $_.Chaos
    }
}

# ── Helpers ──────────────────────────────────────────────────────────────────

function Resolve-BudgetSeconds {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    $t = $Text.Trim()
    if ($t -match '^(\d+(\.\d+)?)([hms]?)$') {
        $num  = [double]$Matches[1]
        $unit = $Matches[3]
        if ($unit -eq 'h') { return [int]($num * 3600) }
        if ($unit -eq 'm') { return [int]($num * 60) }
        if ($unit -eq 's') { return [int]$num }
        return [int]($num * 60)   # bare number = minutes
    }
    throw "Could not parse duration '$Text' - use forms like 1h, 45m, 300s, or a bare number of minutes."
}

function Format-Secs {
    param([double]$Secs)
    $s = [int][math]::Round($Secs)
    if ($s -lt 60) { return "${s}s" }
    $m = [math]::Floor($s / 60)
    $r = $s % 60
    if ($m -lt 60) { return "${m}m ${r}s" }
    $h = [math]::Floor($m / 60)
    $mr = $m % 60
    return "${h}h ${mr}m"
}

function Get-NextCycleUnit {
    param([Nullable[double]]$RemainingSecs)
    if ($null -eq $RemainingSecs) { return $NominalUnitSecs }
    $remainingForPhases = $RemainingSecs - $SweepEstSecs   # reserve this cycle's closing sweep
    if ($remainingForPhases -lt ($MinUnitSecs * $WeightSum)) { return $null }
    $unit = [math]::Floor($remainingForPhases / $WeightSum)
    if ($unit -gt $NominalUnitSecs) { $unit = $NominalUnitSecs }
    if ($unit -lt $MinUnitSecs) { $unit = $MinUnitSecs }
    return [int]$unit
}

function Get-SoakDurations {
    # Splits remaining time into long mild/moderate/wild soak-phase durations.
    # $RemainingSecs = $null -> indefinite budget, use the fixed lap lengths.
    # Returns $null when there isn't enough time left to be worth entering soak
    # mode (caller keeps doing normal short cycles instead) - unless -Force, set
    # when the user asked for soak explicitly (-Soak) and wants it regardless.
    param([Nullable[double]]$RemainingSecs, [switch]$Force)

    if ($null -eq $RemainingSecs) {
        return [ordered]@{
            mild     = $SoakIndefiniteMildSecs
            moderate = $SoakIndefiniteModerateSecs
            wild     = $SoakIndefiniteWildSecs
        }
    }

    $usable = $RemainingSecs - $SweepEstSecs   # reserve the final closing sweep
    if (-not $Force -and $usable -lt $SoakMinRemainingSecs) { return $null }
    if ($usable -lt ($MinUnitSecs * 3)) { return $null }   # too small even for -Force

    $mild = [int]($usable * $SoakMildFrac)
    $moderate = [int]($usable * $SoakModerateFrac)
    $wild = [int]($usable - $mild - $moderate)   # remainder avoids rounding drift
    return [ordered]@{ mild = $mild; moderate = $moderate; wild = $wild }
}

function Get-OutSub {
    param([string]$Kind, [int]$CycleNum, [string]$Key)
    $c = "{0:D2}" -f $CycleNum
    if ($Kind -eq "sweep") { return "sweep_$c" }
    if ($Kind -eq "soak") { return "soak_${c}_$Key" }
    if ($Kind -eq "soaksweep") { return "sweep_soak_final" }
    return "c${c}_$Key"
}

function Get-PhaseFindings {
    param([string]$OutDir)
    $findings = [pscustomobject]@{ CrashFiles = @(); Tracebacks = @(); Screenshots = @() }
    if (-not (Test-Path $OutDir)) { return $findings }

    $crashFiles = Get-ChildItem -Path $OutDir -Filter "*crash*.txt" -File -ErrorAction SilentlyContinue | Select-Object -First 3
    foreach ($cf in $crashFiles) {
        $content = Get-Content $cf.FullName -TotalCount 60 -ErrorAction SilentlyContinue
        $findings.CrashFiles += [pscustomobject]@{ Name = $cf.Name; Content = ($content -join "`n") }
    }

    $logPath = Join-Path $OutDir "monkey.log"
    if (Test-Path $logPath) {
        $lines = Get-Content $logPath -ErrorAction SilentlyContinue
        $blocks = @()
        for ($i = 0; $i -lt $lines.Count -and $blocks.Count -lt 5; $i++) {
            if ($lines[$i] -match '^Traceback \(most recent call last\):') {
                $block = New-Object System.Collections.Generic.List[string]
                $block.Add($lines[$i])
                $j = $i + 1
                while ($j -lt $lines.Count -and $block.Count -lt 30 -and ($lines[$j] -match '^\s+' -or $lines[$j] -eq '')) {
                    $block.Add($lines[$j])
                    $j++
                }
                if ($j -lt $lines.Count -and $block.Count -lt 30) {
                    $block.Add($lines[$j])
                    $j++
                }
                $blockText = ($block -join "`n")
                if ($blocks -notcontains $blockText) { $blocks += $blockText }
                $i = $j - 1
            }
        }
        $findings.Tracebacks = $blocks
    }

    $shots = @(Get-ChildItem -Path $OutDir -Filter "*.png" -File -ErrorAction SilentlyContinue | Select-Object -First 10 -ExpandProperty Name)
    $findings.Screenshots = $shots
    return $findings
}

function Get-TracemallocSnapshots {
    # Extracts the first and last "tracemalloc top-20" blocks from a captured
    # tracemalloc.log (soak phases only - see Invoke-Phase -Tracemalloc). Only
    # the first/last snapshot are kept (not all of them - a multi-hour soak
    # phase can take 200+ snapshots) so an AI reviewing AI_REPORT.md can compare
    # start-of-phase vs end-of-phase allocation sizes directly.
    param([string]$LogPath)
    $result = [pscustomobject]@{ First = $null; Last = $null; Count = 0 }
    if (-not (Test-Path $LogPath)) { return $result }
    $lines = @(Get-Content $LogPath -ErrorAction SilentlyContinue)
    if ($lines.Count -eq 0) { return $result }

    $starts = @()
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'tracemalloc top-20') { $starts += $i }
    }
    $result.Count = $starts.Count
    if ($starts.Count -eq 0) { return $result }

    $firstEnd = $lines.Count - 1
    if ($starts.Count -gt 1) { $firstEnd = $starts[1] - 1 }
    $result.First = ($lines[$starts[0]..$firstEnd] -join "`n")

    if ($starts.Count -gt 1) {
        $lastStart = $starts[$starts.Count - 1]
        $result.Last = ($lines[$lastStart..($lines.Count - 1)] -join "`n")
    }
    return $result
}

function Write-AiReport {
    param(
        [string]$ReportPath,
        [pscustomobject]$Meta,
        [System.Collections.ArrayList]$Results,
        [switch]$Final
    )

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("# NetSentinel chaos test run")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("Paste this whole file into a chat with an AI assistant working on the")
    [void]$sb.AppendLine("NetSentinel repo. Ask it to: summarise what happened per phase, list every")
    [void]$sb.AppendLine("crash or exception with the page/action that triggered it, and give a")
    [void]$sb.AppendLine("prioritised fix list. Ignore pywinauto focus warnings and QThreadStorage")
    [void]$sb.AppendLine("teardown warnings in the logs - those are known harmless noise.")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine('Also check the Peak RSS (MB) column for a rising trend across the `(soak)`')
    [void]$sb.AppendLine("phase rows (mild -> moderate -> wild, and lap-over-lap on an indefinite run)")
    [void]$sb.AppendLine("- those run for hours in one uninterrupted process specifically to surface a")
    [void]$sb.AppendLine("slow leak that a short restart-every-few-minutes phase would never show. Where")
    [void]$sb.AppendLine("a soak phase's tracemalloc first/last snapshots are both present in Findings,")
    [void]$sb.AppendLine("compare their allocation sizes and point out any line/site that grew a lot.")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Run info")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("- Started: $($Meta.Started)")
    if ($Final) {
        [void]$sb.AppendLine("- Finished: $($Meta.Ended)")
    } else {
        [void]$sb.AppendLine("- Status: IN PROGRESS (this file is rewritten after every phase)")
    }
    [void]$sb.AppendLine("- Budget: $($Meta.BudgetLabel)")
    [void]$sb.AppendLine("- Cycles completed: $($Meta.CyclesCompleted)")
    [void]$sb.AppendLine("- Output root: $($Meta.OutRoot)")
    [void]$sb.AppendLine("- Runner: tools/run_all_monkey_tests.ps1")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Phase results")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| Cycle | Phase | Chaos | Seed | Planned | Actual | Exit | Crashes | Exceptions | Iters | Focus-stolen | Peak RSS (MB) |")
    [void]$sb.AppendLine("|---|---|---|---|---|---|---|---|---|---|---|---|")
    foreach ($r in $Results) {
        $chaosCell = "-"; if ($r.Chaos) { $chaosCell = $r.Chaos }
        $seedCell = "-"; if ($null -ne $r.Seed) { $seedCell = "$($r.Seed)" }
        $crashCell = "-"; if ($null -ne $r.Crashes) { $crashCell = "$($r.Crashes)" }
        $excCell = "-"; if ($null -ne $r.Exceptions) { $excCell = "$($r.Exceptions)" }
        $itersCell = "-"; if ($null -ne $r.Iters) { $itersCell = "$($r.Iters)" }
        $focusCell = "-"; if ($null -ne $r.FocusStolen) { $focusCell = "$($r.FocusStolen)" }
        $rssCell = "-"; if ($null -ne $r.PeakRssMb) { $rssCell = "$($r.PeakRssMb)" }
        [void]$sb.AppendLine("| $($r.Cycle) | $($r.Phase) | $chaosCell | $seedCell | $(Format-Secs $r.PlannedSecs) | $(Format-Secs $r.ActualSecs) | $($r.ExitCode) | $crashCell | $excCell | $itersCell | $focusCell | $rssCell |")
    }
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Findings")
    [void]$sb.AppendLine("")

    $anyFindings = $false
    foreach ($r in $Results) {
        $hasTracemalloc = $r.Findings -and $r.Findings.TracemallocSnapshots -and $r.Findings.TracemallocSnapshots.Count -gt 0
        $needsDetail = ($r.ExitCode -ne 0) -or ($r.Crashes -gt 0) -or ($r.Exceptions -gt 0) -or $hasTracemalloc
        if (-not $needsDetail) { continue }
        $anyFindings = $true
        [void]$sb.AppendLine("### Cycle $($r.Cycle) - $($r.Phase)")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("Log: ``$($r.OutDir)\monkey.log``")
        [void]$sb.AppendLine("")
        if ($r.Findings) {
            foreach ($cf in $r.Findings.CrashFiles) {
                [void]$sb.AppendLine("**Crash file: $($cf.Name)**")
                [void]$sb.AppendLine('```')
                [void]$sb.AppendLine($cf.Content)
                [void]$sb.AppendLine('```')
                [void]$sb.AppendLine("")
            }
            $tbNum = 0
            foreach ($tb in $r.Findings.Tracebacks) {
                $tbNum++
                [void]$sb.AppendLine("**Traceback $tbNum**")
                [void]$sb.AppendLine('```')
                [void]$sb.AppendLine($tb)
                [void]$sb.AppendLine('```')
                [void]$sb.AppendLine("")
            }
            if ($r.Findings.Screenshots.Count -gt 0) {
                [void]$sb.AppendLine("Screenshots: " + ($r.Findings.Screenshots -join ", "))
                [void]$sb.AppendLine("")
            }
            $tm = $r.Findings.TracemallocSnapshots
            if ($tm -and $tm.Count -gt 0) {
                [void]$sb.AppendLine("**Tracemalloc snapshots ($($tm.Count) taken, ~1/min) - compare first vs last for growth:**")
                [void]$sb.AppendLine("")
                [void]$sb.AppendLine("_First snapshot:_")
                [void]$sb.AppendLine('```')
                [void]$sb.AppendLine($tm.First)
                [void]$sb.AppendLine('```')
                [void]$sb.AppendLine("")
                if ($tm.Last) {
                    [void]$sb.AppendLine("_Last snapshot:_")
                    [void]$sb.AppendLine('```')
                    [void]$sb.AppendLine($tm.Last)
                    [void]$sb.AppendLine('```')
                    [void]$sb.AppendLine("")
                } else {
                    [void]$sb.AppendLine("_Only one snapshot was taken (phase shorter than ~2 min warmup+interval)._")
                    [void]$sb.AppendLine("")
                }
            }
        }
    }
    if (-not $anyFindings) {
        [void]$sb.AppendLine("No crashes or exceptions recorded in any completed phase so far.")
        [void]$sb.AppendLine("")
    }

    Set-Content -Path $ReportPath -Value $sb.ToString() -Encoding UTF8
}

function Invoke-Phase {
    param(
        [int]$CycleNum,
        [string]$Label,
        [string]$Script,
        [string[]]$ScriptArgs,
        [string]$OutDir,
        [string]$Chaos,
        [Nullable[int]]$Seed,
        [int]$PlannedSecs,
        [switch]$Tracemalloc
    )

    Write-Host ""
    Write-Host ("  -> {0}  (planned {1})..." -f $Label, (Format-Secs $PlannedSecs)) -ForegroundColor Yellow

    $fullArgs = $ScriptArgs + @("--output-dir", $OutDir)
    $t0 = Get-Date
    # Do NOT redirect stderr (2>&1) - in Windows PowerShell that wraps native
    # stderr lines as error records and falsely flips $? even on exit 0.
    & python $Script @fullArgs
    $rc = $LASTEXITCODE
    $actualSecs = ((Get-Date) - $t0).TotalSeconds

    $crashes = $null; $exc = $null; $iters = $null; $focusStolen = $null; $peakRss = $null
    $summaryPath = Join-Path $OutDir "monkey_summary.json"
    if (Test-Path $summaryPath) {
        try {
            $s = Get-Content $summaryPath -Raw | ConvertFrom-Json
            $crashes = $s.crashes
            $exc = $s.exceptions_caught
            $iters = $s.iterations_completed
            $focusStolen = $s.focus_stolen_count
            $peakRss = $s.peak_rss_mb
        } catch {
            # malformed/partial JSON - process may have been killed mid-write; leave placeholders
        }
    }

    # Soak phases run with --tracemalloc; app.py writes snapshots to a single
    # fixed path in get_app_data_dir() (truncated fresh on every app launch),
    # so copy it into this phase's own OutDir before the next phase overwrites it.
    $tracemallocLog = $null
    if ($Tracemalloc) {
        $tmSrc = Join-Path $env:LOCALAPPDATA "NetSentinel\tracemalloc_snapshots.log"
        if (Test-Path $tmSrc) {
            $tmDest = Join-Path $OutDir "tracemalloc.log"
            Copy-Item -Path $tmSrc -Destination $tmDest -Force -ErrorAction SilentlyContinue
            if (Test-Path $tmDest) { $tracemallocLog = $tmDest }
        }
    }

    Write-Host ("     exit={0}  crashes={1}  exceptions={2}  iters={3}  peakRSS={4}MB  actual={5}" -f $rc, $crashes, $exc, $iters, $peakRss, (Format-Secs $actualSecs))

    $needsDetail = ($rc -ne 0) -or ($crashes -gt 0) -or ($exc -gt 0)
    $findings = $null
    if ($needsDetail) { $findings = Get-PhaseFindings -OutDir $OutDir }
    if ($tracemallocLog) {
        if (-not $findings) { $findings = [pscustomobject]@{ CrashFiles = @(); Tracebacks = @(); Screenshots = @() } }
        $findings | Add-Member -NotePropertyName TracemallocSnapshots -NotePropertyValue (Get-TracemallocSnapshots -LogPath $tracemallocLog) -Force
    }

    return [pscustomobject]@{
        Cycle       = $CycleNum
        Phase       = $Label
        Chaos       = $Chaos
        Seed        = $Seed
        PlannedSecs = $PlannedSecs
        ActualSecs  = $actualSecs
        ExitCode    = $rc
        Crashes     = $crashes
        Exceptions  = $exc
        Iters       = $iters
        FocusStolen = $focusStolen
        PeakRssMb   = $peakRss
        OutDir      = $OutDir
        Findings    = $findings
    }
}

# ── Budget resolution ────────────────────────────────────────────────────────

$budgetSecs = $null
try {
    $budgetSecs = Resolve-BudgetSeconds -Text $Duration
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
$budgetLabel = "until Ctrl+C"
if ($budgetSecs) { $budgetLabel = Format-Secs $budgetSecs }

# ── Plan-only preview (no launches, no side effects) ────────────────────────

if ($PlanOnly) {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "NetSentinel chaos test PLAN (preview only - nothing launched)" -ForegroundColor Cyan
    Write-Host ("  budget: {0}" -f $budgetLabel)
    Write-Host "============================================================" -ForegroundColor Cyan

    $elapsed = 0.0
    $cycleNum = 0
    Write-Host ""
    Write-Host ("[cycle 0] sweep (pre)   planned {0}" -f (Format-Secs $SweepEstSecs))
    $elapsed += $SweepEstSecs

    if ($Soak) {
        $remaining = $null
        if ($budgetSecs) { $remaining = $budgetSecs - $elapsed }
        $soakDurations = Get-SoakDurations -RemainingSecs $remaining -Force
        if ($null -eq $soakDurations) {
            Write-Host ""
            Write-Host "  budget too small for -Soak (need a few minutes minimum) - nothing to plan." -ForegroundColor Red
            exit 1
        }
        Write-Host ""
        Write-Host "[soak mode -Soak] straight into long-haul soak from the start - mild/moderate/wild only, continuous (--tracemalloc on), no restarts:" -ForegroundColor DarkCyan
        Write-Host ("    {0,-28} planned {1}" -f "Monkey mild (soak)", (Format-Secs $soakDurations.mild))
        Write-Host ("    {0,-28} planned {1}" -f "Monkey moderate (soak)", (Format-Secs $soakDurations.moderate))
        Write-Host ("    {0,-28} planned {1}" -f "Monkey wild (soak)", (Format-Secs $soakDurations.wild))
        $elapsed += $soakDurations.mild + $soakDurations.moderate + $soakDurations.wild
        if ($budgetSecs) {
            Write-Host ("    {0,-28} planned {1}" -f "sweep (post-soak, final)", (Format-Secs $SweepEstSecs))
            $elapsed += $SweepEstSecs
            Write-Host "  (soak lap runs once, sized to consume the whole budget)" -ForegroundColor DarkGray
        } else {
            Write-Host "  (repeats every ~8h with rotating seeds until Ctrl+C - showing lap 1 only)" -ForegroundColor DarkGray
        }
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Cyan
        if ($budgetSecs) {
            Write-Host ("Estimated total: {0}" -f (Format-Secs $elapsed)) -ForegroundColor Cyan
        } else {
            Write-Host "Runs indefinitely - stop any time with Ctrl+C" -ForegroundColor Cyan
        }
        Write-Host "============================================================" -ForegroundColor Cyan
        exit 0
    }

    while ($true) {
        $cycleNum++
        if ($cycleNum -gt $MaxCyclesGuard) {
            Write-Host "  ... plan truncated at $MaxCyclesGuard cycles" -ForegroundColor DarkGray
            break
        }
        $remaining = $null
        if ($budgetSecs) { $remaining = $budgetSecs - $elapsed }
        $unit = Get-NextCycleUnit -RemainingSecs $remaining
        if ($null -eq $unit) { break }

        $seedOffset = 100 * ($cycleNum - 1)
        Write-Host ""
        Write-Host ("[cycle {0}] unit={1}  seeds: mild={2} moderate={3} wild/mouse={4}" -f `
            $cycleNum, (Format-Secs $unit), (1 + $seedOffset), (42 + $seedOffset), (99 + $seedOffset))
        foreach ($def in $PhaseDefs) {
            $secs = $unit * $def.Weight
            Write-Host ("    {0,-28} planned {1}" -f $def.Label, (Format-Secs $secs))
            $elapsed += $secs
        }
        Write-Host ("    {0,-28} planned {1}" -f "sweep (post/next-pre)", (Format-Secs $SweepEstSecs))
        $elapsed += $SweepEstSecs

        if ($cycleNum -eq 1) {
            $remainingAfterCycle1 = $null
            if ($budgetSecs) { $remainingAfterCycle1 = $budgetSecs - $elapsed }
            $soakDurations = Get-SoakDurations -RemainingSecs $remainingAfterCycle1
            if ($soakDurations) {
                Write-Host ""
                Write-Host "[soak mode] long-haul tail after hour 1 - mild/moderate/wild only, continuous (--tracemalloc on), no restarts:" -ForegroundColor DarkCyan
                Write-Host ("    {0,-28} planned {1}" -f "Monkey mild (soak)", (Format-Secs $soakDurations.mild))
                Write-Host ("    {0,-28} planned {1}" -f "Monkey moderate (soak)", (Format-Secs $soakDurations.moderate))
                Write-Host ("    {0,-28} planned {1}" -f "Monkey wild (soak)", (Format-Secs $soakDurations.wild))
                $elapsed += $soakDurations.mild + $soakDurations.moderate + $soakDurations.wild
                if ($budgetSecs) {
                    Write-Host ("    {0,-28} planned {1}" -f "sweep (post-soak, final)", (Format-Secs $SweepEstSecs))
                    $elapsed += $SweepEstSecs
                    Write-Host "  (soak lap runs once, sized to consume the rest of the budget)" -ForegroundColor DarkGray
                } else {
                    Write-Host "  (repeats every ~8h with rotating seeds until Ctrl+C - showing lap 1 only)" -ForegroundColor DarkGray
                }
                break
            }
        }

        if (-not $budgetSecs) {
            Write-Host ""
            Write-Host "  (repeats with rotating seeds until Ctrl+C - showing cycle 1 only)" -ForegroundColor DarkGray
            break
        }
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    if ($budgetSecs) {
        Write-Host ("Estimated total: {0} across {1} cycle(s)" -f (Format-Secs $elapsed), $cycleNum) -ForegroundColor Cyan
    } else {
        Write-Host "Runs indefinitely - stop any time with Ctrl+C" -ForegroundColor Cyan
    }
    Write-Host "============================================================" -ForegroundColor Cyan
    exit 0
}

# ── Real run ─────────────────────────────────────────────────────────────────

# Activate a local virtualenv if one exists, so the right Python/deps are used
# on a fresh shell.
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

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outRoot = Join-Path $env:USERPROFILE ("Documents\NetSentinel\test_output\run_" + $stamp)
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null
$reportPath = Join-Path $outRoot "AI_REPORT.md"

$setupScript = Join-Path $PSScriptRoot "test_setup.ps1"
if (Test-Path $setupScript) { & $setupScript }

$startTime = Get-Date
$deadline = $null
if ($budgetSecs) { $deadline = $startTime.AddSeconds($budgetSecs) }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "NetSentinel - chaos/monkey test run" -ForegroundColor Cyan
Write-Host ("  budget   : {0}" -f $budgetLabel)
Write-Host ("  output   : {0}" -f $outRoot)
if ($Soak) {
    Write-Host "  mode     : -Soak (memory soak from the start, no coverage cycle)" -ForegroundColor Yellow
} else {
    Write-Host "  NOTE: the real-mouse phase moves your actual cursor - don't" -ForegroundColor Yellow
    Write-Host "        use this PC while that phase is running." -ForegroundColor Yellow
}
Write-Host "============================================================" -ForegroundColor Cyan

$results = New-Object System.Collections.ArrayList
$meta = [pscustomobject]@{
    Started         = $startTime.ToString("yyyy-MM-dd HH:mm:ss")
    Ended           = $null
    BudgetLabel     = $budgetLabel
    CyclesCompleted = 0
    OutRoot         = $outRoot
}

try {
    # Initial coverage sweep
    $sweepArgs = @("--source", "--pause", "0.4", "--focus-interval", "1.5")
    $r = Invoke-Phase -CycleNum 0 -Label "Systematic sweep (pre)" -Script "tools\systematic_test.py" `
        -ScriptArgs $sweepArgs -OutDir (Join-Path $outRoot (Get-OutSub "sweep" 0 "")) `
        -Chaos $null -Seed $null -PlannedSecs $SweepEstSecs
    [void]$results.Add($r)
    Write-AiReport -ReportPath $reportPath -Meta $meta -Results $results

    $cycleNum = 0
    $enterSoak = $false
    $soakDurations = $null

    if ($Soak) {
        # -Soak: skip the coverage cycle, go straight into the long-haul soak
        # using the whole budget (the pre-sweep above is its opening bracket).
        $remaining = $null
        if ($deadline) { $remaining = ($deadline - (Get-Date)).TotalSeconds }
        $soakDurations = Get-SoakDurations -RemainingSecs $remaining -Force
        if ($soakDurations) {
            $enterSoak = $true
        } else {
            Write-Host "  -Soak requested but budget too small to run - stopping." -ForegroundColor Red
        }
    }

    while (-not $Soak) {
        $cycleNum++
        if ($cycleNum -gt $MaxCyclesGuard) { break }   # safety cap, should never trigger in practice

        $remaining = $null
        if ($deadline) { $remaining = ($deadline - (Get-Date)).TotalSeconds }
        $unit = Get-NextCycleUnit -RemainingSecs $remaining
        if ($null -eq $unit) { break }

        $seedOffset = 100 * ($cycleNum - 1)
        Write-Host ""
        Write-Host ("[cycle {0}] unit={1}" -f $cycleNum, (Format-Secs $unit)) -ForegroundColor Cyan

        foreach ($def in $PhaseDefs) {
            if ($deadline -and (Get-Date) -ge $deadline) { break }   # blew the budget mid-cycle - jump to closing sweep

            $secs = $unit * $def.Weight
            $outDir = Join-Path $outRoot (Get-OutSub "phase" $cycleNum $def.Key)
            $seed = $null
            $scriptArgs = @("--source", "--duration", "$secs", "--focus-interval", "1.5")
            if ($def.SeedBase) {
                $seed = $def.SeedBase + $seedOffset
                $scriptArgs += @("--chaos", $def.Chaos, "--seed", "$seed", "--mem-limit", "$($def.MemLimit)")
            }

            $r = Invoke-Phase -CycleNum $cycleNum -Label $def.Label -Script $def.Script `
                -ScriptArgs $scriptArgs -OutDir $outDir -Chaos $def.Chaos -Seed $seed -PlannedSecs $secs
            [void]$results.Add($r)
            Write-AiReport -ReportPath $reportPath -Meta $meta -Results $results
        }

        # Closing sweep for this cycle - also serves as the opening sweep for
        # the next cycle if the budget allows another one.
        $outDir = Join-Path $outRoot (Get-OutSub "sweep" $cycleNum "")
        $r = Invoke-Phase -CycleNum $cycleNum -Label "Systematic sweep (post)" -Script "tools\systematic_test.py" `
            -ScriptArgs $sweepArgs -OutDir $outDir -Chaos $null -Seed $null -PlannedSecs $SweepEstSecs
        [void]$results.Add($r)
        $meta.CyclesCompleted = $cycleNum
        Write-AiReport -ReportPath $reportPath -Meta $meta -Results $results

        # After the first coverage cycle (~1h with mouse/scan included), check
        # whether enough of the budget remains to make a long-haul soak tail
        # worthwhile. Indefinite budgets always qualify (fixed lap lengths).
        if ($cycleNum -eq 1) {
            $remainingAfterCycle1 = $null
            if ($deadline) { $remainingAfterCycle1 = ($deadline - (Get-Date)).TotalSeconds }
            $soakDurations = Get-SoakDurations -RemainingSecs $remainingAfterCycle1
            if ($soakDurations) { $enterSoak = $true }
        }
        if ($enterSoak) { break }

        if ($deadline -and (Get-Date) -ge $deadline) { break }
    }

    if ($enterSoak -and $soakDurations) {
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Cyan
        if ($Soak) {
            Write-Host "[soak] -Soak: long-haul mode from the start - mild/moderate/wild only," -ForegroundColor Cyan
        } else {
            Write-Host "[soak] entering long-haul mode after coverage cycle - mild/moderate/wild only," -ForegroundColor Cyan
        }
        Write-Host "       continuous (--tracemalloc on), no restarts between phases" -ForegroundColor Cyan
        Write-Host "============================================================" -ForegroundColor Cyan

        # Report "Cycle" column: 1 when a coverage cycle preceded the soak, 0 for -Soak-from-start.
        $coverageCycles = $cycleNum

        $lap = 0
        while ($true) {
            $lap++
            $soakSeedOffset = 100 * ($lap - 1)
            foreach ($def in $SoakPhaseDefs) {
                $secs = $soakDurations[$def.Key]
                if ($secs -le 0) { continue }
                $outDir = Join-Path $outRoot (Get-OutSub "soak" $lap $def.Key)
                $seed = $def.SeedBase + $soakSeedOffset
                $scriptArgs = @("--source", "--duration", "$secs", "--focus-interval", "1.5",
                                 "--chaos", $def.Chaos, "--seed", "$seed", "--mem-limit", "$($def.MemLimit)",
                                 "--tracemalloc")

                $r = Invoke-Phase -CycleNum $coverageCycles -Label "$($def.Label) [lap $lap]" -Script $def.Script `
                    -ScriptArgs $scriptArgs -OutDir $outDir -Chaos $def.Chaos -Seed $seed `
                    -PlannedSecs $secs -Tracemalloc
                [void]$results.Add($r)
                $meta.CyclesCompleted = "$coverageCycles (+ soak lap $lap)"
                Write-AiReport -ReportPath $reportPath -Meta $meta -Results $results
            }

            if ($deadline) {
                # Finite budget: the lap was sized to consume the rest of it -
                # close out with one final sweep, same as the old .bat suites.
                $outDir = Join-Path $outRoot (Get-OutSub "soaksweep" 0 "")
                $r = Invoke-Phase -CycleNum $coverageCycles -Label "Systematic sweep (post-soak)" -Script "tools\systematic_test.py" `
                    -ScriptArgs $sweepArgs -OutDir $outDir -Chaos $null -Seed $null -PlannedSecs $SweepEstSecs
                [void]$results.Add($r)
                Write-AiReport -ReportPath $reportPath -Meta $meta -Results $results
                break
            }
            # Indefinite budget: repeat laps with rotating seeds until Ctrl+C -
            # no sweep between laps, so the process keeps accumulating.
        }
    }
} finally {
    # Always restore Quick Edit + sleep timeouts, even on Ctrl+C mid-run.
    if (Test-Path $setupScript) { & $setupScript -Restore }

    $meta.Ended = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Write-AiReport -ReportPath $reportPath -Meta $meta -Results $results -Final
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Cyan
foreach ($r in $results) {
    $color = "Green"
    if ($r.ExitCode -ne 0) { $color = "Red" }
    Write-Host ("  cycle {0,-2} {1,-28} exit={2}  crashes={3}  exceptions={4}  iters={5}" -f `
        $r.Cycle, $r.Phase, $r.ExitCode, $r.Crashes, $r.Exceptions, $r.Iters) -ForegroundColor $color
}
Write-Host "============================================================" -ForegroundColor Cyan

$failed = @($results | Where-Object { $_.ExitCode -ne 0 })
if ($failed.Count -eq 0) {
    Write-Host ("ALL {0} PHASES PASSED across {1} cycle(s)" -f $results.Count, $meta.CyclesCompleted) -ForegroundColor Green
} else {
    Write-Host ("{0} of {1} PHASE(S) FAILED - check AI_REPORT.md" -f $failed.Count, $results.Count) -ForegroundColor Red
}

Write-Host ""
Write-Host "+--------------------------------------------------------------------+" -ForegroundColor Cyan
Write-Host "|  Drop this file into a chat for triage:                            |" -ForegroundColor Cyan
Write-Host ("|  {0,-67}|" -f $reportPath) -ForegroundColor Cyan
Write-Host "+--------------------------------------------------------------------+" -ForegroundColor Cyan
Write-Host ""

if ($failed.Count -eq 0) { exit 0 } else { exit 1 }
