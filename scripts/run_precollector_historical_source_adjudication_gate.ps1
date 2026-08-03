param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ArtifactsRoot = Join-Path $RepositoryRoot "artifacts\precollector"
$OutputDirectory = Join-Path $ArtifactsRoot "historical_source_adjudication"
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_Historical_Source_Adjudication_v1.zip"

function Invoke-GovernedStep {
    param([string]$Name, [scriptblock]$Action)
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "GOVERNED_RUN_FAILED: $Name returned exit code $LASTEXITCODE" }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

function Assert-CleanTree {
    $status = git status --porcelain
    if ($LASTEXITCODE -ne 0) { throw "GOVERNED_RUN_FAILED: unable to read Git status" }
    if ($status) { Write-Host $status; throw "GOVERNED_RUN_FAILED: working tree is not clean" }
}

Set-Location $RepositoryRoot
Invoke-GovernedStep "Fetch GitHub state" { git fetch origin }
$currentBranch = (git branch --show-current).Trim()
if ($currentBranch -ne $ExpectedBranch) { throw "GOVERNED_RUN_FAILED: expected '$ExpectedBranch' but found '$currentBranch'" }
Invoke-GovernedStep "Fast-forward governed branch" { git pull --ff-only }
Assert-CleanTree

$localCommit = (git rev-parse HEAD).Trim()
$remoteCommit = (git rev-parse "origin/$ExpectedBranch").Trim()
if ($localCommit -ne $remoteCommit) { throw "GOVERNED_RUN_FAILED: local commit does not equal origin branch commit" }
Write-Host "PASS_GITHUB_COMMIT_BINDING=$localCommit" -ForegroundColor Green

if (Test-Path $ArtifactsRoot) { Remove-Item $ArtifactsRoot -Recurse -Force }
if (Test-Path $ExportZip) { Remove-Item $ExportZip -Force }

Invoke-GovernedStep "Scope governance and MTG-standard audit" { python .\scripts\audit_precollector_scope_governance.py }
Invoke-GovernedStep "Historical source adjudication tests" {
    python -m pytest -q `
        .\tests\test_precollector_scope_governance.py `
        .\tests\test_precollector_candidate_universe.py `
        .\tests\test_precollector_candidate_universe_source_binding.py `
        .\tests\test_precollector_universe_reconciliation.py `
        .\tests\test_precollector_semantic_cleanup_release_authority.py `
        .\tests\test_precollector_final_universe_resolution.py `
        .\tests\test_precollector_canonical_universe_freeze.py `
        .\tests\test_precollector_historical_price_evidence_inventory.py `
        .\tests\test_precollector_historical_source_adjudication.py
}
Invoke-GovernedStep "Build historical source adjudication" { python .\scripts\build_precollector_historical_source_adjudication.py }

$SummaryPath = Join-Path $OutputDirectory "precollector_historical_source_adjudication_summary_v1.json"
foreach ($name in @(
    "precollector_historical_source_adjudication_v1.csv",
    "precollector_historical_row_level_audit_v1.csv",
    "precollector_historical_adjudicated_product_coverage_v1.csv",
    "precollector_historical_source_adjudication_summary_v1.json",
    "precollector_historical_source_adjudication_manifest_v1.json"
)) {
    if (-not (Test-Path (Join-Path $OutputDirectory $name))) { throw "GOVERNED_RUN_FAILED: required output missing: $name" }
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_HISTORICAL_SOURCE_ADJUDICATION_BUILD") { throw "GOVERNED_RUN_FAILED: summary did not certify" }
if ([int]$summary.candidate_source_rows -ne 2) { throw "GOVERNED_RUN_FAILED: expected two candidate sources" }
if (([int]$summary.source_admissible_rows + [int]$summary.source_review_required_rows) -ne 2) { throw "GOVERNED_RUN_FAILED: source adjudication did not reconcile" }
if ([int]$summary.adjudicated_covered_products -gt 124) { throw "GOVERNED_RUN_FAILED: adjudicated product coverage exceeds canonical universe" }
if ($summary.historical_append_authorized -ne $false -or $summary.forecast_generation_authorized -ne $false -or $summary.ranking_execution_authorized -ne $false -or $summary.purchase_recommendation_authorized -ne $false -or $summary.automatic_purchase_execution_authorized -ne $false) { throw "GOVERNED_RUN_FAILED: downstream authorization drift" }

Write-Host "PASS_PRECOLLECTOR_HISTORICAL_SOURCE_ADJUDICATION_SUMMARY" -ForegroundColor Green
Write-Host "CANDIDATE_SOURCE_ROWS=$($summary.candidate_source_rows)"
Write-Host "SOURCE_ADMISSIBLE_ROWS=$($summary.source_admissible_rows)"
Write-Host "SOURCE_REVIEW_REQUIRED_ROWS=$($summary.source_review_required_rows)"
Write-Host "ADJUDICATED_COVERED_PRODUCTS=$($summary.adjudicated_covered_products)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) { throw "GOVERNED_RUN_FAILED: adjudication ZIP was not created" }
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_PRECOLLECTOR_HISTORICAL_SOURCE_ADJUDICATION_EXPORT" -ForegroundColor Green
Write-Host "ADJUDICATION_ZIP=$ExportZip"
Write-Host "ADJUDICATION_ZIP_SHA256=$zipHash"

Remove-Item $ArtifactsRoot -Recurse -Force
Assert-CleanTree
Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_HISTORICAL_SOURCE_ADJUDICATION_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_CANONICAL_HISTORICAL_PRICE_BUILD"
Write-Host "HISTORICAL_APPEND_AUTHORIZED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
