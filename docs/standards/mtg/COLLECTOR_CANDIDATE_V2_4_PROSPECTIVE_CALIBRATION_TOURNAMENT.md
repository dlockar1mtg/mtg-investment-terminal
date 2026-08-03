# Collector Candidate v2.4 Prospective Calibration Tournament

## Purpose

Evaluate prospective confidence methods and decision-state thresholds in one leakage-safe tournament using the corrected Candidate v2.4 shadow predictions.

## Confidence candidates

- Prior product MAE
- Prior product MAE plus current forecast extremeness
- Prior horizon MAE plus current forecast extremeness

Confidence is assigned at each historical cutoff using only outcomes matured before that cutoff. Realized error is used only for later scoring.

## Decision candidates

All combinations of lower quantiles 0.20, 0.25, 0.33, and 0.40 with upper quantiles 0.60, 0.67, 0.75, and 0.80 are tested. Thresholds are calculated from forecasts available at the historical cutoff. Candidate methods are scored on realized ordering:

FAVORABLE > WATCH > NEUTRAL.

## Governance

This package is diagnostic and shadow-only. It does not authorize a prospective confidence method, decision-state method, candidate methodology change, production projections, purchase recommendations, automatic updates, technical freeze, or UIP acceptance.

## Outputs

- Prospective confidence predictions, summaries, and provisional winners
- Decision-threshold predictions, summaries, and provisional winners
- Structural summary and audit results

A provisional winner is evidence for owner review only. It is not an approved methodology.
