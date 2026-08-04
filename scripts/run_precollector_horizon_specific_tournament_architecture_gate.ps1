$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Branch = "phase-8.3-precollector-scope-governance"
$OutputDir = Join-Path $Root "artifacts\precollector\horizon_specific_tournament_architecture"
$ZipPath = Join-Path $env:TEMP "MTG_PreCollector_Horizon_Specific_Tournament_Architecture_v1.zip"

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

Invoke-Step "Scope governance audit" { python .\scripts\audit_precollector_scope_governance.py }
Invoke-Step "Horizon architecture tests" { python -m pytest .\tests\test_precollector_horizon_specific_tournament_architecture.py -q }
Invoke-Step "Build horizon-specific tournament architecture" { python .\scripts\build_precollector_horizon_specific_tournament_architecture.py }

Invoke-Step "Validate horizon architecture summary" {
    @'
import json
from pathlib import Path

root = Path.cwd()
out = root / "artifacts/precollector/horizon_specific_tournament_architecture"
summary_path = out / "precollector_horizon_specific_tournament_architecture_summary.json"
required = [
    summary_path,
    out / "precollector_horizon_specific_tournament_architecture.csv",
    out / "precollector_horizon_route_model_eligibility.csv",
    out / "precollector_horizon_validation_policy.csv",
    out / "precollector_horizon_architecture_diagnostics.csv",
    out / "precollector_horizon_specific_tournament_architecture_manifest.json",
]
for path in required:
    if not path.is_file():
        raise SystemExit(f"MISSING_OUTPUT:{path.name}")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
expected = {
    "certification_status": "PASS",
    "active_product_rows": 79,
    "forecast_horizon_count": 5,
    "product_horizon_input_rows": 395,
    "route_count": 3,
    "candidate_model_eligibility_rows": 65,
    "validation_metric_rows": 6,
    "blocking_diagnostic_rows": 0,
    "independent_tournament_per_horizon": True,
    "next_stage": "PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_EXECUTION",
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
print("PASS_PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_ARCHITECTURE_SUMMARY")
for key in ["active_product_rows", "forecast_horizon_count", "product_horizon_input_rows", "route_count", "candidate_model_eligibility_rows", "validation_metric_rows"]:
    print(f"{key.upper()}={summary[key]}")
print(f"AUTHORIZED_NEXT_STAGE={summary['next_stage']}")
'@ | python -
}

Invoke-Step "Full repository regression suite" { python -m pytest -q }

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $ZipPath -Force
if (-not (Test-Path $ZipPath)) { throw "GATE_FAILED:certified ZIP was not generated" }
$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "HORIZON_ARCHITECTURE_ZIP=$ZipPath" -ForegroundColor Green
Write-Host "HORIZON_ARCHITECTURE_ZIP_SHA256=$Hash" -ForegroundColor Green

$ArtifactsRoot = Join-Path $Root "artifacts\precollector"
if (Test-Path $ArtifactsRoot) { Remove-Item $ArtifactsRoot -Recurse -Force }

$DirtyEnd = git status --porcelain
if ($DirtyEnd) {
    Write-Host $DirtyEnd
    throw "GATE_FAILED:working tree is not clean after artifact cleanup"
}

Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_ARCHITECTURE_GATE" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_EXECUTION" -ForegroundColor Green
Write-Host "FORECAST_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "RANKING_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE" -ForegroundColor Yellow
Write-Host "UIP_DELIVERY_AUTHORIZED=FALSE" -ForegroundColor Yellow
