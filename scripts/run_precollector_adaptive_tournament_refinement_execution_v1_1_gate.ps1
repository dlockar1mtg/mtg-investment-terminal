$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Branch = "phase-8.3-precollector-scope-governance"
$OutputDir = Join-Path $Root "artifacts\precollector\adaptive_tournament_refinement_execution"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Adaptive_Tournament_Refinement_Execution_v1_1.zip"

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
    throw "GATE_FAILED:working tree must be clean before repaired execution"
}

Invoke-Step "Round Two repair tests" {
    python -m pytest `
        .\tests\test_precollector_adaptive_tournament_refinement_execution.py `
        .\tests\test_precollector_adaptive_tournament_refinement_execution_v1_1.py `
        -q
}

if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}

Invoke-Step "Execute repaired Round Two tournament" {
    python .\scripts\run_precollector_adaptive_tournament_refinement_execution_v1_1.py
}

Invoke-Step "Validate repaired Round Two decisions" {
    @'
import json
from pathlib import Path
import pandas as pd

root = Path.cwd()
out = root / "artifacts/precollector/adaptive_tournament_refinement_execution"
summary = json.loads((out / "precollector_round_two_execution_summary.json").read_text(encoding="utf-8"))
decisions = pd.read_csv(out / "precollector_round_two_preliminary_group_decisions.csv")
scorecard = pd.read_csv(out / "precollector_round_two_candidate_scorecard.csv")
folds = pd.read_csv(out / "precollector_round_two_fold_assignment.csv")

if summary.get("certification_status") != "PASS":
    raise SystemExit("REPAIRED_EXECUTION_NOT_CERTIFIED")
if summary.get("round_one_selected_model_binding_verified") is not True:
    raise SystemExit("ROUND_ONE_SELECTED_MODEL_BINDING_NOT_VERIFIED")
if summary.get("round_one_selected_model_rows") != 15:
    raise SystemExit(f"ROUND_ONE_SELECTED_MODEL_COUNT_FAILURE:{summary.get('round_one_selected_model_rows')}")
if summary.get("short_horizon_insufficient_evidence_rows") != 0:
    raise SystemExit(f"SHORT_HORIZON_EVIDENCE_FAILURE:{summary.get('short_horizon_insufficient_evidence_rows')}")
if summary.get("long_horizon_insufficient_evidence_rows") != 6:
    raise SystemExit(f"LONG_HORIZON_EVIDENCE_COUNT_FAILURE:{summary.get('long_horizon_insufficient_evidence_rows')}")
if summary.get("long_horizon_monte_carlo_required") is not True:
    raise SystemExit("LONG_HORIZON_MONTE_CARLO_REQUIREMENT_MISSING")
if len(decisions) != 15 or len(scorecard) != 2011 or len(folds) != 1992:
    raise SystemExit("REPAIRED_EXECUTION_CARDINALITY_FAILURE")
short = decisions[decisions["horizon_code"].isin(["D90", "D180", "D365"])]
long = decisions[decisions["horizon_code"].isin(["Y3", "Y5"])]
if short["round_one_model"].fillna("").eq("").any():
    raise SystemExit("SHORT_HORIZON_ROUND_ONE_MODEL_MISSING")
if short["selection_status"].eq("NO_PROMOTION_INSUFFICIENT_EVIDENCE").any():
    raise SystemExit("SHORT_HORIZON_STILL_MARKED_INSUFFICIENT")
if not long["selection_status"].eq("NO_PROMOTION_INSUFFICIENT_EVIDENCE").all():
    raise SystemExit("LONG_HORIZON_DIRECT_EVIDENCE_POLICY_DRIFT")
print("PASS_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_EXECUTION_V1_1_SUMMARY")
for key in [
    "preliminary_refined_leader_rows",
    "round_one_leader_retained_rows",
    "boundary_expansion_required_rows",
    "short_horizon_insufficient_evidence_rows",
    "long_horizon_insufficient_evidence_rows",
]:
    print(f"{key.upper()}={summary[key]}")
print("ROUND_ONE_SELECTED_MODEL_ROWS=15")
print("LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE")
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
    throw "GATE_FAILED:repaired Round Two ZIP was not generated"
}
$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "REPAIRED_ROUND_TWO_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "REPAIRED_ROUND_TWO_ZIP_SHA256=$Hash" -ForegroundColor Green

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
    throw "GATE_FAILED:working tree is not clean after repaired execution"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_EXECUTION_V1_1" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE" -ForegroundColor Green
Write-Host "ROUND_ONE_SELECTED_MODEL_BINDING=TRUE" -ForegroundColor Green
Write-Host "SHORT_HORIZON_INSUFFICIENT_EVIDENCE_ROWS=0" -ForegroundColor Green
Write-Host "LONG_HORIZON_INSUFFICIENT_EVIDENCE_ROWS=6" -ForegroundColor Yellow
Write-Host "LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE" -ForegroundColor Yellow
Write-Host "FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "FORECAST_AUTHORIZED=FALSE" -ForegroundColor Yellow
