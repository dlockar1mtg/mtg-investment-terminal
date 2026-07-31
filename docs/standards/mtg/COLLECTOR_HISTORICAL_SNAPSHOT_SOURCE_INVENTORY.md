# Collector Historical Snapshot Source Inventory

## Purpose

This step inventories repository CSV sources that might support time-correct Collector backtests.

It does not build historical forecasts and does not treat present-day files as historical evidence.

## Required historical reconstruction

For every decision date, a later snapshot builder must reconstruct only information available as of that date:

- product identity,
- available price,
- available history,
- available evidence,
- available comparables,
- route that would have been assigned,
- candidate model version under test.

## Readiness classes

- `READY_FOR_PRICE_AS_OF_JOIN`: contains an identity field, temporal field, and price field.
- `READY_FOR_NONPRICE_AS_OF_JOIN`: contains identity and temporal fields.
- `IDENTITY_ONLY_NO_TIME_KEY`: cannot prove when the information was available.
- `TIME_KEY_ONLY_NO_IDENTITY`: cannot connect evidence to a governed product.
- `NOT_READY`: lacks both a governed identity key and a temporal key.
- `UNREADABLE`: could not be parsed safely.

## Governing interpretation

A file may be a useful candidate source without being historically valid. File modification timestamps are inventory metadata only and must never be substituted for observation dates.

Current outputs, regenerated files, and present-day classifications must not be backdated.

Where a historical source is missing, the snapshot must show the missing input rather than borrowing later evidence.

## Outputs

The audit writes:

- `collector_historical_snapshot_source_inventory.csv`
- `collector_historical_snapshot_source_review_required.csv`
- `collector_historical_snapshot_source_inventory_summary.json`

under:

`data/operations/collector_backtest_source_inventory/candidate_v1_0_0/`

## Authorization state

This inventory does not authorize:

- a historical snapshot builder,
- candidate forecasts,
- production forecasts,
- parameter activation,
- purchase recommendations.
