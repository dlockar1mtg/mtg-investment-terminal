# Secret Lair V1 — Model Family Tournament

## Status

SECRET_LAIR_V1_TEMPORAL_OOS_TOURNAMENT_EVIDENCE_CERTIFIED

## Direct validation horizon

1 year / 365 days.

Every fold preserves temporal order.

Future target-product observations are prohibited from training.

For peer models, the forecasted product is excluded from its own peer evidence and only return events fully realized by the forecast origin may be used.

## Established-history route

Candidates:

- LAST_VALUE
- LINEAR_PRICE_TREND
- LOG_LINEAR_TREND
- MEDIAN_LOG_RETURN_TREND

Common temporal OOS folds:

6632

Empirical winner:

LAST_VALUE

Winner SMAPE:

0.24094373549855436

Winner MAE:

18.44609167671894

## New / short-history fallback route

Candidates:

- STRUCTURAL_PEER_MEDIAN_RETURN
- GLOBAL_PEER_MEDIAN_RETURN

Common product-holdout temporal folds:

4829

Empirical winner:

GLOBAL_PEER_MEDIAN_RETURN

Winner SMAPE:

0.2046634260078893

Winner MAE:

15.221911537074002

## Winner selection

Models are compared only on common folds within their route.

Selection order:

1. lowest SMAPE;
2. lowest MAE;
3. lowest absolute bias;
4. deterministic model-name tie break.

No weighted composite score and no arbitrary minimum fold threshold are used.

## Dynamic universe

No fixed Secret Lair population count is part of the model logic.

Future new Secret Lairs do not need one year of their own history before they may enter the fallback forecasting path.

The fallback route is validated using product-held-out historical products.

Products without a governed current market anchor are not assigned fabricated forecasts.

## Long horizons

Direct 3Y validation:

FALSE

Direct 5Y validation:

FALSE

3Y output class:

SCENARIO

5Y output class:

SCENARIO

## Authority

The tournament evidence and empirical route winners are certified.

Production method certification is still FALSE.

Production forecasts, Monte Carlo, rankings, purchase recommendations, and UIP delivery remain unauthorized.

## Next gate

SL4B_SECRET_LAIR_FORECAST_METHOD_CERTIFICATION_AND_PRODUCTION_FORECAST_BUILD