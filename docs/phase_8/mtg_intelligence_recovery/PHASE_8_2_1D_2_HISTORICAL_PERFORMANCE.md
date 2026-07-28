# Phase 8.2.1D.2 — Secret Lair Historical Performance Contract

Phase 8.2.1D.2 creates a historical-performance dataset that is separate from forward forecasts.

## Source evidence

The current warehouse history contains dated Secret Lair observations, but the available extract is primarily a single snapshot date. The engine therefore does not fabricate total return or CAGR.

## Readiness rules

A product is historical-performance eligible only when it has:

- at least two distinct valid observation dates;
- at least 30 elapsed days;
- positive observed start and end values.

When these requirements are not met:

- historical total return remains blank;
- historical CAGR remains blank;
- historical annualized return remains blank;
- the status explains the suppression.

## Forecast boundary

Historical analytics never changes:

- `forecast_eligible`, which remains `NO`;
- `recommendation_eligible`, which remains `NO`;
- one-, three-, or five-year forecast fields, which remain blank.

## Outputs

- `data/validation/phase_8/secret_lair_historical_performance/secret_lair_historical_performance.csv`
- `data/validation/phase_10/universal_export/latest/historical_performance.csv`
- `data/operations/mtg_uip_delivery/latest/historical_performance.csv`
