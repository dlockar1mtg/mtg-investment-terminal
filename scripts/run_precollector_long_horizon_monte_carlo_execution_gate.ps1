$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredExecutionCommit = "1368101aea6378966ac4a42a538cc6281431512a"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\long_horizon_monte_carlo_execution"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Long_Horizon_Monte_Carlo_Execution_v1.zip"

$RequiredPackages = [ordered]@{
    "MTG_PreCollector_Long_Horizon_Monte_Carlo_Architecture_v1.zip" =
        "f77b965bc7acfe315050940e450a4ce011f194656556de06321249e551bcafc1"
    "MTG_PreCollector_Winner_Uncertainty_Certification_Execution_v1.zip" =
        "2a3385fe2f60ddda27e9d0f906cb3e87fea67945d9c0b2e79b5e3cb746837af0"
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

Invoke-GovernedStep "Long horizon Monte Carlo execution tests" {
    python -m pytest -q tests\test_precollector_long_horizon_monte_carlo_execution.py
}

Invoke-GovernedStep "Execute long horizon Monte Carlo" {
    python scripts\run_precollector_long_horizon_monte_carlo_execution.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_long_horizon_monte_carlo_execution_summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_GATE_FAILED: Monte Carlo execution summary missing"
}

$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") {
    throw "GOVERNED_GATE_FAILED: Monte Carlo execution status is not PASS"
}
if ([int]$Summary.governed_products -ne 50) {
    throw "GOVERNED_GATE_FAILED: governed product count drift"
}
if ([int]$Summary.product_horizon_rows -ne 100) {
    throw "GOVERNED_GATE_FAILED: product-horizon row count drift"
}
if ([int]$Summary.required_simulations_per_product_horizon -ne 10000) {
    throw "GOVERNED_GATE_FAILED: simulation count drift"
}
if ([int]$Summary.total_simulated_terminal_values -ne 1000000) {
    throw "GOVERNED_GATE_FAILED: total simulated terminal value count drift"
}
if ([int]$Summary.long_horizon_routes -ne 6) {
    throw "GOVERNED_GATE_FAILED: long-horizon route count drift"
}
if ([bool]$Summary.short_horizon_model_selection_reopened) {
    throw "GOVERNED_GATE_FAILED: short-horizon model selection reopened"
}
if ([bool]$Summary.short_horizon_certifications_modified) {
    throw "GOVERNED_GATE_FAILED: short-horizon certifications modified"
}
if ($Summary.next_stage -ne "PRECOLLECTOR_FORECAST_READINESS_AND_OUTPUT_ARCHITECTURE") {
    throw "GOVERNED_GATE_FAILED: unexpected next stage"
}

Write-Host "PASS_PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_EXECUTION_SUMMARY" -ForegroundColor Green
Write-Host "GOVERNED_PRODUCTS=$($Summary.governed_products)"
Write-Host "PRODUCT_HORIZON_ROWS=$($Summary.product_horizon_rows)"
Write-Host "SIMULATIONS_PER_PRODUCT_HORIZON=$($Summary.required_simulations_per_product_horizon)"
Write-Host "TOTAL_SIMULATED_TERMINAL_VALUES=$($Summary.total_simulated_terminal_values)"
Write-Host "LONG_HORIZON_ROUTES=$($Summary.long_horizon_routes)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" {
    python -m pytest -q
}

if (Test-Path $OutputZip) {
    Remove-Item $OutputZip -Force
}
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force
$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "LONG_HORIZON_MONTE_CARLO_EXECUTION_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "LONG_HORIZON_MONTE_CARLO_EXECUTION_ZIP_SHA256=$OutputHash" -ForegroundColor Green

if (Test-Path $OutputDirectory) {
    Remove-Item $OutputDirectory -Recurse -Force
}
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) {
    Remove-Item $PreCollectorRoot -Force
}
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) {
    Write-Host $FinalStatus
    throw "GOVERNED_GATE_FAILED: repository is not clean after Monte Carlo execution"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_EXECUTION" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_FORECAST_READINESS_AND_OUTPUT_ARCHITECTURE"
Write-Host "GOVERNED_PRODUCTS=50"
Write-Host "PRODUCT_HORIZON_ROWS=100"
Write-Host "SIMULATIONS_PER_PRODUCT_HORIZON=10000"
Write-Host "TOTAL_SIMULATED_TERMINAL_VALUES=1000000"
Write-Host "SHORT_HORIZON_MODEL_SELECTION_REOPENED=FALSE"
Write-Host "SHORT_HORIZON_CERTIFICATIONS_MODIFIED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
