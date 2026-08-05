$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$RequiredAncestry = "b60e819330a284d135aa82cb5a7f874a145595de"
$RequiredPackage = Join-Path $env:TEMP "MTG_PreCollector_Recovery_State_Audit_v1.zip"
$RequiredHash = "8d8ae7a32766d77ef32e67a8a96861ec553ab1fc7e2c2d903da3fe13a9bd2018"
$OutputDir = Join-Path $Root "artifacts\precollector\recovery_owner_review"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Recovery_Owner_Review_v1.zip"

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
git merge-base --is-ancestor $RequiredAncestry $Head
if ($LASTEXITCODE -ne 0) { throw "REQUIRED_ANCESTRY_MISSING:$RequiredAncestry" }
Write-Host "PASS_GITHUB_HEAD_BINDING=$Head" -ForegroundColor Green
Write-Host "PASS_REQUIRED_OWNER_REVIEW_ANCESTRY=$RequiredAncestry" -ForegroundColor Green

if (-not (Test-Path $RequiredPackage)) { throw "RECOVERY_AUDIT_PACKAGE_MISSING" }
$ActualHash = (Get-FileHash $RequiredPackage -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $RequiredHash) { throw "RECOVERY_AUDIT_PACKAGE_HASH_DRIFT:$ActualHash" }
Write-Host "PASS_RECOVERY_AUDIT_PACKAGE_BINDING=$ActualHash" -ForegroundColor Green

Invoke-Step "Recovery owner review tests" {
    python -m pytest tests/test_precollector_recovery_owner_review.py -q
}

if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
$env:PRECOLLECTOR_RECOVERY_AUDIT_PACKAGE = $RequiredPackage
Invoke-Step "Execute recovery owner review" {
    python scripts/review_precollector_recovery_state.py
}

$SummaryPath = Join-Path $OutputDir "precollector_recovery_owner_review_summary.json"
if (-not (Test-Path $SummaryPath)) { throw "OWNER_REVIEW_SUMMARY_MISSING" }
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.status -ne "PASS_PRECOLLECTOR_RECOVERY_OWNER_REVIEW") { throw "OWNER_REVIEW_STATUS_FAILED" }
if ($Summary.authentic_control_point_certified -ne $false) { throw "CONTROL_POINT_MUST_REMAIN_UNCERTIFIED" }
if ($Summary.owner_decision_required -ne $true) { throw "OWNER_DECISION_REQUIREMENT_MISSING" }
if ($Summary.forecast_execution_authorized -ne $false) { throw "FORECAST_AUTHORIZATION_DRIFT" }
if ($Summary.ranking_execution_authorized -ne $false) { throw "RANKING_AUTHORIZATION_DRIFT" }
if ($Summary.purchase_analysis_authorized -ne $false) { throw "PURCHASE_AUTHORIZATION_DRIFT" }

Invoke-Step "Full repository regression suite" { python -m pytest -q }

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipHash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PRECOLLECTOR_RECOVERY_OWNER_REVIEW_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "PRECOLLECTOR_RECOVERY_OWNER_REVIEW_ZIP_SHA256=$ZipHash" -ForegroundColor Green

Remove-Item $OutputDir -Recurse -Force
if (Test-Path $OutputDir) { throw "TRANSIENT_OUTPUT_CLEANUP_FAILED" }
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_RECOVERY_OWNER_REVIEW" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=OWNER_DECISION_ON_AUTHENTIC_PRECOLLECTOR_CONTROL_POINT"
Write-Host "AUTHENTIC_CONTROL_POINT_CERTIFIED=FALSE"
Write-Host "OWNER_DECISION_REQUIRED=TRUE"
Write-Host "FORECAST_EXECUTION_AUTHORIZED=FALSE"
Write-Host "RANKING_EXECUTION_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
