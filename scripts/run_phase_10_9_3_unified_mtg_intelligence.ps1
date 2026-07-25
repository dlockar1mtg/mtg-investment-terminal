$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "Running Phase 10.9.3 unified MTG intelligence build..." -ForegroundColor Cyan
python ".\scripts\build_unified_mtg_intelligence.py"

if ($LASTEXITCODE -ne 0) {
    throw "Phase 10.9.3 certification failed."
}

$OutputRoot = ".\data\validation\phase_10\unified_mtg_intelligence"
$ManifestPath = Join-Path $OutputRoot "unified_mtg_intelligence_manifest.json"
$InterfacePath = Join-Path $OutputRoot "unified_mtg_intelligence_interface.csv"
$DiagnosticsPath = Join-Path $OutputRoot "unified_mtg_intelligence_diagnostics.csv"
$CertificationPath = Join-Path $OutputRoot "PHASE_10_9_3_UNIFIED_MTG_INTELLIGENCE_CERTIFICATION.md"

Write-Host "`nFocused tests" -ForegroundColor Cyan
python -m pytest ".\tests\test_unified_mtg_intelligence.py" -q
if ($LASTEXITCODE -ne 0) {
    throw "Phase 10.9.3 focused tests failed."
}

Write-Host "`nLane and eligibility summary" -ForegroundColor Cyan
$Rows = Import-Csv $InterfacePath
$Rows |
    Group-Object lane |
    Sort-Object Name |
    ForEach-Object {
        [PSCustomObject]@{
            Lane = $_.Name
            Products = $_.Count
            ForecastEligible = ($_.Group | Where-Object forecast_eligible -eq "YES").Count
            RecommendationEligible = ($_.Group | Where-Object recommendation_eligible -eq "YES").Count
        }
    } |
    Format-Table -AutoSize

Write-Host "`nDiagnostics" -ForegroundColor Cyan
$Diagnostics = Import-Csv $DiagnosticsPath
if ($Diagnostics.Count -eq 0) {
    Write-Host "None"
} else {
    $Diagnostics | Format-Table -Wrap -AutoSize
}

Write-Host "`nCertification" -ForegroundColor Cyan
Get-Content $CertificationPath

Write-Host "`nManifest path: $ManifestPath" -ForegroundColor DarkGray
Write-Host "Generated outputs remain local and must not be staged." -ForegroundColor Yellow
