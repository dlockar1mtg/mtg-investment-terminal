# Collector Walk-Forward Phase 2G — Bias-Corrected Conformal Calibration

## Purpose

Phase 2G evaluates whether the 90-day conformal interval can retain target coverage while reducing upper-versus-lower tail imbalance.

## Method

For each horizon, training-window definition, and historical decision cutoff:

1. Use only source forecasts whose outcomes matured before the test cutoff.
2. Estimate forecast bias as the median signed residual, `realized - forecast`.
3. Recenter the test forecast by that historical bias estimate.
4. Calculate centered absolute residuals from the matured calibration sample.
5. Set the conformal radius to the configured target-coverage quantile.
6. Score the unseen test outcomes against the bias-corrected interval.

The phase uses only point-in-time matured outcomes and does not modify Candidate v2.3.

## Interpretation

A useful result should preserve empirical coverage near the 68% target while materially reducing the difference between below-interval and above-interval rates.

A positive bias correction means prior realized returns tended to exceed forecasts. A negative correction means prior realized returns tended to fall below forecasts.

## Authorization

This phase is shadow-only. It does not authorize candidate methodology changes, production projections, purchase recommendations, or automatic updates. The technical freeze remains suspended pending the complete walk-forward program.
