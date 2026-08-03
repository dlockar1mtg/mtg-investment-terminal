# Collector Current Data Controlled Rebuild Plan

## Objective

Produce current Collector Booster forecasts, rankings, maximum purchase prices, and purchase recommendations that are reproducible from one recent, immutable, provider-traceable snapshot and that satisfy the Collector Data Snapshot and Lineage Standard.

## Non-negotiable rule

No downstream model, ranking, maximum-price calculation, purchase recommendation, or UIP export may be treated as current until the end-to-end snapshot lineage certification passes in strict mode.

## Controlled rebuild stages

### Stage 1 — Source trace and authority adjudication

1. Inventory every code and data file that produces or consumes `current_price`, `latest_price_date`, `accepted_listing_count`, and `review_listing_count`.
2. Identify the true upstream marketplace collector and all transformations between raw collection and the feature matrix.
3. Identify and remove or explicitly govern:
   - run-date substitution;
   - forward-filled current prices;
   - carried-forward observations presented as fresh;
   - latest-file-by-modification-time selection;
   - historical/current column collisions;
   - silent fallback sources.
4. Publish a source-authority decision record with exact paths, hashes, provider identity, required credentials, and execution command.

**Exit gate:** one adjudicated current-market ingestion entry point and no unresolved silent fallback.

### Stage 2 — Fresh immutable snapshot capture

1. Run the adjudicated collector.
2. Preserve raw provider responses and normalized current authorities in a new immutable snapshot directory.
3. Generate the snapshot ID and manifest.
4. Record source-observation timestamps separately from capture and generation timestamps.
5. Hash every declared source file.
6. Record all exclusions, failures, carried-forward values, and missing records.

**Exit gate:** snapshot manifest passes source completeness, hash, provenance, observation-date, and product-reconciliation checks.

### Stage 3 — Snapshot-bound feature rebuild

1. Rebuild current-state features only from the certified snapshot.
2. Join historical training data explicitly by product ID without allowing it to overwrite current-state fields.
3. Write lineage columns into the feature matrix.
4. Verify all 50 governed products and identify any product-specific stale or missing current records.

**Exit gate:** feature matrix hash matches the snapshot manifest and all current-state columns trace to the snapshot.

### Stage 4 — Snapshot-bound model rebuild

Run the governed pipeline in order:

1. route assignment;
2. short-horizon forecast application;
3. long-horizon scenario application;
4. product-level forecast and ranking tournament;
5. forecast-compression certification;
6. transaction-cost-adjusted maximum-price calculation;
7. individual purchase-adequacy certification.

Every stage must emit the same snapshot ID and matching source hashes.

**Exit gate:** all model and calculation certifications pass with no cross-snapshot or hash mismatch.

### Stage 5 — End-to-end certification and comparison

1. Run strict end-to-end snapshot lineage certification.
2. Compare the rebuilt outputs with the suspended prior outputs.
3. Explain every material change in price, route, forecast, rank, status, and maximum purchase price.
4. Reinstate only individually qualified products.
5. Keep production forecasting and UIP delivery separately blocked until their own integration certifications pass.

**Exit gate:** `pipeline_snapshot_lineage_certified=true`, zero critical failures, and an approved change-comparison report.

## Required evidence package

The controlled rebuild must produce:

- source-trace inventories;
- source-authority decision record;
- immutable snapshot files;
- snapshot manifest and hashes;
- snapshot certification;
- snapshot-bound feature matrix;
- downstream stage summaries with lineage fields;
- final end-to-end lineage certification;
- old-versus-new output comparison;
- current authorization state.

## Authorization policy

- Historical model methodology may remain certified independently.
- Current analytical outputs remain suspended until the controlled rebuild completes.
- Product-specific stale, missing, carried-forward, or thin-listing records fail closed.
- No global gate may be weakened solely to create recommendations.
- No product may be authorized because a downstream script was rerun more recently than its source observation.
