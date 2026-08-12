# Secret Lair V1.1 — Global-Calibrated Product Model Tournament

## Status

SECRET_LAIR_V1_1_GLOBAL_CALIBRATED_PRODUCT_MODEL_TOURNAMENT_CERTIFIED

## Architecture

Forecast return:

GLOBAL_REALIZED_MEDIAN
+
LEARNED PRODUCT-SPECIFIC RESIDUAL

Each historical event's global baseline is reconstructed at that event's own
historical origin.

Historical residual training therefore does not use a future/global baseline.

## Common temporal OOS folds

2992

## Product-balanced products

543

## Event-level results

- GLOBAL_REALIZED_MEDIAN: SMAPE=0.1868250861371069; Spearman=0.03688313966373373; TopBottom=0.02903935267623778; Unique=41; Gate=False
- GLOBAL_PLUS_MOMENTUM_OLS: SMAPE=0.19389448138375798; Spearman=0.03027646272728857; TopBottom=0.019576564492589432; Unique=52; Gate=False
- GLOBAL_PLUS_MOMENTUM_AND_PEER_GAP_OLS: SMAPE=0.20047158759297892; Spearman=0.03092628903246061; TopBottom=0.01942740558775166; Unique=170; Gate=False

## Equal-product robustness results

- GLOBAL_REALIZED_MEDIAN: PB-SMAPE=0.1910458785725496; PB-Spearman=-0.040459261930532196; PB-TopBottom=-0.018207726576676964; UniqueProducts=70; Gate=False
- GLOBAL_PLUS_MOMENTUM_OLS: PB-SMAPE=0.19846165054514572; PB-Spearman=-0.039093401085004066; PB-TopBottom=-0.019445454110410126; UniqueProducts=70; Gate=False
- GLOBAL_PLUS_MOMENTUM_AND_PEER_GAP_OLS: PB-SMAPE=0.20521071344952915; PB-Spearman=-0.025539548061102278; PB-TopBottom=-0.026278628815475602; UniqueProducts=168; Gate=False

## Promotion

Candidate:

NONE

Status:

NO_GLOBAL_CALIBRATED_PRODUCT_SPECIFIC_MODEL_PASSED_BOTH_GATES

A candidate must pass both the event-level and equal-product gates.

No weighted selection score is used.

## Governance

Manual feature weights:

FALSE

Manual blend weight:

FALSE

Current snapshot used for historical training:

FALSE

Production forecast created:

FALSE

Certified V1 replaced:

FALSE

Automatic purchase execution:

FALSE

## Next gate

SL8C6_SECRET_LAIR_V1_1_MODELING_STOP_AND_SIGNAL_PLACEMENT_REVIEW