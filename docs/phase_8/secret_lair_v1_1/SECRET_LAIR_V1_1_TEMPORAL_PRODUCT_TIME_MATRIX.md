# Secret Lair V1.1 — Temporal Product-Time Feature Matrix

## Status

SECRET_LAIR_V1_1_TEMPORAL_PRODUCT_TIME_MATRIX_CERTIFIED

## Purpose

This dataset reconstructs the product-specific evidence available at each
historical forecast origin.

Future observations are prohibited from predictor construction.

## Matrix

Rows:

7776

Products represented:

547

Unique product/origin pairs:

7776

Rows with at least two own-history observations:

7229

Rows with exact structural peer price evidence:

7776

Rows with exact structural peer trajectory evidence:

7430

## Anti-leakage certification

Own-history future violations:

0

Peer-history future violations:

0

Target held out of peer aggregates:

TRUE

Future endpoint used only as target:

TRUE

## Product-specific historical predictors

The matrix includes historical-origin versions of:

- own price trajectory;
- own annualized historical return;
- own price slope;
- recent momentum;
- recent-versus-own-history momentum;
- volatility;
- downside semi-deviation;
- maximum drawdown;
- position versus own historical median/high/low;
- foil / finish;
- product family and configuration;
- exact structural peer price median at origin;
- relative valuation versus exact peers at origin;
- exact structural peer trajectory available at origin;
- own trajectory relative to exact peers.

## Endpoint

Target horizon:

365 days

Existing Secret Lair V1 endpoint method is preserved:

nearest later observation to origin + 365 days.

No new endpoint tolerance was introduced.

## Modeling status

Model fitted:

FALSE

Model tournament execution:

AUTHORIZED NEXT

V1.1 production forecast:

FALSE

## Next gate

SL8C_SECRET_LAIR_V1_1_PRODUCT_SPECIFIC_MODEL_TOURNAMENT