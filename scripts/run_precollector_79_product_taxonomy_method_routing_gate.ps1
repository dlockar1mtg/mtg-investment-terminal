param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ArtifactsRoot = Join-Path $RepositoryRoot "artifacts\precollector"
$OutputRoot = Join-Path $ArtifactsRoot "79_product_taxonomy_method_routing"
$SummaryPath = Join-Path $OutputRoot "precollector_79_product_taxonomy_method_routing_summary.json"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_79_Product_Taxonomy_Method_Routing_v1.zip"

function Invoke-GovernedStep {
    param([string]$Name, [scriptblock]$Action)
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "GOVERNED_GATE_FAILED: $Name" }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

function Assert-CleanTree {
    $Status = git status --porcelain
    if ($LASTEXITCODE -ne 0) { throw "GOVERNED_GATE_FAILED: unable to inspect Git status" }
    if ($Status) { Write-Host $Status; throw "GOVERNED_GATE_FAILED: working tree is not clean" }
}

Set-Location $RepositoryRoot
Invoke-GovernedStep "Fetch GitHub state" { git fetch origin }
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) { throw "GOVERNED_GATE_FAILED: expected '$ExpectedBranch' but found '$CurrentBranch'" }
Invoke-GovernedStep "Fast-forward governed branch" { git pull --ff-only origin $ExpectedBranch }
Assert-CleanTree
$Commit = (git rev-parse HEAD).Trim()
$RemoteCommit = (git rev-parse "origin/$ExpectedBranch").Trim()
if ($Commit -ne $RemoteCommit) { throw "GOVERNED_GATE_FAILED: local and remote commits differ" }
Write-Host "PASS_GITHUB_COMMIT_BINDING=$Commit" -ForegroundColor Green

if (Test-Path $ArtifactsRoot) { Remove-Item $ArtifactsRoot -Recurse -Force }
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

Invoke-GovernedStep "Scope governance audit" { python .\scripts\audit_precollector_scope_governance.py }
Invoke-GovernedStep "79-product reconciliation tests" {
    python -m pytest -q `
        .\tests\test_precollector_79_product_taxonomy_method_routing.py `
        .\tests\test_precollector_83_product_taxonomy_method_routing.py
}
Invoke-GovernedStep "Build 79-product taxonomy routing reconciliation" {
    python .\scripts\build_precollector_79_product_taxonomy_method_routing.py
}

if (-not (Test-Path $SummaryPath)) { throw "GOVERNED_GATE_FAILED: summary missing" }
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") { throw "GOVERNED_GATE_FAILED: build status '$($Summary.certification_status)'" }
if ([int]$Summary.selected_product_rows -ne 79) { throw "GOVERNED_GATE_FAILED: selected count drift" }
if ([int]$Summary.excluded_product_rows -ne 15) { throw "GOVERNED_GATE_FAILED: excluded count drift" }
if ([int]$Summary.taxonomy_rows -ne 79) { throw "GOVERNED_GATE_FAILED: taxonomy count drift" }
if ([int]$Summary.method_route_rows -ne 79) { throw "GOVERNED_GATE_FAILED: route count drift" }
if ([int]$Summary.comparable_target_rows -ne 79) { throw "GOVERNED_GATE_FAILED: comparable target count drift" }
if ([int]$Summary.blocking_diagnostic_rows -ne 0) { throw "GOVERNED_GATE_FAILED: blocking diagnostics exist" }
foreach ($Name in @("forecast_generation_authorized","ranking_execution_authorized","purchase_analysis_authorized","purchase_recommendation_authorized","automatic_purchase_execution_authorized","uip_delivery_authorized")) {
    if ($Summary.$Name -ne $false) { throw "GOVERNED_GATE_FAILED: authority expanded: $Name" }
}

$RequiredFiles = @(
    "precollector_79_product_selected_universe.csv",
    "precollector_79_product_taxonomy.csv",
    "precollector_79_product_forecast_method_routes.csv",
    "precollector_79_product_comparable_target_status.csv",
    "precollector_79_product_selected_comparables.csv",
    "precollector_15_product_exclusion_reconciliation.csv",
    "precollector_79_product_taxonomy_routing_diagnostics.csv",
    "precollector_79_product_taxonomy_method_routing_summary.json",
    "precollector_79_product_taxonomy_method_routing_manifest.json"
)
foreach ($File in $RequiredFiles) {
    if (-not (Test-Path (Join-Path $OutputRoot $File))) { throw "GOVERNED_GATE_FAILED: missing output $File" }
}

Write-Host "PASS_PRECOLLECTOR_79_PRODUCT_TAXONOMY_ROUTING_SUMMARY" -ForegroundColor Green
Write-Host "SELECTED_PRODUCT_ROWS=$($Summary.selected_product_rows)"
Write-Host "EXCLUDED_PRODUCT_ROWS=$($Summary.excluded_product_rows)"
Write-Host "METHOD_ROUTE_ROWS=$($Summary.method_route_rows)"
Write-Host "SELECTED_COMPARABLE_ROWS=$($Summary.selected_comparable_rows)"
Write-Host "REQUIRED_COMPARABLE_TARGET_ROWS=$($Summary.required_comparable_target_rows)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" { python -m pytest -q }
Compress-Archive -Path (Join-Path $OutputRoot "*") -DestinationPath $ZipPath -Force
$ZipHash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "TAXONOMY_ROUTING_ZIP=$ZipPath"
Write-Host "TAXONOMY_ROUTING_ZIP_SHA256=$ZipHash"

Remove-Item $ArtifactsRoot -Recurse -Force
Assert-CleanTree
Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_79_PRODUCT_TAXONOMY_METHOD_ROUTING_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE"
