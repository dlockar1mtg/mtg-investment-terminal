$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredArchitectureCommit = "7f93a96251d72261b44b73d52acea66a09c0607b"
$RequiredPackageName = "MTG_PreCollector_Final_Champion_Control_Repair_Execution_v1.zip"
$RequiredPackageHash = "fcdc8843f5c9ba0a1a32bea520c592da69b4018982e662ae2a2513142509ae8e"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\winner_uncertainty_certification_architecture"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Winner_Uncertainty_Certification_Architecture_v1.zip"

function Invoke-GovernedStep {
    param(
        [Parameter(Mandatory = $true)] [string]$Name,
        [Parameter(Mandatory = $true)] [scriptblock]$Action
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
git merge-base --is-ancestor $RequiredArchitectureCommit $CurrentCommit
if ($LASTEXITCODE -ne 0) {
    throw "GOVERNED_GATE_FAILED: required architecture ancestry missing required=$RequiredArchitectureCommit actual=$CurrentCommit"
}
Write-Host "PASS_GITHUB_HEAD_BINDING=$CurrentCommit" -ForegroundColor Green
Write-Host "PASS_REQUIRED_ARCHITECTURE_ANCESTRY=$RequiredArchitectureCommit" -ForegroundColor Green

$PackagePath = Join-Path $env:TEMP $RequiredPackageName
if (-not (Test-Path $PackagePath)) {
    throw "GOVERNED_GATE_FAILED: required repaired execution package missing"
}
$ActualHash = (Get-FileHash $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $RequiredPackageHash) {
    throw "GOVERNED_GATE_FAILED: repaired execution package hash drift expected=$RequiredPackageHash actual=$ActualHash"
}
Write-Host "PASS_CONTROL_REPAIR_EXECUTION_PACKAGE_BINDING=$ActualHash" -ForegroundColor Green

Invoke-GovernedStep "Winner uncertainty architecture tests" {
    python -m pytest -q tests\test_precollector_winner_uncertainty_certification_architecture.py
}

Invoke-GovernedStep "Build winner uncertainty certification architecture" {
    python scripts\build_precollector_winner_uncertainty_certification_architecture.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_winner_uncertainty_architecture_summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_GATE_FAILED: architecture summary missing"
}
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") {
    throw "GOVERNED_GATE_FAILED: architecture certification status is not PASS"
}
if ([int]$Summary.certifiable_winner_groups -ne 5) {
    throw "GOVERNED_GATE_FAILED: certifiable winner count drift"
}
if ([int]$Summary.unresolved_no_champion_groups -ne 4) {
    throw "GOVERNED_GATE_FAILED: unresolved group count drift"
}
if ([int]$Summary.long_horizon_monte_carlo_routes -ne 6) {
    throw "GOVERNED_GATE_FAILED: long-horizon route count drift"
}
if ([int]$Summary.preserved_scorecard_rows -ne 90) {
    throw "GOVERNED_GATE_FAILED: preserved scorecard count drift"
}
if ([bool]$Summary.winner_certification_execution_performed) {
    throw "GOVERNED_GATE_FAILED: winner certification was executed during architecture"
}
if ([bool]$Summary.uncertainty_certification_execution_performed) {
    throw "GOVERNED_GATE_FAILED: uncertainty certification was executed during architecture"
}
if ([bool]$Summary.model_selection_reopened) {
    throw "GOVERNED_GATE_FAILED: model selection was reopened"
}
if ([bool]$Summary.lower_uncertainty_authorized) {
    throw "GOVERNED_GATE_FAILED: lower uncertainty was improperly authorized"
}
if ($Summary.next_stage -ne "PRECOLLECTOR_WINNER_AND_UNCERTAINTY_CERTIFICATION_EXECUTION") {
    throw "GOVERNED_GATE_FAILED: unexpected next stage"
}

Write-Host "PASS_PRECOLLECTOR_WINNER_UNCERTAINTY_CERTIFICATION_ARCHITECTURE_SUMMARY" -ForegroundColor Green
Write-Host "CERTIFIABLE_WINNER_GROUPS=$($Summary.certifiable_winner_groups)"
Write-Host "UNRESOLVED_NO_CHAMPION_GROUPS=$($Summary.unresolved_no_champion_groups)"
Write-Host "LONG_HORIZON_MONTE_CARLO_ROUTES=$($Summary.long_horizon_monte_carlo_routes)"
Write-Host "PRESERVED_SCORECARD_ROWS=$($Summary.preserved_scorecard_rows)"
Write-Host "MEAN_SIGNED_PERCENTAGE_ERROR_STATUS=$($Summary.mean_signed_percentage_error_status)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force
$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "WINNER_UNCERTAINTY_ARCHITECTURE_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "WINNER_UNCERTAINTY_ARCHITECTURE_ZIP_SHA256=$OutputHash" -ForegroundColor Green

if (Test-Path $OutputDirectory) { Remove-Item $OutputDirectory -Recurse -Force }
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) {
    Remove-Item $PreCollectorRoot -Force
}
$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) {
    Write-Host $FinalStatus
    throw "GOVERNED_GATE_FAILED: repository dirty after transient cleanup"
}
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_WINNER_UNCERTAINTY_CERTIFICATION_ARCHITECTURE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_WINNER_AND_UNCERTAINTY_CERTIFICATION_EXECUTION"
Write-Host "CERTIFIABLE_WINNER_GROUPS=5"
Write-Host "UNRESOLVED_NO_CHAMPION_GROUPS=4"
Write-Host "LONG_HORIZON_MONTE_CARLO_ROUTES=6"
Write-Host "MODEL_SELECTION_REOPENED=FALSE"
Write-Host "PREDICTION_RECOMPUTATION_AUTHORIZED=FALSE"
Write-Host "ERROR_RECOMPUTATION_AUTHORIZED=FALSE"
Write-Host "LOWER_UNCERTAINTY_AUTHORIZED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
