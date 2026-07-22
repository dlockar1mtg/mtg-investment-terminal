# Phase 10.5R.1D.1 - Premium Universe Structural Eligibility Audit

## Status

**PASS - STRUCTURAL ELIGIBILITY AUDIT COMPLETE**

## Purpose

Phase 10.5R.1D.1 establishes the structural eligibility boundary for the
premium MTG investment universe.

This phase identifies products that structurally match the user's
investment interests while preserving strict separation between:

- canonical identity;
- structural eligibility;
- final investment eligibility;
- investment approval;
- scoring;
- recommendation generation; and
- Universal investability.

## Approved investment strategy

The structural eligibility framework reflects the following requirements:

### Included for further consideration

- Collector Booster displays and boxes;
- sealed Secret Lair drops;
- sealed single-card Secret Lair drops;
- sealed multi-card Secret Lair drops;
- sealed Secret Lair bundles and kits;
- qualifying historical premium booster displays; and
- qualifying Draft Booster displays after historical review.

### Excluded

- all case-level products;
- Commander decks;
- Secret Lair Commander decks;
- ordinary bundles;
- Play Booster displays;
- Set Booster displays;
- Theme Booster displays;
- Jumpstart Booster displays;
- individual Secret Lair cards opened from drops;
- separately listed Secret Lair card variants;
- Secret Lair inserts;
- loose products; and
- ordinary mass-market sealed products.

## Secret Lair eligibility boundary

Secret Lair eligibility is based on sealed-product status rather than card
count.

A sealed Secret Lair product may qualify whether it contains one card or
multiple cards.

An individual card removed from a Secret Lair drop is not eligible.

A separately listed card variant or insert is not eligible.

## Case exclusion

All case-level products are excluded because their purchase price is not
expected to fit the user's monthly MTG investment allocation.

Case exclusion applies regardless of product quality or historical
performance.

## Structural audit results

The governed canonical registry contained:

- 5,239 canonical identities;
- 5,239 unique canonical product IDs.

The structural audit classified:

- 307 structurally eligible candidates;
- 4,769 structurally ineligible products;
- 163 historical-review products;
- 0 unresolved classification-review products.

## Structural candidates

The 307 structural candidates consist of:

- 53 Collector Booster displays;
- 254 sealed Secret Lair bundles or kits.

These records are structural candidates only.

They have not yet been assigned final investment eligibility.

## Historical review queue

The 163-product historical review queue consists of:

- 138 traditional booster displays;
- 25 Draft Booster displays.

Historical review is required because structural product type alone does
not establish premium investment suitability.

Future review should consider:

- product age;
- release generation;
- historical price coverage;
- current acquisition price;
- scarcity;
- print-run or supply evidence;
- long-term liquidity;
- historical appreciation;
- affordability within the monthly allocation; and
- whether the product was a genuinely premium release.

## Structural exclusions

The audit excluded products including:

- 352 case-level products;
- 194 Commander decks;
- 122 ordinary bundles;
- 20 Play Booster displays;
- 18 Set Booster displays;
- 14 Theme Booster displays;
- 11 Jumpstart Booster displays;
- 2,371 individual Secret Lair cards;
- 1,635 separately listed Secret Lair variants;
- 27 Secret Lair inserts; and
- 5 Secret Lair Commander decks.

## Generated artifacts

The phase generates:

- `premium_universe_eligibility_audit_2026-07-22.csv`
- `premium_universe_structural_candidates_2026-07-22.csv`
- `premium_universe_structural_exclusions_2026-07-22.csv`
- `premium_universe_eligibility_review_queue_2026-07-22.csv`
- `secret_lair_structural_candidates_2026-07-22.csv`
- `historical_booster_review_2026-07-22.csv`
- `sealed_product_classification_review_2026-07-22.csv`
- `premium_universe_eligibility_summary_2026-07-22.json`

All focused outputs are generated reproducibly by the Python audit script.

## Safety controls

This phase did not:

- change the canonical registry;
- change the governed registry;
- change the production investment registry;
- assign final eligibility;
- assign investment approval;
- enable scoring;
- generate recommendations;
- create a Universal integration package;
- update Universal investability; or
- modify the Universal database.

All 5,239 products remain:

- `final_eligibility_decision=not_decided`
- `scoring_allowed=false`
- `universal_investable_allowed=false`

## Automated validation

Validation completed successfully:

- Phase-specific tests: 16 passed;
- external-discovery tests: 86 passed;
- full repository tests: 232 passed;
- existing warnings: 13;
- staged-content check: not yet performed;
- whitespace validation: passed.

## Certification decision

Phase 10.5R.1D.1 is certified complete because:

1. the user's investment constraints are represented explicitly;
2. case-level products are excluded;
3. sealed Secret Lair products remain distinct from opened singles;
4. Commander decks and mass-market sealed formats are excluded;
5. Collector Booster displays are retained;
6. historical booster products are placed into review rather than
   automatically accepted;
7. all previously unclassified sealed products have been resolved;
8. focused output files are reproducible;
9. no premature eligibility or scoring was applied; and
10. all automated tests pass.

## Next phase

**Phase 10.5R.1D.2 - Historical Premium Eligibility Resolution**

The next phase will evaluate the 163 historical-review booster displays
against premium-product, affordability, scarcity, liquidity, age, and
historical-performance criteria.