& {
    $ErrorActionPreference = "Stop"
    Set-StrictMode -Version Latest

    function Stop-GovernedRun {
        param([Parameter(Mandatory=$true)][string]$Message)
        Write-Host "FAIL: $Message" -ForegroundColor Red
        throw "GOVERNED_RUN_FAILED"
    }

    function Invoke-GovernedStep {
        param(
            [Parameter(Mandatory=$true)][string]$Name,
            [Parameter(Mandatory=$true)][scriptblock]$Action
        )
        Write-Host "`n=== $Name ===" -ForegroundColor Cyan
        & $Action
        if ($LASTEXITCODE -ne 0) {
            Stop-GovernedRun "$Name returned exit code $LASTEXITCODE"
        }
        Write-Host "PASS: $Name" -ForegroundColor Green
    }

    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
    Set-Location $RepositoryRoot

    $ExpectedBranch = "phase-8.3-precollector-scope-governance"
    $CurrentBranch = (git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { Stop-GovernedRun "Unable to determine current Git branch" }
    if ($CurrentBranch -ne $ExpectedBranch) {
        Stop-GovernedRun "Expected branch '$ExpectedBranch' but found '$CurrentBranch'"
    }

    $StatusBefore = git status --porcelain
    if ($LASTEXITCODE -ne 0) { Stop-GovernedRun "Unable to inspect Git status" }
    if ($StatusBefore) { Stop-GovernedRun "Working tree is not clean before testing" }

    Invoke-GovernedStep "Fetch remote state" { git fetch origin }

    $LocalHead = (git rev-parse HEAD).Trim()
    $RemoteHead = (git rev-parse "origin/$ExpectedBranch").Trim()
    if ($LASTEXITCODE -ne 0) { Stop-GovernedRun "Unable to compare local and remote branch heads" }
    if ($LocalHead -ne $RemoteHead) {
        Stop-GovernedRun "Local branch is not synchronized with origin. Run git pull --ff-only and rerun."
    }

    Invoke-GovernedStep "Parse governance JSON controls" {
        python -c "import json, pathlib; [json.load(open(p, encoding='utf-8')) for p in [pathlib.Path('config/mtg/governance/mtg_github_first_governed_execution_workflow_v1.json'), pathlib.Path('config/mtg/governance/precollector_booster_product_scope_owner_decision_v1.json')]]; print('PASS_JSON_PARSE')"
    }

    Invoke-GovernedStep "Pre-Collector scope governance and MTG-standard audit" {
        python scripts/audit_precollector_scope_governance.py
    }

    if (Test-Path "tests") {
        Invoke-GovernedStep "Relevant Pre-Collector and governance pytest selection" {
            python -m pytest -q tests -k "precollector or governance or mtg_standard"
        }
    }

    Invoke-GovernedStep "Full repository regression suite" {
        python -m pytest -q
    }

    $StatusAfter = git status --porcelain
    if ($LASTEXITCODE -ne 0) { Stop-GovernedRun "Unable to inspect final Git status" }
    if ($StatusAfter) { Stop-GovernedRun "Tests modified the working tree" }

    Write-Host "`nCERTIFIED_PASS_PRECOLLECTOR_SCOPE_GOVERNANCE_GATE" -ForegroundColor Green
    Write-Host "AUTHORIZED_NEXT_STAGE=CANDIDATE_UNIVERSE_INVENTORY_ONLY" -ForegroundColor Green
    Write-Host "FORECAST_AUTHORIZED=FALSE"
    Write-Host "RANKING_AUTHORIZED=FALSE"
    Write-Host "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
    Write-Host "AUTOMATIC_EXECUTION_AUTHORIZED=FALSE"
}
