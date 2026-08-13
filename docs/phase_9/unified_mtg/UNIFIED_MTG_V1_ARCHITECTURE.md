# Unified MTG V1 Architecture

## Status

UNIFIED_MTG_V1_SCHEMA_ARCHITECTURE_CERTIFIED

## Purpose

Unified MTG provides a common interface across three independently governed
production lanes:

1. Collector V1
2. Pre-Collector V1
3. Secret Lair V1.1

It does not replace their native methods.

## Governing principle

COMMON INTERFACE, NATIVE LANE SEMANTICS PRESERVED.

Unified MTG does not create a common predictive model, common ranking score,
or common purchase policy.

## Collector

Certified current-price snapshot products:

50

Certified ranked products:

49

Native ranking field:

final_rank

Native purchase status:

purchase_status

Collector ranking weights and purchase thresholds remain Collector-only.

## Pre-Collector

Canonical products:

131

Ranked / forecastable products:

95

Forecast gaps:

26

Products without current-price authority:

10

Complete canonical disposition:

precollector_final_131_product_disposition_v1.csv

Primary product-level purchase authority:

precollector_purchase_ranking_v1.csv

Three-year and five-year outputs remain scenarios and are not directly
backtested long-horizon forecasts.

## Secret Lair V1.1

Current ranked snapshot:

787

The product universe is dynamic.

787 is not a permanent universe count.

Native ranking:

v1_1_production_competition_rank

Native purchase recommendation:

purchase_recommendation

BUY_CANDIDATE_NOW means:

MODEL_QUALIFIED_ENTRY_CANDIDATE

It does not certify an execution-ready purchase.

Live execution-price verification remains required.

## Unified schema

Unified rows expose common interface concepts including:

- lane-qualified asset identity
- native identity
- product name
- current-price authority state
- forecast availability
- risk authority availability
- native rank
- native purchase status
- purchase semantics
- evidence state
- actionability
- execution authority
- native source lineage and SHA-256

## Rank governance

Native lane ranks are retained.

They are not directly comparable across lanes.

Unified MTG V1 does not create a cross-lane rank.

## Purchase governance

Native purchase policies are retained.

Unified MTG V1 does not create a cross-lane purchase score or threshold.

## Missing authority

Missing price, forecast, risk, rank, or purchase authority remains explicit.

Missing values are never converted to zero, worst rank, WAIT, or another
synthetic state.

## Automatic execution

Automatic purchase execution remains disabled.

## Next gate

MTG_U1C_NORMALIZED_PRODUCT_AUTHORITY_ASSEMBLY