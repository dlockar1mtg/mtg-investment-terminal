$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ArtifactsRoot = Join-Path $RepositoryRoot "artifacts\precollector"
$OutputDirectory = Join-Path $ArtifactsRoot "94_product_evidence_comparable_review"
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_94_Product_Evidence_Comparable_Review_v1.zip"

function Invoke-GovernedStep {
    param([string]$Name, [scriptblock]$Action)
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "GOVERNED_RUN_FAILED: $Name returned exit code $LASTEXITCODE"
    }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

function Assert-CleanTree {
    $status = git status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "GOVERNED_RUN_FAILED: unable to read Git status"
    }
    if ($status) {
        Write-Host $status
        throw "GOVERNED_RUN_FAILED: working tree is not clean"
    }
}

Set-Location $RepositoryRoot
Invoke-GovernedStep "Fetch GitHub state" { git fetch origin }
$currentBranch = (git branch --show-current).Trim()
if ($currentBranch -ne $ExpectedBranch) {
    throw "GOVERNED_RUN_FAILED: expected '$ExpectedBranch' but found '$currentBranch'"
}
Invoke-GovernedStep "Fast-forward governed branch" { git pull --ff-only }
Assert-CleanTree

$localCommit = (git rev-parse HEAD).Trim()
$remoteCommit = (git rev-parse "origin/$ExpectedBranch").Trim()
if ($localCommit -ne $remoteCommit) {
    throw "GOVERNED_RUN_FAILED: local commit does not equal origin branch commit"
}
Write-Host "PASS_GITHUB_COMMIT_BINDING=$localCommit" -ForegroundColor Green

if (Test-Path $ArtifactsRoot) { Remove-Item $ArtifactsRoot -Recurse -Force }
if (Test-Path $ExportZip) { Remove-Item $ExportZip -Force }

Invoke-GovernedStep "Scope governance and MTG-standard audit" {
    python .\scripts\audit_precollector_scope_governance.py
}
Invoke-GovernedStep "94-product comparable review tests" {
    python -m pytest -q `
        .\tests\test_precollector_94_product_evidence_comparable_review.py `
        .\tests\test_precollector_supply_liquidity_authority.py `
        .\tests\test_precollector_historical_price_authority_review.py
}
Invoke-GovernedStep "Build 94-product evidence and comparable review" {
    python .\scripts\build_precollector_94_product_evidence_comparable_review.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_94_product_evidence_comparable_review_summary.json"
foreach ($name in @(
    "precollector_94_product_evidence_review.csv",
    "precollector_comparable_candidate_matrix.csv",
    "precollector_owner_decision_review.csv",
    "precollector_94_product_evidence_comparable_review_summary.json",
    "precollector_94_product_evidence_comparable_review_manifest.json"
)) {
    if (-not (Test-Path (Join-Path $OutputDirectory $name))) {
        throw "GOVERNED_RUN_FAILED: required output missing: $name"
    }
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_94_PRODUCT_EVIDENCE_COMPARABLE_REVIEW_BUILD") {
    throw "GOVERNED_RUN_FAILED: review summary did not certify"
}
if ([int]$summary.final_universe_rows -ne 94) {
    throw "GOVERNED_RUN_FAILED: final universe must remain exactly 94"
}
if ([int]$summary.direct_evidence_rows -ne 67) {
    throw "GOVERNED_RUN_FAILED: direct evidence count drift"
}
if (([int]$summary.direct_evidence_rows + [int]$summary.direct_history_limited_rows + [int]$summary.comparable_product_adjusted_rows) -ne 94) {
    throw "GOVERNED_RUN_FAILED: model routes do not reconcile to 94"
}
if ([int]$summary.comparable_matrix_rows -ne 470) {
    throw "GOVERNED_RUN_FAILED: expected five comparable candidates for each of 94 products"
}
if ($summary.forecast_generation_authorized -ne $false -or $summary.ranking_execution_authorized -ne $false -or $summary.purchase_recommendation_authorized -ne $false -or $summary.automatic_purchase_execution_authorized -ne $false) {
    throw "GOVERNED_RUN_FAILED: downstream authorization drift"
}

Write-Host "PASS_PRECOLLECTOR_94_PRODUCT_EVIDENCE_COMPARABLE_REVIEW_SUMMARY" -ForegroundColor Green
Write-Host "FINAL_UNIVERSE_ROWS=$($summary.final_universe_rows)"
Write-Host "DIRECT_EVIDENCE_ROWS=$($summary.direct_evidence_rows)"
Write-Host "DIRECT_HISTORY_LIMITED_ROWS=$($summary.direct_history_limited_rows)"
Write-Host "COMPARABLE_PRODUCT_ADJUSTED_ROWS=$($summary.comparable_product_adjusted_rows)"
Write-Host "COMPARABLE_MATRIX_ROWS=$($summary.comparable_matrix_rows)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) {
    throw "GOVERNED_RUN_FAILED: review ZIP was not created"
}
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_PRECOLLECTOR_94_PRODUCT_EVIDENCE_COMPARABLE_REVIEW_EXPORT" -ForegroundColor Green
Write-Host "REVIEW_ZIP=$ExportZip"
Write-Host "REVIEW_ZIP_SHA256=$zipHash"

Remove-Item $ArtifactsRoot -Recurse -Force
Assert-CleanTree
Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_94_PRODUCT_EVIDENCE_COMPARABLE_REVIEW_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=$($summary.next_stage)"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
