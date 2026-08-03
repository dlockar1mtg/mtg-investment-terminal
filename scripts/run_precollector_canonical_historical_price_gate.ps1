$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepositoryRoot

function Invoke-GovernedStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "GOVERNED_RUN_FAILED: $Name returned exit code $LASTEXITCODE"
    }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

Invoke-GovernedStep "Fetch GitHub state" { git fetch origin }
Invoke-GovernedStep "Fast-forward governed branch" { git pull --ff-only }
$Commit = (git rev-parse HEAD).Trim()
Write-Host "PASS_GITHUB_COMMIT_BINDING=$Commit"

Invoke-GovernedStep "Scope governance and MTG-standard audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-GovernedStep "Canonical historical price tests" {
    python -m pytest -q `
        .\tests\test_precollector_canonical_historical_prices.py `
        .\tests\test_precollector_historical_source_adjudication.py `
        .\tests\test_precollector_historical_price_evidence_inventory.py `
        .\tests\test_precollector_canonical_universe_freeze.py
}

Invoke-GovernedStep "Build canonical historical prices" {
    python .\scripts\build_precollector_canonical_historical_prices.py
}

$OutputDir = Join-Path $RepositoryRoot "artifacts\precollector\canonical_historical_prices"
$SummaryPath = Join-Path $OutputDir "precollector_canonical_historical_price_summary_v1.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_RUN_FAILED: canonical historical summary missing"
}
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS_PRECOLLECTOR_CANONICAL_HISTORICAL_PRICE_BUILD") {
    throw "GOVERNED_RUN_FAILED: canonical historical summary did not pass"
}
if (($Summary.historically_covered_products + $Summary.products_without_history) -ne 124) {
    throw "GOVERNED_RUN_FAILED: historical product reconciliation did not equal 124"
}
if ($Summary.historical_append_authorized -or $Summary.forecast_generation_authorized -or $Summary.ranking_execution_authorized -or $Summary.purchase_recommendation_authorized -or $Summary.automatic_purchase_execution_authorized) {
    throw "GOVERNED_RUN_FAILED: downstream authority enabled unexpectedly"
}
Write-Host "PASS_PRECOLLECTOR_CANONICAL_HISTORICAL_PRICE_SUMMARY"
Write-Host "CANONICAL_HISTORICAL_ROWS=$($Summary.canonical_historical_rows)"
Write-Host "HISTORICALLY_COVERED_PRODUCTS=$($Summary.historically_covered_products)"
Write-Host "HISTORY_DEPTH_ADMISSIBLE_PRODUCTS=$($Summary.history_depth_admissible_products)"
Write-Host "PRODUCTS_WITHOUT_HISTORY=$($Summary.products_without_history)"
Write-Host "DUPLICATE_SOURCE_ROWS=$($Summary.duplicate_source_rows)"
Write-Host "DUPLICATE_PRICE_CONFLICT_ROWS=$($Summary.duplicate_price_conflict_rows)"

Invoke-GovernedStep "Full repository regression suite" {
    python -m pytest -q
}

$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Canonical_Historical_Prices_v1.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $ZipPath -Force
$ZipHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_PRECOLLECTOR_CANONICAL_HISTORICAL_PRICE_EXPORT"
Write-Host "CANONICAL_HISTORY_ZIP=$ZipPath"
Write-Host "CANONICAL_HISTORY_ZIP_SHA256=$ZipHash"

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_CANONICAL_HISTORICAL_PRICE_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_REVIEW"
Write-Host "HISTORICAL_APPEND_AUTHORIZED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
