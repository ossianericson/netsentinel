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
    coverage extras), each a single LONG uninterrupted process
    (add -Tracemalloc for allocation profiling; off by default), split
    ~12%/33%/55% of the remaining budget (matching the
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
    (opening sweep -> continuous mild/moderate/wild -> closing sweep).
    Use this when you specifically want the memory-leak hunt
    and don't want to wait an hour for the coverage cycle to finish first. The
    whole budget is spent on the soak (minus the two bracketing sweeps).

.PARAMETER PlanOnly
    Print the resolved cycle/phase plan and exit. Launches nothing, does not
    touch console Quick Edit / sleep settings.

.PARAMETER Store
    Target the installed Microsoft Store package instead of `python app.py`.
    Every phase launches the Store app via normal shell activation
    (`explorer.exe shell:AppsFolder\<AUMID>`) and drives it with `--connect`
    instead of `--source`.

    This matters because a raw exe-path launch (`monkey_test.py <path-to-
    WindowsApps-exe>`) bypasses the MSIX activation broker and reliably
    triggers a false-positive native fault (0x8001010d, RULE-WIN10) that real
    Store users - who always launch via Start Menu/search/taskbar - never
    hit. Shell activation + --connect reproduces the real launch path and was
    confirmed clean in a live A/B test (2026-07-15).

    Soak phases run without --tracemalloc (that instrumentation only works
    with --source - there is no way to inject it into a packaged exe you
    don't control the launch of). Requires the Store build to already be
    installed; resolved once via Get-StartApps at startup.

.PARAMETER MildOnly
.PARAMETER ModerateOnly
.PARAMETER Tracemalloc
    Turn ON Python allocation profiling (--tracemalloc) for soak phases.
    OFF by default, and deliberately so: a 2026-08-02 A/B established that
    tracemalloc itself CAUSED the mid-soak hangs (0 hangs / 0 restarts
    without it, against 1-2 on every prior run; cdb showed the main thread
    stuck inside tracemalloc's own traceback capture). Its per-allocation
    cost also distorts the RSS numbers a soak exists to measure, and it has
    never once found this leak - the growth is native, which is exactly why
    five rounds of tracemalloc saw nothing.

    Use it only when you specifically want Python-side allocation sites and
    accept that the run's timing, hang behaviour and RSS are instrumented.
    Ignored with -Store (source-only instrumentation).

.PARAMETER WildOnly
    Run ONLY that one chaos level as a single continuous soak phase - no
    coverage cycle, no other chaos levels, and no opening/closing
    systematic sweep. Mutually
    exclusive with each other (and implies -Soak's "skip the coverage
    cycle" behavior).

    Use this to shorten a targeted re-run: the two systematic sweeps alone
    have taken 25-28 minutes each in practice (nowhere near the nominal
    5-minute estimate used for budget math), which dominates the runtime of
    a short verification run that only cares about one chaos level.

    With -Duration given, the ENTIRE budget goes to that one phase (no
    proportional mild/moderate/wild split, no time reserved for a sweep).
    With no -Duration, it repeats that phase's normal fixed lap length
    (mild=1h, moderate=2.5h, wild=4.5h) in a loop until Ctrl+C, exactly like
    a normal indefinite soak would for that phase.

.PARAMETER Procdump
    Attach Sysinternals ProcDump (winget install Microsoft.Sysinternals.Suite)
    to the app process during every soak phase (mild/moderate/wild), in
    hang-detection mode (-h -n 5 -ma). Re-attached automatically on every
    internal restart. Captures a full native dump the moment Windows marks
    the window hung (IsHungAppWindow) instead of relying on log correlation
    after the fact - dumps land in <phase-outdir>\dumps\. Exception mode
    (-e 1) was tried first and dropped: every launch throws a routine,
    immediately-handled pybind11::attribute_error during native-extension
    startup that -e 1 can't tell apart from a real fault (cdb-confirmed on
    6/6 dumps across two runs, 2026-08-01) - it never once captured anything
    related to an actual hang. -h targets the real open bug directly. Only
    wired into soak phases, not the coverage sweep, since every hang/RSS-
    plateau occurrence to date has happened during a multi-hour soak. No-ops
    with a one-time warning if ProcDump isn't installed.

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

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1 1h -Store
    One coverage cycle against the Microsoft Store package.

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1 8h -Soak -Store
    Long-haul soak against the Store package (no tracemalloc).

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1 4.5h -WildOnly
    Nothing but a single continuous 4.5h wild-chaos soak, no instrumentation -
    no coverage cycle, no mild/moderate, no sweeps. (Duration only accepts one
    number+unit - "4.5h", "270m", or "16200s", not combined forms like "4h30m".)

.EXAMPLE
    .\tools\run_all_monkey_tests.ps1 -MildOnly
    Repeats 1h mild-only soak laps until Ctrl+C (no -Duration = indefinite,
    using that phase's normal fixed lap length).
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Duration = "",

    [switch]$Soak,
    [switch]$PlanOnly,
    [switch]$Store,

    [switch]$MildOnly,
    [switch]$ModerateOnly,
    [switch]$WildOnly,

    [switch]$Procdump,

    [switch]$AllowGflags,

    [switch]$Tracemalloc
)

# Repo root is the parent of tools\ (this script's dir).
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# ── gflags +ust preflight ────────────────────────────────────────────────────
# monkey_test.py enforces this too (that's the real gate, and it covers ad-hoc
# invocations). This copy exists so a 10-hour overnight run dies in ~2 seconds
# instead of after the opening systematic sweep has already burned five minutes
# and rearranged the console/sleep settings. See _preflight_gflags in
# tools/monkey_test.py for what +ust actually costs.
function Test-UstTracing {
    $ifeo = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
    $traced = @()
    foreach ($image in @("python.exe", "NetSentinel.exe")) {
        $key = Join-Path $ifeo $image
        if (-not (Test-Path $key)) { continue }
        try { $raw = (Get-ItemProperty -Path $key -Name GlobalFlag -ErrorAction Stop).GlobalFlag }
        catch { continue }   # no GlobalFlag value on this image — not traced
        $flag = 0
        $text = "$raw".Trim()
        if ($text -match '^0[xX]') { $flag = [Convert]::ToInt64($text.Substring(2), 16) }
        elseif ($text -match '^\d+$') { $flag = [int64]$text }
        if ($flag -band 0x1000) { $traced += [pscustomobject]@{ Image = $image; Flag = $flag } }
    }
    return $traced
}

$ustTraced = Test-UstTracing
if ($ustTraced.Count -gt 0 -and -not $AllowGflags) {
    Write-Host ""
    Write-Host "ABORTING - gflags +ust stack-trace tracing is armed." -ForegroundColor Red
    Write-Host "Every number this run produces (RSS, peak RSS, timings, hang detection)"
    Write-Host "would be an artifact of the instrumentation, not the app."
    Write-Host ""
    Write-Host "Traced image(s):"
    foreach ($t in $ustTraced) { Write-Host ("    {0}  GlobalFlag=0x{1:X8}" -f $t.Image, $t.Flag) }
    Write-Host ""
    Write-Host "Clear it from an ELEVATED PowerShell:"
    $gflagsExe = "C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\gflags.exe"
    foreach ($t in $ustTraced) { Write-Host ("    & `"{0}`" /i {1} -ust" -f $gflagsExe, $t.Image) }
    Write-Host ""
    Write-Host "Then re-run. Pass -AllowGflags to run under tracing on purpose."
    exit 2
}

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

function Get-OnlyPhaseDuration {
    # Single-phase equivalent of Get-SoakDurations for -MildOnly/-ModerateOnly/
    # -WildOnly. No proportional mild/moderate/wild split and no sweep-time
    # reservation - those modes skip both sweeps entirely (see Invoke-Phase
    # call sites gated on $OnlyPhase), so the WHOLE remaining budget (or the
    # phase's own fixed indefinite lap length, same numbers Get-SoakDurations
    # uses) goes to the one selected phase alone. Returns an $soakDurations-
    # shaped hashtable with the other two keys at 0 so the existing soak-lap
    # loop's `if ($secs -le 0) { continue }` skips them with no other changes.
    param([string]$Phase, [Nullable[double]]$RemainingSecs)

    $indefiniteSecs = @{
        mild     = $SoakIndefiniteMildSecs
        moderate = $SoakIndefiniteModerateSecs
        wild     = $SoakIndefiniteWildSecs
    }
    $durations = [ordered]@{ mild = 0; moderate = 0; wild = 0 }

    if ($null -eq $RemainingSecs) {
        $durations[$Phase] = $indefiniteSecs[$Phase]
        return $durations
    }
    if ($RemainingSecs -lt $MinUnitSecs) { return $null }
    $durations[$Phase] = [int]$RemainingSecs
    return $durations
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
    # Extracts the first and last "tracemalloc top-20" blocks across a soak
    # phase's ENTIRE tracemalloc history, not just the currently-running
    # process's log. monkey_test.py's internal health-monitor restart
    # (_restart_app()) kills a hung/crashed app.py and relaunches it; app.py
    # truncates tracemalloc_snapshots.log fresh on every launch (RULE-TM1), so
    # without this, a phase with 1+ restarts only ever showed the LAST
    # (post-restart) process's snapshots - discarding the whole pre-restart
    # allocation history, including the run-up to whatever triggered the
    # restart. monkey_test.py salvages each pre-restart log into the phase's
    # OutDir as tracemalloc_pre_restart_<N>.log (numbered in restart order,
    # see MonkeyTest._salvage_tracemalloc_log()) before killing the old
    # process; this function stitches those together with the final
    # tracemalloc.log, in chronological order, before taking first/last so an
    # AI reviewing AI_REPORT.md can compare true start-of-phase vs
    # end-of-phase allocation sizes even across a restart.
    param([string]$OutDir)
    $result = [pscustomobject]@{ First = $null; Last = $null; Count = 0 }
    if (-not (Test-Path $OutDir)) { return $result }

    $preRestartFiles = @(Get-ChildItem -Path $OutDir -Filter "tracemalloc_pre_restart_*.log" -File -ErrorAction SilentlyContinue |
        Sort-Object { [int]([regex]::Match($_.Name, '\d+').Value) })
    $orderedPaths = @($preRestartFiles | ForEach-Object { $_.FullName })
    $finalPath = Join-Path $OutDir "tracemalloc.log"
    if (Test-Path $finalPath) { $orderedPaths += $finalPath }
    if ($orderedPaths.Count -eq 0) { return $result }

    $allLines = New-Object System.Collections.Generic.List[string]
    foreach ($p in $orderedPaths) {
        foreach ($ln in @(Get-Content $p -ErrorAction SilentlyContinue)) { $allLines.Add($ln) }
    }
    if ($allLines.Count -eq 0) { return $result }
    # Plain array (not List[T]) so the range-slice indexing below (`$lines[$a..$b]`)
    # behaves exactly like it did against @(Get-Content ...) previously.
    $lines = $allLines.ToArray()

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

function Get-PhaseHealth {
    # Parses a phase's monkey.log for RSS trend + health/restart events. These
    # do NOT surface in exit code, crash count, or exception count: monkey_test's
    # health monitor silently RESTARTS a hung or memory-blown app and the phase
    # then finishes with exit 0. Without this parse, a phase that climbed to
    # 1250 MB and hung for 45s looks identical to a clean phase in the report.
    # Also used to reconstruct a partial result for a phase interrupted by Ctrl+C
    # (which never returns from Invoke-Phase and so never writes monkey_summary.json).
    param([string]$OutDir)
    $h = [pscustomobject]@{
        PeakRssMb = $null; LastRssMb = $null; LastIter = $null
        MemExceeded = 0; Hangs = 0; Restarts = 0
        Events = @(); HasLog = $false
    }
    $logPath = Join-Path $OutDir "monkey.log"
    if (-not (Test-Path $logPath)) { return $h }
    $h.HasLog = $true
    # -Encoding UTF8: monkey.log is written by Python logging as UTF-8 (no BOM);
    # without this PS5.1 reads it as cp1252 and mangles em-dashes into "a-hat"
    # mojibake that then gets baked into the report.
    $lines = @(Get-Content $logPath -Encoding UTF8 -ErrorAction SilentlyContinue)
    if ($lines.Count -eq 0) { return $h }

    $peak = 0; $last = $null; $lastIter = $null
    $memFirst = $null; $memLast = $null
    $evt = New-Object System.Collections.Generic.List[string]
    foreach ($ln in $lines) {
        if ($ln -match 'rss=(\d+)\s*MB') {
            $v = [int]$Matches[1]
            if ($v -gt $peak) { $peak = $v }
            $last = $v
        }
        if ($ln -match 'iter=(\d+)') { $lastIter = [int]$Matches[1] }
        elseif ($ln -match 'Interrupted at iteration (\d+)') { $lastIter = [int]$Matches[1] }

        if ($ln -match 'exceeds limit') {
            $h.MemExceeded++
            if ($null -eq $memFirst) { $memFirst = $ln.Trim() }
            $memLast = $ln.Trim()
        }
        if ($ln -match 'may be hung' -or $ln -match 'No iteration for') { $h.Hangs++; $evt.Add($ln.Trim()) }
        # Count restarts once each: the "restarting app (attempt N/3)" line is
        # emitted exactly once per restart (whether triggered by the health
        # monitor or by "Window/process gone"). The follow-on "relaunch attempt"
        # / "App relaunched" lines are kept as context but not re-counted.
        if ($ln -match 'restarting app \(attempt') { $h.Restarts++; $evt.Add($ln.Trim()) }
        elseif ($ln -match '\[restart\]') { $evt.Add($ln.Trim()) }
        if ($ln -match 'Interrupted at iteration') { $evt.Add($ln.Trim()) }
    }
    if ($peak -gt 0) { $h.PeakRssMb = $peak }
    $h.LastRssMb = $last
    $h.LastIter = $lastIter
    if ($h.MemExceeded -gt 0 -and $memFirst) {
        $evt.Insert(0, "RSS exceeded mem-limit x$($h.MemExceeded): first [$memFirst] last [$memLast]")
    }
    # dedupe, preserve order, cap length
    $seen = @{}; $out = New-Object System.Collections.Generic.List[string]
    foreach ($e in $evt) {
        if (-not $seen.ContainsKey($e)) { $seen[$e] = $true; $out.Add($e) }
        if ($out.Count -ge 25) { break }
    }
    $h.Events = $out.ToArray()
    return $h
}

function Resolve-StoreApp {
    # Resolves the Store package's AUMID once via Get-StartApps (the same
    # index Start Menu search uses) - not a hardcoded PackageFamilyName,
    # which changes per-publisher/per-machine. Hard-errors if not found:
    # -Store has nothing to launch without an installed Store build.
    $app = Get-StartApps | Where-Object { $_.Name -eq "NetSentinel" } | Select-Object -First 1
    if (-not $app) {
        Write-Host "ERROR: -Store requires the Microsoft Store build of NetSentinel to be installed (not found via Get-StartApps)." -ForegroundColor Red
        exit 1
    }
    $script:StoreAumid = $app.AppID
    $pfn = ($app.AppID -split '!')[0]
    $pkg = Get-AppxPackage | Where-Object { $_.PackageFamilyName -eq $pfn } | Select-Object -First 1
    if ($pkg) { $script:StorePackageLabel = "$($pkg.Name) $($pkg.Version) ($($pkg.PackageFullName))" }
    else { $script:StorePackageLabel = $app.AppID }
    Write-Host "[setup] Store target: $script:StorePackageLabel" -ForegroundColor Gray
}

function Start-StoreApp {
    # Kills any stale NetSentinel process, then launches the Store package via
    # normal shell activation - NOT a raw exe-path Popen. Direct exe-path
    # launch bypasses the MSIX activation broker (ApplicationActivationManager)
    # and reliably reproduces a false-positive 0x8001010d UIA fault
    # (RULE-WIN10) that real Store users never see, because they always
    # launch via Start Menu/search/taskbar, which goes through the broker.
    # Proved 2026-07-15: identical exe, --connect after shell activation =
    # clean 20/20 iterations; monkey_test.py <exe_path> direct launch =
    # crash on iteration 0.
    Get-Process -Name "NetSentinel" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    Start-Process "explorer.exe" -ArgumentList "shell:AppsFolder\$script:StoreAumid"

    # --connect mode in monkey_test.py/systematic_test.py/etc. is a ONE-SHOT
    # window check (_attach()) - unlike --source/exe launch, it does NOT poll
    # for up to 60s. A cold Store-app launch takes ~15-20s to render its main
    # window (measured 2026-07-15), so this wrapper must own the wait instead
    # or every phase's _attach() fires before the window exists.
    #
    # Must match "*Dashboard*" specifically, not just a non-empty title: the
    # splash screen's own window title is literally "NetSentinel" (matches a
    # bare non-empty check) and is visible for ~10s before the real Dashboard
    # window replaces it (traced 2026-07-15 - splash title holds t=5s..t=12s,
    # "NetSentinel — Dashboard" only appears at t=13s). Matching on the splash
    # would return early and hand _attach() a window that's about to close.
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $p = Get-Process -Name "NetSentinel" -ErrorAction SilentlyContinue |
             Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*Dashboard*" } |
             Select-Object -First 1
        if ($p) { Start-Sleep -Milliseconds 1500; return }   # brief settle so UIA has a stable tree before --connect's one-shot check
        Start-Sleep -Milliseconds 1000
    }
    Write-Host "[warn] Store app window did not appear within 60s - next phase's --connect will likely fail." -ForegroundColor Yellow
}

function Get-LaunchModeArgs {
    # Central switch between the two ways a phase can reach the app: normal
    # dev loop launches fresh `python app.py` per phase (--source); -Store
    # mode instead relies on the caller having already started the app via
    # Start-StoreApp and just attaches (--connect).
    #
    # -SupportsMaxRestarts scripts (monkey_test.py, monkey_mouse_test.py,
    # scan_navigate_test.py) get an explicit --max-restarts 0 in Store mode:
    # their built-in crash-recovery calls _launch_exe(), which uses
    # self.cfg.exe_path - always None in --connect mode - so a real in-phase
    # crash would fail to relaunch anyway. The wrapper's own per-phase fresh
    # relaunch (Start-StoreApp before every Invoke-Phase call) already
    # provides equivalent recovery at the cycle level; this just avoids a
    # confusing "relaunch failed" line in the log for a restart path that was
    # never going to work.
    param([switch]$SupportsMaxRestarts)
    if ($Store) {
        $a = @("--connect")
        if ($SupportsMaxRestarts) { $a += @("--max-restarts", "0") }
        return $a
    }
    return @("--source")
}

function Format-HealthCell {
    param($Health)
    if ($null -eq $Health) { return "-" }
    $parts = @()
    if ($Health.Hangs -gt 0)       { $parts += "hang x$($Health.Hangs)" }
    if ($Health.MemExceeded -gt 0) { $parts += "mem x$($Health.MemExceeded)" }
    if ($Health.Restarts -gt 0)    { $parts += "restart x$($Health.Restarts)" }
    if ($parts.Count -gt 0) { return ($parts -join ", ") }
    if ($Health.HasLog) { return "ok" }
    return "-"
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
    if ($Meta.Target) { [void]$sb.AppendLine("- Target: $($Meta.Target)") }
    [void]$sb.AppendLine("- Cycles completed: $($Meta.CyclesCompleted)")
    [void]$sb.AppendLine("- Output root: $($Meta.OutRoot)")
    [void]$sb.AppendLine("- Runner: tools/run_all_monkey_tests.ps1")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Phase results")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| Cycle | Phase | Chaos | Seed | Planned | Actual | Exit | Crashes | Exceptions | Iters | Focus-stolen | Health | Peak RSS (MB) |")
    [void]$sb.AppendLine("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    foreach ($r in $Results) {
        $chaosCell = "-"; if ($r.Chaos) { $chaosCell = $r.Chaos }
        $seedCell = "-"; if ($null -ne $r.Seed) { $seedCell = "$($r.Seed)" }
        $crashCell = "-"; if ($null -ne $r.Crashes) { $crashCell = "$($r.Crashes)" }
        $excCell = "-"; if ($null -ne $r.Exceptions) { $excCell = "$($r.Exceptions)" }
        $itersCell = "-"; if ($null -ne $r.Iters) { $itersCell = "$($r.Iters)" }
        $focusCell = "-"; if ($null -ne $r.FocusStolen) { $focusCell = "$($r.FocusStolen)" }
        $healthCell = Format-HealthCell $r.Health
        $rssCell = "-"; if ($null -ne $r.PeakRssMb) { $rssCell = "$($r.PeakRssMb)" }
        [void]$sb.AppendLine("| $($r.Cycle) | $($r.Phase) | $chaosCell | $seedCell | $(Format-Secs $r.PlannedSecs) | $(Format-Secs $r.ActualSecs) | $($r.ExitCode) | $crashCell | $excCell | $itersCell | $focusCell | $healthCell | $rssCell |")
    }
    [void]$sb.AppendLine("")

    # Health-events section - surfaces mid-phase hangs, memory-limit breaches, and
    # health-monitor restarts that a phase's exit code / crash / exception counts
    # all hide (the monitor restarts the app and the phase still finishes exit 0).
    $healthPhases = @($Results | Where-Object { $_.Health -and (($_.Health.Hangs -gt 0) -or ($_.Health.MemExceeded -gt 0) -or ($_.Health.Restarts -gt 0)) })
    if ($healthPhases.Count -gt 0) {
        [void]$sb.AppendLine("## Health events (memory limit / hangs / restarts)")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("These do NOT show up in Exit / Crashes / Exceptions - monkey_test's health")
        [void]$sb.AppendLine("monitor silently restarts a hung or memory-blown app and the phase still")
        [void]$sb.AppendLine("finishes exit 0. Treat any row below as a real defect to investigate.")
        [void]$sb.AppendLine("")
        foreach ($r in $healthPhases) {
            [void]$sb.AppendLine("### $($r.Phase)  (cycle $($r.Cycle))")
            $peakTxt = "?"; if ($r.Health.PeakRssMb) { $peakTxt = "$($r.Health.PeakRssMb)" }
            $lastTxt = "?"; if ($r.Health.LastRssMb) { $lastTxt = "$($r.Health.LastRssMb)" }
            [void]$sb.AppendLine("- Peak RSS ${peakTxt} MB, last RSS ${lastTxt} MB, last iter $($r.Health.LastIter)")
            [void]$sb.AppendLine("- hangs=$($r.Health.Hangs)  mem-limit-breaches=$($r.Health.MemExceeded)  restarts=$($r.Health.Restarts)")
            if ($r.Health.Events.Count -gt 0) {
                [void]$sb.AppendLine('```')
                foreach ($e in $r.Health.Events) { [void]$sb.AppendLine($e) }
                [void]$sb.AppendLine('```')
            }
            [void]$sb.AppendLine("")
        }
    }

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
    # The top-level preflight already let this run through, so pass the same
    # consent down - otherwise monkey_test.py's own gate would abort every phase.
    if ($script:AllowGflags -and $Script -like "*monkey_test.py") { $fullArgs += "--allow-gflags" }
    $t0 = Get-Date
    # Publish the in-flight phase to script scope BEFORE launching python, so a
    # Ctrl+C (which aborts this function mid-call and jumps straight to the
    # top-level finally) can still reconstruct a partial row for it. Cleared to
    # $null just before this function returns on a normal completion.
    $script:CurrentPhase = [pscustomobject]@{
        Cycle = $CycleNum; Label = $Label; Chaos = $Chaos; Seed = $Seed
        PlannedSecs = $PlannedSecs; OutDir = $OutDir; T0 = $t0; Tracemalloc = [bool]$Tracemalloc
    }
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
    # This is the FINAL process's log only - any earlier, internally-restarted
    # process's snapshots were already salvaged into tracemalloc_pre_restart_*.log
    # by MonkeyTest._salvage_tracemalloc_log(); Get-TracemallocSnapshots merges both.
    if ($Tracemalloc) {
        $tmSrc = Join-Path $env:LOCALAPPDATA "NetSentinel\tracemalloc_snapshots.log"
        if (Test-Path $tmSrc) {
            $tmDest = Join-Path $OutDir "tracemalloc.log"
            Copy-Item -Path $tmSrc -Destination $tmDest -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host ("     exit={0}  crashes={1}  exceptions={2}  iters={3}  peakRSS={4}MB  actual={5}" -f $rc, $crashes, $exc, $iters, $peakRss, (Format-Secs $actualSecs))

    # Always parse the log for RSS trend + health events (hangs / mem-limit /
    # restarts) - these are invisible in $rc / $crashes / $exc. Backfill peak RSS
    # and iters from the log when the summary JSON is missing or partial.
    $health = Get-PhaseHealth -OutDir $OutDir
    if ($null -eq $peakRss -and $null -ne $health.PeakRssMb) { $peakRss = $health.PeakRssMb }
    if ($null -eq $iters   -and $null -ne $health.LastIter)  { $iters   = $health.LastIter }

    $needsDetail = ($rc -ne 0) -or ($crashes -gt 0) -or ($exc -gt 0)
    $findings = $null
    if ($needsDetail) { $findings = Get-PhaseFindings -OutDir $OutDir }
    if ($Tracemalloc) {
        # Gated on $Tracemalloc (the phase asked for it), not on $tracemallocLog
        # (whether the FINAL copy succeeded) - a phase that restarted and never
        # got a clean final copy can still have salvaged tracemalloc_pre_restart_*.log
        # files worth reporting. Get-TracemallocSnapshots itself no-ops cleanly
        # (Count = 0) when nothing is found in OutDir.
        if (-not $findings) { $findings = [pscustomobject]@{ CrashFiles = @(); Tracebacks = @(); Screenshots = @() } }
        $findings | Add-Member -NotePropertyName TracemallocSnapshots -NotePropertyValue (Get-TracemallocSnapshots -OutDir $OutDir) -Force
    }

    # Phase completed normally - clear the in-flight marker so the finally block
    # does not also emit a partial row for it.
    $script:CurrentPhase = $null

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
        Health      = $health
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

# ── Single-phase-only mode (-MildOnly / -ModerateOnly / -WildOnly) ──────────
# Mutually exclusive; whichever is set skips the coverage cycle (same as
# -Soak) AND both systematic sweeps, running nothing but that one chaos
# level as a single continuous soak phase.
$OnlyPhase = $null
$OnlyPhaseSwitchName = $null   # properly-cased for user-facing messages (e.g. "-WildOnly")
$_onlyPhaseSwitchCount = 0
if ($MildOnly)     { $OnlyPhase = "mild";     $OnlyPhaseSwitchName = "-MildOnly";     $_onlyPhaseSwitchCount++ }
if ($ModerateOnly) { $OnlyPhase = "moderate"; $OnlyPhaseSwitchName = "-ModerateOnly"; $_onlyPhaseSwitchCount++ }
if ($WildOnly)     { $OnlyPhase = "wild";     $OnlyPhaseSwitchName = "-WildOnly";     $_onlyPhaseSwitchCount++ }
if ($_onlyPhaseSwitchCount -gt 1) {
    Write-Host "ERROR: -MildOnly, -ModerateOnly, and -WildOnly are mutually exclusive - pick one." -ForegroundColor Red
    exit 1
}
if ($OnlyPhase) { $Soak = $true }   # implies -Soak's "skip the coverage cycle" behavior

# ── Plan-only preview (no launches, no side effects) ────────────────────────

if ($PlanOnly) {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "NetSentinel chaos test PLAN (preview only - nothing launched)" -ForegroundColor Cyan
    Write-Host ("  budget: {0}" -f $budgetLabel)
    if ($Store) {
        Write-Host "  target: Microsoft Store package (shell activation + --connect per phase)"
    } else {
        Write-Host "  target: python app.py (--source per phase)"
    }
    Write-Host "============================================================" -ForegroundColor Cyan

    $elapsed = 0.0
    $cycleNum = 0
    Write-Host ""
    if (-not $OnlyPhase) {
        Write-Host ("[cycle 0] sweep (pre)   planned {0}" -f (Format-Secs $SweepEstSecs))
        $elapsed += $SweepEstSecs
    }

    if ($OnlyPhase) {
        $remaining = $null
        if ($budgetSecs) { $remaining = $budgetSecs - $elapsed }
        $soakDurations = Get-OnlyPhaseDuration -Phase $OnlyPhase -RemainingSecs $remaining
        if ($null -eq $soakDurations) {
            Write-Host ""
            Write-Host "  budget too small for $OnlyPhaseSwitchName (need at least $MinUnitSecs seconds) - nothing to plan." -ForegroundColor Red
            exit 1
        }
        Write-Host ""
        $tmLabel = if ($Store) { "no tracemalloc (Store build)" } elseif ($Tracemalloc) { "--tracemalloc ON (-Tracemalloc)" } else { "no tracemalloc" }
        Write-Host "[single-phase mode $OnlyPhaseSwitchName] nothing but $OnlyPhase, continuous ($tmLabel), no sweeps, no restarts:" -ForegroundColor DarkCyan
        Write-Host ("    {0,-28} planned {1}" -f "Monkey $OnlyPhase (soak)", (Format-Secs $soakDurations[$OnlyPhase]))
        $elapsed += $soakDurations[$OnlyPhase]
        if ($budgetSecs) {
            Write-Host "  (single lap, sized to consume the whole budget - no closing sweep)" -ForegroundColor DarkGray
        } else {
            Write-Host "  (repeats with rotating seeds until Ctrl+C - showing lap 1 only)" -ForegroundColor DarkGray
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
        $tmLabel = if ($Store) { "no tracemalloc (Store build)" } elseif ($Tracemalloc) { "--tracemalloc ON (-Tracemalloc)" } else { "no tracemalloc" }
        Write-Host "[soak mode -Soak] straight into long-haul soak from the start - mild/moderate/wild only, continuous ($tmLabel), no restarts:" -ForegroundColor DarkCyan
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
                $tmLabel = if ($Store) { "no tracemalloc (Store build)" } elseif ($Tracemalloc) { "--tracemalloc ON (-Tracemalloc)" } else { "no tracemalloc" }
                Write-Host "[soak mode] long-haul tail after hour 1 - mild/moderate/wild only, continuous ($tmLabel), no restarts:" -ForegroundColor DarkCyan
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

$script:StoreAumid = $null
$script:StorePackageLabel = $null
if ($Store) { Resolve-StoreApp }

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
if ($Store) {
    Write-Host ("  target   : Microsoft Store package - {0}" -f $script:StorePackageLabel) -ForegroundColor Yellow
    Write-Host "             (shell activation + --connect per phase, not python app.py)" -ForegroundColor Yellow
}
if ($Soak) {
    Write-Host "  mode     : -Soak (memory soak from the start, no coverage cycle)" -ForegroundColor Yellow
} else {
    Write-Host "  NOTE: the real-mouse phase moves your actual cursor - don't" -ForegroundColor Yellow
    Write-Host "        use this PC while that phase is running." -ForegroundColor Yellow
}
Write-Host "============================================================" -ForegroundColor Cyan

$results = New-Object System.Collections.ArrayList
$script:CurrentPhase = $null   # set by Invoke-Phase while a phase is running; read by finally on Ctrl+C
$meta = [pscustomobject]@{
    Started         = $startTime.ToString("yyyy-MM-dd HH:mm:ss")
    Ended           = $null
    BudgetLabel     = $budgetLabel
    CyclesCompleted = 0
    OutRoot         = $outRoot
    Target          = if ($Store) { $script:StorePackageLabel } else { "python app.py (source)" }
}

try {
    # Initial coverage sweep - skipped entirely for -MildOnly/-ModerateOnly/
    # -WildOnly, which want nothing but the one selected chaos phase.
    $sweepArgs = @(Get-LaunchModeArgs) + @("--pause", "0.4", "--focus-interval", "1.5")
    if (-not $OnlyPhase) {
        if ($Store) { Start-StoreApp }
        $r = Invoke-Phase -CycleNum 0 -Label "Systematic sweep (pre)" -Script "tools\systematic_test.py" `
            -ScriptArgs $sweepArgs -OutDir (Join-Path $outRoot (Get-OutSub "sweep" 0 "")) `
            -Chaos $null -Seed $null -PlannedSecs $SweepEstSecs
        [void]$results.Add($r)
        Write-AiReport -ReportPath $reportPath -Meta $meta -Results $results
    }

    $cycleNum = 0
    $enterSoak = $false
    $soakDurations = $null

    if ($OnlyPhase) {
        # -MildOnly/-ModerateOnly/-WildOnly: skip the coverage cycle AND both
        # sweeps - the whole budget (or that phase's fixed lap length on an
        # indefinite budget) goes to the one selected phase alone.
        $remaining = $null
        if ($deadline) { $remaining = ($deadline - (Get-Date)).TotalSeconds }
        $soakDurations = Get-OnlyPhaseDuration -Phase $OnlyPhase -RemainingSecs $remaining
        if ($soakDurations) {
            $enterSoak = $true
        } else {
            Write-Host "  $OnlyPhaseSwitchName requested but budget too small to run - stopping." -ForegroundColor Red
        }
    } elseif ($Soak) {
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
            $scriptArgs = @(Get-LaunchModeArgs -SupportsMaxRestarts) + @("--duration", "$secs", "--focus-interval", "1.5")
            if ($def.SeedBase) {
                $seed = $def.SeedBase + $seedOffset
                $scriptArgs += @("--chaos", $def.Chaos, "--seed", "$seed", "--mem-limit", "$($def.MemLimit)")
            }

            if ($Store) { Start-StoreApp }
            $r = Invoke-Phase -CycleNum $cycleNum -Label $def.Label -Script $def.Script `
                -ScriptArgs $scriptArgs -OutDir $outDir -Chaos $def.Chaos -Seed $seed -PlannedSecs $secs
            [void]$results.Add($r)
            Write-AiReport -ReportPath $reportPath -Meta $meta -Results $results
        }

        # Closing sweep for this cycle - also serves as the opening sweep for
        # the next cycle if the budget allows another one.
        $outDir = Join-Path $outRoot (Get-OutSub "sweep" $cycleNum "")
        if ($Store) { Start-StoreApp }
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
        if ($OnlyPhase) {
            Write-Host "[soak] ${OnlyPhaseSwitchName}: nothing but $OnlyPhase - no coverage cycle, no sweeps," -ForegroundColor Cyan
        } elseif ($Soak) {
            Write-Host "[soak] -Soak: long-haul mode from the start - mild/moderate/wild only," -ForegroundColor Cyan
        } else {
            Write-Host "[soak] entering long-haul mode after coverage cycle - mild/moderate/wild only," -ForegroundColor Cyan
        }
        $tmLabel = if ($Store) { "no tracemalloc (Store build)" } elseif ($Tracemalloc) { "--tracemalloc ON (-Tracemalloc)" } else { "no tracemalloc" }
        Write-Host "       continuous ($tmLabel), no restarts between phases" -ForegroundColor Cyan
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
                # OFF unless explicitly asked for (-Tracemalloc). It used to be on
                # for every non-Store soak phase, which quietly made the memory hunt
                # worse: a 2026-08-02 A/B found tracemalloc itself CAUSED the mid-soak
                # hangs (0 hangs/0 restarts without it, vs 1-2 on every prior run,
                # cdb-confirmed stuck in tracemalloc's own traceback capture), and its
                # per-allocation cost distorts the very RSS numbers the soak exists to
                # measure. It also never found this leak - the growth is native, which
                # is why five rounds of tracemalloc saw nothing.
                $useTracemalloc = $Tracemalloc -and (-not $Store)
                $scriptArgs = @(Get-LaunchModeArgs -SupportsMaxRestarts) + @("--duration", "$secs", "--focus-interval", "1.5",
                                 "--chaos", $def.Chaos, "--seed", "$seed", "--mem-limit", "$($def.MemLimit)")
                if ($useTracemalloc) { $scriptArgs += "--tracemalloc" }
                if ($Procdump) { $scriptArgs += "--procdump" }

                if ($Store) { Start-StoreApp }
                $r = Invoke-Phase -CycleNum $coverageCycles -Label "$($def.Label) [lap $lap]" -Script $def.Script `
                    -ScriptArgs $scriptArgs -OutDir $outDir -Chaos $def.Chaos -Seed $seed `
                    -PlannedSecs $secs -Tracemalloc:$useTracemalloc
                [void]$results.Add($r)
                $meta.CyclesCompleted = "$coverageCycles (+ soak lap $lap)"
                Write-AiReport -ReportPath $reportPath -Meta $meta -Results $results
            }

            if ($deadline) {
                # Finite budget: the lap was sized to consume the rest of it -
                # close out with one final sweep, same as the old .bat suites.
                # Skipped for -MildOnly/-ModerateOnly/-WildOnly, which want no
                # sweeps at all (each has taken 25-28 min in practice - far more
                # than the nominal 5-min estimate, and would dominate the
                # runtime of a short single-phase verification run).
                if (-not $OnlyPhase) {
                    $outDir = Join-Path $outRoot (Get-OutSub "soaksweep" 0 "")
                    if ($Store) { Start-StoreApp }
                    $r = Invoke-Phase -CycleNum $coverageCycles -Label "Systematic sweep (post-soak)" -Script "tools\systematic_test.py" `
                        -ScriptArgs $sweepArgs -OutDir $outDir -Chaos $null -Seed $null -PlannedSecs $SweepEstSecs
                    [void]$results.Add($r)
                    Write-AiReport -ReportPath $reportPath -Meta $meta -Results $results
                }
                break
            }
            # Indefinite budget: repeat laps with rotating seeds until Ctrl+C -
            # no sweep between laps, so the process keeps accumulating.
        }
    }
} finally {
    # Always restore Quick Edit + sleep timeouts, even on Ctrl+C mid-run.
    if (Test-Path $setupScript) { & $setupScript -Restore }

    # If Ctrl+C (or a never-returning hang) aborted a phase mid-run, Invoke-Phase
    # never returned and its row is missing from $results - exactly the phase most
    # likely to hold the failure. Reconstruct a partial row from its log so the
    # report can't silently drop it. (This is why an earlier -Soak run looked
    # clean: the moderate soak that climbed to 1250 MB and hung was interrupted
    # and never made it into AI_REPORT.md.)
    if ($script:CurrentPhase) {
        $cp = $script:CurrentPhase
        $script:CurrentPhase = $null
        Write-Host ""
        Write-Host "[interrupted] capturing partial data for in-flight phase: $($cp.Label)" -ForegroundColor Yellow

        $findings = $null
        if ($cp.Tracemalloc) {
            # Salvage the soak phase's tracemalloc snapshots before the next launch
            # would truncate them - the memory-growth evidence lives here.
            $tmSrc = Join-Path $env:LOCALAPPDATA "NetSentinel\tracemalloc_snapshots.log"
            if (Test-Path $tmSrc) {
                $tmDest = Join-Path $cp.OutDir "tracemalloc.log"
                Copy-Item -Path $tmSrc -Destination $tmDest -Force -ErrorAction SilentlyContinue
            }
            # -OutDir (not -LogPath $tmDest): this phase may ALSO have one or more
            # tracemalloc_pre_restart_*.log files already sitting in cp.OutDir from
            # an internal MonkeyTest restart before this Ctrl+C - pick those up too.
            $findings = [pscustomobject]@{ CrashFiles = @(); Tracebacks = @(); Screenshots = @() }
            $findings | Add-Member -NotePropertyName TracemallocSnapshots -NotePropertyValue (Get-TracemallocSnapshots -OutDir $cp.OutDir) -Force
        }

        $crashes = $null; $exc = $null; $iters = $null; $focus = $null; $peak = $null
        $sp = Join-Path $cp.OutDir "monkey_summary.json"
        if (Test-Path $sp) {
            try {
                $s = Get-Content $sp -Raw | ConvertFrom-Json
                $crashes = $s.crashes; $exc = $s.exceptions_caught; $iters = $s.iterations_completed
                $focus = $s.focus_stolen_count; $peak = $s.peak_rss_mb
            } catch {
                # partial/malformed JSON (killed mid-write) - fall back to the log below
            }
        }
        $health = Get-PhaseHealth -OutDir $cp.OutDir
        if ($null -eq $peak  -and $null -ne $health.PeakRssMb) { $peak  = $health.PeakRssMb }
        if ($null -eq $iters -and $null -ne $health.LastIter)  { $iters = $health.LastIter }

        [void]$results.Add([pscustomobject]@{
            Cycle       = $cp.Cycle
            Phase       = "$($cp.Label) [INTERRUPTED]"
            Chaos       = $cp.Chaos
            Seed        = $cp.Seed
            PlannedSecs = $cp.PlannedSecs
            ActualSecs  = ((Get-Date) - $cp.T0).TotalSeconds
            ExitCode    = "INT"
            Crashes     = $crashes
            Exceptions  = $exc
            Iters       = $iters
            FocusStolen = $focus
            PeakRssMb   = $peak
            OutDir      = $cp.OutDir
            Findings    = $findings
            Health      = $health
        })
    }

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
