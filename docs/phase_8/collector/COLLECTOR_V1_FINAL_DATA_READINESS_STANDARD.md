# Collector V1 Final Data Readiness Standard

## Purpose

This standard distinguishes a structurally valid feature matrix from a substantively forecast-ready dataset. A feature matrix may pass schema and integrity checks while still lacking enough historical, comparable, structural, or target data to support forecasting.

## Active universe

Collector V1 uses the certified 50-product English-language active universe. Foreign-language products are excluded from all active forecasting, ranking, purchase, and UIP outputs.

## Required current-data gates

Before forecast experiments may begin, the current V1 dataset must satisfy all of the following:

1. The 50-product active universe is certified.
2. Every product has governed identity, release authority, current price, and current Supply Scarcity Index V1 coverage.
3. At least one released product is eligible for a governed forecasting method.
4. Direct-history products have certified multi-date historical observations at the required grain.
5. Comparable-routed products have selected and certified peer evidence.
6. Structural fields required by the model are populated or explicitly excluded by policy.
7. Historical returns, volatility, drawdown, and trend features are built from certified multi-date history.
8. Forecast-horizon eligibility is calculated from real evidence rather than route labels alone.
9. Supply Scarcity Index V1 is tested both in its original experimental form and in an adjusted form without the inactive seller component.
10. Historical cutoff-based experiment rows can be created without future leakage.

## Structural certification versus forecast readiness

The feature-matrix certification proves that:

- The matrix has 50 unique eligible products.
- Required identity and governance fields exist.
- Values satisfy basic bounds and schema checks.
- Foreign-language exclusions are applied.

It does not prove that:

- Historical depth is sufficient.
- Comparable peers are joined.
- Return and volatility features exist.
- Released products are forecast eligible.
- Backtests can be executed.
- Production forecasts are valid.

The final authority for forecast-data readiness is:

```text
scripts/audit_collector_v1_final_data_readiness.py --strict
```

## Current V1 remediation categories

The following are current-data V1 requirements, not V2 upgrades:

- Repair comparable-product joins.
- Locate and certify deeper multi-date price history.
- Recalculate direct-history eligibility.
- Populate pack count, box topper, licensed IP, product family, and edition classification.
- Calculate historical returns, volatility, drawdown, and trends.
- Create an adjusted Supply Scarcity Index V1 without seller differentiation.
- Rebuild and recertify the feature matrix.
- Build historical cutoff datasets and backtests.

## Future V2-only evidence

The following may be deferred without blocking V1:

- Repeated eBay observations.
- Listing persistence.
- Observational entry and exit.
- Temporal seller-count changes.
- Supply Scarcity Index V2.

## Permanent artifacts

Each V1 run must preserve:

- Source hashes.
- Active-universe manifest.
- Feature dictionary.
- Feature coverage report.
- Missing-feature policy.
- Horizon eligibility.
- Final data-readiness summary.
- Current V1 gap register.
- Experiment manifest.
- Backtest report.
- Scarcity ablation report.
- Calibration report.
- Model-selection record.
- Forecast manifest.
- Purchase-eligibility report.
- UIP export manifest.

## Reuse for other MTG lanes

Pre-Collectors and Secret Lairs must follow the same sequence:

```text
source preservation
→ governed active universe
→ canonical history grain
→ structural feature coverage
→ method eligibility
→ final data-readiness audit
→ cutoff-based experiments
→ backtesting
→ calibration
→ production certification
```

Lane-specific identity, pricing, supply, and lifecycle fields may differ, but the distinction between structural validity and forecast readiness is universal.
