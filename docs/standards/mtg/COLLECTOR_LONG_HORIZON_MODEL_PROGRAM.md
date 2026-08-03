# Collector Long-Horizon Model Program

## Purpose

Build separate, governed 365-day, 3-year, and 5-year Collector Booster projection methodologies that satisfy the MTG standards without mechanically extending short-horizon momentum.

## Horizon architecture

### 365 day

Directly testable hybrid return model using product momentum, Collector market momentum, mean reversion, age routing, volatility, drawdown, liquidity, and asymmetric uncertainty.

### 3 year

Lifecycle-adjusted normalized CAGR model using product, category, and comparable growth; lifecycle phase; scarcity; demand durability; reprint risk; liquidity; and bear/base/bull outcomes.

### 5 year

Fundamental terminal-growth probability model using the calibrated year-one forecast, normalized years two and three, conservative terminal growth for years four and five, growth decay, outcome-state probabilities, survivorship risk, proxy priors, and net realizable value.

## Required standard outputs

Every horizon must eventually produce a center, lower and upper bounds, bear/base/bull cases, gross and net returns, method, evidence grade, maturity status, confidence, decision state, liquidity grade, data quality grade, route, and lineage.

## Validation hierarchy

1. Direct point-in-time matured replay where possible.
2. Historical-vintage replay.
3. Ranking discrimination.
4. Class-specific proxy priors.
5. Prospective maturation.

Proxy evidence must never be represented as direct Collector evidence.

## Development sequence

1. Evidence and standards inventory.
2. Required data-contract and feature reconstruction.
3. 365-day direct model tournament.
4. 3-year historical-vintage and lifecycle model.
5. 5-year terminal-growth and probability model.
6. Unified scenario, liquidity, confidence, and decision calibration.
7. Full-route replay and freeze-readiness review.
8. Transfer the completed framework to Pre-Collector and Secret Lair with class-specific inputs and validation.

## Transfer boundaries

Pre-Collector reuses the architecture but requires older-product comparables, distinct lifecycle behavior, and class-specific liquidity.

Secret Lair reuses the architecture but requires sale-window scarcity, edition structure, artist and franchise demand, reprint/substitution risk, and drop-specific liquidity.

## Governance

This program is shadow-only. It does not authorize candidate promotion, production projections, purchase recommendations, automatic model updates, technical freeze, or UIP acceptance.
