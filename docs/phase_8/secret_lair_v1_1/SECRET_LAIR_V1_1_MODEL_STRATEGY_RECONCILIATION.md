# Secret Lair V1.1 — Model Strategy Reconciliation

## Status

SECRET_LAIR_V1_1_MODEL_STRATEGY_RECONCILED

## Product-balanced evidence

Products:

540

Historical OOS events:

2528

Best product-balanced calibration baseline:

GLOBAL_REALIZED_MEDIAN

Best baseline product-balanced SMAPE:

0.192277145090113

Prior individualized candidate:

ANCHOR_PLUS_MOMENTUM_OLS

Candidate product-balanced SMAPE:

0.208247497029255

Candidate product-level Spearman:

0.0573596653309201

Candidate product top-minus-bottom spread:

0.0385667232331693

Candidate unique product-level predictions:

519

Production robustness confirmed:

FALSE

## Interpretation

The prior multivariate model demonstrated that recent product-specific momentum
contains useful investment-selection information.

However, EXACT_PEER_TRAJECTORY was not the strongest calibration anchor.

GLOBAL_REALIZED_MEDIAN remains the strongest product-balanced calibration
baseline observed in the governed evidence.

The next model strategy therefore changes the anchor rather than adding more
features.

## Next architecture

Forecast return:

GLOBAL_REALIZED_MEDIAN
+
LEARNED_PRODUCT_SPECIFIC_RESIDUAL

The residual is learned temporally out of sample.

Authorized product-specific candidates:

1. GLOBAL_PLUS_MOMENTUM_OLS

Predictors:

- own latest interval annualized log return;
- own recent-minus-median momentum.

2. GLOBAL_PLUS_MOMENTUM_AND_PEER_GAP_OLS

Predictors:

- own latest interval annualized log return;
- own recent-minus-median momentum;
- exact-peer trajectory minus the global baseline.

Exact-peer information is therefore retained as evidence but is no longer
forced to be the forecast anchor.

## Prohibited behavior

No manual blend coefficient.

No manual feature weights.

No forced unique forecast per product.

No current-snapshot leakage into historical training.

No production forecast before validation.

## Promotion standard

A product-specific candidate must:

- beat GLOBAL_REALIZED_MEDIAN on common-fold SMAPE;
- retain positive rank discrimination;
- retain positive top-minus-bottom realized-return spread;
- have a noncollapsed forecast distribution;
- survive product-balanced robustness review.

Accuracy alone is insufficient.

## Authority

SL-8C.2 preserved:

TRUE

SL-8C.3 preserved:

TRUE

Certified Secret Lair V1 preserved:

TRUE

V1.1 production forecast:

FALSE

Automatic execution:

FALSE

## Next gate

SL8C5_SECRET_LAIR_V1_1_GLOBAL_CALIBRATED_PRODUCT_MODEL_TOURNAMENT