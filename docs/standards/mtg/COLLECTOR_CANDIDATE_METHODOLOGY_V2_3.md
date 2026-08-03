# Collector Candidate Methodology v2.3

## Status

Candidate v2.3 is authorized for development and testing only.

It does not authorize production forecasts, purchase recommendations, automatic model updates, reverse-score production use, or the Japanese FINAL FANTASY hybrid formula.

## Preserved Base Methodology

Candidate v2.3 preserves Candidate v2.2 base annual rates, including:

- similarity-weighted 10% trimmed comparable aggregation;
- simple observed return for histories under 365 days;
- one-time route blending;
- separately disclosed fundamental adjustments;
- diagnostic-only reverse-score routes;
- inactive Japanese FINAL FANTASY hybrid formula.

## Approved Scenario Methodology

Decision: `COL-SCEN-001`

`APPROVE_ROUTE_BOUNDED_EVIDENCE_WIDTH_WITH_95_PERCENT_LOSS_FLOOR`

Scenario width is the maximum of:

- the route minimum width;
- available retrospective volatility;
- half of methodology sensitivity spread.

The width is bounded by the route maximum and adjusted so the downside annual rate does not fall below -95%.

| Route | Minimum | Maximum |
|---|---:|---:|
| DIRECT_HISTORY_CALIBRATED | 0.10 | 0.20 |
| COMPARABLE_PRODUCT_ADJUSTED | 0.20 | 0.45 |
| DIRECT_HISTORY_LIMITED | 0.30 | 0.75 |
| FUNDAMENTAL_COMPARABLE_HYBRID | 0.35 | 0.60 |

## Approved Confidence Methodology

Decision: `COL-CONF-001`

`APPROVE_NORMALIZED_EVIDENCE_CONFIDENCE_0_TO_100`

Confidence is calculated internally on a 0-to-1 scale and exported on a 0-to-100 scale. The evidence model includes route maturity, peer depth, methodology sensitivity, retrospective volatility, short-history status, reverse-score status, and peer concentration.

Restrictions:

- reverse-score diagnostic routes are capped at 10/100;
- the inactive Japanese hybrid is capped at 15/100.

## Outputs

The builder writes:

- `collector_candidate_methodology_v2_3_forecasts.csv`
- `collector_candidate_methodology_v2_3_comparison.csv`
- `collector_candidate_methodology_v2_3_route_summary.csv`
- `collector_candidate_methodology_v2_3_owner_approval_register.csv`
- `collector_candidate_methodology_v2_3_summary.json`

## Required Validation

Run both normal and strict modes for the builder and audit. Candidate v2.3 remains inactive unless a later, separate production forecast authorization is granted.
