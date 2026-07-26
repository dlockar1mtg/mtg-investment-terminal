# Phase 10.17 — Full Marketplace Universe

## Purpose

Expand the certified three-product marketplace pilot into a governed full-universe collection process for all approved products in `data/product_master/product_master_model_input.csv`.

## Design

1. Build a deterministic product map from the product master.
2. Classify every row as `READY` or with an explicit mapping deficiency.
3. Deduplicate by approved TCGplayer identity.
4. Process `READY` products in bounded batches.
5. Run the existing certified eBay and TCGCSV lanes for every batch.
6. Persist batch evidence, aggregate normalized observations, and write a checkpoint.
7. Upload the entire run as a GitHub Actions artifact.

## Mapping statuses

- `READY`
- `MISSING_PRODUCT_NAME`
- `MISSING_TCGPLAYER_ID`
- `MISSING_TCGCSV_CATEGORY`
- `MISSING_TCGCSV_GROUP`
- `NOT_APPROVED`
- `DUPLICATE_IDENTITY`

Only `READY` products enter live collection.

## Controls

- `batch_size`: products processed in each bounded batch; default `50`.
- `start_batch`: zero-based batch index; default `0`.
- `max_batches`: maximum batches in the workflow run; `0` means all remaining.
- `ebay_limit`: maximum eBay listings requested per product; default `10`, allowed `1–200`.

The eBay limit controls listing depth, not the number of products.

## Outputs

`data/operations/mtg_full_marketplace/`

- `full_product_map.csv`
- `full_product_map_summary.json`
- `latest.json`
- `checkpoint.json`
- `normalized_marketplace_observations.csv`
- `batches/batch_NNNN/product_map.csv`
- `batches/batch_NNNN/latest.json`
- per-batch lane and normalized outputs

## Production workflow

Run `.github/workflows/mtg-full-marketplace-universe.yml` manually.

Recommended first live run:

- live execution: `true`
- batch size: `50`
- start batch: `0`
- max batches: `0`
- eBay limit: `10`

The workflow has a six-hour timeout and uploads all evidence even when a later batch fails. A partial run reports the next batch and preserves completed batch evidence in the artifact.

## Authority boundary

This phase expands MTG source intelligence only. UIP remains the sole cross-domain allocation and future scheduling authority.
