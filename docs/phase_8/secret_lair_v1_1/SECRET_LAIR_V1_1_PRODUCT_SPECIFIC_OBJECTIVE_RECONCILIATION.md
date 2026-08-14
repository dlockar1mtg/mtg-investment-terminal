# Secret Lair V1.1 — Product-Specific Objective Reconciliation

## Status

SECRET_LAIR_V1_1_PRODUCT_SPECIFIC_OBJECTIVE_RECONCILED

## Certified SL-8C result

SL-8C remains certified exactly as executed.

Simple-model winner:

EXACT_PEER_TRAJECTORY

Common OOS folds:

6887

Winner SMAPE:

0.21487915509241193

Winner Spearman rank correlation:

0.034062953862140644

Winner top-minus-bottom realized log-return spread:

0.013937157689018098

Winner unique predictions:

79

The SL-8C certification is not revoked or rewritten.

## Why production promotion is deferred

EXACT_PEER_TRAJECTORY is the strongest simple forecast benchmark found so far.

However, the purpose of Secret Lair V1.1 is not merely to replace two large
forecast groups with a larger number of peer groups.

The governing objective remains product-specific projected outcomes derived
from each asset's own historical behavior plus appropriate peer context.

The simple winner therefore remains the mandatory benchmark for the next
tournament but is not yet promoted directly to V1.1 production authority.

No arbitrary minimum number of unique forecasts is created.

Products with genuinely similar evidence may still receive similar forecasts.

## Important signal findings

### Exact peer trajectory

Role:

BEST_SIMPLE_FORECAST_LEVEL_BENCHMARK

SMAPE:

0.21487915509241193

Unique prediction states:

79

### Recent momentum

Role:

STRONGER_SIMPLE_CROSS_SECTIONAL_DISCRIMINATION_SIGNAL

SMAPE:

0.4154262738730512

Spearman:

0.17503568726102395

Top-minus-bottom spread:

0.0998084602526848

Unique predictions:

6530

This indicates that momentum contains useful cross-sectional information even
though it is too inaccurate to serve as a standalone forecast.

### Relative valuation

The simple directional relative-valuation diagnostic did not justify a manual
forecast adjustment.

No arbitrary valuation coefficient is authorized.

Relative valuation may enter the multivariate tournament only through a
coefficient learned from historical training evidence.

## SL-8C.2 objective

The next tournament will test whether a learned model can combine:

- exact-peer trajectory;
- own historical trajectory;
- own historical price slope;
- recent momentum;
- recent versus longer-term behavior;
- volatility;
- downside behavior;
- maximum drawdown;
- own historical valuation position;
- exact-peer relative valuation;
- foil / finish;
- product family;
- sealed configuration.

The learned model must be evaluated temporally out of sample.

It must be compared directly with:

- LAST_VALUE;
- GLOBAL_REALIZED_MEDIAN;
- EXACT_PEER_TRAJECTORY.

No manually selected feature weights are permitted.

## Authority

SL-8C certification preserved:

TRUE

EXACT_PEER_TRAJECTORY preserved as simple benchmark:

TRUE

Direct simple-model production promotion:

FALSE

SL-8C.2 multivariate tournament:

AUTHORIZED

V1.1 production forecast:

FALSE

V1.1 ranking:

FALSE

V1.1 purchase recommendation:

FALSE

Automatic purchase execution:

FALSE

## Next gate

SL8C2_SECRET_LAIR_V1_1_MULTIVARIATE_PRODUCT_MODEL_TOURNAMENT