$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredCommit = "e62a2df24af2f48a7d9c0b6a479dd643d6c78357"
$RequiredPackage = Join-Path $env:TEMP "MTG_PreCollector_Authentic_Control_Point_Evidence_v1.zip"
$RequiredHash = "957713ba10cde28e875ba38fa7e1cdb8c3fe0dd6f4ce5d5949d8bf8463a2e2ee"
$OutputDir = Join-Path $Root "artifacts\precollector\forecast_control_point_validation"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Forecast_Control_Point_Validation_v1.zip"

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
git merge-base --is-ancestor $RequiredCommit $Head
if ($LASTEXITCODE -ne 0) { throw "REQUIRED_COMMIT_NOT_IN_ANCESTRY:$RequiredCommit" }
Write-Host "PASS_GITHUB_HEAD_BINDING=$Head" -ForegroundColor Green
Write-Host "PASS_REQUIRED_FORECAST_CONTROL_POINT_ANCESTRY=$RequiredCommit" -ForegroundColor Green

if (-not (Test-Path $RequiredPackage)) { throw "CONTROL_POINT_EVIDENCE_PACKAGE_MISSING" }
$ActualHash = (Get-FileHash $RequiredPackage -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $RequiredHash) { throw "CONTROL_POINT_EVIDENCE_PACKAGE_HASH_DRIFT:$ActualHash" }
Write-Host "PASS_CONTROL_POINT_EVIDENCE_PACKAGE_BINDING=$ActualHash" -ForegroundColor Green

Invoke-Step "Forecast control point validation tests" {
    python -m pytest tests/test_precollector_forecast_control_point_validation.py -q
}

if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
$env:PRECOLLECTOR_CONTROL_POINT_EVIDENCE_PACKAGE = $RequiredPackage
Invoke-Step "Execute forecast control point validation" {
    python scripts/validate_precollector_forecast_control_point.py
}

$SummaryPath = Join-Path $OutputDir "precollector_forecast_control_point_validation_summary.json"
if (-not (Test-Path $SummaryPath)) { throw "CONTROL_POINT_VALIDATION_SUMMARY_MISSING" }
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.status -ne "PASS_PRECOLLECTOR_FORECAST_CONTROL_POINT_VALIDATION") { throw "CONTROL_POINT_VALIDATION_STATUS_FAILED" }
if ($Summary.forecast_execution_authorized -ne $false) { throw "FORECAST_AUTHORIZATION_DRIFT" }
if ($Summary.ranking_execution_authorized -ne $false) { throw "RANKING_AUTHORIZATION_DRIFT" }
if ($Summary.purchase_analysis_authorized -ne $false) { throw "PURCHASE_AUTHORIZATION_DRIFT" }

Invoke-Step "Full repository regression suite" { python -m pytest -q }

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipHash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PRECOLLECTOR_FORECAST_CONTROL_POINT_VALIDATION_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "PRECOLLECTOR_FORECAST_CONTROL_POINT_VALIDATION_ZIP_SHA256=$ZipHash" -ForegroundColor Green

Remove-Item $OutputDir -Recurse -Force
if (Test-Path $OutputDir) { throw "TRANSIENT_OUTPUT_CLEANUP_FAILED" }
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FORECAST_CONTROL_POINT_VALIDATION" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=OWNER_REVIEW_OF_FORECAST_CONTROL_POINT_VALIDATION"
Write-Host "CONTROL_POINT_VALIDATED=$($Summary.control_point_validated.ToString().ToUpperInvariant())"
Write-Host "CRITICAL_BLOCKERS=$($Summary.critical_blockers)"
Write-Host "FORECAST_EXECUTION_AUTHORIZED=FALSE"
Write-Host "RANKING_EXECUTION_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
