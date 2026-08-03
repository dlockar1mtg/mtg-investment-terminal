param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function Invoke-Checked {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Command
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

Invoke-Checked "Fetch GitHub state" { git fetch origin }
Invoke-Checked "Fast-forward governed branch" { git pull --ff-only }
$Commit = (git rev-parse HEAD).Trim()
Write-Host "PASS_GITHUB_COMMIT_BINDING=$Commit"
Assert-CleanTree

Invoke-Checked "Scope governance and MTG-standard audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-Checked "Live supply collection tests" {
    python -m pytest .\tests\test_precollector_live_supply_collection.py -q
}

Invoke-Checked "Build fresh Pre-Collector live supply collection" {
    python .\scripts\build_precollector_live_supply_collection.py
}

$SummaryPath = ".\artifacts\precollector\live_supply_collection\precollector_live_supply_collection_summary_v1.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_RUN_FAILED: live supply collection summary missing"
}
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS_PRECOLLECTOR_LIVE_SUPPLY_COLLECTION_BUILD") {
    throw "GOVERNED_RUN_FAILED: live supply collection summary did not pass"
}
if ([int]$Summary.target_product_rows -ne 94) {
    throw "GOVERNED_RUN_FAILED: expected 94 targeted products"
}
if ($Summary.live_api_called -ne $true) {
    throw "GOVERNED_RUN_FAILED: live eBay API was not called"
}
if ($Summary.forecast_generation_authorized -ne $false -or
    $Summary.ranking_execution_authorized -ne $false -or
    $Summary.purchase_recommendation_authorized -ne $false -or
    $Summary.automatic_purchase_execution_authorized -ne $false) {
    throw "GOVERNED_RUN_FAILED: downstream authority unexpectedly enabled"
}

Write-Host "PASS_PRECOLLECTOR_LIVE_SUPPLY_COLLECTION_SUMMARY"
Write-Host "TARGET_PRODUCT_ROWS=$($Summary.target_product_rows)"
Write-Host "LIMIT_PER_PRODUCT=$($Summary.limit_per_product)"
Write-Host "LIVE_API_CALLED=TRUE"

Invoke-Checked "Full repository regression suite" {
    python -m pytest -q
}

$PackageRoot = Join-Path $env:TEMP "MTG_PreCollector_Live_Supply_Collection_v1"
$ZipPath = "$PackageRoot.zip"
if (Test-Path $PackageRoot) { Remove-Item $PackageRoot -Recurse -Force }
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
New-Item -ItemType Directory -Path $PackageRoot | Out-Null
Copy-Item ".\artifacts\precollector\live_supply_collection\*" $PackageRoot -Recurse -Force
Compress-Archive -Path "$PackageRoot\*" -DestinationPath $ZipPath -Force
$ZipHash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS_PRECOLLECTOR_LIVE_SUPPLY_COLLECTION_EXPORT"
Write-Host "LIVE_SUPPLY_ZIP=$ZipPath"
Write-Host "LIVE_SUPPLY_ZIP_SHA256=$ZipHash"

Assert-CleanTree
Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_LIVE_SUPPLY_COLLECTION_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_SUPPLY_AND_LIQUIDITY_AUTHORITY"
Write-Host "HISTORICAL_APPEND_AUTHORIZED=FALSE"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
