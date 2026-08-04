$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredExecutionCommit = "66d3fa6bf804baac7a5a1b68d6e9f1c1f8a9fe01"
$ArchitecturePackageName = "MTG_PreCollector_Final_Champion_Control_Repair_Architecture_v1.zip"
$ArchitecturePackageHash = "95a5921959089d46afb527c082f0610c012c7457106c8dda9b91c830eb9b9d40"
$FinalChallengePackageName = "MTG_PreCollector_Final_Champion_Challenge_Execution_v1.zip"
$FinalChallengePackageHash = "7cc9c8ec5adb4d57bf81156c00b36537ae65077dcceabe295cc1b1f8f2296ca3"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\final_champion_control_repair_execution"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Final_Champion_Control_Repair_Execution_v1.zip"

function Invoke-GovernedStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "GOVERNED_GATE_FAILED: $Name"
    }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

Set-Location $RepositoryRoot

Invoke-GovernedStep "Fetch GitHub state" { git fetch origin }
Invoke-GovernedStep "Fast-forward governed branch" { git pull --ff-only origin $ExpectedBranch }

$CurrentBranch = (git branch --show-current).Trim()
$CurrentCommit = (git rev-parse HEAD).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "GOVERNED_GATE_FAILED: branch drift expected=$ExpectedBranch actual=$CurrentBranch"
}
git merge-base --is-ancestor $RequiredExecutionCommit $CurrentCommit
if ($LASTEXITCODE -ne 0) {
    throw "GOVERNED_GATE_FAILED: required execution commit is not an ancestor required=$RequiredExecutionCommit actual=$CurrentCommit"
}
Write-Host "PASS_GITHUB_HEAD_BINDING=$CurrentCommit" -ForegroundColor Green
Write-Host "PASS_REQUIRED_EXECUTION_ANCESTRY=$RequiredExecutionCommit" -ForegroundColor Green

$Packages = [ordered]@{
    $ArchitecturePackageName = $ArchitecturePackageHash
    $FinalChallengePackageName = $FinalChallengePackageHash
}
foreach ($Name in $Packages.Keys) {
    $Path = Join-Path $env:TEMP $Name
    if (-not (Test-Path $Path)) {
        throw "GOVERNED_GATE_FAILED: required package missing: $Name"
    }
    $Actual = (Get-FileHash $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $Packages[$Name]) {
        throw "GOVERNED_GATE_FAILED: package hash drift name=$Name expected=$($Packages[$Name]) actual=$Actual"
    }
    Write-Host "PASS_PACKAGE_BINDING=$Name" -ForegroundColor Green
    Write-Host "PASS_PACKAGE_SHA256=$Actual" -ForegroundColor Green
}

Invoke-GovernedStep "Control repair execution tests" {
    python -m pytest -q tests\test_precollector_final_champion_control_repair_execution.py
}

Invoke-GovernedStep "Execute repaired final champion challenge" {
    python scripts\run_precollector_final_champion_control_repair_execution.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_final_champion_control_repair_execution_summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_GATE_FAILED: repaired execution summary missing"
}
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") {
    throw "GOVERNED_GATE_FAILED: repaired execution certification status is not PASS"
}
if ([int]$Summary.short_horizon_challenge_groups -ne 9) {
    throw "GOVERNED_GATE_FAILED: short-horizon group count drift"
}
if ([int]$Summary.frozen_candidate_rows -ne 30) {
    throw "GOVERNED_GATE_FAILED: frozen candidate count drift"
}
if ([int]$Summary.preserved_candidate_partition_scorecard_rows -ne 90) {
    throw "GOVERNED_GATE_FAILED: preserved scorecard count drift"
}
if ([int]$Summary.repaired_group_decision_rows -ne 9) {
    throw "GOVERNED_GATE_FAILED: repaired group decision count drift"
}
if ([int]$Summary.long_horizon_monte_carlo_routes -ne 6) {
    throw "GOVERNED_GATE_FAILED: long-horizon route count drift"
}
if ([bool]$Summary.candidate_set_changed -or [bool]$Summary.fold_membership_changed) {
    throw "GOVERNED_GATE_FAILED: governed evidence membership changed"
}
if ([bool]$Summary.prediction_recomputed -or [bool]$Summary.error_recomputed -or [bool]$Summary.new_tuning_performed) {
    throw "GOVERNED_GATE_FAILED: prohibited recomputation or tuning occurred"
}
if ($Summary.mean_signed_percentage_error_status -ne "NOT_EVALUABLE_FROM_PRESERVED_SCORECARD") {
    throw "GOVERNED_GATE_FAILED: missing evidence limitation was not preserved"
}
if ($Summary.next_stage -ne "PRECOLLECTOR_WINNER_AND_UNCERTAINTY_CERTIFICATION") {
    throw "GOVERNED_GATE_FAILED: unexpected next stage"
}

Write-Host "PASS_PRECOLLECTOR_FINAL_CHAMPION_CONTROL_REPAIR_EXECUTION_SUMMARY" -ForegroundColor Green
Write-Host "SHORT_HORIZON_CHALLENGE_GROUPS=$($Summary.short_horizon_challenge_groups)"
Write-Host "FROZEN_CANDIDATE_ROWS=$($Summary.frozen_candidate_rows)"
Write-Host "PRESERVED_SCORECARD_ROWS=$($Summary.preserved_candidate_partition_scorecard_rows)"
Write-Host "REPAIRED_SHORT_HORIZON_WINNER_ROWS=$($Summary.repaired_short_horizon_winner_rows)"
Write-Host "GOVERNED_NO_PRODUCTION_CHAMPION_ROWS=$($Summary.governed_no_production_champion_rows)"
Write-Host "LONG_HORIZON_MONTE_CARLO_ROUTES=$($Summary.long_horizon_monte_carlo_routes)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force
$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "CONTROL_REPAIR_EXECUTION_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "CONTROL_REPAIR_EXECUTION_ZIP_SHA256=$OutputHash" -ForegroundColor Green

if (Test-Path $OutputDirectory) {
    Remove-Item $OutputDirectory -Recurse -Force
}
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) {
    Remove-Item $PreCollectorRoot -Force
}
$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) {
    Write-Host $FinalStatus
    throw "GOVERNED_GATE_FAILED: repository is not clean after transient output cleanup"
}
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FINAL_CHAMPION_CONTROL_REPAIR_EXECUTION" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_WINNER_AND_UNCERTAINTY_CERTIFICATION"
Write-Host "V1_DECISIONS_SUPERSEDED_NOT_DELETED=TRUE"
Write-Host "CANDIDATE_SET_PRESERVED=TRUE"
Write-Host "PRESERVED_SCORECARD_ROWS=90"
Write-Host "PREDICTION_RECOMPUTED=FALSE"
Write-Host "ERROR_RECOMPUTED=FALSE"
Write-Host "NEW_TUNING_PERFORMED=FALSE"
Write-Host "MEAN_SIGNED_PERCENTAGE_ERROR_STATUS=NOT_EVALUABLE_FROM_PRESERVED_SCORECARD"
Write-Host "LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE"
Write-Host "REQUIRED_SIMULATIONS_PER_PRODUCT_HORIZON=10000"
Write-Host "FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE"
