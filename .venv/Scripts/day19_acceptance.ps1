param (
    [Parameter(Mandatory=$true)]
    [string]$RunId
)

$ErrorActionPreference = "Stop"

python -m autoops.tools.runs --help | Out-Null

Write-Host "== show =="
python -m autoops.tools.runs show $RunId

Write-Host "== replay dry-run =="
python -m autoops.tools.runs replay $RunId --dry_run

Write-Host "== replay real =="
$NewRunId = (python -m autoops.tools.runs replay $RunId | Select-Object -Last 1).Trim()

if (-not $NewRunId) {
    throw "Replay did not return NEW_RUN_ID"
}

Write-Host "NEW_RUN_ID=$NewRunId"

Write-Host "== judge =="
python -m autoops.tools.runs judge $NewRunId

Write-Host "== gate_judge =="
python -m autoops.tools.runs gate_judge $NewRunId --min_score 0.7 --max_criticals 0

Write-Host "== compare_judge =="
python -m autoops.tools.runs compare_judge $RunId $NewRunId

Write-Host "Day 19 acceptance PASSED"
