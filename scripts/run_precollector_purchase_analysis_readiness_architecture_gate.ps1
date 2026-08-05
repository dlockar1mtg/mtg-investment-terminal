$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredArchitectureCommit = "301f090d606b69e4c5c8db119b830330eea3a462"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\purchase_analysis_readiness_architecture"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Purchase_Analysis_Readiness_Architecture_v1.zip"
$RequiredPackage = Join-Path $env:TEMP "MTG_PreCollector_Ranking_Execution_v1.zip"
$RequiredPackageHash = "2760613b72389bb0c4edc8c0ca737cc75988df24f7b50830d127c5f2c5b72791"

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
git merge-base --is-ancestor $RequiredArchitectureCommit $CurrentCommit
if ($LASTEXITCODE -ne 0) {
    throw "GOVERNED_GATE_FAILED: required architecture commit is not an ancestor required=$RequiredArchitectureCommit actual=$CurrentCommit"
}
Write-Host "PASS_GITHUB_HEAD_BINDING=$CurrentCommit" -ForegroundColor Green
Write-Host "PASS_REQUIRED_ARCHITECTURE_ANCESTRY=$RequiredArchitectureCommit" -ForegroundColor Green

if (-not (Test-Path $RequiredPackage)) {
    throw "GOVERNED_GATE_FAILED: ranking execution package missing"
}
$ActualPackageHash = (Get-FileHash $RequiredPackage -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualPackageHash -ne $RequiredPackageHash) {
    throw "GOVERNED_GATE_FAILED: ranking execution package hash drift expected=$RequiredPackageHash actual=$ActualPackageHash"
}
Write-Host "PASS_RANKING_EXECUTION_PACKAGE_BINDING=$ActualPackageHash" -ForegroundColor Green

Invoke-GovernedStep "Purchase analysis readiness architecture tests" {
    python -m pytest -q tests\test_precollector_purchase_analysis_readiness_architecture.py
}
Invoke-GovernedStep "Build purchase analysis readiness architecture" {
    python scripts\build_precollector_purchase_analysis_readiness_architecture.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_purchase_analysis_readiness_architecture_summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_GATE_FAILED: purchase analysis readiness summary missing"
}
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") { throw "GOVERNED_GATE_FAILED: architecture status is not PASS" }
if ([int]$Summary.governed_products -ne 50) { throw "GOVERNED_GATE_FAILED: governed product count drift" }
if ([int]$Summary.ranked_product_rows -ne 50) { throw "GOVERNED_GATE_FAILED: ranked product count drift" }
if ([int]$Summary.ranking_components -ne 6) { throw "GOVERNED_GATE_FAILED: ranking component count drift" }
if ([int]$Summary.required_purchase_analysis_dimensions -ne 8) { throw "GOVERNED_GATE_FAILED: purchase dimension count drift" }
if ([int]$Summary.required_purchase_analysis_inputs -ne 10) { throw "GOVERNED_GATE_FAILED: required input count drift" }
if ([bool]$Summary.purchase_analysis_execution_performed) { throw "GOVERNED_GATE_FAILED: purchase analysis was executed" }
if ([bool]$Summary.purchase_analysis_authorized) { throw "GOVERNED_GATE_FAILED: purchase analysis was authorized prematurely" }
if ($Summary.next_stage -ne "PRECOLLECTOR_PURCHASE_ANALYSIS_INPUT_CERTIFICATION") { throw "GOVERNED_GATE_FAILED: unexpected next stage" }

Write-Host "PASS_PRECOLLECTOR_PURCHASE_ANALYSIS_READINESS_ARCHITECTURE_SUMMARY" -ForegroundColor Green
Write-Host "GOVERNED_PRODUCTS=$($Summary.governed_products)"
Write-Host "RANKED_PRODUCT_ROWS=$($Summary.ranked_product_rows)"
Write-Host "PURCHASE_ANALYSIS_DIMENSIONS=$($Summary.required_purchase_analysis_dimensions)"
Write-Host "REQUIRED_PURCHASE_ANALYSIS_INPUTS=$($Summary.required_purchase_analysis_inputs)"
Write-Host "CURRENTLY_AVAILABLE_REQUIRED_INPUTS=$($Summary.currently_available_required_inputs)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force
$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PURCHASE_ANALYSIS_READINESS_ARCHITECTURE_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "PURCHASE_ANALYSIS_READINESS_ARCHITECTURE_ZIP_SHA256=$OutputHash" -ForegroundColor Green

if (Test-Path $OutputDirectory) { Remove-Item $OutputDirectory -Recurse -Force }
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) {
    Remove-Item $PreCollectorRoot -Force
}
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) {
    Write-Host $FinalStatus
    throw "GOVERNED_GATE_FAILED: repository is not clean after purchase analysis readiness architecture"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_PURCHASE_ANALYSIS_READINESS_ARCHITECTURE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_PURCHASE_ANALYSIS_INPUT_CERTIFICATION"
Write-Host "GOVERNED_PRODUCTS=50"
Write-Host "RANKED_PRODUCT_ROWS=50"
Write-Host "PURCHASE_ANALYSIS_DIMENSIONS=8"
Write-Host "REQUIRED_PURCHASE_ANALYSIS_INPUTS=10"
Write-Host "PURCHASE_ANALYSIS_EXECUTION_PERFORMED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
