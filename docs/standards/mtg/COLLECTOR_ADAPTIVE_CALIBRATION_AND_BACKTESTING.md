# Collector Adaptive Calibration and Backtesting

## Purpose

Collector forecasting should improve through governed backtesting. Backtests may evaluate candidate parameters and recommend changes that improve out-of-sample, risk-adjusted results. Active production parameters may change only after owner approval and recertification.

## Required design

- Preserve chronological order.
- Prohibit future-information leakage.
- Use walk-forward evaluation and a holdout period.
- Evaluate each forecast route separately.
- Evaluate release-age cohorts separately.
- Include transaction costs, liquidity effects, downside outcomes, and parameter stability.
- Compare every candidate against the currently approved specification.

## Objective

The primary objective is improved out-of-sample risk-adjusted return rather than maximum raw return. Candidate metrics include net return after costs, drawdown, downside capture, interval coverage, forecast error, directional accuracy, ranking hit rate, turnover, and parameter stability.

Exact metric weights are not approved. Initial diagnostics must show the tradeoffs before approval is requested.

## Recommendation cycle

1. Daily refresh updates governed prices and evidence.
2. Forecasts continue using the approved specification.
3. Matured outcomes enter the validation ledger.
4. Candidate parameters are evaluated through walk-forward backtests.
5. A recommendation package compares current and proposed values, out-of-sample results, downside effects, subgroup results, stability, and limitations.
6. The recommendation remains inactive until Devon Lockard approves it.
7. Approved changes are versioned, tested, reviewed, and recertified before activation.

## Early-opportunity protection

Backtests must measure whether the model identifies attractive products near release. Optimization must not improve mature-product error by systematically excluding newer products before appreciation occurs.

Diagnostics should include historical entry price, route used, eligibility, rank, later return, missed-opportunity rate, and false-positive rate. Exact thresholds remain unset until diagnostic results are reviewed and owner-approved.

## Current authority

Adaptive diagnostics and recommendation generation are allowed. Exact optimization weights, minimum-improvement rules, change limits, stability periods, review thresholds, and production activation remain unapproved.
