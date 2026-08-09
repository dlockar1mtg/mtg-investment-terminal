$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ArtifactsRoot = Join-Path $RepositoryRoot "artifacts\precollector"
$OutputDirectory = Join-Path $ArtifactsRoot "supply_liquidity_authority"
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_Supply_Liquidity_Authority_v1.zip"

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
    if ($LASTEXITCODE -ne 0) { throw "GOVERNED_RUN_FAILED: unable to read Git status" }
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
Invoke-GovernedStep "Supply and liquidity authority tests" {
    python -m pytest -q `
        .\tests\test_precollector_supply_liquidity_authority.py `
        .\tests\test_precollector_historical_price_authority_review.py `
        .\tests\test_precollector_canonical_historical_prices.py `
        .\tests\test_precollector_current_price_authority_review.py `
        .\tests\test_precollector_canonical_universe_freeze.py
}
Invoke-GovernedStep "Build supply and liquidity authority" {
    python .\scripts\build_precollector_supply_liquidity_authority.py
}

$SummaryPath = Join-Path $OutputDirectory "precollector_supply_liquidity_authority_summary_v1.json"
foreach ($name in @(
    "precollector_supply_liquidity_authority_v1.csv",
    "precollector_supply_adjusted_model_eligibility_v1.csv",
    "precollector_supply_liquidity_blocked_products_v1.csv",
    "precollector_live_supply_source_coverage_v1.csv",
    "precollector_supply_liquidity_authority_summary_v1.json",
    "precollector_supply_liquidity_authority_manifest_v1.json"
)) {
    if (-not (Test-Path (Join-Path $OutputDirectory $name))) {
        throw "GOVERNED_RUN_FAILED: required output missing: $name"
    }
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_SUPPLY_LIQUIDITY_AUTHORITY_BUILD") {
    throw "GOVERNED_RUN_FAILED: supply summary did not certify"
}
if ([int]$summary.canonical_product_rows -ne 124) { throw "GOVERNED_RUN_FAILED: canonical product count drift" }
if ([int]$summary.model_input_candidate_rows -ne 94) { throw "GOVERNED_RUN_FAILED: model-input candidate count drift" }
if ([int]$summary.live_supply_product_rows -ne 94) { throw "GOVERNED_RUN_FAILED: live supply product count drift" }
if ([int]$summary.live_listing_rows -ne 7488) { throw "GOVERNED_RUN_FAILED: live listing count drift" }
if ([int]$summary.live_accepted_listing_rows -ne 936) { throw "GOVERNED_RUN_FAILED: accepted listing count drift" }
if (([int]$summary.supply_liquidity_authorized_rows + [int]$summary.supply_liquidity_blocked_rows) -ne 124) {
    throw "GOVERNED_RUN_FAILED: supply authority did not reconcile"
}
if (([int]$summary.supply_adjusted_model_input_candidate_rows + [int]$summary.supply_adjusted_model_input_blocked_rows) -ne 94) {
    throw "GOVERNED_RUN_FAILED: supply-adjusted candidate reconciliation failed"
}
if ([int]$summary.supply_adjusted_model_input_candidate_rows -le 0) {
    throw "GOVERNED_RUN_FAILED: no candidate passed supply authority"
}
if ($summary.historical_append_authorized -ne $false -or
    $summary.forecast_generation_authorized -ne $false -or
    $summary.ranking_execution_authorized -ne $false -or
    $summary.purchase_recommendation_authorized -ne $false -or
    $summary.automatic_purchase_execution_authorized -ne $false) {
    throw "GOVERNED_RUN_FAILED: downstream authorization drift"
}

Write-Host "PASS_PRECOLLECTOR_SUPPLY_LIQUIDITY_AUTHORITY_SUMMARY" -ForegroundColor Green
Write-Host "CANONICAL_PRODUCT_ROWS=$($summary.canonical_product_rows)"
Write-Host "MODEL_INPUT_CANDIDATE_ROWS=$($summary.model_input_candidate_rows)"
Write-Host "LIVE_SUPPLY_PRODUCT_ROWS=$($summary.live_supply_product_rows)"
Write-Host "LIVE_LISTING_ROWS=$($summary.live_listing_rows)"
Write-Host "LIVE_ACCEPTED_LISTING_ROWS=$($summary.live_accepted_listing_rows)"
Write-Host "LIVE_SUPPLY_IDENTITY_OVERLAP_ROWS=$($summary.live_supply_identity_overlap_rows)"
Write-Host "SUPPLY_LIQUIDITY_AUTHORIZED_ROWS=$($summary.supply_liquidity_authorized_rows)"
Write-Host "SUPPLY_LIQUIDITY_BLOCKED_ROWS=$($summary.supply_liquidity_blocked_rows)"
Write-Host "SUPPLY_ADJUSTED_MODEL_INPUT_CANDIDATE_ROWS=$($summary.supply_adjusted_model_input_candidate_rows)"
Write-Host "SUPPLY_ADJUSTED_MODEL_INPUT_BLOCKED_ROWS=$($summary.supply_adjusted_model_input_blocked_rows)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }

Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) { throw "GOVERNED_RUN_FAILED: supply authority ZIP was not created" }
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_PRECOLLECTOR_SUPPLY_LIQUIDITY_AUTHORITY_EXPORT" -ForegroundColor Green
Write-Host "SUPPLY_LIQUIDITY_ZIP=$ExportZip"
Write-Host "SUPPLY_LIQUIDITY_ZIP_SHA256=$zipHash"

Remove-Item $ArtifactsRoot -Recurse -Force
Assert-CleanTree
Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_SUPPLY_LIQUIDITY_AUTHORITY_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=$($summary.next_stage)"
Write-Host "HISTORICAL_APPEND_AUTHORIZED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
