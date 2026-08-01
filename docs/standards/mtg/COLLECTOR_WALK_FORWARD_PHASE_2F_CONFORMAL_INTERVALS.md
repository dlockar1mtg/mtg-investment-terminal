# Collector Walk-Forward Phase 2F — Conformal Interval Calibration

## Purpose

Phase 2F separates forecast calibration from uncertainty calibration. It tests whether coverage-targeted symmetric conformal intervals built from prior matured absolute forecast errors are more robust than signed residual-quantile intervals during market regime changes.

## Inputs

- Phase 2E out-of-sample regime-calibrated forecasts.
- Only forecast errors whose outcomes matured before the current decision cutoff.
- Training windows: expanding and the most recent 2, 3, 4, and 6 cutoffs.

## Target coverages

- 50 percent
- 68 percent
- 80 percent

## Method

For each horizon, training window, decision cutoff, and target coverage:

1. Select prior matured out-of-sample forecast errors.
2. Require at least 50 cases across at least two historical cutoffs.
3. Estimate a conformal radius from the target quantile of absolute error.
4. Construct `forecast ± radius`.
5. Score unseen outcomes for coverage and tail balance.

## Restrictions

- Shadow analysis only.
- Candidate v2.3 is unchanged.
- No production projections.
- No purchase recommendations.
- No automatic methodology update.
- Technical freeze remains suspended.

## Outputs

- `collector_walk_forward_phase_2f_predictions.csv`
- `collector_walk_forward_phase_2f_selections.csv`
- `collector_walk_forward_phase_2f_interval_summary.csv`
- `collector_walk_forward_phase_2f_summary.json`

## Interpretation

A useful interval method should approach its target empirical coverage without a severe imbalance between below-bound and above-bound misses. Results do not authorize a methodology change; they support a later owner decision package.
