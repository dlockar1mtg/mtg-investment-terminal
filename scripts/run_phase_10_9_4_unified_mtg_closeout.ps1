$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "Running Phase 10.9.4 focused closeout tests..."
python -m pytest `
    tests/test_phase_10_9_unified_mtg_closeout.py `
    tests/test_unified_mtg_intelligence.py `
    -q

if ($LASTEXITCODE -ne 0) {
    throw "Phase 10.9.4 focused tests failed."
}

Write-Host ""
Write-Host "Running broader MTG production tests..."
python -m pytest `
    tests/test_full_registry_secret_lair_portfolio.py `
    tests/test_full_secret_lair_model_evaluation.py `
    tests/test_phase_10_secret_lair_production_closeout.py `
    tests/test_collector_booster_box_governed_registry.py `
    tests/test_collector_booster_box_market_value_admission.py `
    tests/test_collector_booster_box_full_evaluation.py `
    tests/test_pre_collector_booster_box_governed_registry.py `
    tests/test_unified_mtg_intelligence.py `
    tests/test_phase_10_9_unified_mtg_closeout.py `
    -q

if ($LASTEXITCODE -ne 0) {
    throw "Broader MTG production tests failed."
}

Write-Host ""
Write-Host "Certifying Phase 10.9.4 production closeout..."
python scripts/certify_phase_10_9_unified_mtg_closeout.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 10.9.4 production closeout certification failed."
}

$CloseoutRoot = ".\data\validation\phase_10\unified_mtg_closeout"

Write-Host ""
Write-Host "Certification"
Get-Content `
    (Join-Path $CloseoutRoot "PHASE_10_9_4_UNIFIED_MTG_PRODUCTION_CLOSEOUT.md")

Write-Host ""
Write-Host "Tracked commit allowlist"
Get-Content `
    (Join-Path $CloseoutRoot "phase_10_9_tracked_commit_allowlist.txt")

Write-Host ""
Write-Host "Repository status"
git status --short

Write-Host ""
Write-Host "Staged files"
git diff --cached --name-only

Write-Host ""
Write-Host "Generated closeout outputs remain local and must not be staged."
