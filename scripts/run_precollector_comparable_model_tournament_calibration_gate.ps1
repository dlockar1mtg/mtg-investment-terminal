param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ArtifactsRoot = Join-Path $Root "artifacts\precollector"
$OutputDir = Join-Path $ArtifactsRoot "comparable_model_tournament_calibration"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Comparable_Model_Tournament_Calibration_v1.zip"

function Invoke-GovernedStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "GATE_FAILED:$Name"
    }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

Set-Location $Root

Invoke-GovernedStep "Fetch GitHub state" {
    git fetch origin
}

$Branch = (git branch --show-current).Trim()
if ($Branch -ne $ExpectedBranch) {
    throw "GATE_FAILED:EXPECTED_BRANCH=$ExpectedBranch;ACTUAL_BRANCH=$Branch"
}

Invoke-GovernedStep "Fast-forward governed branch" {
    git pull --ff-only origin $ExpectedBranch
}

$Commit = (git rev-parse HEAD).Trim()
Write-Host "PASS_GITHUB_COMMIT_BINDING=$Commit" -ForegroundColor Green

$StartStatus = git status --porcelain
if ($StartStatus) {
    Write-Host $StartStatus
    throw "GATE_FAILED:DIRTY_STARTING_REPOSITORY"
}

Invoke-GovernedStep "Scope governance audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-GovernedStep "Comparable model tournament tests" {
    python -m pytest .\tests\test_precollector_comparable_model_tournament_calibration.py -q
}

Invoke-GovernedStep "Build comparable model tournament and calibration" {
    python .\scripts\build_precollector_comparable_model_tournament_calibration.py
}

$SummaryPath = Join-Path $OutputDir "precollector_comparable_model_tournament_calibration_summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GATE_FAILED:SUMMARY_NOT_FOUND"
}

$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") {
    throw "GATE_FAILED:TOURNAMENT_CERTIFICATION_NOT_PASS"
}
if ([int]$Summary.active_product_rows -ne 79) {
    throw "GATE_FAILED:ACTIVE_PRODUCT_COUNT_DRIFT"
}
if ([int]$Summary.required_comparable_target_rows -ne 23) {
    throw "GATE_FAILED:REQUIRED_TARGET_COUNT_DRIFT"
}
if ([int]$Summary.approved_comparable_ledger_rows -ne 369) {
    throw "GATE_FAILED:LEDGER_COUNT_DRIFT"
}
if ([int]$Summary.candidate_model_rows -ne 4) {
    throw "GATE_FAILED:CANDIDATE_MODEL_COUNT_DRIFT"
}
if ([int]$Summary.blocking_diagnostic_rows -ne 0) {
    throw "GATE_FAILED:BLOCKING_DIAGNOSTICS_PRESENT"
}
if ($Summary.forecast_generation_authorized -ne $false) {
    throw "GATE_FAILED:FORECAST_AUTHORITY_DRIFT"
}

Write-Host "PASS_PRECOLLECTOR_COMPARABLE_MODEL_TOURNAMENT_SUMMARY" -ForegroundColor Green
Write-Host "ACTIVE_PRODUCT_ROWS=$($Summary.active_product_rows)"
Write-Host "REQUIRED_COMPARABLE_TARGET_ROWS=$($Summary.required_comparable_target_rows)"
Write-Host "APPROVED_COMPARABLE_LEDGER_ROWS=$($Summary.approved_comparable_ledger_rows)"
Write-Host "CANDIDATE_MODEL_ROWS=$($Summary.candidate_model_rows)"
Write-Host "TOURNAMENT_PREDICTION_ROWS=$($Summary.tournament_prediction_rows)"
Write-Host "SELECTED_MODEL=$($Summary.selected_model)"
Write-Host "WINNER_MEDIAN_ABSOLUTE_LOG_ERROR=$($Summary.winner_median_absolute_log_error)"
Write-Host "WINNER_P90_ABSOLUTE_LOG_ERROR=$($Summary.winner_p90_absolute_log_error)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" {
    python -m pytest -q
}

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal
if (-not (Test-Path $ZipPath)) {
    throw "GATE_FAILED:ZIP_NOT_CREATED"
}
$ZipHash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "MODEL_TOURNAMENT_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "MODEL_TOURNAMENT_ZIP_SHA256=$ZipHash" -ForegroundColor Green

if (Test-Path $ArtifactsRoot) {
    Remove-Item $ArtifactsRoot -Recurse -Force
}

$FinalStatus = git status --porcelain
if ($FinalStatus) {
    Write-Host $FinalStatus
    throw "GATE_FAILED:DIRTY_FINAL_REPOSITORY"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_COMPARABLE_MODEL_TOURNAMENT_CALIBRATION_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_FORECAST_INPUT_ASSEMBLY_AND_METHOD_CERTIFICATION" -ForegroundColor Green
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE"
