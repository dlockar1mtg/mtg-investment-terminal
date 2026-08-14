# Secret Lair V1.1 — Multivariate Product Model Tournament

## Status

SECRET_LAIR_V1_1_MULTIVARIATE_PRODUCT_MODEL_TOURNAMENT_CERTIFIED

## Recovery

The first SL-8C.2 attempt failed before model evaluation because the earliest
historical origins had no matured outcomes available for multivariate training.

The failed evidence package was preserved:

C:\Users\DevonLockard\Downloads\UIP_MTG_Governance\Secret_Lair_V1_1\Product_Specific_Forecasting\SL8C2_MULTIVARIATE_MODEL_TOURNAMENT_20260812_141902

The recovery does not add an arbitrary training threshold.

A learned model is simply unavailable at an origin where zero training
outcomes have matured.

Those origins cannot enter the common-fold model comparison.

## Architecture

Forecast anchor:

EXACT_PEER_TRAJECTORY

Learned residual target:

REALIZED_ANNUALIZED_LOG_RETURN_MINUS_EXACT_PEER_TRAJECTORY

Estimator:

EXPANDING_WINDOW_ORDINARY_LEAST_SQUARES

Manual feature weights:

FALSE

## Temporal OOS population

Common folds:

2528

Only matured historical targets were eligible to train later predictions.

## Tournament results

- LAST_VALUE: SMAPE=0.250193118320794; Spearman=; Top-Bottom=0.03154058797297957; Unique=1; BeatsPeer=False; Promotion=False
- GLOBAL_REALIZED_MEDIAN: SMAPE=0.18802243595556925; Spearman=0.04443157753516439; Top-Bottom=0.03492213220545465; Unique=35; BeatsPeer=False; Promotion=False
- EXACT_PEER_TRAJECTORY: SMAPE=0.20872186342285226; Spearman=0.008564473225114461; Top-Bottom=0.017215585420343044; Unique=33; BeatsPeer=False; Promotion=False
- ANCHOR_PLUS_MOMENTUM_OLS: SMAPE=0.19588801379742354; Spearman=0.053708024337506904; Top-Bottom=0.04167151899831861; Unique=2415; BeatsPeer=True; Promotion=True
- ANCHOR_PLUS_BEHAVIOR_OLS: SMAPE=0.3073882129970733; Spearman=0.11042447878836867; Top-Bottom=0.07697884418836706; Unique=2460; BeatsPeer=False; Promotion=False
- ANCHOR_PLUS_BEHAVIOR_VALUATION_OLS: SMAPE=0.6614801612838386; Spearman=0.09668147844131508; Top-Bottom=0.06466080297881358; Unique=2526; BeatsPeer=False; Promotion=False
- ANCHOR_PLUS_FULL_STRUCTURE_OLS: SMAPE=0.6430256569778688; Spearman=0.10337395305043608; Top-Bottom=0.062257320292453566; Unique=2526; BeatsPeer=False; Promotion=False

## Promotion

Candidate:

ANCHOR_PLUS_MOMENTUM_OLS

Status:

MULTIVARIATE_PRODUCT_SPECIFIC_MODEL_PASSED_ACCURACY_AND_DISCRIMINATION_GATE

Promotion requires all of:

- lower common-fold SMAPE than EXACT_PEER_TRAJECTORY;
- positive rank discrimination;
- positive top-minus-bottom realized-return spread;
- noncollapsed prediction distribution.

## Authority

V1 preserved:

TRUE

Production forecast created:

FALSE

Ranking changed:

FALSE

Purchase recommendation changed:

FALSE

Automatic purchase execution:

FALSE

## Next gate

SL8D_SECRET_LAIR_V1_1_PRODUCT_SPECIFIC_PRODUCTION_FORECAST