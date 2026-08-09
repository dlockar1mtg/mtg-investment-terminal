$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Branch = "phase-8.3-precollector-scope-governance"
$OutputDir = Join-Path $Root "artifacts\precollector\adaptive_tournament_refinement_execution"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Adaptive_Tournament_Refinement_Execution_v1.zip"
$RoundOneZip = Join-Path $env:TEMP "MTG_PreCollector_Horizon_Tournament_Execution_From_Certified_Bundle_v1.zip"
$RoundOneHash = "0088ddd5f1a87c12eb720956c75605f821aafa6d2e495d2b4c291065080ec231"
$ArchitectureZip = Join-Path $env:TEMP "MTG_PreCollector_Adaptive_Tournament_Refinement_Architecture_v1.zip"
$ArchitectureHash = "42ca503d11a8a85ba5519739f273b4f7d9c6e3a8f83ca6df541d00d413ae06be"

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
    throw "GATE_FAILED:working tree must be clean before refinement execution"
}

foreach ($Binding in @(
    @{Path=$RoundOneZip; Hash=$RoundOneHash; Label="ROUND_ONE"},
    @{Path=$ArchitectureZip; Hash=$ArchitectureHash; Label="REFINEMENT_ARCHITECTURE"}
)) {
    if (-not (Test-Path $Binding.Path)) {
        throw "GATE_FAILED:$($Binding.Label) package missing: $($Binding.Path)"
    }
    $Actual = (Get-FileHash $Binding.Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $Binding.Hash) {
        throw "GATE_FAILED:$($Binding.Label) package hash drift expected=$($Binding.Hash) actual=$Actual"
    }
    Write-Host "PASS_$($Binding.Label)_PACKAGE_BINDING=$Actual" -ForegroundColor Green
}

Invoke-Step "Scope governance audit" {
    python .\scripts\audit_precollector_scope_governance.py
}

Invoke-Step "Adaptive refinement execution tests" {
    python -m pytest .\tests\test_precollector_adaptive_tournament_refinement_execution.py -q
}

if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}

Invoke-Step "Execute adaptive refinement tournament" {
    python .\scripts\run_precollector_adaptive_tournament_refinement_execution.py
}

Invoke-Step "Validate adaptive refinement execution" {
    @'
import json
from pathlib import Path
import pandas as pd

root = Path.cwd()
out = root / "artifacts/precollector/adaptive_tournament_refinement_execution"
summary_path = out / "precollector_round_two_execution_summary.json"
folds_path = out / "precollector_round_two_fold_assignment.csv"
scores_path = out / "precollector_round_two_candidate_scorecard.csv"
decisions_path = out / "precollector_round_two_preliminary_group_decisions.csv"
boundary_path = out / "precollector_round_two_boundary_review.csv"
uncertainty_path = out / "precollector_round_two_uncertainty_recalibration.csv"
diagnostics_path = out / "precollector_round_two_execution_diagnostics.csv"
manifest_path = out / "precollector_round_two_execution_manifest.json"
lineage_path = out / "precollector_round_two_execution_input_lineage.csv"
for path in [summary_path, folds_path, scores_path, decisions_path, boundary_path, uncertainty_path, diagnostics_path, manifest_path, lineage_path]:
    if not path.is_file():
        raise SystemExit(f"MISSING_OUTPUT:{path.name}")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
folds = pd.read_csv(folds_path)
scores = pd.read_csv(scores_path)
decisions = pd.read_csv(decisions_path)
diagnostics = pd.read_csv(diagnostics_path)
expected = {
    "certification_status": "PASS",
    "refinement_group_rows": 15,
    "parameter_candidate_rows": 2011,
    "preserved_fold_rows": 1992,
    "fold_assignment_rows": 1992,
    "blocking_diagnostic_rows": 0,
    "preserved_fold_membership_changed": False,
    "recursive_upstream_rebuild_performed": False,
    "live_network_collection_performed": False,
    "current_only_features_used": False,
    "final_winner_certification_authorized": False,
    "forecast_generation_authorized": False,
    "ranking_execution_authorized": False,
    "purchase_analysis_authorized": False,
    "purchase_recommendation_authorized": False,
    "automatic_purchase_execution_authorized": False,
    "uip_delivery_authorized": False,
    "next_stage": "PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE",
}
for key, value in expected.items():
    if summary.get(key) != value:
        raise SystemExit(f"SUMMARY_MISMATCH:{key}:expected={value}:actual={summary.get(key)}")
if decisions["refinement_group_id"].nunique() != 15 or len(decisions) != 15:
    raise SystemExit("GROUP_DECISION_COVERAGE_FAILURE")
if scores["candidate_id"].nunique() != 2011:
    raise SystemExit(f"CANDIDATE_SCORECARD_COVERAGE_FAILURE:{scores['candidate_id'].nunique()}")
if folds["fold_membership_mutable"].astype(str).str.lower().ne("false").any():
    raise SystemExit("PRESERVED_FOLD_MUTABILITY_DRIFT")
if set(folds["fold_role"].unique()) - {"DISCOVERY", "CHAMPION"}:
    raise SystemExit("UNKNOWN_FOLD_ROLE")
if decisions["final_winner_certification_authorized"].astype(str).str.lower().ne("false").any():
    raise SystemExit("FINAL_WINNER_AUTHORITY_DRIFT")
if decisions["forecast_generation_authorized"].astype(str).str.lower().ne("false").any():
    raise SystemExit("FORECAST_AUTHORITY_DRIFT")
if not diagnostics.empty:
    raise SystemExit("BLOCKING_DIAGNOSTICS_PRESENT")
print("PASS_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_EXECUTION_SUMMARY")
for key in [
    "refinement_group_rows", "parameter_candidate_rows", "candidate_scorecard_rows",
    "preserved_fold_rows", "fold_assignment_rows", "preliminary_refined_leader_rows",
    "round_one_leader_retained_rows", "boundary_expansion_required_rows",
    "insufficient_evidence_rows", "blocking_diagnostic_rows",
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
    throw "GATE_FAILED:refinement execution ZIP was not generated"
}
$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "ADAPTIVE_REFINEMENT_EXECUTION_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "ADAPTIVE_REFINEMENT_EXECUTION_ZIP_SHA256=$Hash" -ForegroundColor Green

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

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_EXECUTION" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE" -ForegroundColor Green
Write-Host "PRESERVED_ROUND_ONE_FOLDS=TRUE" -ForegroundColor Green
Write-Host "NO_UPSTREAM_REBUILD_PERFORMED=TRUE" -ForegroundColor Green
Write-Host "NO_LIVE_NETWORK_COLLECTION_PERFORMED=TRUE" -ForegroundColor Green
Write-Host "FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "FORECAST_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "RANKING_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE" -ForegroundColor Yellow
