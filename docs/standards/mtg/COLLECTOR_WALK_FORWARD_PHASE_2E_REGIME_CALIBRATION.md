# Collector Walk-Forward Phase 2E Regime Calibration

## Purpose

Phase 2E compares expanding-history calibration with recent-window calibration using only outcomes matured before each decision cutoff.

## Training windows

- EXPANDING
- LAST_2_CUTOFFS
- LAST_3_CUTOFFS
- LAST_4_CUTOFFS
- LAST_6_CUTOFFS

Each available window independently selects the best product-versus-cross-sectional-median blend from the governed weight grid and estimates asymmetric 16th/84th percentile residual intervals.

## Interpretation

This is a shadow diagnostic. It determines whether recent market regimes improve forecast magnitude and interval calibration relative to expanding history. Missing windows or horizons are allowed when insufficient matured observations exist.

## Restrictions

Phase 2E does not alter Candidate v2.3, authorize production forecasts, authorize purchases, authorize automatic updates, activate reverse-score production use, or activate the Japanese hybrid formula. The technical freeze remains suspended.
