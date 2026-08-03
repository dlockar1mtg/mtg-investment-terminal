# Collector Candidate v2.2 Scenario and Confidence Review

## Purpose

Evaluate whether inherited uncertainty widths and confidence scores remain economically defensible after Candidate Methodology v2.2 changed the base-rate construction.

## Problem identified

The Candidate v2.2 economic review showed inherited scenario widths producing downside annual rates below -100% for many comparable and limited-history products and upside annual rates above +200% for several limited-history products. Those widths were inherited from an older methodology and are not approved for Candidate v2.2.

## Diagnostic alternatives

For each product, the review records:

1. Inherited uncertainty width.
2. Retrospective-volatility width where available.
3. One-half of the methodology sensitivity spread.
4. A route-bounded maximum of available evidence components.
5. A loss-bounded evidence width that prevents the diagnostic downside annual rate from falling below -95%.

The review also creates a diagnostic confidence score using route maturity, peer depth, retrospective volatility, methodology sensitivity, reverse-score status, short-history status, and concentration flags.

## Boundaries

All proposed widths and confidence values are diagnostic only. This batch does not approve or activate scenario methodology, confidence methodology, candidate projections, production forecasts, purchase recommendations, or automatic model updates.

## Outputs

- `collector_candidate_v2_2_scenario_confidence_product_review.csv`
- `collector_candidate_v2_2_scenario_width_variants.csv`
- `collector_candidate_v2_2_scenario_confidence_route_summary.csv`
- `collector_candidate_v2_2_scenario_confidence_review_queue.csv`
- `collector_candidate_v2_2_scenario_confidence_review_summary.json`

## Next gate

After reviewing the evidence, the owner must explicitly approve or reject a replacement scenario-width methodology and confidence methodology before Candidate v2.2 can be considered for final freeze.
