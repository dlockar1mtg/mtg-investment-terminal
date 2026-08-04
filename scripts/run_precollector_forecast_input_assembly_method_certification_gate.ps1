$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Branch = "phase-8.3-precollector-scope-governance"
$OutputDir = Join-Path $Root "artifacts\precollector\forecast_input_assembly_method_certification"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Forecast_Input_Assembly_Method_Certification_v1.zip"

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

Invoke-Step "Fetch GitHub state" {
    git fetch origin
}

Invoke-Step "Fast-forward governed branch" {
    git pull --ff-only origin $Branch
}

$Commit = (git rev-parse HEAD).Trim()
Write-Host "PASS_GITHUB_COMMIT_BINDING=$Commit" -ForegroundColor Green

$DirtyStart = git status --porcelain
if ($DirtyStart) {
    Write-Host $DirtyStart
    throw "GATE_FAILED:working tree must be clean before execution"
}

Invoke-Step "Scope governance audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-Step "Forecast input certification tests" {
    python -m pytest .\tests\test_precollector_forecast_input_assembly_method_certification.py -q
}

Invoke-Step "Build forecast input assembly and method certification" {
    python .\scripts\build_precollector_forecast_input_assembly_method_certification.py
}

Invoke-Step "Validate forecast input certification summary" {
    @'
import json
from pathlib import Path

root = Path.cwd()
out = root / "artifacts/precollector/forecast_input_assembly_method_certification"
summary_path = out / "precollector_forecast_input_assembly_method_certification_summary.json"
product_path = out / "precollector_79_product_forecast_input_certification.csv"
horizon_path = out / "precollector_79_product_horizon_tournament_input_matrix.csv"
method_path = out / "precollector_forecast_method_certification.csv"
lineage_path = out / "precollector_forecast_input_lineage.csv"
diagnostics_path = out / "precollector_forecast_input_diagnostics.csv"
manifest_path = out / "precollector_forecast_input_assembly_method_certification_manifest.json"
for path in [summary_path, product_path, horizon_path, method_path, lineage_path, diagnostics_path, manifest_path]:
    if not path.is_file():
        raise SystemExit(f"MISSING_OUTPUT:{path.name}")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
expected = {
    "certification_status": "PASS",
    "active_product_rows": 79,
    "excluded_product_rows": 15,
    "forecast_horizon_count": 5,
    "product_horizon_matrix_rows": 395,
    "forecast_method_rows": 3,
    "selected_comparable_model": "RANK_DECAY",
    "blocking_diagnostic_rows": 0,
    "all_products_method_certified": True,
    "all_five_horizons_declared": True,
    "independent_horizon_tournaments_required": True,
    "next_stage": "PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_ARCHITECTURE",
    "forecast_generation_authorized": False,
    "ranking_execution_authorized": False,
    "purchase_analysis_authorized": False,
    "purchase_recommendation_authorized": False,
    "automatic_purchase_execution_authorized": False,
    "uip_delivery_authorized": False,
}
for key, value in expected.items():
    if summary.get(key) != value:
        raise SystemExit(f"SUMMARY_MISMATCH:{key}:expected={value}:actual={summary.get(key)}")
print("PASS_PRECOLLECTOR_FORECAST_INPUT_ASSEMBLY_METHOD_CERTIFICATION_SUMMARY")
for key in ["active_product_rows", "excluded_product_rows", "forecast_horizon_count", "product_horizon_matrix_rows", "forecast_method_rows"]:
    print(f"{key.upper()}={summary[key]}")
print(f"SELECTED_COMPARABLE_MODEL={summary['selected_comparable_model']}")
print(f"AUTHORIZED_NEXT_STAGE={summary['next_stage']}")
'@ | python -
}

Invoke-Step "Full repository regression suite" {
    python -m pytest -q
}

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $ZipPath -Force
if (-not (Test-Path $ZipPath)) {
    throw "GATE_FAILED:certified ZIP was not generated"
}

$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "FORECAST_INPUT_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "FORECAST_INPUT_ZIP_SHA256=$Hash" -ForegroundColor Green

$ArtifactsRoot = Join-Path $Root "artifacts\precollector"
if (Test-Path $ArtifactsRoot) {
    Remove-Item $ArtifactsRoot -Recurse -Force
}

$DirtyEnd = git status --porcelain
if ($DirtyEnd) {
    Write-Host $DirtyEnd
    throw "GATE_FAILED:working tree is not clean after artifact cleanup"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FORECAST_INPUT_ASSEMBLY_METHOD_CERTIFICATION_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_ARCHITECTURE" -ForegroundColor Green
Write-Host "FORECAST_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "RANKING_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE" -ForegroundColor Yellow
