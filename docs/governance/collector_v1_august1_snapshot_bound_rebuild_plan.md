# Collector V1 August 1 Snapshot-Bound Current Product Rebuild

## Status

Implementation block authorized from certified snapshot commit `cb1cad762d75b704a776733f4536398473cda2da`.

## Governing snapshot

- Snapshot ID: `collector-20260801T211201Z-7688afbd`
- Operating date: `2026-08-01`
- Operating timezone: `America/Chicago`
- Model rebuild authorized: `true`
- Purchase recommendations authorized: `false`

## Required execution order

1. Verify the certified snapshot manifest and all registered source hashes.
2. Activate the August 1 authority record for model input only.
3. Build the current-product authority directly from the named certified authorities.
4. Certify all governed product rows or block them explicitly.
5. Run forecasts and rankings only after the current-product foundation passes.
6. Run purchase adequacy only after forecasts and rankings pass.
7. Compare invalidated and rebuilt outputs.
8. Run final lineage and recommendation certification.

## Mandatory lineage fields

Every rebuilt product-level artifact must include:

- `source_snapshot_id`
- `source_bundle_sha256`
- `source_price_authority_sha256`
- `source_listing_authority_sha256`
- `source_feature_authority_sha256`
- `model_generated_at_utc`

## Fail-closed conditions

Execution must fail when:

- the snapshot ID differs from the certified snapshot;
- a registered authority path is missing;
- an authority hash differs from the snapshot manifest;
- a current price does not trace to the certified August 1 price authority;
- a governed product identity is missing or mismatched;
- current listing counts do not trace to the certified eBay authorities;
- a generated date is substituted for an observation date;
- a historical record is substituted for a current record;
- a product silently disappears from the governed universe.

## Authorization boundary

This block activates data for controlled model input only. It does not reinstate prior rankings, maximum purchase prices, purchase recommendations, production forecasting, or UIP delivery.
