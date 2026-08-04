$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Branch = "phase-8.3-precollector-scope-governance"
$OutputDir = Join-Path $Root "artifacts\precollector\final_champion_challenge_execution"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Final_Champion_Challenge_Execution_v1.zip"
$ArchitectureZip = Join-Path $env:TEMP "MTG_PreCollector_Final_Champion_Challenge_Architecture_v1.zip"
$ArchitectureHash = "d4c23481c8010123fe3a24cb3abc32d2d8e8123398013594f3ddcc2876f2ba8f"
$RoundTwoZip = Join-Path $env:TEMP "MTG_PreCollector_Adaptive_Tournament_Refinement_Execution_v1_1.zip"
$RoundTwoHash = "f67f2c1f0241f9450498b4cf9cd584852766738e7a5b134591c0365b4bb7fc29"

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

$DirtyStart = git status --porcelain --untracked-files=all
if ($DirtyStart) {
    Write-Host $DirtyStart
    throw "GATE_FAILED:working tree must be clean before final challenge execution"
}

foreach ($Binding in @(
    @{Path=$ArchitectureZip; Hash=$ArchitectureHash; Name="FINAL_CHAMPION_ARCHITECTURE"},
    @{Path=$RoundTwoZip; Hash=$RoundTwoHash; Name="REPAIRED_ROUND_TWO"}
)) {
    if (-not (Test-Path $Binding.Path)) {
        throw "GATE_FAILED:required certified ZIP missing: $($Binding.Path)"
    }
    $Actual = (Get-FileHash $Binding.Path -Algorithm SHA256).Hash.Trim().ToLowerInvariant()
    if (-not [string]::Equals($Actual, $Binding.Hash, [System.StringComparison]::Ordinal)) {
        throw "GATE_FAILED:$($Binding.Name)_HASH_DRIFT expected=$($Binding.Hash) actual=$Actual"
    }
    Write-Host "PASS_$($Binding.Name)_PACKAGE_BINDING=$Actual" -ForegroundColor Green
}

Invoke-Step "Scope governance audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-Step "Final champion execution tests" {
    python -m pytest .\tests\test_precollector_final_champion_challenge_execution.py -q
}

if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}

Invoke-Step "Execute final champion challenge" {
    python .\scripts\run_precollector_final_champion_challenge_execution.py
}

Invoke-Step "Validate final champion challenge" {
    @'
import json
from pathlib import Path
import pandas as pd

root = Path.cwd()
out = root / "artifacts/precollector/final_champion_challenge_execution"
summary_path = out / "precollector_final_champion_execution_summary.json"
scores_path = out / "precollector_final_champion_candidate_partition_scorecard.csv"
decisions_path = out / "precollector_final_champion_group_decisions.csv"
winners_path = out / "precollector_certified_short_horizon_winner_registry.csv"
long_path = out / "precollector_final_champion_long_horizon_routing.csv"
diagnostics_path = out / "precollector_final_champion_execution_diagnostics.csv"
manifest_path = out / "precollector_final_champion_execution_manifest.json"
for path in [summary_path, scores_path, decisions_path, winners_path, long_path, diagnostics_path, manifest_path]:
    if not path.is_file():
        raise SystemExit(f"MISSING_OUTPUT:{path.name}")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
scores = pd.read_csv(scores_path)
decisions = pd.read_csv(decisions_path)
winners = pd.read_csv(winners_path)
long_routes = pd.read_csv(long_path)
diagnostics = pd.read_csv(diagnostics_path)
expected = {
    "certification_status": "PASS",
    "short_horizon_challenge_groups": 9,
    "frozen_candidate_rows": 30,
    "final_group_decision_rows": 9,
    "long_horizon_monte_carlo_routes": 6,
    "long_horizon_monte_carlo_required": True,
    "required_simulations_per_product_horizon": 10000,
    "candidate_set_frozen": True,
    "new_tuning_performed": False,
    "preserved_fold_membership_changed": False,
    "recursive_upstream_rebuild_performed": False,
    "live_network_collection_performed": False,
    "blocking_diagnostic_rows": 0,
    "next_stage": "PRECOLLECTOR_WINNER_AND_UNCERTAINTY_CERTIFICATION",
    "final_winner_certification_authorized": False,
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
if len(decisions) != 9:
    raise SystemExit("FINAL_DECISION_COUNT_FAILURE")
if len(long_routes) != 6:
    raise SystemExit("LONG_HORIZON_ROUTE_COUNT_FAILURE")
if set(scores["partition_name"]) != {"OUTER_ALL", "LATEST_TIME_STRESS", "PRODUCT_CONCENTRATION_STRESS"}:
    raise SystemExit("STRESS_PARTITION_COVERAGE_FAILURE")
if not scores["candidate_set_frozen"].astype(str).str.lower().eq("true").all():
    raise SystemExit("CANDIDATE_FREEZE_DRIFT")
if not scores["new_tuning_performed"].astype(str).str.lower().eq("false").all():
    raise SystemExit("NEW_TUNING_DRIFT")
allowed = {
    "RETAIN_ROUND_ONE_INCUMBENT",
    "PROMOTE_FROZEN_ROUND_TWO_CHALLENGER",
    "RETAIN_GOVERNED_BASELINE",
    "GOVERNED_NO_PRODUCTION_CHAMPION",
}
if not set(decisions["final_challenge_decision"]).issubset(allowed):
    raise SystemExit("INVALID_FINAL_DECISION")
if not diagnostics.empty:
    raise SystemExit("BLOCKING_DIAGNOSTICS_PRESENT")
print("PASS_PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_EXECUTION_SUMMARY")
for key in [
    "short_horizon_challenge_groups",
    "frozen_candidate_rows",
    "candidate_partition_scorecard_rows",
    "final_group_decision_rows",
    "short_horizon_challenge_winner_rows",
    "retained_round_one_incumbent_rows",
    "promoted_frozen_round_two_challenger_rows",
    "retained_governed_baseline_rows",
    "governed_no_production_champion_rows",
    "long_horizon_monte_carlo_routes",
]:
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
    throw "GATE_FAILED:final challenge execution ZIP was not generated"
}
$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "FINAL_CHAMPION_EXECUTION_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "FINAL_CHAMPION_EXECUTION_ZIP_SHA256=$Hash" -ForegroundColor Green

if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}
$PrecollectorRoot = Join-Path $Root "artifacts\precollector"
if ((Test-Path $PrecollectorRoot) -and -not (Get-ChildItem $PrecollectorRoot -Force | Select-Object -First 1)) {
    Remove-Item $PrecollectorRoot -Force
}

$DirtyEnd = git status --porcelain --untracked-files=all
if ($DirtyEnd) {
    Write-Host $DirtyEnd
    throw "GATE_FAILED:working tree is not clean after final challenge cleanup"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_EXECUTION" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_WINNER_AND_UNCERTAINTY_CERTIFICATION" -ForegroundColor Green
Write-Host "CANDIDATE_SET_FROZEN=TRUE" -ForegroundColor Green
Write-Host "NO_NEW_TUNING_PERFORMED=TRUE" -ForegroundColor Green
Write-Host "PRESERVED_ROUND_TWO_FOLDS=TRUE" -ForegroundColor Green
Write-Host "LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE" -ForegroundColor Green
Write-Host "REQUIRED_SIMULATIONS_PER_PRODUCT_HORIZON=10000" -ForegroundColor Green
Write-Host "FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "FORECAST_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "RANKING_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE" -ForegroundColor Yellow
