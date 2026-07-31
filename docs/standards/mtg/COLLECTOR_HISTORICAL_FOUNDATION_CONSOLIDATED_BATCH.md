# Collector Historical Foundation — Consolidated Candidate Batch

## Purpose

This batch replaces the narrow semantic profiler with one governed historical-foundation workflow. It corrects identifier normalization, reconciles the governed Collector universe, adjudicates the primary and supporting ledgers, preserves source lineage, applies release boundaries, classifies knowledge availability, produces a deduplicated governed history dataset, and reports historical snapshot readiness.

It does not authorize historical snapshots, forecasts, methodology activation, projections, or purchases.

## Root cause corrected

Prior matching compared raw CSV string representations. Numeric identifiers can be parsed as values such as `123456.0` while the governed registry contains `123456`. The consolidated builder canonicalizes integral identifiers before matching and preserves the original identifier for audit purposes.

## Inputs

- Primary observation ledger
- Supporting price-history ledger
- Governed Collector registry
- Applied Collector admissions when present
- Governed release-date evidence

The governed universe is not hard-coded to a product count. Applied admissions can extend the earlier registry without changing the script.

## Major processing stages

1. Normalize TCGplayer identifiers.
2. Reconcile governed registry and applied admissions.
3. Extract Collector observations from both ledgers.
4. Profile source, date, price, currency, and live/backfill semantics.
5. Measure exact ledger overlap.
6. Preserve primary-source precedence and retain supporting rows only when unique.
7. Join governed identity and release dates.
8. Identify pre-release observations.
9. Classify knowledge availability.
10. Separate historical decision-input eligibility from outcome-measurement eligibility.
11. Produce exclusions with explicit reasons.
12. Produce per-product historical readiness without inventing minimum thresholds.

## Temporal treatment

`observation_date` is not automatically treated as the date on which the platform could have known the value.

Only observations explicitly classified as contemporaneous live observations are marked candidate-eligible for historical decision inputs. Retrospective or unverified observations remain visible and may be used for outcome measurement when otherwise valid, but fail closed as historical decision inputs.

No owner-approved policy yet permits retrospective rows to be treated as historically available inputs.

## Generated outputs

The candidate output directory contains:

- `collector_identity_reconciliation.csv`
- `collector_ledger_source_profile.csv`
- `collector_ledger_overlap_summary.json`
- `collector_governed_historical_observations.csv`
- `collector_historical_exclusions.csv`
- `collector_product_history_readiness.csv`
- `collector_historical_foundation_summary.json`

## Readiness interpretation

The batch reports factual availability only:

- Product has any governed historical observations
- Product has observations proven contemporaneously available
- Product has outcome-measurement history
- Product has retrospective observations
- Product has pre-release observations

No minimum observation count or minimum history span is approved. The batch therefore does not convert data availability into model-route authorization.

## Required review after execution

Review:

1. Governed universe product count and identity reconciliation.
2. Collector coverage in each ledger.
3. Primary/supporting overlap classification.
4. Live, retrospective, and unknown knowledge classifications.
5. Pre-release exclusions.
6. Per-product historical decision-input coverage.
7. Whether the resulting source and temporal semantics are sufficient to propose historical-foundation authorization.

## Authorization boundary

The following remain false:

- Historical foundation authorized
- Historical snapshot builder authorized
- Exact numeric specification approved
- Methodology activated
- Projection authorized
- Purchase recommendation authorized
