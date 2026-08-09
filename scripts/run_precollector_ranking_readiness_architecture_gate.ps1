$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredArchitectureCommit = "07600b81a675d5c6b00712bad8d8b34548e62aa0"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\ranking_readiness_architecture"
$OutputZip = Join-Path $env:TEMP "MTG_PreCollector_Ranking_Readiness_Architecture_v1.zip"
$RequiredPackageName = "MTG_PreCollector_Forecast_Readiness_Output_Execution_v1.zip"
$RequiredPackageHash = "27af2c4f566e87feaa51c2d75412522c8e8f939ae31192897e92a85f882791f8"

function Invoke-GovernedStep {
    param([Parameter(Mandatory=$true)][string]$Name,[Parameter(Mandatory=$true)][scriptblock]$Action)
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
if ($CurrentBranch -ne $ExpectedBranch) { throw "GOVERNED_GATE_FAILED: branch drift" }
git merge-base --is-ancestor $RequiredArchitectureCommit $CurrentCommit
if ($LASTEXITCODE -ne 0) { throw "GOVERNED_GATE_FAILED: required architecture ancestry missing" }
Write-Host "PASS_GITHUB_HEAD_BINDING=$CurrentCommit" -ForegroundColor Green
Write-Host "PASS_REQUIRED_ARCHITECTURE_ANCESTRY=$RequiredArchitectureCommit" -ForegroundColor Green

$PackagePath = Join-Path $env:TEMP $RequiredPackageName
if (-not (Test-Path $PackagePath)) { throw "GOVERNED_GATE_FAILED: required package missing" }
$ActualHash = (Get-FileHash $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $RequiredPackageHash) { throw "GOVERNED_GATE_FAILED: package hash drift expected=$RequiredPackageHash actual=$ActualHash" }
Write-Host "PASS_FORECAST_OUTPUT_EXECUTION_PACKAGE_BINDING=$ActualHash" -ForegroundColor Green

Invoke-GovernedStep "Ranking readiness architecture tests" {
    python -m pytest -q tests\test_precollector_ranking_readiness_architecture.py
}
Invoke-GovernedStep "Build ranking readiness architecture" {
    python scripts\build_precollector_ranking_readiness_architecture.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_ranking_readiness_architecture_summary.json"
if (-not (Test-Path $SummaryPath)) { throw "GOVERNED_GATE_FAILED: summary missing" }
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") { throw "GOVERNED_GATE_FAILED: architecture status is not PASS" }
if ([int]$Summary.governed_products -ne 50) { throw "GOVERNED_GATE_FAILED: product count drift" }
if ([int]$Summary.long_horizon_output_rows -ne 100) { throw "GOVERNED_GATE_FAILED: long-horizon row drift" }
if ([int]$Summary.ranking_components -ne 6) { throw "GOVERNED_GATE_FAILED: ranking component count drift" }
if ([math]::Abs([double]$Summary.ranking_weight_sum - 1.0) -gt 0.000000001) { throw "GOVERNED_GATE_FAILED: ranking weights invalid" }
if ([bool]$Summary.ranking_execution_performed) { throw "GOVERNED_GATE_FAILED: ranking execution occurred" }
if ($Summary.next_stage -ne "PRECOLLECTOR_RANKING_EXECUTION") { throw "GOVERNED_GATE_FAILED: unexpected next stage" }

Write-Host "PASS_PRECOLLECTOR_RANKING_READINESS_ARCHITECTURE_SUMMARY" -ForegroundColor Green
Write-Host "GOVERNED_PRODUCTS=$($Summary.governed_products)"
Write-Host "LONG_HORIZON_OUTPUT_ROWS=$($Summary.long_horizon_output_rows)"
Write-Host "RANKING_COMPONENTS=$($Summary.ranking_components)"
Write-Host "RANKING_WEIGHT_SUM=$($Summary.ranking_weight_sum)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $OutputZip -Force
$OutputHash = (Get-FileHash $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "RANKING_READINESS_ARCHITECTURE_ZIP=$OutputZip" -ForegroundColor Green
Write-Host "RANKING_READINESS_ARCHITECTURE_ZIP_SHA256=$OutputHash" -ForegroundColor Green

if (Test-Path $OutputDirectory) { Remove-Item $OutputDirectory -Recurse -Force }
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) { Remove-Item $PreCollectorRoot -Force }
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) { Write-Host $FinalStatus; throw "GOVERNED_GATE_FAILED: repository is not clean" }

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_RANKING_READINESS_ARCHITECTURE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_RANKING_EXECUTION"
Write-Host "GOVERNED_PRODUCTS=50"
Write-Host "LONG_HORIZON_OUTPUT_ROWS=100"
Write-Host "RANKING_COMPONENTS=6"
Write-Host "RANKING_WEIGHT_SUM=1.0"
Write-Host "SHORT_HORIZON_PRODUCT_VALUES_USED=FALSE"
Write-Host "RANKING_EXECUTION_PERFORMED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
