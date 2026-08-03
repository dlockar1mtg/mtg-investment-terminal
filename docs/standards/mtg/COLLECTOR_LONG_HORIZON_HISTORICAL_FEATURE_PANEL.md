# Collector Long-Horizon Historical Feature Panel

## Purpose

Build one leakage-safe, point-in-time feature panel shared by the 365-day, 3-year, and 5-year Collector model programs.

## Canonical inputs

- Universal MTG historical observation ledger for historical prices.
- Governed Collector registry for release identity.
- Phase 2A walk-forward outcomes for historical decision cutoffs.
- Product-master fundamentals remain current-only and are not admitted into retrospective predictors without dated evidence.

## Implemented features

- Product age and age route.
- 3-, 6-, and 12-month returns.
- 2- and 3-year CAGR where sufficient history exists.
- Since-history CAGR.
- Collector category trend.
- Trailing volatility.
- Maximum drawdown.
- Positive-month rate.
- Return persistence.
- Forecast extremeness.
- Data-quality grade.

## Controls

- Every observation must be on or before its decision cutoff.
- Realized outcomes are excluded from predictors.
- Duplicate downstream outputs and review queues are not canonical sources.
- Current-only fundamentals are withheld from replay.
- Missing features remain missing.
- All model, production, purchasing, freeze, automatic-update, and UIP authorization gates remain closed.

## Next stage

After the panel passes, run the 365-day direct hybrid tournament. The same panel becomes the historical-vintage foundation for the 3-year and 5-year programs.
