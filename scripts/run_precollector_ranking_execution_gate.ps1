$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredExecutionCommit = "30b14d2ccbfb793b657456ae51386477f67e7a3e"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\ranking_execution"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Ranking_Execution_v1.zip"

$RequiredPackages = [ordered]@{
    "MTG_PreCollector_Ranking_Readiness_Architecture_v1.zip" =
        "8f0235e32674633ef7956d0c55c6de12948a2f51d966de5b01de6bd0b476a660"
    "MTG_PreCollector_Forecast_Readiness_Output_Execution_v1.zip" =
        "27af2c4f566e87feaa51c2d75412522c8e8f939ae31192897e92a85f882791f8"
}

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
    if (-not (Test-Path $PackagePath)) {
        throw "GOVERNED_GATE_FAILED: required package missing name=$PackageName"
    }
    $ActualHash = (Get-FileHash $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $ExpectedHash = ([string]$RequiredPackages[$PackageName]).ToLowerInvariant()
    if ($ActualHash -ne $ExpectedHash) {
        throw "GOVERNED_GATE_FAILED: package hash drift name=$PackageName expected=$ExpectedHash actual=$ActualHash"
    }
    Write-Host "PASS_PACKAGE_BINDING=$PackageName" -ForegroundColor Green
    Write-Host "PASS_PACKAGE_SHA256=$ActualHash" -ForegroundColor Green
}

Invoke-GovernedStep "Ranking execution tests" {
    python -m pytest -q tests\test_precollector_ranking_execution.py
}
Invoke-GovernedStep "Execute governed rankings" {
    python scripts\run_precollector_ranking_execution.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_ranking_execution_summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_GATE_FAILED: ranking execution summary missing"
}
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") { throw "GOVERNED_GATE_FAILED: ranking execution status is not PASS" }
if ([int]$Summary.governed_products -ne 50) { throw "GOVERNED_GATE_FAILED: governed product count drift" }
if ([int]$Summary.long_horizon_output_rows -ne 100) { throw "GOVERNED_GATE_FAILED: long-horizon row count drift" }
if ([int]$Summary.ranked_product_rows -ne 50) { throw "GOVERNED_GATE_FAILED: ranked product count drift" }
if ([int]$Summary.ranking_components -ne 6) { throw "GOVERNED_GATE_FAILED: component count drift" }
if ([math]::Abs([double]$Summary.ranking_weight_sum - 1.0) -gt 0.000000001) { throw "GOVERNED_GATE_FAILED: ranking weight sum drift" }
if ([bool]$Summary.short_horizon_product_values_used) { throw "GOVERNED_GATE_FAILED: short-horizon product values were used" }
if ([bool]$Summary.forecast_recomputed) { throw "GOVERNED_GATE_FAILED: forecasts were recomputed" }
if ([bool]$Summary.monte_carlo_recomputed) { throw "GOVERNED_GATE_FAILED: Monte Carlo was recomputed" }
if ($Summary.next_stage -ne "PRECOLLECTOR_PURCHASE_ANALYSIS_READINESS_ARCHITECTURE") { throw "GOVERNED_GATE_FAILED: unexpected next stage" }

Write-Host "PASS_PRECOLLECTOR_RANKING_EXECUTION_SUMMARY" -ForegroundColor Green
Write-Host "GOVERNED_PRODUCTS=$($Summary.governed_products)"
Write-Host "LONG_HORIZON_OUTPUT_ROWS=$($Summary.long_horizon_output_rows)"
Write-Host "RANKED_PRODUCT_ROWS=$($Summary.ranked_product_rows)"
Write-Host "RANKING_COMPONENTS=$($Summary.ranking_components)"
Write-Host "RANKING_WEIGHT_SUM=$($Summary.ranking_weight_sum)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force
$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "RANKING_EXECUTION_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "RANKING_EXECUTION_ZIP_SHA256=$OutputHash" -ForegroundColor Green

if (Test-Path $OutputDirectory) { Remove-Item $OutputDirectory -Recurse -Force }
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) {
    Remove-Item $PreCollectorRoot -Force
}
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) {
    Write-Host $FinalStatus
    throw "GOVERNED_GATE_FAILED: repository is not clean after ranking execution"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_RANKING_EXECUTION" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_PURCHASE_ANALYSIS_READINESS_ARCHITECTURE"
Write-Host "GOVERNED_PRODUCTS=50"
Write-Host "LONG_HORIZON_OUTPUT_ROWS=100"
Write-Host "RANKED_PRODUCT_ROWS=50"
Write-Host "RANKING_COMPONENTS=6"
Write-Host "SHORT_HORIZON_PRODUCT_VALUES_USED=FALSE"
Write-Host "FORECAST_RECOMPUTED=FALSE"
Write-Host "MONTE_CARLO_RECOMPUTED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
