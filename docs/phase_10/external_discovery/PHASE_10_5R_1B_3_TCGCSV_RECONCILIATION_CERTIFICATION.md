# Phase 10.5R.1B.3 - TCGCSV Candidate Reconciliation

## Status

**PASS - TCGCSV CANDIDATE RECONCILIATION COMPLETE**

## Purpose

Phase 10.5R.1B.3 reconciles the 5,239-record Premium MTG Candidate
Universe against the existing 4,675-row investment-product registry.

The reconciliation determines whether each TCGCSV candidate:

- already exists in the registry by exact TCGplayer product identifier;
- represents a newly discovered candidate;
- requires normalized-name matching;
- contains an ambiguous relationship;
- has a packaging or product-type difference; or
- requires manual review.

This phase does not approve candidates, modify eligibility, apply scores,
create recommendations, change registry records, or alter the database.

## Inputs

The reconciliation used:

- `tcgcsv_premium_candidate_universe_2026-07-22.csv`
- `data/product_master/investment_products.csv`

Input totals were:

- Premium MTG candidate rows: 5,239
- Existing registry rows: 4,675
- Unique candidate record identifiers: 5,239
- Unique candidate TCGplayer identifiers: 5,239

## Reconciliation results

All 5,239 candidate records were reconciled.

The final reconciliation outcomes were:

- Exact TCGplayer-ID matches: 4,674
- New candidates: 565
- Normalized-name matches: 0
- Ambiguous matches: 0
- Missing candidate identifiers: 0
- Unresolved review records: 0

The 565 newly discovered candidates consist of:

- 544 sealed-product candidates
- 21 Secret Lair product-level candidates

## Secret Lair preservation

The Premium MTG Candidate Universe contains 4,347 Secret Lair
product-level records.

Of those records:

- 4,326 match existing registry records by exact TCGplayer identifier;
- 21 are newly discovered candidates; and
- all 4,347 remain included in the candidate universe.

A total of 4,072 existing Secret Lair records use a broader registry type
than the candidate-level classification. These records were classified as:

`compatible_registry_generic_secret_lair`

This status preserves the exact-ID relationship without treating the
registry's broader Secret Lair label as an unresolved conflict.

No Secret Lair candidate was excluded because of registry granularity.

## Generic booster-display compatibility

A total of 27 exact-ID records use a more specific candidate booster-display
subtype than the existing registry.

These records consist of:

- 14 Theme Booster Displays
- 11 Jumpstart Booster Displays
- 2 Draft Booster Displays mapped to the broader Masters or Traditional
  Booster Display registry classification

These records were classified as:

`compatible_registry_generic_booster_display`

They remain included and do not require manual review.

## Case-packaging compatibility

A total of 90 exact-ID records are clearly case-level products but use a
broader booster-display classification in the existing registry.

The candidate names explicitly identify packaging such as:

- Booster Box Case
- Draft Booster Box Case
- Collector Booster Case
- Theme Booster Display Box Case
- Jumpstart Booster Box Case

These records were classified as:

`compatible_registry_generic_case_packaging`

This preserves the case-level candidate classification without modifying
the existing registry during reconciliation.

## Final type alignment

The final type-alignment totals were:

- Compatible generic Secret Lair: 4,072
- Directly compatible: 485
- Compatible generic case packaging: 90
- Compatible generic booster display: 27
- Not applicable for new candidates: 565
- Unresolved type conflicts: 0

## Review queue

The final review queue contains zero records.

The conflict export also contains zero records.

All previously observed differences were resolved as explicit,
deterministic compatibility relationships rather than being removed from
the candidate universe.

## Safety and mutation controls

Phase 10.5R.1B.3 made no changes to:

- eligibility status;
- approval status;
- scoring;
- recommendation generation;
- the existing investment-product registry; or
- the production database.

The reconciliation is an analytical staging and validation process only.

## Generated outputs

The phase generated:

- full candidate reconciliation;
- exact-ID match export;
- normalized-name match export;
- new-candidate export;
- ambiguous-match export;
- type-conflict export;
- reconciliation review queue; and
- reconciliation summary.

## Validation

Automated validation confirmed:

- all 5,239 candidate rows reconcile exactly once;
- all candidate identifiers remain unique;
- all 4,347 Secret Lair records remain included;
- all 4,072 generic Secret Lair relationships are exact-ID matches;
- all 27 generic booster-display relationships are exact-ID matches;
- all 90 case-packaging relationships are exact-ID matches;
- the new-candidate total is 565;
- the new-candidate class breakdown is 544 sealed products and
  21 Secret Lair products;
- the review queue is empty;
- the conflict export is empty; and
- no platform mutation occurred.

Test results:

- Phase reconciliation tests: 8 passed
- External-discovery tests: 29 passed
- Full repository tests: 175 passed
- Existing warnings: 13

## Certification decision

Phase 10.5R.1B.3 is certified complete because:

1. every candidate was reconciled;
2. exact source identifiers were prioritized;
3. no ambiguous candidate relationships remain;
4. all Secret Lair candidates remain included;
5. case and booster-display packaging differences are explicitly preserved;
6. all new candidates remain unapproved and unscored;
7. no registry or database mutation occurred; and
8. all automated tests passed.

## Next phase

**Phase 10.5R.1C - Canonical Product Registry**

The next phase will use the reconciled candidate universe to construct a
canonical MTG product registry that:

- preserves existing registry records;
- incorporates the 565 newly discovered candidates;
- retains source lineage;
- separates product identity from investment eligibility;
- preserves packaging granularity;
- distinguishes sealed products from Secret Lair card-level products; and
- creates a controlled review and approval framework.