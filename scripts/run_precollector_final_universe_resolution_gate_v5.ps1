param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$PreCollectorArtifactsRoot = Join-Path $RepositoryRoot "artifacts\precollector"
$OutputDirectory = Join-Path $PreCollectorArtifactsRoot "final_universe_resolution"
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_Final_Universe_Owner_Review_v5.zip"

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
Invoke-GovernedStep "Final universe resolution governance tests" {
    python -m pytest -q `
        .\tests\test_precollector_scope_governance.py `
        .\tests\test_precollector_candidate_universe.py `
        .\tests\test_precollector_candidate_universe_source_binding.py `
        .\tests\test_precollector_universe_reconciliation.py `
        .\tests\test_precollector_semantic_cleanup_release_authority.py `
        .\tests\test_precollector_final_universe_resolution.py
}
Invoke-GovernedStep "Build final zero-review owner universe" { python .\scripts\build_precollector_final_universe_resolution_v5.py }

$SummaryPath = Join-Path $OutputDirectory "precollector_final_universe_resolution_summary.json"
foreach ($name in @(
    "precollector_final_universe_resolution_summary.json",
    "precollector_final_universe_resolution_manifest.json",
    "precollector_owner_approval_ready.csv",
    "precollector_owner_exclusion_recommended.csv",
    "precollector_owner_review_queue.csv",
    "precollector_fresh_delta_resolution.csv",
    "precollector_resolved_existing_universe.csv",
    "precollector_release_alias_authority.csv"
)) {
    if (-not (Test-Path (Join-Path $OutputDirectory $name))) { throw "GOVERNED_RUN_FAILED: required output missing: $name" }
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_FINAL_UNIVERSE_RESOLUTION_BUILD") { throw "GOVERNED_RUN_FAILED: summary did not certify" }
if ([int]$summary.resolved_existing_rows -ne 124) { throw "GOVERNED_RUN_FAILED: expected 124 resolved existing rows" }
if ([int]$summary.owner_approval_ready_rows -ne 124) { throw "GOVERNED_RUN_FAILED: expected all 124 existing rows owner-approval-ready" }
if ([int]$summary.existing_review_or_conflict_rows -ne 0) { throw "GOVERNED_RUN_FAILED: existing review rows remain" }
if ([int]$summary.fresh_delta_rows -ne 80) { throw "GOVERNED_RUN_FAILED: expected 80 fresh delta rows" }
if ([int]$summary.fresh_exclusion_recommended_rows -ne 80) { throw "GOVERNED_RUN_FAILED: expected all 80 fresh delta rows excluded" }
if ([int]$summary.fresh_review_rows -ne 0) { throw "GOVERNED_RUN_FAILED: fresh review rows remain" }
if ([int]$summary.unresolved_release_date_rows -ne 0) { throw "GOVERNED_RUN_FAILED: unresolved release dates remain" }
if ($summary.forecast_generation_authorized -ne $false -or $summary.ranking_execution_authorized -ne $false -or $summary.purchase_recommendation_authorized -ne $false -or $summary.automatic_purchase_execution_authorized -ne $false) { throw "GOVERNED_RUN_FAILED: downstream authorization drift" }

Write-Host "PASS_FINAL_ZERO_REVIEW_UNIVERSE_SUMMARY" -ForegroundColor Green
Write-Host "OWNER_APPROVAL_READY_ROWS=$($summary.owner_approval_ready_rows)"
Write-Host "EXISTING_REVIEW_OR_CONFLICT_ROWS=$($summary.existing_review_or_conflict_rows)"
Write-Host "FRESH_EXCLUSION_RECOMMENDED_ROWS=$($summary.fresh_exclusion_recommended_rows)"
Write-Host "FRESH_REVIEW_ROWS=$($summary.fresh_review_rows)"
Write-Host "UNRESOLVED_RELEASE_DATE_ROWS=$($summary.unresolved_release_date_rows)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) { throw "GOVERNED_RUN_FAILED: review ZIP was not created" }
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_FINAL_ZERO_REVIEW_OWNER_EXPORT" -ForegroundColor Green
Write-Host "REVIEW_ZIP=$ExportZip"
Write-Host "REVIEW_ZIP_SHA256=$zipHash"

Remove-Item $PreCollectorArtifactsRoot -Recurse -Force
Assert-CleanTree
Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FINAL_ZERO_REVIEW_UNIVERSE_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=OWNER_APPROVAL_AND_CANONICAL_UNIVERSE_FREEZE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
