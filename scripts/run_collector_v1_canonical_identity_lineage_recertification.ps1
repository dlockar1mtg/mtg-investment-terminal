Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedBranch = "phase-8.2.8a-august1-snapshot-bound-current-product-rebuild"
$GovernanceContract = "config\mtg\standards\collector_canonical_identity_lineage_recertification_contract_v1.json"
$CertificationScript = "scripts\certify_collector_v1_canonical_identity_lineage.py"
$OutputDirectory = "data\governance\permanence\certification\collector_v1_canonical_identity_lineage_recertification"
$SummaryPath = Join-Path $OutputDirectory "collector_canonical_identity_lineage_recertification_summary.json"
$SemanticPath = Join-Path $OutputDirectory "collector_lorwyn_pre_simulation_semantic_certification.json"
$FinalForecastPath = Join-Path $OutputDirectory "collector_final_authority_bound_49_product_forecasts.csv"
$BlockedPath = Join-Path $OutputDirectory "collector_final_authority_bound_blocked_horizons.csv"
$LineagePath = Join-Path $OutputDirectory "collector_final_forecast_source_identity_lineage_manifest.csv"
$BaseAuditPath = Join-Path $OutputDirectory "collector_base_48_forecast_identity_recertification.csv"
$EarlyAuditPath = Join-Path $OutputDirectory "collector_early_awareness_identity_recertification.csv"
$LorwynForecastPath = Join-Path $OutputDirectory "collector_authority_bound_lorwyn_forecasts.csv"

function Stop-Governance {
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

function Assert-Condition {
    param([bool]$Condition, [string]$Message, [int]$Code)
    if (-not $Condition) {
        Stop-Governance -Message $Message -Code $Code
    }
}

Write-Host ""
Write-Host "============================================================"
Write-Host "COLLECTOR PROJECT STATUS"
Write-Host "============================================================"
Write-Host "COMPLETED / CERTIFIED"
Write-Host "1. Product-specific contracts do not assert identity."
Write-Host "2. Certified authority is the exclusive identity source."
Write-Host "3. The execution runner is committed and syntax-tested."
Write-Host ""
Write-Host "CURRENTLY WORKING ON"
Write-Host "4. Reconcile all 50 governed products."
Write-Host "5. Recertify all 288 base forecasts and early-awareness identities."
Write-Host "6. Invalidate incorrect derived outputs."
Write-Host "7. Semantically certify and rebuild Lorwyn."
Write-Host "8. Close lineage for all 294 final forecasts."
Write-Host ""
Write-Host "STILL OUTSTANDING"
Write-Host "9. Probabilistic calibration."
Write-Host "10. Final rankings and product analysis."

$currentBranch = git branch --show-current
Assert-Condition ($LASTEXITCODE -eq 0) "Git branch could not be read." 821
Assert-Condition ($currentBranch -eq $ExpectedBranch) "Expected branch $ExpectedBranch but found $currentBranch." 822

$startingStatus = @(git status --porcelain)
Assert-Condition ($LASTEXITCODE -eq 0) "Git status could not be read." 823
if ($startingStatus.Count -ne 0) {
    $startingStatus | ForEach-Object { Write-Host $_ }
    Stop-Governance "Working tree is not clean." 824
}

Write-Host ""
Write-Host "============================================================"
Write-Host "STEP 1 — VERIFY DECLARED AUTHORITIES"
Write-Host "============================================================"

Assert-Condition (Test-Path $GovernanceContract -PathType Leaf) "Governance contract is missing." 825
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
Assert-Condition ($missingAuthorities.Count -eq 0) "At least one declared authority is missing." 826
Write-Host "PASS: Every declared authority exists." -ForegroundColor Green

Write-Host ""
Write-Host "============================================================"
Write-Host "STEP 2 — RUN GOVERNANCE TESTS"
Write-Host "============================================================"

python -m py_compile $CertificationScript
Assert-Condition ($LASTEXITCODE -eq 0) "Recertification engine does not compile." 827

python -m pytest `
    tests\test_collector_v1_canonical_identity_lineage_runner.py `
    tests\test_collector_v1_canonical_identity_lineage_recertification.py `
    tests\test_collector_v1_early_awareness_lorwyn_forecast.py `
    tests\test_collector_v1_complete_horizon_probabilistic_forecasts.py `
    tests\test_collector_v1_final_model_output_validation.py `
    -q
Assert-Condition ($LASTEXITCODE -eq 0) "Governance-focused tests failed." 828
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
    $LorwynForecastPath
)
$missingOutputs = @($requiredOutputs | Where-Object { -not (Test-Path $_ -PathType Leaf) })
if ($missingOutputs.Count -ne 0) {
    $missingOutputs | ForEach-Object { Write-Host $_ -ForegroundColor Red }
    Stop-Governance "One or more recertification outputs are missing." 829
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
    Stop-Governance "Canonical identity and lineage recertification did not pass." $certificationExitCode
}

$failedBase = @($baseAuditRows | Where-Object { $_.recertified -ne "True" })
$failedEarly = @($earlyAuditRows | Where-Object { $_.identity_reconciled -ne "True" })
$openLineage = @($lineageRows | Where-Object { $_.lineage_closed -ne "True" })
$keyValues = @($finalRows | ForEach-Object { "$($_.canonical_product_id)|$($_.horizon_days)" })
$uniqueKeys = @($keyValues | Select-Object -Unique)
$uniqueProducts = @($finalRows | Select-Object -ExpandProperty canonical_product_id -Unique)

$checks = @(
    [pscustomobject]@{ Name = "status"; Passed = ($summary.status -eq "PASS_COLLECTOR_CANONICAL_IDENTITY_LINEAGE_RECERTIFICATION") },
    [pscustomobject]@{ Name = "governed_products"; Passed = ($summary.governed_products -eq 50) },
    [pscustomobject]@{ Name = "products_reconciled"; Passed = ($summary.products_reconciled -eq 50) },
    [pscustomobject]@{ Name = "manual_identity_assertions"; Passed = ($summary.manual_identity_assertion_violations -eq 0) },
    [pscustomobject]@{ Name = "unknown_identities"; Passed = ($summary.unknown_identity_rows -eq 0) },
    [pscustomobject]@{ Name = "name_identity_mismatches"; Passed = ($summary.name_identity_mismatches -eq 0) },
    [pscustomobject]@{ Name = "base_rows"; Passed = ($summary.base_forecast_rows_recertified -eq 288 -and $failedBase.Count -eq 0) },
    [pscustomobject]@{ Name = "early_awareness"; Passed = ($summary.early_awareness_rows_audited -eq $summary.early_awareness_rows_recertified -and $failedEarly.Count -eq 0) },
    [pscustomobject]@{ Name = "lorwyn_semantic"; Passed = ($summary.lorwyn_pre_simulation_semantic_status -eq "PASS_LORWYN_PRE_SIMULATION_SEMANTIC_CERTIFICATION") },
    [pscustomobject]@{ Name = "lorwyn_rows"; Passed = ($summary.lorwyn_forecast_rows -eq 6 -and $lorwynRows.Count -eq 6) },
    [pscustomobject]@{ Name = "final_universe"; Passed = ($summary.final_forecast_products -eq 49 -and $summary.final_forecast_rows -eq 294 -and $finalRows.Count -eq 294) },
    [pscustomobject]@{ Name = "blocked_rows"; Passed = ($summary.blocked_rows -eq 6 -and $blockedRows.Count -eq 6) },
    [pscustomobject]@{ Name = "coverage"; Passed = ($summary.coverage_rows -eq 300) },
    [pscustomobject]@{ Name = "lineage"; Passed = ($summary.lineage_rows -eq 294 -and $summary.lineage_rows_closed -eq 294 -and $openLineage.Count -eq 0) },
    [pscustomobject]@{ Name = "unique_keys"; Passed = ($uniqueKeys.Count -eq 294 -and $uniqueProducts.Count -eq 49) },
    [pscustomobject]@{ Name = "critical_failures"; Passed = ($summary.critical_failures.Count -eq 0) }
)
$checks | Format-Table -AutoSize
$failedChecks = @($checks | Where-Object { $_.Passed -ne $true })
Assert-Condition ($failedChecks.Count -eq 0) "Final authority-bound recertification does not reconcile." 830

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
Assert-Condition ($LASTEXITCODE -eq 0) "Complete Collector regression suite failed." 831

$finalStatus = @(git status --porcelain)
Assert-Condition ($LASTEXITCODE -eq 0) "Final Git status could not be read." 832
if ($finalStatus.Count -ne 0) {
    $finalStatus | ForEach-Object { Write-Host $_ }
    Stop-Governance "Repository is not clean after recertification." 833
}

Write-Host ""
Write-Host "============================================================"
Write-Host "COLLECTOR PROJECT STATUS AFTER EXECUTION"
Write-Host "============================================================"
Write-Host "COMPLETED / CERTIFIED"
Write-Host "1. All 50 governed products reconciled."
Write-Host "2. All 288 base forecasts and early-awareness identities recertified."
Write-Host "3. Incorrect outputs invalidated."
Write-Host "4. Lorwyn rebuilt only after semantic certification."
Write-Host "5. Final 49-product forecast authority created."
Write-Host "6. All 294 forecasts have closed lineage."
Write-Host ""
Write-Host "CURRENTLY WORKING ON"
Write-Host "7. Probabilistic calibration and reasonableness review."
Write-Host ""
Write-Host "STILL OUTSTANDING"
Write-Host "8. Final rankings."
Write-Host "9. Product analysis and purchase authorization."
Write-Host ""
Write-Host "OVERALL RESULT: CANONICAL IDENTITY AND LINEAGE RECERTIFIED" -ForegroundColor Green
Write-Host "RANKING STATUS: BLOCKED" -ForegroundColor Yellow
Write-Host "PURCHASE STATUS: BLOCKED" -ForegroundColor Yellow
exit 0
