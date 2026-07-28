# Phase 8.2.1A — Secret Lair Recovery Audit

## Status

Audit generated successfully.

## Repository

`C:\Users\DevonLockard\mtg-investment-terminal`

## Summary

- Inventory sources inspected: **1642**
- Sources with detected Secret Lair rows: **548**
- Maximum detected Secret Lair population: **17232**
- Terminal HTML sources with embedded Secret Lair data: **0**
- Universal/export-related sources: **127**
- Production-related sources: **36**

## Largest detected Secret Lair sources

| Secret Lair rows | Total rows | Type | Path |
|---:|---:|---|---|
| 17232 | 17232 | csv | data/operations/mtg_tcgcsv_price_backfill/archive/tcgcsv_monthly_archive_observations.csv |
| 4347 | 5239 | csv | data/staging/phase_10/universal_mapping/asset_master_preview_2026-07-22.csv |
| 4347 | 5239 | csv | data/validation/phase_10/universal_mapping/canonical_to_universal_identity_map_2026-07-22.csv |
| 4347 | 5239 | csv | data/staging/phase_10/external_discovery/tcgcsv/reconciliation/tcgcsv_candidate_reconciliation_2026-07-22.csv |
| 4347 | 5239 | csv | data/staging/phase_10/external_discovery/tcgcsv/tcgcsv_premium_candidate_universe_2026-07-22.csv |
| 4347 | 4347 | csv | data/validation/phase_10/external_discovery/tcgcsv/tcgcsv_secret_lair_product_evidence_2026-07-22.csv |
| 4347 | 5239 | csv | data/validation/phase_10/premium_universe_eligibility/premium_universe_eligibility_audit_2026-07-22.csv |
| 4347 | 4347 | csv | data/validation/phase_10/secret_lair_reconstruction/secret_lair_full_catalog_classification_2026-07-22.csv |
| 4327 | 4675 | csv | data/product_master/investment_products.csv |
| 4327 | 4675 | csv | data/staging/phase_10/external_discovery/existing_registry_canonical_stage.csv |
| 4327 | 4446 | csv | data/validation/phase_10/external_discovery/existing_registry_review_queue.csv |
| 4326 | 4674 | csv | data/validation/phase_10/external_discovery/tcgcsv/reconciliation/tcgcsv_exact_id_matches_2026-07-22.csv |
| 4093 | 4792 | csv | data/validation/phase_10/premium_universe_eligibility/premium_universe_structural_exclusions_2026-07-22.csv |
| 4093 | 4093 | csv | data/validation/phase_10/secret_lair_reconstruction/secret_lair_nonstructural_marketplace_evidence_2026-07-22.csv |
| 1971 | 2116 | csv | data/operations/ebay_full_universe_migration/migration_20260727T123556Z/ebay_migrated_classification_changes.csv |
| 1946 | 2450 | csv | data/operations/mtg_history_foundation/universal_mtg_source_identity.csv |
| 1765 | 1765 | csv | data/validation/phase_10/ebay_matching/batches/sealed_secret_lair_0430_0629/ebay_listing_match_results_2026-07-23.csv |
| 1647 | 1647 | csv | data/operations/mtg_source_discovery/universal_tcgcsv_discovery/universal_tcgcsv_candidate_matches.csv |
| 1553 | 1553 | csv | data/operations/mtg_source_discovery/tcgcsv_exact_name_candidates.csv |
| 1482 | 1482 | csv | data/validation/phase_10/ebay_matching/batches/sealed_secret_lair_0230_0429/ebay_listing_match_results_2026-07-23.csv |

## Recovery questions for Phase 8.2.1B

1. Which source contains the complete governed Secret Lair population?
2. Which source fed the previous research terminal?
3. Which source currently feeds the universal export?
4. Which records are absent from the universal package?
5. Which intelligence fields are missing from the universal contract?
6. Are missing records intentionally suppressed or accidentally omitted?
7. Can realized-return intelligence be exported without mislabeling it as a forward forecast?
8. Which Secret Lair products qualify for true horizon-based projections?

## Evidence files

- `secret_lair_source_inventory.csv`
- `secret_lair_field_matrix.csv`
- `secret_lair_coverage_reconciliation.csv`
- `secret_lair_recovery_audit.json`
