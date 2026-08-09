$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredExecutionCommit = "d61b4386aec42fbbe0a44e57f678baf33ab24542"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\winner_uncertainty_certification_execution"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Winner_Uncertainty_Certification_Execution_v1.zip"

$RequiredPackages = [ordered]@{
    "MTG_PreCollector_Winner_Uncertainty_Certification_Architecture_v1.zip" = "6f27cfe24f14be57faa9ccbf7f2bd766da0832c14c8db5cd49724d49cdead08d"
    "MTG_PreCollector_Final_Champion_Control_Repair_Execution_v1.zip" = "fcdc8843f5c9ba0a1a32bea520c592da69b4018982e662ae2a2513142509ae8e"
}

function Invoke-GovernedStep {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][scriptblock]$Action)
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "GOVERNED_GATE_FAILED: $Name" }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

Set-Location $RepositoryRoot
Invoke-GovernedStep "Fetch GitHub state" { git fetch origin }
Invoke-GovernedStep "Fast-forward governed branch" { git pull --ff-only origin $ExpectedBranch }

$CurrentBranch = (git branch --show-current).Trim()
$CurrentCommit = (git rev-parse HEAD).Trim()
if ($CurrentBranch -ne $ExpectedBranch) { throw "GOVERNED_GATE_FAILED: branch drift expected=$ExpectedBranch actual=$CurrentBranch" }
git merge-base --is-ancestor $RequiredExecutionCommit $CurrentCommit
if ($LASTEXITCODE -ne 0) { throw "GOVERNED_GATE_FAILED: required execution commit is not an ancestor" }
Write-Host "PASS_GITHUB_HEAD_BINDING=$CurrentCommit" -ForegroundColor Green
Write-Host "PASS_REQUIRED_EXECUTION_ANCESTRY=$RequiredExecutionCommit" -ForegroundColor Green

foreach ($PackageName in $RequiredPackages.Keys) {
    $PackagePath = Join-Path $env:TEMP $PackageName
    if (-not (Test-Path $PackagePath)) { throw "GOVERNED_GATE_FAILED: required package missing: $PackageName" }
    $ActualHash = (Get-FileHash $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualHash -ne $RequiredPackages[$PackageName]) { throw "GOVERNED_GATE_FAILED: package hash drift: $PackageName" }
    Write-Host "PASS_PACKAGE_BINDING=$PackageName" -ForegroundColor Green
    Write-Host "PASS_PACKAGE_SHA256=$ActualHash" -ForegroundColor Green
}

Invoke-GovernedStep "Winner uncertainty execution tests" {
    python -m pytest -q tests\test_precollector_winner_uncertainty_certification_execution.py
}
Invoke-GovernedStep "Execute winner uncertainty certification" {
    python scripts\run_precollector_winner_uncertainty_certification_execution.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_winner_uncertainty_execution_summary.json"
if (-not (Test-Path $SummaryPath)) { throw "GOVERNED_GATE_FAILED: execution summary missing" }
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") { throw "GOVERNED_GATE_FAILED: certification status is not PASS" }
if ([int]$Summary.certified_winner_rows -ne 5) { throw "GOVERNED_GATE_FAILED: certified winner count drift" }
if ([int]$Summary.unresolved_no_champion_groups -ne 4) { throw "GOVERNED_GATE_FAILED: unresolved group count drift" }
if ([int]$Summary.long_horizon_monte_carlo_routes -ne 6) { throw "GOVERNED_GATE_FAILED: long-horizon route count drift" }
if ([int]$Summary.preserved_scorecard_rows -ne 90) { throw "GOVERNED_GATE_FAILED: scorecard count drift" }
if ([bool]$Summary.model_selection_reopened) { throw "GOVERNED_GATE_FAILED: model selection reopened" }
if ([bool]$Summary.prediction_recomputed) { throw "GOVERNED_GATE_FAILED: predictions recomputed" }
if ([bool]$Summary.error_recomputed) { throw "GOVERNED_GATE_FAILED: errors recomputed" }
if ([bool]$Summary.lower_uncertainty_authorized) { throw "GOVERNED_GATE_FAILED: lower uncertainty authorized" }
if ($Summary.next_stage -ne "PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_ARCHITECTURE") { throw "GOVERNED_GATE_FAILED: unexpected next stage" }

Write-Host "PASS_PRECOLLECTOR_WINNER_UNCERTAINTY_CERTIFICATION_EXECUTION_SUMMARY" -ForegroundColor Green
Write-Host "CERTIFIED_WINNER_ROWS=$($Summary.certified_winner_rows)"
Write-Host "MODERATE_UNCERTAINTY_ROWS=$($Summary.moderate_uncertainty_rows)"
Write-Host "HIGH_UNCERTAINTY_ROWS=$($Summary.high_uncertainty_rows)"
Write-Host "NOT_CERTIFIABLE_ROWS=$($Summary.not_certifiable_rows)"
Write-Host "UNRESOLVED_NO_CHAMPION_GROUPS=$($Summary.unresolved_no_champion_groups)"
Write-Host "LONG_HORIZON_MONTE_CARLO_ROUTES=$($Summary.long_horizon_monte_carlo_routes)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force
$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "WINNER_UNCERTAINTY_EXECUTION_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "WINNER_UNCERTAINTY_EXECUTION_ZIP_SHA256=$OutputHash" -ForegroundColor Green

if (Test-Path $OutputDirectory) { Remove-Item $OutputDirectory -Recurse -Force }
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) { Remove-Item $PreCollectorRoot -Force }
$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) { Write-Host $FinalStatus; throw "GOVERNED_GATE_FAILED: repository dirty after cleanup" }
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_WINNER_UNCERTAINTY_CERTIFICATION_EXECUTION" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_ARCHITECTURE"
Write-Host "MODEL_SELECTION_REOPENED=FALSE"
Write-Host "PREDICTION_RECOMPUTED=FALSE"
Write-Host "ERROR_RECOMPUTED=FALSE"
Write-Host "LOWER_UNCERTAINTY_AUTHORIZED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
