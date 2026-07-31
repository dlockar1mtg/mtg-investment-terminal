# Collector Historical Ledger Semantic Review Candidate

## Purpose

This review determines whether the universal historical observation ledger can serve as the authoritative historical price source for Collector Booster walk-forward backtesting.

The review does not authorize the ledger, construct historical decision snapshots, activate forecasts, or authorize purchase recommendations.

## Candidate sources

Primary candidate:

`data/operations/mtg_universal_history_ledger/universal_mtg_historical_observation_ledger.csv`

Supporting candidate:

`data/operations/mtg_history_foundation/universal_mtg_price_history.csv`

Collector identity boundary:

`data/validation/phase_10/collector_booster_boxes/governed_registry/collector_booster_box_governed_registry.csv`

## Required semantic questions

The review must determine:

1. Which governed Collector products are covered by each ledger.
2. Whether `observation_date` represents the historical market date.
3. Whether `observed_at_utc` represents when the system actually knew the observation.
4. Which rows are live observations and which are retrospective backfills.
5. Whether market, low, and high price fields have consistent meaning across sources.
6. Whether duplicate observation fingerprints represent exact duplicate records or valid source alternatives.
7. Whether the supporting ledger is a strict subset, predecessor, duplicate, or independent source.
8. Whether every observation has adequate source and collection-run lineage.
9. Whether any rows predate the governed product release boundary.
10. Whether nonpositive, missing, non-USD, or structurally extreme prices require quarantine.

## Knowledge-availability boundary

`observation_date` is not automatically the date on which the model could have known the observation.

A historical decision input must satisfy both:

- The market observation occurred on or before the simulated decision date.
- The observation was available to the modeled information set on or before the simulated decision date.

Where `observed_at_utc` has validated semantics, it may become a candidate proxy for knowledge availability. Otherwise, retrospective observations must remain visibly classified and may not be used as decision inputs without an owner-approved policy.

Retrospective price history may still be valid for measuring later realized outcomes even when it is prohibited as a simulated historical input.

## Expected outputs

The audit writes:

- `collector_historical_ledger_semantic_review_summary.json`
- `collector_historical_ledger_source_summary.csv`

under:

`data/operations/collector_historical_ledger_semantic_review/candidate_v1_0_0/`

The outputs profile:

- Collector rows and products
- Registry coverage
- Earliest and latest dates
- Invalid dates
- Missing and nonpositive prices
- Duplicate fingerprints
- Live, nonlive, and unknown observation status
- Source, price-field, and currency diversity
- Overlap between primary and supporting ledgers

## Authorization boundary

The following remain false until separate semantic review and owner approval:

- `primary_ledger_authorized`
- `historical_snapshot_builder_authorized`
- `projection_authorized`
- `purchase_recommendation_authorized`

A passing audit means only that the candidate review ran successfully and preserved the authorization boundary.
