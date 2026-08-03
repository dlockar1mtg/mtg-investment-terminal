param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\semantic_cleanup_release_authority"
$ReconciliationOutput = Join-Path $RepositoryRoot "artifacts\precollector\universe_reconciliation"
$CandidateOutput = Join-Path $RepositoryRoot "artifacts\precollector\candidate_universe"
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_Semantic_Cleanup_Release_Authority.zip"

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
        throw "GOVERNED_RUN_FAILED: unable to inspect Git status"
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
    throw "GOVERNED_RUN_FAILED: expected branch '$ExpectedBranch' but found '$currentBranch'"
}
Invoke-GovernedStep -Name "Fast-forward governed branch" -Action { git pull --ff-only }
Assert-CleanTree

$localCommit = (git rev-parse HEAD).Trim()
$remoteCommit = (git rev-parse "origin/$ExpectedBranch").Trim()
if ($localCommit -ne $remoteCommit) {
    throw "GOVERNED_RUN_FAILED: local commit does not match origin"
}
Write-Host "PASS_GITHUB_COMMIT_BINDING=$localCommit" -ForegroundColor Green

foreach ($path in @($OutputDirectory, $ReconciliationOutput, $CandidateOutput)) {
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
    }
}
if (Test-Path $ExportZip) {
    Remove-Item $ExportZip -Force
}

Invoke-GovernedStep -Name "Scope governance and MTG-standard audit" -Action {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-GovernedStep -Name "Semantic cleanup and release-authority tests" -Action {
    python -m pytest -q `
        .\tests\test_precollector_scope_governance.py `
        .\tests\test_precollector_candidate_universe.py `
        .\tests\test_precollector_candidate_universe_source_binding.py `
        .\tests\test_precollector_universe_reconciliation.py `
        .\tests\test_precollector_semantic_cleanup_release_authority.py
}

Invoke-GovernedStep -Name "Build semantic cleanup and release authority" -Action {
    python .\scripts\build_precollector_semantic_cleanup_release_authority.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_semantic_cleanup_summary.json"
$OwnerReviewPath = Join-Path $OutputDirectory "precollector_owner_review_universe.csv"
$ExcludedPath = Join-Path $OutputDirectory "precollector_excluded_configuration_review.csv"
$ReleaseAuthorityPath = Join-Path $OutputDirectory "precollector_release_date_authority.csv"
$ManifestPath = Join-Path $OutputDirectory "precollector_semantic_cleanup_manifest.json"

foreach ($required in @($SummaryPath, $OwnerReviewPath, $ExcludedPath, $ReleaseAuthorityPath, $ManifestPath)) {
    if (-not (Test-Path $required)) {
        throw "GOVERNED_RUN_FAILED: required output missing: $required"
    }
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_SEMANTIC_CLEANUP_RELEASE_AUTHORITY_BUILD") {
    throw "GOVERNED_RUN_FAILED: semantic cleanup summary did not certify"
}
if ($summary.forecast_generation_authorized -ne $false -or
    $summary.ranking_execution_authorized -ne $false -or
    $summary.purchase_recommendation_authorized -ne $false -or
    $summary.automatic_purchase_execution_authorized -ne $false) {
    throw "GOVERNED_RUN_FAILED: downstream authorization drift detected"
}
if ([int]$summary.input_reconciled_candidates -ne 186) {
    throw "GOVERNED_RUN_FAILED: reconciled candidate count drift"
}
if ([int]$summary.excluded_configurations -le 0) {
    throw "GOVERNED_RUN_FAILED: expected semantic exclusions were not produced"
}
if ([int]$summary.owner_review_rows -le 0) {
    throw "GOVERNED_RUN_FAILED: owner review universe is empty"
}

Write-Host "PASS_SEMANTIC_CLEANUP_SUMMARY" -ForegroundColor Green
Write-Host "INPUT_RECONCILED_CANDIDATES=$($summary.input_reconciled_candidates)"
Write-Host "SEMANTIC_CANDIDATES=$($summary.semantic_candidates)"
Write-Host "EXCLUDED_CONFIGURATIONS=$($summary.excluded_configurations)"
Write-Host "IDENTITY_REVIEW_ROWS=$($summary.identity_review_rows)"
Write-Host "OWNER_REVIEW_ROWS=$($summary.owner_review_rows)"
Write-Host "WIZARDS_DATE_ROWS=$($summary.wizards_date_rows)"
Write-Host "MTGJSON_SECONDARY_DATE_ROWS=$($summary.mtgjson_secondary_date_rows)"
Write-Host "RELEASE_DATE_REVIEW_ROWS=$($summary.release_date_review_rows)"
Write-Host "RELEASE_DATE_CONFLICT_ROWS=$($summary.release_date_conflict_rows)"
Write-Host "FRESH_DELTA_ROWS=$($summary.fresh_delta_rows)"

Invoke-GovernedStep -Name "Full repository regression suite" -Action {
    python -m pytest -q
}

Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) {
    throw "GOVERNED_RUN_FAILED: review ZIP was not created"
}
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_SEMANTIC_CLEANUP_REVIEW_EXPORT" -ForegroundColor Green
Write-Host "REVIEW_ZIP=$ExportZip"
Write-Host "REVIEW_ZIP_SHA256=$zipHash"

foreach ($path in @($OutputDirectory, $ReconciliationOutput, $CandidateOutput)) {
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
    }
}
$precollectorArtifacts = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $precollectorArtifacts) -and -not (Get-ChildItem $precollectorArtifacts -Force | Select-Object -First 1)) {
    Remove-Item $precollectorArtifacts -Force
}
$artifactsRoot = Join-Path $RepositoryRoot "artifacts"
if ((Test-Path $artifactsRoot) -and -not (Get-ChildItem $artifactsRoot -Force | Select-Object -First 1)) {
    Remove-Item $artifactsRoot -Force
}

Assert-CleanTree

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_SEMANTIC_CLEANUP_RELEASE_AUTHORITY_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=OWNER_REVIEW_OF_CLEANED_UNIVERSE_AND_RELEASE_AUTHORITY"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
