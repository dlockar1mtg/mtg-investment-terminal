$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredArchitectureCommit = "37240a3efa072458cfa7193bab6d2c6b60faa0d0"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\forecast_readiness_output_architecture"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Forecast_Readiness_Output_Architecture_v1.zip"

$RequiredPackages = [ordered]@{
    "MTG_PreCollector_Long_Horizon_Monte_Carlo_Execution_v1.zip" =
        "5e0b70ab17a166a05521015c754789275a4d287c2458213f01248c48477cbc20"
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

Invoke-GovernedStep "Forecast readiness output architecture tests" {
    python -m pytest -q tests\test_precollector_forecast_readiness_output_architecture.py
}

Invoke-GovernedStep "Build forecast readiness output architecture" {
    python scripts\build_precollector_forecast_readiness_output_architecture.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_forecast_readiness_output_architecture_summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_GATE_FAILED: forecast readiness output architecture summary missing"
}
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") {
    throw "GOVERNED_GATE_FAILED: architecture status is not PASS"
}
if ([int]$Summary.governed_products -ne 50) {
    throw "GOVERNED_GATE_FAILED: governed product count drift"
}
if ([int]$Summary.short_horizon_certified_winners -ne 5) {
    throw "GOVERNED_GATE_FAILED: certified winner count drift"
}
if ([int]$Summary.short_horizon_unresolved_groups -ne 4) {
    throw "GOVERNED_GATE_FAILED: unresolved group count drift"
}
if ([int]$Summary.long_horizon_product_horizon_rows -ne 100) {
    throw "GOVERNED_GATE_FAILED: long-horizon product row count drift"
}
if ([bool]$Summary.output_execution_performed) {
    throw "GOVERNED_GATE_FAILED: output execution occurred during architecture stage"
}
if ([bool]$Summary.ranking_execution_authorized) {
    throw "GOVERNED_GATE_FAILED: ranking execution was authorized"
}
if ([bool]$Summary.purchase_analysis_authorized) {
    throw "GOVERNED_GATE_FAILED: purchase analysis was authorized"
}
if ($Summary.next_stage -ne "PRECOLLECTOR_FORECAST_READINESS_AND_OUTPUT_EXECUTION") {
    throw "GOVERNED_GATE_FAILED: unexpected next stage"
}

Write-Host "PASS_PRECOLLECTOR_FORECAST_READINESS_OUTPUT_ARCHITECTURE_SUMMARY" -ForegroundColor Green
Write-Host "GOVERNED_PRODUCTS=$($Summary.governed_products)"
Write-Host "SHORT_HORIZON_CERTIFIED_WINNERS=$($Summary.short_horizon_certified_winners)"
Write-Host "SHORT_HORIZON_UNRESOLVED_GROUPS=$($Summary.short_horizon_unresolved_groups)"
Write-Host "LONG_HORIZON_PRODUCT_HORIZON_ROWS=$($Summary.long_horizon_product_horizon_rows)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force
$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "FORECAST_READINESS_OUTPUT_ARCHITECTURE_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "FORECAST_READINESS_OUTPUT_ARCHITECTURE_ZIP_SHA256=$OutputHash" -ForegroundColor Green

if (Test-Path $OutputDirectory) { Remove-Item $OutputDirectory -Recurse -Force }
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) {
    Remove-Item $PreCollectorRoot -Force
}
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) {
    Write-Host $FinalStatus
    throw "GOVERNED_GATE_FAILED: repository is not clean after architecture certification"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FORECAST_READINESS_OUTPUT_ARCHITECTURE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_FORECAST_READINESS_AND_OUTPUT_EXECUTION"
Write-Host "GOVERNED_PRODUCTS=50"
Write-Host "SHORT_HORIZON_CERTIFIED_WINNERS=5"
Write-Host "SHORT_HORIZON_UNRESOLVED_GROUPS=4"
Write-Host "LONG_HORIZON_PRODUCT_HORIZON_ROWS=100"
Write-Host "OUTPUT_EXECUTION_PERFORMED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
