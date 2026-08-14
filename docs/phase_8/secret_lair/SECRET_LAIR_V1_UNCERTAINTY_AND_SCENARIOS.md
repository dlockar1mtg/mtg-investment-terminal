# Secret Lair V1 — Uncertainty and Long-Horizon Scenarios

## Status

SECRET_LAIR_V1_UNCERTAINTY_AND_LONG_HORIZON_SCENARIOS_CERTIFIED

## SL-5A correction lineage

The first SL-5A execution failed closed because its uncertainty builder
incorrectly treated every fold with at least two historical training
observations as an established common fold.

Failed reconstructed established folds:

7229

Certified SL-4A established common folds:

6632

The corrected execution reproduces the original tournament definition:
only folds on which all four established candidate models emitted valid
predictions enter the established common-fold uncertainty population.

The failed external evidence package is preserved at:

C:\Users\DevonLockard\Downloads\UIP_MTG_Governance\Secret_Lair_V1\SL_5_Uncertainty_and_Scenarios\SL5A_UNCERTAINTY_SCENARIOS_20260812_085128

The SL-4A tournament and SL-4B production methods were not reopened.

## 1Y empirical uncertainty

Established production method:

LAST_VALUE

Established common OOS calibration folds:

6632

Fallback production method:

GLOBAL_PEER_MEDIAN_RETURN

Fallback product-held-out common OOS calibration folds:

4829

Products with calibrated uncertainty:

787

Explicit uncertainty/scenario gaps:

206

No Pre-Collector residual values are reused.

No invented volatility parameter is used.

## 3Y / 5Y

Direct 3Y validation:

FALSE

Direct 5Y validation:

FALSE

3Y output:

SCENARIO

5Y output:

SCENARIO

Downside:

Q10 calibrated annualized state

Base:

Q50 calibrated annualized state

Upside:

Q90 calibrated annualized state

These are scenario extrapolations and are not represented as directly
validated long-horizon forecasts.

## Dynamic universe

No fixed Secret Lair count is used.

Future Secret Lairs follow the same governed current-price, production-method,
comparable, and uncertainty assignment rules.

## Authority

1Y production forecast:

AUTHORIZED

1Y empirical uncertainty:

AUTHORIZED

3Y scenario:

AUTHORIZED

5Y scenario:

AUTHORIZED

Monte Carlo execution:

AUTHORIZED NEXT

Monte Carlo certification:

FALSE

Ranking:

NOT AUTHORIZED

Purchase recommendation:

NOT AUTHORIZED

Automatic purchase execution:

FALSE

## Next gate

SL5B_SECRET_LAIR_MONTE_CARLO_AND_RISK_DISTRIBUTION