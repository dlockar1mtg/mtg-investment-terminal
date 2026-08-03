# Collector 365-Day Final Qualification

## Purpose

This stage compares the selected direct challenger and the leakage-free comparable route on the same cases, applies expanding-window bias calibration, and evaluates cutoff and product-age-route stability.

## Inputs

- 365-day direct tournament summary and predictions
- Leakage-free comparable-transfer predictions
- Collector historical decision-feature panel

## Selected direct challenger

`PW0.5_MR0.5_VP0.0_DP0.0_PA0.05`

## Bias calibration

Candidate shrinkage values are `0.0`, `0.25`, `0.5`, `0.75`, and `1.0`.

For each decision cutoff, calibration uses only earlier cutoffs. The median prior signed error is multiplied by the candidate shrinkage and removed from the current forecast. Current-cutoff and future outcomes are not used to calibrate that cutoff.

## Qualification dimensions

- Common-sample MAE
- Median absolute error
- Signed bias
- Direction accuracy
- Rank correlation
- Top-versus-bottom spread
- Cutoff stability
- Product-age-route stability

## Governance

A passing run or a qualified row does not authorize a methodology change. Owner review remains required. Production projections, purchase recommendations, automatic model updates, technical freeze, and UIP acceptance remain prohibited.
