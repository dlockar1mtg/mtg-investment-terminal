# Collector Early-Lifecycle Forecast Engine

## Objective

No Collector product may disappear from the final analytical layout. Every product receives exactly one governed row and one of three statuses:

- `PROVISIONAL_365`: guarded point forecast plus scenarios.
- `SCENARIO_ELIGIBLE`: bear/base/bull scenarios without a qualified point forecast.
- `BLOCKED`: visible record with an explicit reason, next evidence requirement, and review trigger.

Blocked means the current evidence cannot support a reliable forecast. It never means the product is omitted.

## Early lifecycle bands

- `LAUNCH_PRICE_DISCOVERY`: 0-3 months.
- `INITIAL_SUPPLY_ABSORPTION`: 4-8 months.
- `STABILIZATION`: 9-12 months.
- `EARLY_ACCUMULATION`: 13-17 months.
- `DEVELOPING`: 18-35 months.
- `MATURE`: 36 months or older.

## Evidence structure

The engine combines only cutoff-available or current application evidence:

- Age-aligned comparable curves.
- Available 90-day and 180-day forecast signals.
- Product 3-, 6-, and 12-month price behavior.
- Release-class and price-band matching.
- Available supply/inventory evidence.
- Available franchise/demand evidence.
- Wider uncertainty and lower confidence for early lifecycle products.

No peer future outcome may be used as a predictor.

## No-dropout contract

The strict audit fails when:

- Any Collector product is missing.
- A product appears more than once.
- Any required output field is null or blank.
- A non-provisional product exposes a 365-day point forecast.
- Bear, base, or bull scenarios are absent.
- A blocked product lacks a reason or next evidence requirement.
- Future information is used.
- Any production, purchase, freeze, automatic-update, or UIP gate is opened.

Unavailable values use explicit tokens such as `NOT_AVAILABLE` or `NOT_APPLICABLE`; they are never silently blank.

## Status rules

### PROVISIONAL_365

Requires meaningful history, at least three age-aligned comparables, a validated 90-day or 180-day bridge signal, and an available blended estimate. The forecast remains low confidence and receives a wide uncertainty multiplier.

### SCENARIO_ELIGIBLE

Used when enough evidence exists for a reasonable bear/base/bull distribution but the historical qualification for a point forecast is incomplete.

### BLOCKED

Used only when even scenario construction lacks sufficient history, comparables, or bridge signals. The row still contains a conservative placeholder scenario, blocked reason, next evidence requirement, and review trigger.

## Governance

This engine is shadow-only. It does not authorize production projections, purchase recommendations, automatic model updates, technical freeze, candidate promotion, or UIP acceptance.
