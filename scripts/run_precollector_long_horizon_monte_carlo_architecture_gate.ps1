$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredArchitectureCommit = "2e1e1e34c25a1d1ccd287f0d833ff8de5ef90bad"
$RequiredPackageName = "MTG_PreCollector_Winner_Uncertainty_Certification_Execution_v1.zip"
$RequiredPackageHash = "2a3385fe2f60ddda27e9d0f906cb3e87fea67945d9c0b2e79b5e3cb746837af0"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\long_horizon_monte_carlo_architecture"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Long_Horizon_Monte_Carlo_Architecture_v1.zip"

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
git merge-base --is-ancestor $RequiredArchitectureCommit $CurrentCommit
if ($LASTEXITCODE -ne 0) {
    throw "GOVERNED_GATE_FAILED: required architecture commit is not an ancestor required=$RequiredArchitectureCommit actual=$CurrentCommit"
}
Write-Host "PASS_GITHUB_HEAD_BINDING=$CurrentCommit" -ForegroundColor Green
Write-Host "PASS_REQUIRED_ARCHITECTURE_ANCESTRY=$RequiredArchitectureCommit" -ForegroundColor Green

$PackagePath = Join-Path $env:TEMP $RequiredPackageName
if (-not (Test-Path $PackagePath)) {
    throw "GOVERNED_GATE_FAILED: required winner uncertainty execution package missing"
}
$ActualPackageHash = (Get-FileHash $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualPackageHash -ne $RequiredPackageHash) {
    throw "GOVERNED_GATE_FAILED: package hash drift expected=$RequiredPackageHash actual=$ActualPackageHash"
}
Write-Host "PASS_WINNER_UNCERTAINTY_EXECUTION_PACKAGE_BINDING=$ActualPackageHash" -ForegroundColor Green

Invoke-GovernedStep "Long horizon Monte Carlo architecture tests" {
    python -m pytest -q tests\test_precollector_long_horizon_monte_carlo_architecture.py
}
Invoke-GovernedStep "Build long horizon Monte Carlo architecture" {
    python scripts\build_precollector_long_horizon_monte_carlo_architecture.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_long_horizon_monte_carlo_architecture_summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_GATE_FAILED: architecture summary missing"
}
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") { throw "GOVERNED_GATE_FAILED: architecture certification status is not PASS" }
if ([int]$Summary.long_horizon_routes -ne 6) { throw "GOVERNED_GATE_FAILED: long horizon route count drift" }
if ([int]$Summary.long_horizon_horizon_codes -ne 2) { throw "GOVERNED_GATE_FAILED: horizon code count drift" }
if ([int]$Summary.required_simulations_per_product_horizon -ne 10000) { throw "GOVERNED_GATE_FAILED: simulation count drift" }
if ([bool]$Summary.monte_carlo_execution_performed) { throw "GOVERNED_GATE_FAILED: Monte Carlo execution occurred during architecture" }
if ([bool]$Summary.short_horizon_model_selection_reopened) { throw "GOVERNED_GATE_FAILED: short horizon model selection reopened" }
if ($Summary.next_stage -ne "PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_EXECUTION") { throw "GOVERNED_GATE_FAILED: unexpected next stage" }

Write-Host "PASS_PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_ARCHITECTURE_SUMMARY" -ForegroundColor Green
Write-Host "LONG_HORIZON_ROUTES=$($Summary.long_horizon_routes)"
Write-Host "LONG_HORIZON_HORIZON_CODES=$($Summary.long_horizon_horizon_codes)"
Write-Host "REQUIRED_SIMULATIONS_PER_PRODUCT_HORIZON=$($Summary.required_simulations_per_product_horizon)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force
$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "LONG_HORIZON_MONTE_CARLO_ARCHITECTURE_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "LONG_HORIZON_MONTE_CARLO_ARCHITECTURE_ZIP_SHA256=$OutputHash" -ForegroundColor Green

if (Test-Path $OutputDirectory) { Remove-Item $OutputDirectory -Recurse -Force }
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) {
    Remove-Item $PreCollectorRoot -Force
}
$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) {
    Write-Host $FinalStatus
    throw "GOVERNED_GATE_FAILED: repository is not clean after architecture certification"
}
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_ARCHITECTURE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_EXECUTION"
Write-Host "LONG_HORIZON_ROUTES=6"
Write-Host "LONG_HORIZON_HORIZON_CODES=2"
Write-Host "REQUIRED_SIMULATIONS_PER_PRODUCT_HORIZON=10000"
Write-Host "DETERMINISTIC_SEED_REGISTRY_REQUIRED=TRUE"
Write-Host "COMMON_RANDOM_NUMBERS_REQUIRED_WITHIN_PRODUCT=TRUE"
Write-Host "MONTE_CARLO_EXECUTION_PERFORMED=FALSE"
Write-Host "SHORT_HORIZON_MODEL_SELECTION_REOPENED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
