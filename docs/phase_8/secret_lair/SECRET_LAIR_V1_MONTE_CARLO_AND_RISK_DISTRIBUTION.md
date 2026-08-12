# Secret Lair V1 — Monte Carlo and Risk Distribution

## Status

SECRET_LAIR_V1_MONTE_CARLO_AND_RISK_DISTRIBUTION_CERTIFIED

## Simulation design

Paths per product / horizon:

10000

Horizons:

- 1Y
- 3Y
- 5Y

Simulation engine:

EMPIRICAL_BOOTSTRAP_LOG_RETURN_PATHS

Gaussian distribution assumed:

FALSE

Secret Lair OOS residuals used:

TRUE

Pre-Collector residual values reused:

FALSE

Deterministic product seeds:

TRUE

Common random numbers within each product:

TRUE

## Coverage

Snapshot products:

993

Simulated products:

787

Explicit simulation gaps:

206

Simulated product-horizons:

2361

Terminal outcomes generated:

23610000

The raw path matrix is not persisted because deterministic seeds and governed inputs permit exact replay.

## Required risk outputs

Each simulated product/horizon includes:

- expected terminal value;
- Q05;
- Q10;
- Q25;
- Q50;
- Q75;
- Q90;
- Q95;
- expected total return;
- median total return;
- probability of loss;
- probability of positive return;
- downside Q10-tail mean;
- upside Q90-tail mean.

## Long-horizon semantics

1Y:

DIRECT_1Y_FORECAST_DISTRIBUTION

3Y:

SCENARIO_DISTRIBUTION_NOT_DIRECTLY_VALIDATED

5Y:

SCENARIO_DISTRIBUTION_NOT_DIRECTLY_VALIDATED

Direct 3Y validation:

FALSE

Direct 5Y validation:

FALSE

## Dynamic universe

No fixed Secret Lair count is encoded in the simulation logic.

Future Secret Lairs enter Monte Carlo after passing the same governed identity,
current-price, forecast-method, comparable, and uncertainty gates.

No product lacking a governed current TCG market price receives synthetic paths.

## Authority

Monte Carlo:

AUTHORIZED AND CERTIFIED

Risk distributions:

AUTHORIZED AND CERTIFIED

Investment ranking execution:

AUTHORIZED NEXT

Ranking certification:

FALSE

Purchase analysis:

FALSE

Purchase recommendation:

FALSE

Automatic purchase execution:

FALSE

## Next gate

SL6A_SECRET_LAIR_INVESTMENT_RANKING_AND_PURCHASE_ANALYSIS