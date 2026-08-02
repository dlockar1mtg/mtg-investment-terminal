Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedBranch = "phase-8.2.8a-august1-snapshot-bound-current-product-rebuild"
$GovernanceContract = "config\mtg\standards\collector_canonical_identity_lineage_recertification_contract_v1.json"
$CertificationScript = "scripts\certify_collector_v1_canonical_identity_lineage.py"
$CertificationTest = "tests\test_collector_v1_canonical_identity_lineage_recertification.py"
$LorwynContractTest = "tests\test_collector_v1_early_awareness_lorwyn_forecast.py"
$OutputDirectory = "data\governance\permanence\certification\collector_v1_canonical_identity_lineage_recertification"
$SummaryPath = Join-Path $OutputDirectory "collector_canonical_identity_lineage_recertification_summary.json"
$SemanticPath = Join-Path $OutputDirectory "collector_lorwyn_pre_simulation_semantic_certification.json"
$FinalForecastPath = Join-Path $OutputDirectory "collector_final_authority_bound_49_product_forecasts.csv"
$BlockedPath = Join-Path $OutputDirectory "collector_final_authority_bound_blocked_horizons.csv"
$LineagePath = Join-Path $OutputDirectory "collector_final_forecast_source_identity_lineage_manifest.csv"
$BaseAuditPath = Join-Path $OutputDirectory "collector_base_48_forecast_identity_recertification.csv"
$EarlyAuditPath = Join-Path $OutputDirectory "collector_early_awareness_identity_recertification.csv"
$InvalidationPath = Join-Path $OutputDirectory "collector_invalidated_output_ledger.csv"
$LorwynForecastPath = Join-Path $OutputDirectory "collector_authority_bound_lorwyn_forecasts.csv"

function Fail-Governance {
    param([string]$Message, [int]$Code = 1)
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "COLLECTOR GOVERNANCE EXECUTION BLOCKED"
    Write-Host "============================================================"
    Write-Host $Message -ForegroundColor Red
    Write-Host "No calibration was authorized." -ForegroundColor Red
    Write-Host "No ranking was authorized." -ForegroundColor Red
    Write-Host "No purchase recommendation was authorized." -ForegroundColor Red
    exit $Code
}

Write-Host ""
Write-Host "============================================================"
Write-Host "COLLECTOR PROJECT STATUS"
Write-Host "============================================================"
Write-Host "COMPLETED / CERTIFIED"
Write-Host "1. Product-specific contracts no longer assert identity."
Write-Host "2. Certified authority is the exclusive identity source."
Write-Host "3. Authority-path existence tests are installed."
Write-Host ""
Write-Host "CURRENTLY WORKING ON"
Write-Host "4. Reconcile all 50 governed products."
Write-Host "5. Recertify 288 base forecast rows."
Write-Host "6. Recertify early-awareness identity lineage."
Write-Host "7. Invalidate incorrect derived outputs."
Write-Host "8. Rebuild Lorwyn after semantic certification."
Write-Host "9. Close lineage for all 294 final forecasts."
Write-Host ""
Write-Host "STILL OUTSTANDING"
Write-Host "10. Probabilistic calibration."
Write-Host "11. Final rankings."
Write-Host "12. Product analysis and purchase authorization."

$currentBranch = git branch --show-current
if ($LASTEXITCODE -ne 0) { Fail-Governance "Git branch could not be read." 801 }
if ($currentBranch -ne $ExpectedBranch) { Fail-Governance "Expected branch $ExpectedBranch but found $currentBranch." 802 }

$startingStatus = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) { Fail-Governance "Git status could not be read." 803 }
if ($startingStatus.Count -ne 0) {
    $startingStatus | ForEach-Object { Write-Host $_ }
    Fail-Governance "Working tree is not clean." 804
}

Write-Host ""
Write-Host "============================================================"
Write-Host "STEP 1 — VERIFY DECLARED AUTHORITIES"
Write-Host "============================================================"

if (-not (Test-Path $GovernanceContract -PathType Leaf)) {
    Fail-Governance "Governance contract is missing." 805
}

$governance = Get-Content $GovernanceContract -Raw | ConvertFrom-Json
$authorityChecks = @()
foreach ($property in $governance.authorities.PSObject.Properties) {
    $relativePath = [string]$property.Value
    $windowsPath = $relativePath.Replace("/", [IO.Path]::DirectorySeparatorChar)
    $exists = Test-Path $windowsPath -PathType Leaf
    $rowCount = $null
    if ($exists -and $windowsPath.EndsWith(".csv", [StringComparison]::OrdinalIgnoreCase)) {
        $rowCount = @(Import-Csv $windowsPath).Count
    }
    $authorityChecks += [pscustomobject]@{
        authority = $property.Name
        path = $relativePath
        exists = $exists
        rows = $rowCount
    }
}

$authorityChecks | Format-Table -Wrap -AutoSize
$missingAuthorities = @($authorityChecks | Where-Object { $_.exists -ne $true })
if ($missingAuthorities.Count -ne 0) {
    Fail-Governance "At least one declared authority is missing." 806
}

Write-Host "PASS: Every declared authority exists." -ForegroundColor Green

Write-Host ""
Write-Host "============================================================"
Write-Host "STEP 2 — RUN GOVERNANCE TESTS"
Write-Host "============================================================"

python -m py_compile $CertificationScript
if ($LASTEXITCODE -ne 0) { Fail-Governance "Recertification engine does not compile." 807 }

python -m pytest `
    $CertificationTest `
    $LorwynContractTest `
    tests\test_collector_v1_complete_horizon_probabilistic_forecasts.py `
    tests\test_collector_v1_final_model_output_validation.py `
    -q
if ($LASTEXITCODE -ne 0) { Fail-Governance "Governance-focused tests failed." 808 }

Write-Host "PASS: Governance-focused tests passed." -ForegroundColor Green

Write-Host ""
Write-Host "============================================================"
Write-Host "STEP 3 — RUN FULL RECERTIFICATION"
Write-Host "============================================================"

python $CertificationScript
$certificationExitCode = $LASTEXITCODE

$requiredOutputs = @(
    $SummaryPath,
    $SemanticPath,
    $FinalForecastPath,
    $BlockedPath,
    $LineagePath,
    $BaseAuditPath,
    $EarlyAuditPath,
    $InvalidationPath,
    $LorwynForecastPath
)
$missingOutputs = @($requiredOutputs | Where-Object { -not (Test-Path $_ -PathType Leaf) })
if ($missingOutputs.Count -ne 0) {
    $missingOutputs | ForEach-Object { Write-Host $_ -ForegroundColor Red }
    Fail-Governance "One or more recertification outputs are missing." 809
}

$summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
$semantic = Get-Content $SemanticPath -Raw | ConvertFrom-Json
$finalRows = @(Import-Csv $FinalForecastPath)
$blockedRows = @(Import-Csv $BlockedPath)
$lineageRows = @(Import-Csv $LineagePath)
$baseAuditRows = @(Import-Csv $BaseAuditPath)
$earlyAuditRows = @(Import-Csv $EarlyAuditPath)
$lorwynRows = @(Import-Csv $LorwynForecastPath)

Write-Host ""
Write-Host "============================================================"
Write-Host "RECERTIFICATION SUMMARY"
Write-Host "============================================================"
Write-Host "Status:                          $($summary.status)"
Write-Host "Governed products:               $($summary.governed_products)"
Write-Host "Products reconciled:             $($summary.products_reconciled)"
Write-Host "Base forecast rows recertified:  $($summary.base_forecast_rows_recertified)"
Write-Host "Early-awareness rows audited:    $($summary.early_awareness_rows_audited)"
Write-Host "Early-awareness rows certified:  $($summary.early_awareness_rows_recertified)"
Write-Host "Lorwyn semantic status:          $($summary.lorwyn_pre_simulation_semantic_status)"
Write-Host "Lorwyn forecast rows:            $($summary.lorwyn_forecast_rows)"
Write-Host "Final forecast products:         $($summary.final_forecast_products)"
Write-Host "Final forecast rows:             $($summary.final_forecast_rows)"
Write-Host "Blocked rows:                    $($summary.blocked_rows)"
Write-Host "Coverage rows:                   $($summary.coverage_rows)"
Write-Host "Lineage rows:                    $($summary.lineage_rows)"
Write-Host "Closed lineage rows:             $($summary.lineage_rows_closed)"

if ($certificationExitCode -ne 0) {
    $summary.critical_failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Fail-Governance "Canonical identity and lineage recertification did not pass." $certificationExitCode
}

$failedBase = @($baseAuditRows | Where-Object { $_.recertified -ne "True" })
$failedEarly = @($earlyAuditRows | Where-Object { $_.identity_reconciled -ne "True" })
$openLineage = @($lineageRows | Where-Object { $_.lineage_closed -ne "True" })
$uniqueKeys = @($finalRows | ForEach-Object { "$($_.canonical_product_id)|$($_.horizon_days)" } | Select-Object -Unique)
$uniqueProducts = @($finalRows | Select-Object -ExpandProperty canonical_product_id -Unique)

$summaryValid = (
    $summary.status -eq "PASS_COLLECTOR_CANONICAL_IDENTITY_LINEAGE_RECERTIFICATION" -and
    $summary.governed_products -eq 50 -and
    $summary.products_reconciled -eq 50 -and
    $summary.manual_identity_assertion_violations -eq 0 -and
    $summary.unknown_identity_rows -eq 0 -and
    $summary.name_identity_mismatches -eq 0 -and
    $summary.base_forecast_rows_recertified -eq 288 -and
    $summary.early_awareness_rows_audited -eq $summary.early_awareness_rows_recertified -and
    $summary.lorwyn_pre_simulation_semantic_status -eq "PASS_LORWYN_PRE_SIMULATION_SEMANTIC_CERTIFICATION" -and
    $summary.lorwyn_forecast_rows -eq 6 -and
    $summary.final_forecast_products -eq 49 -and
    $summary.final_forecast_rows -eq 294 -and
    $summary.blocked_rows -eq 6 -and
    $summary.coverage_rows -eq 300 -and
    $summary.lineage_rows -eq 294 -and
    $summary.lineage_rows_closed -eq 294 -and
    $summary.critical_failures.Count -eq 0 -and
    $failedBase.Count -eq 0 -and
    $failedEarly.Count -eq 0 -and
    $openLineage.Count -eq 0 -and
    $lorwynRows.Count -eq 6 -and
    $finalRows.Count -eq 294 -and
    $uniqueKeys.Count -eq 294 -and
    $uniqueProducts.Count -eq 49 -and
    $blockedRows.Count -eq 6
)
if (-not $summaryValid) { Fail-Governance "Final authority-bound recertification does not reconcile." 810 }

Write-Host ""
Write-Host "============================================================"
Write-Host "LORWYN PRE-SIMULATION CERTIFICATION"
Write-Host "============================================================"
Write-Host "Status:                    $($semantic.status)"
Write-Host "Requested product:         $($semantic.requested_product_name)"
Write-Host "Resolved canonical ID:     $($semantic.resolved_canonical_product_id)"
Write-Host "Resolved TCGplayer ID:     $($semantic.resolved_tcgplayer_product_id)"
Write-Host "Resolved product name:     $($semantic.resolved_product_name)"
Write-Host "Resolved current price:    $($semantic.resolved_current_price)"
Write-Host "Base forecast collision:   $($semantic.base_forecast_collision)"
Write-Host "Simulation authorized:     $($semantic.simulation_authorized)"

Write-Host ""
Write-Host "============================================================"
Write-Host "STEP 4 — RUN COMPLETE COLLECTOR REGRESSION"
Write-Host "============================================================"

$collectorTests = @(Get-ChildItem tests -File -Filter "test_collector_v1*.py" | Select-Object -ExpandProperty FullName)
python -m pytest $collectorTests -q
if ($LASTEXITCODE -ne 0) { Fail-Governance "Complete Collector regression suite failed." 811 }

$finalStatus = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) { Fail-Governance "Final Git status could not be read." 812 }
if ($finalStatus.Count -ne 0) {
    $finalStatus | ForEach-Object { Write-Host $_ }
    Fail-Governance "Repository is not clean after recertification." 813
}

Write-Host ""
Write-Host "============================================================"
Write-Host "COLLECTOR PROJECT STATUS AFTER EXECUTION"
Write-Host "============================================================"
Write-Host "COMPLETED / CERTIFIED"
Write-Host "1. All 50 governed products reconciled."
Write-Host "2. All 288 base forecast rows recertified."
Write-Host "3. All early-awareness identities recertified."
Write-Host "4. Incorrect derived outputs invalidated."
Write-Host "5. Lorwyn rebuilt only after semantic certification."
Write-Host "6. Final 49-product forecast authority created."
Write-Host "7. All 294 final forecasts have closed lineage."
Write-Host ""
Write-Host "CURRENTLY WORKING ON"
Write-Host "8. Probabilistic calibration and reasonableness review."
Write-Host ""
Write-Host "STILL OUTSTANDING"
Write-Host "9. Final rankings."
Write-Host "10. Product analysis and purchase authorization."
Write-Host ""
Write-Host "OVERALL RESULT: CANONICAL IDENTITY AND LINEAGE RECERTIFIED" -ForegroundColor Green
Write-Host "RANKING STATUS: BLOCKED" -ForegroundColor Yellow
Write-Host "PURCHASE STATUS: BLOCKED" -ForegroundColor Yellow
exit 0
