$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ExpectedCommit = "bad6d045f9cab8ec22fde4c2c0d47d3f5a63328f"
$RequiredPackageName = "MTG_PreCollector_Final_Champion_Challenge_Execution_v1.zip"
$RequiredPackageHash = "7cc9c8ec5adb4d57bf81156c00b36537ae65077dcceabe295cc1b1f8f2296ca3"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\final_champion_control_repair_architecture"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Final_Champion_Control_Repair_Architecture_v1.zip"

function Invoke-GovernedStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "GOVERNED_GATE_FAILED: $Name"
    }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

Set-Location $RepositoryRoot

Invoke-GovernedStep "Fetch GitHub state" {
    git fetch origin
}

Invoke-GovernedStep "Fast-forward governed branch" {
    git pull --ff-only origin $ExpectedBranch
}

$CurrentBranch = (git branch --show-current).Trim()
$CurrentCommit = (git rev-parse HEAD).Trim()

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "GOVERNED_GATE_FAILED: branch drift expected=$ExpectedBranch actual=$CurrentBranch"
}

if ($CurrentCommit -ne $ExpectedCommit) {
    throw "GOVERNED_GATE_FAILED: commit drift expected=$ExpectedCommit actual=$CurrentCommit"
}

Write-Host "PASS_GITHUB_COMMIT_BINDING=$CurrentCommit" -ForegroundColor Green

$PackagePath = Join-Path $env:TEMP $RequiredPackageName
if (-not (Test-Path $PackagePath)) {
    throw "GOVERNED_GATE_FAILED: required final challenge package missing"
}

$ActualPackageHash = (Get-FileHash $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualPackageHash -ne $RequiredPackageHash) {
    throw "GOVERNED_GATE_FAILED: final challenge package hash drift expected=$RequiredPackageHash actual=$ActualPackageHash"
}

Write-Host "PASS_FINAL_CHALLENGE_PACKAGE_BINDING=$ActualPackageHash" -ForegroundColor Green

Invoke-GovernedStep "Control repair architecture tests" {
    python -m pytest -q tests\test_precollector_final_champion_control_repair_architecture.py
}

Invoke-GovernedStep "Build control repair architecture" {
    python scripts\build_precollector_final_champion_control_repair_architecture.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_final_champion_control_repair_architecture_summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_GATE_FAILED: control repair architecture summary missing"
}

$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") {
    throw "GOVERNED_GATE_FAILED: architecture certification status is not PASS"
}
if ([int]$Summary.short_horizon_challenge_groups -ne 9) {
    throw "GOVERNED_GATE_FAILED: short-horizon group count drift"
}
if ([int]$Summary.frozen_candidate_rows -ne 30) {
    throw "GOVERNED_GATE_FAILED: frozen candidate count drift"
}
if ([int]$Summary.candidate_partition_scorecard_rows -ne 90) {
    throw "GOVERNED_GATE_FAILED: scorecard row count drift"
}
if ([int]$Summary.superseded_v1_decision_rows -ne 9) {
    throw "GOVERNED_GATE_FAILED: superseded decision count drift"
}
if ([bool]$Summary.candidate_set_changed) {
    throw "GOVERNED_GATE_FAILED: candidate set changed"
}
if ([bool]$Summary.fold_membership_changed) {
    throw "GOVERNED_GATE_FAILED: fold membership changed"
}
if ([bool]$Summary.prediction_recomputation_authorized) {
    throw "GOVERNED_GATE_FAILED: prediction recomputation was authorized"
}
if ([bool]$Summary.error_recomputation_authorized) {
    throw "GOVERNED_GATE_FAILED: error recomputation was authorized"
}
if ([bool]$Summary.new_tuning_authorized) {
    throw "GOVERNED_GATE_FAILED: new tuning was authorized"
}
if ($Summary.next_stage -ne "PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_CONTROL_REPAIR_EXECUTION") {
    throw "GOVERNED_GATE_FAILED: unexpected next stage"
}

Write-Host "PASS_PRECOLLECTOR_FINAL_CHAMPION_CONTROL_REPAIR_ARCHITECTURE_SUMMARY" -ForegroundColor Green
Write-Host "SHORT_HORIZON_CHALLENGE_GROUPS=$($Summary.short_horizon_challenge_groups)"
Write-Host "FROZEN_CANDIDATE_ROWS=$($Summary.frozen_candidate_rows)"
Write-Host "PRESERVED_SCORECARD_ROWS=$($Summary.candidate_partition_scorecard_rows)"
Write-Host "SUPERSEDED_V1_DECISION_ROWS=$($Summary.superseded_v1_decision_rows)"
Write-Host "LONG_HORIZON_MONTE_CARLO_ROUTES=$($Summary.long_horizon_monte_carlo_routes)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" {
    python -m pytest -q
}

if (Test-Path $OutputZip) {
    Remove-Item $OutputZip -Force
}

Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force

$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "CONTROL_REPAIR_ARCHITECTURE_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "CONTROL_REPAIR_ARCHITECTURE_ZIP_SHA256=$OutputHash" -ForegroundColor Green

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FINAL_CHAMPION_CONTROL_REPAIR_ARCHITECTURE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_CONTROL_REPAIR_EXECUTION"
Write-Host "V1_DECISIONS_SUPERSEDED_NOT_DELETED=TRUE"
Write-Host "CANDIDATE_SET_PRESERVED=TRUE"
Write-Host "PRESERVED_SCORECARD_ROWS=90"
Write-Host "PREDICTION_RECOMPUTATION_AUTHORIZED=FALSE"
Write-Host "ERROR_RECOMPUTATION_AUTHORIZED=FALSE"
Write-Host "NEW_TUNING_AUTHORIZED=FALSE"
Write-Host "LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE"
Write-Host "REQUIRED_SIMULATIONS_PER_PRODUCT_HORIZON=10000"
Write-Host "FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE"
