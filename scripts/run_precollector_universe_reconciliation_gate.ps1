param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\universe_reconciliation"
$CandidateOutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\candidate_universe"
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_Universe_Reconciliation.zip"

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
    if ($LASTEXITCODE -ne 0) { throw "GOVERNED_RUN_FAILED: unable to read Git status" }
    if ($status) {
        Write-Host $status
        throw "GOVERNED_RUN_FAILED: working tree is not clean"
    }
}

function Get-CountOrZero {
    param([object]$Object, [string]$Name)
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return 0 }
    return [int]$property.Value
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
if ($localCommit -ne $remoteCommit) { throw "GOVERNED_RUN_FAILED: local and remote commits differ" }
Write-Host "PASS_GITHUB_COMMIT_BINDING=$localCommit" -ForegroundColor Green

foreach ($path in @($OutputDirectory, $CandidateOutputDirectory)) {
    if (Test-Path $path) { Remove-Item $path -Recurse -Force }
}
if (Test-Path $ExportZip) { Remove-Item $ExportZip -Force }

Invoke-GovernedStep -Name "Scope governance and MTG-standard audit" -Action {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-GovernedStep -Name "Universe reconciliation governance tests" -Action {
    python -m pytest -q `
        .\tests\test_precollector_scope_governance.py `
        .\tests\test_precollector_candidate_universe.py `
        .\tests\test_precollector_candidate_universe_source_binding.py `
        .\tests\test_precollector_universe_reconciliation.py
}

Invoke-GovernedStep -Name "Fresh TCGCSV and Wizards universe reconciliation" -Action {
    python .\scripts\build_precollector_universe_reconciliation.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_universe_reconciliation_summary.json"
$ManifestPath = Join-Path $OutputDirectory "precollector_universe_reconciliation_manifest.json"
$ReconciledPath = Join-Path $OutputDirectory "precollector_reconciled_candidate_universe.csv"
foreach ($required in @($SummaryPath, $ManifestPath, $ReconciledPath)) {
    if (-not (Test-Path $required)) { throw "GOVERNED_RUN_FAILED: missing required output $required" }
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_UNIVERSE_RECONCILIATION_BUILD") {
    throw "GOVERNED_RUN_FAILED: reconciliation summary did not certify"
}
if ($summary.forecast_generation_authorized -ne $false -or
    $summary.ranking_execution_authorized -ne $false -or
    $summary.purchase_recommendation_authorized -ne $false -or
    $summary.automatic_purchase_execution_authorized -ne $false) {
    throw "GOVERNED_RUN_FAILED: downstream authorization drift detected"
}
if ([int]$summary.existing_candidate_rows -le 0 -or [int]$summary.reconciled_candidate_rows -ne [int]$summary.existing_candidate_rows) {
    throw "GOVERNED_RUN_FAILED: reconciled candidate count does not match existing candidate count"
}

$canonicalIncluded = Get-CountOrZero $summary.status_counts "CANONICAL_INCLUDED"
$sourceConflict = Get-CountOrZero $summary.status_counts "SOURCE_CONFLICT"
$dateReview = Get-CountOrZero $summary.status_counts "REQUIRES_RELEASE_DATE_REVIEW"
$formatReview = Get-CountOrZero $summary.status_counts "REQUIRES_FORMAT_REVIEW"
$duplicates = Get-CountOrZero $summary.status_counts "DUPLICATE_LISTING"

Write-Host "PASS_UNIVERSE_RECONCILIATION_SUMMARY" -ForegroundColor Green
Write-Host "EXISTING_CANDIDATES=$($summary.existing_candidate_rows)"
Write-Host "FRESH_TCGCSV_PRODUCTS=$($summary.fresh_tcgcsv_product_rows)"
Write-Host "WIZARDS_RELEASE_ROWS=$($summary.wizards_release_rows)"
Write-Host "RECONCILED_CANDIDATES=$($summary.reconciled_candidate_rows)"
Write-Host "CANONICAL_INCLUDED=$canonicalIncluded"
Write-Host "SOURCE_CONFLICT=$sourceConflict"
Write-Host "REQUIRES_RELEASE_DATE_REVIEW=$dateReview"
Write-Host "REQUIRES_FORMAT_REVIEW=$formatReview"
Write-Host "DUPLICATE_LISTING=$duplicates"
Write-Host "MISSING_FROM_AUGUST1=$($summary.missing_from_august1_rows)"
Write-Host "MISSING_FROM_FRESH_TCG=$($summary.missing_from_fresh_tcg_rows)"

Invoke-GovernedStep -Name "Full repository regression suite" -Action { python -m pytest -q }

Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) { throw "GOVERNED_RUN_FAILED: review ZIP was not created" }
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_RECONCILIATION_REVIEW_EXPORT" -ForegroundColor Green
Write-Host "REVIEW_ZIP=$ExportZip"
Write-Host "REVIEW_ZIP_SHA256=$zipHash"

foreach ($path in @($OutputDirectory, $CandidateOutputDirectory)) {
    if (Test-Path $path) { Remove-Item $path -Recurse -Force }
}
$precollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $precollectorRoot) -and -not (Get-ChildItem $precollectorRoot -Force | Select-Object -First 1)) { Remove-Item $precollectorRoot -Force }
$artifactsRoot = Join-Path $RepositoryRoot "artifacts"
if ((Test-Path $artifactsRoot) -and -not (Get-ChildItem $artifactsRoot -Force | Select-Object -First 1)) { Remove-Item $artifactsRoot -Force }
Assert-CleanTree

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_UNIVERSE_RECONCILIATION_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=OWNER_REVIEW_OF_RECONCILED_UNIVERSE_AND_SOURCE_HIERARCHY"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
