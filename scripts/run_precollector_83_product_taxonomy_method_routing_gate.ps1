param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ArtifactsRoot = Join-Path $RepositoryRoot "artifacts\precollector"
$OutputRoot = Join-Path $ArtifactsRoot "83_product_taxonomy_method_routing"
$SummaryPath = Join-Path $OutputRoot "precollector_83_product_taxonomy_method_routing_summary.json"
$ManifestPath = Join-Path $OutputRoot "precollector_83_product_taxonomy_method_routing_manifest.json"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_83_Product_Taxonomy_Method_Routing_v1.zip"

function Invoke-GovernedStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "GOVERNED_GATE_FAILED: $Name"
    }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

function Assert-CleanTree {
    $status = git status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "GOVERNED_GATE_FAILED: unable to read Git status"
    }
    if ($status) {
        Write-Host $status
        throw "GOVERNED_GATE_FAILED: working tree is not clean"
    }
}

Set-Location $RepositoryRoot

Invoke-GovernedStep "Fetch GitHub state" {
    git fetch origin
}

Invoke-GovernedStep "Fast-forward governed branch" {
    git pull --ff-only origin $ExpectedBranch
}

$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "GOVERNED_GATE_FAILED: expected branch '$ExpectedBranch' but found '$CurrentBranch'"
}

$Commit = (git rev-parse HEAD).Trim()
Write-Host "PASS_GITHUB_COMMIT_BINDING=$Commit" -ForegroundColor Green

Invoke-GovernedStep "Scope governance and MTG-standard audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-GovernedStep "Certified eBay matcher metadata control" {
    python .\scripts\repair_precollector_live_summary_matcher_metadata.py
}

Invoke-GovernedStep "83-product taxonomy and routing tests" {
    python -m pytest .\tests\test_precollector_83_product_taxonomy_method_routing.py -q
}

Invoke-GovernedStep "Build 83-product taxonomy and method routing" {
    python .\scripts\build_precollector_83_product_taxonomy_method_routing.py
}

if (-not (Test-Path $SummaryPath)) {
    throw "GOVERNED_GATE_FAILED: summary missing"
}
if (-not (Test-Path $ManifestPath)) {
    throw "GOVERNED_GATE_FAILED: manifest missing"
}

$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") {
    throw "GOVERNED_GATE_FAILED: certification status is '$($Summary.certification_status)'"
}
if ([int]$Summary.selected_product_rows -ne 83) {
    throw "GOVERNED_GATE_FAILED: selected product count is '$($Summary.selected_product_rows)'"
}
if ([int]$Summary.excluded_product_rows -ne 11) {
    throw "GOVERNED_GATE_FAILED: excluded product count is '$($Summary.excluded_product_rows)'"
}
if ([int]$Summary.taxonomy_rows -ne 83) {
    throw "GOVERNED_GATE_FAILED: taxonomy count is '$($Summary.taxonomy_rows)'"
}
if ([int]$Summary.method_route_rows -ne 83) {
    throw "GOVERNED_GATE_FAILED: route count is '$($Summary.method_route_rows)'"
}
if ([int]$Summary.comparable_target_rows -ne 83) {
    throw "GOVERNED_GATE_FAILED: comparable target count is '$($Summary.comparable_target_rows)'"
}
if ([int]$Summary.blocking_diagnostic_rows -ne 0) {
    throw "GOVERNED_GATE_FAILED: blocking diagnostics exist"
}
if ($Summary.owner_comparable_approval_complete -ne $false) {
    throw "GOVERNED_GATE_FAILED: owner comparable approval was expanded prematurely"
}
if ($Summary.forecast_generation_authorized -ne $false) {
    throw "GOVERNED_GATE_FAILED: forecasting was authorized prematurely"
}
if ($Summary.ranking_execution_authorized -ne $false) {
    throw "GOVERNED_GATE_FAILED: ranking was authorized prematurely"
}
if ($Summary.purchase_recommendation_authorized -ne $false) {
    throw "GOVERNED_GATE_FAILED: recommendations were authorized prematurely"
}
if ($Summary.uip_delivery_authorized -ne $false) {
    throw "GOVERNED_GATE_FAILED: UIP delivery was authorized prematurely"
}

$RequiredFiles = @(
    "precollector_83_product_selected_universe.csv",
    "precollector_83_product_taxonomy.csv",
    "precollector_83_product_forecast_method_routes.csv",
    "precollector_83_product_comparable_target_status.csv",
    "precollector_83_product_selected_comparables.csv",
    "precollector_11_product_exclusion_reconciliation.csv",
    "precollector_83_product_taxonomy_routing_diagnostics.csv",
    "precollector_83_product_taxonomy_method_routing_summary.json",
    "precollector_83_product_taxonomy_method_routing_manifest.json"
)
foreach ($File in $RequiredFiles) {
    if (-not (Test-Path (Join-Path $OutputRoot $File))) {
        throw "GOVERNED_GATE_FAILED: required output missing: $File"
    }
}

Write-Host "PASS_PRECOLLECTOR_83_PRODUCT_TAXONOMY_METHOD_ROUTING_SUMMARY" -ForegroundColor Green
Write-Host "SELECTED_PRODUCT_ROWS=$($Summary.selected_product_rows)"
Write-Host "EXCLUDED_PRODUCT_ROWS=$($Summary.excluded_product_rows)"
Write-Host "TAXONOMY_ROWS=$($Summary.taxonomy_rows)"
Write-Host "METHOD_ROUTE_ROWS=$($Summary.method_route_rows)"
Write-Host "COMPARABLE_TARGET_ROWS=$($Summary.comparable_target_rows)"
Write-Host "SELECTED_COMPARABLE_ROWS=$($Summary.selected_comparable_rows)"
Write-Host "REQUIRED_COMPARABLE_TARGET_ROWS=$($Summary.required_comparable_target_rows)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" {
    python -m pytest -q
}

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path (Join-Path $OutputRoot "*") -DestinationPath $ZipPath -Force
$ZipHash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()

Write-Host "PASS_PRECOLLECTOR_83_PRODUCT_TAXONOMY_METHOD_ROUTING_EXPORT" -ForegroundColor Green
Write-Host "TAXONOMY_ROUTING_ZIP=$ZipPath"
Write-Host "TAXONOMY_ROUTING_ZIP_SHA256=$ZipHash"

if (Test-Path $ArtifactsRoot) {
    Remove-Item $ArtifactsRoot -Recurse -Force
}
Assert-CleanTree

Write-Host ""
Write-Host "CERTIFIED_PASS_PRECOLLECTOR_83_PRODUCT_TAXONOMY_METHOD_ROUTING_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE"
