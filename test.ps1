<#
.SYNOPSIS
    One-command NetSentinel chaos/monkey test runner (shim for tools\run_all_monkey_tests.ps1).

.EXAMPLE
    .\test.ps1
    Run cycles until you press Ctrl+C.

.EXAMPLE
    .\test.ps1 1h

.EXAMPLE
    .\test.ps1 20h

.EXAMPLE
    .\test.ps1 8h -Soak
    Skip the coverage cycle - spend the whole budget on the continuous memory
    soak from the start.

.EXAMPLE
    .\test.ps1 20h -PlanOnly
    Preview the plan without launching anything.

.EXAMPLE
    .\test.ps1 1h -Store
    Same coverage cycle, but against the installed Microsoft Store package
    instead of `python app.py` - launched via normal shell activation
    (shell:AppsFolder) and driven with --connect, so it exercises the exact
    startup path a real Store user takes.

.EXAMPLE
    .\test.ps1 8h -Soak -Store
    Long-haul soak against the Store package. No tracemalloc (source-only).
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Duration = "",

    [switch]$Soak,
    [switch]$PlanOnly,
    [switch]$Store,
    [switch]$Tracemalloc
)

$repoRoot = $PSScriptRoot
& (Join-Path $repoRoot "tools\run_all_monkey_tests.ps1") $Duration -Soak:$Soak -PlanOnly:$PlanOnly -Store:$Store -Tracemalloc:$Tracemalloc
exit $LASTEXITCODE
