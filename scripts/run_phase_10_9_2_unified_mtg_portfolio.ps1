$ErrorActionPreference = "Stop"

Set-Location "C:\Users\DevonLockard\mtg-investment-terminal"

python -m py_compile `
    ".\scripts\build_unified_mtg_portfolio.py"

python `
    ".\scripts\build_unified_mtg_portfolio.py"

if ($LASTEXITCODE -ne 0) {
    throw "Phase 10.9.2 unified MTG portfolio certification failed."
}

$OutputRoot = `
    ".\data\validation\phase_10\unified_mtg_portfolio"

Write-Host ""
Write-Host "Lane summary"
Import-Csv `
    (Join-Path `
        $OutputRoot `
        "unified_mtg_portfolio_lane_summary.csv"
    ) |
Format-Table -AutoSize

Write-Host ""
Write-Host "Certification"
Get-Content `
    (Join-Path `
        $OutputRoot `
        "PHASE_10_9_2_UNIFIED_MTG_PORTFOLIO_CERTIFICATION.md"
    )
