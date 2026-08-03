# Collector Forecast Implementation Traceability Process

## Purpose

This process inventories existing Collector forecasting behavior before any production forecast engine is selected or changed.

It does not create methodology. It does not authorize projections or purchase recommendations.

## Authority rule

Every active formula, factor, threshold, weight, route, penalty, exception, confidence rule, uncertainty rule, or eligibility decision must map to one of:

1. an existing MTG forecasting standard;
2. an existing owner-approved governance artifact; or
3. a new explicit approval from Devon Lockard.

Anything that cannot be mapped remains inactive and must be presented for owner review.

## Required outputs

The traceability audit produces:

- `collector_forecast_implementation_inventory.csv`
- `collector_standard_source_inventory.csv`
- `collector_traceability_review_required.csv`
- `collector_forecast_traceability_summary.json`

The implementation inventory intentionally begins with `authority_status=REVIEW_REQUIRED` and `production_status=UNDETERMINED`. Those values may be changed only after documentary review against the standards and owner-approved artifacts.

## Review sequence

1. Inventory existing scripts and expressions.
2. Identify which files are authoritative, supporting, historical, or superseded.
3. Map each active behavior to its exact standard or approval source.
4. Identify conflicts between implementations.
5. Keep unsupported behavior inactive.
6. Present true standards gaps to the owner.
7. Change production methodology only after owner approval where the standards do not already resolve the issue.

## Certification boundary

Passing this inventory does not certify forecasts. Collector numeric production remains unauthorized until structural, data, semantic, output, UIP, and owner-acceptance gates are completed.
