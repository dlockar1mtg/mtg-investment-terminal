$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Branch = "phase-8.3-precollector-scope-governance"
$OutputDir = Join-Path $Root "artifacts\precollector\tournament_certified_input_bundle_drift_gate"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Tournament_Certified_Input_Bundle_Drift_Gate_v1.zip"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "GATE_FAILED:$Name`:exit=$LASTEXITCODE"
    }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

Set-Location $Root
Invoke-Step "Fetch GitHub state" { git fetch origin }
Invoke-Step "Fast-forward governed branch" { git pull --ff-only origin $Branch }

$Commit = (git rev-parse HEAD).Trim()
Write-Host "PASS_GITHUB_COMMIT_BINDING=$Commit" -ForegroundColor Green

$DirtyStart = git status --porcelain
if ($DirtyStart) {
    Write-Host $DirtyStart
    throw "GATE_FAILED:working tree must be clean before drift audit"
}

Invoke-Step "Scope governance audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-Step "Certified input drift tests" {
    python -m pytest .\tests\test_precollector_tournament_certified_input_bundle_drift.py -q
}

Write-Host "`n=== Inventory certified packages and authorities ===" -ForegroundColor Cyan
python .\scripts\audit_precollector_tournament_certified_input_bundle_drift.py
$AuditExit = $LASTEXITCODE
if ($AuditExit -notin @(0, 2)) {
    throw "GATE_FAILED:certified input drift audit unexpected exit=$AuditExit"
}

if (-not (Test-Path $OutputDir)) {
    throw "GATE_FAILED:drift audit output directory missing"
}

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $ZipPath -Force
$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "DRIFT_AUDIT_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "DRIFT_AUDIT_ZIP_SHA256=$Hash" -ForegroundColor Green

$SummaryPath = Join-Path $OutputDir "precollector_tournament_certified_input_drift_summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "GATE_FAILED:drift summary missing"
}
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
Write-Host "CERTIFICATION_STATUS=$($Summary.certification_status)"
Write-Host "BLOCKING_DIAGNOSTIC_ROWS=$($Summary.blocking_diagnostic_rows)"
Write-Host "NEXT_STAGE=$($Summary.next_stage)"

Remove-Item (Join-Path $Root "artifacts\precollector") -Recurse -Force

$DirtyEnd = git status --porcelain
if ($DirtyEnd) {
    Write-Host $DirtyEnd
    throw "GATE_FAILED:working tree is not clean after audit cleanup"
}

if ($AuditExit -eq 2) {
    Write-Host "`nREVIEW_REQUIRED_PRECOLLECTOR_TOURNAMENT_CERTIFIED_INPUT_BUNDLE_DRIFT_GATE" -ForegroundColor Yellow
    Write-Host "NO_UPSTREAM_REBUILD_PERFORMED=TRUE" -ForegroundColor Green
    Write-Host "NO_LIVE_NETWORK_COLLECTION_PERFORMED=TRUE" -ForegroundColor Green
    Write-Host "FORECAST_AUTHORIZED=FALSE" -ForegroundColor Yellow
    exit 2
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_TOURNAMENT_CERTIFIED_INPUT_BUNDLE_DRIFT_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_EXECUTION_FROM_CERTIFIED_BUNDLE" -ForegroundColor Green
Write-Host "NO_UPSTREAM_REBUILD_PERFORMED=TRUE" -ForegroundColor Green
Write-Host "NO_LIVE_NETWORK_COLLECTION_PERFORMED=TRUE" -ForegroundColor Green
Write-Host "FORECAST_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "RANKING_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
