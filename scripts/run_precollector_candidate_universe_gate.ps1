param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$OutputRelative = "artifacts\precollector\candidate_universe"
$OutputDirectory = Join-Path $RepositoryRoot $OutputRelative
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_Candidate_Universe.zip"

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

Invoke-GovernedStep -Name "Fetch GitHub state" -Action {
    git fetch origin
}

$currentBranch = (git branch --show-current).Trim()
if ($currentBranch -ne $ExpectedBranch) {
    throw "GOVERNED_RUN_FAILED: expected branch '$ExpectedBranch' but found '$currentBranch'"
}

Invoke-GovernedStep -Name "Fast-forward governed branch" -Action {
    git pull --ff-only
}

Assert-CleanTree

$localCommit = (git rev-parse HEAD).Trim()
$remoteCommit = (git rev-parse "origin/$ExpectedBranch").Trim()
if ($localCommit -ne $remoteCommit) {
    throw "GOVERNED_RUN_FAILED: local commit does not equal origin branch commit"
}
Write-Host "PASS_GITHUB_COMMIT_BINDING=$localCommit" -ForegroundColor Green

if (Test-Path $OutputDirectory) {
    Remove-Item $OutputDirectory -Recurse -Force
}
if (Test-Path $ExportZip) {
    Remove-Item $ExportZip -Force
}

Invoke-GovernedStep -Name "Scope governance and MTG-standard audit" -Action {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-GovernedStep -Name "Candidate-universe governance tests" -Action {
    python -m pytest -q `
        .\tests\test_precollector_scope_governance.py `
        .\tests\test_precollector_candidate_universe.py `
        .\tests\test_precollector_candidate_universe_source_binding.py
}

Invoke-GovernedStep -Name "Build governed candidate universe" -Action {
    python .\scripts\build_precollector_candidate_universe.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_candidate_universe_summary.json"
$InventoryPath = Join-Path $OutputDirectory "precollector_candidate_universe_inventory.csv"
$IncludedPath = Join-Path $OutputDirectory "precollector_included_candidate_universe.csv"
$ExcludedPath = Join-Path $OutputDirectory "precollector_excluded_candidate_universe.csv"
$ReviewPath = Join-Path $OutputDirectory "precollector_unresolved_review_queue.csv"
$ManifestPath = Join-Path $OutputDirectory "precollector_candidate_universe_source_manifest.json"

foreach ($required in @($SummaryPath, $InventoryPath, $IncludedPath, $ExcludedPath, $ReviewPath, $ManifestPath)) {
    if (-not (Test-Path $required)) {
        throw "GOVERNED_RUN_FAILED: required output missing: $required"
    }
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_CANDIDATE_UNIVERSE_BUILD") {
    throw "GOVERNED_RUN_FAILED: candidate universe summary did not certify"
}
if ($summary.forecast_generation_authorized -ne $false -or
    $summary.ranking_execution_authorized -ne $false -or
    $summary.purchase_recommendation_authorized -ne $false -or
    $summary.automatic_purchase_execution_authorized -ne $false) {
    throw "GOVERNED_RUN_FAILED: downstream authorization drift detected"
}
if ([int]$summary.inventory_rows -le 0) {
    throw "GOVERNED_RUN_FAILED: inventory contains no rows"
}

Write-Host "PASS_CANDIDATE_UNIVERSE_SUMMARY" -ForegroundColor Green
Write-Host "SOURCE=$($summary.source_path)"
Write-Host "SOURCE_SHA256=$($summary.source_sha256)"
Write-Host "SOURCE_ROWS=$($summary.source_rows)"
Write-Host "INVENTORY_ROWS=$($summary.inventory_rows)"
Write-Host "INCLUDED_CANDIDATES=$($summary.status_counts.INCLUDED_CANDIDATE)"
Write-Host "EXCLUDED_SCOPE=$($summary.status_counts.EXCLUDED_SCOPE)"
Write-Host "UNRESOLVED_REVIEW=$($summary.status_counts.UNRESOLVED_REVIEW)"

Invoke-GovernedStep -Name "Full repository regression suite" -Action {
    python -m pytest -q
}

Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) {
    throw "GOVERNED_RUN_FAILED: review ZIP was not created"
}
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_REVIEW_ARTIFACT_EXPORT" -ForegroundColor Green
Write-Host "REVIEW_ZIP=$ExportZip"
Write-Host "REVIEW_ZIP_SHA256=$zipHash"

Remove-Item $OutputDirectory -Recurse -Force
$artifactRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $artifactRoot) -and -not (Get-ChildItem $artifactRoot -Force | Select-Object -First 1)) {
    Remove-Item $artifactRoot -Force
}
$artifactsRoot = Join-Path $RepositoryRoot "artifacts"
if ((Test-Path $artifactsRoot) -and -not (Get-ChildItem $artifactsRoot -Force | Select-Object -First 1)) {
    Remove-Item $artifactsRoot -Force
}

Assert-CleanTree

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_CANDIDATE_UNIVERSE_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=OWNER_REVIEW_AND_SOURCE_HIERARCHY_DECISION"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
