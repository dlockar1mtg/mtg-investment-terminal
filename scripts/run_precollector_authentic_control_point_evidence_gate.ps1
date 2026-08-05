$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ExpectedHead = "TO_BE_REPLACED"
$RequiredPackage = Join-Path $env:TEMP "MTG_PreCollector_Recovery_Owner_Review_v1.zip"
$RequiredHash = "449020a39de6e7b7048c0204140df27ab7ef49a25f7363eab87f88df8059dd53"
$OutputDir = Join-Path $Root "artifacts\precollector\authentic_control_point_evidence"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Authentic_Control_Point_Evidence_v1.zip"

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

if (-not (Test-Path $RequiredPackage)) { throw "OWNER_REVIEW_PACKAGE_MISSING" }
$ActualHash = (Get-FileHash $RequiredPackage -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $RequiredHash) { throw "OWNER_REVIEW_PACKAGE_HASH_DRIFT:$ActualHash" }
Write-Host "PASS_OWNER_REVIEW_PACKAGE_BINDING=$ActualHash" -ForegroundColor Green

Invoke-Step "Authentic control point evidence tests" {
    python -m pytest tests/test_precollector_authentic_control_point_evidence.py -q
}

if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
$env:PRECOLLECTOR_OWNER_REVIEW_PACKAGE = $RequiredPackage
Invoke-Step "Build authentic control point evidence" {
    python scripts/build_precollector_authentic_control_point_evidence.py
}

$SummaryPath = Join-Path $OutputDir "precollector_authentic_control_point_evidence_summary.json"
if (-not (Test-Path $SummaryPath)) { throw "CONTROL_POINT_SUMMARY_MISSING" }
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.status -ne "PASS_PRECOLLECTOR_AUTHENTIC_CONTROL_POINT_EVIDENCE") { throw "CONTROL_POINT_STATUS_FAILED" }
if ($Summary.recommended_restart_stage -ne "FORECAST_CONTROL_POINT_VALIDATION") { throw "RESTART_STAGE_DRIFT" }
if ($Summary.authentic_control_point_certified -ne $false) { throw "CONTROL_POINT_MUST_REMAIN_UNCERTIFIED" }
if ($Summary.owner_approval_required -ne $true) { throw "OWNER_APPROVAL_REQUIREMENT_MISSING" }
if ($Summary.forecast_execution_authorized -ne $false) { throw "FORECAST_AUTHORIZATION_DRIFT" }

Invoke-Step "Full repository regression suite" { python -m pytest -q }

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipHash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PRECOLLECTOR_AUTHENTIC_CONTROL_POINT_EVIDENCE_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "PRECOLLECTOR_AUTHENTIC_CONTROL_POINT_EVIDENCE_ZIP_SHA256=$ZipHash" -ForegroundColor Green

Remove-Item $OutputDir -Recurse -Force
if (Test-Path $OutputDir) { throw "TRANSIENT_OUTPUT_CLEANUP_FAILED" }
Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_AUTHENTIC_CONTROL_POINT_EVIDENCE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=OWNER_APPROVAL_OR_REJECTION_OF_AUTHENTIC_PRECOLLECTOR_CONTROL_POINT"
Write-Host "RECOMMENDED_RESTART_STAGE=FORECAST_CONTROL_POINT_VALIDATION"
Write-Host "AUTHENTIC_CONTROL_POINT_CERTIFIED=FALSE"
Write-Host "OWNER_APPROVAL_REQUIRED=TRUE"
Write-Host "FORECAST_EXECUTION_AUTHORIZED=FALSE"
Write-Host "RANKING_EXECUTION_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
