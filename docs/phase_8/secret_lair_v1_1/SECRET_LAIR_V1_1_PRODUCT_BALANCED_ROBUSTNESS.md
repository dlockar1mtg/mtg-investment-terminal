# Secret Lair V1.1 — Product-Balanced Robustness Review

## Status

SECRET_LAIR_V1_1_PRODUCT_BALANCED_ROBUSTNESS_CERTIFIED

## Why this review was required

The SL-8C.2 multivariate winner beat EXACT_PEER_TRAJECTORY on the certified
common-fold tournament, but GLOBAL_REALIZED_MEDIAN produced lower event-level
SMAPE on that same restricted common-fold population.

Because Secret Lair V1.1 is intended to support selection among individual
products, this review gives each product equal influence.

No model is retrained.

No new forecast is generated.

## Evidence population

Products:

540

Historical OOS events:

2528

## Results

- LAST_VALUE: ProductBalancedSMAPE=0.25393359875916144; ProductSpearman=; ProductTopBottom=-0.012207259226326456; UniqueProductPredictions=1; Robustness=False
- GLOBAL_REALIZED_MEDIAN: ProductBalancedSMAPE=0.19227714509011334; ProductSpearman=-0.024922360340106784; ProductTopBottom=-0.01164598459076105; UniqueProductPredictions=60; Robustness=False
- EXACT_PEER_TRAJECTORY: ProductBalancedSMAPE=0.21318003912808112; ProductSpearman=-0.02501108380202701; ProductTopBottom=0.011290365617871778; UniqueProductPredictions=61; Robustness=False
- ANCHOR_PLUS_MOMENTUM_OLS: ProductBalancedSMAPE=0.20824749702925535; ProductSpearman=0.05735966533092013; ProductTopBottom=0.03856672323316934; UniqueProductPredictions=519; Robustness=False

## Production robustness

Candidate:

ANCHOR_PLUS_MOMENTUM_OLS

Best product-balanced baseline SMAPE:

0.19227714509011334

Candidate product-balanced SMAPE:

0.20824749702925535

Candidate product-level Spearman:

0.05735966533092013

Candidate product top-minus-bottom spread:

0.03856672323316934

Candidate unique product-level mean predictions:

519

Production robustness confirmed:

False

## Authority

V1 preserved:

TRUE

Production forecast created:

FALSE

Automatic execution:

FALSE

## Next gate

SL8C4_SECRET_LAIR_V1_1_MODEL_STRATEGY_REVIEW