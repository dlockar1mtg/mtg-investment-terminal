$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Branch = "phase-8.3-precollector-scope-governance"
$OutputDir = Join-Path $Root "artifacts\precollector\adaptive_tournament_refinement_architecture"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Adaptive_Tournament_Refinement_Architecture_v1.zip"
$RoundOneZip = Join-Path $env:TEMP "MTG_PreCollector_Horizon_Tournament_Execution_From_Certified_Bundle_v1.zip"
$RoundOneHash = "0088ddd5f1a87c12eb720956c75605f821aafa6d2e495d2b4c291065080ec231"

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

if (-not (Test-Path $RoundOneZip)) {
    throw "GATE_FAILED:certified Round One ZIP missing: $RoundOneZip"
}
$ActualRoundOneHash = (Get-FileHash $RoundOneZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualRoundOneHash -ne $RoundOneHash) {
    throw "GATE_FAILED:Round One ZIP hash drift expected=$RoundOneHash actual=$ActualRoundOneHash"
}
Write-Host "PASS_ROUND_ONE_PACKAGE_BINDING=$ActualRoundOneHash" -ForegroundColor Green

Invoke-Step "Scope governance audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-Step "Adaptive refinement architecture tests" {
    python -m pytest .\tests\test_precollector_adaptive_tournament_refinement_architecture.py -q
}

if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}

Invoke-Step "Build adaptive refinement architecture" {
    python .\scripts\build_precollector_adaptive_tournament_refinement_architecture.py
}

Invoke-Step "Validate adaptive refinement architecture" {
    @'
import json
from pathlib import Path
import pandas as pd

root = Path.cwd()
out = root / "artifacts/precollector/adaptive_tournament_refinement_architecture"
summary_path = out / "precollector_adaptive_refinement_architecture_summary.json"
groups_path = out / "precollector_round_two_refinement_group_registry.csv"
contenders_path = out / "precollector_round_two_contender_registry.csv"
parameters_path = out / "precollector_round_two_parameter_candidate_registry.csv"
folds_path = out / "precollector_round_two_fold_preservation_registry.csv"
boundary_path = out / "precollector_round_two_boundary_expansion_policy.csv"
manifest_path = out / "precollector_adaptive_refinement_architecture_manifest.json"
for path in [summary_path, groups_path, contenders_path, parameters_path, folds_path, boundary_path, manifest_path]:
    if not path.is_file():
        raise SystemExit(f"MISSING_OUTPUT:{path.name}")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
groups = pd.read_csv(groups_path)
contenders = pd.read_csv(contenders_path)
parameters = pd.read_csv(parameters_path)
folds = pd.read_csv(folds_path)
boundary = pd.read_csv(boundary_path)
expected = {
    "certification_status": "PASS",
    "round_one_package_sha256": "0088ddd5f1a87c12eb720956c75605f821aafa6d2e495d2b4c291065080ec231",
    "refinement_group_rows": 15,
    "competitive_refinement_groups": 9,
    "fallback_recovery_groups": 6,
    "identical_round_one_folds_required": True,
    "nested_rolling_origin_required": True,
    "discovery_and_champion_folds_separate": True,
    "product_group_holdout_required": True,
    "multiple_testing_penalty_required": True,
    "round_one_champion_challenge_required": True,
    "uncertainty_recalibration_required": True,
    "recursive_upstream_rebuild_performed": False,
    "live_network_collection_performed": False,
    "refinement_execution_performed": False,
    "next_stage": "PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_EXECUTION",
    "refinement_execution_authorized": True,
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
if groups[["horizon_code", "forecast_method"]].drop_duplicates().shape[0] != 15:
    raise SystemExit("REFINEMENT_GROUP_COVERAGE_FAILURE")
if groups["refinement_mode"].eq("COMPETITIVE_REFINEMENT").sum() != 9:
    raise SystemExit("COMPETITIVE_GROUP_COUNT_FAILURE")
if groups["refinement_mode"].eq("EVIDENCE_RECOVERY_CHALLENGE").sum() != 6:
    raise SystemExit("FALLBACK_RECOVERY_GROUP_COUNT_FAILURE")
if parameters.empty or contenders.empty or folds.empty or boundary.empty:
    raise SystemExit("ARCHITECTURE_REGISTRY_EMPTY")
if folds["fold_membership_mutable"].astype(str).str.lower().ne("false").any():
    raise SystemExit("ROUND_ONE_FOLD_MUTABILITY_DRIFT")
if parameters["current_only_features_used"].astype(str).str.lower().ne("false").any():
    raise SystemExit("CURRENT_ONLY_FEATURE_DRIFT")
if groups["final_winner_certification_authorized"].astype(str).str.lower().ne("false").any():
    raise SystemExit("FINAL_WINNER_AUTHORITY_DRIFT")
print("PASS_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE_SUMMARY")
for key in ["refinement_group_rows", "competitive_refinement_groups", "fallback_recovery_groups", "contender_registry_rows", "parameter_candidate_rows", "preserved_fold_rows", "boundary_policy_rows"]:
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
    throw "GATE_FAILED:architecture ZIP was not generated"
}
$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "ADAPTIVE_REFINEMENT_ARCHITECTURE_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "ADAPTIVE_REFINEMENT_ARCHITECTURE_ZIP_SHA256=$Hash" -ForegroundColor Green

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

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_EXECUTION" -ForegroundColor Green
Write-Host "ROUND_ONE_FOLDS_PRESERVED=TRUE" -ForegroundColor Green
Write-Host "COMPETITIVE_GROUPS=9" -ForegroundColor Green
Write-Host "FALLBACK_RECOVERY_GROUPS=6" -ForegroundColor Green
Write-Host "NO_UPSTREAM_REBUILD_PERFORMED=TRUE" -ForegroundColor Green
Write-Host "NO_LIVE_NETWORK_COLLECTION_PERFORMED=TRUE" -ForegroundColor Green
Write-Host "REFINEMENT_EXECUTION_PERFORMED=FALSE" -ForegroundColor Yellow
Write-Host "FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "FORECAST_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "RANKING_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE" -ForegroundColor Yellow
