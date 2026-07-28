# Phase 8.2.1C — Secret Lair Intelligence Recovery Baseline

**Status:** REVIEW

## Purpose

Establish the exact current Secret Lair source, schema, coverage, and semantic state before producer changes.

## Governing semantic rule

Historical or realized CAGR/return fields must not be mapped into forward forecast fields without an independently certified horizon model.

## Counts

- datasets: 7
- unique_ids_across_layers: 973
- semantic_rows: 1946
- rows_with_native_ranges: 1946
- rows_with_any_horizon_field: 0
- rows_with_suspicious_forecast_method: 0

## Checks

- core_datasets_present: REVIEW
- unified_secret_lair_rows_present: PASS
- uip_secret_lair_rows_present: PASS
- source_code_present: PASS
- tests_present: PASS
- identity_coverage_nonzero: PASS

## Generated evidence

- `secret_lair_dataset_summary.csv`
- `secret_lair_field_semantic_matrix.csv`
- `secret_lair_semantic_row_audit.csv`
- `secret_lair_coverage_matrix.csv`
- `secret_lair_semantic_aggregates.csv`
- `secret_lair_source_inventory.csv`
- `PHASE_8_2_1C_BASELINE_AUDIT.json`
