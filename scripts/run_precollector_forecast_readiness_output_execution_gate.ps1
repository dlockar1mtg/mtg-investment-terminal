$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredExecutionCommit = "2804d802e6986071ba1e00f42f71809c9aba981f"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\forecast_readiness_output_execution"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Forecast_Readiness_Output_Execution_v1.zip"

$RequiredPackages = [ordered]@{
    "MTG_PreCollector_Forecast_Readiness_Output_Architecture_v1.zip" =
        "f1b35a30c6689612e8d319349e1a467e109724f25d03f747a59d2a55cf5e3ac4"
    "MTG_PreCollector_Long_Horizon_Monte_Carlo_Execution_v1.zip" =
        "5e0b70ab17a166a05521015c754789275a4d287c2458213f01248c48477cbc20"
    "MTG_PreCollector_Winner_Uncertainty_Certification_Execution_v1.zip" =
        "2a3385fe2f60ddda27e9d0f906cb3e87fea67945d9c0b2e79b5e3cb746837af0"
}

function Invoke-GovernedStep {
    param([string]$Name, [scriptblock]$Action)
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
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "GOVERNED_GATE_FAILED: branch drift expected=$ExpectedBranch actual=$CurrentBranch"
}
git merge-base --is-ancestor $RequiredExecutionCommit $CurrentCommit
if ($LASTEXITCODE -ne 0) {
    throw "GOVERNED_GATE_FAILED: required execution commit is not an ancestor required=$RequiredExecutionCommit actual=$CurrentCommit"
}
Write-Host "PASS_GITHUB_HEAD_BINDING=$CurrentCommit" -ForegroundColor Green
Write-Host "PASS_REQUIRED_EXECUTION_ANCESTRY=$RequiredExecutionCommit" -ForegroundColor Green

foreach ($PackageName in $RequiredPackages.Keys) {
    $PackagePath = Join-Path $env:TEMP $PackageName
    if (-not (Test-Path $PackagePath)) { throw "GOVERNED_GATE_FAILED: required package missing name=$PackageName" }
    $ActualHash = (Get-FileHash $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $ExpectedHash = ([string]$RequiredPackages[$PackageName]).ToLowerInvariant()
    if ($ActualHash -ne $ExpectedHash) {
        throw "GOVERNED_GATE_FAILED: package hash drift name=$PackageName expected=$ExpectedHash actual=$ActualHash"
    }
    Write-Host "PASS_PACKAGE_BINDING=$PackageName" -ForegroundColor Green
    Write-Host "PASS_PACKAGE_SHA256=$ActualHash" -ForegroundColor Green
}

Invoke-GovernedStep "Forecast output execution tests" {
    python -m pytest -q tests\test_precollector_forecast_readiness_output_execution.py
}
Invoke-GovernedStep "Execute governed forecast output materialization" {
    python scripts\run_precollector_forecast_readiness_output_execution.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_forecast_output_execution_summary.json"
if (-not (Test-Path $SummaryPath)) { throw "GOVERNED_GATE_FAILED: forecast output execution summary missing" }
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") { throw "GOVERNED_GATE_FAILED: execution status is not PASS" }
if ([int]$Summary.governed_products -ne 50) { throw "GOVERNED_GATE_FAILED: governed product count drift" }
if ([int]$Summary.long_horizon_output_rows -ne 100) { throw "GOVERNED_GATE_FAILED: long-horizon output row count drift" }
if ([int]$Summary.short_horizon_certified_winners -ne 5) { throw "GOVERNED_GATE_FAILED: short-horizon winner count drift" }
if ([int]$Summary.short_horizon_unresolved_groups -ne 4) { throw "GOVERNED_GATE_FAILED: unresolved group count drift" }
if ([int]$Summary.short_horizon_scope_rows -ne 9) { throw "GOVERNED_GATE_FAILED: short-horizon scope count drift" }
if ([bool]$Summary.short_horizon_product_values_materialized) { throw "GOVERNED_GATE_FAILED: unavailable short-horizon values were materialized" }
if ([bool]$Summary.monte_carlo_recomputed) { throw "GOVERNED_GATE_FAILED: Monte Carlo was recomputed" }
if ([bool]$Summary.model_selection_reopened) { throw "GOVERNED_GATE_FAILED: model selection reopened" }
if ($Summary.next_stage -ne "PRECOLLECTOR_RANKING_READINESS_ARCHITECTURE") { throw "GOVERNED_GATE_FAILED: unexpected next stage" }

Write-Host "PASS_PRECOLLECTOR_FORECAST_READINESS_OUTPUT_EXECUTION_SUMMARY" -ForegroundColor Green
Write-Host "GOVERNED_PRODUCTS=$($Summary.governed_products)"
Write-Host "LONG_HORIZON_OUTPUT_ROWS=$($Summary.long_horizon_output_rows)"
Write-Host "SHORT_HORIZON_CERTIFIED_WINNERS=$($Summary.short_horizon_certified_winners)"
Write-Host "SHORT_HORIZON_UNRESOLVED_GROUPS=$($Summary.short_horizon_unresolved_groups)"
Write-Host "SHORT_HORIZON_PRODUCT_VALUES_MATERIALIZED=$($Summary.short_horizon_product_values_materialized.ToString().ToUpperInvariant())"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force
$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "FORECAST_READINESS_OUTPUT_EXECUTION_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "FORECAST_READINESS_OUTPUT_EXECUTION_ZIP_SHA256=$OutputHash" -ForegroundColor Green

if (Test-Path $OutputDirectory) { Remove-Item $OutputDirectory -Recurse -Force }
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) {
    Remove-Item $PreCollectorRoot -Force
}
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) {
    Write-Host $FinalStatus
    throw "GOVERNED_GATE_FAILED: repository is not clean after forecast output execution"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FORECAST_READINESS_OUTPUT_EXECUTION" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_RANKING_READINESS_ARCHITECTURE"
Write-Host "GOVERNED_PRODUCTS=50"
Write-Host "LONG_HORIZON_OUTPUT_ROWS=100"
Write-Host "SHORT_HORIZON_CERTIFIED_WINNERS=5"
Write-Host "SHORT_HORIZON_UNRESOLVED_GROUPS=4"
Write-Host "SHORT_HORIZON_PRODUCT_VALUES_MATERIALIZED=FALSE"
Write-Host "MONTE_CARLO_RECOMPUTED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
