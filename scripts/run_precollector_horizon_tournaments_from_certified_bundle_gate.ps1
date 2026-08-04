$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Branch = "phase-8.3-precollector-scope-governance"
$OutputDir = Join-Path $Root "artifacts\precollector\horizon_tournament_execution_from_certified_bundle"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Horizon_Tournament_Execution_From_Certified_Bundle_v1.zip"

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
    throw "GATE_FAILED:working tree must be clean before execution"
}

Invoke-Step "Scope governance audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-Step "Certified-bundle Round One tests" {
    python -m pytest .\tests\test_precollector_horizon_tournaments_from_certified_bundle.py -q
}

if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}

Invoke-Step "Execute Round One from certified bundle" {
    python .\scripts\run_precollector_horizon_tournaments_from_certified_bundle.py
}

Invoke-Step "Validate certified-bundle Round One summary" {
    @'
import json
from pathlib import Path
import pandas as pd

root = Path.cwd()
out = root / "artifacts/precollector/horizon_tournament_execution_from_certified_bundle"
summary_path = out / "precollector_round_one_execution_summary.json"
winners_path = out / "precollector_round_one_preliminary_winner_registry.csv"
lineage_path = out / "precollector_round_one_certified_input_lineage.csv"
manifest_path = out / "precollector_round_one_execution_manifest.json"
for path in [summary_path, winners_path, lineage_path, manifest_path]:
    if not path.is_file():
        raise SystemExit(f"MISSING_OUTPUT:{path.name}")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
winners = pd.read_csv(winners_path)
lineage = pd.read_csv(lineage_path)
expected = {
    "certification_status": "PASS",
    "active_product_rows": 79,
    "forecast_horizon_count": 5,
    "route_count": 3,
    "product_horizon_input_rows": 395,
    "winner_registry_rows": 15,
    "blocking_diagnostic_rows": 0,
    "recursive_upstream_rebuild_performed": False,
    "live_network_collection_performed": False,
    "round_two_refinement_required": True,
    "final_winner_certification_authorized": False,
    "next_stage": "PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE",
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
if winners[["horizon_code", "forecast_method"]].drop_duplicates().shape[0] != 15:
    raise SystemExit("WINNER_COVERAGE_FAILURE")
if lineage["artifact_role"].nunique() != 7:
    raise SystemExit("CERTIFIED_INPUT_LINEAGE_COVERAGE_FAILURE")
if winners["forecast_generation_authorized"].astype(str).str.lower().ne("false").any():
    raise SystemExit("FORECAST_AUTHORITY_DRIFT")
print("PASS_PRECOLLECTOR_HORIZON_TOURNAMENT_EXECUTION_FROM_CERTIFIED_BUNDLE_SUMMARY")
for key in ["active_product_rows", "forecast_horizon_count", "route_count", "product_horizon_input_rows", "rolling_prediction_rows", "model_scorecard_rows", "winner_registry_rows", "competitive_winner_rows", "fallback_winner_rows", "uncertainty_evidence_rows"]:
    print(f"{key.upper()}={summary[key]}")
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
Write-Host "ROUND_ONE_CERTIFIED_BUNDLE_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "ROUND_ONE_CERTIFIED_BUNDLE_ZIP_SHA256=$Hash" -ForegroundColor Green

# Clean only this stage's generated execution output. Certified upstream ZIPs remain untouched.
if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}

$DirtyEnd = git status --porcelain
if ($DirtyEnd) {
    Write-Host $DirtyEnd
    throw "GATE_FAILED:working tree is not clean after stage-local cleanup"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_HORIZON_TOURNAMENT_EXECUTION_FROM_CERTIFIED_BUNDLE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE" -ForegroundColor Green
Write-Host "NO_UPSTREAM_REBUILD_PERFORMED=TRUE" -ForegroundColor Green
Write-Host "NO_LIVE_NETWORK_COLLECTION_PERFORMED=TRUE" -ForegroundColor Green
Write-Host "ROUND_TWO_REFINEMENT_REQUIRED=TRUE" -ForegroundColor Green
Write-Host "FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "FORECAST_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "RANKING_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE" -ForegroundColor Yellow
