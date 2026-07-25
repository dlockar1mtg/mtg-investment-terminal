$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

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
