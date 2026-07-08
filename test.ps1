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
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Duration = "",

    [switch]$Soak,
    [switch]$PlanOnly
)

$repoRoot = $PSScriptRoot
& (Join-Path $repoRoot "tools\run_all_monkey_tests.ps1") $Duration -Soak:$Soak -PlanOnly:$PlanOnly
exit $LASTEXITCODE
