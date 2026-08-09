$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ExpectedBranch = "phase-8.3-precollector-scope-governance"
$OutputDirectory = Join-Path $RepositoryRoot "artifacts\precollector\recovery_state_audit"
$PackagePath = Join-Path $env:TEMP "MTG_PreCollector_Recovery_State_Audit_v1.zip"

Set-Location $RepositoryRoot

function Assert-LastExitCode([string]$Message) {
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

Write-Host "`n=== Fetch GitHub state ===" -ForegroundColor Cyan
git fetch origin
Assert-LastExitCode "RECOVERY_AUDIT_FAILED: git fetch origin failed"
Write-Host "PASS: Fetch GitHub state" -ForegroundColor Green

Write-Host "`n=== Fast-forward governed branch ===" -ForegroundColor Cyan
git pull --ff-only origin $ExpectedBranch
Assert-LastExitCode "RECOVERY_AUDIT_FAILED: git pull --ff-only failed"
Write-Host "PASS: Fast-forward governed branch" -ForegroundColor Green

$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "RECOVERY_AUDIT_FAILED: wrong branch $CurrentBranch"
}

$StartingStatus = git status --porcelain --untracked-files=all
if ($StartingStatus) {
    Write-Host $StartingStatus
    throw "RECOVERY_AUDIT_FAILED: repository must be clean before audit"
}

$CurrentHead = (git rev-parse HEAD).Trim()
Write-Host "PASS_GITHUB_HEAD_BINDING=$CurrentHead" -ForegroundColor Green

if (Test-Path $OutputDirectory) {
    Remove-Item $OutputDirectory -Recurse -Force
}
if (Test-Path $PackagePath) {
    Remove-Item $PackagePath -Force
}

Write-Host "`n=== Recovery state audit tests ===" -ForegroundColor Cyan
python -m pytest -q tests/test_precollector_recovery_state_audit.py
Assert-LastExitCode "RECOVERY_AUDIT_FAILED: targeted recovery audit tests failed"
Write-Host "PASS: Recovery state audit tests" -ForegroundColor Green

Write-Host "`n=== Execute read-only recovery state audit ===" -ForegroundColor Cyan
python scripts/audit_precollector_recovery_state.py
Assert-LastExitCode "RECOVERY_AUDIT_FAILED: recovery state audit failed"
Write-Host "PASS: Execute read-only recovery state audit" -ForegroundColor Green

Write-Host "`n=== Full repository regression suite ===" -ForegroundColor Cyan
python -m pytest -q
Assert-LastExitCode "RECOVERY_AUDIT_FAILED: full repository regression failed"
Write-Host "PASS: Full repository regression suite" -ForegroundColor Green

if (-not (Test-Path $OutputDirectory)) {
    throw "RECOVERY_AUDIT_FAILED: output directory missing"
}

Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $PackagePath -Force
$PackageHash = (Get-FileHash $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PRECOLLECTOR_RECOVERY_STATE_AUDIT_ZIP=$PackagePath" -ForegroundColor Green
Write-Host "PRECOLLECTOR_RECOVERY_STATE_AUDIT_ZIP_SHA256=$PackageHash" -ForegroundColor Green

Remove-Item $OutputDirectory -Recurse -Force
$PreCollectorRoot = Join-Path $RepositoryRoot "artifacts\precollector"
if ((Test-Path $PreCollectorRoot) -and -not (Get-ChildItem $PreCollectorRoot -Force -ErrorAction SilentlyContinue)) {
    Remove-Item $PreCollectorRoot -Force
}

$FinalStatus = git status --porcelain --untracked-files=all
if ($FinalStatus) {
    Write-Host $FinalStatus
    throw "RECOVERY_AUDIT_FAILED: repository is not clean after audit"
}

Write-Host "PASS_TRANSIENT_OUTPUT_CLEANUP=TRUE" -ForegroundColor Green
Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_RECOVERY_STATE_AUDIT" -ForegroundColor Green
Write-Host "AUTHORIZED_NEXT_STAGE=OWNER_REVIEW_OF_PRECOLLECTOR_RECOVERY_STATE" -ForegroundColor Green
Write-Host "FORECAST_EXECUTION_AUTHORIZED=FALSE" -ForegroundColor Green
Write-Host "RANKING_EXECUTION_AUTHORIZED=FALSE" -ForegroundColor Green
Write-Host "PURCHASE_ANALYSIS_AUTHORIZED=FALSE" -ForegroundColor Green
