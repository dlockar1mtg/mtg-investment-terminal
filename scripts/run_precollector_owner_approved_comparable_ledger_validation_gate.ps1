param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$ArtifactsRoot = Join-Path $RepositoryRoot "artifacts\precollector"
$OutputRoot = Join-Path $ArtifactsRoot "owner_approved_comparable_ledger_validation"
$SummaryPath = Join-Path $OutputRoot "precollector_owner_approved_comparable_ledger_summary.json"
$ManifestPath = Join-Path $OutputRoot "precollector_owner_approved_comparable_ledger_manifest.json"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Owner_Approved_Comparable_Ledger_Validation_v1.zip"

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
    $Status = git status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "GOVERNED_GATE_FAILED: unable to read Git status"
    }
    if ($Status) {
        Write-Host $Status
        throw "GOVERNED_GATE_FAILED: working tree is not clean"
    }
}

Set-Location $RepositoryRoot

Invoke-GovernedStep "Fetch GitHub state" { git fetch origin }
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "GOVERNED_GATE_FAILED: expected '$ExpectedBranch' but found '$CurrentBranch'"
}
Invoke-GovernedStep "Fast-forward governed branch" { git pull --ff-only origin $ExpectedBranch }
Assert-CleanTree

$LocalCommit = (git rev-parse HEAD).Trim()
$RemoteCommit = (git rev-parse "origin/$ExpectedBranch").Trim()
if ($LocalCommit -ne $RemoteCommit) {
    throw "GOVERNED_GATE_FAILED: local commit does not equal origin branch commit"
}
Write-Host "PASS_GITHUB_COMMIT_BINDING=$LocalCommit" -ForegroundColor Green

if (Test-Path $ArtifactsRoot) { Remove-Item $ArtifactsRoot -Recurse -Force }
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

Invoke-GovernedStep "Scope governance audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-GovernedStep "Owner-approved comparable ledger tests" {
    python -m pytest -q .\tests\test_precollector_owner_approved_comparable_ledger_validation.py
}

Invoke-GovernedStep "Build owner-approved comparable ledger and validation" {
    python .\scripts\build_precollector_owner_approved_comparable_ledger_validation.py
}

foreach ($Required in @(
    "precollector_owner_approved_comparable_ledger.csv",
    "precollector_comparable_target_validation.csv",
    "precollector_comparable_product_holdout_validation.csv",
    "precollector_comparable_ledger_diagnostics.csv",
    "precollector_owner_approved_comparable_ledger_summary.json",
    "precollector_owner_approved_comparable_ledger_manifest.json"
)) {
    if (-not (Test-Path (Join-Path $OutputRoot $Required))) {
        throw "GOVERNED_GATE_FAILED: required output missing: $Required"
    }
}

$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.certification_status -ne "PASS") { throw "GOVERNED_GATE_FAILED: summary did not certify" }
if ([int]$Summary.active_product_rows -ne 79) { throw "GOVERNED_GATE_FAILED: active product count drift" }
if ([int]$Summary.excluded_product_rows -ne 15) { throw "GOVERNED_GATE_FAILED: excluded product count drift" }
if ([int]$Summary.required_comparable_target_rows -ne 23) { throw "GOVERNED_GATE_FAILED: required target count drift" }
if ([int]$Summary.approved_comparable_ledger_rows -le 0) { throw "GOVERNED_GATE_FAILED: approved ledger is empty" }
if ([int]$Summary.target_validation_blocked_rows -ne 0) { throw "GOVERNED_GATE_FAILED: blocked target validations exist" }
if ([int]$Summary.holdout_validation_blocked_rows -ne 0) { throw "GOVERNED_GATE_FAILED: blocked holdout validations exist" }
if ([int]$Summary.blocking_diagnostic_rows -ne 0) { throw "GOVERNED_GATE_FAILED: blocking diagnostics exist" }
if ($Summary.owner_comparable_approval_complete -ne $true) { throw "GOVERNED_GATE_FAILED: owner approval is not complete" }
if ($Summary.forecast_generation_authorized -ne $false -or
    $Summary.ranking_execution_authorized -ne $false -or
    $Summary.purchase_analysis_authorized -ne $false -or
    $Summary.purchase_recommendation_authorized -ne $false -or
    $Summary.automatic_purchase_execution_authorized -ne $false -or
    $Summary.uip_delivery_authorized -ne $false) {
    throw "GOVERNED_GATE_FAILED: downstream authority expanded prematurely"
}

Write-Host "PASS_PRECOLLECTOR_OWNER_APPROVED_COMPARABLE_LEDGER_SUMMARY" -ForegroundColor Green
Write-Host "ACTIVE_PRODUCT_ROWS=$($Summary.active_product_rows)"
Write-Host "EXCLUDED_PRODUCT_ROWS=$($Summary.excluded_product_rows)"
Write-Host "REQUIRED_COMPARABLE_TARGET_ROWS=$($Summary.required_comparable_target_rows)"
Write-Host "APPROVED_COMPARABLE_LEDGER_ROWS=$($Summary.approved_comparable_ledger_rows)"
Write-Host "PRIMARY_COMPARABLE_ROWS=$($Summary.primary_comparable_rows)"
Write-Host "SECONDARY_COMPARABLE_ROWS=$($Summary.secondary_comparable_rows)"
Write-Host "HOLDOUT_VALIDATION_ROWS=$($Summary.holdout_validation_rows)"
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"

Invoke-GovernedStep "Full repository regression suite" {
    python -m pytest -q
}

Compress-Archive -Path (Join-Path $OutputRoot "*") -DestinationPath $ZipPath -Force
if (-not (Test-Path $ZipPath)) { throw "GOVERNED_GATE_FAILED: ZIP was not created" }
$ZipHash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()

Write-Host "COMPARABLE_LEDGER_ZIP=$ZipPath"
Write-Host "COMPARABLE_LEDGER_ZIP_SHA256=$ZipHash"

if (Test-Path $ArtifactsRoot) { Remove-Item $ArtifactsRoot -Recurse -Force }
Assert-CleanTree

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_OWNER_APPROVED_COMPARABLE_LEDGER_VALIDATION_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=$($Summary.next_stage)"
Write-Host "FORECAST_AUTHORIZED=FALSE"
Write-Host "RANKING_AUTHORIZED=FALSE"
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE"
