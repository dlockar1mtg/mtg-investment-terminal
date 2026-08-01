# Collector Walk-Forward Phase 2I — Calibrated-History Finalist Tournament

## Purpose

Run the remaining calibrated-history forecast and uncertainty choices in one governed comparison batch rather than as sequential micro-tests.

## Tournament grid

- 5 training windows
- 8 product-versus-market blend weights
- 5 bias-shrinkage factors
- 3 target coverages
- 5 robustness slices

The builder uses only outcomes matured before each historical decision cutoff.

## Robustness slices

- Full sample
- Early half of available cutoffs
- Late half of available cutoffs
- Excluding the worst current-model product
- Trimming the top 5% of current-model errors

## Selection logic

Configurations are ranked using forecast MAE, coverage gap, tail imbalance, and robustness stability penalties. A configuration is disqualified if:

- empirical coverage falls outside the configured tolerance;
- any required robustness slice has negative MAE improvement versus the current model; or
- any required robustness slice is unavailable.

## Outputs

- predictions
- parameter selections
- configuration summary
- robustness results
- top finalists by horizon
- one provisional winner by horizon, when a non-disqualified candidate exists
- structural summary

## Governance

This tournament is shadow-only. It does not amend Candidate v2.3, authorize production forecasts, authorize purchases, permit automatic model updates, or lift the walk-forward freeze suspension.
