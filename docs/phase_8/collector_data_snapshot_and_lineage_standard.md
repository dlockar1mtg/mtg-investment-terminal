# Collector Data Snapshot and Lineage Standard

## Purpose

Every Collector Booster analytical output must be traceable to one recent, immutable source snapshot. A pipeline run is not considered a data refresh merely because downstream scripts were rerun.

## Required snapshot identity

Each governed run must have one `snapshot_id` in the form `collector-YYYYMMDDTHHMMSSZ-<8-char-hash>` and one manifest at:

`data/governance/permanence/snapshots/<snapshot_id>/collector_snapshot_manifest.json`

The manifest must include:

- `snapshot_id`
- `captured_at_utc`: when ingestion completed
- `maximum_source_observation_at_utc`: newest accepted market observation
- `minimum_source_observation_at_utc`: oldest accepted market observation
- `freshness_cutoff_utc`
- `product_count`
- source file paths and SHA-256 hashes
- source/provider identity
- product-level price-date coverage
- product-level listing coverage
- explicit exclusions and reasons
- `certified_for_model_input`

## Time semantics

These fields must never be conflated:

- **captured_at_utc**: when the ingestion job ran.
- **source_observation_at_utc**: when the marketplace observation was valid.
- **generated_at_utc**: when a downstream model artifact was produced.

A downstream `generated_at_utc` does not refresh `source_observation_at_utc`.

## Freshness rules

1. Purchase-facing runs require every individually authorized product to have a valid observation date within the configured freshness window.
2. A model may include older historical observations for training, but its current-state features must come from the active snapshot.
3. Missing dates are never imputed with the pipeline run date.
4. Carried-forward prices must be explicitly labeled `carried_forward=true` and are ineligible for purchase authorization.
5. A snapshot may contain product-specific stale records, but those products must fail closed.

## Lineage rules

Every downstream certification summary and output dataset must include:

- `source_snapshot_id`
- `source_snapshot_manifest_sha256`
- `source_feature_matrix_sha256`
- `source_price_authority_sha256`
- `source_route_authority_sha256`
- `model_generated_at_utc`

All stages in one governed run must reference the same snapshot ID and matching source hashes. Any mismatch invalidates the run.

## Pipeline order

1. Ingest current marketplace data.
2. Write immutable snapshot files and manifest.
3. Certify snapshot completeness, dates, hashes, and provider provenance.
4. Build the feature matrix only from the certified snapshot.
5. Run route assignment, forecasts, rankings, and purchase adequacy.
6. Run end-to-end lineage certification.
7. Publish recommendations only after lineage certification passes.

## Fail-closed conditions

The pipeline must stop when:

- no certified snapshot is supplied;
- a downstream file references a different snapshot;
- a source hash differs from the manifest;
- the feature matrix observation dates are newer than their source records;
- a refresh timestamp is substituted for a market observation timestamp;
- an authorized product has stale, missing, or carried-forward current data;
- generated outputs cannot be reproduced from the declared snapshot.

## Historical-data separation

Historical training data and current decision data must be separate authorities. Historical files may never silently overwrite or populate current-price fields. Joins must be explicit on product ID, and current-state columns must be suffixed or namespaced when ambiguity is possible.

## Required run record

Each end-to-end run must emit:

`data/governance/permanence/certification/collector_v1_pipeline_lineage/<snapshot_id>/collector_v1_pipeline_lineage_certification.json`

This is the final authority for whether the run used recent, internally consistent data. Purchase recommendations and UIP delivery remain blocked unless it passes.
