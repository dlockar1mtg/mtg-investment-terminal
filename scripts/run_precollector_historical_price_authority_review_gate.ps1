param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ArtifactsRoot = Join-Path $RepositoryRoot "artifacts\precollector"
$OutputDirectory = Join-Path $ArtifactsRoot "historical_price_authority_review"
$ExportZip = Join-Path $env:TEMP "MTG_PreCollector_Historical_Price_Authority_Review_v1.zip"

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
Invoke-GovernedStep "Historical price authority review tests" {
    python -m pytest -q `
        .\tests\test_precollector_scope_governance.py `
        .\tests\test_precollector_canonical_universe_freeze.py `
        .\tests\test_precollector_current_price_authority_review.py `
        .\tests\test_precollector_canonical_historical_prices.py `
        .\tests\test_precollector_historical_price_authority_review.py
}
Invoke-GovernedStep "Build historical price authority review" { python .\scripts\build_precollector_historical_price_authority_review.py }

$SummaryPath = Join-Path $OutputDirectory "precollector_historical_price_authority_review_summary_v1.json"
foreach ($name in @(
    "precollector_historical_price_authority_v1.csv",
    "precollector_model_input_eligibility_v1.csv",
    "precollector_historical_price_blocked_products_v1.csv",
    "precollector_historical_price_authority_coverage_v1.csv",
    "precollector_historical_price_authority_review_summary_v1.json",
    "precollector_historical_price_authority_review_manifest_v1.json"
)) {
    if (-not (Test-Path (Join-Path $OutputDirectory $name))) { throw "GOVERNED_RUN_FAILED: required output missing: $name" }
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($summary.certification_status -ne "PASS_PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_REVIEW_BUILD") { throw "GOVERNED_RUN_FAILED: summary did not certify" }
if ([int]$summary.canonical_product_rows -ne 124) { throw "GOVERNED_RUN_FAILED: canonical product count drift" }
if ([int]$summary.canonical_historical_rows -ne 2826) { throw "GOVERNED_RUN_FAILED: canonical historical row count drift" }
if (([int]$summary.historical_price_authorized_rows + [int]$summary.historical_price_blocked_rows) -ne 124) { throw "GOVERNED_RUN_FAILED: historical authority did not reconcile" }
if (([int]$summary.current_and_history_authorized_rows + [int]$summary.current_only_rows + [int]$summary.history_only_rows + [int]$summary.neither_authorized_rows) -ne 124) { throw "GOVERNED_RUN_FAILED: combined authority matrix did not reconcile" }
if ([int]$summary.model_input_candidate_rows -ne [int]$summary.current_and_history_authorized_rows) { throw "GOVERNED_RUN_FAILED: model candidate count mismatch" }
if ($summary.historical_append_authorized -ne $false -or $summary.forecast_generation_authorized -ne $false -or $summary.ranking_execution_authorized -ne $false -or $summary.purchase_recommendation_authorized -ne $false -or $summary.automatic_purchase_execution_authorized -ne $false) { throw "GOVERNED_RUN_FAILED: downstream authorization drift" }

Write-Host "PASS_PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_REVIEW_SUMMARY" -ForegroundColor Green
Write-Host "CANONICAL_PRODUCT_ROWS=$($summary.canonical_product_rows)"
Write-Host "CANONICAL_HISTORICAL_ROWS=$($summary.canonical_historical_rows)"
Write-Host "HISTORICAL_PRICE_AUTHORIZED_ROWS=$($summary.historical_price_authorized_rows)"
Write-Host "HISTORICAL_PRICE_BLOCKED_ROWS=$($summary.historical_price_blocked_rows)"
Write-Host "CURRENT_AND_HISTORY_AUTHORIZED_ROWS=$($summary.current_and_history_authorized_rows)"
Write-Host "CURRENT_ONLY_ROWS=$($summary.current_only_rows)"
Write-Host "HISTORY_ONLY_ROWS=$($summary.history_only_rows)"
Write-Host "NEITHER_AUTHORIZED_ROWS=$($summary.neither_authorized_rows)"
Write-Host "MODEL_INPUT_CANDIDATE_ROWS=$($summary.model_input_candidate_rows)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $ExportZip -Force
if (-not (Test-Path $ExportZip)) { throw "GOVERNED_RUN_FAILED: historical authority ZIP was not created" }
$zipHash = (Get-FileHash $ExportZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_REVIEW_EXPORT" -ForegroundColor Green
Write-Host "HISTORICAL_AUTHORITY_ZIP=$ExportZip"
Write-Host "HISTORICAL_AUTHORITY_ZIP_SHA256=$zipHash"

Remove-Item $ArtifactsRoot -Recurse -Force
Assert-CleanTree
Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_REVIEW_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_SUPPLY_AND_LIQUIDITY_AUTHORITY"
Write-Host "HISTORICAL_APPEND_AUTHORIZED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
