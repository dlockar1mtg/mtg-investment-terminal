# Phase 10.5R.1C.1 - Canonical MTG Product Registry

## Status

**PASS - CANONICAL PRODUCT IDENTITY REGISTRY COMPLETE**

## Purpose

Phase 10.5R.1C.1 constructs a canonical MTG product-identity registry from
the reconciled Premium MTG Candidate Universe.

The registry creates one stable canonical identity for each discovered
TCGplayer product while preserving:

- source identifiers;
- existing investment-registry relationships;
- packaging granularity;
- Secret Lair product-level granularity;
- approval and eligibility separation;
- scoring separation; and
- source lineage.

This phase does not replace or mutate the existing production investment
registry.

## Inputs

The canonical registry was constructed from:

- the 5,239-row Premium MTG Candidate Universe;
- the 5,239-row TCGCSV reconciliation output; and
- the existing 4,675-row investment-product registry.

## Canonical registry totals

The completed canonical registry contains:

- Canonical product identities: 5,239
- Unique canonical product identifiers: 5,239
- Unique TCGplayer product identifiers: 5,239
- Established existing identities: 4,674
- New source identities: 565
- Identity-review records: 0
- Duplicate canonical identifiers: 0
- Duplicate TCGplayer identifiers: 0

## Product classes

The canonical universe contains:

- Secret Lair products: 4,347
- Sealed products: 892

All Secret Lair records remain included.

The Secret Lair identity breakdown is:

- Established existing identities: 4,326
- New source identities: 21

## New canonical identities

The 565 new source identities consist of:

- Commander decks: 210
- Bundles: 173
- Sealed cases: 115
- Play Booster Displays: 20
- Set Booster Displays: 18
- Secret Lair card-or-product records: 15
- Secret Lair card variants: 5
- Traditional Booster Displays: 4
- Collector Booster Displays: 4
- Secret Lair bundle or kit: 1

Every new identity remains:

- investment approval status: `review_required`
- investment eligibility status: `not_evaluated`
- scoring status: `not_scored`

No new identity was automatically approved, scored, or recommended.

## Existing-registry preservation

The 4,674 exact-ID relationships preserve the existing investment-registry
information.

Existing approval-status distribution:

- Approved: 234
- Review required: 4,440

The canonical registry does not reinterpret those approval decisions.

It records them as historical investment-registry attributes while keeping
canonical identity independent from approval and eligibility.

## Canonical identity structure

Each canonical product includes:

- stable canonical product ID;
- canonical registry version;
- identity status;
- canonical set and product names;
- product class, family, and type;
- packaging level;
- language;
- foil variant;
- edition variant;
- TCGplayer product ID;
- TCGCSV category and group IDs;
- candidate record ID;
- reconciliation status;
- type alignment;
- existing investment-registry relationship;
- investment eligibility and approval states;
- scoring state; and
- serialized source lineage.

Canonical IDs use the TCGplayer product identifier where available:

`MTG-CANON-TCGPLAYER-<tcgplayer_product_id>`

This provides deterministic identity across rebuilds.

## Packaging granularity

The canonical registry preserves product packaging rather than collapsing
cases, displays, bundles, decks, and individual Secret Lair records into a
single generic product class.

Packaging-level counts are:

- Individual card or variant: 4,005
- Bundle: 376
- Case: 352
- Display: 279
- Deck: 200
- Individual card insert: 27

The 90 previously reconciled case-packaging relationships remain canonically
classified as cases.

## Secret Lair granularity

Secret Lair records remain represented at the product level available from
TCGCSV.

This includes:

- individual cards or product records;
- card variants;
- bundles or kits;
- inserts; and
- case-level records.

No Secret Lair record was excluded merely because the existing investment
registry used a broader Secret Lair label.

## Identity review

The identity-review queue contains zero records.

Every candidate has:

- a unique canonical identity;
- a unique TCGplayer product ID;
- a completed reconciliation status; and
- an accepted canonical type relationship.

An empty identity-review queue does not imply investment approval.

Identity completion and investment approval remain separate controls.

## Safety controls

Phase 10.5R.1C.1 made no changes to:

- the production investment registry;
- investment eligibility;
- approval decisions;
- scoring;
- recommendations; or
- the production database.

The canonical registry is currently a staged identity artifact.

## Generated artifacts

The phase generated:

- `canonical_mtg_product_registry_2026-07-22.csv`
- `canonical_registry_new_products_2026-07-22.csv`
- `canonical_registry_identity_review_queue_2026-07-22.csv`
- `canonical_registry_summary_2026-07-22.json`

The redundant full existing-products subset was intentionally not retained,
because those rows are already present in the canonical registry.

## Validation

Automated tests confirmed:

- 5,239 canonical registry rows;
- 5,239 unique canonical IDs;
- 5,239 unique TCGplayer IDs;
- 5,239 unique candidate record IDs;
- 4,674 established existing identities;
- 565 new source identities;
- all 4,347 Secret Lair records remain included;
- all new identities remain unapproved and unscored;
- existing approval information is preserved;
- all case-packaging relationships remain cases;
- source-lineage values contain valid JSON;
- the identity-review queue is empty;
- the production registry remains at 4,675 rows; and
- no platform mutation occurred.

Test results:

- Canonical-registry tests: 10 passed
- External-discovery tests: 39 passed
- Full repository tests: 185 passed
- Existing warnings: 13

## Certification decision

Phase 10.5R.1C.1 is certified complete because:

1. every discovered candidate has one unique canonical identity;
2. exact source identifiers are preserved;
3. Secret Lair product granularity is retained;
4. packaging granularity is retained;
5. existing approval information is preserved;
6. new identities are not automatically approved;
7. identity and investment eligibility remain separate;
8. source lineage is retained;
9. no unresolved identity conflicts remain; and
10. all automated tests passed.

## Next phase

**Phase 10.5R.1C.2 - Canonical Registry Governance and Universal Mapping**

The next phase will define:

- canonical-registry lifecycle states;
- identity-update and supersession policy;
- source-conflict handling;
- approval and eligibility boundaries;
- mapping from canonical MTG identities to Universal `asset_master`;
- package lineage and refresh rules; and
- controlled promotion from staging to production use.