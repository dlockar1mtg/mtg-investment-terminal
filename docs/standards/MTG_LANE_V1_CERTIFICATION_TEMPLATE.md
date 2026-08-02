# MTG Lane V1 Certification Template

## Scope

This template is the shared certification process for Collector Boosters, Pre-Collectors, Secret Lairs, and future MTG investment lanes.

The lane must supply its own governed universe, identity rules, source map, structural fields, forecast methods, and exceptions. The authorization sequence remains consistent.

## Required lane configuration

Each lane must define:

- Lane name and version.
- Governed product registry.
- Product identity key.
- Authoritative release-date source.
- Authoritative current-price source.
- Historical target-price source.
- Structural evidence source.
- Marketplace-supply source, when applicable.
- Forecast horizons.
- Method-routing policy.
- Comparable-selection policy.
- Feature contract.
- Missing-feature policy.
- Backtest policy.
- Calibration policy.
- Purchase-eligibility policy.
- UIP export contract.

## Universal certification blocks

### A. Source preservation

- Preserve raw source artifacts immutably.
- Record hashes, collection times, source versions, and acquisition parameters.
- Never modify raw evidence to make downstream checks pass.

### B. Governed identity

- Normalize product IDs and names.
- Resolve aliases and edition variants.
- Fail closed on ambiguous identities.
- Produce a governed exceptions ledger.

### C. Data sufficiency

- Verify required files exist.
- Verify required columns exist.
- Verify coverage by governed product.
- Verify forecast target availability.
- Identify current-data gaps separately from future upgrades.

### D. Data coherence

- Check ID uniqueness.
- Check join cardinality.
- Check price positivity.
- Check date validity.
- Check duplicate product-date keys.
- Check release-date consistency.
- Check feature bounds.
- Check that categorical values belong to governed sets.
- Check that uncertainty and confidence calculations reconcile.

### E. Feature matrix

- Build one governed product-level current feature matrix.
- Build cutoff-specific historical matrices for backtesting.
- Preserve feature vintages and source hashes.
- Prevent future leakage.

### F. Forecast routing

- Route each product to a governed method.
- Require explicit handling for limited history, presale products, and exceptions.
- Do not force every product through one model.

### G. Backtesting

- Backtest by method and horizon.
- Use only information available at each historical cutoff.
- Report MAE, MAPE, median APE, RMSE, bias, directional accuracy, interval coverage, and eligible-product coverage.

### H. Feature ablation

- Compare the baseline model with each major derived feature removed or added.
- Retain derived features only when they improve a governed validation objective or provide justified risk information.

### I. Calibration

- Calibrate intervals by method and horizon.
- Measure empirical interval coverage.
- Widen or reject intervals that are undercalibrated.

### J. Model selection

- Preserve all candidates and results.
- Select by governed out-of-sample criteria.
- Approve one version before production use.

### K. Purchase eligibility

- Separate forecasts from recommendations.
- Apply freshness, liquidity, confidence, downside, risk, and portfolio constraints.
- Keep unresolved critical exceptions ineligible.

### L. UIP export

- Export only approved production outputs.
- Include model version, feature vintage, source hashes, confidence, uncertainty, eligibility, and limitations.

## Required documentation package

Each lane must retain:

1. Lane architecture and source-precedence document.
2. Data-sufficiency certification.
3. Data-coherence certification.
4. Universe reconciliation.
5. Governed exceptions ledger.
6. Feature dictionary.
7. Feature matrix manifest.
8. Forecast-method routing report.
9. Comparable-selection report.
10. Backtest report.
11. Feature-ablation report.
12. Calibration report.
13. Model-selection ballot.
14. Production forecast manifest.
15. Purchase-eligibility report.
16. UIP export manifest.
17. Future-upgrade backlog.

## Lane-specific application

### Collector Boosters

Typical lane-specific evidence:

- TCGCSV sealed-product prices.
- MTGJSON sealed structure.
- eBay observable display supply.
- Supply Scarcity Index.
- Packaging and box-topper fields.

### Pre-Collectors

Typical lane-specific differences:

- Different product-era definitions.
- Potentially weaker marketplace identity.
- Longer history but inconsistent naming and packaging.
- Additional manual identity adjudication.
- Separate comparable cohorts from modern Collector Boosters.

Pre-Collectors must not inherit Collector Booster packaging or supply assumptions without evidence.

### Secret Lairs

Typical lane-specific differences:

- Drop-level and edition-level identity.
- Direct-sale window and fulfillment timing.
- Foil/nonfoil and bundle variants.
- Smaller or irregular secondary-market supply.
- Different release-age and comparable logic.
- Different liquidity and transaction-cost assumptions.

Secret Lairs must not use sealed-display scarcity or box-level packaging features.

## Authorization states

Use these standard states:

- NOT_STARTED
- IN_PROGRESS
- REVIEW_REQUIRED
- CERTIFIED_WITH_GOVERNED_GAPS
- CERTIFIED
- AUTHORIZED_FOR_EXPERIMENTS
- AUTHORIZED_FOR_PRODUCTION
- AUTHORIZED_FOR_PURCHASE_SCORING
- AUTHORIZED_FOR_UIP_DELIVERY
- BLOCKED

Authorization must be explicit. Completion of an upstream block does not automatically authorize downstream use.

## Future upgrades

Future evidence should be listed as an upgrade backlog, not silently promoted into a V1 requirement unless governance explicitly approves the change.

Each upgrade must state:

- New evidence required.
- Why it improves the lane.
- Which current limitation it addresses.
- Whether it changes historical comparability.
- Whether models require retraining or recertification.
- The reminder or refresh cadence.
