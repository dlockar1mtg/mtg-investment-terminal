# Secret Lair V1.1 — Product-Specific Simple Signal Tournament

## Status

SECRET_LAIR_V1_1_PRODUCT_SIGNAL_TOURNAMENT_CERTIFIED

## Common OOS folds

6887

## Candidate results

- LAST_VALUE: SMAPE=0.2450940601865836; Spearman=; Top-Bottom=-0.009506953257198109; Unique=1; Promotion=False
- GLOBAL_REALIZED_MEDIAN: SMAPE=0.21808422351805626; Spearman=0.05529194936631621; Top-Bottom=0.04087269764721335; Unique=42; Promotion=False
- OWN_ANNUALIZED_TRAJECTORY: SMAPE=0.43045941384828784; Spearman=0.0022265325354605923; Top-Bottom=0.0090629498062961; Unique=6847; Promotion=False
- OWN_LOG_PRICE_SLOPE: SMAPE=0.4161637406203981; Spearman=0.01777652210083384; Top-Bottom=0.016885515949989632; Unique=6852; Promotion=False
- RECENT_MOMENTUM: SMAPE=0.4154262738730512; Spearman=0.17503568726102395; Top-Bottom=0.0998084602526848; Unique=6530; Promotion=False
- EXACT_PEER_TRAJECTORY: SMAPE=0.21487915509241193; Spearman=0.034062953862140644; Top-Bottom=0.013937157689018098; Unique=79; Promotion=True

## Relative valuation diagnostic

Rows:

6887

Spearman:

-0.01999878213659749

Top-minus-bottom quartile realized log return:

-0.032389059537123704

Relative valuation was not converted into a forecast through an arbitrary
coefficient.

It remains authorized as an input to a learned multivariate model.

## Promotion

Candidate:

EXACT_PEER_TRAJECTORY

Status:

SIMPLE_PRODUCT_SPECIFIC_CANDIDATE_PASSED_GATE

## Governance

Accuracy alone is insufficient.

Promotion requires:

- noncollapsed predictions;
- positive rank discrimination;
- positive top-versus-bottom realized-return spread;
- lower common-fold SMAPE than the best V1-style baseline.

Weighted score:

FALSE

Production forecast created:

FALSE

V1 replaced:

FALSE

Automatic purchase execution:

FALSE

## Next gate

SL8D_SECRET_LAIR_V1_1_PRODUCT_SPECIFIC_PRODUCTION_FORECAST