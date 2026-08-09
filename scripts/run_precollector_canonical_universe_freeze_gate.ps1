param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$PreCollectorArtifactsRoot = Join-Path $RepositoryRoot "artifacts\precollector"
$OutputDirectory = Join-Path $PreCollectorArtifactsRoot "canonical_universe_freeze"
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_Canonical_Universe_Freeze_v1.zip"

function Invoke-GovernedStep {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][scriptblock]$Action)
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

if (Test-Path $PreCollectorArtifactsRoot) { Remove-Item $PreCollectorArtifactsRoot -Recurse -Force }
if (Test-Path $ExportZip) { Remove-Item $ExportZip -Force }

Invoke-GovernedStep -Name "Scope governance and MTG-standard audit" -Action {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-GovernedStep -Name "Canonical universe freeze tests" -Action {
    python -m pytest -q `
        .\tests\test_precollector_scope_governance.py `
        .\tests\test_precollector_candidate_universe.py `
        .\tests\test_precollector_candidate_universe_source_binding.py `
        .\tests\test_precollector_universe_reconciliation.py `
        .\tests\test_precollector_semantic_cleanup_release_authority.py `
        .\tests\test_precollector_final_universe_resolution.py `
        .\tests\test_precollector_canonical_universe_freeze.py
}

Invoke-GovernedStep -Name "Build owner-approved canonical universe freeze" -Action {
    python .\scripts\build_precollector_canonical_universe_freeze.py
}

$RequiredFiles = @(
    "precollector_canonical_product_universe_v1.csv",
    "precollector_canonical_freeze_exclusions_v1.csv",
    "precollector_canonical_universe_freeze_summary_v1.json",
    "precollector_canonical_universe_freeze_manifest_v1.json",
    "precollector_canonical_universe_owner_approval_v1.json"
)
foreach ($name in $RequiredFiles) {
    if (-not (Test-Path (Join-Path $OutputDirectory $name))) {
        throw "GOVERNED_RUN_FAILED: required freeze output missing: $name"
    }
}

$summary = Get-Content (Join-Path $OutputDirectory "precollector_canonical_universe_freeze_summary_v1.json") -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_CANONICAL_UNIVERSE_FREEZE_BUILD") {
    throw "GOVERNED_RUN_FAILED: canonical freeze summary did not certify"
}
if ([int]$summary.canonical_product_rows -ne 124) { throw "GOVERNED_RUN_FAILED: canonical row count drift" }
if ([int]$summary.fresh_exclusion_rows -ne 80) { throw "GOVERNED_RUN_FAILED: fresh exclusion count drift" }
if ([int]$summary.unresolved_rows -ne 0) { throw "GOVERNED_RUN_FAILED: unresolved rows remain" }
if ($summary.forecast_generation_authorized -ne $false -or
    $summary.ranking_execution_authorized -ne $false -or
    $summary.purchase_recommendation_authorized -ne $false -or
    $summary.automatic_purchase_execution_authorized -ne $false) {
    throw "GOVERNED_RUN_FAILED: downstream authorization drift detected"
}

Write-Host "PASS_PRECOLLECTOR_CANONICAL_UNIVERSE_FREEZE_SUMMARY" -ForegroundColor Green
Write-Host "CANONICAL_PRODUCT_ROWS=$($summary.canonical_product_rows)"
Write-Host "FRESH_EXCLUSION_ROWS=$($summary.fresh_exclusion_rows)"
Write-Host "UNRESOLVED_ROWS=$($summary.unresolved_rows)"
Write-Host "CANONICAL_UNIVERSE_SHA256=$($summary.canonical_universe_sha256)"

Invoke-GovernedStep -Name "Full repository regression suite" -Action {
    python -m pytest -q
}

Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) { throw "GOVERNED_RUN_FAILED: freeze ZIP was not created" }
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_PRECOLLECTOR_CANONICAL_UNIVERSE_FREEZE_EXPORT" -ForegroundColor Green
Write-Host "FREEZE_ZIP=$ExportZip"
Write-Host "FREEZE_ZIP_SHA256=$zipHash"

Remove-Item $PreCollectorArtifactsRoot -Recurse -Force
Assert-CleanTree

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_CANONICAL_UNIVERSE_FREEZE_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_CURRENT_PRICE_AUTHORITY"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
