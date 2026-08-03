# Collector 365-Day Direct and Comparable Transfer Tournament

## Purpose

This governed shadow program evaluates two related capabilities in one batch:

1. A directly validated 365-day hybrid forecast for Collector Booster Displays with matured outcomes.
2. A comparable-transfer route for products with incomplete direct history.

Neither capability is authorized automatically. All winning methods require owner review.

## Direct tournament

The direct tournament evaluates combinations of:

- Product 12-month momentum weight.
- Collector-category weight.
- Mean-reversion strength.
- Volatility penalty.
- Maximum-drawdown penalty.
- Return-persistence adjustment.

Every challenger is compared with:

- The current 365-day forecast.
- A no-change forecast.
- The Collector-category median forecast.

Required evaluation includes MAE, median absolute error, signed bias, direction accuracy, Spearman rank correlation, top-versus-bottom realized-return spread, cutoff stability, and outlier dependence.

## Comparable transfer

The comparable route is evaluated historically by treating a matured historical product as the target and finding peers using only features available at the same decision cutoff.

Matching dimensions include:

- Product age.
- 3- and 6-month returns.
- Volatility.
- Maximum drawdown.
- Positive-month rate.
- Return persistence.

The route outputs:

- Target product.
- Comparable product.
- Match distance and weight.
- Comparable count.
- Forecast route.
- Evidence grade.
- Uncertainty multiplier.

## Routes

- `DIRECT`: sufficient direct history and matured outcome evidence.
- `BLENDED`: partial product history plus at least three comparables.
- `COMPARABLE`: limited product history plus at least three comparables.
- `BLOCKED`: insufficient direct and comparable evidence.

A comparable-supported product is never represented as having direct history it does not possess.

## Governance

The program is shadow-only. It does not authorize:

- Candidate methodology promotion.
- Production forecasts.
- Purchase recommendations.
- Automatic model updates.
- Technical freeze.
- UIP acceptance.

## Class transfer

After Collector completion, the same validation ideology will be reused for Pre-Collector and Secret Lair with class-specific identity, lifecycle, matching dimensions, liquidity assumptions, and calibration. Collector coefficients are not transferred directly.
