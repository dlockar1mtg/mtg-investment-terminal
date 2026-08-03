# Collector V1 English-Language Eligibility Standard

## Investment mandate

Collector V1 includes only English-language sealed Collector Booster products. Foreign-language products are outside the investment mandate and are not eligible for forecasting, ranking, purchase analysis, purchase recommendations, or UIP export.

## Current exclusion

- TCGplayer product ID: `628315`
- Investment product ID: `TCGCSV-24219-628315`
- Reason: foreign-language product outside the user's investment mandate

## Source preservation

Historical source and immutable audit artifacts may retain the excluded product so prior work remains reproducible. Those records are evidence only and are not part of the active investment universe.

## Active-universe rule

Every regenerated Collector V1 artifact must apply `config/mtg/governance/collector_v1_product_exclusions.json` before feature engineering or forecasting. The active route, scarcity, release, normalized-evidence, comparable, feature, forecast, ranking, purchase, and UIP outputs must contain no excluded product IDs.

## Certification

`scripts/build_collector_v1_active_english_universe.py --strict` must pass before feature-matrix construction. A pass requires:

1. Exactly 50 active governed route products.
2. Route IDs equal Supply Scarcity Index V1 IDs.
3. Route IDs equal release-authority IDs.
4. No excluded product occurs in any generated active-universe artifact.
5. Original historical source artifacts remain unchanged.

## Future products

New foreign-language products default to excluded unless the investment mandate is explicitly changed and the eligibility policy is versioned.
