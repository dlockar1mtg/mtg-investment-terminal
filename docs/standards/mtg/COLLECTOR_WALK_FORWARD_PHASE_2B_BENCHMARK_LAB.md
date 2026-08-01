# Collector Walk-Forward Phase 2B Benchmark and Calibration Lab

## Purpose

Phase 2B evaluates the leakage-safe Phase 2A calibrated-history forecasts against shadow alternatives. It does not alter Candidate Methodology v2.3 and does not authorize forecasts or purchases.

## Source

The lab reads only the held-out scored outcomes produced by:

`data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0`

## Forecast variants

- Current model
- No-change benchmark
- 25%, 50%, and 75% shrinkage toward zero
- Annual-rate caps at 50% and 75%
- Fifty-percent blend with the contemporaneous cross-sectional median annual forecast

## Scenario variants

The lab evaluates fixed annual widths of 20%, 30%, 40%, 50%, and 75%, retaining the diagnostic -95% downside floor.

## Outputs

- Variant-level scored outcomes
- Accuracy summary by horizon and variant
- Scenario coverage by horizon and width
- Best shadow variant by horizon
- Decision-state realized-return summary
- Structural summary

## Interpretation rules

A shadow variant may be recommended for further owner review when it has at least 25 scored cases and lower mean absolute error than the current model at that horizon. A recommendation is diagnostic only.

The current Candidate v2.3 methodology remains unchanged. The technical freeze remains suspended pending completion of the full walk-forward program, including comparable-adjusted and limited-history route reconstruction.

## Authorization boundaries

The lab does not authorize:

- Candidate methodology changes
- Production forecasts
- Purchase recommendations
- Automatic model updates
- Technical freeze
