# Phase 10.5R.1C.1 - Universal Investment Platform Mapping

## Purpose

This document defines how the canonical MTG product registry aligns with
the Universal Investment Intelligence Platform.

The canonical MTG registry is a native-platform identity registry.

It is not the Universal database and must not write directly to the
Universal platform database.

MTG data will be published through the Universal Integration Package
contract and imported through the Universal Import Engine.

## System boundaries

### MTG platform owns

The MTG platform owns:

- native TCGCSV discovery;
- TCGplayer product identity;
- MTG product classification;
- Secret Lair granularity;
- packaging granularity;
- MTG-specific approval workflows;
- MTG-specific scoring;
- native price history;
- native forecasts;
- native recommendations; and
- Universal export generation.

### Universal platform owns

The Universal platform owns:

- package validation;
- universal contract validation;
- platform registration;
- atomic import;
- duplicate-package rejection;
- universal asset identity;
- cross-asset portfolio intelligence;
- universal scoring orchestration;
- universal forecasting orchestration;
- decision intelligence; and
- the Universal DuckDB database.

## Canonical registry role

The canonical registry provides the authoritative native identity layer for
MTG products.

Each row represents one source-distinct MTG product identity.

The registry separates four concepts:

1. Product identity
2. Investment eligibility
3. Scoring state
4. Recommendation state

A product may exist canonically without being approved, scored, or
recommended.

## Canonical-to-universal identity mapping

The canonical registry maps to Universal `asset_master` as follows:

| Canonical MTG field | Universal field | Mapping rule |
|---|---|---|
| `canonical_product_id` | `source_asset_id` | Stable native MTG identity |
| `tcgplayer_product_id` | `external_asset_id` | TCGplayer source identifier |
| `canonical_product_name` | `asset_name` | Canonical MTG display name |
| `canonical_set_name` | `issuer_or_collection` | MTG set, drop, or product group |
| `canonical_product_class` | `asset_subclass` | Sealed product or Secret Lair product |
| `canonical_product_family` | `asset_category_detail` | Booster display, Secret Lair, bundle, deck, or case |
| `canonical_product_type` | `instrument_type` | Specific MTG product subtype |
| `canonical_packaging_level` | native metadata | Case, display, bundle, deck, card, or insert |
| `language` | native metadata | Language identity dimension |
| `foil_variant` | native metadata | Foil identity dimension |
| `edition_variant` | native metadata | Edition identity dimension |
| `investment_eligibility_status` | eligibility metadata | Native eligibility state |
| `investment_approval_status` | approval metadata | Native approval state |
| `source_lineage` | lineage metadata | Native source and reconciliation trace |

The universal asset class should be:

`collectible`

The universal asset subclass should distinguish at minimum:

- `mtg_sealed_product`
- `mtg_secret_lair_product`

## Universal asset identifier

The Universal platform should generate or maintain its own universal asset
identifier.

The MTG canonical ID must remain stored as the native source identity.

Recommended relationship:

- Universal identity: Universal-platform controlled
- Platform ID: `mtg-investment-terminal`
- Source asset ID: canonical MTG product ID
- External source ID: TCGplayer product ID

The Universal platform must not replace the canonical MTG ID with a
Universal-generated ID inside the native MTG registry.

## Export eligibility

Canonical identity alone does not imply that a row should receive forecasts,
recommendations, or portfolio allocation.

### Asset-master export

All canonical identities may eventually be exported to Universal
`asset_master` when the export contract permits identity-only assets.

Identity-only exports should clearly preserve:

- approval status;
- eligibility status;
- scoring status; and
- data-availability status.

### Forecast export

A canonical product should enter `forecasts.csv` only when:

- it has sufficient native price history;
- the MTG forecasting engine supports the product type;
- forecast validation passes;
- the forecast has a defined as-of date;
- the forecast horizon is supported; and
- forecast lineage is complete.

### Recommendation export

A canonical product should enter `recommendations.csv` only when:

- the product is investment eligible;
- required scoring is complete;
- recommendation constraints pass;
- the recommendation has an explicit status;
- evidence and rationale are available; and
- the recommendation is not merely inferred from canonical inclusion.

### Risk-metric export

A canonical product should enter `risk_metrics.csv` only when the required
native price and liquidity data exist.

## Package structure

The MTG Universal export package must follow the Universal Integration
Package Standard.

Required files:

- `export_manifest.csv`
- `platform_status.csv`

Supported MTG datasets may include:

- `asset_master.csv`
- `forecasts.csv`
- `recommendations.csv`
- `risk_metrics.csv`
- `portfolio_positions.csv`
- native audit files
- package metadata files

The native MTG platform must not write directly to Universal DuckDB.

## Package identity

Every MTG package must include:

- `platform_id`
- `package_id`
- `run_id`
- `adapter_version`
- `contract_version`
- `generated_at_utc`

Recommended platform identity:

`mtg-investment-terminal`

The package ID and run ID must be unique for each export execution.

## Manifest requirements

Each exported dataset must be recorded in `export_manifest.csv` with:

- package ID;
- platform ID;
- run ID;
- adapter version;
- contract version;
- dataset name;
- filename;
- row count;
- file size;
- SHA-256 checksum;
- generation timestamp;
- required status; and
- validation status.

## Row-level lineage

Every exported MTG row must remain traceable to:

- canonical MTG product ID;
- TCGplayer product ID;
- candidate record ID;
- native source snapshot;
- package ID;
- platform ID;
- source filename;
- source row number;
- export timestamp; and
- manifest checksum after Universal import.

The canonical registry's `source_lineage` field is native lineage.

Universal import lineage should supplement, not replace, native lineage.

## Approval boundary

The existing 234 approved investment products retain their current native
approval status.

The remaining 5,005 canonical identities are not universally approved by
virtue of inclusion in the canonical registry.

This includes:

- 4,440 existing review-required records; and
- 565 newly discovered identities.

Universal ingestion must preserve that distinction.

## Secret Lair handling

All 4,347 Secret Lair product-level identities remain valid canonical
identities.

Universal mappings must not collapse them into one generic Secret Lair asset.

The following should remain distinguishable where present:

- card-or-product records;
- card variants;
- bundles or kits;
- inserts; and
- cases.

Universal analytics may aggregate these records for reporting, but the source
identity must remain product-specific.

## Packaging handling

Cases, displays, bundles, decks, cards, and inserts remain separate source
identities.

The Universal platform may group them into broader analytical families, but
must not merge distinct TCGplayer product IDs into one source identity.

## Refresh policy

The canonical registry should be rebuilt from reproducible TCGCSV source
snapshots.

A refresh should:

1. discover the current TCGCSV universe;
2. reconcile candidates against the prior canonical registry;
3. preserve stable canonical IDs;
4. identify new source identities;
5. identify removed or unavailable source identities;
6. detect source-name or classification changes;
7. produce a review queue for true identity conflicts;
8. certify uniqueness and lineage; and
9. publish a new version only after validation.

## Supersession policy

Canonical records should not be silently deleted when a source product
disappears.

Future governance should support statuses such as:

- active
- source_unavailable
- superseded
- merged_after_review
- retired
- identity_review_required

Any merge or supersession must preserve historical lineage.

## Current integration status

At completion of Phase 10.5R.1C.1:

- canonical identity registry: complete;
- Universal mapping: defined;
- production MTG registry: unchanged;
- Universal package generation: not yet rerun;
- canonical identities imported into Universal platform: no;
- eligibility recalculated: no;
- scoring applied to new identities: no;
- forecasts generated for new identities: no;
- recommendations generated for new identities: no.

## Next integration work

The next implementation work should:

1. formalize canonical-registry governance;
2. map eligible canonical identities into the MTG Universal export adapter;
3. preserve identity-only records separately from forecast-ready records;
4. update package validation tests;
5. generate a new MTG Universal integration package;
6. validate it in the MTG repository;
7. import it through the Universal Import Engine; and
8. verify cross-platform lineage and duplicate protection.