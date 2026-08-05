$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ExpectedHead = "TO_BE_REPLACED"
$RequiredPackage = Join-Path $env:TEMP "MTG_PreCollector_Forecast_Control_Point_Validation_v1.zip"
$RequiredHash = "f286938d3996bd2b167af138d9150cdf6ee6f5f7537df91287138b63d6006958"
$OutputDir = Join-Path $Root "artifacts\precollector\forecast_control_point_owner_review"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Forecast_Control_Point_Owner_Review_v1.zip"

function Invoke-Step([string]$Name, [scriptblock]$Action) {
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "FAILED: $Name" }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

Invoke-Step "Fetch GitHub state" { git fetch origin }
Invoke-Step "Fast-forward governed branch" { git pull --ff-only origin $ExpectedBranch }
$Branch = (git branch --show-current).Trim()
$Head = (git rev-parse HEAD).Trim()
if ($Branch -ne $ExpectedBranch) { throw "BRANCH_MISMATCH:$Branch" }
if ($Head -ne $ExpectedHead) { throw "HEAD_MISMATCH:$Head" }
Write-Host "PASS_GITHUB_HEAD_BINDING=$Head" -ForegroundColor Green

if (-not (Test-Path $RequiredPackage)) { throw "FORECAST_CONTROL_POINT_VALIDATION_PACKAGE_MISSING" }
$ActualHash = (Get-FileHash $RequiredPackage -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $RequiredHash) { throw "FORECAST_CONTROL_POINT_VALIDATION_PACKAGE_HASH_DRIFT:$ActualHash" }
Write-Host "PASS_FORECAST_CONTROL_POINT_VALIDATION_PACKAGE_BINDING=$ActualHash" -ForegroundColor Green

Invoke-Step "Forecast control point owner review tests" {
    python -m pytest tests/test_precollector_forecast_control_point_owner_review.py -q
}

if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
$env:PRECOLLECTOR_FORECAST_CONTROL_POINT_VALIDATION_PACKAGE = $RequiredPackage
Invoke-Step "Execute forecast control point owner review" {
    python scripts/review_precollector_forecast_control_point_validation.py
}

$SummaryPath = Join-Path $OutputDir "precollector_forecast_control_point_owner_review_summary.json"
if (-not (Test-Path $SummaryPath)) { throw "OWNER_REVIEW_SUMMARY_MISSING" }
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.status -ne "PASS_PRECOLLECTOR_FORECAST_CONTROL_POINT_OWNER_REVIEW") { throw "OWNER_REVIEW_STATUS_FAILED" }
if ($Summary.critical_blockers -ne 1) { throw "CRITICAL_BLOCKER_COUNT_DRIFT" }
if ($Summary.control_point_validated -ne $false) { throw "CONTROL_POINT_MUST_REMAIN_UNVALIDATED" }
if ($Summary.repair_required -ne $true) { throw "REPAIR_REQUIREMENT_MISSING" }
if ($Summary.forecast_execution_authorized -ne $false) { throw "FORECAST_AUTHORIZATION_DRIFT" }

Invoke-Step "Full repository regression suite" { python -m pytest -q }

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipHash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PRECOLLECTOR_FORECAST_CONTROL_POINT_OWNER_REVIEW_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "PRECOLLECTOR_FORECAST_CONTROL_POINT_OWNER_REVIEW_ZIP_SHA256=$ZipHash" -ForegroundColor Green

Remove-Item $OutputDir -Recurse -Force
if (Test-Path $OutputDir) { throw "TRANSIENT_OUTPUT_CLEANUP_FAILED" }
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FORECAST_CONTROL_POINT_OWNER_REVIEW" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=REPAIR_CRITICAL_FORECAST_CONTROL_POINT_BLOCKER"
Write-Host "BLOCKER_CATEGORY=$($Summary.blocker_category)"
Write-Host "CONTROL_POINT_VALIDATED=FALSE"
Write-Host "REPAIR_REQUIRED=TRUE"
Write-Host "FORECAST_EXECUTION_AUTHORIZED=FALSE"
Write-Host "RANKING_EXECUTION_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
