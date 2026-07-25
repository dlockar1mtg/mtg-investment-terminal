$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$RegistryManifest = ".\data\validation\phase_10\unified_mtg_registry\unified_mtg_product_registry_manifest.json"
$PortfolioManifest = ".\data\validation\phase_10\unified_mtg_portfolio\unified_mtg_portfolio_manifest.json"
$IntelligenceManifest = ".\data\validation\phase_10\unified_mtg_intelligence\unified_mtg_intelligence_manifest.json"
$CloseoutManifest = ".\data\validation\phase_10\unified_mtg_closeout\phase_10_9_unified_mtg_production_closeout.json"

Write-Host "Checking Phase 10.9 certified export prerequisites..."

if (-not (Test-Path $RegistryManifest)) {
    throw "Missing unified MTG registry manifest: $RegistryManifest. The local Phase 10.9.1B registry output must exist before Phase 10.10 can run."
}

if (-not (Test-Path $PortfolioManifest)) {
    Write-Host "Phase 10.9 portfolio manifest is missing. Rebuilding Phase 10.9.2..."
    powershell -ExecutionPolicy Bypass -File ".\scripts\run_phase_10_9_2_unified_mtg_portfolio.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not (Test-Path $IntelligenceManifest)) {
    Write-Host "Phase 10.9 intelligence manifest is missing. Rebuilding Phase 10.9.3..."
    powershell -ExecutionPolicy Bypass -File ".\scripts\run_phase_10_9_3_unified_mtg_intelligence.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not (Test-Path $CloseoutManifest)) {
    Write-Host "Phase 10.9 closeout manifest is missing. Regenerating Phase 10.9.4 closeout..."
    powershell -ExecutionPolicy Bypass -File ".\scripts\run_phase_10_9_4_unified_mtg_closeout.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

foreach ($RequiredManifest in @(
    $RegistryManifest,
    $PortfolioManifest,
    $IntelligenceManifest,
    $CloseoutManifest
)) {
    if (-not (Test-Path $RequiredManifest)) {
        throw "Required certified prerequisite was not produced: $RequiredManifest"
    }
}

Write-Host "Phase 10.9 prerequisites are available."
Write-Host ""
Write-Host "Building Phase 10.10 universal export package..."
python .\scripts\build_phase_10_10_universal_export.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Validating Phase 10.10 universal export package..."
python .\scripts\validate_phase_10_10_universal_export.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Running focused Phase 10.10 tests..."
python -m pytest .\tests\test_phase_10_10_universal_export.py -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Latest = ".\data\validation\phase_10\universal_export\latest"

Write-Host ""
Write-Host "Export package files"
Get-ChildItem $Latest -File |
    Select-Object Name, Length |
    Format-Table -AutoSize

Write-Host ""
Write-Host "Platform status"
Import-Csv (Join-Path $Latest "platform_status.csv") |
    Format-List

Write-Host ""
Write-Host "Portfolio summary"
Import-Csv (Join-Path $Latest "portfolio_summary.csv") |
    Format-Table -AutoSize

Write-Host ""
Write-Host "Package summary"
Get-Content (Join-Path $Latest "package_summary.json")

Write-Host ""
Write-Host "Repository status"
git status --short

Write-Host ""
Write-Host "Staged files"
git diff --cached --name-only

Write-Host ""
Write-Host "Generated universal export outputs remain local and must not be staged."
