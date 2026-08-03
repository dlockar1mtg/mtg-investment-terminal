param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$PreCollectorArtifactsRoot = Join-Path $RepositoryRoot "artifacts\precollector"
$OutputDirectory = Join-Path $PreCollectorArtifactsRoot "current_price_authority_review"
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_Current_Price_Authority_Review_v1.zip"

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

if (Test-Path $PreCollectorArtifactsRoot) { Remove-Item $PreCollectorArtifactsRoot -Recurse -Force }
if (Test-Path $ExportZip) { Remove-Item $ExportZip -Force }

Invoke-GovernedStep "Scope governance and MTG-standard audit" { python .\scripts\audit_precollector_scope_governance.py }
Invoke-GovernedStep "Current price authority review tests" {
    python -m pytest -q `
        .\tests\test_precollector_scope_governance.py `
        .\tests\test_precollector_candidate_universe.py `
        .\tests\test_precollector_candidate_universe_source_binding.py `
        .\tests\test_precollector_universe_reconciliation.py `
        .\tests\test_precollector_semantic_cleanup_release_authority.py `
        .\tests\test_precollector_final_universe_resolution.py `
        .\tests\test_precollector_canonical_universe_freeze.py `
        .\tests\test_precollector_current_price_evidence.py `
        .\tests\test_precollector_live_current_price_collection.py `
        .\tests\test_precollector_current_price_authority_review.py
}
Invoke-GovernedStep "Build governed current price authority review" { python .\scripts\build_precollector_current_price_authority_review.py }

$SummaryPath = Join-Path $OutputDirectory "precollector_current_price_authority_review_summary_v1.json"
foreach ($name in @(
    "precollector_current_price_authority_v1.csv",
    "precollector_current_price_blocked_v1.csv",
    "precollector_current_price_blocker_summary_v1.csv",
    "precollector_current_price_authority_review_summary_v1.json",
    "precollector_current_price_authority_review_manifest_v1.json"
)) {
    if (-not (Test-Path (Join-Path $OutputDirectory $name))) { throw "GOVERNED_RUN_FAILED: required output missing: $name" }
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_CURRENT_PRICE_AUTHORITY_REVIEW_BUILD") { throw "GOVERNED_RUN_FAILED: summary did not certify" }
if ([int]$summary.canonical_product_rows -ne 124) { throw "GOVERNED_RUN_FAILED: canonical product count drift" }
if (([int]$summary.current_price_authorized_rows + [int]$summary.blocked_rows) -ne 124) { throw "GOVERNED_RUN_FAILED: authority reconciliation drift" }
if ([int]$summary.current_price_authorized_rows -le 0) { throw "GOVERNED_RUN_FAILED: no current-price authority rows" }
if ($summary.historical_append_authorized -ne $false -or $summary.forecast_generation_authorized -ne $false -or $summary.ranking_execution_authorized -ne $false -or $summary.purchase_recommendation_authorized -ne $false -or $summary.automatic_purchase_execution_authorized -ne $false) { throw "GOVERNED_RUN_FAILED: downstream authorization drift" }

Write-Host "PASS_PRECOLLECTOR_CURRENT_PRICE_AUTHORITY_REVIEW_SUMMARY" -ForegroundColor Green
Write-Host "CURRENT_PRICE_AUTHORIZED_ROWS=$($summary.current_price_authorized_rows)"
Write-Host "BLOCKED_ROWS=$($summary.blocked_rows)"
$summary.blocker_reason_counts.PSObject.Properties | Sort-Object Name | ForEach-Object {
    Write-Host "BLOCKER_$($_.Name)=$($_.Value)"
}

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) { throw "GOVERNED_RUN_FAILED: authority review ZIP was not created" }
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_PRECOLLECTOR_CURRENT_PRICE_AUTHORITY_REVIEW_EXPORT" -ForegroundColor Green
Write-Host "AUTHORITY_REVIEW_ZIP=$ExportZip"
Write-Host "AUTHORITY_REVIEW_ZIP_SHA256=$zipHash"

Remove-Item $PreCollectorArtifactsRoot -Recurse -Force
Assert-CleanTree
Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_CURRENT_PRICE_AUTHORITY_REVIEW_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY"
Write-Host "HISTORICAL_APPEND_AUTHORIZED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
