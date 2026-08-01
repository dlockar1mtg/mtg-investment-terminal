# Collector Walk-Forward Phase 2D — Horizon Calibration

## Purpose

Phase 2D performs rolling, leakage-safe selection of the product-versus-cross-sectional-median blend separately for 90-, 180-, and 365-day horizons. It also estimates asymmetric empirical residual intervals from outcomes that matured before each decision cutoff.

## Controls

- Candidate v2.3 remains unchanged.
- Selection uses only outcomes with maturity dates before the test cutoff.
- Early cutoffs without sufficient training evidence fall back to the current product-only forecast and are marked `training_ready = false`.
- Residual intervals use the historical 16th and 84th percentiles.
- Results are shadow-only.
- Production, purchase, automatic update, and methodology-change authorization remain false.
- The technical freeze remains suspended.

## Blend grid

- 100% product / 0% median
- 75% product / 25% median
- 60% product / 40% median
- 50% product / 50% median
- 40% product / 60% median
- 25% product / 75% median
- 0% product / 100% median

## Outputs

- `collector_walk_forward_phase_2d_oos_predictions.csv`
- `collector_walk_forward_phase_2d_weight_selections.csv`
- `collector_walk_forward_phase_2d_horizon_summary.csv`
- `collector_walk_forward_phase_2d_summary.json`

## Interpretation

Phase 2D does not approve a new methodology. It determines whether dynamically selected horizon-specific blends improve genuinely out-of-sample error and whether asymmetric residual intervals provide credible empirical coverage.
