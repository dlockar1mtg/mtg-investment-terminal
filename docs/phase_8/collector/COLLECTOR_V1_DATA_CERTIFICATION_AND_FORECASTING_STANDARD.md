# Collector V1 Data Certification and Forecasting Standard

## Purpose

This document is the permanent operating standard for certifying the Collector Booster lane before feature engineering, forecasting, purchase eligibility, or UIP delivery. It prevents the lane from being reconstructed from memory or from a sequence of ad hoc fixes.

The standard separates:

1. Current-data V1 requirements that can be completed now.
2. Governed limitations that must remain visible in V1.
3. Future V2 evidence that may improve the lane but does not block V1.

## Governing principle

A file existing in the repository does not establish that its data is fit for forecasting. Every source must pass identity, grain, value, date, coverage, reconciliation, and anti-leakage checks before it enters the feature matrix.

## Source precedence

1. Wizards official product and release evidence.
2. TCGCSV identity, current price, and historical price evidence.
3. MTGJSON sealed-product structure and configuration evidence.
4. Certified eBay observable marketplace-supply evidence.
5. Derived scarcity, comparable, forecast, and recommendation outputs.

Lower-precedence sources may enrich higher-precedence sources but may not overwrite authoritative identity or release facts.

## Immutable V1 authorities

- Governed Collector product registry.
- Official release-date authority.
- Certified TCGCSV product map and price history.
- MTGJSON sealed-product crosswalk.
- Collector forecast-method router.
- Collector comparable-selection outputs.
- Certified eBay day-one accepted, review, ambiguity, and product-snapshot artifacts.
- Supply Scarcity Index V1 policy and output.
- Collector V1 forecast-horizon policy.

## Required V1 certification sequence

### 1. Universe authority

- Establish the governed product universe.
- Normalize product IDs.
- Prove uniqueness.
- Reconcile the forecasting universe against all feature universes.
- Record every mismatch in a governed exceptions ledger.
- Never manufacture a missing feature value solely to force a complete join.

### 2. Historical pricing

- Identify the governed product-ID column.
- Identify the observation-date column.
- Identify the forecast target price column.
- Reject nonpositive prices.
- Reject materially future-dated observations.
- quantify duplicate product-date rows.
- Measure history depth for every governed product.
- Assign products to direct-history, limited-history, comparable, or hybrid methods according to certified evidence.

### 3. Release and structural evidence

- Join release date by governed product ID.
- Calculate product age only from certified release dates and the feature vintage.
- Preserve presale state.
- Join packaging and sealed-product structure from MTGJSON or another governed authority.
- Do not infer print run from packaging or observed listings.

### 4. eBay supply evidence

- Use only hardened accepted listings in observable supply counts.
- Exclude review listings from supply totals.
- Exclude cross-product ambiguity mappings from supply totals.
- Preserve zero accepted listings as an observed acquisition result, not proof of universal absence.
- Treat seller counts as unusable when the saved evidence does not contain differentiating seller identity.

### 5. Supply Scarcity Index V1

V1 is a current-snapshot, cross-sectional feature. It does not require repeated future observations.

It may include:

- Accepted observable listing count.
- Review and ambiguity uncertainty.
- Observable seller count only when certified as differentiating.
- A confidence score and confidence-adjusted scarcity score.

Supply Scarcity Index V1 must be tested through model ablation. It is not automatically retained in production merely because it exists.

### 6. Forecast horizons

The governed V1 horizons are:

- 30 days.
- 90 days.
- 180 days.
- 365 days.
- 1,095 days.
- 1,825 days.

The three-year horizon is the primary investment-comparison horizon. The five-year horizon is a scenario horizon and requires the widest uncertainty.

### 7. Data coherence certification

Run:

```powershell
python scripts\audit_collector_v1_data_sufficiency.py --strict
python scripts\certify_collector_v1_data_coherence.py --strict
```

Feature engineering may begin only when no critical coherence checks fail. Governed gaps may remain when they are explicitly documented and handled by policy.

### 8. Feature matrix

The product-level feature matrix must preserve:

- Product ID and governed name.
- Forecast method.
- History certification state.
- Current target price.
- Observation count and history duration.
- Returns, trend, volatility, and drawdown.
- Release date, age, and presale state.
- Structural and packaging fields.
- Comparable group and peer weights.
- Current accepted eBay listings.
- Review and ambiguity counts.
- Supply Scarcity Index V1, confidence, and adjusted score.
- Feature vintage and source hashes.

No feature may use information occurring after the forecast cutoff in backtesting.

### 9. Routed forecast experiments

- DIRECT_HISTORY_CALIBRATED for sufficiently certified history.
- DIRECT_HISTORY_LIMITED for usable but limited history with wider uncertainty.
- COMPARABLE_PRODUCT_ADJUSTED for products requiring governed peer transfer.
- FUNDAMENTAL_COMPARABLE_HYBRID for governed exceptions.

### 10. Historical validation

For each eligible method and horizon, calculate:

- MAE.
- MAPE.
- Median absolute percentage error.
- RMSE.
- Bias.
- Directional accuracy.
- Prediction-interval coverage.
- Eligible-product coverage.

Compare models with and without Supply Scarcity Index V1.

### 11. Calibration and model selection

- Calibrate uncertainty by method and horizon.
- Reject models with unstable or misleading interval coverage.
- Select the best validated model by governed objective, not by in-sample fit.
- Preserve all experiment versions, inputs, hashes, and results.

### 12. Production and purchase gates

A candidate forecast is not a purchase recommendation.

Production forecasting requires:

- Certified feature matrix.
- Passing backtests.
- Passing uncertainty calibration.
- Product-level and portfolio-level validation.
- Approved production model version.

Purchase eligibility additionally requires:

- Decision-engine eligibility.
- Risk and liquidity controls.
- Confidence thresholds.
- Data freshness checks.
- No unresolved critical exceptions.

UIP delivery occurs only after those gates pass.

## Governed V1 gaps versus V2 upgrades

### Allowed governed V1 gaps

- Missing seller differentiation, provided the seller component is disabled or reweighted.
- Products without an eBay scarcity score, provided the exception is explicit and a missing-feature policy is used.
- Limited historical depth, provided the method router and uncertainty policy handle it.
- Presale products without realized outcomes, provided they are not treated as direct-history backtest cases.

### V2-only enhancements

- Repeated eBay observations.
- Listing persistence.
- Observational listing entry and exit.
- Temporal seller-count movement.
- Temporal supply acceleration.
- Supply Scarcity Index V2.

These V2 features may improve later forecasts but do not block V1.

## Permanent outputs

Every V1 certification run must retain:

- Data-sufficiency summary.
- Artifact diagnostics.
- Universe reconciliation.
- History coverage.
- Data-coherence checks.
- Governed exceptions.
- Feature matrix manifest.
- Experiment manifest.
- Backtest metrics.
- Calibration report.
- Model-selection ballot.
- Forecast output manifest.
- Purchase eligibility report.
- UIP export manifest.

## Reuse for other MTG lanes

Pre-Collectors and Secret Lairs must follow the same sequence and authorization logic. The universal process is documented in `docs/standards/MTG_LANE_V1_CERTIFICATION_TEMPLATE.md`.

Lane-specific differences must be explicit. They must not be hidden inside shared code or inferred from product names.
