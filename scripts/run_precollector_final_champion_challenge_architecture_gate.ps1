$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Branch = "phase-8.3-precollector-scope-governance"
$OutputDir = Join-Path $Root "artifacts\precollector\final_champion_challenge_architecture"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Final_Champion_Challenge_Architecture_v1.zip"
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
    throw "GATE_FAILED:working tree must be clean before architecture certification"
}

if (-not (Test-Path $RoundTwoZip)) {
    throw "GATE_FAILED:certified repaired Round Two ZIP missing: $RoundTwoZip"
}
$ActualRoundTwoHash = (Get-FileHash $RoundTwoZip -Algorithm SHA256).Hash.Trim().ToLowerInvariant()
if (-not [string]::Equals($ActualRoundTwoHash, $RoundTwoHash, [System.StringComparison]::Ordinal)) {
    throw "GATE_FAILED:Round Two ZIP hash drift expected=$RoundTwoHash actual=$ActualRoundTwoHash"
}
Write-Host "PASS_REPAIRED_ROUND_TWO_PACKAGE_BINDING=$ActualRoundTwoHash" -ForegroundColor Green

Invoke-Step "Scope governance audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-Step "Final champion architecture tests" {
    python -m pytest .\tests\test_precollector_final_champion_challenge_architecture.py -q
}

if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}

Invoke-Step "Build final champion challenge architecture" {
    python .\scripts\build_precollector_final_champion_challenge_architecture.py
}

Invoke-Step "Validate final champion challenge architecture" {
    @'
import json
from pathlib import Path
import pandas as pd

root = Path.cwd()
out = root / "artifacts/precollector/final_champion_challenge_architecture"
summary_path = out / "precollector_final_champion_challenge_architecture_summary.json"
groups_path = out / "precollector_final_champion_challenge_group_registry.csv"
candidates_path = out / "precollector_final_champion_frozen_candidate_registry.csv"
partitions_path = out / "precollector_final_champion_stress_partition_registry.csv"
long_path = out / "precollector_final_champion_long_horizon_routing.csv"
policy_path = out / "precollector_final_champion_decision_policy.csv"
manifest_path = out / "precollector_final_champion_challenge_architecture_manifest.json"
lineage_path = out / "precollector_final_champion_architecture_input_lineage.csv"
for path in [summary_path, groups_path, candidates_path, partitions_path, long_path, policy_path, manifest_path, lineage_path]:
    if not path.is_file():
        raise SystemExit(f"MISSING_OUTPUT:{path.name}")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
groups = pd.read_csv(groups_path)
candidates = pd.read_csv(candidates_path)
partitions = pd.read_csv(partitions_path)
long_routes = pd.read_csv(long_path)
policy = pd.read_csv(policy_path)
expected = {
    "certification_status": "PASS",
    "short_horizon_challenge_groups": 9,
    "long_horizon_monte_carlo_routes": 6,
    "stress_partition_rows": 27,
    "candidate_set_frozen_before_challenge": True,
    "new_parameter_tuning_authorized": False,
    "new_feature_tuning_authorized": False,
    "preserved_fold_membership_changed": False,
    "final_challenge_execution_performed": False,
    "recursive_upstream_rebuild_performed": False,
    "live_network_collection_performed": False,
    "long_horizon_monte_carlo_required": True,
    "required_simulations_per_product_horizon": 10000,
    "next_stage": "PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_EXECUTION",
    "final_challenge_execution_authorized": True,
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
if groups.shape[0] != 9:
    raise SystemExit("CHALLENGE_GROUP_COUNT_FAILURE")
if groups["incumbent_model"].fillna("").eq("").any():
    raise SystemExit("INCUMBENT_MODEL_MISSING")
if candidates.empty or candidates["candidate_set_frozen"].astype(str).str.lower().ne("true").any():
    raise SystemExit("FROZEN_CANDIDATE_REGISTRY_FAILURE")
if candidates["new_tuning_authorized"].astype(str).str.lower().ne("false").any():
    raise SystemExit("NEW_TUNING_AUTHORITY_DRIFT")
if partitions.shape[0] != 27:
    raise SystemExit("STRESS_PARTITION_COUNT_FAILURE")
if partitions["fold_membership_mutable"].astype(str).str.lower().ne("false").any():
    raise SystemExit("FOLD_MUTABILITY_DRIFT")
if long_routes.shape[0] != 6:
    raise SystemExit("LONG_HORIZON_ROUTE_COUNT_FAILURE")
if long_routes["required_simulations_per_product_horizon"].astype(int).ne(10000).any():
    raise SystemExit("MONTE_CARLO_RUN_COUNT_DRIFT")
if long_routes["direct_backtest_champion_authorized"].astype(str).str.lower().ne("false").any():
    raise SystemExit("LONG_HORIZON_DIRECT_CHAMPION_AUTHORITY_DRIFT")
if policy.shape[0] != 4:
    raise SystemExit("DECISION_POLICY_COUNT_FAILURE")
print("PASS_PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE_SUMMARY")
for key in ["short_horizon_challenge_groups", "long_horizon_monte_carlo_routes", "frozen_candidate_rows", "stress_partition_rows", "decision_policy_rows"]:
    print(f"{key.upper()}={summary[key]}")
print("LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE")
print("REQUIRED_SIMULATIONS_PER_PRODUCT_HORIZON=10000")
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
    throw "GATE_FAILED:architecture ZIP was not generated"
}
$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "FINAL_CHAMPION_ARCHITECTURE_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "FINAL_CHAMPION_ARCHITECTURE_ZIP_SHA256=$Hash" -ForegroundColor Green

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
    throw "GATE_FAILED:working tree is not clean after stage-local cleanup"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_EXECUTION" -ForegroundColor Green
Write-Host "SHORT_HORIZON_CHALLENGE_GROUPS=9" -ForegroundColor Green
Write-Host "LONG_HORIZON_MONTE_CARLO_ROUTES=6" -ForegroundColor Green
Write-Host "LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE" -ForegroundColor Green
Write-Host "REQUIRED_SIMULATIONS_PER_PRODUCT_HORIZON=10000" -ForegroundColor Green
Write-Host "CANDIDATE_SET_FROZEN=TRUE" -ForegroundColor Green
Write-Host "NO_NEW_TUNING_AUTHORIZED=TRUE" -ForegroundColor Green
Write-Host "FINAL_CHALLENGE_EXECUTION_PERFORMED=FALSE" -ForegroundColor Yellow
Write-Host "FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "FORECAST_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "RANKING_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE" -ForegroundColor Yellow
