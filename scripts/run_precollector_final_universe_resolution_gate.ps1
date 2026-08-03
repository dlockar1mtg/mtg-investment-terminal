param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\final_universe_resolution"
$ArtifactsRoot = Join-Path $RepositoryRoot "artifacts"
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_Final_Universe_Owner_Review.zip"

function Invoke-GovernedStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
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

Invoke-GovernedStep -Name "Fetch GitHub state" -Action { git fetch origin }
$currentBranch = (git branch --show-current).Trim()
if ($currentBranch -ne $ExpectedBranch) {
    throw "GOVERNED_RUN_FAILED: expected '$ExpectedBranch' but found '$currentBranch'"
}
Invoke-GovernedStep -Name "Fast-forward governed branch" -Action { git pull --ff-only }
Assert-CleanTree

$localCommit = (git rev-parse HEAD).Trim()
$remoteCommit = (git rev-parse "origin/$ExpectedBranch").Trim()
if ($localCommit -ne $remoteCommit) {
    throw "GOVERNED_RUN_FAILED: local commit does not equal origin branch commit"
}
Write-Host "PASS_GITHUB_COMMIT_BINDING=$localCommit" -ForegroundColor Green

if (Test-Path $ArtifactsRoot) { Remove-Item $ArtifactsRoot -Recurse -Force }
if (Test-Path $ExportZip) { Remove-Item $ExportZip -Force }

Invoke-GovernedStep -Name "Scope governance and MTG-standard audit" -Action {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-GovernedStep -Name "Final universe resolution governance tests" -Action {
    python -m pytest -q `
        .\tests\test_precollector_scope_governance.py `
        .\tests\test_precollector_candidate_universe.py `
        .\tests\test_precollector_candidate_universe_source_binding.py `
        .\tests\test_precollector_universe_reconciliation.py `
        .\tests\test_precollector_semantic_cleanup_release_authority.py `
        .\tests\test_precollector_final_universe_resolution.py
}

Invoke-GovernedStep -Name "Build final owner-review universe resolution" -Action {
    python .\scripts\build_precollector_final_universe_resolution_v3.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_final_universe_resolution_summary.json"
$ManifestPath = Join-Path $OutputDirectory "precollector_final_universe_resolution_manifest.json"
$ReadyPath = Join-Path $OutputDirectory "precollector_owner_approval_ready.csv"
$ReviewPath = Join-Path $OutputDirectory "precollector_owner_review_queue.csv"
$ExclusionPath = Join-Path $OutputDirectory "precollector_owner_exclusion_recommended.csv"
$FreshPath = Join-Path $OutputDirectory "precollector_fresh_delta_resolution.csv"
$ResolvedPath = Join-Path $OutputDirectory "precollector_resolved_existing_universe.csv"
$AliasPath = Join-Path $OutputDirectory "precollector_release_alias_authority.csv"

foreach ($required in @($SummaryPath, $ManifestPath, $ReadyPath, $ReviewPath, $ExclusionPath, $FreshPath, $ResolvedPath, $AliasPath)) {
    if (-not (Test-Path $required)) {
        throw "GOVERNED_RUN_FAILED: required output missing: $required"
    }
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_FINAL_UNIVERSE_RESOLUTION_BUILD") {
    throw "GOVERNED_RUN_FAILED: final universe resolution summary did not certify"
}
if ($summary.forecast_generation_authorized -ne $false -or
    $summary.ranking_execution_authorized -ne $false -or
    $summary.purchase_recommendation_authorized -ne $false -or
    $summary.automatic_purchase_execution_authorized -ne $false) {
    throw "GOVERNED_RUN_FAILED: downstream authorization drift detected"
}
if ([int]$summary.resolved_existing_rows -ne 124) {
    throw "GOVERNED_RUN_FAILED: expected 124 resolved existing rows"
}
if ([int]$summary.owner_approval_ready_rows -le 0) {
    throw "GOVERNED_RUN_FAILED: no owner-approval-ready rows produced"
}
if (([int]$summary.owner_approval_ready_rows + [int]$summary.existing_review_or_conflict_rows) -ne [int]$summary.resolved_existing_rows) {
    throw "GOVERNED_RUN_FAILED: existing-universe status counts do not reconcile"
}
if (([int]$summary.fresh_exclusion_recommended_rows + [int]$summary.fresh_review_rows) -ne [int]$summary.fresh_delta_rows) {
    throw "GOVERNED_RUN_FAILED: fresh-delta status counts do not reconcile"
}

Write-Host "PASS_FINAL_UNIVERSE_RESOLUTION_SUMMARY" -ForegroundColor Green
Write-Host "RESOLVED_EXISTING_ROWS=$($summary.resolved_existing_rows)"
Write-Host "OWNER_APPROVAL_READY_ROWS=$($summary.owner_approval_ready_rows)"
Write-Host "EXISTING_REVIEW_OR_CONFLICT_ROWS=$($summary.existing_review_or_conflict_rows)"
Write-Host "FRESH_DELTA_ROWS=$($summary.fresh_delta_rows)"
Write-Host "FRESH_EXCLUSION_RECOMMENDED_ROWS=$($summary.fresh_exclusion_recommended_rows)"
Write-Host "FRESH_REVIEW_ROWS=$($summary.fresh_review_rows)"
Write-Host "UNRESOLVED_RELEASE_DATE_ROWS=$($summary.unresolved_release_date_rows)"

Invoke-GovernedStep -Name "Full repository regression suite" -Action {
    python -m pytest -q
}

Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) {
    throw "GOVERNED_RUN_FAILED: owner-review ZIP was not created"
}
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_FINAL_UNIVERSE_OWNER_REVIEW_EXPORT" -ForegroundColor Green
Write-Host "REVIEW_ZIP=$ExportZip"
Write-Host "REVIEW_ZIP_SHA256=$zipHash"

Remove-Item $ArtifactsRoot -Recurse -Force
Assert-CleanTree

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FINAL_UNIVERSE_RESOLUTION_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=OWNER_DECISION_ON_FINAL_PRECOLLECTOR_UNIVERSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
