# Collector Walk-Forward Phase 2H Bias Shrinkage Calibration

## Purpose

Phase 2H tests partial bias correction for the 90-day conformal interval candidate. Phase 2F achieved acceptable total coverage but had excessive upper-tail misses. Phase 2G improved tail balance but full median-bias correction reduced total coverage below target.

## Method

For each historical cutoff, Phase 2H uses only previously matured Phase 2E forecast outcomes. It estimates the median signed residual and applies shrinkage factors of 0%, 25%, 50%, 75%, and 100%. A conformal radius is recalculated after each partial recentering.

The selection score prioritizes:

1. Empirical coverage within five percentage points of the 68% target.
2. Lower tail imbalance.
3. Smaller absolute coverage error.

## Restrictions

- Shadow evaluation only.
- No Candidate v2.3 methodology change is authorized.
- No production projection is authorized.
- No purchase recommendation is authorized.
- No automatic model update is authorized.
- Technical freeze remains suspended.

## Outputs

- `collector_walk_forward_phase_2h_predictions.csv`
- `collector_walk_forward_phase_2h_selections.csv`
- `collector_walk_forward_phase_2h_interval_summary.csv`
- `collector_walk_forward_phase_2h_summary.json`
